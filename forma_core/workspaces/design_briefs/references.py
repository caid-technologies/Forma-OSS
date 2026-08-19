"""Helpers for uploaded hardware-reference images on a DesignBrief."""

from __future__ import annotations

from typing import Any

from forma_core.workspaces.design_briefs.models import DesignBrief, DesignBriefReference


INLINE_REFERENCE_DATA_KEYS = ("data_url", "inline_data_url")
UPLOADED_IMAGE_KIND = "uploaded_image"


def uploaded_image_payload(brief: DesignBrief) -> tuple[str | None, str | None]:
    """Return the first displayable uploaded image and its media type."""

    for reference in brief.references:
        if str(reference.kind or "").strip().lower() != UPLOADED_IMAGE_KIND:
            continue
        media_type = reference.media_type if isinstance(reference.media_type, str) else None
        metadata = reference.metadata if isinstance(reference.metadata, dict) else {}
        for key in INLINE_REFERENCE_DATA_KEYS:
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip(), media_type
        uri = str(reference.uri or "").strip()
        if uri.startswith(("data:image/", "http://", "https://")):
            return uri, media_type
    return None, None


def prompt_safe_design_brief(brief: DesignBrief) -> DesignBrief:
    """Drop inline image payloads so frozen-brief prompts stay bounded."""

    references: list[DesignBriefReference] = []
    for reference in brief.references:
        metadata = dict(reference.metadata or {})
        stripped = False
        for key in INLINE_REFERENCE_DATA_KEYS:
            if key in metadata:
                metadata.pop(key, None)
                stripped = True
        if stripped:
            metadata["inline_data_supplied"] = True
        references.append(reference.model_copy(update={"metadata": metadata}))
    return brief.model_copy(update={"references": references})


def inline_image_metadata(attachment_data_url: str | None, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata = dict(existing or {})
    if not attachment_data_url:
        return metadata
    metadata["inline_data_supplied"] = True
    metadata["inline_data_length"] = len(attachment_data_url)
    metadata["data_url"] = attachment_data_url
    return metadata
