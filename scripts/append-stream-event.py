#!/usr/bin/env python3
"""Append a simple text event to a local Forma JSONL stream."""

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

from blueprint_core.continuous_agents import JsonlStreamStore


def now_ms() -> int:
    return int(time.time() * 1000)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("text", nargs="+", help="Text content to append to the stream.")
    parser.add_argument("--spacebase-root", type=Path, default=ROOT_DIR / ".spacebase")
    parser.add_argument("--stream-id", default="llama-cpp-local")
    parser.add_argument("--provider", default="manual")
    parser.add_argument("--model", default="manual-stream-event")
    parser.add_argument("--source-name", default="manual")
    parser.add_argument("--kind", default="llm.manual.chunk")
    parser.add_argument("--sequence", type=int, default=1)
    parser.add_argument("--not-done", action="store_true", help="Mark the event as an incomplete stream chunk.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv if argv is not None else sys.argv[1:]))
    store = JsonlStreamStore(args.spacebase_root.expanduser().resolve(), args.stream_id)
    store.ensure()

    text = " ".join(args.text)
    payload: dict[str, Any] = {
        "schema_version": 1,
        "event_id": f"manual-{uuid.uuid4().hex}",
        "observed_at_unix_ms": now_ms(),
        "kind": args.kind,
        "source": {
            "provider": args.provider,
            "source_type": "llm.stream",
            "name": args.source_name,
            "uri": None,
        },
        "payload": {
            "model": args.model,
            "sequence": args.sequence,
            "content": text,
            "done": not args.not_done,
        },
        "metadata": {
            "manual": True,
        },
    }
    with store.events_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")

    print(f"[append-stream-event] stream={store.stream_id}")
    print(f"[append-stream-event] event_id={payload['event_id']}")
    print(f"[append-stream-event] events={store.events_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
