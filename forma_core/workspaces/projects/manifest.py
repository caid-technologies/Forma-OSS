"""Portable project manifests used by the local-first Forma CLI."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


PROJECT_MANIFEST_FORMAT = "forma-project"
PROJECT_MANIFEST_VERSION = 1
_SECRET_FIELD_MARKERS = (
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
    "token",
)


def _is_secret_field(name: object) -> bool:
    normalized = str(name).strip().lower().replace("-", "_")
    return normalized in {"key", "credential", "credentials"} or any(
        marker in normalized for marker in _SECRET_FIELD_MARKERS
    )


def redact_project_secrets(value: Any) -> Any:
    """Return a JSON-compatible copy without credential-like fields."""
    if isinstance(value, Mapping):
        return {
            str(key): redact_project_secrets(item)
            for key, item in value.items()
            if not _is_secret_field(key)
        }
    if isinstance(value, list):
        return [redact_project_secrets(item) for item in value]
    if isinstance(value, tuple):
        return [redact_project_secrets(item) for item in value]
    return deepcopy(value)


class ProjectArtifactReference(BaseModel):
    model_config = ConfigDict(extra="allow")

    path: str
    sha256: str | None = None
    media_type: str | None = None


class ProjectManifest(BaseModel):
    """Canonical, uploadable representation of one local Forma project."""

    model_config = ConfigDict(extra="allow")

    format: str = PROJECT_MANIFEST_FORMAT
    version: int = Field(default=PROJECT_MANIFEST_VERSION, ge=1)
    project_id: str = Field(min_length=1)
    workspace_id: str | None = None
    title: str = ""
    prompt: str = ""
    project_ir: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[ProjectArtifactReference] = Field(default_factory=list)

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> "ProjectManifest":
        """Accept both the canonical wrapper and legacy raw HardwareIR JSON."""
        raw = dict(document)
        nested = raw.get("project_ir") or raw.get("hardware_ir")
        project_ir = dict(nested) if isinstance(nested, Mapping) else raw
        metadata = project_ir.get("assembly_metadata")
        metadata = metadata if isinstance(metadata, Mapping) else {}
        project_id = raw.get("project_id") or metadata.get("project_id") or str(uuid4())
        overview = project_ir.get("overview")
        overview = overview if isinstance(overview, Mapping) else {}
        title = raw.get("title") or overview.get("title") or "Untitled Forma Project"
        prompt = raw.get("prompt") or metadata.get("project_prompt") or ""
        artifact_values = []
        for item in raw.get("artifacts") or []:
            if not isinstance(item, Mapping):
                continue
            artifact = dict(item)
            artifact.setdefault("path", artifact.get("uri") or artifact.get("name") or "")
            artifact_values.append(artifact)
        return cls(
            format=str(raw.get("format") or PROJECT_MANIFEST_FORMAT),
            version=int(raw.get("version") or PROJECT_MANIFEST_VERSION),
            project_id=str(project_id),
            workspace_id=str(raw["workspace_id"]) if raw.get("workspace_id") else None,
            title=str(title),
            prompt=str(prompt),
            project_ir=project_ir,
            artifacts=[ProjectArtifactReference.model_validate(item) for item in artifact_values],
        )

    def upload_payload(self) -> dict[str, Any]:
        """Build the only payload shape that may cross the cloud boundary."""
        payload = self.model_dump(mode="json")
        payload["project_ir"] = redact_project_secrets(payload["project_ir"])
        payload["artifacts"] = redact_project_secrets(payload["artifacts"])
        return payload


def load_project_manifest(path: str | Path) -> ProjectManifest:
    project_path = Path(path)
    with project_path.open(encoding="utf-8") as file:
        document = json.load(file)
    if not isinstance(document, Mapping):
        raise ValueError(f"Project manifest must contain a JSON object: {project_path}")
    return ProjectManifest.from_document(document)


def write_project_manifest(path: str | Path, manifest: ProjectManifest) -> None:
    project_path = Path(path)
    safe_payload = redact_project_secrets(manifest.model_dump(mode="json"))
    project_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = project_path.with_suffix(f"{project_path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(safe_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(project_path)


__all__ = [
    "PROJECT_MANIFEST_FORMAT",
    "PROJECT_MANIFEST_VERSION",
    "ProjectArtifactReference",
    "ProjectManifest",
    "load_project_manifest",
    "redact_project_secrets",
    "write_project_manifest",
]
