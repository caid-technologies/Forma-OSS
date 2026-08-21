from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from apps.api.auth import UserContext, require_user_context
from apps.api.context_builds import ContextBuildDispatcher
from forma_core.database import (
    cancel_project_generation_plan,
    get_project_generation_plan,
    reset_project_generation_plan,
)
from forma_core.workers import WorkerExecutionPlan, WorkerPlanningError


router = APIRouter(prefix="/projects/{project_id}/build", tags=["project-build-execution"])


def _owner(user: UserContext) -> str:
    owner = str(user.owner_user_id or "").strip()
    if not owner:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in to view build execution.")
    return owner


def _owned_plan(project_id: UUID, plan_id: str, owner: str) -> WorkerExecutionPlan:
    try:
        plan = get_project_generation_plan(plan_id, owner)
    except WorkerPlanningError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.as_dict()) from exc
    if str(plan.project_id) != str(project_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Build execution not found.")
    return plan


@router.get("/plans/{plan_id}", response_model=WorkerExecutionPlan)
def get_build_plan_endpoint(
    project_id: UUID,
    plan_id: str,
    user: UserContext = Depends(require_user_context),
) -> WorkerExecutionPlan:
    return _owned_plan(project_id, plan_id, _owner(user))


@router.post("/plans/{plan_id}/execute", response_model=WorkerExecutionPlan)
async def execute_build_plan_endpoint(
    project_id: UUID,
    plan_id: str,
    user: UserContext = Depends(require_user_context),
) -> WorkerExecutionPlan:
    """Execute a plan inside this request so serverless runtimes keep it alive."""

    owner = _owner(user)
    _owned_plan(project_id, plan_id, owner)
    return await ContextBuildDispatcher.execute(plan_id, owner)


@router.post("/plans/{plan_id}/resume", response_model=WorkerExecutionPlan)
def resume_build_plan_endpoint(
    project_id: UUID,
    plan_id: str,
    user: UserContext = Depends(require_user_context),
) -> WorkerExecutionPlan:
    """Relaunch a detached plan when this process no longer owns it."""

    owner = _owner(user)
    _owned_plan(project_id, plan_id, owner)
    return ContextBuildDispatcher.resume(plan_id, owner)


@router.post("/plans/{plan_id}/cancel", response_model=WorkerExecutionPlan)
async def cancel_build_plan_endpoint(
    project_id: UUID,
    plan_id: str,
    user: UserContext = Depends(require_user_context),
) -> WorkerExecutionPlan:
    owner = _owner(user)
    _owned_plan(project_id, plan_id, owner)
    ContextBuildDispatcher.signal_cancel(plan_id)
    return await cancel_project_generation_plan(plan_id, owner)


@router.post("/plans/{plan_id}/reset", response_model=WorkerExecutionPlan)
async def reset_build_plan_endpoint(
    project_id: UUID,
    plan_id: str,
    user: UserContext = Depends(require_user_context),
) -> WorkerExecutionPlan:
    """Reset a failed generation plan so the current user can try it again."""

    owner = _owner(user)
    _owned_plan(project_id, plan_id, owner)
    try:
        reset_plan = await reset_project_generation_plan(plan_id, owner)
    except WorkerPlanningError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.as_dict()) from exc
    if reset_plan.status.value == "planned" and not ContextBuildDispatcher.requires_request_bound_execution():
        ContextBuildDispatcher._launch(plan_id, owner)
    return reset_plan


__all__ = ["router"]
