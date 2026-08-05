from __future__ import annotations

import base64
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import threading
import tempfile
import unittest
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[2]
SKILL_DIR = ROOT_DIR / "integrations" / "agent-skills" / "forma-hardware"
CLIENT_PATH = SKILL_DIR / "scripts" / "forma.py"
INSTALLER_PATH = ROOT_DIR / "scripts" / "operations" / "install-forma-skill.py"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


forma_client = _load_module("forma_skill_client", CLIENT_PATH)
forma_installer = _load_module("forma_skill_installer", INSTALLER_PATH)


class _MCPHandler(BaseHTTPRequestHandler):
    requests: list[dict] = []
    authorization: str | None = None
    rpc_error: dict | None = None

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length))
        type(self).requests.append(payload)
        type(self).authorization = self.headers.get("Authorization")

        if type(self).rpc_error:
            response = {"jsonrpc": "2.0", "id": payload["id"], "error": type(self).rpc_error}
        elif payload["method"] == "tools/list":
            response = {
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {"tools": [{"name": "blueprint.generate_project"}]},
            }
        elif (
            payload["params"]["name"] == "blueprint.export_project_pdf"
            or "pdf" in payload["params"]["arguments"].get("output_formats", [])
        ):
            encoded_pdf = base64.b64encode(b"%PDF-1.4\n%%EOF\n").decode("ascii")
            response = {
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {
                    "content": [
                        {"type": "text", "text": "pdf"},
                        {
                            "type": "resource",
                            "resource": {
                                "uri": "forma://artifacts/test/report.pdf",
                                "mimeType": "application/pdf",
                                "blob": encoded_pdf,
                            },
                        },
                    ],
                    "structuredContent": {
                        "received": payload["params"]["arguments"],
                        "artifacts": [
                            {
                                "format": "pdf",
                                "filename": "report.pdf",
                                "mime_type": "application/pdf",
                                "delivery": "embedded_resource",
                            }
                        ]
                    },
                },
            }
        else:
            arguments = payload["params"]["arguments"]
            response = {
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {
                    "content": [{"type": "text", "text": "ignored"}],
                    "structuredContent": {"received": arguments},
                },
            }

        rendered = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(rendered)))
        self.end_headers()
        self.wfile.write(rendered)

    def log_message(self, format: str, *args) -> None:
        return


