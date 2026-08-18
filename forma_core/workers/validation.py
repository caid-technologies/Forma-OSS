"""Validation worker for exact canonical project revisions."""

from __future__ import annotations

import inspect
from typing import Any, Awaitable, Callable, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from forma_core.workers.contracts import (
    WORKER_CONTRACT_VERSION,
    NonEmptyString,
    WorkerArtifact,
    WorkerError,
    WorkerProgress,
    WorkerRequest,
    WorkerResult,
    WorkerResultStatus,
)
from forma_core.workers.registry import WorkerCapability, WorkerDefinition
from forma_core.workspaces.design_briefs import DesignBrief
from forma_core.workspaces.projects import ProjectRevision, ProjectStateError, ProjectStateService
from forma_core.workspaces.validation import (
    ValidationReport,
    ValidationReportDraft,
    ValidationReportError,
    ValidationReportOutcome,
    ValidationReportService,
    evaluate_project_revision,
)


VALIDATION_WORKER_ID = "validation-worker"
VALIDATION_CAPABILITY_ID = "project.validate"
VALIDATION_INPUT_VERSION = "project-revision.v1"
VALIDATION_OUTPUT_VERSION = "validation-findings.v1"


class ValidationWorkerPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_checks: list[NonEmptyString] = Field(default_factory=list)
    revalidation_of_report_id: UUID | None = None


class ValidationEngine(Protocol):
    def validate(
        self,
        revision: ProjectRevision,
        design_brief: DesignBrief,
        requested_checks: list[str],
    ) -> ValidationReportDraft | Awaitable[ValidationReportDraft]: ...


class RuleBasedValidationEngine:
    def validate(
        self,
        revision: ProjectRevision,
        design_brief: DesignBrief,
        requested_checks: list[str],
    ) -> ValidationReportDraft:
        return evaluate_project_revision(revision, design_brief, requested_checks or None)


ProgressReporter = Callable[[WorkerProgress], Awaitable[None]]


class ValidationWorker:
    def __init__(
        self,
        project_state: ProjectStateService,
        reports: ValidationReportService,
        engine: ValidationEngine | None = None,
    ) -> None:
        self._project_state = project_state
        self._reports = reports
        self._engine = engine or RuleBasedValidationEngine()

    def worker_definition(self) -> WorkerDefinition:
        return WorkerDefinition(
            worker_id=VALIDATION_WORKER_ID,
            name="Forma Validation Worker",
            worker_version="1.0.0",
            capabilities=[
                WorkerCapability(
                    capability_id=VALIDATION_CAPABILITY_ID,
                    description="Evaluate and persist actionable findings for an exact project revision.",
                    supported_input_versions=[VALIDATION_INPUT_VERSION],
                    supported_output_versions=[VALIDATION_OUTPUT_VERSION],
                )
            ],
        )

    async def execute(self, request: WorkerRequest, report_progress: ProgressReporter) -> WorkerResult:
        try:
            payload = ValidationWorkerPayload.model_validate(request.payload)
            owner = str(request.metadata.get("execution_owner_user_id") or "").strip()
            if not owner:
                raise ValidationReportError(
                    "validation_owner_missing",
                    "Validation execution is missing its owner scope.",
                )
            revision = self._project_state.get_revision(request.project_id, owner, request.project_revision)
            self._require_request_identity(request, revision)
            brief = self._project_state.get_frozen_design_brief(
                request.project_id,
                owner,
                request.design_brief_id,
                request.design_brief_version,
            )
        except ValidationError as exc:
            return _failure_result(
                request,
                ValidationReportError(
                    "invalid_validation_request",
                    "Validation payload is invalid.",
                    context={"validation_errors": exc.errors(include_url=False)},
                ),
                retryable=False,
            )
        except (ProjectStateError, ValidationReportError, ValueError) as exc:
            return _failure_result(request, exc, retryable=False)

        replay = self._reports.get_by_source_job(revision.project_id, owner, request.job_id)
        if replay is not None:
            if not _report_matches_request(replay, request):
                return _failure_result(
                    request,
                    ValidationReportError(
                        "validation_report_idempotency_conflict",
                        "The source job is already attached to a different project revision or DesignBrief.",
                    ),
                    retryable=False,
                )
            return _success_result(request, ValidationReportOutcome(report=replay, idempotent_replay=True))

        try:
            await report_progress(WorkerProgress(
                **_worker_context(request),
                sequence=1,
                status="running",
                percent_complete=20,
                message=f"Evaluating canonical project revision {revision.revision}.",
            ))
            candidate = self._engine.validate(revision, brief, payload.requested_checks)
            draft = await candidate if inspect.isawaitable(candidate) else candidate
            draft = ValidationReportDraft.model_validate(draft)
            await report_progress(WorkerProgress(
                **_worker_context(request),
                sequence=2,
                status="running",
                percent_complete=85,
                message="Persisting revision-bound validation findings.",
            ))
            outcome = self._reports.create_report(
                draft,
                revision,
                owner_user_id=owner,
                source_job_id=request.job_id,
                revalidation_of_report_id=payload.revalidation_of_report_id,
            )
        except ValidationReportError as exc:
            return _failure_result(request, exc, retryable=exc.retryable)
        except Exception as exc:
            return _failure_result(request, exc, retryable=True)
        return _success_result(request, outcome)

    @staticmethod
    def _require_request_identity(request: WorkerRequest, revision: ProjectRevision) -> None:
        if (
            revision.project_id != request.project_id
            or revision.revision != request.project_revision
            or revision.design_brief_id != request.design_brief_id
            or revision.design_brief_version != request.design_brief_version
        ):
            raise ValidationReportError(
                "validation_context_mismatch",
                "Validation request does not match the persisted project revision and DesignBrief identity.",
            )


