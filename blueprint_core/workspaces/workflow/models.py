from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ProjectWorkflowState(str, Enum):
    GATHERING_CONTEXT = "gathering_context"
    READY_TO_BUILD = "ready_to_build"
    BUILDING = "building"
    AWAITING_FEEDBACK = "awaiting_feedback"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class WorkflowActorType(str, Enum):
    USER = "user"
    SYSTEM = "system"


class ProjectWorkflow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    owner_user_id: NonEmptyString
    state: ProjectWorkflowState
    revision: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class ProjectWorkflowTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transition_id: UUID
    project_id: UUID
    owner_user_id: NonEmptyString
    from_state: ProjectWorkflowState | None
    to_state: ProjectWorkflowState
    actor_type: WorkflowActorType
    actor_id: NonEmptyString | None = None
    reason: NonEmptyString
    idempotency_key: NonEmptyString | None = None
    revision: int = Field(ge=1)
    created_at: datetime


class WorkflowTransitionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to_state: ProjectWorkflowState
    reason: NonEmptyString
    idempotency_key: NonEmptyString | None = None


class WorkflowTransitionOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow: ProjectWorkflow
    transition: ProjectWorkflowTransition | None
    idempotent_replay: bool = False


class ProjectWorkflowHistory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow: ProjectWorkflow
    transitions: list[ProjectWorkflowTransition]

