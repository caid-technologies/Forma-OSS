"""Canonical, immutable project revision boundary shared by workers and workspace adapters."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal, Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from blueprint_core.workspaces.design_briefs import DesignBrief
from blueprint_core.workspaces.projects.models import ComponentInstance, HardwareIR


PROJECT_REVISION_SCHEMA_VERSION = "1.0"
NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProjectSystem(BaseModel):
    """A generated functional system composed from project components."""

    model_config = ConfigDict(extra="forbid")

    system_id: NonEmptyString
    kind: NonEmptyString
    name: NonEmptyString
    component_refs: list[NonEmptyString] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectArtifact(BaseModel):
    """A durable artifact reference owned by one canonical project revision."""

    model_config = ConfigDict(extra="forbid")

    artifact_id: NonEmptyString
    kind: NonEmptyString
    uri: NonEmptyString
    media_type: NonEmptyString | None = None
    checksum: NonEmptyString | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectRevisionDraft(BaseModel):
    """Identity-free structured output produced by a worker before persistence."""

    model_config = ConfigDict(extra="forbid")

    state: HardwareIR
    components: list[ComponentInstance] = Field(default_factory=list)
    systems: list[ProjectSystem] = Field(default_factory=list)
    artifacts: list[ProjectArtifact] = Field(default_factory=list)
    assumptions: list[NonEmptyString] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_consistent_unique_output(self) -> "ProjectRevisionDraft":
        if self.components != self.state.components:
            raise ValueError("Project revision components must match the canonical HardwareIR state.")
        for values, label in (
            ([item.system_id for item in self.systems], "system_id"),
            ([item.artifact_id for item in self.artifacts], "artifact_id"),
            (list(self.assumptions), "assumption"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"Project revision {label} values must be unique.")
        component_refs = {item.ref_des for item in self.components}
        dangling = sorted({
            ref_des
            for system in self.systems
            for ref_des in system.component_refs
            if ref_des not in component_refs
        })
        if dangling:
            raise ValueError(f"Project systems reference unknown components: {', '.join(dangling)}.")
        return self


class ProjectRevision(ProjectRevisionDraft):
    """An immutable revision committed through the shared project-state boundary."""

    schema_version: Literal["1.0"] = PROJECT_REVISION_SCHEMA_VERSION
    revision_id: UUID
    project_id: UUID
    owner_user_id: NonEmptyString
    revision: int = Field(ge=1)
    parent_revision: int | None = Field(default=None, ge=1)
    design_brief_id: UUID
    design_brief_version: int = Field(ge=1)
    source_job_id: NonEmptyString
    created_at: datetime = Field(default_factory=_utc_now)


class ProjectRevisionOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: ProjectRevision
    idempotent_replay: bool = False


class ProjectStateError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.context = context or {}

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "context": dict(self.context),
        }


class ProjectStateRepository(Protocol):
    def get_design_brief_version(
        self,
        project_id: str,
        owner_user_id: str,
        brief_version: int,
    ) -> Any | None: ...

    def get_latest_project_revision(self, project_id: str, owner_user_id: str) -> Any | None: ...

    def get_project_revision_by_source_job(
        self,
        project_id: str,
        owner_user_id: str,
        source_job_id: str,
    ) -> Any | None: ...

    def insert_initial_project_revision(self, record: dict[str, Any]) -> Any | None: ...


def _canonical_uuid(value: str | UUID, field_name: str) -> UUID:
    try:
        return UUID(str(value).strip())
    except (TypeError, ValueError, AttributeError) as exc:
        raise ProjectStateError("invalid_project_revision_identity", f"{field_name} must be a UUID.") from exc


def _revision_from_record(record: Any) -> ProjectRevision:
    payload = getattr(record, "payload_json", None)
    if not isinstance(payload, dict):
        raise ProjectStateError(
            "invalid_persisted_project_revision",
            "Persisted project revision payload_json must be an object.",
        )
    return ProjectRevision.model_validate(payload)


class ProjectStateService:
    """Create and retrieve revisions without allowing cross-project or stale writes."""

    def __init__(self, repository: ProjectStateRepository) -> None:
        self._repository = repository

    def get_latest(self, project_id: str | UUID, owner_user_id: str) -> ProjectRevision:
        project = str(_canonical_uuid(project_id, "project_id"))
        owner = str(owner_user_id or "").strip()
        record = self._repository.get_latest_project_revision(project, owner)
        if record is None:
            raise ProjectStateError("project_revision_not_found", "Project revision not found.")
        return _revision_from_record(record)

    def get_by_source_job(
        self,
        project_id: str | UUID,
        owner_user_id: str,
        source_job_id: str,
    ) -> ProjectRevision | None:
        project = str(_canonical_uuid(project_id, "project_id"))
        owner = str(owner_user_id or "").strip()
        job_id = str(source_job_id or "").strip()
        record = self._repository.get_project_revision_by_source_job(project, owner, job_id)
        return _revision_from_record(record) if record is not None else None

    def require_frozen_design_brief(
        self,
        design_brief: DesignBrief,
        owner_user_id: str,
    ) -> DesignBrief:
        owner = str(owner_user_id or "").strip()
        record = self._repository.get_design_brief_version(
            str(design_brief.project_id),
            owner,
            design_brief.brief_version,
        )
        payload = getattr(record, "payload_json", None) if record is not None else None
        if not isinstance(payload, dict):
            raise ProjectStateError(
                "frozen_design_brief_not_found",
                "The exact frozen DesignBrief is not available to the project owner.",
            )
        persisted = DesignBrief.model_validate(payload)
        if persisted != design_brief:
            raise ProjectStateError(
                "frozen_design_brief_mismatch",
                "Generation input does not match the persisted frozen DesignBrief snapshot.",
                context={
                    "project_id": str(design_brief.project_id),
                    "design_brief_id": str(design_brief.design_brief_id),
                    "design_brief_version": design_brief.brief_version,
                },
            )
        return persisted

    def create_initial_revision(
        self,
        draft: ProjectRevisionDraft,
        *,
        project_id: str | UUID,
        owner_user_id: str,
        design_brief_id: str | UUID,
        design_brief_version: int,
        source_job_id: str,
    ) -> ProjectRevisionOutcome:
        project_uuid = _canonical_uuid(project_id, "project_id")
        brief_uuid = _canonical_uuid(design_brief_id, "design_brief_id")
        project = str(project_uuid)
        owner = str(owner_user_id or "").strip()
        job_id = str(source_job_id or "").strip()
        if not owner or not job_id:
            raise ProjectStateError(
                "invalid_project_revision_identity",
                "owner_user_id and source_job_id are required.",
            )

        replay = self._repository.get_project_revision_by_source_job(project, owner, job_id)
        if replay is not None:
            revision = _revision_from_record(replay)
            self._require_identity(revision, project_uuid, brief_uuid, design_brief_version, job_id)
            return ProjectRevisionOutcome(revision=revision, idempotent_replay=True)

        brief_record = self._repository.get_design_brief_version(project, owner, design_brief_version)
        if brief_record is None or str(getattr(brief_record, "design_brief_id", "")) != str(brief_uuid):
            raise ProjectStateError(
                "frozen_design_brief_not_found",
                "The exact frozen DesignBrief is not available to the project owner.",
                context={
                    "project_id": project,
                    "design_brief_id": str(brief_uuid),
                    "design_brief_version": design_brief_version,
                },
            )
        if self._repository.get_latest_project_revision(project, owner) is not None:
            raise ProjectStateError(
                "initial_project_revision_exists",
                "The project already has an initial revision.",
                context={"project_id": project},
            )

        state = draft.state.model_copy(deep=True)
        metadata = dict(state.assembly_metadata or {})
        supplied_project = str(metadata.get("project_id") or "").strip()
        if supplied_project and supplied_project != project:
            raise ProjectStateError(
                "project_revision_identity_mismatch",
                "Generated state targets a different project.",
                context={"expected_project_id": project, "actual_project_id": supplied_project},
            )
        supplied_revision = metadata.get("revision")
        if supplied_revision not in (None, 1, "1"):
            raise ProjectStateError(
                "project_revision_identity_mismatch",
                "Generated state targets a different project revision.",
                context={"expected_revision": 1, "actual_revision": supplied_revision},
            )
        state.assembly_metadata = {
            **metadata,
            "project_id": project,
            "revision": 1,
            "design_brief_id": str(brief_uuid),
            "design_brief_version": design_brief_version,
            "source_job_id": job_id,
        }
        normalized_draft = draft.model_copy(update={"state": state, "components": list(state.components)})
        revision = ProjectRevision(
            **normalized_draft.model_dump(),
            revision_id=uuid4(),
            project_id=project_uuid,
            owner_user_id=owner,
            revision=1,
            parent_revision=None,
            design_brief_id=brief_uuid,
            design_brief_version=design_brief_version,
            source_job_id=job_id,
        )
        record = {
            "id": str(revision.revision_id),
            "project_id": project,
            "owner_user_id": owner,
            "revision": revision.revision,
            "parent_revision": revision.parent_revision,
            "design_brief_id": str(brief_uuid),
            "design_brief_version": design_brief_version,
            "source_job_id": job_id,
            "payload_json": revision.model_dump(mode="json"),
            "created_at": revision.created_at.isoformat(),
        }
        saved = self._repository.insert_initial_project_revision(record)
        if saved is not None:
            return ProjectRevisionOutcome(revision=_revision_from_record(saved))

        replay = self._repository.get_project_revision_by_source_job(project, owner, job_id)
        if replay is not None:
            persisted = _revision_from_record(replay)
            self._require_identity(persisted, project_uuid, brief_uuid, design_brief_version, job_id)
            return ProjectRevisionOutcome(revision=persisted, idempotent_replay=True)
        raise ProjectStateError(
            "project_revision_conflict",
            "Project state changed before the initial revision could be committed.",
            retryable=True,
            context={"project_id": project},
        )

    @staticmethod
    def _require_identity(
        revision: ProjectRevision,
        project_id: UUID,
        design_brief_id: UUID,
        design_brief_version: int,
        source_job_id: str,
    ) -> None:
        if (
            revision.project_id != project_id
            or revision.design_brief_id != design_brief_id
            or revision.design_brief_version != design_brief_version
            or revision.source_job_id != source_job_id
        ):
            raise ProjectStateError(
                "project_revision_idempotency_conflict",
                "The source job is already attached to a different project or DesignBrief revision.",
            )


__all__ = [
    "PROJECT_REVISION_SCHEMA_VERSION",
    "ProjectArtifact",
    "ProjectRevision",
    "ProjectRevisionDraft",
    "ProjectRevisionOutcome",
    "ProjectStateError",
    "ProjectStateRepository",
    "ProjectStateService",
    "ProjectSystem",
]
