from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from pydantic_core import PydanticCustomError


DESIGN_BRIEF_SCHEMA_VERSION = "1.0"
NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class DesignBriefReadiness(str, Enum):
    """Explicit handoff state; scoring belongs to a later readiness service."""

    DRAFT = "draft"
    NEEDS_CLARIFICATION = "needs_clarification"
    READY = "ready"


class DesignBriefReference(BaseModel):
    """A durable pointer to context used when preparing a design brief."""

    model_config = ConfigDict(extra="forbid")

    reference_id: NonEmptyString
    kind: NonEmptyString
    label: NonEmptyString | None = None
    uri: NonEmptyString | None = None
    media_type: NonEmptyString | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DesignBriefCreate(BaseModel):
    """Client-authored fields in the canonical DesignBrief v1 contract."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    conversation_id: NonEmptyString
    intent: NonEmptyString
    summary: NonEmptyString
    requirements: list[NonEmptyString] = Field(default_factory=list)
    constraints: list[NonEmptyString] = Field(default_factory=list)
    references: list[DesignBriefReference] = Field(default_factory=list)
    requested_outputs: list[NonEmptyString] = Field(default_factory=list)
    validation_criteria: list[NonEmptyString] = Field(default_factory=list)
    unresolved_questions: list[NonEmptyString] = Field(default_factory=list)
    assumptions: list[NonEmptyString] = Field(default_factory=list)
    readiness: DesignBriefReadiness = DesignBriefReadiness.DRAFT

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        normalized = str(value).strip()
        if normalized != DESIGN_BRIEF_SCHEMA_VERSION:
            raise PydanticCustomError(
                "unsupported_design_brief_schema_version",
                "Unsupported DesignBrief schema version '{version}'; supported versions: {supported_versions}",
                {
                    "version": normalized,
                    "supported_versions": [DESIGN_BRIEF_SCHEMA_VERSION],
                },
            )
        return normalized


class DesignBrief(DesignBriefCreate):
    """A server-versioned, immutable DesignBrief snapshot."""

    design_brief_id: UUID
    project_id: UUID
    brief_version: int = Field(ge=1)
    previous_version: int | None = Field(default=None, ge=1)
    created_at: datetime


class DesignBriefVersionList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    versions: list[DesignBrief]
