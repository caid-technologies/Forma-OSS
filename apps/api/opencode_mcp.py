"""Restricted MCP tools for one authenticated OpenCode project session."""

from __future__ import annotations

import json
import hashlib
import logging
from pydantic import ValidationError

from apps.api.a2a import _persist_mcp_compile
from apps.api.auth import UserContext
from forma_core.workspaces.projects.cad_generation import ensure_native_cad_model
from forma_core.debug import new_error_correlation_id
from forma_core.opencode.capabilities import ConnectorCapability
from forma_core.opencode.models import (
    McpJsonRpcRequest,
    McpToolArguments,
    McpToolCallParams,
    ProjectToolResult,
    AuthoringFieldError,
    AuthoringToolError,
)
from forma_core.database import get_latest_project_revision, get_project_revision_by_source_job
from forma_core.validation import build_validation_summary, validate_circuit
from forma_core.workspaces.projects.models import HardwareIR
from forma_core.workspaces.projects.outcomes import evaluate_design_outcome
from forma_core.utils import generate_mermaid_chart, generate_svg_schematic


logger = logging.getLogger(__name__)


def opencode_mcp_tools() -> list[dict[str, object]]:
    """Return only project authoring tools, never the broad Forma MCP registry."""
    project_ir_schema = HardwareIR.model_json_schema()
    definitions = project_ir_schema.pop("$defs", {})
    authoring_schema = {"type": "object", "properties": {"project_ir": project_ir_schema}, "required": ["project_ir"], "$defs": definitions, "additionalProperties": False}
    return [
        {
            "name": "forma.opencode.create_project",
            "description": "Save an empty private draft bound to this session. This does not produce a populated hardware design.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "forma.opencode.read_project",
            "description": "Read the latest saved session project, revision, current validation, and design_outcome before reporting results.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "forma.opencode.update_project",
            "description": "Validate and persist a revision. Follow this schema and correct field errors before retrying. A saved draft is not a produced design; report project_readiness and validation, not HTTP success.",
            "inputSchema": authoring_schema,
        },
        {
            "name": "forma.opencode.compile_project",
            "description": "Compile and persist Hardware IR. Correct schema errors and critical validation findings. Report the saved revision and project_readiness; draft/partial is not a completed design or physical verification.",
            "inputSchema": authoring_schema,
        },
        {
            "name": "forma.opencode.validate_project",
            "description": "Run deterministic Forma electrical validation for the session project.",
            "inputSchema": authoring_schema,
        },
    ]


async def handle_opencode_mcp_json_rpc(
    payload: McpJsonRpcRequest | list[McpJsonRpcRequest],
    capability: ConnectorCapability,
) -> dict[str, object] | list[dict[str, object]] | None:
    if isinstance(payload, list):
        responses = [await _handle_request(item, capability) for item in payload]
        return [response for response in responses if response is not None] or None
    return await _handle_request(payload, capability)


async def _handle_request(request: McpJsonRpcRequest, capability: ConnectorCapability) -> dict[str, object] | None:
    request_id = request.id
    if "id" not in request.model_fields_set:
        return None
    method = request.method
    params = request.params
    if method == "initialize":
        return _result(request_id, {"protocolVersion": "2025-06-18", "serverInfo": {"name": "forma-opencode", "version": "1.0.0"}, "capabilities": {"tools": {}}})
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return _result(request_id, {})
    if method == "tools/list":
        return _result(request_id, {"tools": opencode_mcp_tools()})
    if method != "tools/call":
        return _error(request_id, -32601, "The requested MCP method was not found.", "mcp_method_not_found")
    assert isinstance(params, McpToolCallParams)
    tool_name = params.name
    arguments = params.arguments
    if not tool_name:
        return _error(request_id, -32602, "Request parameters are invalid.", "mcp_invalid_params")
    try:
        result = await _call_tool(tool_name, arguments, capability)
    except PermissionError:
        return _error(request_id, -32003, "The OpenCode tool is outside the session scope.", "authorization_required")
    except ValidationError as exc:
        # Never echo inputs, validator messages, context, or arbitrary mapping keys.
        schema = HardwareIR.model_json_schema()
        fields = {"project_ir", *schema.get("properties", {})}
        for definition in schema.get("$defs", {}).values():
            fields.update(definition.get("properties", {}))
        errors = tuple(AuthoringFieldError(path=("project_ir", *[part if isinstance(part, int) or part in fields else "<key>" for part in error["loc"]]), type=error["type"])
                       for error in exc.errors(include_input=False, include_context=False, include_url=False))
        result = AuthoringToolError(errors=errors).model_dump(mode="json")
        return _result(request_id, {"isError": True, "content": [{"type": "text", "text": json.dumps(result)}], "structuredContent": result})
    except (TypeError, ValueError, KeyError):
        return _error(request_id, -32602, "The project tool parameters are invalid.", "mcp_invalid_params")
    except Exception:
        logger.warning("Restricted OpenCode MCP tool failed")
        return _error(request_id, -32000, "The OpenCode project tool could not complete.", "mcp_tool_failed")
    return _result(request_id, {"content": [{"type": "text", "text": json.dumps(result)}], "structuredContent": result})


