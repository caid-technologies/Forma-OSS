"""Design obligations, abstract component roles, and completeness measures."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ObligationStatus(StrEnum):
    """Lifecycle state shared by obligations and component roles."""

    UNRESOLVED = "unresolved"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    DEFERRED = "deferred"
    BLOCKED = "blocked"


class DesignObligationDraft(BaseModel):
    """Bounded agent output which deliberately carries no application ID."""

    model_config = ConfigDict(extra="forbid")

    capability_name: str
    description: str
    obligation_type: Literal[
        "functional",
        "electrical",
        "mechanical",
        "interface",
        "power",
        "safety",
        "manufacturing",
    ]
    criticality: Literal["required", "preferred"] = "required"


class DesignObligation(DesignObligationDraft):
    """An application-owned requirement that the design must satisfy."""

    obligation_id: str
    status: ObligationStatus = ObligationStatus.UNRESOLVED
    satisfied_by_ids: list[str] = Field(default_factory=list)
    failure_reason: str | None = None


class ComponentRoleDraft(BaseModel):
    """An abstract component function, before selecting a physical part."""

    model_config = ConfigDict(extra="forbid")

    subsystem_name: str
    name: str
    function: str
    obligation_descriptions: list[str] = Field(min_length=1)
    requirements: list[str] = Field(default_factory=list)
    quantity: int = Field(default=1, ge=1)
    depends_on_role_names: list[str] = Field(default_factory=list)


class SubsystemPlanDraft(BaseModel):
    """Bounded subsystem proposal without application identity."""

    model_config = ConfigDict(extra="forbid")

    name: str
    purpose: str
    obligation_descriptions: list[str] = Field(min_length=1)


class SubsystemPlan(BaseModel):
    """Application-owned functional subsystem derived from obligations."""

    model_config = ConfigDict(extra="forbid")

    subsystem_id: str
    name: str
    purpose: str
    obligation_ids: list[str] = Field(min_length=1)


class ComponentRole(BaseModel):
    """Canonical component role and its application-owned relationships."""

    model_config = ConfigDict(extra="forbid")

    role_id: str
    subsystem_id: str | None = None
    subsystem_name: str
    name: str
    function: str
    obligation_ids: list[str] = Field(min_length=1)
    requirements: list[str] = Field(default_factory=list)
    quantity: int = Field(default=1, ge=1)
    depends_on_role_ids: list[str] = Field(default_factory=list)
    status: ObligationStatus = ObligationStatus.UNRESOLVED
    selected_definition_id: str | None = None
    failure_reason: str | None = None


class BomGapReview(BaseModel):
    """Canonical result of reviewing selected parts for procurement gaps."""

    model_config = ConfigDict(extra="forbid")

    is_complete: bool
    missing_roles: list[ComponentRole] = Field(default_factory=list)


class DesignCompleteness(BaseModel):
    """Deterministic capability, obligation, BOM, and instance coverage totals."""

    required_capability_count: int = Field(default=0, ge=0)
    covered_capability_count: int = Field(default=0, ge=0)
    required_obligation_count: int = Field(default=0, ge=0)
    resolved_obligation_count: int = Field(default=0, ge=0)
    unresolved_obligation_count: int = Field(default=0, ge=0)
    deferred_obligation_count: int = Field(default=0, ge=0)
    blocked_obligation_count: int = Field(default=0, ge=0)
    valid_bom_line_count: int = Field(default=0, ge=0)
    physical_component_count: int = Field(default=0, ge=0)

    @property
    def required_obligation_coverage(self) -> float:
        if not self.required_obligation_count:
            return 1.0
        return self.resolved_obligation_count / self.required_obligation_count

    @property
    def required_capability_coverage(self) -> float:
        if not self.required_capability_count:
            return 1.0
        return self.covered_capability_count / self.required_capability_count


class BomLineTrace(BaseModel):
    """Trace one counted BOM row back to roles, obligations, and capabilities."""

    line_id: str
    role_ids: list[str] = Field(min_length=1)
    obligation_ids: list[str] = Field(min_length=1)
    required_capabilities: list[str] = Field(min_length=1)
