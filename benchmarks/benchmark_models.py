#!/usr/bin/env python3
"""Benchmark configured Blueprint LLM providers and models."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


import sample
import sample_async
from blueprint_core.selectors import LLMSelector
from blueprint_core.huggingface_artifacts import (
    HuggingFaceUploadConfig,
    build_artifacts,
    upload_artifacts_to_huggingface,
)


DEFAULT_ITERATIONS = 1
DEFAULT_OUTPUT_DIR = ".logs/benchmarks"
LATEST_REPORT_NAME = "model-latest.json"
JOB_CSV_COLUMNS = [
    "sequence",
    "completed_at",
    "round",
    "measured",
    "llm",
    "provider",
    "model",
    "actual_model",
    "status",
    "duration_seconds",
    "benchmark_duration_seconds",
    "provider_duration_seconds",
    "configured",
    "live_generation_enabled",
    "validation_error",
    "error",
    "response_summary",
]


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def run_id_from_timestamp(value: datetime) -> str:
    return sample.format_utc(value).replace("-", "").replace(":", "").replace("Z", "Z")


def parse_job_log_formats(value: str) -> set[str]:
    normalized = {item.strip().lower() for item in value.split(",") if item.strip()}
    if not normalized:
        return {"jsonl", "csv"}
    if "both" in normalized:
        normalized.update({"jsonl", "csv"})
        normalized.discard("both")
    invalid = normalized - {"jsonl", "csv"}
    if invalid:
        raise argparse.ArgumentTypeError("job log format must be jsonl, csv, or both.")
    return normalized


class BenchmarkJobSink:
    """Append each completed benchmark job to durable local artifacts."""

    def __init__(self, *, output_dir: str | Path, run_id: str, formats: set[str]):
        self.output_dir = sample.path_from_repo(output_dir)
        self.run_id = run_id
        self.formats = formats
        self.jsonl_path = self.output_dir / f"model-job-results-{run_id}.jsonl"
        self.csv_path = self.output_dir / f"model-job-results-{run_id}.csv"
        self.count = 0
        self._lock = threading.Lock()
        self._jsonl_handle = None
        self._csv_handle = None
        self._csv_writer = None

    def __enter__(self) -> "BenchmarkJobSink":
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if "jsonl" in self.formats:
            self._jsonl_handle = self.jsonl_path.open("a", encoding="utf-8")
        if "csv" in self.formats:
            self._csv_handle = self.csv_path.open("a", encoding="utf-8", newline="")
            self._csv_writer = csv.DictWriter(self._csv_handle, fieldnames=JOB_CSV_COLUMNS)
            if self.csv_path.stat().st_size == 0:
                self._csv_writer.writeheader()
                self._csv_handle.flush()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self._jsonl_handle:
            self._jsonl_handle.close()
        if self._csv_handle:
            self._csv_handle.close()

    def as_report_metadata(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "jsonl_path": str(self.jsonl_path) if "jsonl" in self.formats else None,
            "csv_path": str(self.csv_path) if "csv" in self.formats else None,
        }

    def record(self, result: dict[str, Any], *, round_index: int, measured: bool) -> None:
        validation = result.get("validation") if isinstance(result.get("validation"), dict) else {}
        response = result.get("response") if isinstance(result.get("response"), dict) else {}
        benchmark_duration = float(result.get("benchmark_duration_seconds", result.get("duration_seconds") or 0.0))
        provider_duration = float(result.get("duration_seconds") or 0.0)

        with self._lock:
            self.count += 1
            sequence = self.count

            record = {
                "schema_version": 1,
                "sequence": sequence,
                "completed_at": sample.format_utc(sample.utc_now()),
                "round": round_index,
                "measured": measured,
                "llm": result.get("llm"),
                "provider": result.get("provider"),
                "model": result.get("model"),
                "actual_model": result.get("actual_model"),
                "status": result.get("status"),
                "duration_seconds": round(benchmark_duration, 6),
                "benchmark_duration_seconds": round(benchmark_duration, 6),
                "provider_duration_seconds": round(provider_duration, 6),
                "configured": result.get("configured"),
                "live_generation_enabled": validation.get("live_generation_enabled"),
                "validation_error": validation.get("validation_error"),
                "error": result.get("error"),
                "response_summary": response.get("summary"),
                "result": result,
            }

            if self._jsonl_handle:
                self._jsonl_handle.write(json.dumps(record, sort_keys=True) + "\n")
                self._jsonl_handle.flush()

            if self._csv_writer and self._csv_handle:
                self._csv_writer.writerow({column: record.get(column) for column in JOB_CSV_COLUMNS})
                self._csv_handle.flush()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benchmark configured Blueprint LLM provider/model pairs.")
    parser.add_argument("prompt", nargs="?", default=sample.DEFAULT_PROMPT, help="Prompt to send in live mode.")
    parser.add_argument("--env-file", default=sample.DEFAULT_ENV_FILE, help=f"Dotenv file to load. Defaults to {sample.DEFAULT_ENV_FILE}.")
    parser.add_argument("--llm", action="append", type=sample.parse_llm_selector, help="Specific provider/model selector. Can be repeated.")
    parser.add_argument("--provider", help="Benchmark a single provider. Pair with --model or use the provider default model.")
    parser.add_argument("--model", help="Model to benchmark with --provider.")
    parser.add_argument("--include-simulation", action="store_true", help="Include simulation in auto-discovered candidates.")
    parser.add_argument("--only-default-model", action="store_true", help="Only benchmark each provider's resolved default model.")
    parser.add_argument("--timeout-seconds", type=float, help="Override provider read/poll timeout for this run.")
    parser.add_argument("--concurrency", type=int, default=sample_async.DEFAULT_CONCURRENCY, help=f"Max models running at once. Defaults to {sample_async.DEFAULT_CONCURRENCY}.")
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS, help=f"Benchmark rounds. Defaults to {DEFAULT_ITERATIONS}.")
    parser.add_argument("--warmup", type=int, default=0, help="Optional warmup rounds before measured rounds. Defaults to 0.")
    parser.add_argument("--live", action="store_true", help="Send real generation calls. By default this only validates model configuration.")
    parser.add_argument("--list", action="store_true", help="List discovered candidates without benchmarking them.")
    parser.add_argument("--json", action="store_true", help="Print the full JSON report.")
    parser.add_argument("--no-save", action="store_true", help="Do not save a JSON report.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help=f"Report directory. Defaults to {DEFAULT_OUTPUT_DIR}.")
    parser.add_argument("--output-file", help="Write the report to a specific JSON file.")
    parser.add_argument("--no-job-log", action="store_true", help="Do not stream completed model jobs to local JSONL/CSV files.")
    parser.add_argument("--job-output-dir", help="Directory for per-completed-job logs. Defaults to --output-dir.")
    parser.add_argument(
        "--job-log-format",
        default=parse_job_log_formats("both"),
        type=parse_job_log_formats,
        help="Per-job log format: jsonl, csv, or both. Defaults to both.",
    )
    parser.add_argument("--upload-huggingface", action="store_true", help="Upload saved benchmark artifacts to a Hugging Face dataset repo.")
    parser.add_argument("--hf-repo-id", help="Hugging Face dataset repo id, for example username/blueprint-metrics. Defaults to HF_ARTIFACT_REPO_ID.")
    parser.add_argument("--hf-repo-type", default="dataset", help="Hugging Face repo type. Defaults to dataset.")
    parser.add_argument("--hf-path-prefix", default="blueprint", help="Path prefix inside the Hugging Face repo. Defaults to blueprint.")
    parser.add_argument("--hf-private", action="store_true", help="Create the Hugging Face repo as private when it does not exist.")
    parser.add_argument("--hf-no-create-repo", action="store_true", help="Do not create the Hugging Face repo before uploading.")
    parser.add_argument("--hf-commit-message", default="Upload Blueprint model benchmark artifacts", help="Commit message for Hugging Face uploads.")
    return parser


def resolve_candidates(args: argparse.Namespace) -> list[LLMSelector]:
    return sample_async.resolve_candidates(args)


async def run_round(
    *,
    round_index: int,
    candidates: list[LLMSelector],
    args: argparse.Namespace,
    measured: bool,
    job_sink: BenchmarkJobSink | None = None,
) -> dict[str, Any]:
    def runner(candidate: LLMSelector) -> dict[str, Any]:
        started_at = time.perf_counter()
        result = sample.run_candidate(
            candidate,
            prompt=args.prompt,
            timeout_seconds=args.timeout_seconds,
            config_only=not args.live,
        )
        result["benchmark_duration_seconds"] = round(time.perf_counter() - started_at, 6)
        return result

    def on_result(result: dict[str, Any]) -> None:
        if job_sink:
            job_sink.record(result, round_index=round_index, measured=measured)

    started_monotonic = time.perf_counter()
    results = await sample_async.run_candidates_async(
        candidates,
        prompt=args.prompt,
        timeout_seconds=args.timeout_seconds,
        config_only=not args.live,
        concurrency=args.concurrency,
        sync_runner=runner,
        on_result=on_result,
    )
    elapsed = time.perf_counter() - started_monotonic
    for result in results:
        result["round"] = round_index
        result["measured"] = measured
    return {
        "round": round_index,
        "measured": measured,
        "duration_seconds": round(elapsed, 3),
        "results": results,
    }


async def run_model_benchmark(
    args: argparse.Namespace,
    candidates: list[LLMSelector],
    *,
    job_sink: BenchmarkJobSink | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    warmup_rounds: list[dict[str, Any]] = []
    measured_rounds: list[dict[str, Any]] = []

    for index in range(1, max(0, args.warmup) + 1):
        warmup_rounds.append(await run_round(round_index=index, candidates=candidates, args=args, measured=False, job_sink=job_sink))

    for index in range(1, args.iterations + 1):
        measured_rounds.append(await run_round(round_index=index, candidates=candidates, args=args, measured=True, job_sink=job_sink))

    return warmup_rounds, measured_rounds


def summarize_candidate_runs(candidates: list[LLMSelector], rounds: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for benchmark_round in rounds:
        for result in benchmark_round.get("results", []):
            grouped[str(result.get("llm"))].append(result)

    candidate_summaries: list[dict[str, Any]] = []
    for candidate in candidates:
        results = grouped.get(candidate.key, [])
        durations = [
            float(result.get("benchmark_duration_seconds", result.get("duration_seconds") or 0.0))
            for result in results
        ]
        errors = []
        for result in results:
            error = result.get("error")
            if error and error not in errors:
                errors.append(error)

        candidate_summaries.append(
            {
                "llm": candidate.key,
                "provider": candidate.provider,
                "model": candidate.model,
                "runs": len(results),
                "passed": sum(1 for result in results if result.get("status") == "pass"),
                "failed": sum(1 for result in results if result.get("status") != "pass"),
                "duration_seconds": {
                    "min": round(min(durations), 6) if durations else 0.0,
                    "mean": round(mean(durations), 6) if durations else 0.0,
                    "median": round(median(durations), 6) if durations else 0.0,
                    "p95": round(percentile(durations, 0.95), 6) if durations else 0.0,
                    "max": round(max(durations), 6) if durations else 0.0,
                },
                "actual_model": next((result.get("actual_model") for result in reversed(results) if result.get("actual_model")), None),
                "errors": errors[:5],
            }
        )

    all_results = [result for benchmark_round in rounds for result in benchmark_round.get("results", [])]
    return {
        "ok": all(result.get("status") == "pass" for result in all_results) if all_results else False,
        "passed": sum(1 for result in all_results if result.get("status") == "pass"),
        "failed": sum(1 for result in all_results if result.get("status") != "pass"),
        "total": len(all_results),
        "candidates": candidate_summaries,
    }


def build_report(
    *,
    args: argparse.Namespace,
    candidates: list[LLMSelector],
    warmup_rounds: list[dict[str, Any]],
    measured_rounds: list[dict[str, Any]],
    started_at: datetime,
    completed_at: datetime,
    job_artifacts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = summarize_candidate_runs(candidates, measured_rounds)
    return {
        "schema_version": 1,
        "tool": "benchmarks/benchmark_models.py",
        "started_at": sample.format_utc(started_at),
        "completed_at": sample.format_utc(completed_at),
        "duration_seconds": round((completed_at - started_at).total_seconds(), 3),
        "env_file": str(sample.path_from_repo(args.env_file)),
        "prompt": args.prompt,
        "mode": {
            "live": bool(args.live),
            "config_only": not bool(args.live),
            "iterations": args.iterations,
            "warmup": args.warmup,
            "concurrency": max(1, int(args.concurrency or sample_async.DEFAULT_CONCURRENCY)),
            "include_simulation": bool(args.include_simulation),
            "only_default_model": bool(args.only_default_model),
            "timeout_seconds": args.timeout_seconds,
        },
        "candidates": [{"provider": item.provider, "model": item.model, "llm": item.key} for item in candidates],
        "summary": summary,
        "job_artifacts": job_artifacts,
        "warmup_rounds": warmup_rounds,
        "rounds": measured_rounds,
    }


def save_report(report: dict[str, Any], *, output_dir: str, output_file: str | None) -> tuple[Path, Path]:
    completed_at = str(report.get("completed_at") or sample.format_utc(sample.utc_now()))
    run_id = completed_at.replace("-", "").replace(":", "").replace("Z", "Z")
    status = "pass" if report.get("summary", {}).get("ok") else "fail"

    if output_file:
        report_path = sample.path_from_repo(output_file)
        report_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        report_dir = sample.path_from_repo(output_dir)
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"model-benchmark-{run_id}-{status}.json"

    latest_path = report_path.parent / LATEST_REPORT_NAME
    general_latest_path = report_path.parent / "latest.json"
    report["report_path"] = str(report_path)
    report["latest_report_path"] = str(latest_path)
    report["summary"]["report_path"] = str(report_path)
    report["summary"]["latest_report_path"] = str(latest_path)

    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    report_path.write_text(payload, encoding="utf-8")
    latest_path.write_text(payload, encoding="utf-8")
    general_latest_path.write_text(payload, encoding="utf-8")
    return report_path, latest_path


def rewrite_saved_report(report: dict[str, Any], *, report_path: Path | None, latest_path: Path | None) -> None:
    if not report_path:
        return
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    report_path.write_text(payload, encoding="utf-8")
    if latest_path:
        latest_path.write_text(payload, encoding="utf-8")
        (latest_path.parent / "latest.json").write_text(payload, encoding="utf-8")


def artifact_paths_for_upload(
    *,
    report_path: Path | None,
    latest_path: Path | None,
    job_artifacts: dict[str, Any] | None,
) -> list[Path]:
    paths: list[Path] = []
    for path in (report_path, latest_path):
        if path:
            paths.append(path)
    if job_artifacts:
        for key in ("jsonl_path", "csv_path"):
            value = job_artifacts.get(key)
            if value:
                paths.append(Path(value))
    return paths


def upload_saved_artifacts(
    args: argparse.Namespace,
    *,
    report_path: Path | None,
    latest_path: Path | None,
    job_artifacts: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not args.upload_huggingface:
        return None
    if not report_path:
        raise ValueError("Hugging Face upload requires a saved report. Remove --no-save or set --output-file.")

    config = HuggingFaceUploadConfig.from_env(
        repo_id=args.hf_repo_id,
        repo_type=args.hf_repo_type,
        private=bool(args.hf_private),
        create_repo=not bool(args.hf_no_create_repo),
        path_prefix=args.hf_path_prefix,
        commit_message=args.hf_commit_message,
    )
    artifacts = build_artifacts(
        artifact_paths_for_upload(
            report_path=report_path,
            latest_path=latest_path,
            job_artifacts=job_artifacts,
        ),
        artifact_type="benchmarks/model",
        path_prefix=config.path_prefix,
        root_dir=ROOT_DIR,
    )
    result = upload_artifacts_to_huggingface(artifacts, config=config)
    return result.as_dict()


def print_candidate_summary(summary: dict[str, Any]) -> None:
    for candidate in summary.get("candidates", []):
        durations = candidate.get("duration_seconds") or {}
        print(
            f"[benchmark-models] {candidate['llm']:<48} "
            f"passed={candidate['passed']} failed={candidate['failed']} "
            f"mean={durations.get('mean', 0.0):.6f}s p95={durations.get('p95', 0.0):.6f}s"
        )
        if candidate.get("errors"):
            print(f"[benchmark-models] {'':<48} error={candidate['errors'][0]}")


async def async_main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.iterations <= 0:
        parser.error("--iterations must be greater than zero.")
    if args.warmup < 0:
        parser.error("--warmup cannot be negative.")

    try:
        sample.load_env_file(sample.path_from_repo(args.env_file))
    except Exception as exc:
        print(f"[benchmark-models] config error: {exc}", file=sys.stderr)
        return 2

    candidates = resolve_candidates(args)
    if not candidates:
        print("[benchmark-models] no candidates found", file=sys.stderr)
        return 2

    if args.list:
        payload = [{"provider": item.provider, "model": item.model, "llm": item.key} for item in candidates]
        print(json.dumps(payload, indent=2, sort_keys=True) if args.json else "\n".join(f"[benchmark-models] candidate {item.key}" for item in candidates))
        return 0

    if not args.json:
        mode = "live" if args.live else "config-only"
        print(
            f"[benchmark-models] running {len(candidates)} model(s), "
            f"iterations={args.iterations}, concurrency={max(1, int(args.concurrency or sample_async.DEFAULT_CONCURRENCY))}, mode={mode}"
        )

    started_at = sample.utc_now()
    run_id = run_id_from_timestamp(started_at)
    job_sink: BenchmarkJobSink | None = None
    job_artifacts: dict[str, Any] | None = None

    if args.no_job_log:
        warmup_rounds, measured_rounds = await run_model_benchmark(args, candidates)
    else:
        job_sink = BenchmarkJobSink(
            output_dir=args.job_output_dir or args.output_dir,
            run_id=run_id,
            formats=args.job_log_format,
        )
        with job_sink:
            if not args.json:
                print(
                    "[benchmark-models] streaming completed jobs to "
                    + ", ".join(path for path in (str(job_sink.jsonl_path) if "jsonl" in job_sink.formats else None, str(job_sink.csv_path) if "csv" in job_sink.formats else None) if path)
                )
            warmup_rounds, measured_rounds = await run_model_benchmark(args, candidates, job_sink=job_sink)
            job_artifacts = job_sink.as_report_metadata()
    completed_at = sample.utc_now()
    report = build_report(
        args=args,
        candidates=candidates,
        warmup_rounds=warmup_rounds,
        measured_rounds=measured_rounds,
        started_at=started_at,
        completed_at=completed_at,
        job_artifacts=job_artifacts,
    )

    report_path: Path | None = None
    latest_path: Path | None = None
    if not args.no_save or args.output_file:
        report_path, latest_path = save_report(report, output_dir=args.output_dir, output_file=args.output_file)

    huggingface_upload: dict[str, Any] | None = None
    if args.upload_huggingface:
        try:
            huggingface_upload = upload_saved_artifacts(
                args,
                report_path=report_path,
                latest_path=latest_path,
                job_artifacts=job_artifacts,
            )
            report["huggingface_upload"] = huggingface_upload
            rewrite_saved_report(report, report_path=report_path, latest_path=latest_path)
        except Exception as exc:
            report["huggingface_upload"] = {"status": "failed", "error": str(exc)}
            rewrite_saved_report(report, report_path=report_path, latest_path=latest_path)
            print(f"[benchmark-models] huggingface upload failed: {exc}", file=sys.stderr)
            return 2

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_candidate_summary(report["summary"])
        print(
            f"[benchmark-models] summary passed={report['summary']['passed']} "
            f"failed={report['summary']['failed']} total={report['summary']['total']}"
        )
        if not args.live:
            print("[benchmark-models] live generation was not run; use --live to measure provider response latency.")
        if job_artifacts:
            if job_artifacts.get("jsonl_path"):
                print(f"[benchmark-models] job jsonl={job_artifacts['jsonl_path']}")
            if job_artifacts.get("csv_path"):
                print(f"[benchmark-models] job csv={job_artifacts['csv_path']}")
        if report_path and latest_path:
            print(f"[benchmark-models] saved report={report_path}")
            print(f"[benchmark-models] latest report={latest_path}")
        if huggingface_upload:
            print(
                f"[benchmark-models] huggingface repo={huggingface_upload['repo_id']} "
                f"uploaded={huggingface_upload['count']}"
            )

    return 0 if report["summary"]["ok"] else 1


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
