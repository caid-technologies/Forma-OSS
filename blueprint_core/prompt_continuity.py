from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from blueprint_core.agents.firecrawl_mcp import FirecrawlMCPResearchClient, FirecrawlResearchResult
from blueprint_core.continuous_agents import JsonlStreamStore
from blueprint_core.continuous_openai_jobs import (
    ContinuousOpenAIJobMetadata,
    ContinuousOpenAIJobQueue,
    ContinuousOpenAIJobResult,
    ContinuousOpenAIJobSpec,
    FirecrawlJobSourceRecord,
    FirecrawlJobSourceUsage,
)


DEFAULT_PROMPT_BATCH_MODEL = "gpt-5.5"
DEFAULT_PROMPT_BATCH_MAX_OUTPUT_TOKENS = 1600
DEFAULT_PROMPT_BATCH_OBJECTIVE = (
    "Iterate a buildable blue electromechanical desktop environmental monitor while preserving continuity across design, "
    "electrical, mechanical, firmware, visual, test, and manufacturing decisions."
)
DEFAULT_CONTINUITY_ANCHOR = "Blue Sentinel desktop environmental monitor"


@dataclass(frozen=True)
class PromptSeed:
    index: int
    stage: str
    prompt: str
    source_query: str


@dataclass(frozen=True)
class PromptContinuityFinding:
    severity: str
    code: str
    message: str

    def to_dict(self) -> dict[str, object]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }


@dataclass(frozen=True)
class PromptContinuityReview:
    job_id: str
    prompt_index: Optional[int]
    passed: bool
    findings: tuple[PromptContinuityFinding, ...]
    revised_prompt: str
    child_job_id: Optional[str] = None

    def to_dict(self) -> dict[str, object]:
        return {
            "job_id": self.job_id,
            "prompt_index": self.prompt_index,
            "passed": self.passed,
            "findings": [finding.to_dict() for finding in self.findings],
            "revised_prompt": self.revised_prompt,
            "child_job_id": self.child_job_id,
        }


@dataclass(frozen=True)
class PromptBatchReport:
    process_id: str
    batch_id: str
    stream_id: str
    model: str
    initial_job_count: int
    repaired_job_count: int
    firecrawl: FirecrawlJobSourceUsage
    reviews: tuple[PromptContinuityReview, ...]
    report_path: Optional[Path] = None

    def to_dict(self) -> dict[str, object]:
        return {
            "process_id": self.process_id,
            "batch_id": self.batch_id,
            "stream_id": self.stream_id,
            "model": self.model,
            "initial_job_count": self.initial_job_count,
            "repaired_job_count": self.repaired_job_count,
            "firecrawl": self.firecrawl.to_dict(),
            "reviews": [review.to_dict() for review in self.reviews],
            "report_path": str(self.report_path) if self.report_path else None,
        }


