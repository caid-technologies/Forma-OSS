#!/usr/bin/env python3
"""Hardcoded async prompt test for Baseten GLM-5.2 and OpenAI."""

from __future__ import annotations

import asyncio
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Protocol


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from blueprint_core.openai_streams import DEFAULT_OPENAI_BASE_URL, OpenAIStreamConfig, first_env, merged_env
from blueprint_core.providers import ProviderEvent, ProviderRegistry, ProviderRequest, model_name_for_provider, normalize_provider_name


ENV_FILE = ROOT_DIR / ".env"
OUTPUT_DIR = ROOT_DIR / "examples" / "results"
OPENAI_MODEL = "gpt-5.5"
BASETEN_GLM_MODEL = "zai-org/GLM-5.2"
TIMEOUT_SECONDS = 300.0
MAX_OUTPUT_TOKENS = 1200

EXAMPLE_PROMPT = """Blue Sentinel is a USB-C powered desktop environmental monitor with an ESP32-S3, I2C environmental sensors, an OLED display, and a small airflow module.

Review the project for continuity risks across electrical, mechanical, firmware, and documentation work.
Return a concise answer with exactly three sections: Summary, Risks, Fixes."""

INSTRUCTIONS = (
    "You are a senior electromechanical design reviewer. "
    "Be concrete, preserve the product facts, and do not invent a different product."
)


class ProviderTextRuntime(Protocol):
    def prepare(self, request: ProviderRequest) -> object:
        ...

    def stream_text(self, prepared: object) -> Iterable[ProviderEvent]:
        ...


@dataclass(frozen=True)
class ModelCandidate:
    provider: str
    model: str

    @property
    def llm_id(self) -> str:
        return f"{self.provider}/{self.model}"

    @classmethod
    def create(cls, provider: str, model: str) -> "ModelCandidate":
        resolved_provider = normalize_provider_name(provider)
        return cls(
            provider=resolved_provider,
            model=model_name_for_provider(resolved_provider, model),
        )


