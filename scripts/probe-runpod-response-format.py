#!/usr/bin/env python3
"""Probe which structured-output mode the deployed RunPod vLLM worker honors.

Sends one WebProjectPlan request per mode (json_schema, guided_json,
json_object) to the configured runpod OpenAI-compatible endpoint and reports,
for each: HTTP acceptance, and whether the returned JSON actually nests the
required overview/requirements keys. Ends with the recommended
RUNPOD_RESPONSE_FORMAT setting.

Requires RUNPOD_API_KEY and RUNPOD_OPENAI_BASE_URL (or the equivalent endpoint
config). Costs three short live generations.

    python scripts/probe-runpod-response-format.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from blueprint_core.agents.web_research_workflow import WebProjectPlan
from blueprint_core.llm_providers import OpenAICompatibleProvider, _schema_name

PROMPT = (
    "Turn this user request into a buildable low-voltage maker electronics "
    "architecture: a desk clock with an OLED display and a buzzer alarm. "
    "Return WebProjectPlan."
)


def probe(provider, mode: str) -> dict:
    schema = WebProjectPlan.model_json_schema()
    payload = {
        "model": provider.model_name,
        "messages": [
            {"role": "system", "content": "You produce concise, valid JSON only."},
            {"role": "user", "content": f"{PROMPT}\n\nThe JSON must conform to this schema:\n{json.dumps(schema)}"},
        ],
        "max_tokens": 1024,
        "temperature": 0.2,
    }
    if mode == "json_schema":
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": _schema_name(WebProjectPlan), "schema": schema, "strict": False},
        }
    elif mode == "guided_json":
        payload["response_format"] = {"type": "json_object"}
        payload["guided_json"] = schema
    else:
        payload["response_format"] = {"type": "json_object"}

    outcome = {"mode": mode, "accepted": False, "nested": False, "detail": ""}
    try:
        response = provider._request_json("chat/completions", method="POST", payload=payload)
    except Exception as exc:
        outcome["detail"] = f"{type(exc).__name__}: {str(exc)[:300]}"
        return outcome

    outcome["accepted"] = True
    try:
        content = response["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        outcome["nested"] = isinstance(parsed.get("overview"), dict) and isinstance(parsed.get("requirements"), dict)
        outcome["detail"] = f"top-level keys: {sorted(parsed)[:8]}"
    except Exception as exc:
        outcome["detail"] = f"response not parseable: {type(exc).__name__}: {str(exc)[:200]}"
    return outcome


def main() -> int:
    # Direct construction: this is a diagnostic, the LLM_ALLOWED_PROVIDERS
    # runtime allowlist does not apply to it.
    provider = OpenAICompatibleProvider(provider_name="runpod")
    if not provider.is_configured:
        print("runpod provider is not configured (set RUNPOD_API_KEY and RUNPOD_OPENAI_BASE_URL).", file=sys.stderr)
        return 2

    print(f"Probing {provider.base_url} model={provider.model_name}\n")
    results = [probe(provider, mode) for mode in ("json_schema", "guided_json", "json_object")]
    for r in results:
        status = "accepted" if r["accepted"] else "REJECTED"
        shape = "nested correctly" if r["nested"] else "NOT nested"
        print(f"  {r['mode']:<12} {status:<9} {shape:<17} {r['detail']}")

    by_mode = {r["mode"]: r for r in results}
    if by_mode["json_schema"]["accepted"] and by_mode["json_schema"]["nested"]:
        print("\nRecommendation: keep the default (json_schema). Guided decoding is honored.")
    elif by_mode["guided_json"]["accepted"] and by_mode["guided_json"]["nested"]:
        print("\nRecommendation: set RUNPOD_RESPONSE_FORMAT=guided_json (worker predates json_schema support).")
    else:
        print(
            "\nRecommendation: set RUNPOD_RESPONSE_FORMAT=json_object. Neither guided mode is honored; "
            "the deterministic flat-field re-nesting layer is the operative fix. Consider upgrading the "
            "worker-vllm image to a vLLM >= 0.6 build."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
