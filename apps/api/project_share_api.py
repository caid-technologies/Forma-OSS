"""Capability links grant read-only access to one explicitly shared revision."""
from __future__ import annotations

import hashlib
import hmac
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel

from apps.api.auth import UserContext, require_user_context
from apps.api.project_history_api import RevisionSnapshot, _cad_response, _owner, _revision, _snapshot
from forma_core.config import config
from forma_core.database import get_project_identity
from forma_core.workspaces.projects.state import ProjectRevision

router = APIRouter(prefix="/projects/{project_id}/shared", tags=["project-sharing"])


class ShareLink(BaseModel):
    """A version-scoped capability; never grants access to chat or history."""

    revision_id: UUID
    token: str


def _signature(project_id: UUID, revision_id: UUID, owner: str) -> str:
    """Sign one owner/project/revision tuple using a stable deployment key."""
    secret = config.optional("FORMA_PROJECT_SHARE_SECRET") or ""
    if len(secret.encode()) < 32:
        raise HTTPException(status_code=503, detail="Project sharing is not configured.")
    message = f"forma-project-share:v1:{owner}:{project_id}:{revision_id}"
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def _shared_revision(project_id: UUID, revision_id: UUID, token: str | None) -> ProjectRevision:
    """Reject missing, altered, cross-version, and deleted-project capabilities."""
    identity = get_project_identity(str(project_id))
    owner = str((identity or {}).get("owner_user_id") or "")
    if not identity or not owner or identity.get("status", "active") != "active" or not token:
        raise HTTPException(status_code=404, detail="Shared version unavailable.")
    expected = _signature(project_id, revision_id, owner)
    if not hmac.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(status_code=404, detail="Shared version unavailable.")
    return _revision(project_id, revision_id, owner)


@router.post("/{revision_id}", response_model=ShareLink)
def create_share_link(
    project_id: UUID, revision_id: UUID, response: Response,
    user: UserContext = Depends(require_user_context),
) -> ShareLink:
    """Only the owner may issue a link for an existing saved revision."""
    owner = _owner(project_id, user)
    _revision(project_id, revision_id, owner)
    response.headers["Cache-Control"] = "private, no-store"
    return ShareLink(revision_id=revision_id, token=_signature(project_id, revision_id, owner))


@router.get("/{revision_id}", response_model=RevisionSnapshot)
def get_shared_snapshot(
    project_id: UUID, revision_id: UUID, response: Response,
    x_project_share: str | None = Header(None),
) -> RevisionSnapshot:
    """Expose the design only; omit conversation, provenance, and other history."""
    revision = _shared_revision(project_id, revision_id, x_project_share)
    snapshot = _snapshot(project_id, revision_id, revision, response)
    metadata = snapshot.project_ir.get("assembly_metadata") or {}
    # Generation metadata may contain chat IDs, prompts, and uploaded references.
    allowed = {"project_id", "canonical_revision_id", "project_revision", "image_features"}
    allowed.update(f"product{view}_image_{field}" for view in ("", "_case", "_hero", "_exploded", "_diagram")
                   for field in ("url", "data", "content_type"))
    public_metadata = {key: value for key, value in metadata.items() if key in allowed}
    sequence = metadata.get("product_visual_sequence")
    if isinstance(sequence, list):
        public_metadata["product_visual_sequence"] = [
            {key: item[key] for key in ("view_id", "label", "url", "data", "content_type") if key in item}
            for item in sequence if isinstance(item, dict)
        ]
    snapshot.project_ir["assembly_metadata"] = public_metadata
    snapshot.project_ir["project_version_history"] = []
    snapshot.summary = f"Shared project version {revision.revision}"
    snapshot.parent_revision = None
    cad = snapshot.project_ir.get("cad_model")
    if isinstance(cad, dict) and cad.get("stored_sha256"):
        cad["signed_url"] = f"/api/projects/{project_id}/shared/{revision_id}/cad/{cad['stored_sha256']}"
    return snapshot


@router.get("/{revision_id}/cad/{sha256}")
def get_shared_cad(
    project_id: UUID, revision_id: UUID, sha256: str,
    x_project_share: str | None = Header(None),
) -> Response:
    """Authorize the exact shared revision before serving its verified CAD."""
    return _cad_response(project_id, _shared_revision(project_id, revision_id, x_project_share), sha256)
