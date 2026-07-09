#!/usr/bin/env python3
"""Stream an OpenAI Responses API call into a local Blueprint JSONL stream."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from blueprint_core.continuous_agents import ContinuousAgentState, JsonlStreamStore
from blueprint_core.openai_streams import (
    DEFAULT_OPENAI_STREAM_MODEL,
    DEFAULT_OPENAI_STREAM_PROMPT,
    OpenAIResponsesStreamer,
    OpenAIStreamConfig,
    OpenAIStreamConfigError,
    OpenAIStreamEventWriter,
    OpenAIStreamRequestError,
)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT_DIR / ".env")
    parser.add_argument("--spacebase-root", type=Path, default=ROOT_DIR / ".spacebase")
    parser.add_argument("--stream-id", default="openai-local")
    parser.add_argument("--model", default=None, help=f"OpenAI model. Defaults to env or {DEFAULT_OPENAI_STREAM_MODEL}.")
    parser.add_argument("--base-url", default=None, help="OpenAI API base URL. Defaults to env or https://api.openai.com/v1.")
    parser.add_argument("--prompt", default=None, help=f"Prompt to send. Defaults to env or {DEFAULT_OPENAI_STREAM_PROMPT!r}.")
    parser.add_argument("--instructions", default=None)
    parser.add_argument("--timeout-seconds", type=float, default=None)
    parser.add_argument("--max-output-tokens", type=int, default=None)
    parser.add_argument("--reset", action="store_true", help="Clear stream events, agent outputs, and state before streaming.")
    parser.add_argument("--no-stdout", action="store_true", help="Do not print model text chunks as they arrive.")
    return parser.parse_args(argv)


def reset_store(store: JsonlStreamStore) -> None:
    store.ensure()
    store.events_path.write_text("", encoding="utf-8")
    if store.state_path.exists():
        store.state_path.unlink()
    for path in store.agents_dir.glob("*.jsonl"):
        path.unlink()
    store.save_state(ContinuousAgentState(current_prompt="Generate a precise Blueprint project output."))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv if argv is not None else sys.argv[1:]))
    try:
        config = OpenAIStreamConfig.from_env_file(
            args.env_file.expanduser(),
            model=args.model,
            base_url=args.base_url,
            prompt=args.prompt,
            timeout_seconds=args.timeout_seconds,
            max_output_tokens=args.max_output_tokens,
            instructions=args.instructions,
        )
        store = JsonlStreamStore(args.spacebase_root.expanduser().resolve(), args.stream_id)
        store.ensure()
        if args.reset:
            reset_store(store)

        streamer = OpenAIResponsesStreamer(config)
        writer = OpenAIStreamEventWriter(store)

        print(f"[openai-stream] stream={store.stream_id}", flush=True)
        print(f"[openai-stream] events={store.events_path}", flush=True)
        print(f"[openai-stream] model={config.model}", flush=True)
        print(f"[openai-stream] base_url={config.base_url}", flush=True)
        print("[openai-stream] starting", flush=True)

        event_count = 0
        text_parts: list[str] = []
        for chunk in streamer.stream_text():
            writer.append(chunk, model=config.model, base_url=config.base_url)
            event_count += 1
            if chunk.content:
                text_parts.append(chunk.content)
                if not args.no_stdout:
                    print(chunk.content, end="", flush=True)
            if chunk.error_message:
                print(f"\n[openai-stream] stream error event={chunk.response_event_type} error={chunk.error_message}", file=sys.stderr, flush=True)
        if text_parts and not args.no_stdout:
            print("", flush=True)
        print(f"[openai-stream] done events={event_count} chars={sum(len(part) for part in text_parts)}", flush=True)
        print(f"[openai-stream] listen=./scripts/listen-continuous-stream.py --stream-id {store.stream_id} --latest", flush=True)
        print(f"[openai-stream] agents=./scripts/run-continuous-agents.py --stream-id {store.stream_id}", flush=True)
        return 0
    except OpenAIStreamConfigError as exc:
        print(f"[openai-stream] config error: {exc}", file=sys.stderr)
        return 1
    except OpenAIStreamRequestError as exc:
        print(f"[openai-stream] request error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n[openai-stream] interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
