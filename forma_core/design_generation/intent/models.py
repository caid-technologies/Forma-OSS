"""Intent-only contracts for progressively concretized design generation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MachineIntentDraft(BaseModel):
    """Minimal semantic interpretation returned by an intent agent.

    Deliberately absent are components, pins, wiring, sourcing data, IDs, and
    workflow metadata. Those belong to later stages or application code.
    """

    model_config = ConfigDict(extra="forbid")

    purpose: str = Field(min_length=1)
    users: list[str] = Field(default_factory=list)
    operating_environment: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    success_conditions: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)


class MachineIntent(BaseModel):
    """Canonical, application-owned representation of machine intent."""

    model_config = ConfigDict(extra="forbid")

    intent_id: str
    project_id: str
    source_prompt: str
    purpose: str
    users: list[str] = Field(default_factory=list)
    operating_environment: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    success_conditions: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
