from __future__ import annotations

import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from apps.api.opencode_api import router
from apps.api.opencode_mcp import _revision_identifier, opencode_mcp_tools
from forma_core.opencode.capabilities import ConnectorCapability
from forma_core.opencode.models import (
    McpInitializeParams,
    McpJsonRpcRequest,
    McpRequestParams,
    McpToolArguments,
    McpToolCallParams,
    McpToolsListParams,
)


class OpenCodeMcpModelTests(unittest.TestCase):
    def test_revision_identifier_uses_canonical_revision_id(self) -> None:
        revision = type("Revision", (), {"revision_id": "revision-1"})()

        self.assertEqual("revision-1", _revision_identifier(revision))

    def test_model_validate_retains_typed_variants_and_wire_aliases(self) -> None:
        for method, params, expected_type in (
            ("initialize", {
                "protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "opencode", "version": "1.0.0"},
                "_meta": {"progressToken": "init"},
            }, McpInitializeParams),
            ("tools/call", {"name": "forma.opencode.read_project", "arguments": {}}, McpToolCallParams),
            ("tools/list", {"cursor": "opaque"}, McpToolsListParams),
            ("ping", {}, McpRequestParams),
            ("notifications/initialized", {}, McpRequestParams),
        ):
            with self.subTest(method=method):
                payload = {"jsonrpc": "2.0", "method": method, "params": params}
                request = McpJsonRpcRequest.model_validate(payload)
                self.assertIs(type(request.params), expected_type)
                self.assertEqual(payload, request.model_dump(by_alias=True, exclude_unset=True))
                self.assertEqual(request, McpJsonRpcRequest.model_validate_json(
                    request.model_dump_json(by_alias=True, exclude_unset=True),
                ))
                self.assertEqual(request, McpJsonRpcRequest.model_validate({**payload, "params": request.params}))
                if isinstance(request.params, McpToolCallParams):
                    self.assertIsInstance(request.params.arguments, McpToolArguments)

    def test_typed_params_cannot_bypass_method_validation(self) -> None:
        params = McpToolCallParams(name="forma.opencode.read_project")
        for method in ("initialize", "ping", "notifications/initialized", "tools/list"):
            with self.subTest(method=method), self.assertRaises(ValidationError):
                McpJsonRpcRequest.model_validate({"jsonrpc": "2.0", "method": method, "params": params})


class OpenCodeMcpHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = FastAPI()
        self.app.include_router(router, prefix="/api")
        self.capability = ConnectorCapability(
            "mini", "session", str(uuid4()), "user", 2_000_000_000, "nonce", frozenset({"mcp"}),
        )
        self.authorize = self.enterContext(patch(
            "apps.api.opencode_api._connector_capability", return_value=self.capability,
        ))
        self.client = self.enterContext(TestClient(self.app))
        self.initialize_params = {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "opencode", "version": "1.0.0"},
        }

    def test_standard_initialize_reaches_handler(self) -> None:
        response = self.client.post("/api/opencode/mcp", json={
            "jsonrpc": "2.0", "id": 0, "method": "initialize", "params": self.initialize_params,
        }, headers={"Authorization": "Bearer test-capability"})

        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual({
            "jsonrpc": "2.0", "id": 0,
            "result": {
                "protocolVersion": "2025-06-18",
                "serverInfo": {"name": "forma-opencode", "version": "1.0.0"},
                "capabilities": {"tools": {}},
            },
        }, response.json())
        self.authorize.assert_called_once_with("test-capability", scope="mcp")

    def test_initialize_accepts_capability_extensions_and_metadata(self) -> None:
        params = {
            **self.initialize_params,
            "clientInfo": {"name": "opencode", "version": "1.0.0", "title": "OpenCode"},
            "capabilities": {
                "roots": {"listChanged": True},
                "sampling": {},
                "elicitation": {"form": {}},
                "experimental": {"example.test/feature": {"versions": [1, 2]}},
                "example.test/extension": {"enabled": True},
            },
            "_meta": {"progressToken": 1, "example.test/trace": {"tags": ["initialize"]}},
        }
        response = self.client.post("/api/opencode/mcp", json={
            "jsonrpc": "2.0", "id": "init", "method": "initialize", "params": params,
        })
        self.assertEqual(200, response.status_code, response.text)

    def test_initialize_accepts_newer_client_metadata_before_protocol_negotiation(self) -> None:
        client_info = {
            "name": "opencode", "version": "1.0.0", "title": "OpenCode",
            "description": "Project authoring client", "websiteUrl": "https://opencode.ai",
            "icons": [{"src": "https://opencode.ai/icon.svg", "mimeType": "image/svg+xml",
                       "sizes": ["any"], "theme": "dark"}],
        }
        payload = {
            "jsonrpc": "2.0", "id": "init", "method": "initialize",
            "params": {**self.initialize_params, "protocolVersion": "2025-11-25", "clientInfo": client_info},
        }
        request = McpJsonRpcRequest.model_validate(payload)
        self.assertEqual(payload, request.model_dump(by_alias=True, exclude_unset=True))
        response = self.client.post("/api/opencode/mcp", json=payload)
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual("2025-06-18", response.json()["result"]["protocolVersion"])

    def test_openapi_includes_typed_initialization_and_client_metadata(self) -> None:
        response = self.client.get("/openapi.json")
        self.assertEqual(200, response.status_code)
        schemas = response.json()["components"]["schemas"]
        self.assertEqual({"protocolVersion", "capabilities", "clientInfo"}, set(schemas["McpInitializeParams"]["required"]))
        self.assertEqual({"name", "version"}, set(schemas["McpClientInfo"]["required"]))
        self.assertIn("websiteUrl", schemas["McpClientInfo"]["properties"])
        self.assertIn("mimeType", schemas["McpIcon"]["properties"])

    def test_initialize_requires_protocol_capabilities_and_client_identity(self) -> None:
        invalid_params = [None, {}, []]
        invalid_params.extend(
            {key: value for key, value in self.initialize_params.items() if key != missing}
            for missing in ("protocolVersion", "capabilities", "clientInfo")
        )
        invalid_params.extend(
            {**self.initialize_params, "clientInfo": info}
            for info in ({}, {"name": "opencode"}, {"version": "1.0.0"})
        )
        for params in invalid_params:
            with self.subTest(params=params):
                response = self.client.post("/api/opencode/mcp", json={
                    "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": params,
                })
                self.assertEqual(422, response.status_code, response.text)
        response = self.client.post("/api/opencode/mcp", json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
        })
        self.assertEqual(422, response.status_code, response.text)
        self.authorize.assert_not_called()

    def test_initialize_rejects_invalid_known_fields(self) -> None:
        for changes in (
            {"protocolVersion": 123},
            {"protocolVersion": None},
            {"capabilities": None},
            {"capabilities": []},
            {"capabilities": {"roots": {"listChanged": "true"}}},
            {"capabilities": {"sampling": True}},
            {"capabilities": {"elicitation": []}},
            {"capabilities": {"experimental": {"feature": True}}},
            {"clientInfo": None},
            {"clientInfo": {"name": "opencode", "version": 1}},
            {"clientInfo": {"name": "opencode", "version": "1", "unknown": True}},
            {"clientInfo": {"name": "opencode", "version": "1", "description": 1}},
            {"clientInfo": {"name": "opencode", "version": "1", "websiteUrl": []}},
            {"clientInfo": {"name": "opencode", "version": "1", "icons": [{}]}},
            {"clientInfo": {"name": "opencode", "version": "1", "icons": [{"src": "icon.svg", "sizes": "any"}]}},
            {"clientInfo": {"name": "opencode", "version": "1", "icons": [{"src": "icon.svg", "theme": "unknown"}]}},
            {"_meta": []},
            {"arguments": {}},
            {"unknown": True},
        ):
            with self.subTest(changes=changes):
                response = self.client.post("/api/opencode/mcp", json={
                    "jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {**self.initialize_params, **changes},
                })
                self.assertEqual(422, response.status_code, response.text)
        self.authorize.assert_not_called()

    def test_initialized_ping_and_tools_list_accept_optional_params(self) -> None:
        for method in ("notifications/initialized", "ping", "tools/list"):
            for fields in ({}, {"params": {}}, {"params": {"_meta": {"example.test/trace": "test"}}}):
                with self.subTest(method=method, fields=fields):
                    payload = {"jsonrpc": "2.0", "method": method, **fields}
                    if method != "notifications/initialized":
                        payload["id"] = "request"
                    response = self.client.post("/api/opencode/mcp", json=payload)
                    if method == "notifications/initialized":
                        self.assertEqual(202, response.status_code, response.text)
                        self.assertEqual(b"", response.content)
                    else:
                        self.assertEqual(200, response.status_code, response.text)
                        expected = {"tools": opencode_mcp_tools()} if method == "tools/list" else {}
                        self.assertEqual(expected, response.json()["result"])
        response = self.client.post("/api/opencode/mcp", json={
            "jsonrpc": "2.0", "id": "list", "method": "tools/list", "params": {"cursor": "opaque"},
        })
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual(opencode_mcp_tools(), response.json()["result"]["tools"])

    def test_params_are_validated_by_method_not_by_union_shape(self) -> None:
        for method, params in (
            ("initialize", {"name": "forma.opencode.read_project", "arguments": {}}),
            ("tools/call", self.initialize_params),
            ("ping", self.initialize_params),
            ("notifications/initialized", {"name": "forma.opencode.read_project"}),
            ("tools/list", {"name": "forma.opencode.read_project"}),
            ("tools/list", {"cursor": 123}),
            ("tools/call", {"name": "forma.opencode.read_project", "arguments": {"project_id": "foreign"}}),
        ):
            with self.subTest(method=method, params=params):
                response = self.client.post("/api/opencode/mcp", json={
                    "jsonrpc": "2.0", "id": 1, "method": method, "params": params,
                })
                self.assertEqual(422, response.status_code, response.text)
        self.authorize.assert_not_called()

    def test_unknown_methods_and_forbidden_tools_still_rejected(self) -> None:
        response = self.client.post("/api/opencode/mcp", json={
            "jsonrpc": "2.0", "id": "unknown", "method": "unknown/method",
        })
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual(-32601, response.json()["error"]["code"])
        for name in ("forma.generate_project", "forma.opencode.unknown", "shell"):
            with self.subTest(name=name):
                response = self.client.post("/api/opencode/mcp", json={
                    "jsonrpc": "2.0", "id": name, "method": "tools/call",
                    "params": {"name": name, "arguments": {}},
                })
                self.assertEqual(200, response.status_code, response.text)
                self.assertEqual(-32003, response.json()["error"]["code"])
                self.assertEqual("authorization_required", response.json()["error"]["data"]["code"])

    def test_missing_tool_name_retains_json_rpc_invalid_params_error(self) -> None:
        for fields in ({}, {"params": {}}, {"params": {"name": ""}}):
            with self.subTest(fields=fields):
                response = self.client.post("/api/opencode/mcp", json={
                    "jsonrpc": "2.0", "id": 1, "method": "tools/call", **fields,
                })
                self.assertEqual(200, response.status_code, response.text)
                self.assertEqual(-32602, response.json()["error"]["code"])

    def test_allowed_tool_retains_typed_arguments_with_metadata(self) -> None:
        with patch("apps.api.opencode_mcp.validate_circuit", return_value=[]) as validate:
            response = self.client.post("/api/opencode/mcp", json={
                "jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {
                    "name": "forma.opencode.validate_project",
                    "arguments": {"project_ir": {"components": [], "nets": []}},
                    "_meta": {"progressToken": "validation"},
                },
            })
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual({"is_valid": True, "issues": []}, response.json()["result"]["structuredContent"])
        validate.assert_called_once()

    def test_initialize_cannot_bypass_capability_authorization(self) -> None:
        self.authorize.side_effect = HTTPException(status_code=403, detail="test denial")
        response = self.client.post("/api/opencode/mcp", json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": self.initialize_params,
        })
        self.assertEqual(403, response.status_code, response.text)

    def test_batch_validates_initialize_and_omits_notification_responses(self) -> None:
        response = self.client.post("/api/opencode/mcp", json=[
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": self.initialize_params},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ])
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual([1, 2], [item["id"] for item in response.json()])
        response = self.client.post("/api/opencode/mcp", json=[
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "ping"},
        ])
        self.assertEqual(422, response.status_code, response.text)
