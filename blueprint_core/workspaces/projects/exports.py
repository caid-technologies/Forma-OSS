"""Portable project artifact exports for Forma clients and MCP tools."""

from __future__ import annotations

import base64
import hashlib
import re
import unicodedata
from pathlib import Path
from typing import Any, Mapping

from blueprint_core.workspaces.projects.report_views import render_project_screenshot_pdf


PDF_MIME_TYPE = "application/pdf"
SUPPORTED_PROJECT_OUTPUT_FORMATS = ("pdf",)


def _mapping(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json")
        return dumped if isinstance(dumped, dict) else {}
    return dict(value) if isinstance(value, Mapping) else {}


def _single_line(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def render_project_pdf(project_ir: Any) -> bytes:
    """Render INFO, BOM, MECH, WIRE, and DOCS workspace captures as a PDF."""
    return render_project_screenshot_pdf(project_ir)


def project_pdf_filename(project_ir: Any, requested_filename: str | None = None) -> str:
    """Return a safe PDF filename derived from the request or project title."""
    if requested_filename:
        source = re.sub(r"(?i)\.pdf$", "", Path(requested_filename).name)
        suffix = ""
    else:
        overview = _mapping(_mapping(project_ir).get("overview"))
        source = _single_line(overview.get("title")) or "forma_project"
        suffix = "_report"
    normalized = unicodedata.normalize("NFKD", source).encode("ascii", errors="ignore").decode("ascii")
    basename = re.sub(r"[^a-z0-9]+", "_", normalized.lower()).strip("_")[:80] or "forma_project"
    return f"{basename}{suffix}.pdf"


def build_project_pdf_artifact(
    project_ir: Any,
    *,
    requested_filename: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Build a base64 PDF artifact ready for MCP embedded-resource delivery."""
    pdf = render_project_pdf(project_ir)
    digest = hashlib.sha256(pdf).hexdigest()
    filename = project_pdf_filename(project_ir, requested_filename)
    resolved_project_id = _single_line(project_id) or _single_line(
        _mapping(_mapping(project_ir).get("assembly_metadata")).get("project_id")
    )
    resource_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", resolved_project_id).strip("-") or digest[:16]
    return {
        "format": "pdf",
        "filename": filename,
        "mime_type": PDF_MIME_TYPE,
        "size_bytes": len(pdf),
        "sha256": digest,
        "uri": f"forma://artifacts/{resource_id}/{filename}",
        "data_base64": base64.b64encode(pdf).decode("ascii"),
        "views": ["info", "bom", "mech", "wire", "docs"],
        "page_count": 5,
        "rendering": "workspace_screenshots",
    }


def normalize_project_output_formats(value: Any) -> list[str]:
    """Normalize and validate requested additional project output formats."""
    if value is None:
        return []
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, (list, tuple, set)):
        raise ValueError("output_formats must be a list of format names.")
    normalized = []
    for item in values:
        output_format = _single_line(item).lower()
        if output_format not in SUPPORTED_PROJECT_OUTPUT_FORMATS:
            raise ValueError(f"Unsupported project output format: {output_format or item!r}.")
        if output_format not in normalized:
            normalized.append(output_format)
    return normalized


def attach_project_output_artifacts(result: dict[str, Any], output_formats: Any) -> dict[str, Any]:
    """Attach explicitly requested output artifacts to a generation response."""
    formats = normalize_project_output_formats(output_formats)
    if not formats:
        return result
    project_ir = result.get("project_ir")
    if not isinstance(project_ir, Mapping):
        raise ValueError("A generated project_ir object is required for project exports.")
    artifacts = list(result.get("artifacts") or [])
    if "pdf" in formats:
        artifacts.append(build_project_pdf_artifact(project_ir, project_id=result.get("project_id")))
    return {**result, "artifacts": artifacts, "output_formats": formats}


__all__ = [
    "PDF_MIME_TYPE",
    "SUPPORTED_PROJECT_OUTPUT_FORMATS",
    "attach_project_output_artifacts",
    "build_project_pdf_artifact",
    "normalize_project_output_formats",
    "project_pdf_filename",
    "render_project_pdf",
]
