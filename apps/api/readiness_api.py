from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from apps.api.auth import UserContext, require_user_context
from apps.api.hosted_chat import require_hosted_chat_enabled
from forma_core.database import (
    evaluate_project_readiness,
    get_latest_project_build,
    initiate_project_build,
)
from forma_core.workspaces.readiness import (
    BuildAnywayRequest,
    BuildInitiationOutcome,
    BuildMode,
    BuildRequest,
    ProjectBuild,
    ReadinessError,
    ReadinessResult,
)
from forma_core.workspaces.workflow import WorkflowStateError


router = APIRouter(prefix="/projects/{project_id}", tags=["project-readiness"])


def _owner(user: UserContext) -> str:
    owner = str(user.owner_user_id or "").strip()
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "authentication_required", "message": "Sign in to evaluate or build a project."},
        )
    return owner


def _domain_error(exc: ReadinessError | WorkflowStateError) -> HTTPException:
    not_found_codes = {"design_brief_not_found", "project_build_not_found", "workflow_not_found"}
    status_code = status.HTTP_404_NOT_FOUND if exc.code in not_found_codes else status.HTTP_409_CONFLICT
    return HTTPException(status_code=status_code, detail=exc.as_dict())


@router.get("/readiness", response_model=ReadinessResult)
def evaluate_readiness_endpoint(
    project_id: UUID,
    user: UserContext = Depends(require_user_context),
) -> ReadinessResult:
    try:
        return evaluate_project_readiness(str(project_id), _owner(user))
    except (ReadinessError, WorkflowStateError) as exc:
        raise _domain_error(exc) from exc


@router.post("/build", response_model=BuildInitiationOutcome)
def build_project_endpoint(
    project_id: UUID,
    request: BuildRequest,
    user: UserContext = Depends(require_user_context),
) -> BuildInitiationOutcome:
    require_hosted_chat_enabled()
    owner = _owner(user)
    try:
        return initiate_project_build(
            str(project_id),
            owner,
            mode=BuildMode.BUILD,
            actor_id=owner,
            idempotency_key=request.idempotency_key,
        )
    except (ReadinessError, WorkflowStateError) as exc:
        raise _domain_error(exc) from exc


@router.post("/build-anyway", response_model=BuildInitiationOutcome)
def build_project_anyway_endpoint(
    project_id: UUID,
    request: BuildAnywayRequest,
    user: UserContext = Depends(require_user_context),
) -> BuildInitiationOutcome:
    require_hosted_chat_enabled()
    owner = _owner(user)
    try:
        return initiate_project_build(
            str(project_id),
            owner,
            mode=BuildMode.BUILD_ANYWAY,
            actor_id=owner,
            assumptions=request.assumptions,
            idempotency_key=request.idempotency_key,
        )
    except (ReadinessError, WorkflowStateError) as exc:
        raise _domain_error(exc) from exc


@router.get("/build", response_model=ProjectBuild)
def get_frozen_build_endpoint(
    project_id: UUID,
    user: UserContext = Depends(require_user_context),
) -> ProjectBuild:
    try:
        return get_latest_project_build(str(project_id), _owner(user))
    except (ReadinessError, WorkflowStateError) as exc:
        raise _domain_error(exc) from exc
