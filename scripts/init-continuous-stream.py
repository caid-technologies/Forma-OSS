#!/usr/bin/env python3
"""Initialize a local Forma continuous-agent stream."""

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

from blueprint_core.continuous_agents import ContinuousAgentState, JsonlStreamStore, utc_now


def now_ms() -> int:
    return int(time.time() * 1000)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spacebase-root", type=Path, default=ROOT_DIR / ".spacebase")
    parser.add_argument("--stream-id", default="llama-cpp-local")
    parser.add_argument("--initial-prompt", default="Generate a precise Forma project output.")
    parser.add_argument("--seed-text", default=None, help="Append one sample event after initialization.")
    parser.add_argument("--reset", action="store_true", help="Clear stream events, agent outputs, and state before initializing.")
    return parser.parse_args(argv)


def reset_store(store: JsonlStreamStore) -> None:
    if store.events_path.exists():
        store.events_path.write_text("", encoding="utf-8")
    if store.state_path.exists():
        store.state_path.unlink()
    if store.agents_dir.exists():
        for path in store.agents_dir.glob("*.jsonl"):
            path.unlink()


def write_config(store: JsonlStreamStore) -> Path:
    config_path = store.stream_dir / "continuous-stream-config.json"
    payload = {
        "schema_version": 1,
        "stream_id": store.stream_id,
        "created_or_updated_at": utc_now(),
        "events_path": str(store.events_path),
        "jobs_path": str(store.stream_dir / "jobs.jsonl"),
        "job_results_path": str(store.stream_dir / "job-results.jsonl"),
        "agents_dir": str(store.agents_dir),
        "state_path": str(store.state_path),
        "agent_outputs": {
            "reader": str(store.agent_path("reader")),
            "writer": str(store.agent_path("writer")),
            "reviewer": str(store.agent_path("reviewer")),
            "prompt_iterator": str(store.agent_path("prompt-iterator")),
        },
    }
    config_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return config_path


def append_seed_event(store: JsonlStreamStore, text: str) -> str:
    event_id = f"seed-{uuid.uuid4().hex}"
    payload: dict[str, Any] = {
        "schema_version": 1,
        "event_id": event_id,
        "observed_at_unix_ms": now_ms(),
        "kind": "llm.seed.chunk",
        "source": {
            "provider": "seed",
            "source_type": "llm.stream",
            "name": "init-continuous-stream",
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
    return event_id


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv if argv is not None else sys.argv[1:]))
    store = JsonlStreamStore(args.spacebase_root.expanduser().resolve(), args.stream_id)
    store.ensure()

    if args.reset:
        reset_store(store)
        store.ensure()

    if not store.state_path.exists() or args.reset:
        store.save_state(ContinuousAgentState(current_prompt=args.initial_prompt))

    config_path = write_config(store)
    seed_event_id = append_seed_event(store, args.seed_text) if args.seed_text else None

    print(f"[init-continuous-stream] stream={store.stream_id}")
    print(f"[init-continuous-stream] root={store.root_dir}")
    print(f"[init-continuous-stream] events={store.events_path}")
    print(f"[init-continuous-stream] agents={store.agents_dir}")
    print(f"[init-continuous-stream] state={store.state_path}")
    print(f"[init-continuous-stream] config={config_path}")
    if seed_event_id:
        print(f"[init-continuous-stream] seed_event_id={seed_event_id}")
    print("[init-continuous-stream] listen: ./scripts/listen-continuous-stream.py --stream-id " + store.stream_id)
    print("[init-continuous-stream] run agents: ./scripts/run-continuous-agents.py --stream-id " + store.stream_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