def default_prompt_seeds() -> tuple[PromptSeed, ...]:
    project = DEFAULT_CONTINUITY_ANCHOR
    return (
        PromptSeed(
            1,
            "product.overview",
            f"Define the product promise for {project}: user, environment, main functions, constraints, and success criteria.",
            "desktop environmental monitor electromechanical product requirements sensors display battery",
        ),
        PromptSeed(
            2,
            "product.electrical",
            f"Choose the electrical architecture for {project}: MCU, sensor buses, power tree, protection, connectors, and test points.",
            "environmental monitor MCU sensor bus power tree USB-C battery charger design",
        ),
        PromptSeed(
            3,
            "product.mech",
            f"Design the enclosure and internal layout for {project}: blue housing, vents, sensor exposure, display window, fasteners, and service access.",
            "electronics enclosure design vents sensor exposure display window fasteners",
        ),
        PromptSeed(
            4,
            "product.firmware",
            f"Plan firmware for {project}: sampling loop, calibration, display states, data logging, alarms, and low-power behavior.",
            "environmental sensor firmware calibration display states data logging alarms",
        ),
        PromptSeed(
            5,
            "project.docs",
            f"Write assembly documentation for {project}: ordered build steps, wire harness notes, calibration, safety checks, and acceptance tests.",
            "electronics assembly documentation calibration acceptance test checklist",
        ),
        PromptSeed(
            6,
            "product.visual",
            f"Describe a generated product image for {project}: blue finish, visible display, vents, sensor openings, scale, and realistic tabletop context.",
            "product render prompt blue electronics enclosure sensor display tabletop",
        ),
        PromptSeed(
            7,
            "project.validation",
            f"Create a validation plan for {project}: electrical tests, mechanical fit checks, sensor accuracy, thermal behavior, and battery runtime.",
            "hardware validation plan sensor accuracy battery runtime mechanical fit electrical test",
        ),
        PromptSeed(
            8,
            "project.manufacturing",
            f"Prepare manufacturing notes for {project}: BOM risks, sourcing substitutions, enclosure fabrication, QA gates, and packaging.",
            "small electronics manufacturing notes BOM risk sourcing enclosure fabrication QA",
        ),
        PromptSeed(
            9,
            "project.iteration",
            f"Review all prior {project} design outputs and identify contradictions, missing interfaces, untestable claims, and prompt updates.",
            "engineering design review continuity contradictions interface checks prompt iteration",
        ),
        PromptSeed(
            10,
            "project.release",
            f"Produce a release-ready project summary for {project}: final spec, namespace checklist, known risks, and next iteration backlog.",
            "hardware project release checklist known risks next iteration backlog",
        ),
    )


def firecrawl_usage_from_result(result: FirecrawlResearchResult) -> FirecrawlJobSourceUsage:
    records = tuple(
        FirecrawlJobSourceRecord(
            title=hit.title,
            url=hit.url,
            content_preview=hit.content[:360],
        )
        for hit in result.hits[:12]
    )
    return FirecrawlJobSourceUsage(
        configured=result.configured,
        searches_attempted=result.searches_attempted,
        source_count=len(result.hits),
        tool_name=result.tool_name or "",
        error=result.error or "",
        records=records,
    )


