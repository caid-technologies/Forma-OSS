"""The first-party ``forma-oss`` command line application."""

from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path
import sys
import time
import webbrowser
from typing import Any

from forma_core import __version__
from forma_cli.config import api_url, load_linkage
from forma_cli.credentials import CredentialStore, CredentialStoreError
from forma_cli.local import (
    LOCAL_PROVIDER_ENVIRONMENT,
    LocalProjectError,
    build_project,
    import_project,
    init_project,
    project_root,
    read_project,
    status_project,
    update_linkage,
)
from forma_cli.metadata_api import project_metadata, serve_metadata_api
from forma_cli.sdk import FormaAPIClient, FormaAPIError


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, default=str))


def _client(args: argparse.Namespace) -> FormaAPIClient:
    return FormaAPIClient(base_url=args.api_url if getattr(args, "api_url", None) else None)


def cmd_login(args: argparse.Namespace) -> int:
    client = _client(args)
    authorization = client.request_device_authorization()
    print("Opening Forma in your browser...")
    print(f"If the browser does not open, visit: {authorization.verification_uri}")
    if not args.no_browser:
        webbrowser.open(authorization.verification_uri)
    print("Waiting for authorization...")
    deadline = time.monotonic() + authorization.expires_in
    while time.monotonic() < deadline:
        result = client.poll_device_authorization(authorization.device_code)
        if result.status == "approved":
            client.exchange_device_code(authorization.device_code)
            identity = client.whoami()
            account = identity.email or identity.display_name or identity.subject
            print(f"Logged in as {account}")
            if client._store.using_plaintext_fallback:
                print("WARNING: credentials stored in plaintext because the explicit fallback is enabled.")
            else:
                print("Credentials stored securely")
            return 0
        if result.status in {"expired", "denied"}:
            raise FormaAPIError(result.message or f"Device authorization {result.status}.")
        time.sleep(authorization.interval)
    raise FormaAPIError("Device authorization expired before it was approved.")


def cmd_logout(args: argparse.Namespace) -> int:
    _client(args).revoke()
    print("Logged out")
    return 0


def cmd_whoami(args: argparse.Namespace) -> int:
    identity = _client(args).whoami()
    if args.json:
        _print_json(identity.model_dump(mode="json"))
    else:
        print(identity.email or identity.display_name or identity.subject)
        print(f"Provider: {identity.provider}")
        print(f"API endpoint: {identity.api_url}")
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    manifest = init_project(args.path, title=args.title or "")
    print(f"Initialized Forma project {manifest.project_id}")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    manifest = build_project(
        args.path,
        prompt=args.prompt,
        workflow=args.workflow,
        provider=args.provider,
        model=args.model,
        simulation=args.simulation,
        assembly_step=args.assembly_step,
    )
    print(
        f"Built {manifest.title or manifest.project_id}, persisted {manifest.project_id} to Forma DB, "
        f"at {project_root(args.path) / 'forma-project.json'}"
    )
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    source_path = Path(args.source).expanduser()
    destination = Path(args.path).expanduser() if args.path else (
        source_path if source_path.is_dir() else source_path.parent
    )
    manifest = import_project(
        args.source,
        destination=destination,
        assembly_step=args.assembly_step,
        preview_stl=args.preview_stl,
    )
    print(
        f"Imported {manifest.title or manifest.project_id}, persisted {manifest.project_id} to Forma DB, "
        f"at {destination / 'forma-project.json'}"
    )
    return 0


def cmd_metadata(args: argparse.Namespace) -> int:
    payload = project_metadata(args.path)
    if args.json:
        _print_json(payload)
    else:
        print(f"Project: {payload['title'] or payload['project_id']}")
        print(f"Project ID: {payload['project_id']}")
        print(f"Database: {'present' if payload['database']['present'] else 'missing'}")
        print(f"CAD: {payload['cad']['meshes']} mesh(es), {payload['cad']['mesh_vertices']} vertices")
        print(f"Components: {payload['hardware']['components']}")
        print(f"Placements: {payload['hardware']['placements']}")
        print(f"Valid: {'yes' if payload['valid'] else 'no'}")
    return 0


