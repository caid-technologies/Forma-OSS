#!/usr/bin/env python3
"""Append an LLM job object to a Blueprint continuous stream queue."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from blueprint_core.continuous_agents import JsonlStreamStore
from blueprint_core.continuous_openai_jobs import ContinuousOpenAIJobQueue, ContinuousOpenAIJobSpec
from blueprint_core.openai_streams import DEFAULT_OPENAI_STREAM_MODEL, DEFAULT_OPENAI_STREAM_PROMPT


LOG_PREFIX = "[enqueue-llm-job]"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", nargs="*", help="Prompt text for the job.")
    parser.add_argument("--spacebase-root", type=Path, default=ROOT_DIR / ".spacebase")
    parser.add_argument("--stream-id", default="openai-loop")
    parser.add_argument("--provider", default="openai", help="Provider name, for example openai or baseten.")
    parser.add_argument("--model", default=DEFAULT_OPENAI_STREAM_MODEL)
    parser.add_argument("--instructions", default=None)
    parser.add_argument("--max-output-tokens", type=int, default=None)
    parser.add_argument("--parent-job-id", default=None)
    parser.add_argument("--clone-of-job-id", default=None)
    parser.add_argument("--generation", type=int, default=0)
    parser.add_argument("--created-by", default="manual")
    parser.add_argument("--reason", default="manual enqueue")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv if argv is not None else sys.argv[1:]))
    prompt = " ".join(args.prompt).strip() or DEFAULT_OPENAI_STREAM_PROMPT

    store = JsonlStreamStore(args.spacebase_root.expanduser().resolve(), args.stream_id)
    queue = ContinuousOpenAIJobQueue(store)
    queue.ensure()
    job = ContinuousOpenAIJobSpec.create(
        prompt=prompt,
        model=args.model,
        provider=args.provider,
        instructions=args.instructions,
        max_output_tokens=args.max_output_tokens,
        parent_job_id=args.parent_job_id,
        clone_of_job_id=args.clone_of_job_id,
        generation=args.generation,
        created_by=args.created_by,
        reason=args.reason,
    )
    queue.append_job(job)

    print(f"{LOG_PREFIX} stream={store.stream_id}")
    print(f"{LOG_PREFIX} job_id={job.job_id}")
    print(f"{LOG_PREFIX} provider={job.provider}")
    print(f"{LOG_PREFIX} model={job.model}")
    print(f"{LOG_PREFIX} jobs={queue.jobs_path}")
    print(f"{LOG_PREFIX} prompt={job.prompt[:240]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