class PromptContinuityReviewer:
    def __init__(self, *, required_anchor: str = DEFAULT_CONTINUITY_ANCHOR) -> None:
        self.required_anchor = required_anchor

    def review(self, job: ContinuousOpenAIJobSpec) -> PromptContinuityReview:
        metadata = job.metadata
        findings: list[PromptContinuityFinding] = []
        prompt_lower = job.prompt.lower()
        anchor_lower = (metadata.continuity_anchor or self.required_anchor).lower()

        if job.model != DEFAULT_PROMPT_BATCH_MODEL:
            findings.append(PromptContinuityFinding("error", "wrong_model", f"Expected {DEFAULT_PROMPT_BATCH_MODEL}, got {job.model}."))
        if not metadata.batch_id:
            findings.append(PromptContinuityFinding("error", "missing_batch_id", "Job metadata is missing batch_id."))
        if metadata.prompt_index is None:
            findings.append(PromptContinuityFinding("error", "missing_prompt_index", "Job metadata is missing prompt_index."))
        if not metadata.stage:
            findings.append(PromptContinuityFinding("warning", "missing_stage", "Job metadata is missing stage/namespace."))
        if anchor_lower and anchor_lower not in prompt_lower:
            findings.append(PromptContinuityFinding("warning", "missing_anchor", "Prompt does not name the continuity anchor."))
        if "continuity contract" not in prompt_lower:
            findings.append(PromptContinuityFinding("warning", "missing_continuity_contract", "Prompt does not include an explicit continuity contract."))
        if "firecrawl source context" not in prompt_lower:
            findings.append(PromptContinuityFinding("warning", "missing_firecrawl_context", "Prompt does not include Firecrawl source context."))
        if metadata.firecrawl is None:
            findings.append(PromptContinuityFinding("warning", "missing_firecrawl_metadata", "Job metadata has no Firecrawl source usage object."))
        elif not metadata.firecrawl.configured:
            findings.append(PromptContinuityFinding("warning", "firecrawl_unconfigured", metadata.firecrawl.error or "Firecrawl was not configured."))
        if metadata.prompt_index and metadata.prompt_index > 1 and "preserve decisions from earlier prompts" not in prompt_lower:
            findings.append(PromptContinuityFinding("warning", "missing_previous_decisions_clause", "Prompt does not instruct the model to preserve earlier decisions."))

        revised_prompt = job.prompt if not findings else self.revised_prompt(job, tuple(findings))
        return PromptContinuityReview(
            job_id=job.job_id,
            prompt_index=metadata.prompt_index,
            passed=not findings,
            findings=tuple(findings),
            revised_prompt=revised_prompt,
        )

    def revised_prompt(self, job: ContinuousOpenAIJobSpec, findings: tuple[PromptContinuityFinding, ...]) -> str:
        metadata = job.metadata
        source_context = metadata.source_context_preview or "No Firecrawl source context was available; explicitly record that limitation."
        finding_text = "\n".join(f"- {finding.code}: {finding.message}" for finding in findings)
        previous_clause = "Preserve decisions from earlier prompts in this batch unless a reviewer finding explicitly requires changing them."
        return (
            f"Continuity contract for {metadata.continuity_anchor or self.required_anchor}:\n"
            f"- Batch: {metadata.batch_id or 'unknown'} prompt {metadata.prompt_index or '?'} of {metadata.total_prompts or '?'}.\n"
            f"- Stage: {metadata.stage or 'unknown'}.\n"
            f"- Objective: {metadata.objective or DEFAULT_PROMPT_BATCH_OBJECTIVE}.\n"
            f"- {previous_clause}\n"
            "- Keep names, interfaces, power assumptions, enclosure constraints, and validation criteria consistent across jobs.\n"
            "- Keep the response concise for streaming review: target under 900 words and avoid exhaustive tables unless essential.\n"
            "- If information is unavailable, say what is missing instead of inventing contradictory details.\n\n"
            f"Firecrawl source context:\n{source_context}\n\n"
            f"Continuity reviewer findings to fix:\n{finding_text}\n\n"
            f"Original prompt:\n{job.prompt}"
        )


