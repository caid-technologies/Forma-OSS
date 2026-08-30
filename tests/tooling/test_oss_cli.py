from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from forma_cli.app import build_parser, cmd_projects_pull, cmd_render
from forma_cli.credentials import CredentialStore
from forma_cli.local import build_project, init_project
from forma_cli.sdk import CloudProjectRevision, FormaAPIClient
from forma_core.database import get_generated_project
from forma_core.workspaces.projects.manifest import ProjectManifest, write_project_manifest


class FakeKeyring:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, name: str) -> str | None:
        return self.values.get((service, name))

    def set_password(self, service: str, name: str, value: str) -> None:
        self.values[(service, name)] = value

    def delete_password(self, service: str, name: str) -> None:
        self.values.pop((service, name), None)


class Response:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __enter__(self) -> "Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class OssCliTests(unittest.TestCase):
    def test_help_hierarchy_contains_initial_command_groups(self) -> None:
        parser = build_parser()
        self.assertEqual("forma-oss", parser.prog)
        self.assertEqual(
            {"login", "logout", "whoami", "init", "build", "status", "render", "projects", "keys"},
            set(parser._subparsers._group_actions[0].choices),
        )

    def test_init_creates_local_manifest_and_non_secret_linkage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = init_project(temp_dir, title="Sensor")
            root = Path(temp_dir)
            self.assertEqual("forma-project", json.loads((root / "forma-project.json").read_text())["format"])
            linkage = (root / ".forma" / "project.toml").read_text(encoding="utf-8")
            self.assertIn(f'project_id = "{manifest.project_id}"', linkage)
            self.assertNotIn("token", linkage.lower())

    def test_upload_payload_redacts_provider_secrets_recursively(self) -> None:
        manifest = ProjectManifest(
            project_id="local-project",
            project_ir={
                "components": [],
                "assembly_metadata": {"api_key": "do-not-upload", "safe": "yes"},
                "nested": {"authorization": "Bearer secret", "safe": "yes"},
            },
        )

        payload = manifest.upload_payload()

        serialized = json.dumps(payload)
        self.assertNotIn("do-not-upload", serialized)
        self.assertNotIn("Bearer secret", serialized)
        self.assertEqual("yes", payload["project_ir"]["assembly_metadata"]["safe"])

    def test_local_manifest_writer_does_not_persist_provider_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "forma-project.json"
            write_project_manifest(
                path,
                ProjectManifest(project_id="local-project", project_ir={"api_key": "secret-value"}),
            )
            self.assertNotIn("secret-value", path.read_text(encoding="utf-8"))

    def test_render_writes_a_local_dashboard_png(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest = ProjectManifest(
                project_id="render-project",
                title="Rendered project",
                project_ir=json.loads(
                    (Path(__file__).resolve().parents[2] / "apps" / "web" / "public" / "examples" / "plant_watering.json")
                    .read_text(encoding="utf-8")
                ),
            )
            write_project_manifest(root / "forma-project.json", manifest)
            args = type(
                "Args",
                (),
                {"path": temp_dir, "output": "render.png", "width": 720, "height": 520, "yaw": 20.0},
            )()

            self.assertEqual(0, cmd_render(args))
            output = root / "render.png"
            self.assertTrue(output.exists())
            self.assertGreater(output.stat().st_size, 1000)

    def test_simulated_test_tube_build_has_matching_cad_preview(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            init_project(temp_dir, title="Test tube")
            root = Path(temp_dir)
            (root / "assembled.step").write_text(
                "ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n",
                encoding="ascii",
            )

            manifest = build_project(temp_dir, prompt="test tube", simulation=True)
            ir = manifest.project_ir

            self.assertEqual("Test Tube Monitor", ir["overview"]["title"])
            self.assertEqual("forma-opencad", ir["cad_model"]["adapter"])
            self.assertEqual(1, len(ir["cad_model"]["meshes"]))
            self.assertGreater(len(ir["cad_model"]["meshes"][0]["vertices"]), 100)
            self.assertTrue((root / "assembly.step").is_file())
            self.assertEqual("assembly.step", manifest.artifacts[-1].path)
            saved = get_generated_project(manifest.project_id)
            self.assertIsNotNone(saved)
            self.assertEqual(
                str((root / "assembly.step").resolve()),
                saved.hardware_ir["cad_model"]["path"],
            )

    def test_credential_store_uses_keyring_backend_without_exposing_values(self) -> None:
        keyring = FakeKeyring()
        store = CredentialStore(keyring_backend=keyring)
        store.set("provider:openai", "secret-value")

        self.assertEqual("secret-value", store.get("provider:openai"))
        self.assertNotIn("secret-value", repr({"configured": bool(store.get("provider:openai"))}))
        store.delete("provider:openai")
        self.assertIsNone(store.get("provider:openai"))

    def test_sdk_exchange_persists_typed_tokens_in_credential_store(self) -> None:
        keyring = FakeKeyring()
        client = FormaAPIClient(
            base_url="https://api.example.test",
            credential_store=CredentialStore(keyring_backend=keyring),
        )
        with patch(
            "forma_cli.sdk.urlopen",
            return_value=Response(
                {
                    "access_token": "access",
                    "refresh_token": "refresh",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                }
            ),
        ):
            tokens = client.exchange_device_code("device")

        self.assertEqual("access", tokens.access_token)
        self.assertEqual("refresh", client._saved_tokens().refresh_token)

    def test_projects_pull_writes_typed_remote_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            init_project(temp_dir)
            client = FormaAPIClient(base_url="https://api.example.test", credential_store=CredentialStore(
                keyring_backend=FakeKeyring()
            ))
            client.pull_project = lambda _project_id, _revision_id=None: CloudProjectRevision(
                revision_id="revision-1",
                project_id="project-1",
                revision=1,
                manifest={"format": "forma-project", "project_id": "project-1", "project_ir": {"components": []}},
            )  # type: ignore[method-assign]
            args = type("Args", (), {
                "path": temp_dir,
                "project_id": "project-1",
                "revision_id": None,
                "json": False,
                "api_url": None,
            })()
            with patch("forma_cli.app.FormaAPIClient", return_value=client):
                self.assertEqual(0, cmd_projects_pull(args))
            saved = json.loads((Path(temp_dir) / "forma-project.json").read_text(encoding="utf-8"))
            self.assertEqual("project-1", saved["project_id"])


if __name__ == "__main__":
    unittest.main()
