#!/usr/bin/env python3
"""Verify a Runpod Serverless queue endpoint using repo-root dotenv settings."""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_ENV_FILE = ".env"
DEFAULT_PROMPT = "Reply with exactly: runpod serverless ok"
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_WAIT_MS = 90_000
DEFAULT_POLL_TIMEOUT_SECONDS = 180.0
DEFAULT_POLL_INTERVAL_SECONDS = 5.0
MAX_RUNSYNC_WAIT_MS = 300_000
SUCCESS_STATUSES = {"COMPLETED"}
PENDING_STATUSES = {"IN_QUEUE", "IN_PROGRESS"}
FAILURE_STATUSES = {"FAILED", "ERROR", "TIMED_OUT", "CANCELLED"}


class ConfigError(RuntimeError):
    pass


class RequestError(RuntimeError):
    def __init__(self, method: str, url: str, status_code: int | None, body: str) -> None:
        self.method = method
        self.url = url
        self.status_code = status_code
        self.body = body
        status = f"HTTP {status_code}" if status_code is not None else "request failed"
        super().__init__(f"{method} {url} returned {status}: {body}")


def _strip_inline_comment(value: str) -> str:
    quote: str | None = None
    escaped = False

    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote == '"':
            escaped = True
            continue
        if char in {"'", '"'}:
            if quote is None:
                quote = char
            elif quote == char:
                quote = None
            continue
        if char == "#" and quote is None and (index == 0 or value[index - 1].isspace()):
            return value[:index].strip()

    return value.strip()


def _parse_env_value(raw_value: str) -> str:
    value = _strip_inline_comment(raw_value)
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        try:
            parsed = ast.literal_eval(value)
        except (SyntaxError, ValueError):
            parsed = value[1:-1]
        return str(parsed)
    return value


def load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        raise ConfigError(f"Env file not found: {path}")

    env: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            continue

        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key:
            raise ConfigError(f"Invalid empty key in {path}:{line_number}")
        env[key] = _parse_env_value(raw_value)

    return env


def first_env(env: dict[str, str], names: list[str], default: str | None = None) -> str | None:
    for name in names:
        value = env.get(name)
        if value is not None and value.strip():
            return value.strip()
    return default


def parse_int_env(env: dict[str, str], names: list[str]) -> int | None:
    raw_value = first_env(env, names)
    if raw_value is None:
        return None
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ConfigError(f"{names[0]} must be an integer, got {raw_value!r}") from exc


def parse_float_env(env: dict[str, str], names: list[str]) -> float | None:
    raw_value = first_env(env, names)
    if raw_value is None:
        return None
    try:
        return float(raw_value)
    except ValueError as exc:
        raise ConfigError(f"{names[0]} must be a number, got {raw_value!r}") from exc


def clamp_wait_ms(value: int) -> int:
    if value < 1_000:
        return 1_000
    if value > MAX_RUNSYNC_WAIT_MS:
        return MAX_RUNSYNC_WAIT_MS
    return value


def mask(value: str | None, visible: int = 4) -> str:
    if not value:
        return "<missing>"
    if len(value) <= visible * 2:
        return "*" * len(value)
    return f"{value[:visible]}...{value[-visible:]} ({len(value)} chars)"


def derive_endpoint_base_url(env: dict[str, str], args: argparse.Namespace) -> tuple[str, str | None]:
    endpoint_id = args.endpoint_id or first_env(env, ["RUNPOD_ENDPOINT_ID", "ENDPOINT_ID"])
    endpoint_url = args.endpoint_url or first_env(env, ["RUNPOD_ENDPOINT_URL"])

    if endpoint_url:
        parsed = urllib.parse.urlparse(endpoint_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ConfigError(f"RUNPOD_ENDPOINT_URL must be an absolute URL, got {endpoint_url!r}")

        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) >= 2 and path_parts[0] == "v2":
            derived_endpoint_id = urllib.parse.unquote(path_parts[1])
            base_path = f"/v2/{urllib.parse.quote(derived_endpoint_id, safe='')}"
            base_url = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, base_path, "", "", ""))
            return base_url.rstrip("/"), endpoint_id or derived_endpoint_id

    if endpoint_id:
        quoted_endpoint_id = urllib.parse.quote(endpoint_id, safe="")
        return f"https://api.runpod.ai/v2/{quoted_endpoint_id}", endpoint_id

    raise ConfigError("Missing RUNPOD_ENDPOINT_ID or a RUNPOD_ENDPOINT_URL containing /v2/<endpoint-id>.")