async def _call_tool(name: str, arguments: McpToolArguments, capability: ConnectorCapability) -> dict[str, object]:
    allowed = {tool["name"] for tool in opencode_mcp_tools()}
    if name not in allowed:
        raise PermissionError("The requested tool is not part of the project-only surface.")
    project_id = capability.project_id
    owner_user_id = capability.owner_user_id
    user_context = UserContext(
        provider="opencode-connector",
        subject=owner_user_id,
        owner_user_id=owner_user_id,
        is_authenticated=True,
        is_admin=False,
    )
    if name == "forma.opencode.create_project":
        project = HardwareIR.model_validate({"components": [], "nets": []})
        result = _compile(project, project_id, user_context)
        return ProjectToolResult.model_validate(result).model_dump(mode="json")
    if name == "forma.opencode.read_project":
        revision = get_latest_project_revision(project_id, owner_user_id)
        if revision is None:
            raise ValueError("The session project has not been created.")
        project = revision.state
        return _tool_result(project, project_id, _revision_identifier(revision))
    try:
        project = HardwareIR.model_validate(arguments.project_ir)
    except TypeError as exc:
        # Legacy normalization can raise TypeError before Pydantic wraps it.
        raise ValidationError.from_exception_data("HardwareIR", [{
            "type": "model_type", "loc": (), "input": None,
            "ctx": {"class_name": "HardwareIR"},
        }]) from exc
    if name == "forma.opencode.validate_project":
        return _validation_result(project)
    if name in {"forma.opencode.compile_project", "forma.opencode.update_project"}:
        result = _compile(project, project_id, user_context)
        return ProjectToolResult.model_validate(result).model_dump(mode="json")
    raise PermissionError("The requested tool is not part of the project-only surface.")


def _compile(project: HardwareIR, project_id: str, user_context: UserContext) -> dict[str, object]:
    metadata = dict(project.assembly_metadata or {})
    metadata.update({"project_id": project_id, "authoring_agent": "opencode"})
    project.assembly_metadata = metadata
    issues = validate_circuit(project.components, project.nets, project.requirements)
    project.validation = build_validation_summary(issues)
    project.is_valid = not project.validation.critical
    ensure_native_cad_model(project, project_id=project_id, required=False, authoring_agent="opencode", workflow="default")
    source_job_id = "opencode-" + hashlib.sha256(
        json.dumps(project.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:32]
    existing = get_project_revision_by_source_job(project_id, user_context.owner_user_id or "", source_job_id)
    if existing is not None:
        return _tool_result(existing.state, project_id, _revision_identifier(existing))
    _persist_mcp_compile(
        project,
        {"project_id": project_id, "prompt": "OpenCode project", "visibility": "private", "authoring_agent": "opencode", "source_job_id": source_job_id},
        user_context,
    )
    revision = get_latest_project_revision(project_id, user_context.owner_user_id or "")
    return _tool_result(project, project_id, _revision_identifier(revision))


def _revision_identifier(revision: object | None) -> str | None:
    if revision is None:
        return None
    value = getattr(revision, "revision_id", None) or getattr(revision, "id", None)
    return str(value) if value else None


def _tool_result(project: HardwareIR, project_id: str, revision_id: str | None) -> dict[str, object]:
    return {
        "project_id": project_id,
        "revision_id": revision_id,
        "design_outcome": evaluate_design_outcome(project).model_dump(mode="json"),
        "project_ir": project.model_dump(mode="json"),
        "validation": _validation_result(project),
        "mermaid_code": generate_mermaid_chart(project),
        "svg_schematic": generate_svg_schematic(project),
    }


def _validation_result(project: HardwareIR) -> dict[str, object]:
    issues = validate_circuit(project.components, project.nets, project.requirements)
    return {"is_valid": not any(issue.severity.upper() == "CRITICAL" for issue in issues), "issues": [issue.model_dump(mode="json") for issue in issues]}


def _result(request_id: object, result: object) -> dict[str, object]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: object, code: int, message: str, error_code: str) -> dict[str, object]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message, "data": {"code": error_code, "correlation_id": new_error_correlation_id()}}}