def cmd_metadata_api(args: argparse.Namespace) -> int:
    print(f"Serving project metadata at http://{args.host}:{args.port}/metadata")
    serve_metadata_api(args.path, args.host, args.port)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    payload = status_project(args.path)
    if args.json:
        _print_json(payload)
    else:
        print(f"Project: {payload['title'] or payload['project_id']}")
        print(f"Path: {payload['path']}")
        print(f"Validation: {'ok' if payload['valid'] else 'failed'}")
        if payload.get("remote"):
            print(f"Remote: {payload['remote']}")
            print(f"Revision: {payload.get('revision_id') or 'none'}")
    return 0 if payload["valid"] else 1


def cmd_render(args: argparse.Namespace) -> int:
    from forma_core.terminal.dashboard import DashboardRenderConfig, render_dashboard_image

    root = project_root(args.path)
    manifest = read_project(root)
    output = Path(args.output).expanduser()
    if not output.is_absolute():
        output = root / output
    render_dashboard_image(
        manifest.project_ir,
        output,
        config=DashboardRenderConfig(
            width=args.width,
            height=args.height,
            scene_yaw_degrees=args.yaw,
            scene_label="FORMA OSS / CLI RENDER",
        ),
    )
    print(f"Rendered {manifest.title or manifest.project_id} at {output}")
    return 0


def cmd_projects_list(args: argparse.Namespace) -> int:
    projects = _client(args).list_projects()
    if args.json:
        _print_json([project.model_dump(mode="json") for project in projects])
    else:
        for project in projects:
            revision = project.revision_id or "no revisions"
            print(f"{project.project_id}\t{project.title or 'Untitled'}\t{revision}")
    return 0


def _confirm_push(args: argparse.Namespace, manifest: Any) -> bool:
    output = sys.stderr if args.json else sys.stdout
    artifacts = list(getattr(manifest, "artifacts", []) or [])
    print(f"This will upload the private project manifest and {len(artifacts)} referenced artifact(s).", file=output)
    for artifact in artifacts:
        print(f"  - {artifact.path}", file=output)
    print("Provider credentials and authentication tokens are excluded.", file=output)
    if args.yes:
        return True
    if args.json:
        print("Continue? [y/N] ", end="", file=output, flush=True)
        answer = input().strip().lower()
    else:
        answer = input("Continue? [y/N] ").strip().lower()
    return answer in {"y", "yes"}


def cmd_projects_push(args: argparse.Namespace) -> int:
    root = project_root(args.path)
    manifest = read_project(root)
    if not _confirm_push(args, manifest):
        print("Upload cancelled.")
        return 1
    linkage = load_linkage(root)
    revision = _client(args).push_project(
        manifest.upload_payload(),
        parent_revision_id=linkage.get("revision_id"),
    )
    update_linkage(
        root,
        version=1,
        remote=args.api_url.rstrip("/") if args.api_url else api_url(),
        remote_project_id=revision.project_id,
        project_id=manifest.project_id,
        revision_id=revision.revision_id,
        parent_revision_id=revision.parent_revision_id,
        manifest_digest=_manifest_digest(manifest.upload_payload()),
    )
    payload = revision.model_dump(mode="json")
    if args.json:
        _print_json(payload)
    else:
        print(f"Uploaded private project {revision.project_id} revision {revision.revision_id}")
    return 0


def cmd_projects_pull(args: argparse.Namespace) -> int:
    root = project_root(args.path)
    linkage = load_linkage(root)
    remote_project_id = args.project_id or linkage.get("remote_project_id") or linkage.get("project_id")
    if not remote_project_id:
        raise LocalProjectError("No remote project is linked. Push this project first or pass --project-id.")
    revision = _client(args).pull_project(remote_project_id, args.revision_id)
    current_revision = linkage.get("revision_id")
    if current_revision and current_revision != revision.revision_id:
        local_manifest = read_project(root)
        if linkage.get("manifest_digest") and _manifest_digest(local_manifest.upload_payload()) != linkage["manifest_digest"]:
            raise LocalProjectError(
                "Local changes diverge from the linked cloud revision; refusing to overwrite them."
            )
        if revision.parent_revision_id not in {current_revision, None}:
            raise LocalProjectError(
                "Cloud revision ancestry diverges from the linked local revision; refusing to overwrite it."
            )
    from forma_core.workspaces.projects.manifest import ProjectManifest, write_project_manifest

    manifest = ProjectManifest.from_document(revision.manifest)
    write_project_manifest(root / "forma-project.json", manifest)
    update_linkage(
        root,
        remote=args.api_url.rstrip("/") if args.api_url else api_url(),
        remote_project_id=revision.project_id,
        project_id=manifest.project_id,
        revision_id=revision.revision_id,
        parent_revision_id=revision.parent_revision_id,
        manifest_digest=_manifest_digest(manifest.upload_payload()),
    )
    if args.json:
        _print_json(revision.model_dump(mode="json"))
    else:
        print(f"Pulled private project {revision.project_id} revision {revision.revision_id}")
    return 0


