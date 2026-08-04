"""Portable project report exports for Forma clients and MCP tools."""

from __future__ import annotations

import base64
import hashlib
import re
import textwrap
import unicodedata
from pathlib import Path
from typing import Any, Iterable, Mapping


PDF_MIME_TYPE = "application/pdf"
SUPPORTED_PROJECT_OUTPUT_FORMATS = ("pdf",)

_PAGE_WIDTH = 612.0
_PAGE_HEIGHT = 792.0
_MARGIN_X = 48.0
_TOP_Y = 744.0
_BOTTOM_Y = 52.0

_STYLE = {
    "title": ("F2", 20.0, 26.0, 10.0),
    "heading": ("F2", 14.0, 19.0, 5.0),
    "subheading": ("F2", 11.0, 15.0, 2.0),
    "body": ("F1", 9.5, 13.0, 2.0),
    "bullet": ("F1", 9.5, 13.0, 1.0),
    "warning": ("F2", 9.5, 13.0, 2.0),
    "small": ("F1", 8.0, 11.0, 1.0),
}


def _mapping(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json")
        return dumped if isinstance(dumped, dict) else {}
    return dict(value) if isinstance(value, Mapping) else {}


def _items(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _single_line(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _money(value: Any) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


def _append_list(lines: list[tuple[str, str]], values: Iterable[Any], *, empty: str | None = None) -> None:
    appended = False
    for value in values:
        text = _single_line(value)
        if text:
            lines.append(("bullet", f"- {text}"))
            appended = True
    if not appended and empty:
        lines.append(("small", empty))


def build_project_report_lines(project_ir: Any) -> list[tuple[str, str]]:
    """Build deterministic styled text lines for a Forma project report."""
    project = _mapping(project_ir)
    overview = _mapping(project.get("overview"))
    requirements = _mapping(project.get("requirements"))
    validation = _mapping(project.get("validation"))
    mechanical = _mapping(project.get("mechanical"))
    title = _single_line(overview.get("title")) or "Untitled Forma Project"

    lines: list[tuple[str, str]] = [
        ("title", title),
        ("small", "Forma Hardware Project Report"),
        ("body", _single_line(overview.get("description")) or "No project description was provided."),
        (
            "small",
            " | ".join(
                part
                for part in (
                    f"Category: {_single_line(overview.get('category'))}" if overview.get("category") else "",
                    f"Difficulty: {_single_line(overview.get('difficulty'))}" if overview.get("difficulty") else "",
                    f"Estimated BOM: {_money(overview.get('estimated_cost'))}",
                    f"IR version: {_single_line(project.get('hardware_ir_version')) or 'unknown'}",
                )
                if part
            ),
        ),
        ("heading", "Requirements and Power"),
    ]
    power_parts = [
        _single_line(requirements.get("power_needs")),
        f"Operating voltage: {_single_line(requirements.get('operating_voltage'))} V"
        if requirements.get("operating_voltage") is not None
        else "",
        f"Estimated peak current: {_single_line(project.get('estimated_current_draw_ma'))} mA"
        if project.get("estimated_current_draw_ma") is not None
        else "",
    ]
    lines.append(("body", " | ".join(part for part in power_parts if part) or "Power requirements were not provided."))
    _append_list(lines, _items(requirements.get("requirements")), empty="No functional requirements were listed.")
    _append_list(lines, _items(requirements.get("physical_constraints")))
    for note in _items(requirements.get("safety_notes")):
        text = _single_line(note)
        if text:
            lines.append(("warning", f"Safety: {text}"))
    for missing in _items(requirements.get("missing_info")):
        text = _single_line(missing)
        if text:
            lines.append(("warning", f"Open question: {text}"))

    lines.append(("heading", "Bill of Materials"))
    components = _items(project.get("components"))
    if not components:
        lines.append(("small", "No components were listed."))
    for component_value in components:
        component = _mapping(component_value)
        ref_des = _single_line(component.get("ref_des")) or "UNREF"
        name = _single_line(component.get("name")) or _single_line(component.get("part_number")) or "Unnamed component"
        part_number = _single_line(component.get("part_number"))
        quantity = component.get("quantity", 1)
        unit_price = _money(component.get("unit_price"))
        lines.append(("subheading", f"{ref_des} - {name}"))
        lines.append(("small", f"Part: {part_number or 'unspecified'} | Qty: {quantity} | Unit estimate: {unit_price}"))
        rationale = _single_line(component.get("rationale"))
        if rationale:
            lines.append(("body", rationale))

    lines.append(("heading", "Electrical Connections"))
    nets = _items(project.get("nets"))
    if not nets:
        lines.append(("small", "No connection nets were listed."))
    for net_value in nets:
        net = _mapping(net_value)
        name = _single_line(net.get("name")) or _single_line(net.get("net_id")) or "Unnamed net"
        details = [_single_line(net.get("net_type"))]
        if net.get("voltage") is not None:
            details.append(f"{_single_line(net.get('voltage'))} V")
        pins = []
        for pin_value in _items(net.get("pins")):
            pin = _mapping(pin_value)
            pin_text = ".".join(filter(None, (_single_line(pin.get("ref_des")), _single_line(pin.get("pin_id")))))
            if pin_text:
                pins.append(pin_text)
        if pins:
            details.append(", ".join(pins))
        lines.append(("bullet", f"- {name}: {' | '.join(filter(None, details))}"))

    lines.append(("heading", "Validation and Safety Audit"))
    critical = _items(validation.get("critical"))
    warnings = _items(validation.get("warning"))
    info = _items(validation.get("info"))
    lines.append(("warning" if critical else "subheading", "BLOCKED - critical issues remain" if critical else "PASS - no critical issues reported"))
    issues = [*critical, *warnings, *info]
    if not issues:
        lines.append(("small", "No validation findings were reported."))
    for issue_value in issues:
        issue = _mapping(issue_value)
        severity = _single_line(issue.get("severity")).upper() or "INFO"
        category = _single_line(issue.get("category")) or "Validation note"
        description = _single_line(issue.get("description"))
        troubleshooting = _single_line(issue.get("troubleshooting"))
        lines.append(("warning" if severity == "CRITICAL" else "subheading", f"{severity} - {category}"))
        if description:
            lines.append(("body", description))
        if troubleshooting:
            lines.append(("small", f"Suggested action: {troubleshooting}"))

    lines.append(("heading", "Assembly Instructions"))
    assembly = _items(project.get("assembly"))
    if not assembly:
        lines.append(("small", "No assembly instructions were listed."))
    for index, step_value in enumerate(assembly, start=1):
        step = _mapping(step_value)
        step_number = step.get("step_num") or index
        step_title = _single_line(step.get("title")) or f"Step {step_number}"
        lines.append(("subheading", f"{step_number}. {step_title}"))
        description = _single_line(step.get("description"))
        if description:
            lines.append(("body", description))
        if step.get("danger_flag"):
            warning = _single_line(step.get("danger_message")) or "Pay close attention to safety constraints during this step."
            lines.append(("warning", f"WARNING: {warning}"))

    if mechanical:
        lines.append(("heading", "Mechanical and Fabrication Notes"))
        enclosure_type = _single_line(mechanical.get("enclosure_type"))
        rating = _single_line(mechanical.get("manufacturability_rating"))
        if enclosure_type or rating:
            lines.append(("body", " | ".join(filter(None, (enclosure_type, f"Manufacturability: {rating}" if rating else "")))))
        mounting = _single_line(mechanical.get("mounting_guidance"))
        if mounting:
            lines.append(("body", mounting))
        _append_list(lines, _items(mechanical.get("fabrication_details")))

    lines.extend(
        [
            ("heading", "Prototype Disclaimer"),
            (
                "warning",
                "This report is an AI-assisted low-voltage prototype plan. Verify component ratings, wiring, sourcing, mechanical clearances, and regulatory requirements before fabrication or power-up.",
            ),
        ]
    )
    return lines


def _pdf_text_bytes(value: str) -> bytes:
    normalized = unicodedata.normalize("NFKD", value).replace("\u2014", "-").replace("\u2013", "-")
    return normalized.encode("cp1252", errors="replace")


def _wrapped_lines(style: str, value: str) -> list[str]:
    _font, font_size, _leading, _after = _STYLE[style]
    usable_width = _PAGE_WIDTH - (2 * _MARGIN_X)
    width = max(24, int(usable_width / (font_size * 0.52)))
    return textwrap.wrap(_single_line(value), width=width, break_long_words=True, break_on_hyphens=True) or [""]


def _paginate(lines: list[tuple[str, str]]) -> list[list[tuple[str, float, float, float, str]]]:
    pages: list[list[tuple[str, float, float, float, str]]] = [[]]
    y = _TOP_Y
    for style, value in lines:
        font, size, leading, after = _STYLE[style]
        wrapped = _wrapped_lines(style, value)
        for index, wrapped_line in enumerate(wrapped):
            if y - leading < _BOTTOM_Y:
                pages.append([])
                y = _TOP_Y
            prefix_indent = 10.0 if style == "bullet" and index > 0 else 0.0
            pages[-1].append((font, size, _MARGIN_X + prefix_indent, y, wrapped_line))
            y -= leading
        y -= after
    return pages


def _content_stream(page: list[tuple[str, float, float, float, str]], page_number: int, page_count: int) -> bytes:
    commands: list[bytes] = []
    for font, size, x, y, value in page:
        encoded = _pdf_text_bytes(value).hex().upper().encode("ascii")
        commands.append(
            b"BT /" + font.encode("ascii") + f" {size:.2f} Tf 1 0 0 1 {x:.2f} {y:.2f} Tm <".encode("ascii") + encoded + b"> Tj ET\n"
        )
    footer = f"Forma prototype report | Page {page_number} of {page_count}"
    footer_hex = _pdf_text_bytes(footer).hex().upper().encode("ascii")
    commands.append(b"BT /F1 7.50 Tf 1 0 0 1 48.00 28.00 Tm <" + footer_hex + b"> Tj ET\n")
    return b"".join(commands)


def render_project_pdf(project_ir: Any) -> bytes:
    """Render a self-contained, text-based PDF report without optional dependencies."""
    pages = _paginate(build_project_report_lines(project_ir))
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
    ]
    page_refs: list[str] = []
    for index, page in enumerate(pages):
        page_object_number = 5 + (index * 2)
        content_object_number = page_object_number + 1
        page_refs.append(f"{page_object_number} 0 R")
        stream = _content_stream(page, index + 1, len(pages))
        page_object = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {_PAGE_WIDTH:.0f} {_PAGE_HEIGHT:.0f}] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {content_object_number} 0 R >>"
        ).encode("ascii")
        content_object = f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"endstream"
        objects.extend((page_object, content_object))
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(page_refs)}] /Count {len(pages)} >>".encode("ascii")

    document = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, payload in enumerate(objects, start=1):
        offsets.append(len(document))
        document.extend(f"{number} 0 obj\n".encode("ascii"))
        document.extend(payload)
        document.extend(b"\nendobj\n")
    xref_offset = len(document)
    document.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    document.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        document.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    document.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(document)


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
    resolved_project_id = _single_line(project_id) or _single_line(_mapping(_mapping(project_ir).get("assembly_metadata")).get("project_id"))
    resource_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", resolved_project_id).strip("-") or digest[:16]
    return {
        "format": "pdf",
        "filename": filename,
        "mime_type": PDF_MIME_TYPE,
        "size_bytes": len(pdf),
        "sha256": digest,
        "uri": f"forma://artifacts/{resource_id}/{filename}",
        "data_base64": base64.b64encode(pdf).decode("ascii"),
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
    "build_project_report_lines",
    "normalize_project_output_formats",
    "project_pdf_filename",
    "render_project_pdf",
]
