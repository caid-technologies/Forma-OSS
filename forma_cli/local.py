"""Local project discovery and offline operations for ``forma-oss``."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from forma_core.config import config
from forma_core.workspaces.projects.manifest import (
    PROJECT_MANIFEST_FORMAT,
    ProjectManifest,
    load_project_manifest,
    write_project_manifest,
)

from forma_cli.config import load_linkage, save_linkage
from forma_cli.credentials import CredentialStore, CredentialStoreError


PROJECT_FILENAME = "forma-project.json"
STRICT_GENERATION_ENVIRONMENT = {
    "FORMA_DISABLE_GENERATION_FALLBACK": "true",
    "FORMA_STRICT_GENERATION": "true",
    "LLM_DISABLE_FALLBACK": "true",
}
SIMULATION_ENVIRONMENT = {
    "FORMA_DEV_MODE": "true",
    "FORMA_DISABLE_GENERATION_FALLBACK": "false",
    "FORMA_STRICT_GENERATION": "false",
    "LLM_DISABLE_FALLBACK": "false",
}
LOCAL_PROVIDER_ENVIRONMENT = {
    "anthropic": "ANTHROPIC_API_KEY",
    "baseten": "BASETEN_API_KEY",
    "cloudflare": "CLOUDFLARE_API_TOKEN",
    "firecrawl": "FIRECRAWL_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "gmi": "GMI_API_KEY",
    "huggingface": "HF_TOKEN",
    "nvidia": "NVIDIA_API_KEY",
    "openai": "OPENAI_API_KEY",
    "runpod": "RUNPOD_API_KEY",
    "tavily": "TAVILY_API_KEY",
    "together": "TOGETHER_API_KEY",
    "xai": "XAI_API_KEY",
}


class LocalProjectError(RuntimeError):
    """Raised when a local project cannot be read or safely updated."""


def project_root(path: str | Path | None = None) -> Path:
    start = Path(path or Path.cwd()).expanduser().resolve()
    if start.is_file():
        start = start.parent
    for candidate in (start, *start.parents):
        if (candidate / PROJECT_FILENAME).is_file():
            return candidate
    raise LocalProjectError(f"Could not find {PROJECT_FILENAME} from {start}.")


def project_path(path: str | Path | None = None) -> Path:
    return project_root(path) / PROJECT_FILENAME


def read_project(path: str | Path | None = None) -> ProjectManifest:
    return load_project_manifest(project_path(path))


def init_project(path: str | Path | None = None, *, title: str = "") -> ProjectManifest:
    root = Path(path or Path.cwd()).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = root / PROJECT_FILENAME
    if target.exists():
        raise LocalProjectError(f"A Forma project already exists at {target}.")
    manifest = ProjectManifest(
        format=PROJECT_MANIFEST_FORMAT,
        version=1,
        project_id=str(uuid4()),
        title=title.strip(),
        project_ir={},
    )
    write_project_manifest(target, manifest)
    save_linkage(root, {"version": 1, "project_id": manifest.project_id})
    return manifest


def _local_provider_environment(store: CredentialStore) -> dict[str, str]:
    values: dict[str, str] = {}
    for provider, environment_name in LOCAL_PROVIDER_ENVIRONMENT.items():
        try:
            value = store.get(f"provider:{provider}")
        except CredentialStoreError:
            # Local generation remains usable with environment-supplied keys.
            value = None
        if value:
            values[environment_name] = value
    return values


def build_project(
    path: str | Path | None = None,
    *,
    prompt: str | None = None,
    workflow: str = "default",
    provider: str | None = None,
    model: str | None = None,
    simulation: bool = False,
    credential_store: CredentialStore | None = None,
) -> ProjectManifest:
    root = project_root(path)
    current = read_project(root)
    from forma_core.generation import generate_project_with_workflow

    requested_prompt = (prompt or current.prompt or current.title).strip()
    if not requested_prompt:
        raise LocalProjectError("Build requires a prompt. Pass one or set prompt in forma-project.json.")
    store = credential_store or CredentialStore()
    generation_environment = SIMULATION_ENVIRONMENT if simulation else STRICT_GENERATION_ENVIRONMENT
    environment = {**generation_environment, **_local_provider_environment(store)}
    with config.override(environment):
        ir = generate_project_with_workflow(
            workflow,
            requested_prompt,
            provider_name="simulation" if simulation else provider,
            model_name=None if simulation else model,
            generation_metadata={"project_id": current.project_id, "project_prompt": requested_prompt},
            persist_project=False,
        )
    metadata = dict(ir.assembly_metadata or {})
    metadata["project_id"] = current.project_id
    metadata["project_prompt"] = requested_prompt
    ir.assembly_metadata = metadata
    updated = ProjectManifest(
        format=PROJECT_MANIFEST_FORMAT,
        version=1,
        project_id=current.project_id,
        workspace_id=current.workspace_id,
        title=current.title or (ir.overview.title if ir.overview else requested_prompt),
        prompt=requested_prompt,
        project_ir=ir.model_dump(mode="json"),
        artifacts=current.artifacts,
    )
    write_project_manifest(root / PROJECT_FILENAME, updated)
    return updated


def status_project(path: str | Path | None = None) -> dict[str, Any]:
    root = project_root(path)
    manifest = read_project(root)
    try:
        from forma_core.validation import build_validation_summary, validate_circuit
        from forma_core.workspaces.projects.models import HardwareIR

        ir = HardwareIR.model_validate(manifest.project_ir)
        summary = build_validation_summary(validate_circuit(ir.components, ir.nets, ir.requirements))
        valid = not summary.critical
        validation = summary.model_dump(mode="json")
    except Exception as exc:
        valid = False
        validation = {"critical": [str(exc)], "warning": [], "info": []}
    linkage = load_linkage(root)
    return {
        "project_id": manifest.project_id,
        "title": manifest.title,
        "path": str(root / PROJECT_FILENAME),
        "valid": valid,
        "validation": validation,
        "remote": linkage.get("remote"),
        "remote_project_id": linkage.get("remote_project_id") or linkage.get("project_id") if linkage.get("remote") else None,
        "revision_id": linkage.get("revision_id"),
        "parent_revision_id": linkage.get("parent_revision_id"),
    }


def update_linkage(path: str | Path, **values: Any) -> dict[str, Any]:
    root = project_root(path)
    linkage = {**load_linkage(root), **values}
    save_linkage(root, linkage)
    return linkage


__all__ = [
    "LOCAL_PROVIDER_ENVIRONMENT",
    "LocalProjectError",
    "PROJECT_FILENAME",
    "build_project",
    "init_project",
    "project_path",
    "project_root",
    "read_project",
    "status_project",
    "update_linkage",
]