def build_validation_request(
    revision: ProjectRevision,
    *,
    job_id: str,
    correlation_id: str,
    requested_checks: list[str] | None = None,
    revalidation_of_report_id: str | UUID | None = None,
) -> WorkerRequest:
    """Build a downstream validation or revalidation request without copying project state."""

    return WorkerRequest(
        contract_version=WORKER_CONTRACT_VERSION,
        project_id=revision.project_id,
        project_revision=revision.revision,
        design_brief_id=revision.design_brief_id,
        design_brief_version=revision.design_brief_version,
        job_id=job_id,
        correlation_id=correlation_id,
        worker_id=VALIDATION_WORKER_ID,
        capability_id=VALIDATION_CAPABILITY_ID,
        input_contract_version=VALIDATION_INPUT_VERSION,
        payload=ValidationWorkerPayload(
            requested_checks=requested_checks or [],
            revalidation_of_report_id=revalidation_of_report_id,
        ).model_dump(mode="json"),
    )


def _report_matches_request(report: ValidationReport, request: WorkerRequest) -> bool:
    return (
        report.project_id == request.project_id
        and report.project_revision == request.project_revision
        and report.design_brief_id == request.design_brief_id
        and report.design_brief_version == request.design_brief_version
    )


def _success_result(request: WorkerRequest, outcome: ValidationReportOutcome) -> WorkerResult:
    report = outcome.report
    artifact = WorkerArtifact(
        **_worker_context(request),
        artifact_id=f"validation-report-{report.report_id}",
        kind="validation-report",
        uri=f"forma://projects/{report.project_id}/revisions/{report.project_revision}/validation/{report.report_id}",
        media_type="application/vnd.forma.validation-report+json",
        metadata={
            "project_revision": report.project_revision,
            "finding_count": report.summary.total,
        },
    )
    return WorkerResult(
        **_worker_context(request),
        output_contract_version=VALIDATION_OUTPUT_VERSION,
        status=WorkerResultStatus.SUCCEEDED,
        output={
            "validation_report": report.model_dump(mode="json"),
            "findings": [item.model_dump(mode="json") for item in report.findings],
            "summary": report.summary.model_dump(mode="json"),
            "idempotent_replay": outcome.idempotent_replay,
        },
        artifacts=[artifact],
    )


def _worker_context(request: WorkerRequest) -> dict[str, Any]:
    return request.model_dump(include={
        "contract_version",
        "project_id",
        "project_revision",
        "design_brief_id",
        "design_brief_version",
        "job_id",
        "correlation_id",
        "worker_id",
        "capability_id",
    })


def _failure_result(request: WorkerRequest, exc: Exception, *, retryable: bool) -> WorkerResult:
    context = _worker_context(request)
    error = WorkerError(
        **context,
        code=str(getattr(exc, "code", "validation_failed")),
        message=str(getattr(exc, "message", "") or str(exc) or exc.__class__.__name__),
        retryable=retryable,
        details={
            "exception_type": exc.__class__.__name__,
            "context": dict(getattr(exc, "context", {}) or {}),
        },
    )
    return WorkerResult(
        **context,
        output_contract_version=VALIDATION_OUTPUT_VERSION,
        status=WorkerResultStatus.FAILED,
        error=error,
    )


__all__ = [
    "VALIDATION_CAPABILITY_ID",
    "VALIDATION_INPUT_VERSION",
    "VALIDATION_OUTPUT_VERSION",
    "VALIDATION_WORKER_ID",
    "RuleBasedValidationEngine",
    "ValidationEngine",
    "ValidationWorker",
    "ValidationWorkerPayload",
    "build_validation_request",
]
