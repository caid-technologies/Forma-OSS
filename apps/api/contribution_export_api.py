"""Admin review and export endpoints for anonymized contribution snapshots."""

from __future__ import annotations

import csv
import io
import json
import logging
import re
import zipfile
from datetime import datetime, timezone
from typing import Any, Literal
from xml.etree import ElementTree as ET

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel

from apps.api.auth import (
    UserContext,
    require_admin_destructive_user_context,
    require_admin_user_context,
)
from blueprint_core.database import (
    list_project_contribution_snapshots,
    review_project_contribution_snapshot,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin-contribution-exports"])

_XML_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_XLSX_COLUMNS = (
    "dataset_record_id",
    "schema_version",
    "sanitization_version",
    "consent_version",
    "permitted_purposes",
    "anonymized_at",
    "reviewed_at",
    "is_valid",
    "component_count",
    "component_categories",
    "component_pin_counts",
    "net_count",
    "net_connection_counts",
    "critical_issue_count",
    "warning_issue_count",
    "payload_json",
)


class AnonymizationReviewRequest(BaseModel):
    status: Literal["approved", "rejected"]


def _attr(record: Any, name: str, default: Any = None) -> Any:
    if isinstance(record, dict):
        return record.get(name, default)
    return getattr(record, name, default)


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _exportable(snapshot: Any) -> bool:
    return bool(
        _attr(snapshot, "contribution_status") == "anonymized"
        and _attr(snapshot, "anonymized_at")
        and _attr(snapshot, "anonymization_review_status", "pending") == "approved"
        and _attr(snapshot, "reviewed_at")
        and isinstance(_attr(snapshot, "payload_json"), dict)
    )


def _public_snapshot(snapshot: Any, *, include_payload: bool = True) -> dict[str, Any]:
    payload = _attr(snapshot, "payload_json", {})
    result = {
        "snapshot_id": str(_attr(snapshot, "id", "")),
        "contribution_status": _attr(snapshot, "contribution_status"),
        "sanitization_version": _attr(snapshot, "sanitization_version"),
        "created_at": _attr(snapshot, "created_at"),
        "sanitized_at": _attr(snapshot, "sanitized_at"),
        "anonymized_at": _attr(snapshot, "anonymized_at"),
        "anonymization_review_status": _attr(snapshot, "anonymization_review_status", "pending"),
        "reviewed_at": _attr(snapshot, "reviewed_at"),
        "exportable": _exportable(snapshot),
    }
    if include_payload:
        result["payload"] = payload if isinstance(payload, dict) else {}
    return result


def contribution_export_inventory(limit: int = 500) -> dict[str, Any]:
    snapshots = list_project_contribution_snapshots(limit)
    public_snapshots = [_public_snapshot(snapshot) for snapshot in snapshots]
    return {
        "counts": {
            "total": len(public_snapshots),
            "pending_review": sum(
                snapshot["contribution_status"] == "anonymized"
                and snapshot["anonymization_review_status"] == "pending"
                for snapshot in public_snapshots
            ),
            "approved": sum(snapshot["anonymization_review_status"] == "approved" for snapshot in public_snapshots),
            "rejected": sum(snapshot["anonymization_review_status"] == "rejected" for snapshot in public_snapshots),
            "exportable": sum(snapshot["exportable"] for snapshot in public_snapshots),
        },
        "snapshots": public_snapshots,
    }


def _dataset_record(snapshot: Any) -> dict[str, Any]:
    payload = _attr(snapshot, "payload_json", {})
    return {
        "dataset_record_id": str(_attr(snapshot, "id", "")),
        "sanitization_version": str(_attr(snapshot, "sanitization_version", "")),
        "anonymized_at": _attr(snapshot, "anonymized_at"),
        "reviewed_at": _attr(snapshot, "reviewed_at"),
        "consent_version": payload.get("consent_version"),
        "permitted_purposes": payload.get("permitted_purposes", []),
        "payload": payload,
    }


def exportable_contribution_records() -> list[dict[str, Any]]:
    snapshots = list_project_contribution_snapshots()
    return [_dataset_record(snapshot) for snapshot in snapshots if _exportable(snapshot)]


def build_contribution_zip(records: list[dict[str, Any]], generated_at: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        manifest_buffer = io.StringIO(newline="")
        writer = csv.writer(manifest_buffer)
        writer.writerow(
            (
                "dataset_record_id",
                "sanitization_version",
                "consent_version",
                "permitted_purposes",
                "anonymized_at",
                "reviewed_at",
                "file",
            )
        )
        for record in records:
            record_id = record["dataset_record_id"]
            path = f"snapshots/{record_id}.json"
            writer.writerow(
                (
                    record_id,
                    record["sanitization_version"],
                    record["consent_version"],
                    ";".join(record["permitted_purposes"] or []),
                    record["anonymized_at"],
                    record["reviewed_at"],
                    path,
                )
            )
            archive.writestr(path, json.dumps(record, indent=2, sort_keys=True) + "\n")
        archive.writestr("manifest.csv", manifest_buffer.getvalue())
        archive.writestr(
            "export.json",
            json.dumps(
                {
                    "schema_version": 1,
                    "generated_at": generated_at,
                    "record_count": len(records),
                    "eligibility": "anonymized and anonymization_review_status=approved",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
    return buffer.getvalue()


def _column_name(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _xlsx_cell(row_number: int, column_number: int, value: Any, *, header: bool = False) -> ET.Element:
    attributes = {"r": f"{_column_name(column_number)}{row_number}"}
    if header:
        attributes["s"] = "1"
    cell = ET.Element("c", attributes)
    if isinstance(value, bool):
        cell.set("t", "b")
        ET.SubElement(cell, "v").text = "1" if value else "0"
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        cell.set("t", "n")
        ET.SubElement(cell, "v").text = str(value)
    else:
        cell.set("t", "inlineStr")
        inline = ET.SubElement(cell, "is")
        text = ET.SubElement(inline, "t")
        text.text = _XML_CONTROL_CHARACTERS.sub("", "" if value is None else str(value))[:32767]
    return cell


def _xlsx_row(record: dict[str, Any]) -> dict[str, Any]:
    payload = record["payload"]
    hardware = payload.get("hardware_summary") if isinstance(payload.get("hardware_summary"), dict) else {}
    validation = hardware.get("validation_counts") if isinstance(hardware.get("validation_counts"), dict) else {}
    return {
        "dataset_record_id": record["dataset_record_id"],
        "schema_version": payload.get("schema_version"),
        "sanitization_version": record["sanitization_version"],
        "consent_version": record["consent_version"],
        "permitted_purposes": ";".join(record["permitted_purposes"] or []),
        "anonymized_at": record["anonymized_at"],
        "reviewed_at": record["reviewed_at"],
        "is_valid": bool(hardware.get("is_valid")),
        "component_count": hardware.get("component_count", 0),
        "component_categories": json.dumps(hardware.get("component_categories", {}), sort_keys=True),
        "component_pin_counts": json.dumps(hardware.get("component_pin_counts", [])),
        "net_count": hardware.get("net_count", 0),
        "net_connection_counts": json.dumps(hardware.get("net_connection_counts", [])),
        "critical_issue_count": validation.get("critical", 0),
        "warning_issue_count": validation.get("warnings", 0),
        "payload_json": json.dumps(payload, sort_keys=True),
    }


def build_contribution_xlsx(records: list[dict[str, Any]]) -> bytes:
    spreadsheet_namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    ET.register_namespace("", spreadsheet_namespace)
    worksheet = ET.Element(f"{{{spreadsheet_namespace}}}worksheet")
    views = ET.SubElement(worksheet, f"{{{spreadsheet_namespace}}}sheetViews")
    view = ET.SubElement(views, f"{{{spreadsheet_namespace}}}sheetView", {"workbookViewId": "0"})
    ET.SubElement(view, f"{{{spreadsheet_namespace}}}pane", {"ySplit": "1", "topLeftCell": "A2", "state": "frozen"})
    sheet_data = ET.SubElement(worksheet, f"{{{spreadsheet_namespace}}}sheetData")
    header_row = ET.SubElement(sheet_data, f"{{{spreadsheet_namespace}}}row", {"r": "1"})
    for column_number, column in enumerate(_XLSX_COLUMNS, 1):
        header_row.append(_xlsx_cell(1, column_number, column, header=True))
    for row_number, record in enumerate(records, 2):
        row_values = _xlsx_row(record)
        row = ET.SubElement(sheet_data, f"{{{spreadsheet_namespace}}}row", {"r": str(row_number)})
        for column_number, column in enumerate(_XLSX_COLUMNS, 1):
            row.append(_xlsx_cell(row_number, column_number, row_values.get(column)))
    if records:
        ET.SubElement(
            worksheet,
            f"{{{spreadsheet_namespace}}}autoFilter",
            {"ref": f"A1:{_column_name(len(_XLSX_COLUMNS))}{len(records) + 1}"},
        )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>""",
        )
        archive.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="Contributions" sheetId="1" r:id="rId1"/></sheets>
</workbook>""",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "xl/styles.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2"><font/><font><b/></font></fonts>
  <fills count="1"><fill><patternFill patternType="none"/></fill></fills>
  <borders count="1"><border/></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>
</styleSheet>""",
        )
        archive.writestr("xl/worksheets/sheet1.xml", ET.tostring(worksheet, encoding="utf-8", xml_declaration=True))
    return buffer.getvalue()


@router.get("/contribution-snapshots")
def list_contribution_snapshots_endpoint(
    response: Response,
    limit: int = Query(500, ge=1, le=500),
    _user: UserContext = Depends(require_admin_user_context),
):
    response.headers["Cache-Control"] = "no-store"
    return contribution_export_inventory(limit)


@router.put("/contribution-snapshots/{snapshot_id}/anonymization-review")
def review_contribution_snapshot_endpoint(
    snapshot_id: str,
    request: AnonymizationReviewRequest,
    user: UserContext = Depends(require_admin_destructive_user_context),
):
    reviewed = review_project_contribution_snapshot(
        snapshot_id,
        request.status,
        _utc_timestamp(),
        user.owner_user_id or user.subject or "",
    )
    if not reviewed:
        raise HTTPException(status_code=409, detail="Only anonymized contribution snapshots can be reviewed.")
    logger.info("Contribution snapshot anonymization review completed; snapshot_id=%s status=%s", snapshot_id, request.status)
    return _public_snapshot(reviewed)


@router.get("/contribution-exports")
def download_contribution_export_endpoint(
    format: Literal["xlsx", "zip"] = Query("zip"),
    _user: UserContext = Depends(require_admin_user_context),
):
    records = exportable_contribution_records()
    generated_at = _utc_timestamp()
    filename_timestamp = generated_at.replace("-", "").replace(":", "").split(".", 1)[0]
    if format == "xlsx":
        content = build_contribution_xlsx(records)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        content = build_contribution_zip(records, generated_at)
        media_type = "application/zip"
    filename = f"forma-consented-contributions-{filename_timestamp}.{format}"
    logger.info("Contribution dataset exported; format=%s record_count=%d", format, len(records))
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Contribution-Record-Count": str(len(records)),
        },
    )