@contextmanager
def _mcp_server():
    _MCPHandler.requests = []
    _MCPHandler.authorization = None
    _MCPHandler.rpc_error = None
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MCPHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class FormaSkillClientTests(unittest.TestCase):
    def test_lists_tools_and_normalizes_bare_origin(self) -> None:
        with _mcp_server() as url:
            result = forma_client.request("tools/list", url=url, timeout=2)

        self.assertEqual("blueprint.generate_project", result["tools"][0]["name"])
        self.assertEqual("tools/list", _MCPHandler.requests[0]["method"])

    def test_generate_uses_structured_content_and_bearer_token(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, _mcp_server() as url:
            output = Path(temp_dir) / "project.json"
            with patch.dict("os.environ", {"FORMA_AUTH_TOKEN": "test-token"}, clear=False):
                exit_code = forma_client.main([
                    "generate",
                    "ESP32 soil monitor",
                    "--use-configured-provider",
                    "--workflow",
                    "web_research",
                    "--past-jobs",
                    "--url",
                    url,
                    "--timeout",
                    "2",
                    "--output",
                    str(output),
                ])

            saved = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(0, exit_code)
        self.assertEqual("ESP32 soil monitor", saved["received"]["prompt"])
        self.assertEqual(["past_jobs"], saved["received"]["data_sources"])
        self.assertEqual("Bearer test-token", _MCPHandler.authorization)
        self.assertEqual("blueprint.generate_project", _MCPHandler.requests[0]["params"]["name"])

    def test_validate_extracts_project_ir(self) -> None:
        project = {"project_ir": {"components": [{"id": "mcu"}], "nets": [{"id": "power"}]}}
        with tempfile.TemporaryDirectory() as temp_dir, _mcp_server() as url:
            project_path = Path(temp_dir) / "project.json"
            output_path = Path(temp_dir) / "validation.json"
            project_path.write_text(json.dumps(project), encoding="utf-8")
            exit_code = forma_client.main([
                "validate",
                str(project_path),
                "--url",
                url,
                "--output",
                str(output_path),
            ])
            saved = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(0, exit_code)
        self.assertEqual([{"id": "mcu"}], saved["received"]["components"])
        self.assertEqual([{"id": "power"}], saved["received"]["nets"])

    def test_generate_can_save_requested_pdf_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, _mcp_server() as url:
            pdf_path = Path(temp_dir) / "generated-report.pdf"
            metadata_path = Path(temp_dir) / "project.json"

            exit_code = forma_client.main([
                "generate",
                "ESP32 soil monitor",
                "--use-configured-provider",
                "--url",
                url,
                "--pdf-output",
                str(pdf_path),
                "--output",
                str(metadata_path),
            ])
            saved_pdf = pdf_path.read_bytes()
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

        self.assertEqual(0, exit_code)
        self.assertTrue(saved_pdf.startswith(b"%PDF-"))
        self.assertEqual(["pdf"], metadata["received"]["output_formats"])

    def test_export_pdf_saves_embedded_resource(self) -> None:
        project = {"project_ir": {"overview": {"title": "Test"}, "components": [], "nets": []}}
        with tempfile.TemporaryDirectory() as temp_dir, _mcp_server() as url:
            project_path = Path(temp_dir) / "project.json"
            pdf_path = Path(temp_dir) / "report.pdf"
            metadata_path = Path(temp_dir) / "metadata.json"
            project_path.write_text(json.dumps(project), encoding="utf-8")

            exit_code = forma_client.main([
                "export-pdf",
                str(project_path),
                "--url",
                url,
                "--pdf-output",
                str(pdf_path),
                "--output",
                str(metadata_path),
            ])
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            saved_pdf = pdf_path.read_bytes()

        self.assertEqual(0, exit_code)
        self.assertEqual(b"%PDF-1.4\n%%EOF\n", saved_pdf)
        resource = metadata["_embedded_resources"][0]
        self.assertEqual(str(pdf_path), resource["saved_path"])
        self.assertNotIn("blob", resource)

    def test_compile_uses_host_agent_and_saves_pdf(self) -> None:
        project = {"overview": {"title": "Agent project"}, "components": [], "nets": []}
        with tempfile.TemporaryDirectory() as temp_dir, _mcp_server() as url:
            project_path = Path(temp_dir) / "agent-project.json"
            pdf_path = Path(temp_dir) / "agent-project.pdf"
            metadata_path = Path(temp_dir) / "compiled.json"
            project_path.write_text(json.dumps(project), encoding="utf-8")

            exit_code = forma_client.main([
                "compile",
                str(project_path),
                "--authoring-agent",
                "codex",
                "--pdf-output",
                str(pdf_path),
                "--url",
                url,
                "--output",
                str(metadata_path),
            ])
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            saved_pdf = pdf_path.read_bytes()

        self.assertEqual(0, exit_code)
        self.assertTrue(saved_pdf.startswith(b"%PDF-"))
        self.assertEqual("codex", metadata["received"]["authoring_agent"])
        self.assertEqual(["pdf"], metadata["received"]["output_formats"])

    def test_simulation_generation_requires_double_opt_in(self) -> None:
        parser = forma_client.build_parser()
        args = parser.parse_args(["generate", "test", "--provider", "simulation"])

        with self.assertRaisesRegex(forma_client.FormaClientError, "--allow-simulation"):
            forma_client.run(args)

    def test_surfaces_json_rpc_errors(self) -> None:
        with _mcp_server() as url:
            _MCPHandler.rpc_error = {"code": -32000, "message": "provider unavailable"}
            with self.assertRaisesRegex(forma_client.FormaClientError, "provider unavailable"):
                forma_client.request("tools/list", url=url, timeout=2)


class FormaSkillInstallerTests(unittest.TestCase):
    def test_installs_for_claude_and_codex_at_user_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            exit_code = forma_installer.main(["--home", str(home), "--source", str(SKILL_DIR)])

            claude_skill = home / ".claude" / "skills" / "forma-hardware"
            codex_skill = home / ".agents" / "skills" / "forma-hardware"
            self.assertEqual(0, exit_code)
            self.assertTrue((claude_skill / "SKILL.md").is_file())
            self.assertTrue((codex_skill / "scripts" / "forma.py").is_file())
            self.assertFalse(any(path.name == "__pycache__" for path in claude_skill.rglob("*")))
            self.assertFalse(any(path.suffix == ".pyc" for path in codex_skill.rglob("*")))
            self.assertEqual(
                (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8"),
                (claude_skill / "SKILL.md").read_text(encoding="utf-8"),
            )

    def test_requires_force_to_update_an_existing_skill(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            first = forma_installer.main([
                "--agent",
                "codex",
                "--home",
                str(home),
                "--source",
                str(SKILL_DIR),
            ])
            second = forma_installer.main([
                "--agent",
                "codex",
                "--home",
                str(home),
                "--source",
                str(SKILL_DIR),
            ])
            updated = forma_installer.main([
                "--agent",
                "codex",
                "--home",
                str(home),
                "--source",
                str(SKILL_DIR),
                "--force",
            ])

        self.assertEqual(0, first)
        self.assertEqual(2, second)
        self.assertEqual(0, updated)


class FormaSkillPackageTests(unittest.TestCase):
    def test_skill_has_cross_agent_metadata_and_docs(self) -> None:
        skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        openai_metadata = (SKILL_DIR / "agents" / "openai.yaml").read_text(encoding="utf-8")

        self.assertIn("name: forma-hardware", skill)
        self.assertIn("description:", skill)
        self.assertNotIn("TODO", skill)
        self.assertIn("$forma-hardware", openai_metadata)
        self.assertTrue((SKILL_DIR / "references" / "configuration.md").is_file())
        self.assertTrue((ROOT_DIR / "docs" / "agent-skills.md").is_file())


if __name__ == "__main__":
    unittest.main()
