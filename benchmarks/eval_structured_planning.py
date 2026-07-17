#!/usr/bin/env python3
"""Periodic eval: WebProjectPlan structured-output shape conformance.

Replays representative planning prompts against the configured live provider
and measures how often the model's JSON is valid on the first parse, how often
the deterministic repair layers (flat-field re-nesting, truncation salvage) had
to fire, and how often the record was unusable.

This is the before/after measurement for the json_schema guided-decoding
default: with guided decoding honored by the endpoint the renest rate should be
~0; on a json_object fallback the renest layer is the operative fix and this
eval proves it holds. A future model checkpoint that changes output shape moves
these rates before it breaks production.

Paid (live LLM calls). Run before ship and nightly, not per-commit:

    python benchmarks/eval_structured_planning.py --iterations 10

Exits non-zero when the valid rate (first-parse + repaired) drops below
--pass-threshold (default 0.9). Report written to
.logs/benchmarks/structured-planning-latest.json.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from blueprint_core.agents.web_research_workflow import WebProjectPlan
from blueprint_core.llm import build_llm_provider

DEFAULT_OUTPUT_DIR = ".logs/benchmarks"
LATEST_REPORT_NAME = "structured-planning-latest.json"

# Representative of the web_architect step's real prompt shape (see
# WebResearchHardwarePipeline._plan_project). Kept deterministic so runs are
# comparable across checkpoints.
EVAL_PROMPTS = [
    "Turn this user request into a buildable low-voltage maker electronics architecture: "
    "a desk clock with an OLED display and a buzzer alarm.",
    "Turn this user request into a buildable low-voltage maker electronics architecture: "
    "a soil moisture monitor that reports readings over WiFi.",
    "Turn this user request into a buildable low-voltage maker electronics architecture: "
    "a battery-powered door sensor that sends an alert when opened.",
    "Turn this user request into a buildable low-voltage maker electronics architecture: "
    "an air quality station with CO2 and particulate sensors and a status LED.",
    "Turn this user request into a buildable low-voltage maker electronics architecture: "
    "a pet feeder with a servo-driven hopper and a feeding schedule.",
]

REPAIR_LOGGER = "blueprint_core.llm_providers"
RENEST_MARKER = "flat-field re-nesting"
SALVAGE_MARKER = "required JSON salvage"


class _RepairLogCapture(logging.Handler):
    """Collects repair-layer warnings emitted during a single structured call."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def run_case(provider: Any, prompt: str) -> dict[str, Any]:
    capture = _RepairLogCapture()
    repair_logger = logging.getLogger(REPAIR_LOGGER)
    repair_logger.addHandler(capture)
    started = time.perf_counter()
    try:
        provider.generate_structured(prompt, WebProjectPlan)
        error = None
    except Exception as exc:  # the eval reports failures, it does not crash
        error = f"{type(exc).__name__}: {exc}"
    finally:
        repair_logger.removeHandler(capture)

    renested = any(RENEST_MARKER in message for message in capture.messages)
    salvaged = any(SALVAGE_MARKER in message for message in capture.messages)
    if error is not None:
        outcome = "failed"
    elif renested or salvaged:
        outcome = "valid_after_repair"
    else:
        outcome = "valid_first_parse"
    return {
        "prompt": prompt,
        "outcome": outcome,
        "renested": renested,
        "salvaged": salvaged,
        "duration_seconds": round(time.perf_counter() - started, 3),
        "error": error,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--iterations", type=int, default=2,
                        help="Passes over the prompt set (default 2 -> 10 calls).")
    parser.add_argument("--pass-threshold", type=float, default=0.9,
                        help="Minimum overall valid rate (default 0.9).")
    parser.add_argument("--provider", default=None,
                        help="Provider override (default: configured LLM_PROVIDER).")
    parser.add_argument("--model", default=None,
                        help="Model override (default: configured model).")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    provider = build_llm_provider(provider_name=args.provider, model_name=args.model)
    if not provider.is_configured:
        print(f"Provider {provider.provider_name} is not configured; aborting eval.", file=sys.stderr)
        return 2

    cases = [
        run_case(provider, prompt)
        for _ in range(max(1, args.iterations))
        for prompt in EVAL_PROMPTS
    ]

    total = len(cases)
    counts = {
        "valid_first_parse": sum(1 for c in cases if c["outcome"] == "valid_first_parse"),
        "valid_after_repair": sum(1 for c in cases if c["outcome"] == "valid_after_repair"),
        "failed": sum(1 for c in cases if c["outcome"] == "failed"),
    }
    valid_rate = (counts["valid_first_parse"] + counts["valid_after_repair"]) / total
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider": provider.provider_name,
        "model": provider.model_name,
        "response_format": getattr(provider, "response_format", None),
        "total_cases": total,
        "counts": counts,
        "valid_rate": round(valid_rate, 3),
        "renest_rate": round(sum(1 for c in cases if c["renested"]) / total, 3),
        "salvage_rate": round(sum(1 for c in cases if c["salvaged"]) / total, 3),
        "pass_threshold": args.pass_threshold,
        "passed": valid_rate >= args.pass_threshold,
        "cases": cases,
    }

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / LATEST_REPORT_NAME
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(
        f"structured-planning eval: {counts['valid_first_parse']}/{total} first-parse, "
        f"{counts['valid_after_repair']}/{total} repaired, {counts['failed']}/{total} failed "
        f"(valid rate {valid_rate:.0%}, threshold {args.pass_threshold:.0%}) -> {report_path}"
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
