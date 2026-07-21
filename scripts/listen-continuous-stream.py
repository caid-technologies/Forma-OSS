#!/usr/bin/env python3
"""Listen to a local Forma stream and its continuous-agent outputs."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from blueprint_core.continuous_agents import JsonlStreamStore
from blueprint_core.terminal_images import TerminalImageRenderConfig, extract_image_paths, render_images


@dataclass
class WatchedFile:
    label: str
    path: Path
    offset: int
    line_count: int


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spacebase-root", type=Path, default=ROOT_DIR / ".spacebase")
    parser.add_argument("--stream-id", default="llama-cpp-local")
    parser.add_argument("--from-start", action="store_true", help="Print existing JSONL rows before waiting for new ones.")
    parser.add_argument("--latest", action="store_true", help="Print the latest row from each watched file, then wait for new rows.")
    parser.add_argument("--poll-interval-seconds", type=float, default=0.5)
    parser.add_argument("--raw-json", action="store_true", help="Print each JSON object exactly as compact JSON.")
    parser.add_argument("--show-images", action="store_true", help="Render local image paths found in stream or agent JSON.")
    parser.add_argument("--image-width", type=int, default=None, help="Maximum terminal columns to use for rendered images.")
    parser.add_argument("--image-max-height", type=int, default=40, help="Maximum terminal rows to use per rendered image.")
    parser.add_argument("--max-lines", type=int, default=None, help="Stop after printing this many JSONL rows.")
    return parser.parse_args(argv)


def initial_offset(path: Path, *, from_start: bool) -> int:
    if from_start or not path.exists():
        return 0
    return path.stat().st_size


def line_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def latest_line(path: Path) -> str | None:
    if not path.exists():
        return None
    latest = None
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                latest = line
    return latest


def event_summary(value: dict[str, Any]) -> str:
    payload = value.get("payload") if isinstance(value.get("payload"), dict) else {}
    source = value.get("source") if isinstance(value.get("source"), dict) else {}
    content = str(payload.get("content") or "")
    preview = content.replace("\n", "\\n")[:180]
    done = payload.get("done")
    model = payload.get("model") or source.get("name") or "unknown-model"
    event_id = value.get("event_id") or "no-event-id"
    kind = value.get("kind") or "event"
    return f"[stream:event] kind={kind} id={event_id} model={model} done={done} content={preview!r}"


def agent_summary(value: dict[str, Any], *, label: str) -> str:
    payload = value.get("payload") if isinstance(value.get("payload"), dict) else {}
    kind = value.get("kind") or "agent.output"
    agent_name = value.get("agent_name") or label
    if kind == "agent.reader.batch":
        return (
            f"[agent:{agent_name}] kind={kind} events={payload.get('event_count')} "
            f"done={payload.get('done_count')} preview={str(payload.get('text_preview') or '')[:180]!r}"
        )
    if kind == "agent.writer.summary":
        return (
            f"[agent:{agent_name}] kind={kind} received={payload.get('received_events')} "
            f"completed={payload.get('completed')} last={str(payload.get('last_content') or '')[:180]!r}"
        )
    if kind == "agent.reviewer.findings":
        findings = payload.get("findings") if isinstance(payload.get("findings"), list) else []
        codes = ", ".join(str(item.get("code") or "finding") for item in findings if isinstance(item, dict))
        return f"[agent:{agent_name}] kind={kind} events={payload.get('event_count')} findings={len(findings)} codes={codes or 'none'}"
    if kind == "agent.prompt_iteration.proposal":
        return (
            f"[agent:{agent_name}] kind={kind} revision={payload.get('revision')} "
            f"reason={str(payload.get('reason') or '')[:180]!r}"
        )
    return f"[agent:{agent_name}] kind={kind} payload_keys={sorted(payload.keys())}"


def job_summary(value: dict[str, Any]) -> str:
    job_id = value.get("job_id") or "no-job-id"
    provider = value.get("provider") or "unknown"
    model = value.get("model") or "unknown-model"
    generation = value.get("generation")
    parent_job_id = value.get("parent_job_id")
    clone_of_job_id = value.get("clone_of_job_id")
    prompt = str(value.get("prompt") or "").replace("\n", "\\n")[:180]
    return (
        f"[job:queued] id={job_id} provider={provider} model={model} generation={generation} "
        f"parent={parent_job_id or 'none'} clone_of={clone_of_job_id or 'none'} prompt={prompt!r}"
    )


def compact_error_message(value: Any) -> str:
    raw = str(value or "")
    if not raw:
        return ""
    stripped = raw.strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return stripped[:220]
    if isinstance(parsed, dict):
        reason = parsed.get("reason")
        if reason == "max_output_tokens":
            return "max_output_tokens: increase job max_output_tokens or make the prompt more concise"
        if reason:
            return f"reason={reason}"
    return stripped[:220]


def job_result_summary(value: dict[str, Any]) -> str:
    job_id = value.get("job_id") or "no-job-id"
    status = value.get("status") or "unknown"
    provider = value.get("provider") or "unknown"
    model = value.get("model") or "unknown-model"
    child_job_id = value.get("child_job_id")
    agents = ", ".join(str(item) for item in value.get("agent_output_names", []) if item) or "none"
    error = compact_error_message(value.get("error_message"))
    return (
        f"[job:result] id={job_id} status={status} provider={provider} model={model} events={value.get('event_count')} "
        f"chars={value.get('character_count')} child={child_job_id or 'none'} agents={agents}"
        + (f" error={error!r}" if error else "")
    )


def parse_json_line(label: str, line: str) -> tuple[dict[str, Any] | None, str | None]:
    stripped = line.strip()
    if not stripped:
        return None, None
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError as exc:
        return None, f"[{label}] invalid-json error={exc} raw={stripped[:240]!r}"
    return value, None


def format_parsed_line(label: str, value: dict[str, Any], *, raw_json: bool) -> str:
    if raw_json:
        return json.dumps(value, sort_keys=True)
    if label == "events":
        return event_summary(value)
    if label == "jobs":
        return job_summary(value)
    if label == "job-results":
        return job_result_summary(value)
    return agent_summary(value, label=label)


def discover_files(store: JsonlStreamStore, watched: dict[Path, WatchedFile], *, from_start: bool) -> list[WatchedFile]:
    discovered: list[WatchedFile] = []
    candidates = [
        ("jobs", store.stream_dir / "jobs.jsonl"),
        ("job-results", store.stream_dir / "job-results.jsonl"),
        ("events", store.events_path),
    ]
    candidates.extend((path.stem, path) for path in sorted(store.agents_dir.glob("*.jsonl")))
    for label, path in candidates:
        if path in watched:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.touch()
        existing_lines = line_count(path)
        watched_file = WatchedFile(label=label, path=path, offset=initial_offset(path, from_start=from_start), line_count=existing_lines)
        watched[path] = watched_file
        discovered.append(watched_file)
        note = ""
        if not from_start and existing_lines:
            note = " tailing_new_rows_only"
        print(f"[listen-continuous-stream] watching {label}={path} lines={existing_lines}{note}", flush=True)
    return discovered


def read_new_lines(watched_file: WatchedFile) -> list[str]:
    lines: list[str] = []
    if not watched_file.path.exists():
        return lines
    with watched_file.path.open("r", encoding="utf-8") as handle:
        handle.seek(watched_file.offset)
        for line in handle:
            lines.append(line)
        watched_file.offset = handle.tell()
    return lines


def print_line(
    watched_file: WatchedFile,
    line: str,
    *,
    raw_json: bool,
    show_images: bool,
    image_config: TerminalImageRenderConfig,
) -> bool:
    parsed, parse_error = parse_json_line(watched_file.label, line)
    formatted = parse_error or (format_parsed_line(watched_file.label, parsed, raw_json=raw_json) if parsed else "")
    if not formatted:
        return False
    print(formatted, flush=True)
    if show_images and parsed:
        image_paths = extract_image_paths(parsed, base_dir=ROOT_DIR)
        if image_paths:
            print(render_images(image_paths, image_config), flush=True)
    return True


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv if argv is not None else sys.argv[1:]))
    store = JsonlStreamStore(args.spacebase_root.expanduser().resolve(), args.stream_id)
    store.ensure()

    print(f"[listen-continuous-stream] stream={store.stream_id}", flush=True)
    print(f"[listen-continuous-stream] root={store.root_dir}", flush=True)
    mode = "from-start" if args.from_start else ("latest" if args.latest else "tail")
    print(f"[listen-continuous-stream] mode={mode}", flush=True)
    if not args.from_start and not args.latest:
        print("[listen-continuous-stream] tail mode waits for new rows only; use --from-start or --latest to print existing rows.", flush=True)
    if args.show_images:
        print("[listen-continuous-stream] images=enabled", flush=True)

    watched: dict[Path, WatchedFile] = {}
    image_config = TerminalImageRenderConfig(width=args.image_width, max_height=args.image_max_height)
    printed = 0
    try:
        while True:
            discovered = discover_files(store, watched, from_start=args.from_start)
            if args.latest and not args.from_start:
                for watched_file in discovered:
                    line = latest_line(watched_file.path)
                    if line and print_line(
                        watched_file,
                        line,
                        raw_json=args.raw_json,
                        show_images=args.show_images,
                        image_config=image_config,
                    ):
                        printed += 1
                        if args.max_lines is not None and printed >= args.max_lines:
                            return 0
            for watched_file in list(watched.values()):
                for line in read_new_lines(watched_file):
                    if print_line(
                        watched_file,
                        line,
                        raw_json=args.raw_json,
                        show_images=args.show_images,
                        image_config=image_config,
                    ):
                        printed += 1
                        if args.max_lines is not None and printed >= args.max_lines:
                            return 0
            time.sleep(args.poll_interval_seconds)
    except KeyboardInterrupt:
        print("[listen-continuous-stream] stopped", flush=True)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
