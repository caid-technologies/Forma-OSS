#!/usr/bin/env python3
"""Run deterministic local benchmarks for the Blueprint core package."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Callable, Iterator


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


DEFAULT_ITERATIONS = 1000
DEFAULT_CONCURRENCY = 4
DEFAULT_SCHEDULER_TASKS = 8
DEFAULT_SCHEDULER_SLEEP_MS = 10.0
DEFAULT_OUTPUT_DIR = ".logs/benchmarks"
LATEST_REPORT_NAME = "offline-latest.json"

from blueprint_core.huggingface_artifacts import (
    HuggingFaceUploadConfig,
    build_artifacts,
    upload_artifacts_to_huggingface,
)


@dataclass
class BenchmarkResult:
    name: str
    iterations: int
    total_seconds: float
    seconds_per_iteration: float
    iterations_per_second: float
    notes: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["total_seconds"] = round(self.total_seconds, 6)
        payload["seconds_per_iteration"] = round(self.seconds_per_iteration, 9)
        payload["iterations_per_second"] = round(self.iterations_per_second, 3)
        return payload


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_utc(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def path_from_repo(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path


@contextmanager
def isolated_environment(overrides: dict[str, str]) -> Iterator[None]:
    old_environ = os.environ.copy()
    try:
        for key in list(os.environ):
            if key.startswith(
                (
                    "ALLOWED_",
                    "BASETEN_",
                    "GEMINI_",
                    "GOOGLE_",
                    "LLM_",
                    "NIM_",
                    "NVIDIA_",
                    "OPENAI_",
                    "RUNPOD_",
                    "STRICT_",
                )
            ):
                os.environ.pop(key, None)
        os.environ.update(overrides)
        yield
    finally:
        os.environ.clear()
        os.environ.update(old_environ)


def measure_operation(
    name: str,
    *,
    iterations: int,
    operation: Callable[[], Any],
    warmup_iterations: int = 3,
    notes: dict[str, Any] | None = None,
) -> BenchmarkResult:
    if iterations <= 0:
        raise ValueError("iterations must be greater than zero.")

    for _ in range(max(0, min(warmup_iterations, iterations))):
        operation()

    started_at = time.perf_counter()
    for _ in range(iterations):
        operation()
    total_seconds = time.perf_counter() - started_at

    seconds_per_iteration = total_seconds / iterations
    return BenchmarkResult(
        name=name,
        iterations=iterations,
        total_seconds=total_seconds,
        seconds_per_iteration=seconds_per_iteration,
        iterations_per_second=(1.0 / seconds_per_iteration) if seconds_per_iteration else 0.0,
        notes=notes or {},
    )


def make_sample_circuit() -> tuple[list[Any], list[Any]]:
    from blueprint_core.models import ComponentInstance, ConnectionNet, PinDefinition, PinReference

    esp32 = ComponentInstance(
        ref_des="U1",
        part_number="ESP32-WROOM-32D",
        name="ESP32 Development Module",
        category="Microcontroller",
        quantity=1,
        unit_price=7.5,
        rationale="Runs sensing, display updates, and low-power telemetry.",
        pins=[
            PinDefinition(pin_id="3V3", name="3.3V", pin_type="Power", voltage=3.3),
            PinDefinition(pin_id="GND", name="Ground", pin_type="Ground", voltage=0.0),
            PinDefinition(pin_id="GPIO21", name="I2C SDA", pin_type="I2C", voltage=3.3),
            PinDefinition(pin_id="GPIO22", name="I2C SCL", pin_type="I2C", voltage=3.3),
            PinDefinition(pin_id="GPIO34", name="Moisture ADC", pin_type="Analog", voltage=3.3),
        ],
    )
    display = ComponentInstance(
        ref_des="DISP1",
        part_number="SSD1306-128x64",
        name="0.96 inch OLED Display",
        category="Display",
        quantity=1,
        unit_price=4.0,
        rationale="Shows moisture level, battery status, and alerts.",
        pins=[
            PinDefinition(pin_id="VCC", name="VCC", pin_type="Power", voltage=3.3),
            PinDefinition(pin_id="GND", name="Ground", pin_type="Ground", voltage=0.0),
            PinDefinition(pin_id="SDA", name="I2C SDA", pin_type="I2C", voltage=3.3),
            PinDefinition(pin_id="SCL", name="I2C SCL", pin_type="I2C", voltage=3.3),
        ],
    )
    sensor = ComponentInstance(
        ref_des="SEN1",
        part_number="CAP-MOIST-3V3",
        name="Capacitive Soil Moisture Sensor",
        category="Sensor",
        quantity=1,
        unit_price=3.5,
        rationale="Measures soil moisture without exposed resistive probes.",
        pins=[
            PinDefinition(pin_id="VCC", name="VCC", pin_type="Power", voltage=3.3),
            PinDefinition(pin_id="GND", name="Ground", pin_type="Ground", voltage=0.0),
            PinDefinition(pin_id="AOUT", name="Analog Output", pin_type="Analog", voltage=3.3),
        ],
    )

    nets = [
        ConnectionNet(
            net_id="NET_3V3",
            name="3.3V Power Rail",
            net_type="Power",
            voltage=3.3,
            pins=[
                PinReference(ref_des="U1", pin_id="3V3"),
                PinReference(ref_des="DISP1", pin_id="VCC"),
                PinReference(ref_des="SEN1", pin_id="VCC"),
            ],
        ),
        ConnectionNet(
            net_id="NET_GND",
            name="Ground",
            net_type="Ground",
            voltage=0.0,
            pins=[
                PinReference(ref_des="U1", pin_id="GND"),
                PinReference(ref_des="DISP1", pin_id="GND"),
                PinReference(ref_des="SEN1", pin_id="GND"),
            ],
        ),
        ConnectionNet(
            net_id="NET_I2C_SDA",
            name="I2C SDA",
            net_type="I2C",
            voltage=3.3,
            pins=[
                PinReference(ref_des="U1", pin_id="GPIO21"),
                PinReference(ref_des="DISP1", pin_id="SDA"),
            ],
        ),
        ConnectionNet(
            net_id="NET_I2C_SCL",
            name="I2C SCL",
            net_type="I2C",
            voltage=3.3,
            pins=[
                PinReference(ref_des="U1", pin_id="GPIO22"),
                PinReference(ref_des="DISP1", pin_id="SCL"),
            ],
        ),
        ConnectionNet(
            net_id="NET_MOISTURE_ADC",
            name="Moisture ADC",
            net_type="Analog",
            voltage=3.3,
            pins=[
                PinReference(ref_des="U1", pin_id="GPIO34"),
                PinReference(ref_des="SEN1", pin_id="AOUT"),
            ],
        ),
    ]
    return [esp32, display, sensor], nets


def benchmark_selector_parsing(iterations: int) -> BenchmarkResult:
    from blueprint_core.selectors import parse_llm_selector

    selectors = [
        "openai/gpt-5.5",
        "runpod/caid-technologies/parti-base",
        "baseten/deepseek-ai/DeepSeek-V4-Pro",
        "nvidia/meta/llama-3.1-8b-instruct",
    ]

    def operation() -> None:
        parsed = [parse_llm_selector(selector) for selector in selectors]
        if any(item is None for item in parsed):
            raise RuntimeError("selector parsing unexpectedly returned None")

    return measure_operation(
        "selectors.parse_llm_selector_batch",
        iterations=iterations,
        operation=operation,
        notes={"selectors_per_iteration": len(selectors)},
    )


def benchmark_runtime_resolution(iterations: int) -> BenchmarkResult:
    overrides = {
        "LLM_PROVIDER": "simulation",
        "LLM_ALLOWED_PROVIDERS": "simulation,openai,runpod,runpod-serverless,baseten,huggingface,nvidia",
        "OPENAI_ALLOWED_MODELS": "gpt-5.5",
        "RUNPOD_ALLOWED_MODELS": "caid-technologies/parti-base",
        "BASETEN_ALLOWED_MODELS": "deepseek-ai/DeepSeek-V4-Pro",
        "HUGGINGFACE_ALLOWED_MODELS": "Qwen/Qwen2.5-Coder-3B-Instruct:nscale",
        "NVIDIA_ALLOWED_MODELS": "meta/llama-3.1-8b-instruct",
        "RUNPOD_MODEL_ENDPOINTS": '{"caid-technologies/parti-base":"offline-endpoint"}',
    }

    with isolated_environment(overrides):
        from blueprint_core.llm import resolve_llm_runtime_config

        selections = [
            ("openai", "gpt-5.5"),
            ("runpod", "caid-technologies/parti-base"),
            ("baseten", "deepseek-ai/DeepSeek-V4-Pro"),
            ("huggingface", "Qwen/Qwen2.5-Coder-3B-Instruct:nscale"),
            ("nvidia", "meta/llama-3.1-8b-instruct"),
            ("runpod-serverless", "caid-technologies/parti-base"),
        ]

        def operation() -> None:
            resolved = [resolve_llm_runtime_config(provider, model) for provider, model in selections]
            if [item.provider for item in resolved] != [provider for provider, _ in selections]:
                raise RuntimeError("runtime resolution returned an unexpected provider")

        return measure_operation(
            "llm.resolve_runtime_config_batch",
            iterations=iterations,
            operation=operation,
            notes={"selectors_per_iteration": len(selections), "env": "isolated"},
        )


def benchmark_pydantic_netlist_build(iterations: int) -> BenchmarkResult:
    return measure_operation(
        "models.build_sample_netlist",
        iterations=iterations,
        operation=make_sample_circuit,
        notes={"components": 3, "nets": 5},
    )


def benchmark_circuit_validation(iterations: int) -> BenchmarkResult:
    from blueprint_core.validation import validate_circuit

    components, nets = make_sample_circuit()

    def operation() -> None:
        issues = validate_circuit(components, nets)
        critical = [issue for issue in issues if issue.severity.upper() == "CRITICAL"]
        if critical:
            raise RuntimeError(f"sample circuit unexpectedly produced {len(critical)} critical issue(s)")

    return measure_operation(
        "validation.validate_circuit",
        iterations=iterations,
        operation=operation,
        notes={"components": len(components), "nets": len(nets)},
    )


def benchmark_async_scheduler(task_count: int, concurrency: int, sleep_ms: float) -> BenchmarkResult:
    import sample_async
    from blueprint_core.selectors import LLMSelector

    candidates = [LLMSelector("benchmark", f"model-{index}") for index in range(task_count)]
    active_count = 0
    max_active = 0
    lock = threading.Lock()
    sleep_seconds = max(0.0, sleep_ms / 1000.0)

    def runner(candidate: LLMSelector) -> dict[str, Any]:
        nonlocal active_count, max_active
        with lock:
            active_count += 1
            max_active = max(max_active, active_count)
        try:
            if sleep_seconds:
                time.sleep(sleep_seconds)
            return {"llm": candidate.key, "status": "pass", "duration_seconds": round(sleep_seconds, 6)}
        finally:
            with lock:
                active_count -= 1

    started_at = time.perf_counter()
    results = asyncio.run(
        sample_async.run_candidates_async(
            candidates,
            prompt="offline async scheduler benchmark",
            timeout_seconds=None,
            config_only=True,
            concurrency=concurrency,
            sync_runner=runner,
        )
    )
    total_seconds = time.perf_counter() - started_at
    if len(results) != len(candidates) or any(result.get("status") != "pass" for result in results):
        raise RuntimeError("async scheduler benchmark returned unexpected results")

    effective_concurrency = max(1, min(int(concurrency or DEFAULT_CONCURRENCY), len(candidates)))
    serial_estimate = sleep_seconds * len(candidates)
    speedup = serial_estimate / total_seconds if total_seconds else 0.0
    return BenchmarkResult(
        name="sample_async.fake_provider_scheduler",
        iterations=len(candidates),
        total_seconds=total_seconds,
        seconds_per_iteration=total_seconds / len(candidates),
        iterations_per_second=(len(candidates) / total_seconds) if total_seconds else 0.0,
        notes={
            "task_count": len(candidates),
            "requested_concurrency": concurrency,
            "effective_concurrency": effective_concurrency,
            "max_active": max_active,
            "sleep_ms": sleep_ms,
            "estimated_serial_seconds": round(serial_estimate, 6),
            "estimated_speedup": round(speedup, 3),
        },
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run deterministic offline Blueprint benchmarks.")
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS, help=f"Iterations for CPU benchmarks. Defaults to {DEFAULT_ITERATIONS}.")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY, help=f"Concurrency for async scheduler benchmark. Defaults to {DEFAULT_CONCURRENCY}.")
    parser.add_argument("--scheduler-tasks", type=int, default=DEFAULT_SCHEDULER_TASKS, help=f"Fake provider tasks for async benchmark. Defaults to {DEFAULT_SCHEDULER_TASKS}.")
    parser.add_argument("--scheduler-sleep-ms", type=float, default=DEFAULT_SCHEDULER_SLEEP_MS, help=f"Fake provider sleep per task. Defaults to {DEFAULT_SCHEDULER_SLEEP_MS}ms.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help=f"Report directory. Defaults to {DEFAULT_OUTPUT_DIR}.")
    parser.add_argument("--output-file", help="Write the report to a specific JSON file.")
    parser.add_argument("--json", action="store_true", help="Print the full JSON report.")
    parser.add_argument("--no-save", action="store_true", help="Do not save a JSON report.")
    parser.add_argument("--upload-huggingface", action="store_true", help="Upload saved benchmark artifacts to a Hugging Face dataset repo.")
    parser.add_argument("--hf-repo-id", help="Hugging Face dataset repo id, for example username/blueprint-metrics. Defaults to HF_ARTIFACT_REPO_ID.")
    parser.add_argument("--hf-repo-type", default="dataset", help="Hugging Face repo type. Defaults to dataset.")
    parser.add_argument("--hf-path-prefix", default="blueprint", help="Path prefix inside the Hugging Face repo. Defaults to blueprint.")
    parser.add_argument("--hf-private", action="store_true", help="Create the Hugging Face repo as private when it does not exist.")
    parser.add_argument("--hf-no-create-repo", action="store_true", help="Do not create the Hugging Face repo before uploading.")
    parser.add_argument("--hf-commit-message", default="Upload Blueprint offline benchmark artifacts", help="Commit message for Hugging Face uploads.")
    return parser


def build_report(args: argparse.Namespace, results: list[BenchmarkResult], started_at: datetime, completed_at: datetime) -> dict[str, Any]:
    payload_results = [result.as_dict() for result in results]
    return {
        "schema_version": 1,
        "tool": "benchmarks/benchmark_offline.py",
        "started_at": format_utc(started_at),
        "completed_at": format_utc(completed_at),
        "duration_seconds": round((completed_at - started_at).total_seconds(), 3),
        "python": {
            "version": platform.python_version(),
            "executable": sys.executable,
            "platform": platform.platform(),
        },
        "mode": {
            "iterations": args.iterations,
            "concurrency": args.concurrency,
            "scheduler_tasks": args.scheduler_tasks,
            "scheduler_sleep_ms": args.scheduler_sleep_ms,
        },
        "summary": {
            "ok": True,
            "benchmarks": len(results),
            "mean_iterations_per_second": round(mean(result.iterations_per_second for result in results), 3) if results else 0.0,
        },
        "results": payload_results,
    }


def save_report(report: dict[str, Any], *, output_dir: str, output_file: str | None) -> tuple[Path, Path]:
    completed_at = str(report.get("completed_at") or format_utc(utc_now()))
    run_id = completed_at.replace("-", "").replace(":", "").replace("Z", "Z")

    if output_file:
        report_path = path_from_repo(output_file)
        report_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        report_dir = path_from_repo(output_dir)
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"offline-benchmark-{run_id}.json"

    latest_path = report_path.parent / LATEST_REPORT_NAME
    general_latest_path = report_path.parent / "latest.json"
    report["report_path"] = str(report_path)
    report["latest_report_path"] = str(latest_path)

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


def upload_saved_artifacts(
    args: argparse.Namespace,
    *,
    report_path: Path | None,
    latest_path: Path | None,
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
        [path for path in (report_path, latest_path) if path],
        artifact_type="benchmarks/offline",
        path_prefix=config.path_prefix,
        root_dir=ROOT_DIR,
    )
    result = upload_artifacts_to_huggingface(artifacts, config=config)
    return result.as_dict()


def print_result(result: BenchmarkResult) -> None:
    ms_per_iteration = result.seconds_per_iteration * 1000.0
    print(
        f"[benchmark-offline] {result.name:<42} "
        f"{ms_per_iteration:9.4f} ms/iter  {result.iterations_per_second:10.1f} iter/s"
    )
    if result.name == "sample_async.fake_provider_scheduler":
        print(
            "[benchmark-offline] "
            f"{'':<42} max_active={result.notes.get('max_active')} "
            f"speedup={result.notes.get('estimated_speedup')}x"
        )


def run_benchmarks(args: argparse.Namespace) -> list[BenchmarkResult]:
    return [
        benchmark_selector_parsing(args.iterations),
        benchmark_runtime_resolution(args.iterations),
        benchmark_pydantic_netlist_build(args.iterations),
        benchmark_circuit_validation(args.iterations),
        benchmark_async_scheduler(args.scheduler_tasks, args.concurrency, args.scheduler_sleep_ms),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.iterations <= 0:
        parser.error("--iterations must be greater than zero.")
    if args.scheduler_tasks <= 0:
        parser.error("--scheduler-tasks must be greater than zero.")

    started_at = utc_now()
    results = run_benchmarks(args)
    completed_at = utc_now()
    report = build_report(args, results, started_at, completed_at)

    report_path: Path | None = None
    latest_path: Path | None = None
    if not args.no_save or args.output_file:
        report_path, latest_path = save_report(report, output_dir=args.output_dir, output_file=args.output_file)

    huggingface_upload: dict[str, Any] | None = None
    if args.upload_huggingface:
        try:
            huggingface_upload = upload_saved_artifacts(args, report_path=report_path, latest_path=latest_path)
            report["huggingface_upload"] = huggingface_upload
            rewrite_saved_report(report, report_path=report_path, latest_path=latest_path)
        except Exception as exc:
            report["huggingface_upload"] = {"status": "failed", "error": str(exc)}
            rewrite_saved_report(report, report_path=report_path, latest_path=latest_path)
            print(f"[benchmark-offline] huggingface upload failed: {exc}", file=sys.stderr)
            return 2

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for result in results:
            print_result(result)
        print(f"[benchmark-offline] summary benchmarks={len(results)}")
        if report_path and latest_path:
            print(f"[benchmark-offline] saved report={report_path}")
            print(f"[benchmark-offline] latest report={latest_path}")
        if huggingface_upload:
            print(
                f"[benchmark-offline] huggingface repo={huggingface_upload['repo_id']} "
                f"uploaded={huggingface_upload['count']}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
