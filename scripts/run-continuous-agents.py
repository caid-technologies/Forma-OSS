#!/usr/bin/env python3
"""Run continuous Forma agents over a local Spacebase-style JSONL stream."""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from blueprint_core.continuous_agents import ContinuousAgentCoordinator, ContinuousAgentCycleReport, JsonlStreamStore


def now_ms() -> int:
    return int(time.time() * 1000)


def seed_event(store: JsonlStreamStore, text: str) -> None:
    store.ensure()
    payload: dict[str, Any] = {
        "schema_version": 1,
        "event_id": f"seed-{uuid.uuid4().hex}",
        "observed_at_unix_ms": now_ms(),
        "kind": "llm.seed.chunk",
        "source": {
            "provider": "seed",
            "source_type": "llm.stream",
            "name": "manual",
            "uri": None,
        },
        "payload": {
            "model": "manual-seed",
            "sequence": 1,
            "content": text,
            "done": True,
        },
        "metadata": {
            "seed": True,
        },
    }
    with store.events_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spacebase-root", type=Path, default=ROOT_DIR / ".spacebase")
    parser.add_argument("--stream-id", default="llama-cpp-local")
    parser.add_argument("--image", action="append", type=Path, default=[], help="Image path to inspect continuously. Can be repeated.")
    parser.add_argument("--video", action="append", type=Path, default=[], help="Video path to inspect continuously. Can be repeated.")
    parser.add_argument("--poll-interval-seconds", type=float, default=1.0)
    parser.add_argument("--idle-log-every-cycles", type=int, default=10)
    parser.add_argument("--max-cycles", type=int, default=None)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--seed-text", default=None, help="Append one sample event before starting the loop.")
    return parser.parse_args(argv)


def event_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def print_cycle_report(report: ContinuousAgentCycleReport, *, idle_log_every_cycles: int) -> None:
    if report.has_activity():
        agents = ", ".join(report.output_agent_names) or "none"
        print(
            "[continuous-agents] "
            f"cycle={report.cycle_index} events={report.new_event_count} "
            f"outputs={report.output_count} agents={agents} "
            f"offset={report.input_offset} prompt_revision={report.prompt_revision}",
            flush=True,
        )
        return
    if idle_log_every_cycles > 0 and (report.cycle_index == 1 or report.cycle_index % idle_log_every_cycles == 0):
        print(
            "[continuous-agents] "
            f"idle cycle={report.cycle_index}; waiting for new JSONL events "
            f"offset={report.input_offset}",
            flush=True,
        )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv if argv is not None else sys.argv[1:]))
    max_cycles = 1 if args.once else args.max_cycles

    store = JsonlStreamStore(args.spacebase_root.expanduser().resolve(), args.stream_id)
    store.ensure()
    if args.seed_text:
        seed_event(store, args.seed_text)

    coordinator = ContinuousAgentCoordinator(
        store,
        image_paths=[path.expanduser().resolve() for path in args.image],
        video_paths=[path.expanduser().resolve() for path in args.video],
        poll_interval_seconds=args.poll_interval_seconds,
    )

    print(f"[continuous-agents] stream={store.stream_id}", flush=True)
    print(f"[continuous-agents] events={store.events_path}", flush=True)
    print(f"[continuous-agents] agents={store.agents_dir}", flush=True)
    print(f"[continuous-agents] mode={'once' if max_cycles == 1 else 'continuous'}", flush=True)
    print(f"[continuous-agents] existing_events={event_count(store.events_path)}", flush=True)
    if store.events_path.stat().st_size == 0:
        print(
            "[continuous-agents] waiting: events.jsonl is empty. "
            "Append an event or run again with --seed-text to smoke test the agents.",
            flush=True,
        )

    try:
        coordinator.run(
            max_cycles=max_cycles,
            on_cycle=lambda report: print_cycle_report(report, idle_log_every_cycles=args.idle_log_every_cycles),
        )
    except KeyboardInterrupt:
        coordinator.stop()
        print("[continuous-agents] stopped")
        return 130

    print("[continuous-agents] cycle complete" if max_cycles else "[continuous-agents] stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
