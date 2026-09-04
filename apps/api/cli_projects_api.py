"""Private project/revision synchronization endpoints for the Forma CLI."""

from __future__ import annotations

import hashlib
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from apps.api.auth import UserContext, require_user_context
from forma_core.config.compatibility import (
    UnsupportedHardwareIRVersion,
    ensure_supported_hardware_ir_version,
    hosted_compatibility_metadata,
)
from forma_core.database import (
    CliProjectConflictError,
    get_cli_project_revision,
    insert_cli_project_revision,
    list_project_identities,
)
from forma_core.persistence.project_artifacts import (
    ProjectArtifactStorage,
    ProjectArtifactStorageError,
)
from forma_core.workspaces.projects.manifest import (
    ProjectManifest,
    normalize_artifact_media_type,
    validate_artifact_references,
)
from forma_core.workspaces.projects.models import ProjectIdentityResponse


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
    items = [
        ProjectIdentityResponse.model_validate(identity).model_dump(mode="json", exclude_unset=True)
        for identity in list_project_identities(_owner(user))
    ]
    return {"items": items}


@router.post("/push")
async def push_cli_project(
    request: ProjectPushRequest,
    user: UserContext = Depends(require_user_context),
) -> dict[str, Any]:
    owner = _owner(user)
    try:
        compatibility = hosted_compatibility_metadata()
        ensure_supported_hardware_ir_version(
            request.manifest,
            supported_versions=compatibility.supported_hardware_ir_versions,
        )
        manifest = ProjectManifest.from_document(request.manifest)
        payload = manifest.upload_payload()
        payload["artifacts"] = validate_artifact_references(payload.get("artifacts"), require_integrity=True)
        if payload["artifacts"] and not ProjectArtifactStorage().config.get("enabled"):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="CLI project artifact storage is not configured.",
            )
        return insert_cli_project_revision(
            payload,
            owner,
            expected_revision_id=request.parent_revision_id,
        )
    except CliProjectConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except UnsupportedHardwareIRVersion as exc:
        raise HTTPException(
            status_code=status.HTTP_426_UPGRADE_REQUIRED,
            detail={
                "code": "UNSUPPORTED_HARDWARE_IR_VERSION",
                "message": str(exc),
                "hardware_ir_version": exc.version,
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def _revision_artifact(project_id: str, revision_id: str, owner: str, artifact_sha256: str) -> tuple[dict[str, Any], dict[str, Any]]:
    revision = get_cli_project_revision(project_id, owner, revision_id)
    if revision is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cloud project artifact not found or not authorized.",
        )
    try:
        manifest = ProjectManifest.from_document(revision.get("manifest") or {})
        artifacts = validate_artifact_references(manifest.artifacts, require_integrity=True)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    normalized_sha256 = str(artifact_sha256 or "").strip().lower()
    for artifact in artifacts:
        if artifact.get("sha256") == normalized_sha256:
            return revision, artifact
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="The requested artifact is not declared by this cloud revision.",
    )


@router.put("/{project_id}/revisions/{revision_id}/artifacts/{artifact_sha256}")
async def upload_cli_project_artifact(
    project_id: str,
    revision_id: str,
    artifact_sha256: str,
    request: Request,
    user: UserContext = Depends(require_user_context),
) -> dict[str, Any]:
    _revision, artifact = _revision_artifact(project_id, revision_id, _owner(user), artifact_sha256)
    try:
        media_type = normalize_artifact_media_type(request.headers.get("content-type"))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Artifact Content-Type is required.") from exc
    if media_type != artifact["media_type"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Artifact media type mismatch for {artifact['path']}: "
                f"expected {artifact['media_type']}, received {media_type}."
            ),
        )

    storage = ProjectArtifactStorage()
    max_bytes = int(storage.config["max_bytes"])
    content_length = request.headers.get("content-length")
    try:
        if content_length is not None:
            declared_length = int(content_length)
            if declared_length < 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Content-Length header.")
            if declared_length > max_bytes:
                raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Project artifact is too large.")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Content-Length header.") from exc
    content_parts: list[bytes] = []
    content_size = 0
    async for chunk in request.stream():
        content_size += len(chunk)
        if content_size > max_bytes:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Project artifact is too large.")
        content_parts.append(chunk)
    content = b"".join(content_parts)
    actual_sha256 = hashlib.sha256(content).hexdigest()
    if actual_sha256 != artifact["sha256"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Artifact hash mismatch for {artifact['path']}: "
                f"expected {artifact['sha256']}, received {actual_sha256}."
            ),
        )
    if artifact.get("size_bytes") is not None and len(content) != artifact["size_bytes"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Artifact size mismatch for {artifact['path']}.",
        )
    try:
        stored = storage.put(project_id, artifact["sha256"], content, artifact["media_type"])
    except ProjectArtifactStorageError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Project artifact storage is unavailable.") from exc
    return {
        "path": artifact["path"],
        "status": "uploaded",
        "sha256": stored.sha256,
        "media_type": stored.media_type,
        "size_bytes": stored.size_bytes,
    }


@router.get("/{project_id}/revisions/{revision_id}/artifacts/{artifact_sha256}")
async def download_cli_project_artifact(
    project_id: str,
    revision_id: str,
    artifact_sha256: str,
    user: UserContext = Depends(require_user_context),
) -> Response:
    _revision, artifact = _revision_artifact(project_id, revision_id, _owner(user), artifact_sha256)
    try:
        stored = ProjectArtifactStorage().get(project_id, artifact["sha256"], artifact["media_type"])
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cloud project artifact is missing.") from exc
    except ProjectArtifactStorageError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cloud project artifact is missing.") from exc
    content = stored.content or b""
    actual_sha256 = hashlib.sha256(content).hexdigest()
    if actual_sha256 != artifact["sha256"]:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Stored cloud artifact {artifact['path']} failed its SHA-256 integrity check.",
        )
    if artifact.get("size_bytes") is not None and len(content) != artifact["size_bytes"]:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Stored cloud artifact {artifact['path']} failed its size check.",
        )
    return Response(
        content=content,
        media_type=artifact["media_type"],
        headers={
            "X-Forma-Artifact-SHA256": artifact["sha256"],
            "X-Forma-Artifact-Size": str(len(content)),
        },
    )


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
