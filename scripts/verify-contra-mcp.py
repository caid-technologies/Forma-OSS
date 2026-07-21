#!/usr/bin/env python3
"""Verify Contra MCP endpoint metadata and optional authenticated access."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT_DIR / ".logs" / "contra-mcp"
DEFAULT_ENDPOINT = "https://contra.com/mcp"
DEFAULT_METADATA_URL = "https://contra.com/.well-known/oauth-protected-resource/mcp"
TOKEN_ENV_NAMES = ("CONTRA_MCP_TOKEN", "CONTRA_API_TOKEN", "CONTRA_TOKEN")


@dataclass(frozen=True)
class HttpResult:
    status: int
    headers: dict[str, str]
    body: str

    def json_body(self) -> Any:
        return json.loads(self.body) if self.body.strip() else None


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def first_env(names: tuple[str, ...]) -> tuple[str | None, str | None]:
    for name in names:
        value = os.getenv(name)
        if value:
            return name, value
    return None, None


def header_value(headers: dict[str, str], name: str) -> str | None:
    expected = name.lower()
    for key, value in headers.items():
        if key.lower() == expected:
            return value
    return None


def request(
    url: str,
    *,
    method: str = "GET",
    token: str | None = None,
    body: dict[str, Any] | None = None,
    timeout_seconds: float = 15.0,
) -> HttpResult:
    data = None
    headers = {
        "Accept": "application/json, text/event-stream",
        "User-Agent": "Forma-OSS/contra-mcp-verifier",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return HttpResult(response.status, dict(response.headers.items()), raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return HttpResult(exc.code, dict(exc.headers.items()), raw)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default=os.getenv("CONTRA_MCP_ENDPOINT", DEFAULT_ENDPOINT))
    parser.add_argument("--metadata-url", default=os.getenv("CONTRA_MCP_METADATA_URL", DEFAULT_METADATA_URL))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--require-auth", action="store_true", help="Fail if no Contra bearer token is available.")
    parser.add_argument("--timeout-seconds", type=float, default=15.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv if argv is not None else sys.argv[1:]))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    token_env, token = first_env(TOKEN_ENV_NAMES)

    report: dict[str, Any] = {
        "created_at": utc_stamp(),
        "endpoint": args.endpoint,
        "metadata_url": args.metadata_url,
        "token_env": token_env,
        "has_token": bool(token),
    }

    metadata = request(args.metadata_url, timeout_seconds=args.timeout_seconds)
    report["metadata_status"] = metadata.status
    report["metadata_headers"] = metadata.headers
    try:
        report["metadata"] = metadata.json_body()
    except json.JSONDecodeError:
        report["metadata_raw"] = metadata.body

    challenge = request(args.endpoint, timeout_seconds=args.timeout_seconds)
    report["unauthenticated_status"] = challenge.status
    report["www_authenticate"] = header_value(challenge.headers, "www-authenticate")
    try:
        report["unauthenticated_body"] = challenge.json_body()
    except json.JSONDecodeError:
        report["unauthenticated_body_raw"] = challenge.body

    if token:
        initialize_body = {
            "jsonrpc": "2.0",
            "id": "contra-mcp-verify",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "blueprint-edge",
                    "version": "0.1.0",
                },
            },
        }
        authenticated = request(
            args.endpoint,
            method="POST",
            token=token,
            body=initialize_body,
            timeout_seconds=args.timeout_seconds,
        )
        report["authenticated_status"] = authenticated.status
        report["authenticated_headers"] = authenticated.headers
        try:
            report["authenticated_body"] = authenticated.json_body()
        except json.JSONDecodeError:
            report["authenticated_body_raw"] = authenticated.body
        report["status"] = "passed" if 200 <= authenticated.status < 300 else "failed"
    elif args.require_auth:
        report["status"] = "failed"
        report["error"] = f"missing Contra token; set one of {', '.join(TOKEN_ENV_NAMES)}"
    else:
        report["status"] = "auth_required"
        report["message"] = "Contra MCP endpoint is reachable and requires a bearer token."

    report_path = args.output_dir / f"contra-mcp-{utc_stamp()}.json"
    latest_path = args.output_dir / "latest.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    latest_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"[contra-mcp] endpoint={args.endpoint}")
    print(f"[contra-mcp] metadata_status={report.get('metadata_status')}")
    print(f"[contra-mcp] unauthenticated_status={report.get('unauthenticated_status')}")
    print(f"[contra-mcp] status={report['status']}")
    print(f"[contra-mcp] report={report_path}")
    print(f"[contra-mcp] latest={latest_path}")

    return 1 if report["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
