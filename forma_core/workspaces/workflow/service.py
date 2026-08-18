from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import UUID, uuid4

from forma_core.workspaces.workflow.models import (
    ProjectWorkflow,
    ProjectWorkflowState,
    ProjectWorkflowTransition,
    WorkflowActorType,
    WorkflowTransitionOutcome,
)


ALLOWED_WORKFLOW_TRANSITIONS: dict[ProjectWorkflowState, frozenset[ProjectWorkflowState]] = {
    ProjectWorkflowState.GATHERING_CONTEXT: frozenset({
        ProjectWorkflowState.READY_TO_BUILD,
        ProjectWorkflowState.BUILDING,
        ProjectWorkflowState.CANCELLED,
        ProjectWorkflowState.FAILED,
    }),
    ProjectWorkflowState.READY_TO_BUILD: frozenset({
        ProjectWorkflowState.GATHERING_CONTEXT,
        ProjectWorkflowState.BUILDING,
        ProjectWorkflowState.CANCELLED,
        ProjectWorkflowState.FAILED,
    }),
    ProjectWorkflowState.BUILDING: frozenset({
        ProjectWorkflowState.AWAITING_FEEDBACK,
        ProjectWorkflowState.CANCELLED,
        ProjectWorkflowState.FAILED,
    }),
    ProjectWorkflowState.AWAITING_FEEDBACK: frozenset({
        ProjectWorkflowState.GATHERING_CONTEXT,
        ProjectWorkflowState.BUILDING,
        ProjectWorkflowState.COMPLETED,
        ProjectWorkflowState.CANCELLED,
        ProjectWorkflowState.FAILED,
    }),
    ProjectWorkflowState.COMPLETED: frozenset(),
    ProjectWorkflowState.CANCELLED: frozenset(),
    ProjectWorkflowState.FAILED: frozenset({
        ProjectWorkflowState.GATHERING_CONTEXT,
        ProjectWorkflowState.READY_TO_BUILD,
        ProjectWorkflowState.BUILDING,
        ProjectWorkflowState.CANCELLED,
    }),
}


class WorkflowRepository(Protocol):
    def get_project_workflow(self, project_id: str, owner_user_id: str | None) -> Any | None: ...
    def list_project_workflow_transitions(self, project_id: str, owner_user_id: str) -> list[Any]: ...
    def get_project_workflow_transition_by_idempotency(
        self, project_id: str, owner_user_id: str, idempotency_key: str
    ) -> Any | None: ...
    def apply_project_workflow_transition(
        self,
        state_record: dict[str, Any],
        transition_record: dict[str, Any],
        expected_state: str | None,
        expected_revision: int | None,
    ) -> tuple[Any, Any] | None: ...


class WorkflowStateError(RuntimeError):
    def __init__(self, code: str, message: str, *, context: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.context = context or {}

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "context": dict(self.context)}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _project_id(value: str | UUID) -> str:
    try:
        return str(UUID(str(value).strip()))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("project_id must be a UUID.") from exc


