#!/usr/bin/env python3
"""Listen for queued LLM provider jobs, stream them to JSONL, and run agents."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from blueprint_core.continuous_agents import ContinuousAgentState, JsonlStreamStore
from blueprint_core.continuous_openai_jobs import ContinuousOpenAIJobReport, ContinuousOpenAIJobRunner, ContinuousOpenAIJobSpec
from blueprint_core.openai_streams import (
    DEFAULT_OPENAI_STREAM_MODEL,
    DEFAULT_OPENAI_STREAM_PROMPT,
    OpenAIStreamConfig,
    OpenAIStreamConfigError,
    load_env_file,
)
from blueprint_core.providers import normalize_provider_name


LOG_PREFIX = "[continuous-llm]"
ENQUEUE_COMMAND = "./scripts/enqueue-llm-job.py"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT_DIR / ".env")
    parser.add_argument("--spacebase-root", type=Path, default=ROOT_DIR / ".spacebase")
    parser.add_argument("--stream-id", default="openai-loop")
    parser.add_argument("--provider", default="openai", help="Provider for --enqueue-initial-job. Queued jobs keep their own provider.")
    parser.add_argument("--model", default=None, help=f"Default/fallback model. Queued jobs keep their own model. Defaults to env or {DEFAULT_OPENAI_STREAM_MODEL}.")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--prompt", default=None, help=f"Prompt to enqueue with --enqueue-initial-job. Defaults to env or {DEFAULT_OPENAI_STREAM_PROMPT!r}.")
    parser.add_argument("--instructions", default=None)
    parser.add_argument("--timeout-seconds", type=float, default=None)
    parser.add_argument("--max-output-tokens", type=int, default=None)
    parser.add_argument("--sleep-seconds", type=float, default=5.0, help="Delay between jobs when running continuously.")
    parser.add_argument("--max-jobs", type=int, default=None, help="Stop after processing this many queued LLM jobs. Omit to run continuously.")
    parser.add_argument("--once", action="store_true", help="Equivalent to --max-jobs 1.")
    parser.add_argument("--wait-for-jobs", action="store_true", help="When --max-jobs/--once is set, wait for future jobs instead of exiting on an empty queue.")
    parser.add_argument("--enqueue-initial-job", action="store_true", help="Append one job from --prompt before listening.")
    parser.add_argument("--clone-on-pass", action="store_true", help="After a successful review with no corrections, enqueue a cloned child job.")
    parser.add_argument("--no-iterate-on-findings", action="store_true", help="Do not enqueue prompt-iterator child jobs when the reviewer finds issues.")
    parser.add_argument("--idle-log-every-cycles", type=int, default=10)
    parser.add_argument("--continue-on-error", action="store_true", help="Keep processing queued jobs after provider request failures.")
    parser.add_argument("--reset", action="store_true", help="Clear stream events, agent outputs, and state before starting.")
    parser.add_argument("--image", action="append", type=Path, default=[], help="Image path for the reviewer to inspect. Can be repeated.")
    parser.add_argument("--video", action="append", type=Path, default=[], help="Video path for the reviewer to inspect. Can be repeated.")
    parser.add_argument("--no-stdout", action="store_true", help="Do not print streamed model text chunks.")
    return parser.parse_args(argv)


def reset_store(store: JsonlStreamStore, *, initial_prompt: str) -> None:
    store.ensure()
    store.events_path.write_text("", encoding="utf-8")
    for path in [store.stream_dir / "jobs.jsonl", store.stream_dir / "job-results.jsonl"]:
        if path.exists():
            path.write_text("", encoding="utf-8")
    if store.state_path.exists():
        store.state_path.unlink()
    for path in store.agents_dir.glob("*.jsonl"):
        path.unlink()
    store.save_state(ContinuousAgentState(current_prompt=initial_prompt))


def load_env_into_process(path: Path) -> None:
    if not path.exists():
        return
    for key, value in load_env_file(path.expanduser()).items():
        os.environ[key] = value


def print_job_report(report: ContinuousOpenAIJobReport) -> None:
    status = "FAIL" if report.error_message else "PASS"
    agents = ", ".join(report.agent_report.output_agent_names) or "none"
    print(
        f"{LOG_PREFIX} "
        f"{status} job={report.job_index} job_id={report.job_id} "
        f"provider={report.provider} model={report.model} "
        f"events={report.event_count} chars={report.character_count} "
        f"duration={report.duration_seconds:.1f}s prompt_revision={report.prompt_revision} "
        f"agent_events={report.agent_report.new_event_count} "
        f"agent_outputs={report.agent_report.output_count} agents={agents}",
        flush=True,
    )
    if report.error_message:
        print(f"{LOG_PREFIX} error={report.error_message}", file=sys.stderr, flush=True)


def pending_job_count(runner: ContinuousOpenAIJobRunner) -> int:
    processed = runner.queue.processed_job_ids()
    return sum(1 for job in runner.queue.jobs() if job.job_id not in processed)


def next_pending_job(runner: ContinuousOpenAIJobRunner) -> ContinuousOpenAIJobSpec | None:
    processed = runner.queue.processed_job_ids()
    for job in runner.queue.jobs():
        if job.job_id not in processed:
            return job
    return None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv if argv is not None else sys.argv[1:]))
    max_jobs = 1 if args.once else args.max_jobs

    try:
        load_env_into_process(args.env_file)
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
            reset_store(store, initial_prompt=config.prompt)
        elif not store.state_path.exists():
            store.save_state(ContinuousAgentState(current_prompt=config.prompt))

        runner = ContinuousOpenAIJobRunner(
            store=store,
            config=config,
            env_file=args.env_file.expanduser(),
            image_paths=[path.expanduser().resolve() for path in args.image],
            video_paths=[path.expanduser().resolve() for path in args.video],
            sleep_seconds=args.sleep_seconds,
        )
        if args.enqueue_initial_job:
            initial_job = ContinuousOpenAIJobSpec.create(
                prompt=config.prompt,
                model=config.model,
                provider=normalize_provider_name(args.provider),
                instructions=config.instructions,
                max_output_tokens=config.max_output_tokens,
                created_by=Path(sys.argv[0]).name,
                reason="initial job enqueued from CLI",
            )
            runner.queue.append_job(initial_job)

        queued_jobs = len(runner.queue.jobs())
        processed_jobs = len(runner.queue.results())
        pending_jobs = pending_job_count(runner)
        print(f"{LOG_PREFIX} stream={store.stream_id}", flush=True)
        print(f"{LOG_PREFIX} events={store.events_path}", flush=True)
        print(f"{LOG_PREFIX} jobs={runner.queue.jobs_path}", flush=True)
        print(f"{LOG_PREFIX} results={runner.queue.results_path}", flush=True)
        print(f"{LOG_PREFIX} agents={store.agents_dir}", flush=True)
        print(f"{LOG_PREFIX} enqueue_default_provider={normalize_provider_name(args.provider)}", flush=True)
        print(f"{LOG_PREFIX} fallback_model={config.model}", flush=True)
        print(f"{LOG_PREFIX} mode={'bounded-queue' if max_jobs is not None else 'continuous-queue'}", flush=True)
        print(f"{LOG_PREFIX} max_jobs={max_jobs if max_jobs is not None else 'unbounded'}", flush=True)
        print(f"{LOG_PREFIX} queued_jobs={queued_jobs} processed_jobs={processed_jobs} pending_jobs={pending_jobs}", flush=True)
        print(f"{LOG_PREFIX} listen=./scripts/listen-continuous-stream.py --stream-id {store.stream_id} --latest", flush=True)
        if args.enqueue_initial_job:
            print(f"{LOG_PREFIX} enqueued_initial_job={initial_job.job_id}", flush=True)
        else:
            hint_job = next_pending_job(runner)
            hint_provider = hint_job.provider if hint_job else normalize_provider_name(args.provider)
            hint_model = hint_job.model if hint_job else (args.model or config.model)
            print(
                f"{LOG_PREFIX} waiting for jobs; enqueue with "
                f"{ENQUEUE_COMMAND} --stream-id {store.stream_id} --provider {hint_provider} --model {hint_model} 'your prompt'",
                flush=True,
            )

        def on_chunk(chunk: object) -> None:
            content = getattr(chunk, "content", "")
            if content and not args.no_stdout:
                print(content, end="", flush=True)

        def on_job(report: ContinuousOpenAIJobReport) -> None:
            if not args.no_stdout and report.character_count:
                print("", flush=True)
            print_job_report(report)

        idle_cycles = 0

        def on_idle() -> None:
            nonlocal idle_cycles
            idle_cycles += 1
            if args.idle_log_every_cycles > 0 and (idle_cycles == 1 or idle_cycles % args.idle_log_every_cycles == 0):
                print(f"{LOG_PREFIX} idle waiting_for_jobs cycle={idle_cycles} pending_jobs={pending_job_count(runner)}", flush=True)

        if max_jobs is not None and pending_jobs == 0 and not args.wait_for_jobs:
            on_idle()
            print(f"{LOG_PREFIX} empty queue for bounded run; exiting. Use --wait-for-jobs to keep listening.", flush=True)
            print(f"{LOG_PREFIX} stopped", flush=True)
            return 0

        runner.run_queue(
            max_jobs=max_jobs,
            continue_on_error=args.continue_on_error,
            iterate_on_findings=not args.no_iterate_on_findings,
            clone_on_pass=args.clone_on_pass,
            on_chunk=on_chunk,
            on_job=on_job,
            on_idle=on_idle,
        )
        print(f"{LOG_PREFIX} stopped", flush=True)
        return 0
    except OpenAIStreamConfigError as exc:
        print(f"{LOG_PREFIX} config error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(f"\n{LOG_PREFIX} interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
