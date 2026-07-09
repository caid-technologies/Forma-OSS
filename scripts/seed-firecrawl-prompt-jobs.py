#!/usr/bin/env python3
"""Seed Firecrawl-backed prompt jobs and repair continuity issues."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from blueprint_core.continuous_agents import ContinuousAgentState, JsonlStreamStore
from blueprint_core.continuous_openai_jobs import ContinuousOpenAIJobMetadata, ContinuousOpenAIJobSpec, FirecrawlJobSourceUsage
from blueprint_core.openai_streams import load_env_file
from blueprint_core.prompt_continuity import (
    DEFAULT_CONTINUITY_ANCHOR,
    DEFAULT_PROMPT_BATCH_MAX_OUTPUT_TOKENS,
    DEFAULT_PROMPT_BATCH_MODEL,
    DEFAULT_PROMPT_BATCH_OBJECTIVE,
    FirecrawlPromptBatchSeeder,
    PromptSeed,
    default_prompt_seeds,
)


DEFAULT_BASETEN_BATCH_MODEL = "zai-org/GLM-5.2"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT_DIR / ".env")
    parser.add_argument("--spacebase-root", type=Path, default=ROOT_DIR / ".spacebase")
    parser.add_argument("--stream-id", default="firecrawl-prompt-batch")
    parser.add_argument("--model", default=DEFAULT_PROMPT_BATCH_MODEL)
    parser.add_argument("--prompt-count", type=int, default=10, help="Number of default OpenAI prompt seeds to enqueue.")
    parser.add_argument("--max-output-tokens", type=int, default=DEFAULT_PROMPT_BATCH_MAX_OUTPUT_TOKENS)
    parser.add_argument("--include-baseten-job", action="store_true", help="Append one Baseten job after the OpenAI prompt seeds.")
    parser.add_argument("--baseten-model", default=None)
    parser.add_argument("--baseten-max-output-tokens", type=int, default=None)
    parser.add_argument("--batch-id", default=None)
    parser.add_argument("--process-id", default=None)
    parser.add_argument("--objective", default=None)
    parser.add_argument("--continuity-anchor", default=None)
    parser.add_argument("--report-dir", type=Path, default=None)
    parser.add_argument("--no-report", action="store_true")
    parser.add_argument("--reset", action="store_true", help="Clear this stream before seeding jobs.")
    parser.add_argument("--require-firecrawl", action="store_true", help="Exit non-zero if Firecrawl was not configured or failed.")
    return parser.parse_args(argv)


def load_env_into_process(path: Path) -> None:
    if not path.exists():
        return
    for key, value in load_env_file(path.expanduser()).items():
        os.environ[key] = value


def reset_stream(store: JsonlStreamStore) -> None:
    store.ensure()
    for path in [
        store.events_path,
        store.stream_dir / "jobs.jsonl",
        store.stream_dir / "job-results.jsonl",
        store.state_path,
    ]:
        if path.exists():
            if path == store.state_path:
                path.unlink()
            else:
                path.write_text("", encoding="utf-8")
    if store.agents_dir.exists():
        for path in store.agents_dir.glob("*.jsonl"):
            path.unlink()
    store.save_state(ContinuousAgentState(current_prompt=""))


def source_context_from_firecrawl(usage: FirecrawlJobSourceUsage) -> str:
    if usage.records:
        blocks = []
        for index, record in enumerate(usage.records[:6], start=1):
            title = record.title or "Untitled source"
            url = record.url or "no-url"
            preview = record.content_preview.strip() or "No preview text."
            blocks.append(f"{index}. {title}\nURL: {url}\n{preview}")
        return "\n\n".join(blocks)
    if usage.error:
        return f"Firecrawl source lookup failed or was unavailable: {usage.error}"
    return "No Firecrawl source context was available; record this limitation explicitly."


def queued_prompt_context(seeds: tuple[PromptSeed, ...]) -> str:
    blocks = []
    for seed in seeds:
        blocks.append(
            f"{seed.index}. stage={seed.stage}\n"
            f"Prompt: {seed.prompt}\n"
            f"Source query: {seed.source_query}"
        )
    return "\n\n".join(blocks)


def baseten_prompt(
    *,
    continuity_anchor: str,
    batch_id: str,
    prompt_index: int,
    total_prompts: int,
    objective: str,
    source_context: str,
    prompt_context: str,
) -> str:
    return (
        f"Continuity contract for {continuity_anchor}:\n"
        f"- Batch: {batch_id} prompt {prompt_index} of {total_prompts}.\n"
        "- Stage: provider.baseten.\n"
        f"- Objective: {objective}.\n"
        "- Preserve decisions from earlier prompts in this batch unless you identify a clear contradiction.\n"
        "- Focus on continuity, missing interfaces, impossible claims, and prompt updates for the next iteration.\n\n"
        "- Keep the response concise for streaming review: target under 700 words.\n\n"
        f"Firecrawl source context:\n{source_context}\n\n"
        f"Queued prompt definitions:\n{prompt_context}\n\n"
        "Task:\n"
        "Review the queued GPT-5.5 prompt definitions and metadata before execution. Do not claim the model outputs are available yet. "
        "Return a concise engineering review with three sections: "
        "Summary, Continuity Risks, Prompt Updates."
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv if argv is not None else sys.argv[1:]))
    load_env_into_process(args.env_file)

    store = JsonlStreamStore(args.spacebase_root.expanduser().resolve(), args.stream_id)
    store.ensure()
    if args.reset:
        reset_stream(store)

    report_dir = None if args.no_report else (args.report_dir.expanduser().resolve() if args.report_dir else store.stream_dir / "prompt-batches")
    seeder = FirecrawlPromptBatchSeeder(
        store=store,
        model=args.model,
        max_output_tokens=args.max_output_tokens,
        objective=args.objective or DEFAULT_PROMPT_BATCH_OBJECTIVE,
        continuity_anchor=args.continuity_anchor or DEFAULT_CONTINUITY_ANCHOR,
    )
    seeds = default_prompt_seeds()
    if args.prompt_count < 1 or args.prompt_count > len(seeds):
        print(f"[seed-firecrawl-prompts] prompt-count must be between 1 and {len(seeds)}", file=sys.stderr)
        return 2
    selected_seeds = seeds[: args.prompt_count]
    report = seeder.seed_and_review(
        seeds=selected_seeds,
        batch_id=args.batch_id,
        process_id=args.process_id,
        write_report_dir=report_dir,
    )
    baseten_job = None
    if args.include_baseten_job:
        baseten_model = args.baseten_model or os.getenv("BASETEN_BLUEPRINT_MODEL") or os.getenv("BASETEN_MODEL") or DEFAULT_BASETEN_BATCH_MODEL
        total_prompts = len(selected_seeds) + 1
        source_context = source_context_from_firecrawl(report.firecrawl)
        metadata = ContinuousOpenAIJobMetadata(
            process_id=report.process_id,
            batch_id=report.batch_id,
            prompt_index=total_prompts,
            total_prompts=total_prompts,
            stage="provider.baseten",
            objective=args.objective or DEFAULT_PROMPT_BATCH_OBJECTIVE,
            continuity_anchor=args.continuity_anchor or DEFAULT_CONTINUITY_ANCHOR,
            source_queries=tuple(seed.source_query for seed in selected_seeds),
            source_context_preview=source_context[:2000],
            firecrawl=report.firecrawl,
        )
        baseten_job = ContinuousOpenAIJobSpec.create(
            provider="baseten",
            prompt=baseten_prompt(
                continuity_anchor=args.continuity_anchor or DEFAULT_CONTINUITY_ANCHOR,
                batch_id=report.batch_id,
                prompt_index=total_prompts,
                total_prompts=total_prompts,
                objective=args.objective or DEFAULT_PROMPT_BATCH_OBJECTIVE,
                source_context=source_context[:4000],
                prompt_context=queued_prompt_context(selected_seeds)[:2400],
            ),
            model=baseten_model,
            max_output_tokens=args.baseten_max_output_tokens or args.max_output_tokens,
            metadata=metadata,
            created_by="firecrawl-prompt-batch-seeder",
            reason="baseten continuity review job",
        )
        seeder.queue.append_job(baseten_job)

    queue = seeder.queue
    print(f"[seed-firecrawl-prompts] stream={store.stream_id}")
    print(f"[seed-firecrawl-prompts] jobs={queue.jobs_path}")
    print(f"[seed-firecrawl-prompts] results={queue.results_path}")
    print(f"[seed-firecrawl-prompts] batch_id={report.batch_id}")
    print(f"[seed-firecrawl-prompts] process_id={report.process_id}")
    print(f"[seed-firecrawl-prompts] model={report.model}")
    print(f"[seed-firecrawl-prompts] prompt_count={len(selected_seeds)}")
    print(f"[seed-firecrawl-prompts] max_output_tokens={args.max_output_tokens}")
    print(f"[seed-firecrawl-prompts] initial_jobs={report.initial_job_count}")
    print(f"[seed-firecrawl-prompts] repaired_jobs={report.repaired_job_count}")
    if baseten_job:
        print(f"[seed-firecrawl-prompts] baseten_job={baseten_job.job_id}")
        print(f"[seed-firecrawl-prompts] baseten_model={baseten_job.model}")
    print(
        "[seed-firecrawl-prompts] "
        f"firecrawl configured={report.firecrawl.configured} searches={report.firecrawl.searches_attempted} "
        f"sources={report.firecrawl.source_count}"
    )
    if report.firecrawl.error:
        print(f"[seed-firecrawl-prompts] firecrawl_error={report.firecrawl.error}")
    if report.report_path:
        print(f"[seed-firecrawl-prompts] report={report.report_path}")
    pending_hint = report.repaired_job_count + (1 if baseten_job else 0)
    print(f"[seed-firecrawl-prompts] queued_total={len(queue.jobs())} processed_or_superseded={len(queue.results())}")
    print(f"[seed-firecrawl-prompts] listen=./scripts/listen-continuous-stream.py --stream-id {store.stream_id} --latest")
    print(f"[seed-firecrawl-prompts] run=./scripts/run-continuous-llm-jobs.py --stream-id {store.stream_id} --model {report.model} --max-jobs {pending_hint}")

    if args.require_firecrawl and (not report.firecrawl.configured or report.firecrawl.error):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
