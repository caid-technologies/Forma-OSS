from __future__ import annotations

from forma_core.workspaces.workflow.models import ProjectWorkflow, ProjectWorkflowState
from forma_core.workspaces.workflow.service import WorkflowStateError


MUTATING_ACTION_MARKERS = (
    "generate",
    "build",
    "fabricat",
    "opencad",
    "cad.mutat",
    "iterate",
)


def ensure_action_allowed(workflow: ProjectWorkflow, action: str) -> None:
    """Prevent tool-backed project mutations while context is still being gathered."""

    normalized = str(action or "").strip().casefold()
    if workflow.state != ProjectWorkflowState.GATHERING_CONTEXT:
        return
    if not any(marker in normalized for marker in MUTATING_ACTION_MARKERS):
        return
    raise WorkflowStateError(
        "tool_execution_blocked_while_gathering_context",
        "Build, generation, fabrication, and OpenCAD mutations are blocked while project context is being gathered.",
        context={
            "project_id": str(workflow.project_id),
            "workflow_state": workflow.state.value,
            "action": action,
        },
    )
