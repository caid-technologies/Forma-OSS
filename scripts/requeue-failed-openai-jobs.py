#!/usr/bin/env python3
"""Append concise retry/repair child jobs for a continuous job queue."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from blueprint_core.continuous_agents import JsonlStreamStore
from blueprint_core.continuous_openai_jobs import ContinuousOpenAIJobMetadata, ContinuousOpenAIJobQueue, ContinuousOpenAIJobResult, now_seconds
from blueprint_core.prompt_continuity import DEFAULT_PROMPT_BATCH_MAX_OUTPUT_TOKENS


LOG_PREFIX = "[requeue-llm-jobs]"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spacebase-root", type=Path, default=ROOT_DIR / ".spacebase")
    parser.add_argument("--stream-id", default="firecrawl-prompt-batch")
    parser.add_argument("--max-output-tokens", type=int, default=DEFAULT_PROMPT_BATCH_MAX_OUTPUT_TOKENS)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--include-superseded", action="store_true")
    parser.add_argument("--include-pending", action="store_true", help="Repair currently pending jobs as concise child jobs.")
    parser.add_argument("--supersede-pending", action="store_true", help="Mark repaired pending originals as superseded so the worker skips them.")
    parser.add_argument("--word-limit", type=int, default=900, help="Word target added to repaired prompts.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned repairs without appending jobs/results.")
    return parser.parse_args(argv)


def repair_prompt(prompt: str, *, word_limit: int) -> str:
    if "Keep the response concise for streaming review" in prompt:
        return prompt
    return (
        f"{prompt.rstrip()}\n\n"
        "Queue repair instruction:\n"
        f"- Keep the response concise for streaming review: target under {word_limit} words.\n"
        "- Prefer compact sections and short bullets over exhaustive tables.\n"
        "- If the previous attempt failed due max_output_tokens, summarize the most important decisions first."
    )


def repair_metadata(metadata: ContinuousOpenAIJobMetadata, *, reason: str, error_message: str = "") -> ContinuousOpenAIJobMetadata:
    repair_findings = tuple(
        item
        for item in [
            *metadata.continuity_findings,
            reason,
            error_message,
        ]
        if item
    )
    return ContinuousOpenAIJobMetadata(
        process_id=metadata.process_id,
        batch_id=metadata.batch_id,
        prompt_index=metadata.prompt_index,
        total_prompts=metadata.total_prompts,
        stage=metadata.stage,
        objective=metadata.objective,
        continuity_anchor=metadata.continuity_anchor,
        continuity_revision=metadata.continuity_revision + 1,
        continuity_findings=repair_findings,
        source_queries=metadata.source_queries,
        source_context_preview=metadata.source_context_preview,
        firecrawl=metadata.firecrawl,
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv if argv is not None else sys.argv[1:]))
    store = JsonlStreamStore(args.spacebase_root.expanduser().resolve(), args.stream_id)
    queue = ContinuousOpenAIJobQueue(store)
    queue.ensure()

    jobs_by_id = {job.job_id: job for job in queue.jobs()}
    already_retried_parent_ids = {
        job.parent_job_id
        for job in jobs_by_id.values()
        if job.parent_job_id and job.created_by in {"failed-job-retry", "queue-repair-agent"}
    }
    retry_count = 0

    def append_repair_child(job_id: str, *, status: str, error_message: str = "") -> str | None:
        nonlocal retry_count
        if job_id in already_retried_parent_ids:
            return None
        source_job = jobs_by_id.get(job_id)
        if source_job is None:
            return None
        metadata = repair_metadata(
            source_job.metadata,
            reason=f"repair_after_{status}",
            error_message=error_message,
        )
        retry_job = source_job.child(
            prompt=repair_prompt(source_job.prompt, word_limit=args.word_limit),
            created_by="queue-repair-agent",
            reason=f"concise repair after {status}: {error_message or 'no error message'}",
            metadata=metadata,
        )
        retry_job = replace(retry_job, max_output_tokens=args.max_output_tokens)
        retry_count += 1
        print(
            f"{LOG_PREFIX} "
            f"repair_job={retry_job.job_id} parent={job_id} provider={retry_job.provider} "
            f"model={retry_job.model} max_output_tokens={retry_job.max_output_tokens}"
            + (" dry_run=true" if args.dry_run else "")
        )
        if not args.dry_run:
            queue.append_job(retry_job)
        already_retried_parent_ids.add(job_id)
        return retry_job.job_id

    for result in queue.results():
        if result.status != "failed":
            if not args.include_superseded or result.status != "superseded":
                continue
        append_repair_child(result.job_id, status=result.status, error_message=result.error_message or "")
        if args.limit is not None and retry_count >= args.limit:
            break

    if args.include_pending and (args.limit is None or retry_count < args.limit):
        processed = queue.processed_job_ids()
        for job in queue.jobs():
            if job.job_id in processed:
                continue
            if job.created_by == "queue-repair-agent":
                continue
            repair_job_id = append_repair_child(job.job_id, status="pending", error_message="pending job repaired with concise prompt")
            if repair_job_id and not args.dry_run and args.supersede_pending:
                queue.append_result(
                    ContinuousOpenAIJobResult(
                        job_id=job.job_id,
                        status="superseded",
                        event_count=0,
                        character_count=0,
                        duration_seconds=0.0,
                        agent_output_names=("queue-repair-agent",),
                        provider=job.provider,
                        model=job.model,
                        child_job_id=repair_job_id,
                        completed_at_unix_seconds=now_seconds(),
                    )
                )
            if args.limit is not None and retry_count >= args.limit:
                break

    print(f"{LOG_PREFIX} stream={store.stream_id}")
    print(f"{LOG_PREFIX} added={retry_count}")
    print(f"{LOG_PREFIX} jobs={queue.jobs_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
