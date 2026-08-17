"""Atomic persistence boundary for revision-bound validation findings."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import UUID, uuid4

from forma_core.workspaces.projects import ProjectRevision
from forma_core.workspaces.validation.models import (
    ValidationCheckStatus,
    ValidationFinding,
    ValidationReport,
    ValidationReportDraft,
    ValidationReportOutcome,
    ValidationReportSummary,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ValidationReportRepository(Protocol):
    def get_project_revision(
        self,
        project_id: str,
        owner_user_id: str,
        revision: int,
    ) -> Any | None: ...

    def get_validation_report(self, report_id: str, owner_user_id: str) -> Any | None: ...

    def get_validation_report_by_source_job(
        self,
        project_id: str,
        owner_user_id: str,
        source_job_id: str,
    ) -> Any | None: ...

    def insert_project_validation_report(self, record: dict[str, Any]) -> Any | None: ...


class ValidationReportError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.context = context or {}


def _report_from_record(record: Any) -> ValidationReport:
    payload = getattr(record, "payload_json", None)
    if not isinstance(payload, dict):
        raise ValidationReportError(
            "invalid_persisted_validation_report",
            "Persisted validation report payload_json must be an object.",
        )
    return ValidationReport.model_validate(payload)


class ValidationReportService:
    def __init__(self, repository: ValidationReportRepository) -> None:
        self._repository = repository

    def get(self, report_id: str | UUID, owner_user_id: str) -> ValidationReport:
        record = self._repository.get_validation_report(str(report_id), owner_user_id)
        if record is None:
            raise ValidationReportError("validation_report_not_found", "Validation report not found.")
        return _report_from_record(record)

    def get_by_source_job(
        self,
        project_id: str | UUID,
        owner_user_id: str,
        source_job_id: str,
    ) -> ValidationReport | None:
        record = self._repository.get_validation_report_by_source_job(
            str(project_id), owner_user_id, source_job_id
        )
        return _report_from_record(record) if record is not None else None

    def create_report(
        self,
        draft: ValidationReportDraft,
        revision: ProjectRevision,
        *,
        owner_user_id: str,
        source_job_id: str,
        revalidation_of_report_id: str | UUID | None = None,
    ) -> ValidationReportOutcome:
        owner = str(owner_user_id or "").strip()
        source_job = str(source_job_id or "").strip()
        if owner != revision.owner_user_id or not source_job:
            raise ValidationReportError(
                "validation_report_identity_mismatch",
                "Validation report owner and source job must match the project revision execution context.",
            )

        replay = self.get_by_source_job(revision.project_id, owner, source_job)
        if replay is not None:
            self._require_revision_identity(replay, revision)
            return ValidationReportOutcome(report=replay, idempotent_replay=True)

        parent_report_id: UUID | None = None
        if revalidation_of_report_id is not None:
            parent = self.get(revalidation_of_report_id, owner)
            if parent.project_id != revision.project_id or parent.project_revision >= revision.revision:
                raise ValidationReportError(
                    "invalid_revalidation_parent",
                    "Revalidation must reference an older report for the same project.",
                )
            parent_report_id = parent.report_id

        exact_revision = self._repository.get_project_revision(
            str(revision.project_id), owner, revision.revision
        )
        if exact_revision is None:
            raise ValidationReportError(
                "project_revision_not_found",
                "The exact project revision is not available for validation.",
            )

        now = _utc_now()
        report_id = uuid4()
        findings = [
            ValidationFinding(
                **finding.model_dump(),
                finding_id=uuid4(),
                report_id=report_id,
                project_id=revision.project_id,
                project_revision=revision.revision,
                design_brief_id=revision.design_brief_id,
                design_brief_version=revision.design_brief_version,
                created_at=now,
            )
            for finding in draft.findings
        ]
        summary = ValidationReportSummary(
            total=len(findings),
            passed=sum(item.status == ValidationCheckStatus.PASSED for item in findings),
            warnings=sum(item.status == ValidationCheckStatus.WARNING for item in findings),
            failed=sum(item.status == ValidationCheckStatus.FAILED for item in findings),
            skipped=sum(item.status == ValidationCheckStatus.SKIPPED for item in findings),
        )
        report = ValidationReport(
            report_id=report_id,
            project_id=revision.project_id,
            owner_user_id=owner,
            project_revision=revision.revision,
            design_brief_id=revision.design_brief_id,
            design_brief_version=revision.design_brief_version,
            source_job_id=source_job,
            revalidation_of_report_id=parent_report_id,
            findings=findings,
            summary=summary,
            created_at=now,
        )
        record = {
            "id": str(report.report_id),
            "project_id": str(report.project_id),
            "owner_user_id": owner,
            "project_revision": report.project_revision,
            "design_brief_id": str(report.design_brief_id),
            "design_brief_version": report.design_brief_version,
            "source_job_id": source_job,
            "revalidation_of_report_id": str(parent_report_id) if parent_report_id else None,
            "payload_json": report.model_dump(mode="json"),
            "created_at": now.isoformat(),
        }
        saved = self._repository.insert_project_validation_report(record)
        if saved is not None:
            return ValidationReportOutcome(report=_report_from_record(saved))

        replay = self.get_by_source_job(revision.project_id, owner, source_job)
        if replay is not None:
            self._require_revision_identity(replay, revision)
            return ValidationReportOutcome(report=replay, idempotent_replay=True)
        raise ValidationReportError(
            "validation_report_conflict",
            "Project revision changed before validation findings could be persisted.",
            retryable=True,
            context={"project_id": str(revision.project_id), "revision": revision.revision},
        )

    @staticmethod
    def _require_revision_identity(report: ValidationReport, revision: ProjectRevision) -> None:
        if (
            report.project_id != revision.project_id
            or report.project_revision != revision.revision
            or report.design_brief_id != revision.design_brief_id
            or report.design_brief_version != revision.design_brief_version
        ):
            raise ValidationReportError(
                "validation_report_idempotency_conflict",
                "The source job is already attached to a different project revision or DesignBrief.",
            )


__all__ = [
    "ValidationReportError",
    "ValidationReportRepository",
    "ValidationReportService",
]
