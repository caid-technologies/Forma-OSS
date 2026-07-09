#!/usr/bin/env python3
"""Verify OpenAI API access using repo-root dotenv settings."""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_ENV_FILE = ".env"
DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_PROMPT = "Reply with exactly: openai ok"
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_MAX_OUTPUT_TOKENS = 32
SUCCESS_STATUSES = {"completed"}
INCOMPLETE_STATUSES = {"incomplete"}
FAILURE_STATUSES = {"failed", "cancelled", "expired"}


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


def parse_float_env(env: dict[str, str], names: list[str], default: float | None = None) -> float | None:
    raw_value = first_env(env, names)
    if raw_value is None:
        return default
    try:
        return float(raw_value)
    except ValueError as exc:
        raise ConfigError(f"{names[0]} must be a number, got {raw_value!r}") from exc


def parse_int_env(env: dict[str, str], names: list[str], default: int | None = None) -> int | None:
    raw_value = first_env(env, names)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ConfigError(f"{names[0]} must be an integer, got {raw_value!r}") from exc


def parse_optional_float_env(env: dict[str, str], names: list[str]) -> float | None:
    raw_value = first_env(env, names)
    if raw_value is None or raw_value.lower() in {"default", "none", "omit"}:
        return None
    try:
        return float(raw_value)
    except ValueError as exc:
        raise ConfigError(f"{names[0]} must be a number, got {raw_value!r}") from exc


def mask(value: str | None, visible: int = 4) -> str:
    if not value:
        return "<missing>"
    if len(value) <= visible * 2:
        return "*" * len(value)
    return f"{value[:visible]}...{value[-visible:]} ({len(value)} chars)"


def normalize_base_url(value: str | None) -> str:
    base_url = (value or DEFAULT_BASE_URL).strip().rstrip("/")
    if not base_url:
        return DEFAULT_BASE_URL
    parsed = urllib.parse.urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigError(f"OPENAI_BASE_URL must be an absolute URL, got {base_url!r}")
    return base_url


def compact_error_body(body: str, max_chars: int = 900) -> str:
    stripped = body.strip()
    if not stripped:
        return "<empty response>"
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        parsed = None

    if isinstance(parsed, dict):
        error = parsed.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            error_type = error.get("type")
            code = error.get("code")
            parts = [str(part) for part in [message, error_type, code] if part]
            if parts:
                stripped = " | ".join(parts)

    if len(stripped) <= max_chars:
        return stripped
    return stripped[:max_chars] + "...<truncated>"


def parse_json_argument(name: str, raw_value: str) -> Any:
    try:
        return json.loads(raw_value)
    except json.JSONDecodeError as exc:
        example = 'OPENAI_INPUT_TEMPLATE={"input":"{prompt}"}'
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


def build_headers(api_key: str, env: dict[str, str]) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    project_id = first_env(env, ["OPENAI_PROJECT_ID"])
    organization_id = first_env(env, ["OPENAI_ORG_ID", "OPENAI_ORGANIZATION"])
    if project_id:
        headers["OpenAI-Project"] = project_id
    if organization_id:
        headers["OpenAI-Organization"] = organization_id
    return headers


def request_json(
    method: str,
    url: str,
    headers: dict[str, str],
    *,
    payload: dict[str, Any] | None = None,
    timeout_seconds: float,
) -> Any:
    request_headers = dict(headers)
    body: bytes | None = None
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    request = urllib.request.Request(url=url, data=body, headers=request_headers, method=method)
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
            if any(
                secret_word in lowered
                for secret_word in ["secret", "api_key", "apikey", "authorization", "access_token", "refresh_token"]
            ):
                compacted[key] = "<redacted>"
            elif key in {"output", "output_text"} and not show_output:
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


def response_preview(response: Any) -> dict[str, Any]:
    if not isinstance(response, dict):
        return {"type": type(response).__name__}
    preview: dict[str, Any] = {}
    for key in ["id", "object", "model", "status"]:
        if key in response:
            preview[key] = response[key]
    usage = response.get("usage")
    if isinstance(usage, dict):
        preview["usage"] = {
            key: usage[key]
            for key in ["input_tokens", "output_tokens", "total_tokens"]
            if key in usage
        }
    if "output_text" in response:
        preview["output_text"] = response["output_text"]
    elif "output" in response:
        preview["output"] = response["output"]
    return preview


