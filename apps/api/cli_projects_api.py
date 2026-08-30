"""Private project/revision synchronization endpoints for the Forma CLI."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from apps.api.auth import UserContext, require_user_context
from forma_core.database import (
    CliProjectConflictError,
    get_cli_project_revision,
    insert_cli_project_revision,
    list_cli_projects,
)
from forma_core.workspaces.projects.manifest import ProjectManifest


router = APIRouter(prefix="/cli/projects", tags=["cli"])


class ProjectPushRequest(BaseModel):
    manifest: dict[str, Any]
    parent_revision_id: str | None = Field(default=None, max_length=200)


def _owner(user: UserContext) -> str:
    if not user.owner_user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in to use cloud projects.")
    return user.owner_user_id


@router.get("")
async def list_cli_projects_endpoint(user: UserContext = Depends(require_user_context)) -> dict[str, object]:
    return {"items": list_cli_projects(_owner(user))}


@router.post("/push")
async def push_cli_project(
    request: ProjectPushRequest,
    user: UserContext = Depends(require_user_context),
) -> dict[str, Any]:
    owner = _owner(user)
    try:
        manifest = ProjectManifest.from_document(request.manifest)
        payload = manifest.upload_payload()
        return insert_cli_project_revision(
            payload,
            owner,
            expected_revision_id=request.parent_revision_id,
        )
    except CliProjectConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{project_id}/revisions/{revision_id}")
async def get_cli_project_revision_endpoint(
    project_id: str,
    revision_id: str,
    user: UserContext = Depends(require_user_context),
) -> dict[str, Any]:
    revision = get_cli_project_revision(project_id, _owner(user), revision_id)
    if revision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cloud project revision not found.")
    return revision


@router.get("/{project_id}")
async def get_latest_cli_project_revision(
    project_id: str,
    user: UserContext = Depends(require_user_context),
) -> dict[str, Any]:
    revision = get_cli_project_revision(project_id, _owner(user))
    if revision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cloud project not found.")
    return revision


__all__ = ["router"]
