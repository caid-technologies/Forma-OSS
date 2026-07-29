#!/usr/bin/env python3
"""Run the same Forma hardware prompt against one or more configured LLMs."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from blueprint_core.selectors import LLMSelector
from blueprint_core.selectors import parse_llm_selector as parse_core_llm_selector


DEFAULT_ENV_FILE = ".env"
DEFAULT_OUTPUT_DIR = ".logs/model-samples"
DEFAULT_PROMPT = "Describe a low-voltage plant watering monitor with OLED status"
LATEST_REPORT_NAME = "latest.json"


def parse_llm_selector(value: str) -> LLMSelector:
    try:
        selector = parse_core_llm_selector(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    if selector is None:
        raise argparse.ArgumentTypeError("LLM selector is required.")
    return selector


def dedupe_candidates(candidates: list[LLMSelector]) -> list[LLMSelector]:
    seen: set[str] = set()
    unique: list[LLMSelector] = []
    for candidate in candidates:
        if candidate.key in seen:
            continue
        seen.add(candidate.key)
        unique.append(candidate)
    return unique


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_utc(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def path_from_repo(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path


def load_env_file(path: Path) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError as exc:
        raise RuntimeError("python-dotenv is required. Install backend requirements first.") from exc

    if not path.exists():
        raise RuntimeError(f"Env file not found: {path}")
    load_dotenv(path, override=True)


def discover_candidates(*, include_simulation: bool, only_default_model: bool) -> list[LLMSelector]:
    from blueprint_core.llm import LLMProviderConfigError, resolve_llm_runtime_config

    default_runtime = resolve_llm_runtime_config()
    providers = default_runtime.allowed_providers or [default_runtime.provider]
    candidates: list[LLMSelector] = []

    for provider_name in providers:
        if provider_name == "simulation" and not include_simulation:
            continue
        try:
            runtime = resolve_llm_runtime_config(provider_name, None)
        except LLMProviderConfigError as exc:
            print(f"[sample] skip provider={provider_name}: {exc}", file=sys.stderr)
            continue

        models = [runtime.model] if only_default_model else (runtime.allowed_models or [runtime.model])
        candidates.extend(LLMSelector(runtime.provider, model) for model in models if model)

    return dedupe_candidates(candidates)


def resolve_candidates(args: argparse.Namespace) -> list[LLMSelector]:
    if args.llm:
        return dedupe_candidates(args.llm)
    if args.provider:
        from blueprint_core.llm import resolve_llm_runtime_config

        runtime = resolve_llm_runtime_config(args.provider, args.model)
        return [LLMSelector(runtime.provider, runtime.model)]
    return discover_candidates(
        include_simulation=bool(args.include_simulation),
        only_default_model=bool(args.only_default_model),
    )


def compact_error(error: BaseException, max_chars: int = 900) -> str:
    message = str(error).strip() or error.__class__.__name__
    return message if len(message) <= max_chars else message[:max_chars] + "...<truncated>"


def run_candidate(
    candidate: LLMSelector,
    *,
    prompt: str,
    timeout_seconds: float | None,
    config_only: bool,
) -> dict[str, Any]:
    from blueprint_core.agents.orchestrator import HardwarePipelineOrchestrator

    started_at = time.monotonic()
    result: dict[str, Any] = {
        "llm": candidate.key,
        "provider": candidate.provider,
        "model": candidate.model,
        "status": "fail",
    }

    try:
        orchestrator = HardwarePipelineOrchestrator(
            provider_name=candidate.provider,
            model_name=candidate.model,
        )
        provider = orchestrator.llm_provider
        if timeout_seconds is not None and hasattr(provider, "timeout_seconds"):
            provider.timeout_seconds = float(timeout_seconds)
        if timeout_seconds is not None and hasattr(provider, "poll_timeout_seconds"):
            provider.poll_timeout_seconds = float(timeout_seconds)

        validation = orchestrator.validate_configured_model(raise_on_strict=False)
        result["validation"] = validation.as_debug_dict()
        result["actual_model"] = validation.actual_model or provider.model_name
        result["configured"] = bool(provider.is_configured)

        if validation.validation_error or not validation.live_generation_enabled or not provider.is_configured:
            result["error"] = validation.validation_error or "Provider is not configured for live generation."
            return result

        if config_only:
            result["status"] = "pass"
            return result

        ir = orchestrator.generate_project(prompt)
        result["response"] = {
            "summary": {
                "title": ir.overview.title if ir.overview else None,
                "description": ir.overview.description if ir.overview else None,
                "is_valid": ir.is_valid,
                "component_count": len(ir.components),
                "net_count": len(ir.nets),
                "critical_issue_count": len(ir.validation.critical),
                "warning_count": len(ir.validation.warning),
            },
            "project_ir": ir.model_dump(mode="json"),
        }
        result["status"] = "pass"
        return result
    except Exception as exc:
        result["error"] = compact_error(exc)
        return result
    finally:
        result["duration_seconds"] = round(time.monotonic() - started_at, 3)


def build_report(
    *,
    prompt: str,
    env_file: str,
    candidates: list[LLMSelector],
    results: list[dict[str, Any]],
    started_at: datetime,
    completed_at: datetime,
    tool: str = "scripts/models/sample.py",
) -> dict[str, Any]:
    passed = sum(1 for result in results if result.get("status") == "pass")
    failed = len(results) - passed
    return {
        "schema_version": 1,
        "tool": tool,
        "started_at": format_utc(started_at),
        "completed_at": format_utc(completed_at),
        "duration_seconds": round((completed_at - started_at).total_seconds(), 3),
        "env_file": str(path_from_repo(env_file)),
        "prompt": prompt,
        "candidates": [
            {"provider": candidate.provider, "model": candidate.model, "llm": candidate.key}
            for candidate in candidates
        ],
        "summary": {"ok": failed == 0, "passed": passed, "failed": failed, "total": len(results)},
        "results": results,
    }


def save_report(
    report: dict[str, Any],
    *,
    output_dir: str | Path,
    output_file: str | Path | None,
) -> tuple[Path, Path]:
    completed_at = str(report.get("completed_at") or format_utc(utc_now()))
    run_id = completed_at.replace("-", "").replace(":", "").replace("Z", "Z")
    status = "pass" if report.get("summary", {}).get("ok") else "fail"

    if output_file:
        report_path = path_from_repo(output_file)
        report_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        report_dir = path_from_repo(output_dir)
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"model-sample-{run_id}-{status}.json"

    latest_path = report_path.parent / LATEST_REPORT_NAME
    report["report_path"] = str(report_path)
    report["latest_report_path"] = str(latest_path)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    report_path.write_text(payload, encoding="utf-8")
    latest_path.write_text(payload, encoding="utf-8")
    return report_path, latest_path


def print_result(result: dict[str, Any]) -> None:
    status = str(result.get("status") or "fail").upper()
    print(f"[sample] {status:<4} {result.get('llm')} ({float(result.get('duration_seconds') or 0):.1f}s)")
    if result.get("error"):
        print(f"[sample]      error={result['error']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", nargs="?", default=DEFAULT_PROMPT)
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    parser.add_argument("--llm", action="append", type=parse_llm_selector)
    parser.add_argument("--provider")
    parser.add_argument("--model")
    parser.add_argument("--include-simulation", action="store_true")
    parser.add_argument("--only-default-model", action="store_true")
    parser.add_argument("--timeout-seconds", type=float)
    parser.add_argument("--config-only", action="store_true")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-save", action="store_true")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--output-file")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        load_env_file(path_from_repo(args.env_file))
        candidates = resolve_candidates(args)
    except Exception as exc:
        print(f"[sample] config error: {exc}", file=sys.stderr)
        return 2

    if not candidates:
        print("[sample] no candidates found", file=sys.stderr)
        return 2
    if args.list:
        payload = [{"provider": item.provider, "model": item.model, "llm": item.key} for item in candidates]
        print(json.dumps(payload, indent=2, sort_keys=True) if args.json else "\n".join(item.key for item in candidates))
        return 0

    started_at = utc_now()
    results = [
        run_candidate(
            candidate,
            prompt=args.prompt,
            timeout_seconds=args.timeout_seconds,
            config_only=args.config_only,
        )
        for candidate in candidates
    ]
    report = build_report(
        prompt=args.prompt,
        env_file=args.env_file,
        candidates=candidates,
        results=results,
        started_at=started_at,
        completed_at=utc_now(),
    )

    report_path: Path | None = None
    latest_path: Path | None = None
    if not args.no_save or args.output_file:
        report_path, latest_path = save_report(report, output_dir=args.output_dir, output_file=args.output_file)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for result in results:
            print_result(result)
        print(f"[sample] summary passed={report['summary']['passed']} failed={report['summary']['failed']}")
        if report_path and latest_path:
            print(f"[sample] saved report={report_path}")
            print(f"[sample] latest report={latest_path}")
    return 0 if report["summary"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
