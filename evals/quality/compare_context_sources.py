#!/usr/bin/env python3
"""Compare Web Research and Past Jobs generation with an OpenAI quality judge."""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

DEFAULT_PROMPT = (
    "Design a buildable ESP32 indoor air-quality monitor with CO2, particulate, temperature, "
    "and humidity sensing, an OLED status display, an audible warning, USB power, and a printable desk enclosure."
)
DEFAULT_OUTPUT_DIR = ".logs/context-source-eval"


class QualityScores(BaseModel):
    prompt_adherence: int = Field(ge=1, le=10)
    electrical_correctness: int = Field(ge=1, le=10)
    component_realism: int = Field(ge=1, le=10)
    completeness: int = Field(ge=1, le=10)
    manufacturability: int = Field(ge=1, le=10)
    safety: int = Field(ge=1, le=10)
    documentation: int = Field(ge=1, le=10)
    visual_quality: int = Field(ge=1, le=10)


class RunQualityReview(BaseModel):
    scores: QualityScores
    overall_score: float = Field(ge=1, le=10)
    buildability_verdict: Literal["buildable", "buildable_with_changes", "not_buildable"]
    image_verdict: Literal["useful", "partially_useful", "not_useful", "missing"]
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    critical_issues: list[str] = Field(default_factory=list)
    summary: str