def _owner_id(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError("owner_user_id is required.")
    return normalized


def _reason(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError("A workflow transition reason is required.")
    return normalized


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


class ProjectWorkflowService:
    def __init__(self, repository: WorkflowRepository) -> None:
        self._repository = repository

    def initialize(
        self,
        project_id: str | UUID,
        owner_user_id: str,
        *,
        actor_type: WorkflowActorType = WorkflowActorType.SYSTEM,
        actor_id: str | None = None,
        reason: str = "Project workflow initialized.",
    ) -> WorkflowTransitionOutcome:
        project = _project_id(project_id)
        owner = _owner_id(owner_user_id)
        existing = self._repository.get_project_workflow(project, None)
        if existing is not None:
            if existing.owner_user_id != owner:
                raise WorkflowStateError("workflow_not_found", "Project workflow not found.")
            return WorkflowTransitionOutcome(workflow=_workflow(existing), transition=None, idempotent_replay=True)
        now = _utc_now()
        transition_id = str(uuid4())
        state_record = {
            "project_id": project,
            "owner_user_id": owner,
            "state": ProjectWorkflowState.GATHERING_CONTEXT.value,
            "revision": 1,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        transition_record = {
            "id": transition_id,
            "project_id": project,
            "owner_user_id": owner,
            "from_state": None,
            "to_state": ProjectWorkflowState.GATHERING_CONTEXT.value,
            "actor_type": actor_type.value,
            "actor_id": str(actor_id).strip() if actor_id else None,
            "reason": _reason(reason),
            "idempotency_key": f"workflow:init:{project}",
            "revision": 1,
            "created_at": now.isoformat(),
        }
        applied = self._repository.apply_project_workflow_transition(state_record, transition_record, None, None)
        if applied is None:
            existing = self._repository.get_project_workflow(project, None)
            if existing is not None and existing.owner_user_id == owner:
                return WorkflowTransitionOutcome(workflow=_workflow(existing), transition=None, idempotent_replay=True)
            raise WorkflowStateError("workflow_transition_conflict", "Workflow initialization conflicted.")
        workflow_record, transition_record_obj = applied
        return WorkflowTransitionOutcome(
            workflow=_workflow(workflow_record),
            transition=_transition(transition_record_obj),
        )

    def get(self, project_id: str | UUID, owner_user_id: str) -> ProjectWorkflow:
        record = self._repository.get_project_workflow(_project_id(project_id), _owner_id(owner_user_id))
        if record is None:
            raise WorkflowStateError("workflow_not_found", "Project workflow not found.")
        return _workflow(record)

    def history(self, project_id: str | UUID, owner_user_id: str) -> list[ProjectWorkflowTransition]:
        project = _project_id(project_id)
        owner = _owner_id(owner_user_id)
        self.get(project, owner)
        return [_transition(item) for item in self._repository.list_project_workflow_transitions(project, owner)]

    def transition(
        self,
        project_id: str | UUID,
        owner_user_id: str,
        to_state: ProjectWorkflowState,
        *,
        actor_type: WorkflowActorType,
        actor_id: str | None,
        reason: str,
        idempotency_key: str | None = None,
    ) -> WorkflowTransitionOutcome:
        project = _project_id(project_id)
        owner = _owner_id(owner_user_id)
        key = str(idempotency_key or "").strip() or None
        if key:
            replay = self._repository.get_project_workflow_transition_by_idempotency(project, owner, key)
            if replay is not None:
                current = self.get(project, owner)
                prior = _transition(replay)
                historical = current.model_copy(update={
                    "state": prior.to_state,
                    "revision": prior.revision,
                    "updated_at": prior.created_at,
                })
                return WorkflowTransitionOutcome(
                    workflow=historical,
                    transition=prior,
                    idempotent_replay=True,
                )
        current = self.get(project, owner)
        if current.state == to_state:
            return WorkflowTransitionOutcome(workflow=current, transition=None, idempotent_replay=True)
        allowed = ALLOWED_WORKFLOW_TRANSITIONS[current.state]
        if to_state not in allowed:
            raise WorkflowStateError(
                "invalid_workflow_transition",
                f"Cannot transition project workflow from {current.state.value} to {to_state.value}.",
                context={
                    "project_id": project,
                    "current_state": current.state.value,
                    "requested_state": to_state.value,
                    "allowed_states": sorted(state.value for state in allowed),
                },
            )
        now = _utc_now()
        next_revision = current.revision + 1
        state_record = {
            "project_id": project,
            "owner_user_id": owner,
            "state": to_state.value,
            "revision": next_revision,
            "created_at": current.created_at.isoformat(),
            "updated_at": now.isoformat(),
        }
        transition_record = {
            "id": str(uuid4()),
            "project_id": project,
            "owner_user_id": owner,
            "from_state": current.state.value,
            "to_state": to_state.value,
            "actor_type": actor_type.value,
            "actor_id": str(actor_id).strip() if actor_id else None,
            "reason": _reason(reason),
            "idempotency_key": key,
            "revision": next_revision,
            "created_at": now.isoformat(),
        }
        applied = self._repository.apply_project_workflow_transition(
            state_record,
            transition_record,
            current.state.value,
            current.revision,
        )
        if applied is None:
            if key:
                replay = self._repository.get_project_workflow_transition_by_idempotency(project, owner, key)
                if replay is not None:
                    return self.transition(
                        project, owner, to_state,
                        actor_type=actor_type, actor_id=actor_id, reason=reason, idempotency_key=key,
                    )
            raise WorkflowStateError(
                "workflow_transition_conflict",
                "Project workflow changed before the transition could be committed.",
                context={"project_id": project, "expected_revision": current.revision},
            )
        workflow_record, transition_record_obj = applied
        return WorkflowTransitionOutcome(
            workflow=_workflow(workflow_record),
            transition=_transition(transition_record_obj),
        )
