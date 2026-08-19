"""Fixed-prompt quality metrics for comparing hardware generation pipelines."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from statistics import median

from pydantic import BaseModel, Field

from forma_core.design_generation.state_machine.models import (
    GenerationStatus,
    ProjectGenerationResult,
)


class GenerationBenchmarkAttempt(BaseModel):
    pipeline: str
    prompt: str
    status: str
    valid_bom_line_count: int = Field(ge=0)
    physical_component_count: int = Field(ge=0)
    required_capability_count: int = Field(default=0, ge=0)
    covered_capability_count: int = Field(default=0, ge=0)
    required_obligation_count: int = Field(ge=0)
    resolved_obligation_count: int = Field(ge=0)
    deferred_role_count: int = Field(ge=0)
    blocked_role_count: int = Field(ge=0)
    localized_retry_count: int = Field(ge=0)
    partial_retained_useful_bom: bool = False


class GenerationBenchmarkSummary(BaseModel):
    pipeline: str
    attempt_count: int
    valid_bom_yield: float
    generation_failure_rate: float
    median_valid_bom_lines: float
    median_physical_component_count: float
    required_obligation_coverage: float
    required_capability_coverage: float
    resolved_obligation_coverage: float
    deferred_role_count: int
    blocked_role_count: int
    localized_retry_count: int
    partial_project_bom_retention_rate: float


def attempt_from_result(
    pipeline: str,
    prompt: str,
    result: ProjectGenerationResult,
    *,
    deferred_role_count: int = 0,
    blocked_role_count: int = 0,
) -> GenerationBenchmarkAttempt:
    return GenerationBenchmarkAttempt(
        pipeline=pipeline,
        prompt=prompt,
        status=result.status.value,
        valid_bom_line_count=result.completeness.valid_bom_line_count,
        physical_component_count=result.completeness.physical_component_count,
        required_capability_count=result.completeness.required_capability_count,
        covered_capability_count=result.completeness.covered_capability_count,
        required_obligation_count=result.completeness.required_obligation_count,
        resolved_obligation_count=result.completeness.resolved_obligation_count,
        deferred_role_count=deferred_role_count,
        blocked_role_count=blocked_role_count,
        localized_retry_count=sum(1 for item in result.failures if item.recoverable),
        partial_retained_useful_bom=(
            result.status == GenerationStatus.PARTIAL
            and result.completeness.valid_bom_line_count > 0
        ),
    )


def summarize_attempts(
    attempts: Iterable[GenerationBenchmarkAttempt],
) -> GenerationBenchmarkSummary:
    rows = list(attempts)
    if not rows:
        raise ValueError("At least one generation attempt is required.")
    pipeline = rows[0].pipeline
    if any(item.pipeline != pipeline for item in rows):
        raise ValueError("Summarize one pipeline at a time.")
    required = sum(item.required_obligation_count for item in rows)
    required_capabilities = sum(item.required_capability_count for item in rows)
    resolved_obligation_coverage = (
        sum(item.resolved_obligation_count for item in rows) / required
        if required
        else 1.0
    )
    partial = [item for item in rows if item.status == GenerationStatus.PARTIAL.value]
    return GenerationBenchmarkSummary(
        pipeline=pipeline,
        attempt_count=len(rows),
        valid_bom_yield=sum(item.valid_bom_line_count for item in rows) / len(rows),
        generation_failure_rate=(
            sum(item.status == GenerationStatus.FAILED.value for item in rows)
            / len(rows)
        ),
        median_valid_bom_lines=median(item.valid_bom_line_count for item in rows),
        median_physical_component_count=median(
            item.physical_component_count for item in rows
        ),
        required_obligation_coverage=resolved_obligation_coverage,
        required_capability_coverage=(
            sum(item.covered_capability_count for item in rows) / required_capabilities
            if required_capabilities
            else 1.0
        ),
        resolved_obligation_coverage=resolved_obligation_coverage,
        deferred_role_count=sum(item.deferred_role_count for item in rows),
        blocked_role_count=sum(item.blocked_role_count for item in rows),
        localized_retry_count=sum(item.localized_retry_count for item in rows),
        partial_project_bom_retention_rate=(
            sum(item.partial_retained_useful_bom for item in partial) / len(partial)
            if partial
            else 1.0
        ),
    )


def run_fixed_prompt_benchmark(
    *,
    pipeline: str,
    prompts: list[str],
    iterations: int,
    generate: Callable[[str], ProjectGenerationResult],
) -> GenerationBenchmarkSummary:
    if iterations < 1:
        raise ValueError("iterations must be at least one.")
    attempts = [
        attempt_from_result(pipeline, prompt, generate(prompt))
        for prompt in prompts
        for _ in range(iterations)
    ]
    return summarize_attempts(attempts)


__all__ = [
    "GenerationBenchmarkAttempt",
    "GenerationBenchmarkSummary",
    "attempt_from_result",
    "run_fixed_prompt_benchmark",
    "summarize_attempts",
]