def _manifest_digest(value: Any) -> str:
    import hashlib

    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _local_key_rows(store: CredentialStore) -> list[dict[str, Any]]:
    rows = []
    for provider in sorted(LOCAL_PROVIDER_ENVIRONMENT):
        try:
            configured = bool(store.get(f"provider:{provider}"))
        except CredentialStoreError:
            configured = False
        rows.append({"provider": provider, "scope": "local", "configured": configured})
    return rows


def cmd_keys_list(args: argparse.Namespace) -> int:
    rows: list[dict[str, Any]] = []
    if args.scope in {"local", "both"}:
        rows.extend(_local_key_rows(CredentialStore()))
    if args.scope in {"cloud", "both"}:
        rows.extend(
            {**key.model_dump(mode="json"), "scope": "cloud"}
            for key in _client(args).list_keys()
        )
    if args.json:
        _print_json(rows)
    else:
        for row in rows:
            masked = row.get("masked_value") or ("configured" if row.get("configured") else "not configured")
            print(f"{row['scope']}\t{row['provider']}\t{masked}")
    return 0


def cmd_keys_set(args: argparse.Namespace) -> int:
    if args.scope == "local" and args.provider not in LOCAL_PROVIDER_ENVIRONMENT:
        raise ValueError(
            f"Unknown local provider {args.provider!r}. Supported providers: "
            + ", ".join(sorted(LOCAL_PROVIDER_ENVIRONMENT))
        )
    value = args.value or getpass.getpass("Provider key (input hidden): ")
    if args.scope == "local":
        CredentialStore().set(f"provider:{args.provider}", value)
        print(f"Stored {args.provider} in the OS credential store for local generation.")
    else:
        result = _client(args).set_key(args.provider, value, label=args.label)
        print(f"Stored managed {result.provider} credential {result.credential_id or result.label or ''}".rstrip())
    return 0