class FirecrawlPromptBatchSeeder:
    def __init__(
        self,
        *,
        store: JsonlStreamStore,
        model: str = DEFAULT_PROMPT_BATCH_MODEL,
        max_output_tokens: int = DEFAULT_PROMPT_BATCH_MAX_OUTPUT_TOKENS,
        objective: str = DEFAULT_PROMPT_BATCH_OBJECTIVE,
        continuity_anchor: str = DEFAULT_CONTINUITY_ANCHOR,
        firecrawl_client: Optional[FirecrawlMCPResearchClient] = None,
    ) -> None:
        self.store = store
        self.queue = ContinuousOpenAIJobQueue(store)
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.objective = objective
        self.continuity_anchor = continuity_anchor
        self.firecrawl_client = firecrawl_client or FirecrawlMCPResearchClient()
        self.reviewer = PromptContinuityReviewer(required_anchor=continuity_anchor)

    def seed_and_review(
        self,
        *,
        seeds: Iterable[PromptSeed] | None = None,
        batch_id: Optional[str] = None,
        process_id: Optional[str] = None,
        write_report_dir: Optional[Path] = None,
    ) -> PromptBatchReport:
        prompt_seeds = tuple(seeds or default_prompt_seeds())
        resolved_batch_id = batch_id or f"prompt-batch-{uuid.uuid4().hex}"
        resolved_process_id = process_id or f"process-{uuid.uuid4().hex}"
        self.queue.ensure()

        firecrawl_result = self.firecrawl_client.research(seed.source_query for seed in prompt_seeds)
        firecrawl_usage = firecrawl_usage_from_result(firecrawl_result)
        source_context = firecrawl_result.as_prompt_context(max_chars=4000)
        source_queries = tuple(seed.source_query for seed in prompt_seeds)

        initial_jobs: list[ContinuousOpenAIJobSpec] = []
        reviews: list[PromptContinuityReview] = []
        repaired_count = 0

        for seed in prompt_seeds:
            metadata = ContinuousOpenAIJobMetadata(
                process_id=resolved_process_id,
                batch_id=resolved_batch_id,
                prompt_index=seed.index,
                total_prompts=len(prompt_seeds),
                stage=seed.stage,
                objective=self.objective,
                continuity_anchor=self.continuity_anchor,
                source_queries=source_queries,
                source_context_preview=source_context[:2000],
                firecrawl=firecrawl_usage,
            )
            job = ContinuousOpenAIJobSpec.create(
                prompt=seed.prompt,
                model=self.model,
                max_output_tokens=self.max_output_tokens,
                metadata=metadata,
                created_by="firecrawl-prompt-batch-seeder",
                reason="initial prompt batch",
            )
            self.queue.append_job(job)
            initial_jobs.append(job)

            review = self.reviewer.review(job)
            child_job_id = None
            if not review.passed:
                finding_codes = tuple(finding.code for finding in review.findings)
                child_metadata = metadata.with_review(finding_codes, source_context_preview=source_context[:2000])
                child = job.child(
                    prompt=review.revised_prompt,
                    created_by="prompt-continuity-reviewer",
                    reason="continuity reviewer repaired prompt before execution",
                    metadata=child_metadata,
                )
                self.queue.append_job(child)
                child_job_id = child.job_id
                self.queue.append_result(
                    ContinuousOpenAIJobResult(
                        job_id=job.job_id,
                        status="superseded",
                        event_count=0,
                        character_count=0,
                        duration_seconds=0.0,
                        agent_output_names=("prompt-continuity-reviewer",),
                        child_job_id=child.job_id,
                    )
                )
                repaired_count += 1
            reviews.append(
                PromptContinuityReview(
                    job_id=review.job_id,
                    prompt_index=review.prompt_index,
                    passed=review.passed,
                    findings=review.findings,
                    revised_prompt=review.revised_prompt,
                    child_job_id=child_job_id,
                )
            )

        report_path = None
        report = PromptBatchReport(
            process_id=resolved_process_id,
            batch_id=resolved_batch_id,
            stream_id=self.store.stream_id,
            model=self.model,
            initial_job_count=len(initial_jobs),
            repaired_job_count=repaired_count,
            firecrawl=firecrawl_usage,
            reviews=tuple(reviews),
        )
        if write_report_dir:
            write_report_dir.mkdir(parents=True, exist_ok=True)
            report_path = write_report_dir / f"{resolved_batch_id}.prompt-continuity-report.json"
            report_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
            report = PromptBatchReport(
                process_id=report.process_id,
                batch_id=report.batch_id,
                stream_id=report.stream_id,
                model=report.model,
                initial_job_count=report.initial_job_count,
                repaired_job_count=report.repaired_job_count,
                firecrawl=report.firecrawl,
                reviews=report.reviews,
                report_path=report_path,
            )
        return report


__all__ = [
    "DEFAULT_CONTINUITY_ANCHOR",
    "DEFAULT_PROMPT_BATCH_MODEL",
    "DEFAULT_PROMPT_BATCH_MAX_OUTPUT_TOKENS",
    "DEFAULT_PROMPT_BATCH_OBJECTIVE",
    "FirecrawlPromptBatchSeeder",
    "PromptBatchReport",
    "PromptContinuityFinding",
    "PromptContinuityReview",
    "PromptContinuityReviewer",
    "PromptSeed",
    "default_prompt_seeds",
    "firecrawl_usage_from_result",
]
