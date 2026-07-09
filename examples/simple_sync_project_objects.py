#!/usr/bin/env python3
"""Hardcoded sync example: create Ollama, Runpod, Baseten GLM, GMI Fable, and Hugging Face project objects."""

from __future__ import annotations

import os

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

HUGGINGFACE_QWEN_MODEL = "Qwen/Qwen2.5-72B-Instruct:deepinfra"
HUGGINGFACE_BASE_URL = "https://router.huggingface.co/v1"

GENERATE_IMAGE = True
PRINT_FULL_OBJECT_JSON = False


def main() -> int:
    run_id = utc_run_id()
    output_dir = repo_path(OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    load_env_file(repo_path(ENV_FILE))
    base_environment = dict(os.environ)

    jobs = [
        # ollama_job(OLLAMA_MODEL, OLLAMA_BASE_URL, TIMEOUT_SECONDS, generate_image=GENERATE_IMAGE),
        # baseten_job(BASETEN_GLM_MODEL, TIMEOUT_SECONDS, BASETEN_BASE_URL, generate_image=GENERATE_IMAGE),
        # gmi_job(GMI_FABLE_MODEL, TIMEOUT_SECONDS, GMI_BASE_URL, generate_image=GENERATE_IMAGE),
        huggingface_job(HUGGINGFACE_QWEN_MODEL, TIMEOUT_SECONDS, HUGGINGFACE_BASE_URL, generate_image=GENERATE_IMAGE),
        # runpod_job(RUNPOD_MODEL, TIMEOUT_SECONDS, RUNPOD_BASE_URL, generate_image=GENERATE_IMAGE),
    ]

    results = [
        run_project_object_job(
            job,
            prompt=PROMPT,
            output_dir=output_dir,
            run_id=run_id,
            base_environment=base_environment,
            print_object_json=PRINT_FULL_OBJECT_JSON,
            generate_image=GENERATE_IMAGE,
        )
        for job in jobs
    ]

    save_summary(results, output_dir=output_dir, run_id=run_id)
    return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
