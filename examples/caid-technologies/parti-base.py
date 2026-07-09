#!/usr/bin/env python3
"""Probe caid-technologies/parti-base through the configured Runpod endpoint.

This script intentionally does not create a Blueprint project and does not use
generation fallback. It sends small raw chat/completions requests so the saved
results show how the model itself behaves.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


MODEL = "caid-technologies/parti-base"
ENV_FILE = ".env"
OUTPUT_DIR = "examples/results"
TIMEOUT_SECONDS = 1200.0
TEMPERATURE = 0.2
MAX_TOKENS = 500
USER_PROJECT_PROMPT = (
    "Design a compact blue desktop environmental monitor with an OLED display, "
    "temperature and humidity sensing, USB-C power, and optional battery operation."
)
SECRET_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9_-]{8,}|rpa_[A-Za-z0-9_-]{8,}|nvapi-[A-Za-z0-9_-]{8,}|"
    r"[A-Za-z0-9]{8}\.[A-Za-z0-9._-]{16,})"
)
COMPONENT_TITLE_VALUES = {
    "main mcu",
    "mcu",
    "main controller",
    "microcontroller",
    "controller",
    "sensor",
    "display",
    "battery",
    "resistor",
    "led",
    "component",
    "module",
    "power module",
}
COMPONENT_TITLE_TOKENS = {
    "mcu",
    "microcontroller",
    "sensor",
    "display",
    "battery",
    "resistor",
    "led",
    "module",
    "component",
}


@dataclass(frozen=True)
class Probe:
    name: str
    system: str
    user: str
    max_tokens: int = MAX_TOKENS
    temperature: float = TEMPERATURE
    response_format: Optional[dict[str, str]] = None


def utc_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def repo_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return ROOT_DIR / path


def load_env_file(path: Path) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError as exc:
        raise RuntimeError("python-dotenv is required. Install the repo requirements first.") from exc
    if not path.exists():
        raise RuntimeError(f"Env file not found: {path}")
    load_dotenv(path, override=True)


def scrub(value: Any) -> Any:
    if isinstance(value, str):
        return SECRET_PATTERN.sub(lambda match: match.group(0)[:5] + "...redacted", value)
    if isinstance(value, list):
        return [scrub(item) for item in value]
    if isinstance(value, dict):
        return {str(key): scrub(item) for key, item in value.items()}
    return value


def strip_markdown_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def extract_json_object(text: str) -> Optional[dict[str, Any]]:
    decoder = json.JSONDecoder()
    cleaned = strip_markdown_fence(text)
    for index, char in enumerate(cleaned):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(cleaned[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def message_content(response: dict[str, Any]) -> str:
    choices = response.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict)).strip()
    if isinstance(content, str):
        return content.strip()
    text = choices[0].get("text")
    return text.strip() if isinstance(text, str) else ""


def clean_text(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    cleaned = value.strip().replace("_", " ")
    cleaned = re.sub(r"\s*rewrite\s*\d+\s*$", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if cleaned.lower() in {"", "unknown", "n/a", "na", "none", "null", "new", "new__rewrite_1"}:
        return None
    return cleaned or None


def normalized_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.strip().lower()).strip()


def is_component_like_title(value: Optional[str]) -> bool:
    normalized = normalized_text(value or "")
    if not normalized:
        return True
    if normalized in COMPONENT_TITLE_VALUES:
        return True
    compact = normalized.replace(" ", "")
    if re.fullmatch(r"(u|r|c|sen|disp|bat|led|mcu)\d*", compact):
        return True
    tokens = normalized.split()
    return len(tokens) <= 3 and any(token in COMPONENT_TITLE_TOKENS for token in tokens)


def seed_title(seed: dict[str, Any]) -> Optional[str]:
    for key in ("project_title", "title", "display_name", "project_name", "seed_project_name"):
        text = clean_text(seed.get(key))
        if text:
            return text
    return None


def seed_summary(seed: dict[str, Any]) -> Optional[str]:
    for key in ("summary", "description", "project_summary", "new_prompt"):
        text = clean_text(seed.get(key))
        if text:
            return text
    return None


def classify_seed(seed: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not seed:
        return {"status": "fail", "reason": "no JSON object extracted"}
    title = seed_title(seed)
    summary = seed_summary(seed)
    failures: list[str] = []
    if seed.get("synthetic") is True or seed.get("seed_true") is True:
        failures.append("seed is marked synthetic")
    if is_component_like_title(title):
        failures.append(f"title is component-like: {title!r}")
    if not summary:
        failures.append("summary is missing or placeholder")
    return {
        "status": "fail" if failures else "pass",
        "title": title,
        "summary": summary,
        "failures": failures,
    }


def configure_runpod_env() -> None:
    os.environ["LLM_PROVIDER"] = "runpod"
    os.environ["LLM_ALLOWED_PROVIDERS"] = "runpod"
    os.environ["RUNPOD_MODEL"] = MODEL
    os.environ["RUNPOD_OPENAI_MODEL"] = MODEL
    os.environ["RUNPOD_ALLOWED_MODELS"] = MODEL
    os.environ["RUNPOD_TIMEOUT_SECONDS"] = str(TIMEOUT_SECONDS)
    os.environ["LLM_TIMEOUT_SECONDS"] = str(TIMEOUT_SECONDS)
    os.environ["RUNPOD_MAX_TOKENS"] = str(MAX_TOKENS)
    os.environ["RUNPOD_TEMPERATURE"] = str(TEMPERATURE)
    os.environ["STRICT_RUNPOD"] = "true"
    os.environ["STRICT_LLM"] = "true"
    os.environ["RUNPOD_FALLBACK_MODEL"] = ""
    os.environ["RUNPOD_OPENAI_FALLBACK_MODEL"] = ""
    os.environ["LLM_FALLBACK_MODEL"] = ""
    os.environ["BLUEPRINT_DISABLE_GENERATION_FALLBACK"] = "true"
    os.environ["BLUEPRINT_STRICT_GENERATION"] = "true"
    os.environ["LLM_DISABLE_FALLBACK"] = "true"


def build_probes() -> list[Probe]:
    adapter_seed_prompt = (
        "You are Parti, a hardware project seed generator. Return only one concise JSON object. "
        "Give a concrete project name, a one sentence summary, and up to eight hardware role hints. "
        "Do not use unknown, new__, synthetic, seed_ref, visual_ref, or placeholder values.\n"
        f"User request: {USER_PROJECT_PROMPT}"
    )
    strict_seed_prompt = (
        "Return only valid JSON for a hardware project seed. Use this exact shape:\n"
        "{\"project_title\":\"...\",\"summary\":\"...\",\"hardware_roles\":[\"...\"]}\n"
        "Rules: project_title must be a complete product/project name, not a component name; "
        "summary must be one concrete sentence; never output synthetic=true; never output Main_MCU.\n"
        f"User request: {USER_PROJECT_PROMPT}"
    )
    simple_json_prompt = (
        "Return only valid JSON with fields project_title and summary for this hardware project:\n"
        f"{USER_PROJECT_PROMPT}"
    )
    plain_chat_prompt = "Reply with exactly: runpod parti base ok"

    return [
        Probe(
            name="adapter_seed_prompt",
            system="You produce concise JSON only. Do not include markdown.",
            user=adapter_seed_prompt,
            response_format={"type": "json_object"},
        ),
        Probe(
            name="strict_seed_prompt",
            system="You produce concise JSON only. Do not include markdown.",
            user=strict_seed_prompt,
            response_format={"type": "json_object"},
        ),
        Probe(
            name="simple_json_prompt",
            system="You produce concise JSON only. Do not include markdown.",
            user=simple_json_prompt,
            response_format={"type": "json_object"},
        ),
        Probe(
            name="plain_chat_prompt",
            system="Reply exactly as requested.",
            user=plain_chat_prompt,
            max_tokens=80,
            temperature=0.0,
        ),
    ]


def run_probe(provider: Any, probe: Probe) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": probe.system},
            {"role": "user", "content": probe.user},
        ],
        "max_tokens": probe.max_tokens,
        "temperature": probe.temperature,
        "stream": False,
    }
    if probe.response_format:
        payload["response_format"] = probe.response_format

    started = time.monotonic()
    result: dict[str, Any] = {
        "name": probe.name,
        "request": payload,
        "status": "fail",
    }
    try:
        response = provider._request_json("chat/completions", method="POST", payload=payload)
        duration = time.monotonic() - started
        content = message_content(response)
        parsed = extract_json_object(content)
        classification = classify_seed(parsed) if probe.name != "plain_chat_prompt" else None
        result.update(
            {
                "status": "pass",
                "duration_seconds": round(duration, 3),
                "content": content,
                "parsed_json": parsed,
                "seed_classification": classification,
                "raw_response": response,
            }
        )
        print(
            f"[parti-base] {probe.name} ok duration={duration:.1f}s "
            f"content={content[:180]!r}",
            flush=True,
        )
        if classification:
            print(f"[parti-base] {probe.name} seed={classification}", flush=True)
        return result
    except Exception as exc:
        duration = time.monotonic() - started
        result.update(
            {
                "status": "fail",
                "duration_seconds": round(duration, 3),
                "error_type": exc.__class__.__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(limit=10),
            }
        )
        print(f"[parti-base] {probe.name} fail duration={duration:.1f}s error={exc}", flush=True)
        return result


def main() -> int:
    load_env_file(repo_path(ENV_FILE))
    configure_runpod_env()

    from blueprint_core.llm_providers import OpenAICompatibleProvider

    run_id = utc_run_id()
    output_dir = repo_path(OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    provider = OpenAICompatibleProvider(provider_name="runpod", model_name=MODEL)
    validation = provider.validate_configured_model(raise_on_strict=False)
    print(f"[parti-base] provider=runpod model={MODEL}", flush=True)
    print(f"[parti-base] configured={provider.is_configured} base_url={provider.base_url}", flush=True)
    if validation.validation_error:
        print(f"[parti-base] validation_error={validation.validation_error}", flush=True)

    results = [run_probe(provider, probe) for probe in build_probes()]
    summary = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "provider": "runpod",
        "model": MODEL,
        "base_url": provider.base_url,
        "validation": validation.as_debug_dict(),
        "summary": {
            "total": len(results),
            "request_passed": sum(1 for item in results if item.get("status") == "pass"),
            "request_failed": sum(1 for item in results if item.get("status") != "pass"),
            "usable_seed_count": sum(
                1
                for item in results
                if (item.get("seed_classification") or {}).get("status") == "pass"
            ),
        },
        "results": results,
    }

    safe_summary = scrub(summary)
    report_path = output_dir / f"{run_id}-caid-technologies-parti-base-behavior.json"
    latest_path = output_dir / "latest-caid-technologies-parti-base-behavior.json"
    report_path.write_text(json.dumps(safe_summary, indent=2) + "\n", encoding="utf-8")
    latest_path.write_text(json.dumps(safe_summary, indent=2) + "\n", encoding="utf-8")
    print(f"[parti-base] report={report_path}", flush=True)
    print(f"[parti-base] latest={latest_path}", flush=True)
    return 0 if any((item.get("seed_classification") or {}).get("status") == "pass" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
