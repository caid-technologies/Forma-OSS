"""Versioned findings emitted by revision-bound validation workers."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


VALIDATION_REPORT_SCHEMA_VERSION = "1.0"
NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ValidationCheckStatus(str, Enum):
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"
    SKIPPED = "skipped"


class ValidationSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class ValidationFindingKind(str, Enum):
    CONSTRAINT = "constraint"
    CONSISTENCY = "consistency"
    ASSUMPTION = "assumption"
    CRITERION = "criterion"
    REQUESTED_CHECK = "requested_check"


class ValidationFindingDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion_id: NonEmptyString
    criterion: NonEmptyString
    kind: ValidationFindingKind
    status: ValidationCheckStatus
    severity: ValidationSeverity
    affected_artifact_id: NonEmptyString | None = None
    evidence: list[NonEmptyString] = Field(min_length=1)
    remediation: NonEmptyString
    metadata: dict[str, Any] = Field(default_factory=dict)


class ValidationReportDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    findings: list[ValidationFindingDraft] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_criteria(self) -> "ValidationReportDraft":
        criterion_ids = [item.criterion_id for item in self.findings]
        if len(criterion_ids) != len(set(criterion_ids)):
            raise ValueError("Validation finding criterion_id values must be unique within a report.")
        return self


class ValidationFinding(ValidationFindingDraft):
    finding_id: UUID
    report_id: UUID
    project_id: UUID
    project_revision: int = Field(ge=1)
    design_brief_id: UUID
    design_brief_version: int = Field(ge=1)
    created_at: datetime


class ValidationReportSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int = Field(ge=1)
    passed: int = Field(ge=0)
    warnings: int = Field(ge=0)
    failed: int = Field(ge=0)
    skipped: int = Field(ge=0)


class ValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = VALIDATION_REPORT_SCHEMA_VERSION
    report_id: UUID
    project_id: UUID
    owner_user_id: NonEmptyString
    project_revision: int = Field(ge=1)
    design_brief_id: UUID
    design_brief_version: int = Field(ge=1)
    source_job_id: NonEmptyString
    revalidation_of_report_id: UUID | None = None
    findings: list[ValidationFinding] = Field(min_length=1)
    summary: ValidationReportSummary
    created_at: datetime

    @model_validator(mode="after")
    def require_matching_findings_and_summary(self) -> "ValidationReport":
        finding_ids = [item.finding_id for item in self.findings]
        criterion_ids = [item.criterion_id for item in self.findings]
        if len(finding_ids) != len(set(finding_ids)) or len(criterion_ids) != len(set(criterion_ids)):
            raise ValueError("Validation report finding and criterion identities must be unique.")
        for finding in self.findings:
            if (
                finding.report_id != self.report_id
                or finding.project_id != self.project_id
                or finding.project_revision != self.project_revision
                or finding.design_brief_id != self.design_brief_id
                or finding.design_brief_version != self.design_brief_version
            ):
                raise ValueError("Validation finding identity must match its report.")
        counts = {
            "total": len(self.findings),
            "passed": sum(item.status == ValidationCheckStatus.PASSED for item in self.findings),
            "warnings": sum(item.status == ValidationCheckStatus.WARNING for item in self.findings),
            "failed": sum(item.status == ValidationCheckStatus.FAILED for item in self.findings),
            "skipped": sum(item.status == ValidationCheckStatus.SKIPPED for item in self.findings),
        }
        if self.summary.model_dump() != counts:
            raise ValueError("Validation report summary must match its findings.")
        return self


class ValidationReportOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report: ValidationReport
    idempotent_replay: bool = False


__all__ = [
    "VALIDATION_REPORT_SCHEMA_VERSION",
    "ValidationCheckStatus",
    "ValidationFinding",
    "ValidationFindingDraft",
    "ValidationFindingKind",
    "ValidationReport",
    "ValidationReportDraft",
    "ValidationReportOutcome",
    "ValidationReportSummary",
    "ValidationSeverity",
]
