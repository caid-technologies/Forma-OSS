"""State and public result contracts for intent-first generation."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from forma_core.design_generation.completeness.models import (
    BomLineTrace,
    DesignCompleteness,
)
from forma_core.workspaces.projects.models import HardwareIR


class GenerationPhase(StrEnum):
    """Explicit state-machine phases for intent-first generation."""

    UNDERSTAND_INTENT = "understand_intent"
    EXPAND_OBLIGATIONS = "expand_obligations"
    PLAN_ARCHITECTURE = "plan_architecture"
    SELECT_COMPONENT = "select_component"
    ENRICH_COMPONENT = "enrich_component"
    VALIDATE_COMPONENT = "validate_component"
    COMMIT_COMPONENT = "commit_component"
    ASSESS_COMPLETENESS = "assess_completeness"
    AUDIT_BOM = "audit_bom"
    GENERATE_WIRING = "generate_wiring"
    VALIDATE_PROJECT = "validate_project"
    COMPILE_PROJECT = "compile_project"
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class GenerationStatus(StrEnum):
    """Public terminal and nonterminal generation statuses."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class GenerationOptions(BaseModel):
    """Bounded retry, role-count, and provider settings for a run."""

    max_role_attempts: int = Field(default=3, ge=1)
    max_component_roles: int = Field(default=100, ge=1)
    max_bom_audit_passes: int = Field(default=3, ge=1)
    max_circuit_patches: int = Field(default=50, ge=1)
    allow_partial: bool = True
    provider_name: str | None = None
    model_name: str | None = None


class GenerationFailure(BaseModel):
    """Persisted internal failure with retry metadata."""

    failure_id: str
    phase: GenerationPhase
    target_id: str | None = None
    error_code: str
    message: str
    attempt_count: int = Field(default=1, ge=1)
    recoverable: bool = True


class DesignGenerationState(BaseModel):
    """Durable state for one intent-first project generation run."""

    run_id: str
    project_id: str
    intent_id: str | None = None
    phase: GenerationPhase = GenerationPhase.UNDERSTAND_INTENT
    status: GenerationStatus = GenerationStatus.PENDING
    pending_role_ids: list[str] = Field(default_factory=list)
    completed_role_ids: list[str] = Field(default_factory=list)
    deferred_role_ids: list[str] = Field(default_factory=list)
    blocked_role_ids: list[str] = Field(default_factory=list)
    current_role_id: str | None = None
    attempt_counts: dict[str, int] = Field(default_factory=dict)
    bom_audit_pass_count: int = Field(default=0, ge=0)
    bom_audit_complete: bool = False
    failures: list[GenerationFailure] = Field(default_factory=list)
    completeness: DesignCompleteness = Field(default_factory=DesignCompleteness)

    @property
    def is_terminal(self) -> bool:
        return self.status in {
            GenerationStatus.COMPLETE,
            GenerationStatus.PARTIAL,
            GenerationStatus.FAILED,
        }


class GenerationFailureSummary(BaseModel):
    """Stable public projection of a generation failure."""

    phase: str
    target_id: str | None = None
    error_code: str
    message: str
    recoverable: bool


class GenerationCompleteness(DesignCompleteness):
    """Stable public name for a generation run's completeness summary."""


class ProjectGenerationResult(BaseModel):
    """Terminal public result with partial work and BOM traceability."""

    run_id: str
    project_id: str
    status: GenerationStatus
    project: HardwareIR | None
    completeness: GenerationCompleteness
    failures: list[GenerationFailureSummary] = Field(default_factory=list)
    bom_traces: list[BomLineTrace] = Field(default_factory=list)
