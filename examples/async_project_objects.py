#!/usr/bin/env python3
"""Create Forma project objects with Ollama, Runpod, Baseten, GMI, and Hugging Face, concurrently."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


ROOT_DIR = Path(__file__).resolve().parents[1]
SYNC_SCRIPT = Path(__file__).resolve().with_name("sync_project_objects.py")
DEFAULT_PROMPT = (
    "Design a compact blue desktop environmental monitor with an OLED display, "
    "temperature and humidity sensing, USB-C power, and optional battery operation."
)
DEFAULT_OUTPUT_DIR = "examples/results"
DEFAULT_ENV_FILE = ".env"
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434/v1"
DEFAULT_OLLAMA_MODEL = "qwen3:0.6b"
DEFAULT_RUNPOD_MODEL = "caid-technologies/parti-base"
DEFAULT_BASETEN_BASE_URL = "https://inference.baseten.co/v1"
DEFAULT_BASETEN_GLM_MODEL = "zai-org/GLM-5.2"
DEFAULT_GMI_BASE_URL = "https://api.gmi-serving.com/v1"
DEFAULT_GMI_FABLE_MODEL = "anthropic/claude-fable-5"
DEFAULT_HUGGINGFACE_BASE_URL = "https://router.huggingface.co/v1"
DEFAULT_HUGGINGFACE_QWEN_MODEL = "Qwen/Qwen2.5-Coder-3B-Instruct:nscale"


@dataclass(frozen=True)
class ProviderProcess:
    label: str
    command: tuple[str, ...]
    summary_path: Path


@dataclass
class ProviderProcessResult:
    label: str
    returncode: int
    summary_path: Path
    summary: Optional[dict[str, Any]]

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def to_json_object(self) -> dict[str, Any]:
        return {
            "provider": self.label,
            "returncode": self.returncode,
            "ok": self.ok,
            "summary_path": str(self.summary_path),
            "summary": self.summary,
        }


def utc_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def repo_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return ROOT_DIR / path


async def print_stream(label: str, stream: asyncio.StreamReader, stream_name: str) -> None:
    while True:
        line = await stream.readline()
        if not line:
            return
        text = line.decode("utf-8", errors="replace").rstrip()
        print(f"[async-project-objects:{label}:{stream_name}] {text}", flush=True)


async def run_provider_process(process: ProviderProcess) -> ProviderProcessResult:
    print(f"[async-project-objects] starting {process.label}", flush=True)
    child = await asyncio.create_subprocess_exec(
        *process.command,
        cwd=str(ROOT_DIR),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert child.stdout is not None
    assert child.stderr is not None
    await asyncio.gather(
        print_stream(process.label, child.stdout, "out"),
        print_stream(process.label, child.stderr, "err"),
    )
    returncode = await child.wait()

    summary = None
    if process.summary_path.exists():
        try:
            summary = json.loads(process.summary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            summary = {"error": f"Could not parse summary JSON: {process.summary_path}"}

    print(f"[async-project-objects] done {process.label} returncode={returncode}", flush=True)
    return ProviderProcessResult(
        label=process.label,
        returncode=returncode,
        summary_path=process.summary_path,
        summary=summary,
    )


def build_processes(args: argparse.Namespace, *, run_id: str, output_dir: Path) -> list[ProviderProcess]:
    requested = set(args.only or ("ollama", "runpod", "baseten"))
    processes: list[ProviderProcess] = []

    def base_command(label: str) -> list[str]:
        provider_run_id = f"{run_id}-{label}"
        command = [
            sys.executable,
            str(SYNC_SCRIPT),
            args.prompt,
            "--env-file",
            args.env_file,
            "--output-dir",
            str(output_dir),
            "--timeout-seconds",
            str(args.timeout_seconds),
            "--run-id",
            provider_run_id,
            "--only",
            label,
            "--ollama-model",
            args.ollama_model,
            "--ollama-base-url",
            args.ollama_base_url,
            "--runpod-model",
            args.runpod_model,
            "--baseten-model",
            args.baseten_model,
            "--baseten-base-url",
            args.baseten_base_url,
            "--gmi-model",
            args.gmi_model,
            "--gmi-base-url",
            args.gmi_base_url,
            "--huggingface-model",
            args.huggingface_model,
            "--huggingface-base-url",
            args.huggingface_base_url,
        ]
        if args.generate_image:
            command.append("--generate-image")
        return command

    if "ollama" in requested:
        command = base_command("ollama")
        if args.runpod_base_url:
            command.extend(["--runpod-base-url", args.runpod_base_url])
        processes.append(
            ProviderProcess(
                label="ollama",
                command=tuple(command),
                summary_path=output_dir / f"{run_id}-ollama-summary.json",
            )
        )

    if "runpod" in requested:
        command = base_command("runpod")
        if args.runpod_base_url:
            command.extend(["--runpod-base-url", args.runpod_base_url])
        processes.append(
            ProviderProcess(
                label="runpod",
                command=tuple(command),
                summary_path=output_dir / f"{run_id}-runpod-summary.json",
            )
        )

    if "baseten" in requested:
        command = base_command("baseten")
        processes.append(
            ProviderProcess(
                label="baseten",
                command=tuple(command),
                summary_path=output_dir / f"{run_id}-baseten-summary.json",
            )
        )

    if "gmi" in requested:
        command = base_command("gmi")
        processes.append(
            ProviderProcess(
                label="gmi",
                command=tuple(command),
                summary_path=output_dir / f"{run_id}-gmi-summary.json",
            )
        )

    if "huggingface" in requested:
        command = base_command("huggingface")
        processes.append(
            ProviderProcess(
                label="huggingface",
                command=tuple(command),
                summary_path=output_dir / f"{run_id}-huggingface-summary.json",
            )
        )

    return processes


def save_combined_summary(results: list[ProviderProcessResult], *, output_dir: Path, run_id: str) -> Path:
    summary_path = output_dir / f"{run_id}-async-summary.json"
    latest_path = output_dir / "latest-async-project-objects-summary.json"
    payload = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "summary": {
            "total": len(results),
            "passed": sum(1 for result in results if result.ok),
            "failed": sum(1 for result in results if not result.ok),
            "ok": all(result.ok for result in results),
        },
        "results": [result.to_json_object() for result in results],
    }
    summary_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    latest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"[async-project-objects] summary={summary_path}", flush=True)
    print(f"[async-project-objects] latest={latest_path}", flush=True)
    return summary_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create Forma project objects with Ollama, Runpod, Baseten, GMI, and Hugging Face concurrently.")
    parser.add_argument("prompt", nargs="?", default=DEFAULT_PROMPT, help="Project prompt to generate.")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE, help=f"Dotenv file to load. Defaults to {DEFAULT_ENV_FILE}.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help=f"Directory for JSON output. Defaults to {DEFAULT_OUTPUT_DIR}.")
    parser.add_argument("--run-id", default=None, help="Stable run id for output filenames.")
    parser.add_argument("--only", action="append", choices=("ollama", "runpod", "baseten", "gmi", "huggingface"), help="Run only one provider. Can be repeated.")
    parser.add_argument("--ollama-model", default=os.getenv("OLLAMA_BLUEPRINT_MODEL", DEFAULT_OLLAMA_MODEL))
    parser.add_argument("--ollama-base-url", default=os.getenv("OLLAMA_OPENAI_BASE_URL", DEFAULT_OLLAMA_BASE_URL))
    parser.add_argument("--runpod-model", default=os.getenv("RUNPOD_BLUEPRINT_MODEL", DEFAULT_RUNPOD_MODEL))
    parser.add_argument("--runpod-base-url", default=os.getenv("RUNPOD_OPENAI_BASE_URL"), help="Optional Runpod OpenAI-compatible base URL override.")
    parser.add_argument("--baseten-model", default=os.getenv("BASETEN_BLUEPRINT_MODEL", DEFAULT_BASETEN_GLM_MODEL))
    parser.add_argument("--baseten-base-url", default=os.getenv("BASETEN_BASE_URL", DEFAULT_BASETEN_BASE_URL))
    parser.add_argument("--gmi-model", default=os.getenv("GMI_BLUEPRINT_MODEL", os.getenv("GMI_MODEL", DEFAULT_GMI_FABLE_MODEL)))
    parser.add_argument("--gmi-base-url", default=os.getenv("GMI_BASE_URL", DEFAULT_GMI_BASE_URL))
    parser.add_argument("--huggingface-model", default=os.getenv("HUGGINGFACE_BLUEPRINT_MODEL", DEFAULT_HUGGINGFACE_QWEN_MODEL))
    parser.add_argument("--huggingface-base-url", default=os.getenv("HUGGINGFACE_BASE_URL", DEFAULT_HUGGINGFACE_BASE_URL))
    parser.add_argument("--timeout-seconds", type=float, default=1200.0, help="Provider timeout for slow jobs.")
    parser.add_argument("--generate-image", action="store_true", help="Request product image generation for each project object.")
    return parser


async def async_main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    run_id = args.run_id or utc_run_id()
    output_dir = repo_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    processes = build_processes(args, run_id=run_id, output_dir=output_dir)
    if not processes:
        print("[async-project-objects] no providers selected", file=sys.stderr)
        return 2

    results = await asyncio.gather(*(run_provider_process(process) for process in processes))
    save_combined_summary(results, output_dir=output_dir, run_id=run_id)
    return 0 if all(result.ok for result in results) else 1


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
