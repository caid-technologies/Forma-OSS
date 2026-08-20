from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from apps.api.a2a import MCP_DEFAULT_PROTOCOL_VERSION, handle_mcp_json_rpc
from apps.api.main import app


class McpAgentCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    def test_mcp_route_accepts_a_dedicated_agent_api_key(self) -> None:
        api_key = "n" * 32
        with patch.dict(
            os.environ,
            {"FORMA_AUTH_MODE": "clerk", "FORMA_MCP_API_KEY": api_key},
            clear=True,
        ):
            response = TestClient(app).post(
                "/mcp",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"jsonrpc": "2.0", "id": "tools", "method": "tools/list"},
            )

        self.assertEqual(200, response.status_code)
        names = [tool["name"] for tool in response.json()["result"]["tools"]]
        self.assertIn("forma.compile_project", names)

    async def test_initialize_negotiates_current_protocol(self) -> None:
        response = await handle_mcp_json_rpc(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18", "clientInfo": {"name": "opencode"}},
            }
        )

        self.assertEqual("2025-06-18", response["result"]["protocolVersion"])
        self.assertEqual("forma-oss", response["result"]["serverInfo"]["name"])

    async def test_unknown_protocol_falls_back_to_supported_version(self) -> None:
        response = await handle_mcp_json_rpc(
            {
                "jsonrpc": "2.0",
                "id": "init",
                "method": "initialize",
                "params": {"protocolVersion": "2099-01-01"},
            }
        )

        self.assertEqual(MCP_DEFAULT_PROTOCOL_VERSION, response["result"]["protocolVersion"])

    async def test_initialized_notification_has_no_json_rpc_response(self) -> None:
        response = await handle_mcp_json_rpc(
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
        )

        self.assertIsNone(response)

    async def test_batch_omits_notification_responses(self) -> None:
        response = await handle_mcp_json_rpc(
            [
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "ping"},
            ]
        )

        self.assertEqual([{"jsonrpc": "2.0", "id": 2, "result": {}}], response)

    async def test_tools_include_host_authored_compiler(self) -> None:
        response = await handle_mcp_json_rpc(
            {"jsonrpc": "2.0", "id": 3, "method": "tools/list"}
        )

        tools = response["result"]["tools"]
        names = [tool["name"] for tool in tools]
        self.assertIn("forma.compile_project", names)
        compiler = next(tool for tool in tools if tool["name"] == "forma.compile_project")
        authoring_agents = compiler["inputSchema"]["properties"]["authoring_agent"]["enum"]
        self.assertIn("nemoclaw", authoring_agents)

    async def test_compile_project_validates_without_generation(self) -> None:
        response = await handle_mcp_json_rpc(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "forma.compile_project",
                    "arguments": {
                        "project_ir": {"components": [], "nets": []},
                        "authoring_agent": "nemoclaw",
                    },
                },
            }
        )

        compiled = response["result"]["structuredContent"]
        self.assertTrue(compiled["is_valid"])
        self.assertEqual("nemoclaw", compiled["project_ir"]["assembly_metadata"]["authoring_agent"])
        self.assertIn("mermaid_code", compiled)
        self.assertIn("svg_schematic", compiled)


if __name__ == "__main__":
    unittest.main()
