from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from forma_core.workspaces.design_briefs import DesignBrief
from forma_core.workspaces.workflow import ProjectWorkflow, ProjectWorkflowTransition


NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ReadinessStatus(str, Enum):
    READY = "ready"
    NOT_READY = "not_ready"
    BLOCKED = "blocked"


class ReadinessBlockerCategory(str, Enum):
    REQUIREMENTS = "requirements"
    OUTPUTS = "outputs"
    VALIDATION = "validation"
    SAFETY = "safety"
    DIMENSIONAL = "dimensional"
    ELECTRICAL = "electrical"
    MATERIAL = "material"
    MANUFACTURING = "manufacturing"
    OTHER = "other"


class ReadinessBlocker(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: NonEmptyString
    category: ReadinessBlockerCategory
    message: NonEmptyString
    critical: bool
    source: NonEmptyString


class ReadinessResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    design_brief_id: UUID
    brief_version: int = Field(ge=1)
    status: ReadinessStatus
    reasons: list[NonEmptyString]
    unresolved_blockers: list[ReadinessBlocker]
    evaluated_at: datetime


class BuildMode(str, Enum):
    BUILD = "build"
    BUILD_ANYWAY = "build_anyway"


class BuildRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: NonEmptyString | None = None


class BuildAnywayRequest(BuildRequest):
    assumptions: list[NonEmptyString] = Field(min_length=1)


class ProjectBuild(BaseModel):
    model_config = ConfigDict(extra="forbid")

    build_id: UUID
    project_id: UUID
    owner_user_id: NonEmptyString
    design_brief_id: UUID
    brief_version: int = Field(ge=1)
    brief_snapshot: DesignBrief
    mode: BuildMode
    readiness: ReadinessResult
    introduced_assumptions: list[NonEmptyString]
    warnings: list[NonEmptyString]
    transition_id: UUID
    idempotency_key: NonEmptyString | None = None
    initiated_by: NonEmptyString
    created_at: datetime


class BuildInitiationOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    build: ProjectBuild
    workflow: ProjectWorkflow
    transition: ProjectWorkflowTransition
    idempotent_replay: bool = False