def build_response_payload(env: dict[str, str], args: argparse.Namespace, model: str) -> dict[str, Any]:
    prompt = args.prompt or first_env(env, ["OPENAI_TEST_PROMPT"], DEFAULT_PROMPT) or DEFAULT_PROMPT
    raw_template = args.input_json or first_env(env, ["OPENAI_INPUT_TEMPLATE", "OPENAI_REQUEST_JSON"])

    if raw_template:
        parsed = apply_template_values(
            parse_json_argument("--input-json" if args.input_json else "OPENAI_INPUT_TEMPLATE", raw_template),
            prompt=prompt,
        )
        if isinstance(parsed, dict):
            payload = dict(parsed)
        else:
            payload = {"input": parsed}
    else:
        payload = {"input": prompt}

    if "input" not in payload:
        raise ConfigError("OpenAI Responses request payload must contain an 'input' key.")
    payload.setdefault("model", model)

    max_output_tokens = args.max_output_tokens
    if max_output_tokens is None:
        max_output_tokens = parse_int_env(env, ["OPENAI_TEST_MAX_OUTPUT_TOKENS"], DEFAULT_MAX_OUTPUT_TOKENS)
    if max_output_tokens is not None:
        if max_output_tokens <= 0:
            raise ConfigError("OPENAI_TEST_MAX_OUTPUT_TOKENS must be greater than zero.")
        payload.setdefault("max_output_tokens", max_output_tokens)

    temperature = parse_optional_float_env(env, ["OPENAI_TEMPERATURE", "LLM_TEMPERATURE"])
    if temperature is not None:
        payload.setdefault("temperature", temperature)

    reasoning_effort = first_env(env, ["OPENAI_REASONING_EFFORT", "LLM_REASONING_EFFORT"])
    if reasoning_effort and reasoning_effort.lower() not in {"default", "none", "omit"}:
        reasoning = payload.get("reasoning") if isinstance(payload.get("reasoning"), dict) else {}
        reasoning.setdefault("effort", reasoning_effort)
        payload.setdefault("reasoning", reasoning)

    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify OpenAI API access using .env configuration.")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE, help="Dotenv file to load. Defaults to .env.")
    parser.add_argument("--model", help="Override OPENAI_MODEL.")
    parser.add_argument("--base-url", help="Override OPENAI_BASE_URL. Defaults to https://api.openai.com/v1.")
    parser.add_argument(
        "--input-json",
        help="Override OPENAI_INPUT_TEMPLATE. Pass either a full Responses request JSON or an input value.",
    )
    parser.add_argument("--prompt", help="Override OPENAI_TEST_PROMPT.")
    parser.add_argument("--timeout-seconds", type=float, help="HTTP client timeout in seconds.")
    parser.add_argument("--max-output-tokens", type=int, help="Override OPENAI_TEST_MAX_OUTPUT_TOKENS.")
    parser.add_argument("--skip-model-check", action="store_true", help="Skip GET /models/{model}.")
    parser.add_argument("--show-output", action="store_true", help="Print full response output.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        env_file = Path(args.env_file).expanduser()
        file_env = load_env_file(env_file)
        env = dict(os.environ)
        env.update(file_env)

        api_key = first_env(env, ["OPENAI_API_KEY", "LLM_API_KEY"])
        if not api_key:
            raise ConfigError("Missing OPENAI_API_KEY in the selected env file or process environment.")

        model = args.model or first_env(env, ["OPENAI_MODEL", "LLM_MODEL"], DEFAULT_MODEL) or DEFAULT_MODEL
        base_url = normalize_base_url(args.base_url or first_env(env, ["OPENAI_BASE_URL"]))
        timeout_seconds = (
            args.timeout_seconds
            or parse_float_env(env, ["OPENAI_TIMEOUT_SECONDS", "LLM_TIMEOUT_SECONDS"], DEFAULT_TIMEOUT_SECONDS)
            or DEFAULT_TIMEOUT_SECONDS
        )
        headers = build_headers(api_key, env)

        print(f"[openai-check] env_file={env_file}")
        print(f"[openai-check] base_url={base_url}")
        print(f"[openai-check] model={model}")
        print(f"[openai-check] api_key={mask(api_key)}")
        project_id = first_env(env, ["OPENAI_PROJECT_ID"])
        organization_id = first_env(env, ["OPENAI_ORG_ID", "OPENAI_ORGANIZATION"])
        if project_id:
            print(f"[openai-check] project={mask(project_id)}")
        if organization_id:
            print(f"[openai-check] organization={mask(organization_id)}")

        if not args.skip_model_check:
            model_url = f"{base_url}/models/{urllib.parse.quote(model, safe='')}"
            model_response = request_json("GET", model_url, headers, timeout_seconds=timeout_seconds)
            print_json(
                "[openai-check] model",
                {key: model_response.get(key) for key in ["id", "object", "owned_by"] if isinstance(model_response, dict)},
                show_output=args.show_output,
            )

        payload = build_response_payload(env, args, model)
        print_json("[openai-check] request", payload, show_output=args.show_output)

        response_url = f"{base_url}/responses"
        response = request_json("POST", response_url, headers, payload=payload, timeout_seconds=timeout_seconds)
        preview = response_preview(response)
        print_json("[openai-check] response", preview, show_output=args.show_output)

        status = response.get("status") if isinstance(response, dict) else None
        if status is None and isinstance(response, dict) and response.get("id"):
            print("[openai-check] success: OpenAI returned a response.")
            return 0
        if isinstance(status, str) and status.lower() in SUCCESS_STATUSES:
            print("[openai-check] success: OpenAI returned a completed response.")
            return 0
        if isinstance(status, str) and status.lower() in INCOMPLETE_STATUSES:
            print("[openai-check] incomplete: OpenAI returned a response but it was incomplete.", file=sys.stderr)
            return 2
        if isinstance(status, str) and status.lower() in FAILURE_STATUSES:
            print(f"[openai-check] failed: OpenAI response ended with {status}.", file=sys.stderr)
            return 2

        print(
            f"[openai-check] inconclusive: expected completed response, got {status or 'no status field'}.",
            file=sys.stderr,
        )
        return 2

    except ConfigError as exc:
        print(f"[openai-check] config error: {exc}", file=sys.stderr)
        return 1
    except RequestError as exc:
        print(f"[openai-check] request error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n[openai-check] interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
