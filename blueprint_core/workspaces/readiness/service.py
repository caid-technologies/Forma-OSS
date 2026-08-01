from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4

from blueprint_core.workspaces.design_briefs import DesignBrief
from blueprint_core.workspaces.readiness.models import (
    BuildInitiationOutcome,
    BuildMode,
    ProjectBuild,
    ReadinessResult,
    ReadinessStatus,
)
from blueprint_core.workspaces.workflow import (
    ProjectWorkflow,
    ProjectWorkflowState,
    ProjectWorkflowTransition,
    WorkflowActorType,
)


class BuildRepository(Protocol):
    def get_project_workflow(self, project_id: str, owner_user_id: str | None) -> Any | None: ...
    def get_project_build_by_idempotency(self, project_id: str, owner_user_id: str, idempotency_key: str) -> Any | None: ...
    def get_project_workflow_transition_by_idempotency(
        self, project_id: str, owner_user_id: str, idempotency_key: str
    ) -> Any | None: ...
    def apply_project_build_initiation(
        self,
        state_record: dict[str, Any],
        transition_record: dict[str, Any],
        build_record: dict[str, Any],
        expected_state: str,
        expected_revision: int,
    ) -> tuple[Any, Any, Any] | None: ...


class ReadinessError(RuntimeError):
    def __init__(self, code: str, message: str, *, context: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.context = context or {}

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "context": dict(self.context)}


def _workflow(record: Any) -> ProjectWorkflow:
    return ProjectWorkflow.model_validate({
        "project_id": record.project_id,
        "owner_user_id": record.owner_user_id,
        "state": record.state,
        "revision": record.revision,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    })


def _transition(record: Any) -> ProjectWorkflowTransition:
    return ProjectWorkflowTransition.model_validate({
        "transition_id": record.id,
        "project_id": record.project_id,
        "owner_user_id": record.owner_user_id,
        "from_state": record.from_state,
        "to_state": record.to_state,
        "actor_type": record.actor_type,
        "actor_id": record.actor_id,
        "reason": record.reason,
        "idempotency_key": record.idempotency_key,
        "revision": record.revision,
        "created_at": record.created_at,
    })


def _build(record: Any) -> ProjectBuild:
    return ProjectBuild.model_validate({
        "build_id": record.id,
        "project_id": record.project_id,
        "owner_user_id": record.owner_user_id,
        "design_brief_id": record.design_brief_id,
        "brief_version": record.brief_version,
        "brief_snapshot": record.brief_snapshot_json,
        "mode": record.mode,
        "readiness": record.readiness_result_json,
        "introduced_assumptions": record.introduced_assumptions_json,
        "warnings": record.warnings_json,
        "transition_id": record.transition_id,
        "idempotency_key": record.idempotency_key,
        "initiated_by": record.initiated_by,
        "created_at": record.created_at,
    })