def parse_json_argument(name: str, raw_value: str) -> Any:
    try:
        return json.loads(raw_value)
    except json.JSONDecodeError as exc:
        example = 'RUNPOD_INPUT_TEMPLATE={"prompt":"{prompt}"}'
        raise ConfigError(
            f"{name} must be valid JSON: {exc.msg} at char {exc.pos}. "
            f"For a prompt template, use: {example}"
        ) from exc


def apply_template_values(value: Any, *, prompt: str) -> Any:
    if isinstance(value, dict):
        return {key: apply_template_values(item, prompt=prompt) for key, item in value.items()}
    if isinstance(value, list):
        return [apply_template_values(item, prompt=prompt) for item in value]
    if isinstance(value, str):
        return value.replace("{prompt}", prompt)
    return value


def build_default_input(env: dict[str, str]) -> dict[str, Any]:
    input_payload: dict[str, Any] = {
        "prompt": first_env(env, ["RUNPOD_TEST_PROMPT"], DEFAULT_PROMPT),
    }

    model = first_env(env, ["RUNPOD_MODEL"])
    if model:
        input_payload["model"] = model

    temperature = parse_float_env(env, ["RUNPOD_TEMPERATURE"])
    if temperature is not None:
        input_payload["temperature"] = temperature

    return input_payload


def build_run_payload(env: dict[str, str], args: argparse.Namespace) -> dict[str, Any]:
    prompt = first_env(env, ["RUNPOD_TEST_PROMPT"], DEFAULT_PROMPT) or DEFAULT_PROMPT
    raw_template = args.input_json or first_env(env, ["RUNPOD_INPUT_TEMPLATE"])
    if raw_template:
        parsed = parse_json_argument("--input-json" if args.input_json else "RUNPOD_INPUT_TEMPLATE", raw_template)
        parsed = apply_template_values(parsed, prompt=prompt)
        if isinstance(parsed, dict) and "input" in parsed:
            payload = parsed
        else:
            payload = {"input": parsed}
    else:
        payload = {"input": build_default_input(env)}

    if not isinstance(payload, dict):
        raise ConfigError("Runpod request payload must be a JSON object.")
    if "input" not in payload:
        raise ConfigError("Runpod request payload must contain an 'input' key.")

    execution_timeout_ms = parse_int_env(env, ["RUNPOD_EXECUTION_TIMEOUT_MS"])
    ttl_ms = parse_int_env(env, ["RUNPOD_TTL_MS"])
    policy: dict[str, Any] = {}
    if isinstance(payload.get("policy"), dict):
        policy.update(payload["policy"])
    if execution_timeout_ms is not None:
        policy.setdefault("executionTimeout", execution_timeout_ms)
    if ttl_ms is not None:
        policy.setdefault("ttl", ttl_ms)
    if policy:
        payload["policy"] = policy

    return payload