class PairwiseReview(BaseModel):
    winner: Literal["web_research", "past_jobs", "tie"]
    confidence: float = Field(ge=0, le=1)
    quality_difference: float = Field(description="Estimated absolute difference on a 10-point quality scale.", ge=0, le=10)
    rationale: str
    web_research_advantages: list[str] = Field(default_factory=list)
    past_jobs_advantages: list[str] = Field(default_factory=list)
    recommendation: str


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_utc(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def parse_timestamp(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def job_duration_seconds(job: dict[str, Any]) -> Optional[float]:
    started = parse_timestamp(job.get("started_at"))
    completed = parse_timestamp(job.get("completed_at"))
    if not started or not completed or completed < started:
        return None
    return round((completed - started).total_seconds(), 6)


def safe_output(value: Any) -> Any:
    """Remove inline binary payloads while preserving output structure and image metadata."""
    if isinstance(value, list):
        return [safe_output(item) for item in value]
    if not isinstance(value, dict):
        return value
    result: dict[str, Any] = {}
    for key, item in value.items():
        key_text = str(key)
        if key_text == "data" or key_text.endswith("_data"):
            if isinstance(item, str) and (item.startswith("data:") or len(item) > 10_000):
                result[key_text] = f"<inline-data:{len(item)} chars>"
                continue
        result[key_text] = safe_output(item)
    return result


def first_image(response: dict[str, Any]) -> tuple[Optional[bytes], Optional[str]]:
    metadata = ((response.get("project_ir") or {}).get("assembly_metadata") or {})
    candidates = [metadata.get("product_image_data")]
    for record in metadata.get("product_visual_sequence") or []:
        if isinstance(record, dict):
            candidates.append(record.get("data"))
    for candidate in candidates:
        if not isinstance(candidate, str) or not candidate.startswith("data:") or "," not in candidate:
            continue
        header, encoded = candidate.split(",", 1)
        mime_type = header.removeprefix("data:").split(";", 1)[0] or "image/png"
        try:
            return base64.b64decode(encoded), mime_type
        except ValueError:
            continue
    return None, None


def deterministic_metrics(response: dict[str, Any]) -> dict[str, Any]:
    ir = response.get("project_ir") or {}
    metadata = ir.get("assembly_metadata") or {}
    validation = ir.get("validation") or {}
    return {
        "is_valid": ir.get("is_valid"),
        "component_count": len(ir.get("components") or []),
        "net_count": len(ir.get("nets") or []),
        "assembly_step_count": len(ir.get("assembly") or []),
        "constraint_count": len(ir.get("constraints") or []),
        "critical_issue_count": len(validation.get("critical") or []),
        "warning_issue_count": len(validation.get("warning") or []),
        "image_status": metadata.get("image_output_status"),
        "image_provider": metadata.get("product_image_provider") or metadata.get("image_output_provider"),
        "image_model": metadata.get("product_image_model") or metadata.get("image_output_model"),
        "generated_image_count": metadata.get("image_output_generated_count"),
        "source_usage": metadata.get("source_usage"),
        "past_jobs_context": metadata.get("past_jobs_context"),
        "external_research": metadata.get("external_research"),
    }


async def run_generation(
    *,
    label: str,
    prompt: str,
    owner_user_id: str,
    past_jobs_limit: int,
) -> dict[str, Any]:
    from apps.api.a2a import build_generation_response
    from blueprint_core.agents.pipeline import observe_agent_pipeline
    from blueprint_core.database import get_generated_project
    from blueprint_core.jobs.context import PastJobContextSource
    from blueprint_core.jobs.store import JOB_STORE

    is_web = label == "web_research"
    job_id = f"job_context_eval_{label}_{uuid4().hex}"
    payload = {
        "prompt": prompt,
        "workflow": "web_research" if is_web else "default",
        "provider": "openai",
        "model": "gpt-5.5",
        "generate_image": True,
        "owner_user_id": owner_user_id,
        "external_source_provider": "firecrawl" if is_web else None,
        "data_sources": [] if is_web else ["past_jobs"],
        "past_jobs_limit": past_jobs_limit,
        "client_job_id": job_id,
    }
    JOB_STORE.create_job(
        job_id=job_id,
        message_id=f"msg_{uuid4().hex}",
        correlation_id=f"context-source-eval-{label}",
        action="blueprint.generate_project",
        sender="quality-eval",
        recipient="blueprint",
        payload=payload,
        server_owned=True,
        status="queued",
    )
    JOB_STORE.mark_running(job_id)
    wall_started = utc_now()
    wall_clock = time.perf_counter()
    retrieval_seconds = 0.0
    generation_started = time.perf_counter()
    past_job_context = None
    try:
        if not is_web:
            retrieval_started = time.perf_counter()
            past_job_context = await PastJobContextSource(JOB_STORE, get_generated_project).retrieve(
                prompt,
                owner_user_id=owner_user_id,
                limit=past_jobs_limit,
                exclude_job_id=job_id,
            )
            retrieval_seconds = time.perf_counter() - retrieval_started
        generation_started = time.perf_counter()
        with observe_agent_pipeline(
            lambda event: JOB_STORE.append_progress_event(job_id, event.as_dict()),
            cancellation_check=lambda: JOB_STORE.is_cancelled(job_id),
        ):
            response = await asyncio.to_thread(
                build_generation_response,
                prompt,
                None,
                generate_image=True,
                workflow="web_research" if is_web else "default",
                provider="openai",
                model="gpt-5.5",
                external_source_provider="firecrawl" if is_web else None,
                frontend_job_id=job_id,
                owner_user_id=owner_user_id,
                data_sources=[] if is_web else ["past_jobs"],
                past_job_context=past_job_context,
            )
        generation_seconds = time.perf_counter() - generation_started
        JOB_STORE.mark_succeeded(job_id, response)
        status = "succeeded"
        error = None
    except Exception as exc:
        generation_seconds = time.perf_counter() - generation_started
        JOB_STORE.mark_failed(job_id, str(exc))
        response = {}
        status = "failed"
        error = f"{exc.__class__.__name__}: {exc}"

    wall_completed = utc_now()
    wall_seconds = time.perf_counter() - wall_clock
    job = JOB_STORE.get_job(job_id) or {}
    return {
        "label": label,
        "status": status,
        "error": error,
        "job_id": job_id,
        "prompt": prompt,
        "configuration": {
            "llm_provider": "openai",
            "llm_model": "gpt-5.5",
            "image_provider": "gmi",
            "image_model": "gpt-image-2",
            "workflow": payload["workflow"],
            "external_source_provider": payload["external_source_provider"],
            "data_sources": payload["data_sources"],
            "past_jobs_limit": past_jobs_limit if not is_web else None,
        },
        "timing": {
            "wall_started_at": format_utc(wall_started),
            "wall_completed_at": format_utc(wall_completed),
            "wall_seconds": round(wall_seconds, 6),
            "retrieval_seconds": round(retrieval_seconds, 6),
            "generation_and_image_seconds": round(generation_seconds, 6),
            "job_started_at": job.get("started_at"),
            "job_completed_at": job.get("completed_at"),
            "persisted_job_seconds": job_duration_seconds(job),
        },
        "metrics": deterministic_metrics(response),
        "job": safe_output(job),
        "response": response,
    }


def review_run(run: dict[str, Any], *, judge_model: str) -> RunQualityReview:
    from blueprint_core.llm import build_llm_provider

    provider = build_llm_provider("openai", judge_model)
    image_bytes, image_mime_type = first_image(run.get("response") or {})
    review_payload = {
        "label": run["label"],
        "prompt": run["prompt"],
        "configuration": run["configuration"],
        "timing": run["timing"],
        "metrics": run["metrics"],
        "project_ir": safe_output((run.get("response") or {}).get("project_ir") or {}),
    }
    prompt = f"""
You are an independent senior hardware-design evaluator. Review this generated Forma project against the
user request. Inspect electrical plausibility, exact component and pin compatibility, completeness,
manufacturability, safety, documentation, and whether the attached product image (if present) is coherent
and useful. Do not trust the project's own is_valid flag; find concrete issues yourself. Apply a strict,
consistent 1-10 rubric. A 9-10 must be close to build-ready with datasheet verification; 7-8 is strong but
needs normal engineering review; 5-6 has meaningful omissions; below 5 is substantially flawed.

RUN DATA:
{json.dumps(review_payload, ensure_ascii=True, default=str)}
"""
    return provider.generate_structured(
        prompt,
        RunQualityReview,
        image_bytes=image_bytes,
        image_mime_type=image_mime_type,
    )


def review_pair(runs: list[dict[str, Any]], reviews: dict[str, dict[str, Any]], *, judge_model: str) -> PairwiseReview:
    from blueprint_core.llm import build_llm_provider

    provider = build_llm_provider("openai", judge_model)
    pair_payload = []
    for run in runs:
        pair_payload.append(
            {
                "label": run["label"],
                "prompt": run["prompt"],
                "configuration": run["configuration"],
                "timing": run["timing"],
                "metrics": run["metrics"],
                "independent_review": reviews.get(run["label"]),
                "project_ir": safe_output((run.get("response") or {}).get("project_ir") or {}),
            }
        )
    prompt = f"""
Act as a strict pairwise hardware-project judge. Both candidates used the same language and image models;
their context source differs. Compare output quality, not speed, and choose a winner only when the evidence
supports it. Treat the independent reviews as advisory and verify their claims against the project data.
Explain the most decision-relevant differences and give a practical recommendation.

CANDIDATES:
{json.dumps(pair_payload, ensure_ascii=True, default=str)}
"""
    return provider.generate_structured(prompt, PairwiseReview)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--owner-user-id", default="local-dev-user")
    parser.add_argument("--past-jobs-limit", type=int, default=3, choices=range(1, 9))
    parser.add_argument("--judge-model", default="gpt-5.5")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    from dotenv import load_dotenv

    load_dotenv(ROOT_DIR / ".env", override=False)
    os.environ["IMAGE_PROVIDER"] = "gmi"
    os.environ["GMI_IMAGE_MODEL"] = "gpt-image-2"
    os.environ["IMAGE_OUTPUT_ENABLED"] = "true"

    started = utc_now()
    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    output_dir = Path(args.output_dir).expanduser()
    if not output_dir.is_absolute():
        output_dir = ROOT_DIR / output_dir
    report_dir = output_dir / run_id

    runs: list[dict[str, Any]] = []
    for label in ("web_research", "past_jobs"):
        print(f"[context-eval] starting {label}", flush=True)
        run = asyncio.run(
            run_generation(
                label=label,
                prompt=args.prompt,
                owner_user_id=args.owner_user_id,
                past_jobs_limit=args.past_jobs_limit,
            )
        )
        runs.append(run)
        write_json(report_dir / f"{label}.json", safe_output(run))
        print(
            f"[context-eval] {label} {run['status']} wall={run['timing']['wall_seconds']:.2f}s "
            f"job={run['timing']['persisted_job_seconds']}",
            flush=True,
        )

    reviews: dict[str, dict[str, Any]] = {}
    evaluation_errors: dict[str, str] = {}
    for run in runs:
        if run["status"] != "succeeded":
            continue
        try:
            print(f"[context-eval] OpenAI review {run['label']}", flush=True)
            reviews[run["label"]] = review_run(run, judge_model=args.judge_model).model_dump(mode="json")
        except Exception as exc:
            evaluation_errors[run["label"]] = f"{exc.__class__.__name__}: {exc}"

    pairwise = None
    if len(reviews) == 2:
        try:
            print("[context-eval] OpenAI pairwise review", flush=True)
            pairwise = review_pair(runs, reviews, judge_model=args.judge_model).model_dump(mode="json")
        except Exception as exc:
            evaluation_errors["pairwise"] = f"{exc.__class__.__name__}: {exc}"

    completed = utc_now()
    public_runs = []
    for run in runs:
        public_run = {key: value for key, value in safe_output(run).items() if key != "response"}
        public_runs.append(public_run)
    report = {
        "schema_version": 1,
        "eval": "context_source_comparison",
        "prompt": args.prompt,
        "started_at": format_utc(started),
        "completed_at": format_utc(completed),
        "total_wall_seconds": round((completed - started).total_seconds(), 6),
        "judge": {"provider": "openai", "model": args.judge_model},
        "runs": public_runs,
        "reviews": reviews,
        "pairwise": pairwise,
        "evaluation_errors": evaluation_errors,
        "artifact_paths": {
            "web_research": str(report_dir / "web_research.json"),
            "past_jobs": str(report_dir / "past_jobs.json"),
        },
    }
    write_json(report_dir / "comparison.json", report)
    write_json(output_dir / "latest.json", report)
    print(f"[context-eval] report={report_dir / 'comparison.json'}", flush=True)
    return 0 if all(run["status"] == "succeeded" for run in runs) and pairwise else 1


if __name__ == "__main__":
    raise SystemExit(main())
