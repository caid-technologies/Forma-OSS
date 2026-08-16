"""Versioned contracts shared by specialized Forma workers."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError


WORKER_CONTRACT_VERSION = "1.0"
NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WorkerProgressStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"


class WorkerResultStatus(str, Enum):
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkerContract(BaseModel):
    """Common identity and correlation fields carried by every worker envelope."""

    model_config = ConfigDict(extra="forbid")

    contract_version: str
    project_id: UUID
    project_revision: int = Field(ge=1)
    design_brief_id: UUID
    design_brief_version: int = Field(ge=1)
    job_id: NonEmptyString
    correlation_id: NonEmptyString
    worker_id: NonEmptyString
    capability_id: NonEmptyString

    @field_validator("contract_version")
    @classmethod
    def validate_contract_version(cls, value: str) -> str:
        normalized = str(value).strip()
        if normalized != WORKER_CONTRACT_VERSION:
            raise PydanticCustomError(
                "unsupported_worker_contract_version",
                "Unsupported worker envelope version '{version}'; supported versions: {supported_versions}",
                {"version": normalized, "supported_versions": [WORKER_CONTRACT_VERSION]},
            )
        return normalized

    def context_identity(self) -> tuple[object, ...]:
        return (
            self.project_id,
            self.project_revision,
            self.design_brief_id,
            self.design_brief_version,
            self.job_id,
            self.correlation_id,
            self.worker_id,
            self.capability_id,
        )


class WorkerDependency(BaseModel):
    """A prerequisite job whose result is required or advisory for a request."""

    model_config = ConfigDict(extra="forbid")

    dependency_id: NonEmptyString = Field(default_factory=lambda: f"dep_{uuid4().hex}")
    job_id: NonEmptyString
    worker_id: NonEmptyString | None = None
    capability_id: NonEmptyString | None = None
    required: bool = True


class WorkerRequest(WorkerContract):
    """Validated input handed to one worker capability."""

    input_contract_version: NonEmptyString
    dependencies: list[WorkerDependency] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    requested_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_unique_dependencies(self) -> "WorkerRequest":
        dependency_ids = [dependency.dependency_id for dependency in self.dependencies]
        if len(dependency_ids) != len(set(dependency_ids)):
            raise ValueError("WorkerRequest dependency_id values must be unique.")
        return self


class WorkerProgress(WorkerContract):
    """Ordered progress observation emitted while a request is running."""

    sequence: int = Field(ge=0)
    status: WorkerProgressStatus
    percent_complete: float | None = Field(default=None, ge=0, le=100)
    message: NonEmptyString | None = None
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkerArtifact(WorkerContract):
    """Durable reference to one artifact produced by a worker."""

    artifact_id: NonEmptyString = Field(default_factory=lambda: f"artifact_{uuid4().hex}")
    kind: NonEmptyString
    uri: NonEmptyString
    media_type: NonEmptyString | None = None
    checksum: NonEmptyString | None = None
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkerError(WorkerContract):
    """Stable machine-readable worker failure shape."""

    error_id: NonEmptyString = Field(default_factory=lambda: f"error_{uuid4().hex}")
    code: NonEmptyString
    message: NonEmptyString
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class WorkerResult(WorkerContract):
    """Terminal output for one worker request."""

    output_contract_version: NonEmptyString
    status: WorkerResultStatus
    output: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[WorkerArtifact] = Field(default_factory=list)
    error: WorkerError | None = None
    completed_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_terminal_shape(self) -> "WorkerResult":
        if self.status == WorkerResultStatus.FAILED and self.error is None:
            raise ValueError("A failed WorkerResult requires error details.")
        if self.status == WorkerResultStatus.PARTIAL and (self.error is None or not self.artifacts):
            raise ValueError("A partial WorkerResult requires both an error and successful artifacts.")
        if self.status == WorkerResultStatus.SUCCEEDED and self.error is not None:
            raise ValueError("A successful WorkerResult cannot include an error.")
        for artifact in self.artifacts:
            if artifact.context_identity() != self.context_identity():
                raise ValueError("WorkerArtifact context must match its WorkerResult.")
        if self.error is not None and self.error.context_identity() != self.context_identity():
            raise ValueError("WorkerError context must match its WorkerResult.")
        return self


__all__ = [
    "WORKER_CONTRACT_VERSION",
    "WorkerArtifact",
    "WorkerContract",
    "WorkerDependency",
    "WorkerError",
    "WorkerProgress",
    "WorkerProgressStatus",
    "WorkerRequest",
    "WorkerResult",
    "WorkerResultStatus",
]