@dataclass(frozen=True)
class ModelRunResult:
    candidate_index: int
    provider: str
    model: str
    status: str
    text: str
    event_count: int
    duration_seconds: float
    error_message: str = ""

    @property
    def llm_id(self) -> str:
        return f"{self.provider}/{self.model}"

    @property
    def passed(self) -> bool:
        return self.status == "pass"

    def to_json_obj(self) -> dict[str, object]:
        return {
            "candidate_index": self.candidate_index,
            "provider": self.provider,
            "model": self.model,
            "llm": self.llm_id,
            "status": self.status,
            "passed": self.passed,
            "text": self.text,
            "event_count": self.event_count,
            "duration_seconds": self.duration_seconds,
            "error_message": self.error_message,
        }


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_utc(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def compact_error(error: BaseException, max_chars: int = 1200) -> str:
    message = str(error).strip() or error.__class__.__name__
    if len(message) <= max_chars:
        return message
    return message[:max_chars] + "...<truncated>"


def default_candidates() -> tuple[ModelCandidate, ...]:
    return (
        ModelCandidate.create("baseten", BASETEN_GLM_MODEL),
        ModelCandidate.create("openai", OPENAI_MODEL),
    )


def build_provider_registry(env_file: Path = ENV_FILE) -> ProviderRegistry:
    env = merged_env(env_file)
    openai_config = OpenAIStreamConfig(
        api_key=first_env(env, "OPENAI_API_KEY", "LLM_API_KEY") or "",
        model=OPENAI_MODEL,
        base_url=first_env(env, "OPENAI_BASE_URL") or DEFAULT_OPENAI_BASE_URL,
        prompt=EXAMPLE_PROMPT,
        timeout_seconds=TIMEOUT_SECONDS,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        project_id=first_env(env, "OPENAI_PROJECT_ID"),
        organization_id=first_env(env, "OPENAI_ORG_ID", "OPENAI_ORGANIZATION"),
        instructions=INSTRUCTIONS,
    )
    return ProviderRegistry.default(env_file=env_file, openai_config=openai_config)


def run_model_sync(
    *,
    candidate_index: int,
    candidate: ModelCandidate,
    registry: ProviderTextRuntime,
    prompt: str,
    instructions: str,
) -> ModelRunResult:
    started_at = time.monotonic()
    try:
        request = ProviderRequest(
            provider=candidate.provider,
            model=candidate.model,
            prompt=prompt,
            instructions=instructions,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            timeout_seconds=TIMEOUT_SECONDS,
        )
        prepared = registry.prepare(request)
        events = tuple(registry.stream_text(prepared))
        text = "".join(event.content for event in events).strip()
        error_message = next((event.error_message for event in events if event.error_message), "") or ""
        if error_message:
            status = "fail"
        elif not text:
            status = "fail"
            error_message = "Provider returned no text."
        else:
            status = "pass"
        return ModelRunResult(
            candidate_index=candidate_index,
            provider=candidate.provider,
            model=candidate.model,
            status=status,
            text=text,
            event_count=len(events),
            duration_seconds=round(time.monotonic() - started_at, 3),
            error_message=error_message,
        )
    except Exception as exc:
        return ModelRunResult(
            candidate_index=candidate_index,
            provider=candidate.provider,
            model=candidate.model,
            status="fail",
            text="",
            event_count=0,
            duration_seconds=round(time.monotonic() - started_at, 3),
            error_message=compact_error(exc),
        )


async def run_models_async(
    *,
    candidates: tuple[ModelCandidate, ...],
    registry: ProviderTextRuntime,
    prompt: str = EXAMPLE_PROMPT,
    instructions: str = INSTRUCTIONS,
    emit_output: bool = True,
) -> tuple[ModelRunResult, ...]:
    async def run_one(index: int, candidate: ModelCandidate) -> ModelRunResult:
        return await asyncio.to_thread(
            run_model_sync,
            candidate_index=index,
            candidate=candidate,
            registry=registry,
            prompt=prompt,
            instructions=instructions,
        )

    tasks = [asyncio.create_task(run_one(index, candidate)) for index, candidate in enumerate(candidates)]
    results: list[ModelRunResult] = []
    for task in asyncio.as_completed(tasks):
        result = await task
        if emit_output:
            print_result(result)
        results.append(result)
    return tuple(sorted(results, key=lambda item: item.candidate_index))


def build_report(
    *,
    started_at: datetime,
    completed_at: datetime,
    prompt: str,
    results: tuple[ModelRunResult, ...],
) -> dict[str, object]:
    passed = sum(1 for result in results if result.passed)
    failed = len(results) - passed
    return {
        "schema_version": 1,
        "tool": "examples/async_glm_openai_prompt.py",
        "started_at": format_utc(started_at),
        "completed_at": format_utc(completed_at),
        "duration_seconds": round((completed_at - started_at).total_seconds(), 3),
        "prompt": prompt,
        "models": [result.llm_id for result in results],
        "summary": {
            "ok": failed == 0,
            "passed": passed,
            "failed": failed,
            "total": len(results),
        },
        "results": [result.to_json_obj() for result in results],
    }


def save_report(report: dict[str, object], output_dir: Path = OUTPUT_DIR) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    completed_at = str(report["completed_at"])
    run_id = completed_at.replace("-", "").replace(":", "").replace("Z", "Z")
    summary = report["summary"]
    if not isinstance(summary, dict):
        raise TypeError("report summary must be a JSON object")
    status = "pass" if summary.get("ok") else "fail"
    report_path = output_dir / f"{run_id}-async-glm-openai-prompt-{status}.json"
    latest_path = output_dir / "latest-async-glm-openai-prompt.json"
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    report_path.write_text(payload, encoding="utf-8")
    latest_path.write_text(payload, encoding="utf-8")
    return report_path, latest_path


def print_model_stdout(result: ModelRunResult) -> None:
    label = f"[async-glm-openai:stdout model={result.llm_id}]"
    for line in result.text.strip().splitlines():
        print(f"{label} {line}", flush=True)


def print_result(result: ModelRunResult) -> None:
    status = "PASS" if result.passed else "FAIL"
    print(
        f"[async-glm-openai] {status} {result.llm_id} "
        f"duration={result.duration_seconds:.1f}s events={result.event_count}",
        flush=True,
    )
    if result.text:
        print_model_stdout(result)
    if result.error_message:
        print(f"[async-glm-openai] error model={result.llm_id} {result.error_message}", file=sys.stderr, flush=True)


async def main() -> int:
    started_at = utc_now()
    candidates = default_candidates()
    registry = build_provider_registry(ENV_FILE)
    print("[async-glm-openai] prompt:", flush=True)
    print(EXAMPLE_PROMPT, flush=True)
    print(f"[async-glm-openai] running {len(candidates)} model(s) concurrently", flush=True)
    for candidate in candidates:
        print(f"[async-glm-openai] candidate={candidate.llm_id}", flush=True)

    results = await run_models_async(candidates=candidates, registry=registry)
    completed_at = utc_now()
    report = build_report(started_at=started_at, completed_at=completed_at, prompt=EXAMPLE_PROMPT, results=results)
    report_path, latest_path = save_report(report)
    summary = report["summary"]
    print(
        "[async-glm-openai] "
        f"summary passed={summary['passed']} failed={summary['failed']} total={summary['total']}",
        flush=True,
    )
    print(f"[async-glm-openai] report={report_path}", flush=True)
    print(f"[async-glm-openai] latest={latest_path}", flush=True)
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