def request_json(
    method: str,
    url: str,
    api_key: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout_seconds: float,
) -> Any:
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    body: bytes | None = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    request = urllib.request.Request(url=url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            response_body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RequestError(method, url, exc.code, compact_error_body(error_body)) from exc
    except urllib.error.URLError as exc:
        raise RequestError(method, url, None, str(exc.reason)) from exc
    except TimeoutError as exc:
        raise RequestError(method, url, None, f"timed out after {timeout_seconds:.1f}s") from exc

    if not response_body.strip():
        return {}
    try:
        return json.loads(response_body)
    except json.JSONDecodeError:
        return response_body


def get_status(value: Any) -> str | None:
    if isinstance(value, dict):
        status = value.get("status")
        if isinstance(status, str):
            return status
    return None


def get_job_id(value: Any) -> str | None:
    if isinstance(value, dict):
        job_id = value.get("id")
        if isinstance(job_id, str) and job_id.strip():
            return job_id.strip()
    return None


def poll_job_status(
    base_url: str,
    job_id: str,
    api_key: str,
    *,
    timeout_seconds: float,
    request_timeout_seconds: float,
    interval_seconds: float,
    show_output: bool,
) -> Any:
    deadline = time.monotonic() + timeout_seconds
    status_url = f"{base_url}/status/{urllib.parse.quote(job_id, safe='')}"
    last_result: Any = None
    last_status: str | None = None

    while time.monotonic() < deadline:
        sleep_seconds = min(interval_seconds, max(0.0, deadline - time.monotonic()))
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

        last_result = request_json("GET", status_url, api_key, timeout_seconds=request_timeout_seconds)
        current_status = get_status(last_result)
        if current_status != last_status:
            print(f"[runpod-check] status={current_status or 'UNKNOWN'}")
            last_status = current_status

        if current_status in SUCCESS_STATUSES or current_status in FAILURE_STATUSES:
            print_json("[runpod-check] final status", last_result, show_output=show_output)
            return last_result

    print_json("[runpod-check] last status", last_result, show_output=show_output)
    return last_result


def compact_error_body(body: str, max_chars: int = 700) -> str:
    stripped = body.strip()
    if not stripped:
        return "<empty response>"
    if len(stripped) <= max_chars:
        return stripped
    return stripped[:max_chars] + "...<truncated>"


def summarize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {"type": "object", "keys": sorted(value.keys())[:20]}
    if isinstance(value, list):
        return {"type": "array", "items": len(value)}
    if isinstance(value, str):
        return value if len(value) <= 240 else value[:240] + "...<truncated>"
    return value


def compact_response(value: Any, *, show_output: bool = False) -> Any:
    if isinstance(value, dict):
        compacted: dict[str, Any] = {}
        for key, item in value.items():
            lowered = key.lower()
            if any(secret_word in lowered for secret_word in ["secret", "token", "api_key", "apikey", "authorization"]):
                compacted[key] = "<redacted>"
            elif key == "output" and not show_output:
                compacted[key] = summarize_value(item)
            else:
                compacted[key] = compact_response(item, show_output=show_output)
        return compacted
    if isinstance(value, list):
        if len(value) > 10 and not show_output:
            return [compact_response(item, show_output=show_output) for item in value[:10]] + ["...<truncated>"]
        return [compact_response(item, show_output=show_output) for item in value]
    if isinstance(value, str) and len(value) > 500 and not show_output:
        return value[:500] + "...<truncated>"
    return value


def print_json(label: str, value: Any, *, show_output: bool = False) -> None:
    compacted = compact_response(value, show_output=show_output)
    print(f"{label}:")
    print(json.dumps(compacted, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify a Runpod Serverless queue endpoint using .env configuration."
    )
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE, help="Dotenv file to load. Defaults to .env.")
    parser.add_argument("--endpoint-id", help="Override RUNPOD_ENDPOINT_ID.")
    parser.add_argument("--endpoint-url", help="Override RUNPOD_ENDPOINT_URL.")
    parser.add_argument(
        "--input-json",
        help="Override RUNPOD_INPUT_TEMPLATE. Pass either an input object or the full Runpod request JSON.",
    )
    parser.add_argument("--wait-ms", type=int, help="Runpod /runsync wait parameter in milliseconds.")
    parser.add_argument("--timeout-seconds", type=float, help="HTTP client timeout in seconds.")
    parser.add_argument("--poll-timeout-seconds", type=float, help="How long to poll /status after a pending /runsync.")
    parser.add_argument("--poll-interval-seconds", type=float, help="Seconds between /status polls.")
    parser.add_argument("--skip-health", action="store_true", help="Skip the /health check.")
    parser.add_argument("--health-only", action="store_true", help="Only run the /health check.")
    parser.add_argument(
        "--accept-pending",
        action="store_true",
        help="Exit successfully if /runsync reaches Runpod but returns IN_QUEUE or IN_PROGRESS.",
    )
    parser.add_argument("--show-output", action="store_true", help="Print the full Runpod output field.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        env_file = Path(args.env_file).expanduser()
        file_env = load_env_file(env_file)
        env = dict(os.environ)
        env.update(file_env)

        api_key = first_env(env, ["RUNPOD_API_KEY"])
        if not api_key:
            raise ConfigError("Missing RUNPOD_API_KEY in the selected env file or process environment.")

        base_url, endpoint_id = derive_endpoint_base_url(env, args)
        wait_ms = clamp_wait_ms(
            args.wait_ms
            or parse_int_env(env, ["RUNPOD_WAIT_MS", "RUNPOD_RUNSYNC_WAIT_MS"])
            or DEFAULT_WAIT_MS
        )
        env_timeout = parse_float_env(env, ["RUNPOD_TIMEOUT_SECONDS"])
        timeout_seconds = args.timeout_seconds or env_timeout or DEFAULT_TIMEOUT_SECONDS
        timeout_seconds = max(timeout_seconds, (wait_ms / 1000.0) + 15.0)
        poll_timeout_seconds = (
            args.poll_timeout_seconds
            or parse_float_env(env, ["RUNPOD_POLL_TIMEOUT_SECONDS"])
            or DEFAULT_POLL_TIMEOUT_SECONDS
        )
        poll_interval_seconds = (
            args.poll_interval_seconds
            or parse_float_env(env, ["RUNPOD_POLL_INTERVAL_SECONDS"])
            or DEFAULT_POLL_INTERVAL_SECONDS
        )
        poll_interval_seconds = max(1.0, poll_interval_seconds)

        print(f"[runpod-check] env_file={env_file}")
        print(f"[runpod-check] endpoint_id={mask(endpoint_id)}")
        print(f"[runpod-check] endpoint_base={base_url}")
        print(f"[runpod-check] api_key={mask(api_key)}")

        if not args.skip_health:
            health_url = f"{base_url}/health"
            health = request_json("GET", health_url, api_key, timeout_seconds=timeout_seconds)
            print_json("[runpod-check] health", health, show_output=args.show_output)

        if args.health_only:
            print("[runpod-check] health check completed.")
            return 0

        payload = build_run_payload(env, args)
        print_json("[runpod-check] request", payload, show_output=args.show_output)

        run_url = f"{base_url}/runsync?{urllib.parse.urlencode({'wait': wait_ms})}"
        result = request_json("POST", run_url, api_key, payload=payload, timeout_seconds=timeout_seconds)
        print_json("[runpod-check] runsync", result, show_output=args.show_output)

        status = get_status(result)
        job_id = get_job_id(result)
        if status in PENDING_STATUSES and job_id and not args.accept_pending:
            print(
                f"[runpod-check] runsync returned {status}; polling /status for up to "
                f"{poll_timeout_seconds:.0f}s."
            )
            result = poll_job_status(
                base_url,
                job_id,
                api_key,
                timeout_seconds=poll_timeout_seconds,
                request_timeout_seconds=timeout_seconds,
                interval_seconds=poll_interval_seconds,
                show_output=args.show_output,
            )
            status = get_status(result)

        if status in SUCCESS_STATUSES:
            print("[runpod-check] success: Runpod Serverless returned COMPLETED.")
            return 0
        if args.accept_pending and status in PENDING_STATUSES:
            print(f"[runpod-check] reachable: job is still {status}.")
            return 0
        if status in FAILURE_STATUSES:
            print(f"[runpod-check] failed: Runpod job ended with {status}.", file=sys.stderr)
            return 2

        print(
            f"[runpod-check] inconclusive: expected COMPLETED, got {status or 'no status field'}.",
            file=sys.stderr,
        )
        return 2

    except ConfigError as exc:
        print(f"[runpod-check] config error: {exc}", file=sys.stderr)
        return 1
    except RequestError as exc:
        print(f"[runpod-check] request error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n[runpod-check] interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
