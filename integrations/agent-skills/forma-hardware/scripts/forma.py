#!/usr/bin/env python3
"""Small MCP JSON-RPC client for the Forma Agent Skill."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
from pathlib import Path
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, urlopen
import uuid


DEFAULT_MCP_URL = "http://127.0.0.1:8000/mcp"
DEFAULT_TIMEOUT_SECONDS = 600.0


class FormaClientError(RuntimeError):
    """A connection, protocol, or Forma tool error."""


def _mcp_url(value: str | None) -> str:
    url = (value or os.environ.get("FORMA_MCP_URL") or DEFAULT_MCP_URL).strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise FormaClientError("FORMA_MCP_URL must be an http:// or https:// URL.")
    if parsed.path in {"", "/"}:
        parsed = parsed._replace(path="/mcp")
    return urlunparse(parsed)


def _timeout(value: float | None) -> float:
    if value is not None:
        timeout = value
    else:
        raw = os.environ.get("FORMA_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))
        try:
            timeout = float(raw)
        except ValueError as exc:
            raise FormaClientError("FORMA_TIMEOUT_SECONDS must be a number.") from exc
    if timeout <= 0:
        raise FormaClientError("The Forma timeout must be greater than zero.")
    return timeout


def _decode_response(raw: bytes, content_type: str) -> Any:
    text = raw.decode("utf-8")
    if "text/event-stream" not in content_type.lower():
        return json.loads(text)

    events: list[Any] = []
    for line in text.splitlines():
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data and data != "[DONE]":
            events.append(json.loads(data))
    if not events:
        raise FormaClientError("Forma returned an empty event stream.")
    return events[-1]


def request(
    method: str,
    params: dict[str, Any] | None = None,
    *,
    url: str | None = None,
    timeout: float | None = None,
) -> Any:
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

    http_request = Request(
        _mcp_url(url),
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(http_request, timeout=_timeout(timeout)) as response:
            result = _decode_response(response.read(), response.headers.get("Content-Type", "application/json"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        suffix = f": {detail}" if detail else ""
        raise FormaClientError(f"Forma returned HTTP {exc.code}{suffix}") from exc
    except URLError as exc:
        raise FormaClientError(f"Could not reach Forma at {_mcp_url(url)}: {exc.reason}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FormaClientError("Forma returned a response that was not valid JSON.") from exc

    if not isinstance(result, dict):
        raise FormaClientError("Forma returned an invalid JSON-RPC response.")
    if result.get("error"):
        error = result["error"]
        if isinstance(error, dict):
            message = error.get("message") or json.dumps(error, sort_keys=True)
        else:
            message = str(error)
        raise FormaClientError(f"Forma JSON-RPC error: {message}")
    if "result" not in result:
        raise FormaClientError("Forma JSON-RPC response did not include a result.")
    return result["result"]


def call_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    url: str | None = None,
    timeout: float | None = None,
) -> Any:
    result = request("tools/call", {"name": name, "arguments": arguments}, url=url, timeout=timeout)
    if isinstance(result, dict) and "structuredContent" in result:
        return result["structuredContent"]
    return result


def _load_json(path_value: str) -> Any:
    if path_value == "-":
        return json.load(sys.stdin)
    return json.loads(Path(path_value).read_text(encoding="utf-8"))


def _write_json(value: Any, output: str | None) -> None:
    rendered = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if not output or output == "-":
        sys.stdout.write(rendered)
        return
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")
    print(str(path))


def _project_ir(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise FormaClientError("The project JSON must contain an object.")
    for key in ("project_ir", "hardware_ir"):
        nested = value.get(key)
        if isinstance(nested, dict):
            return nested
    response = value.get("response")
    if isinstance(response, dict) and isinstance(response.get("project_ir"), dict):
        return response["project_ir"]
    return value


def _image_data_url(path_value: str) -> str:
    path = Path(path_value)
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _shared_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--url", help="Forma MCP URL; overrides FORMA_MCP_URL.")
    parser.add_argument("--timeout", type=float, help="HTTP timeout in seconds.")
    parser.add_argument("--output", help="Write JSON to this path instead of stdout.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Call Forma from Claude, Codex, or another Agent Skills host.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    tools = subparsers.add_parser("tools", help="List Forma MCP tools.")
    _shared_options(tools)

    config = subparsers.add_parser("config", help="Show credential-safe Forma runtime configuration.")
    _shared_options(config)

    generate = subparsers.add_parser("generate", help="Generate a structured Forma hardware project.")
    generate.add_argument("prompt", help="Complete hardware brief.")
    generate.add_argument("--workflow", choices=("default", "web_research"), default="default")
    generate.add_argument("--generate-image", action="store_true")
    generate.add_argument("--image-file", help="Optional reference image path.")
    generate.add_argument("--external-source-provider", choices=("firecrawl",))
    generate.add_argument("--past-jobs", action="store_true", help="Use relevant completed jobs as context.")
    generate.add_argument("--past-jobs-limit", type=int, choices=range(1, 9), default=3)
    _shared_options(generate)

    validate = subparsers.add_parser("validate", help="Validate components and nets from Forma project JSON.")
    validate.add_argument("project", help="Project JSON path, or - for stdin.")
    _shared_options(validate)

    job = subparsers.add_parser("job", help="Fetch one persisted A2A job.")
    job.add_argument("job_id")
    _shared_options(job)

    jobs = subparsers.add_parser("jobs", help="List persisted A2A jobs.")
    jobs.add_argument("--sender")
    jobs.add_argument("--status")
    jobs.add_argument("--limit", type=int, default=50)
    _shared_options(jobs)

    call = subparsers.add_parser("call", help="Call any discovered Forma MCP tool.")
    call.add_argument("tool")
    argument_source = call.add_mutually_exclusive_group()
    argument_source.add_argument("--arguments", default="{}", help="Tool arguments as a JSON object.")
    argument_source.add_argument("--arguments-file", help="Tool arguments JSON path, or - for stdin.")
    _shared_options(call)
    return parser


def run(args: argparse.Namespace) -> Any:
    options = {"url": args.url, "timeout": args.timeout}
    if args.command == "tools":
        return request("tools/list", **options)
    if args.command == "config":
        return call_tool("blueprint.debug_config", {}, **options)
    if args.command == "generate":
        arguments: dict[str, Any] = {
            "prompt": args.prompt,
            "workflow": args.workflow,
            "generate_image": args.generate_image,
            "past_jobs_limit": args.past_jobs_limit,
        }
        if args.image_file:
            arguments["image_data"] = _image_data_url(args.image_file)
        if args.external_source_provider:
            arguments["external_source_provider"] = args.external_source_provider
        if args.past_jobs:
            arguments["data_sources"] = ["past_jobs"]
        return call_tool("blueprint.generate_project", arguments, **options)
    if args.command == "validate":
        project = _project_ir(_load_json(args.project))
        components = project.get("components")
        nets = project.get("nets")
        if not isinstance(components, list) or not isinstance(nets, list):
            raise FormaClientError("The project JSON must contain components and nets arrays.")
        return call_tool("blueprint.validate_circuit", {"components": components, "nets": nets}, **options)
    if args.command == "job":
        return call_tool("blueprint.a2a.get_job", {"job_id": args.job_id}, **options)
    if args.command == "jobs":
        arguments = {"limit": args.limit}
        if args.sender:
            arguments["sender"] = args.sender
        if args.status:
            arguments["status"] = args.status
        return call_tool("blueprint.a2a.list_jobs", arguments, **options)
    if args.command == "call":
        arguments = _load_json(args.arguments_file) if args.arguments_file else json.loads(args.arguments)
        if not isinstance(arguments, dict):
            raise FormaClientError("Tool arguments must be a JSON object.")
        return call_tool(args.tool, arguments, **options)
    raise FormaClientError(f"Unknown command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = run(args)
        _write_json(result, args.output)
        return 0
    except (FormaClientError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"forma: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
