#!/usr/bin/env python3
"""Hardcoded async example: create Ollama, Runpod, Baseten GLM, GMI Fable, and Hugging Face project objects concurrently."""

from __future__ import annotations

import asyncio
import json
import os
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from typing import Any

from sync_project_objects import (
    baseten_job,
    gmi_job,
    huggingface_job,
    load_env_file,
    ollama_job,
    repo_path,
    run_project_object_job,
    runpod_job,
    save_summary,
    scrub,
    utc_run_id,
)


PROMPT = (
    "Design a compact blue desktop environmental monitor with an OLED display, "
    "temperature and humidity sensing, USB-C power, and optional battery operation."
)
ENV_FILE = ".env"
OUTPUT_DIR = "examples/results"
TIMEOUT_SECONDS = 1200.0

OLLAMA_MODEL = "qwen3:0.6b"
OLLAMA_BASE_URL = "http://127.0.0.1:11434/v1"

RUNPOD_MODEL = "caid-technologies/parti-base"
RUNPOD_BASE_URL = None

BASETEN_GLM_MODEL = "zai-org/GLM-5.2"
BASETEN_BASE_URL = "https://inference.baseten.co/v1"

GMI_FABLE_MODEL = "anthropic/claude-fable-5"
GMI_BASE_URL = "https://api.gmi-serving.com/v1"

HUGGINGFACE_QWEN_MODEL = "Qwen/Qwen2.5-Coder-3B-Instruct:nscale"
HUGGINGFACE_BASE_URL = "https://router.huggingface.co/v1"

# Add "gmi" after setting GMI_API_KEY or GMI_CLOUD_API_KEY.
# Add "huggingface" after setting HF_TOKEN, HUGGINGFACE_API_KEY, or HUGGINGFACE_HUB_TOKEN.
PROVIDERS = ("ollama", "runpod", "baseten")
GENERATE_IMAGE = True
PRINT_FULL_OBJECT_JSON = False


def run_provider(provider_label: str, run_id: str) -> dict[str, Any]:
    output_dir = repo_path(OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    load_env_file(repo_path(ENV_FILE))
    base_environment = dict(os.environ)

    if provider_label == "ollama":
        job = ollama_job(OLLAMA_MODEL, OLLAMA_BASE_URL, TIMEOUT_SECONDS, generate_image=GENERATE_IMAGE)
    elif provider_label == "runpod":
        job = runpod_job(RUNPOD_MODEL, TIMEOUT_SECONDS, RUNPOD_BASE_URL, generate_image=GENERATE_IMAGE)
    elif provider_label == "baseten":
        job = baseten_job(BASETEN_GLM_MODEL, TIMEOUT_SECONDS, BASETEN_BASE_URL, generate_image=GENERATE_IMAGE)
    elif provider_label == "gmi":
        job = gmi_job(GMI_FABLE_MODEL, TIMEOUT_SECONDS, GMI_BASE_URL, generate_image=GENERATE_IMAGE)
    elif provider_label == "huggingface":
        job = huggingface_job(HUGGINGFACE_QWEN_MODEL, TIMEOUT_SECONDS, HUGGINGFACE_BASE_URL, generate_image=GENERATE_IMAGE)
    else:
        raise ValueError(f"Unknown provider label: {provider_label}")

    provider_run_id = f"{run_id}-{provider_label}"
    result = run_project_object_job(
        job,
        prompt=PROMPT,
        output_dir=output_dir,
        run_id=provider_run_id,
        base_environment=base_environment,
        print_object_json=PRINT_FULL_OBJECT_JSON,
        generate_image=GENERATE_IMAGE,
    )
    save_summary([result], output_dir=output_dir, run_id=provider_run_id)
    return result.to_json_object()


def save_async_summary(results: list[dict[str, Any]], run_id: str) -> None:
    output_dir = repo_path(OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / f"{run_id}-simple-async-summary.json"
    latest_path = output_dir / "latest-simple-async-project-objects-summary.json"
    payload = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "summary": {
            "total": len(results),
            "passed": sum(1 for result in results if result.get("status") == "pass"),
            "failed": sum(1 for result in results if result.get("status") != "pass"),
            "ok": all(result.get("status") == "pass" for result in results),
        },
        "results": results,
    }
    safe_payload = scrub(payload)
    summary_path.write_text(json.dumps(safe_payload, indent=2) + "\n", encoding="utf-8")
    latest_path.write_text(json.dumps(safe_payload, indent=2) + "\n", encoding="utf-8")
    print(f"[simple-async-project-objects] summary={summary_path}", flush=True)
    print(f"[simple-async-project-objects] latest={latest_path}", flush=True)


async def main() -> int:
    run_id = utc_run_id()
    loop = asyncio.get_running_loop()

    with ProcessPoolExecutor(max_workers=len(PROVIDERS)) as executor:
        tasks = [
            loop.run_in_executor(executor, run_provider, provider_label, run_id)
            for provider_label in PROVIDERS
        ]
        results = await asyncio.gather(*tasks)

    save_async_summary(results, run_id)
    return 0 if all(result.get("status") == "pass" for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
