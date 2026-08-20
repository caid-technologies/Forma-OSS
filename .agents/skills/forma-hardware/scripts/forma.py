#!/usr/bin/env python3
"""Small MCP JSON-RPC client for the portable Forma Agent Skill."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, urlopen


DEFAULT_MCP_URL = "http://127.0.0.1:8000/mcp"


class FormaClientError(RuntimeError):
    pass


def _url(value: str | None) -> str:
    raw = (value or os.environ.get("FORMA_MCP_URL") or DEFAULT_MCP_URL).strip()
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise FormaClientError("FORMA_MCP_URL must be an http:// or https:// URL.")
    if parsed.path in {"", "/"}:
        parsed = parsed._replace(path="/mcp")
    return urlunparse(parsed)


def _timeout(value: float | None) -> float:
    raw: float | str = value if value is not None else os.environ.get("FORMA_TIMEOUT_SECONDS", "600")
    try:
        timeout = float(raw)
    except ValueError as exc:
        raise FormaClientError("FORMA_TIMEOUT_SECONDS must be a number.") from exc
    if timeout <= 0:
        raise FormaClientError("Timeout must be greater than zero.")
    return timeout


def request(method: str, params: dict[str, Any] | None = None, *, url: str | None = None, timeout: float | None = None) -> Any:
    payload = {
        "jsonrpc": "2.0",
        "id": f"forma-skill-{uuid.uuid4().hex}",
        "method": method,
        "params": params or {},
    }
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "User-Agent": "Forma-Agent-Skill/1.0",
    }
    token = os.environ.get("FORMA_AUTH_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    http_request = Request(_url(url), data=json.dumps(payload).encode(), headers=headers, method="POST")
    try:
        with urlopen(http_request, timeout=_timeout(timeout)) as response:
            result = json.loads(response.read().decode())
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace").strip()
        raise FormaClientError(f"Forma returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise FormaClientError(f"Could not reach Forma at {_url(url)}: {exc.reason}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FormaClientError("Forma returned invalid JSON.") from exc
    if not isinstance(result, dict):
        raise FormaClientError("Forma returned an invalid JSON-RPC response.")
    if result.get("error"):
        error = result["error"]
        message = error.get("message") if isinstance(error, dict) else str(error)
        raise FormaClientError(f"Forma JSON-RPC error: {message}")
    return result.get("result")


def call_tool(name: str, arguments: dict[str, Any], **options: Any) -> Any:
    result = request("tools/call", {"name": name, "arguments": arguments}, **options)
    if isinstance(result, dict) and "structuredContent" in result:
        return result["structuredContent"]
    return result


def _load(path_value: str) -> dict[str, Any]:
    value = json.load(sys.stdin) if path_value == "-" else json.loads(Path(path_value).read_text())
    if not isinstance(value, dict):
        raise FormaClientError("Project JSON must contain an object.")
    for key in ("project_ir", "hardware_ir"):
        if isinstance(value.get(key), dict):
            return value[key]
    return value


def _write(value: Any, output: str | None) -> None:
    rendered = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if not output or output == "-":
        sys.stdout.write(rendered)
    else:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered)
        print(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Call Forma from any Agent Skills host.")
    commands = parser.add_subparsers(dest="command", required=True)
    tools_parser = commands.add_parser("tools")
    compile_parser = commands.add_parser("compile")
    compile_parser.add_argument("project")
    compile_parser.add_argument(
        "--authoring-agent",
        required=True,
        choices=("openclaw", "opencode", "nemoclaw", "claude", "codex", "other"),
    )
    validate_parser = commands.add_parser("validate")
    validate_parser.add_argument("project")
    generate_parser = commands.add_parser("generate")
    generate_parser.add_argument("prompt")
    generate_parser.add_argument("--workflow", choices=("default", "web_research"), default="default")
    call_parser = commands.add_parser("call")
    call_parser.add_argument("tool")
    call_parser.add_argument("--arguments", default="{}")
    for command_parser in (tools_parser, compile_parser, validate_parser, generate_parser, call_parser):
        command_parser.add_argument("--url")
        command_parser.add_argument("--timeout", type=float)
        command_parser.add_argument("--output")
    return parser


def run(args: argparse.Namespace) -> Any:
    options = {"url": args.url, "timeout": args.timeout}
    if args.command == "tools":
        return request("tools/list", **options)
    if args.command == "compile":
        return call_tool("forma.compile_project", {"project_ir": _load(args.project), "authoring_agent": args.authoring_agent}, **options)
    if args.command == "validate":
        project = _load(args.project)
        return call_tool("forma.validate_circuit", {"components": project.get("components", []), "nets": project.get("nets", [])}, **options)
    if args.command == "generate":
        return call_tool("forma.generate_project", {"prompt": args.prompt, "workflow": args.workflow}, **options)
    arguments = json.loads(args.arguments)
    if not isinstance(arguments, dict):
        raise FormaClientError("--arguments must decode to an object.")
    return call_tool(args.tool, arguments, **options)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        _write(run(args), args.output)
        return 0
    except (FormaClientError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"forma: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
