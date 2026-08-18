#!/usr/bin/env python3
"""Run a Forma hardware prompt against configured LLMs concurrently."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Callable


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from scripts.models import sample
from blueprint_core.selectors import LLMSelector


DEFAULT_CONCURRENCY = 4


def resolve_candidates(args: argparse.Namespace) -> list[LLMSelector]:
    return sample.resolve_candidates(args)


async def run_candidates_async(
    candidates: list[LLMSelector],
    *,
    prompt: str,
    timeout_seconds: float | None,
    config_only: bool,
    concurrency: int,
    sync_runner: Callable[[LLMSelector], dict[str, Any]] | None = None,
    on_result: Callable[[dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    limit = max(1, int(concurrency or DEFAULT_CONCURRENCY))
    semaphore = asyncio.Semaphore(limit)

    def default_runner(candidate: LLMSelector) -> dict[str, Any]:
        return sample.run_candidate(
            candidate,
            prompt=prompt,
            timeout_seconds=timeout_seconds,
            config_only=config_only,
        )

    runner = sync_runner or default_runner

    async def run_one(index: int, candidate: LLMSelector) -> dict[str, Any]:
        async with semaphore:
            try:
                result = await asyncio.to_thread(runner, candidate)
            except Exception as exc:
                result = {
                    "llm": candidate.key,
                    "provider": candidate.provider,
                    "model": candidate.model,
                    "status": "fail",
                    "error": sample.compact_error(exc),
                }
        result.setdefault("llm", candidate.key)
        result.setdefault("provider", candidate.provider)
        result.setdefault("model", candidate.model)
        result["candidate_index"] = index
        if on_result:
            on_result(result)
        return result

    return await asyncio.gather(*(run_one(index, candidate) for index, candidate in enumerate(candidates)))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", nargs="?", default=sample.DEFAULT_PROMPT)
    parser.add_argument("--env-file", default=sample.DEFAULT_ENV_FILE)
    parser.add_argument("--llm", action="append", type=sample.parse_llm_selector)
    parser.add_argument("--provider")
    parser.add_argument("--model")
    parser.add_argument("--include-simulation", action="store_true")
    parser.add_argument("--only-default-model", action="store_true")
    parser.add_argument("--timeout-seconds", type=float)
    parser.add_argument("--config-only", action="store_true")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-save", action="store_true")
    parser.add_argument("--output-dir", default=sample.DEFAULT_OUTPUT_DIR)
    parser.add_argument("--output-file")
    return parser


async def async_main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.concurrency <= 0:
        print("[sample-async] --concurrency must be greater than zero", file=sys.stderr)
        return 2

    try:
        sample.load_env_file(sample.path_from_repo(args.env_file))
        candidates = resolve_candidates(args)
    except Exception as exc:
        print(f"[sample-async] config error: {exc}", file=sys.stderr)
        return 2

    if not candidates:
        print("[sample-async] no candidates found", file=sys.stderr)
        return 2
    if args.list:
        payload = [{"provider": item.provider, "model": item.model, "llm": item.key} for item in candidates]
        print(json.dumps(payload, indent=2, sort_keys=True) if args.json else "\n".join(item.key for item in candidates))
        return 0

    started_at = sample.utc_now()
    results = await run_candidates_async(
        candidates,
        prompt=args.prompt,
        timeout_seconds=args.timeout_seconds,
        config_only=args.config_only,
        concurrency=args.concurrency,
    )
    report = sample.build_report(
        prompt=args.prompt,
        env_file=args.env_file,
        candidates=candidates,
        results=results,
        started_at=started_at,
        completed_at=sample.utc_now(),
        tool="scripts/models/sample_async.py",
    )

    report_path: Path | None = None
    latest_path: Path | None = None
    if not args.no_save or args.output_file:
        report_path, latest_path = sample.save_report(
            report,
            output_dir=args.output_dir,
            output_file=args.output_file,
        )

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for result in results:
            sample.print_result(result)
        print(f"[sample-async] summary passed={report['summary']['passed']} failed={report['summary']['failed']}")
        if report_path and latest_path:
            print(f"[sample-async] saved report={report_path}")
            print(f"[sample-async] latest report={latest_path}")
    return 0 if report["summary"]["ok"] else 1


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
