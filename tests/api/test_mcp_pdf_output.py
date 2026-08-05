from __future__ import annotations

import asyncio
import base64
import unittest
from unittest.mock import patch

from apps.api import a2a

from tests.projects.test_project_exports import SAMPLE_PROJECT


class McpPdfOutputTests(unittest.TestCase):
    def test_pdf_export_tool_is_discoverable(self) -> None:
        tools = {tool["name"]: tool for tool in a2a._mcp_tools()}

        self.assertIn("blueprint.export_project_pdf", tools)
        self.assertIn("blueprint.compile_project", tools)
        self.assertEqual(["project_ir"], tools["blueprint.export_project_pdf"]["inputSchema"]["required"])
        self.assertEqual(
            ["project_ir", "authoring_agent"],
            tools["blueprint.compile_project"]["inputSchema"]["required"],
        )
        output_formats = tools["blueprint.generate_project"]["inputSchema"]["properties"]["output_formats"]
        self.assertEqual(["pdf"], output_formats["items"]["enum"])

    def test_export_tool_returns_an_embedded_pdf_resource(self) -> None:
        response = asyncio.run(
            a2a.handle_mcp_json_rpc(
                {
                    "jsonrpc": "2.0",
                    "id": "pdf-test",
                    "method": "tools/call",
                    "params": {
                        "name": "blueprint.export_project_pdf",
                        "arguments": {"project_ir": SAMPLE_PROJECT},
                    },
                }
            )
        )

        result = response["result"]
        resource_blocks = [block for block in result["content"] if block.get("type") == "resource"]
        self.assertEqual(1, len(resource_blocks))
        resource = resource_blocks[0]["resource"]
        self.assertEqual("application/pdf", resource["mimeType"])
        self.assertTrue(base64.b64decode(resource["blob"], validate=True).startswith(b"%PDF-"))
        artifact = result["structuredContent"]["artifacts"][0]
        self.assertEqual("embedded_resource", artifact["delivery"])
        self.assertNotIn("data_base64", artifact)

    def test_compile_tool_marks_host_agent_and_returns_five_view_pdf(self) -> None:
        response = asyncio.run(
            a2a.call_blueprint_action(
                "blueprint.compile_project",
                {
                    "project_ir": SAMPLE_PROJECT,
                    "authoring_agent": "codex",
                    "output_formats": ["pdf"],
                },
            )
        )

        self.assertEqual("host_agent", response["generation"]["mode"])
        self.assertEqual("codex", response["generation"]["authoring_agent"])
        self.assertFalse(response["generation"]["simulation"])
        self.assertEqual("codex", response["project_ir"]["assembly_metadata"]["authoring_agent"])
        self.assertEqual(["info", "bom", "mech", "wire", "docs"], response["artifacts"][0]["views"])

    def test_simulation_requires_an_explicit_opt_in(self) -> None:
        config = {"provider": "simulation", "runtime": {"runtime_provider": "simulation"}}

        with self.assertRaisesRegex(ValueError, "allow_simulation=true"):
            a2a.require_explicit_simulation(config, allow_simulation=False)
        a2a.require_explicit_simulation(config, allow_simulation=True)

    def test_generate_project_only_attaches_pdf_when_requested(self) -> None:
        generated = {"project_id": "project-123", "project_ir": SAMPLE_PROJECT}

        async def run_to_thread_inline(func, *args, **kwargs):
            return func(*args, **kwargs)

        with patch.object(a2a, "_apply_owner_user_integrations"), patch.object(
            a2a, "build_generation_response", return_value=generated
        ), patch.object(a2a.asyncio, "to_thread", side_effect=run_to_thread_inline):
            normal = asyncio.run(a2a.call_blueprint_action("blueprint.generate_project", {"prompt": "test"}))
            with_pdf = asyncio.run(
                a2a.call_blueprint_action(
                    "blueprint.generate_project",
                    {"prompt": "test", "output_formats": ["pdf"]},
                )
            )

        self.assertNotIn("artifacts", normal)
        self.assertEqual("pdf", with_pdf["artifacts"][0]["format"])
        self.assertTrue(base64.b64decode(with_pdf["artifacts"][0]["data_base64"]).startswith(b"%PDF-"))


if __name__ == "__main__":
    unittest.main()
