#!/usr/bin/env python3
"""Smoke-test configured Blueprint LLM providers and runtime model selectors."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


DEFAULT_ENV_FILE = ".env"
DEFAULT_EXPECTED_MESSAGE = "blueprint llm provider ok"
DEFAULT_REPORT_DIR = ".logs/llm-smoke"
LATEST_REPORT_NAME = "latest.json"
PLACEHOLDER_VALUES = {"", "unknown", "n/a", "na", "none", "null", "new"}


from blueprint_core.selectors import LLMSelector as LlmCandidate
from blueprint_core.selectors import parse_llm_selector as parse_core_llm_selector


def parse_llm_selector(value: str) -> LlmCandidate:
    try:
        selector = parse_core_llm_selector(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    if selector is None:
        raise argparse.ArgumentTypeError("LLM selector is required.")
    return selector


def is_placeholder(value: str | None) -> bool:
    return str(value or "").strip().lower() in PLACEHOLDER_VALUES


def compact_error(error: BaseException, max_chars: int = 900) -> str:
    message = str(error).strip() or error.__class__.__name__
    if len(message) <= max_chars:
        return message
    return message[:max_chars] + "...<truncated>"


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


def discover_candidates(*, include_simulation: bool, only_default_model: bool) -> list[LlmCandidate]:
    from blueprint_core.llm import LLMProviderConfigError, resolve_llm_runtime_config

    default_runtime = resolve_llm_runtime_config()
    providers = default_runtime.allowed_providers or [default_runtime.provider]
    candidates: list[LlmCandidate] = []

    for provider in providers:
        if provider == "simulation" and not include_simulation:
            continue
        try:
            provider_runtime = resolve_llm_runtime_config(provider, None)
        except LLMProviderConfigError as exc:
            print(f"[llm-smoke] skip provider={provider}: {exc}", file=sys.stderr)
            continue

        models = [provider_runtime.model] if only_default_model else (provider_runtime.allowed_models or [provider_runtime.model])
        for model in models:
            if model:
                candidates.append(LlmCandidate(provider_runtime.provider, model))

    return dedupe_candidates(candidates)


def dedupe_candidates(candidates: list[LlmCandidate]) -> list[LlmCandidate]:
    seen: set[str] = set()
    unique: list[LlmCandidate] = []
    for candidate in candidates:
        if candidate.key in seen:
            continue
        seen.add(candidate.key)
        unique.append(candidate)
    return unique


def smoke_prompt(candidate: LlmCandidate, expected_message: str) -> str:
    return (
        "Blueprint LLM provider smoke test.\n"
        f"Provider selector: {candidate.provider}\n"
        f"Model selector: {candidate.model}\n"
        "Return only valid JSON. Set ok to true. "
        f"Set message to exactly {expected_message!r}."
    )


def run_candidate(
    candidate: LlmCandidate,
    *,
    expected_message: str,
    timeout_seconds: float | None,
    require_exact_message: bool,
    config_only: bool,
) -> dict[str, Any]:
    from pydantic import BaseModel, Field

    from blueprint_core.llm import build_llm_provider, resolve_llm_runtime_config

    class LLMProviderSmokeResponse(BaseModel):
        ok: bool = Field(..., description="True when the provider understood and completed the smoke test.")
        message: str = Field(..., description="Short success message.")

    started_at = time.monotonic()
    result: dict[str, Any] = {
        "provider": candidate.provider,
        "model": candidate.model,
        "status": "fail",
    }

    try:
        runtime = resolve_llm_runtime_config(candidate.provider, candidate.model)
        provider = build_llm_provider(runtime_config=runtime)
        if timeout_seconds is not None and hasattr(provider, "timeout_seconds"):
            provider.timeout_seconds = float(timeout_seconds)
        if timeout_seconds is not None and hasattr(provider, "poll_timeout_seconds"):
            provider.poll_timeout_seconds = float(timeout_seconds)

        validation = provider.validate_configured_model(raise_on_strict=False)
        result["validation"] = validation.as_debug_dict()
        result["actual_model"] = validation.actual_model or getattr(provider, "model_name", None)
        result["configured"] = bool(getattr(provider, "is_configured", False))

        if validation.validation_error or not validation.live_generation_enabled or not getattr(provider, "is_configured", False):
            result["status"] = "fail"
            result["error"] = validation.validation_error or "Provider is not configured for live generation."
            return result

        if config_only:
            result["status"] = "pass"
            return result

        response = provider.generate_structured(
            smoke_prompt(candidate, expected_message),
            LLMProviderSmokeResponse,
        )
        response_payload = response.model_dump()
        result["response"] = response_payload

        message = str(response.message or "").strip()
        if response.ok is not True:
            raise RuntimeError(f"Provider returned ok={response.ok!r}.")
        if is_placeholder(message):
            raise RuntimeError(f"Provider returned placeholder message {message!r}.")
        if require_exact_message and message != expected_message:
            raise RuntimeError(f"Provider returned message {message!r}, expected {expected_message!r}.")

        result["status"] = "pass"
        return result
    except Exception as exc:
        result["status"] = "fail"
        result["error"] = compact_error(exc)
        return result
    finally:
        result["duration_seconds"] = round(time.monotonic() - started_at, 3)


def print_human_result(result: dict[str, Any]) -> None:
    status = result.get("status", "fail").upper()
    key = f"{result.get('provider')}/{result.get('model')}"
    duration = result.get("duration_seconds", 0)
    print(f"[llm-smoke] {status:<4} {key} ({duration:.1f}s)")
    if result.get("actual_model") and result.get("actual_model") != result.get("model"):
        print(f"[llm-smoke]      actual_model={result.get('actual_model')}")
    if result.get("response"):
        print(f"[llm-smoke]      response={json.dumps(result['response'], sort_keys=True)}")
    if result.get("error"):
        print(f"[llm-smoke]      error={result['error']}")


def build_report(
    *,
    args: argparse.Namespace,
    candidates: list[LlmCandidate],
    summary: dict[str, Any],
    started_at: datetime,
    completed_at: datetime,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "tool": "verify-llm-providers.py",
        "started_at": format_utc(started_at),
        "completed_at": format_utc(completed_at),
        "duration_seconds": round((completed_at - started_at).total_seconds(), 3),
        "env_file": str(path_from_repo(args.env_file)),
        "mode": {
            "config_only": bool(args.config_only),
            "include_simulation": bool(args.include_simulation),
            "only_default_model": bool(args.only_default_model),
            "require_exact_message": bool(args.require_exact_message),
            "timeout_seconds": args.timeout_seconds,
        },
        "expected_message": args.expected_message,
        "candidates": [{"provider": item.provider, "model": item.model, "llm": item.key} for item in candidates],
        "summary": summary,
    }


def save_report(report: dict[str, Any], *, output_dir: str, output_file: str | None) -> tuple[Path, Path]:
    completed_at = str(report.get("completed_at") or format_utc(utc_now()))
    run_id = completed_at.replace("-", "").replace(":", "").replace("Z", "Z").replace("+0000", "Z")
    status = "pass" if report.get("summary", {}).get("ok") else "fail"

    if output_file:
        report_path = path_from_repo(output_file)
        report_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        report_dir = path_from_repo(output_dir)
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"llm-smoke-{run_id}-{status}.json"

    latest_path = report_path.parent / LATEST_REPORT_NAME
    report["report_path"] = str(report_path)
    report["latest_report_path"] = str(latest_path)
    if isinstance(report.get("summary"), dict):
        report["summary"]["report_path"] = str(report_path)
        report["summary"]["latest_report_path"] = str(latest_path)

    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    report_path.write_text(payload, encoding="utf-8")
    latest_path.write_text(payload, encoding="utf-8")
    return report_path, latest_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify configured Blueprint LLM providers with a tiny structured JSON smoke prompt."
    )
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE, help=f"Dotenv file to load. Defaults to {DEFAULT_ENV_FILE}.")
    parser.add_argument(
        "--llm",
        action="append",
        type=parse_llm_selector,
        help="Specific provider/model selector to test. Can be repeated.",
    )
    parser.add_argument("--provider", help="Test a single provider. Pair with --model or use the provider default model.")
    parser.add_argument("--model", help="Model to test with --provider.")
    parser.add_argument("--include-simulation", action="store_true", help="Include simulation in auto-discovered candidates.")
    parser.add_argument("--only-default-model", action="store_true", help="Only test each provider's resolved default model.")
    parser.add_argument("--timeout-seconds", type=float, help="Override provider read/poll timeout for this smoke test.")
    parser.add_argument("--config-only", action="store_true", help="Validate provider/model config without making generation calls.")
    parser.add_argument("--list", action="store_true", help="List discovered candidates without testing them.")
    parser.add_argument("--json", action="store_true", help="Emit JSON summary instead of human-readable lines.")
    parser.add_argument("--save", action="store_true", help=f"Save a JSON report under {DEFAULT_REPORT_DIR}.")
    parser.add_argument("--output-dir", default=DEFAULT_REPORT_DIR, help=f"Directory for saved reports. Defaults to {DEFAULT_REPORT_DIR}.")
    parser.add_argument("--output-file", help="Write the saved report to a specific JSON file. Implies --save.")
    parser.add_argument("--expected-message", default=DEFAULT_EXPECTED_MESSAGE, help="Expected smoke response message.")
    parser.add_argument(
        "--require-exact-message",
        action="store_true",
        help="Fail unless the returned message exactly matches --expected-message.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    started_at = utc_now()

    try:
        load_env_file(path_from_repo(args.env_file))
    except Exception as exc:
        print(f"[llm-smoke] config error: {exc}", file=sys.stderr)
        return 2

    if args.llm:
        candidates = dedupe_candidates(args.llm)
    elif args.provider:
        from blueprint_core.llm import resolve_llm_runtime_config

        runtime = resolve_llm_runtime_config(args.provider, args.model)
        candidates = [LlmCandidate(runtime.provider, runtime.model)]
    else:
        candidates = discover_candidates(
            include_simulation=args.include_simulation,
            only_default_model=args.only_default_model,
        )

    if not candidates:
        print("[llm-smoke] no candidates found", file=sys.stderr)
        return 2

    if args.list:
        payload = [{"provider": item.provider, "model": item.model, "llm": item.key} for item in candidates]
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            for item in candidates:
                print(f"[llm-smoke] candidate {item.key}")
        return 0

    results = [
        run_candidate(
            candidate,
            expected_message=args.expected_message,
            timeout_seconds=args.timeout_seconds,
            require_exact_message=args.require_exact_message,
            config_only=args.config_only,
        )
        for candidate in candidates
    ]

    summary = {
        "ok": all(result.get("status") == "pass" for result in results),
        "passed": sum(1 for result in results if result.get("status") == "pass"),
        "failed": sum(1 for result in results if result.get("status") != "pass"),
        "results": results,
    }
    completed_at = utc_now()

    report_path: Path | None = None
    latest_path: Path | None = None
    if args.save or args.output_file:
        report = build_report(
            args=args,
            candidates=candidates,
            summary=summary,
            started_at=started_at,
            completed_at=completed_at,
        )
        report_path, latest_path = save_report(
            report,
            output_dir=args.output_dir,
            output_file=args.output_file,
        )

    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        for result in results:
            print_human_result(result)
        print(f"[llm-smoke] summary passed={summary['passed']} failed={summary['failed']}")
        if report_path and latest_path:
            print(f"[llm-smoke] saved report={report_path}")
            print(f"[llm-smoke] latest report={latest_path}")

    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
