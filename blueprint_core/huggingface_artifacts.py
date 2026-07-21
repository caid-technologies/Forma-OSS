from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional


DEFAULT_HF_REPO_TYPE = "dataset"
DEFAULT_HF_ARTIFACT_PREFIX = "blueprint"
HF_TOKEN_ENV_NAMES = ("HF_TOKEN", "HUGGINGFACE_API_KEY", "HUGGINGFACE_HUB_TOKEN", "HF_API_TOKEN")
HF_REPO_ENV_NAMES = ("HF_ARTIFACT_REPO_ID", "HUGGINGFACE_ARTIFACT_REPO_ID", "HF_DATASET_REPO_ID")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def first_env(names: Iterable[str]) -> Optional[str]:
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return None


def path_from_repo(value: str | Path, *, root_dir: str | Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return Path(root_dir).resolve() / path


def normalize_repo_path(value: str) -> str:
    normalized = str(value).replace("\\", "/").strip("/")
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    return normalized


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_artifact_path(path: Path, root_dir: Path) -> str:
    try:
        return normalize_repo_path(str(path.resolve().relative_to(root_dir.resolve())))
    except ValueError:
        return normalize_repo_path(path.name)


@dataclass(frozen=True)
class HuggingFaceArtifact:
    local_path: Path
    path_in_repo: str
    artifact_type: str
    size_bytes: int
    sha256: str

    @classmethod
    def from_path(
        cls,
        path: Path,
        *,
        artifact_type: str,
        path_prefix: str,
        root_dir: Path,
    ) -> "HuggingFaceArtifact":
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Artifact file not found: {path}")
        relative = _relative_artifact_path(path, root_dir)
        path_in_repo = normalize_repo_path(f"{path_prefix}/{artifact_type}/{relative}")
        return cls(
            local_path=path,
            path_in_repo=path_in_repo,
            artifact_type=artifact_type,
            size_bytes=path.stat().st_size,
            sha256=sha256_file(path),
        )

    def as_manifest_item(self) -> dict[str, Any]:
        return {
            "artifact_type": self.artifact_type,
            "local_path": str(self.local_path),
            "path_in_repo": self.path_in_repo,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class HuggingFaceUploadConfig:
    repo_id: str
    token: Optional[str] = None
    repo_type: str = DEFAULT_HF_REPO_TYPE
    private: bool = False
    create_repo: bool = True
    path_prefix: str = DEFAULT_HF_ARTIFACT_PREFIX
    commit_message: str = "Upload Forma artifacts"

    @classmethod
    def from_env(
        cls,
        *,
        repo_id: Optional[str] = None,
        token: Optional[str] = None,
        repo_type: Optional[str] = None,
        private: bool = False,
        create_repo: bool = True,
        path_prefix: Optional[str] = None,
        commit_message: Optional[str] = None,
    ) -> "HuggingFaceUploadConfig":
        resolved_repo_id = repo_id or first_env(HF_REPO_ENV_NAMES)
        if not resolved_repo_id:
            raise ValueError(
                "Hugging Face artifact upload requires --hf-repo-id or HF_ARTIFACT_REPO_ID."
            )
        resolved_token = token or first_env(HF_TOKEN_ENV_NAMES)
        if not resolved_token:
            raise ValueError(
                "Hugging Face artifact upload requires HF_TOKEN, HUGGINGFACE_API_KEY, or HUGGINGFACE_HUB_TOKEN."
            )
        return cls(
            repo_id=resolved_repo_id,
            token=resolved_token,
            repo_type=repo_type or os.getenv("HF_ARTIFACT_REPO_TYPE", DEFAULT_HF_REPO_TYPE),
            private=private,
            create_repo=create_repo,
            path_prefix=path_prefix or os.getenv("HF_ARTIFACT_PATH_PREFIX", DEFAULT_HF_ARTIFACT_PREFIX),
            commit_message=commit_message or "Upload Forma artifacts",
        )


@dataclass(frozen=True)
class HuggingFaceUploadedFile:
    artifact: HuggingFaceArtifact
    commit_url: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        payload = self.artifact.as_manifest_item()
        payload["commit_url"] = self.commit_url
        return payload


@dataclass(frozen=True)
class HuggingFaceUploadResult:
    repo_id: str
    repo_type: str
    path_prefix: str
    uploaded_at: str
    uploaded_files: list[HuggingFaceUploadedFile] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.uploaded_files)

    def as_dict(self) -> dict[str, Any]:
        return {
            "repo_id": self.repo_id,
            "repo_type": self.repo_type,
            "path_prefix": self.path_prefix,
            "uploaded_at": self.uploaded_at,
            "count": self.count,
            "uploaded_files": [item.as_dict() for item in self.uploaded_files],
        }


def build_artifacts(
    paths: Iterable[str | Path],
    *,
    artifact_type: str,
    path_prefix: str,
    root_dir: str | Path,
) -> list[HuggingFaceArtifact]:
    root_path = Path(root_dir).resolve()
    artifacts: list[HuggingFaceArtifact] = []
    seen: set[Path] = set()
    for raw_path in paths:
        path = path_from_repo(raw_path, root_dir=root_path).resolve()
        if path in seen:
            continue
        if not path.exists() or not path.is_file():
            continue
        seen.add(path)
        artifacts.append(
            HuggingFaceArtifact.from_path(
                path,
                artifact_type=artifact_type,
                path_prefix=path_prefix,
                root_dir=root_path,
            )
        )
    return artifacts


def upload_artifacts_to_huggingface(
    artifacts: Iterable[HuggingFaceArtifact],
    *,
    config: HuggingFaceUploadConfig,
) -> HuggingFaceUploadResult:
    artifact_list = list(artifacts)
    if not artifact_list:
        return HuggingFaceUploadResult(
            repo_id=config.repo_id,
            repo_type=config.repo_type,
            path_prefix=config.path_prefix,
            uploaded_at=utc_now(),
            uploaded_files=[],
        )

    try:
        from huggingface_hub import HfApi
    except ImportError as exc:
        raise RuntimeError(
            "huggingface_hub is required for artifact upload. Install with `pip install huggingface_hub`."
        ) from exc

    api = HfApi(token=config.token)
    if config.create_repo:
        api.create_repo(
            repo_id=config.repo_id,
            repo_type=config.repo_type,
            private=config.private,
            exist_ok=True,
        )

    uploaded_files: list[HuggingFaceUploadedFile] = []
    for artifact in artifact_list:
        commit_info = api.upload_file(
            path_or_fileobj=str(artifact.local_path),
            path_in_repo=artifact.path_in_repo,
            repo_id=config.repo_id,
            repo_type=config.repo_type,
            commit_message=config.commit_message,
        )
        uploaded_files.append(
            HuggingFaceUploadedFile(
                artifact=artifact,
                commit_url=str(getattr(commit_info, "commit_url", "") or "") or None,
            )
        )

    return HuggingFaceUploadResult(
        repo_id=config.repo_id,
        repo_type=config.repo_type,
        path_prefix=config.path_prefix,
        uploaded_at=utc_now(),
        uploaded_files=uploaded_files,
    )


__all__ = [
    "DEFAULT_HF_ARTIFACT_PREFIX",
    "DEFAULT_HF_REPO_TYPE",
    "HF_REPO_ENV_NAMES",
    "HF_TOKEN_ENV_NAMES",
    "HuggingFaceArtifact",
    "HuggingFaceUploadConfig",
    "HuggingFaceUploadResult",
    "HuggingFaceUploadedFile",
    "build_artifacts",
    "upload_artifacts_to_huggingface",
]