class ProjectBuildService:
    def __init__(self, repository: BuildRepository) -> None:
        self._repository = repository

    def initiate(
        self,
        brief: DesignBrief,
        readiness: ReadinessResult,
        owner_user_id: str,
        *,
        mode: BuildMode,
        actor_id: str,
        introduced_assumptions: list[str],
        warnings: list[str],
        idempotency_key: str | None,
    ) -> BuildInitiationOutcome:
        project_id = str(brief.project_id)
        owner = str(owner_user_id or "").strip()
        actor = str(actor_id or "").strip()
        key = str(idempotency_key or "").strip() or None
        if not owner or not actor:
            raise ValueError("owner_user_id and actor_id are required.")
        if key:
            existing_build = self._repository.get_project_build_by_idempotency(project_id, owner, key)
            existing_transition = self._repository.get_project_workflow_transition_by_idempotency(project_id, owner, key)
            if existing_build is not None and existing_transition is not None:
                current = self._repository.get_project_workflow(project_id, owner)
                if current is None:
                    raise ReadinessError("workflow_not_found", "Project workflow not found.")
                return BuildInitiationOutcome(
                    build=_build(existing_build),
                    workflow=_workflow(current),
                    transition=_transition(existing_transition),
                    idempotent_replay=True,
                )

        current_record = self._repository.get_project_workflow(project_id, owner)
        if current_record is None:
            raise ReadinessError("workflow_not_found", "Project workflow not found.")
        current = _workflow(current_record)
        if current.state not in {ProjectWorkflowState.GATHERING_CONTEXT, ProjectWorkflowState.READY_TO_BUILD}:
            raise ReadinessError(
                "build_transition_not_allowed",
                f"Build cannot start while the project workflow is {current.state.value}.",
                context={"project_id": project_id, "workflow_state": current.state.value},
            )
        if mode == BuildMode.BUILD and readiness.status != ReadinessStatus.READY:
            code = "readiness_blocked" if readiness.status == ReadinessStatus.BLOCKED else "readiness_not_ready"
            raise ReadinessError(code, "The DesignBrief is not ready for Build.", context=readiness.model_dump(mode="json"))
        if mode == BuildMode.BUILD_ANYWAY:
            if readiness.status == ReadinessStatus.BLOCKED:
                raise ReadinessError(
                    "critical_readiness_blockers",
                    "Build Anyway cannot bypass critical project unknowns.",
                    context=readiness.model_dump(mode="json"),
                )
            if readiness.status == ReadinessStatus.NOT_READY and not introduced_assumptions:
                raise ReadinessError(
                    "build_anyway_assumptions_required",
                    "Build Anyway requires explicit assumptions for incomplete context.",
                )

        now = datetime.now(timezone.utc)
        build_id = str(uuid4())
        transition_id = str(uuid4())
        transition_key = key or f"build:{build_id}"
        next_revision = current.revision + 1
        state_record = {
            "project_id": project_id,
            "owner_user_id": owner,
            "state": ProjectWorkflowState.BUILDING.value,
            "revision": next_revision,
            "created_at": current.created_at.isoformat(),
            "updated_at": now.isoformat(),
        }
        transition_record = {
            "id": transition_id,
            "project_id": project_id,
            "owner_user_id": owner,
            "from_state": current.state.value,
            "to_state": ProjectWorkflowState.BUILDING.value,
            "actor_type": WorkflowActorType.USER.value,
            "actor_id": actor,
            "reason": "User started Build Anyway." if mode == BuildMode.BUILD_ANYWAY else "User started Build.",
            "idempotency_key": transition_key,
            "revision": next_revision,
            "created_at": now.isoformat(),
        }
        build_record = {
            "id": build_id,
            "project_id": project_id,
            "owner_user_id": owner,
            "design_brief_id": str(brief.design_brief_id),
            "brief_version": brief.brief_version,
            "brief_snapshot_json": brief.model_dump(mode="json"),
            "mode": mode.value,
            "readiness_result_json": readiness.model_dump(mode="json"),
            "introduced_assumptions_json": introduced_assumptions,
            "warnings_json": warnings,
            "transition_id": transition_id,
            "idempotency_key": transition_key,
            "initiated_by": actor,
            "created_at": now.isoformat(),
        }
        applied = self._repository.apply_project_build_initiation(
            state_record,
            transition_record,
            build_record,
            current.state.value,
            current.revision,
        )
        if applied is None:
            if key:
                return self.initiate(
                    brief,
                    readiness,
                    owner,
                    mode=mode,
                    actor_id=actor,
                    introduced_assumptions=introduced_assumptions,
                    warnings=warnings,
                    idempotency_key=key,
                )
            raise ReadinessError("build_transition_conflict", "Project workflow changed before Build could start.")
        workflow_record, transition_record_obj, build_record_obj = applied
        return BuildInitiationOutcome(
            build=_build(build_record_obj),
            workflow=_workflow(workflow_record),
            transition=_transition(transition_record_obj),
        )