def cmd_keys_remove(args: argparse.Namespace) -> int:
    if args.scope == "local" and args.provider not in LOCAL_PROVIDER_ENVIRONMENT:
        raise ValueError(
            f"Unknown local provider {args.provider!r}. Supported providers: "
            + ", ".join(sorted(LOCAL_PROVIDER_ENVIRONMENT))
        )
    if args.scope == "local":
        CredentialStore().delete(f"provider:{args.provider}")
        print(f"Removed local {args.provider} credential.")
    else:
        _client(args).remove_key(args.provider)
        print(f"Removed managed {args.provider} credential.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="forma-oss", description="Local-first Forma project CLI.")
    parser.add_argument("--api-url", default=None, help="Forma API endpoint; defaults to local config or FORMA_API_URL.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    login = subparsers.add_parser("login", help="Authenticate with browser/device authorization.")
    login.add_argument("--no-browser", action="store_true", help="Print the approval URL without opening a browser.")
    login.set_defaults(func=cmd_login)
    logout = subparsers.add_parser("logout", help="Revoke the CLI session and remove local credentials.")
    logout.set_defaults(func=cmd_logout)
    whoami = subparsers.add_parser("whoami", help="Show the signed-in account and API endpoint.")
    whoami.add_argument("--json", action="store_true")
    whoami.set_defaults(func=cmd_whoami)

    init = subparsers.add_parser("init", help="Create a local forma-project.json.")
    init.add_argument("path", nargs="?", default=".")
    init.add_argument("--title", default="")
    init.set_defaults(func=cmd_init)
    build = subparsers.add_parser("build", help="Generate or rebuild a project locally.")
    build.add_argument("prompt", nargs="?")
    build.add_argument("--path", default=".")
    build.add_argument("--workflow", default="default")
    build.add_argument("--provider")
    build.add_argument("--model")
    build.add_argument("--simulation", action="store_true")
    build.add_argument(
        "--assembly-step",
        help="Optional native STEP file; otherwise assembly.step is generated from the project layout.",
    )
    build.set_defaults(func=cmd_build)
    imported = subparsers.add_parser(
        "import",
        help="Import an existing generated HardwareIR project and its native CAD artifacts.",
    )
    imported.add_argument("source", help="Existing forma-project.json or its containing directory.")
    imported.add_argument("--path", default=None, help="Destination project directory; defaults to the source directory.")
    imported.add_argument("--assembly-step", help="Override the STEP artifact discovered from the source project.")
    imported.add_argument("--preview-stl", help="Override the STL preview discovered from the source project.")
    imported.set_defaults(func=cmd_import)
    metadata = subparsers.add_parser("metadata", help="Read local project and artifact metadata without the Forma API.")
    metadata.add_argument("--path", default=".")
    metadata.add_argument("--json", action="store_true")
    metadata.set_defaults(func=cmd_metadata)
    metadata_api = subparsers.add_parser("metadata-api", help="Serve local project metadata over a read-only HTTP API.")
    metadata_api.add_argument("--path", default=".")
    metadata_api.add_argument("--host", default="127.0.0.1")
    metadata_api.add_argument("--port", type=int, default=8765)
    metadata_api.set_defaults(func=cmd_metadata_api)
    status = subparsers.add_parser("status", help="Validate and show local/remote project state.")
    status.add_argument("--path", default=".")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=cmd_status)

    render = subparsers.add_parser("render", help="Render the local mechanical project layout to a PNG.")
    render.add_argument("--path", default=None)
    render.add_argument("--output", default="forma-render.png")
    render.add_argument("--width", type=int, default=1280)
    render.add_argument("--height", type=int, default=900)
    render.add_argument("--yaw", type=float, default=0.0)
    render.set_defaults(func=cmd_render)

    projects = subparsers.add_parser("projects", help="Manage explicit cloud project synchronization.")
    project_commands = projects.add_subparsers(dest="projects_command", required=True)
    projects_list = project_commands.add_parser("list", help="List private cloud projects.")
    projects_list.add_argument("--json", action="store_true")
    projects_list.set_defaults(func=cmd_projects_list)
    push = project_commands.add_parser("push", help="Upload the canonical local manifest explicitly.")
    push.add_argument("--path", default=".")
    push.add_argument("--yes", action="store_true", help="Confirm upload without prompting.")
    push.add_argument("--json", action="store_true")
    push.set_defaults(func=cmd_projects_push)
    pull = project_commands.add_parser("pull", help="Download an exact or latest linked revision.")
    pull.add_argument("--path", default=".")
    pull.add_argument("--project-id")
    pull.add_argument("--revision-id")
    pull.add_argument("--json", action="store_true")
    pull.set_defaults(func=cmd_projects_pull)

    keys = subparsers.add_parser("keys", help="Manage local or hosted provider credentials.")
    key_commands = keys.add_subparsers(dest="keys_command", required=True)
    keys_list = key_commands.add_parser("list", help="List credential metadata only.")
    keys_list.add_argument("--scope", choices=("local", "cloud", "both"), default="local")
    keys_list.add_argument("--json", action="store_true")
    keys_list.set_defaults(func=cmd_keys_list)
    keys_set = key_commands.add_parser("set", help="Store a provider credential.")
    keys_set.add_argument("provider")
    keys_set.add_argument("--scope", choices=("local", "cloud"), default="local")
    keys_set.add_argument("--value", help=argparse.SUPPRESS)
    keys_set.add_argument("--label")
    keys_set.set_defaults(func=cmd_keys_set)
    keys_remove = key_commands.add_parser("remove", help="Remove a provider credential.")
    keys_remove.add_argument("provider")
    keys_remove.add_argument("--scope", choices=("local", "cloud"), default="local")
    keys_remove.set_defaults(func=cmd_keys_remove)
    return parser


def app(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (CredentialStoreError, FormaAPIError, LocalProjectError, OSError, ValueError, RuntimeError) as exc:
        print(f"{parser.prog}: {exc}", file=sys.stderr)
        return 2


main = app


if __name__ == "__main__":
    raise SystemExit(app())
