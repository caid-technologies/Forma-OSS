"""Reverse-Engineering worker for bounded, non-mutating artifact inspection."""

from __future__ import annotations

import inspect
from typing import Any, Awaitable, Callable, Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from forma_core.workers.contracts import (
    WORKER_CONTRACT_VERSION,
    WorkerArtifact,
    WorkerError,
    WorkerProgress,
    WorkerRequest,
    WorkerResult,
    WorkerResultStatus,
)
from forma_core.workers.registry import WorkerCapability, WorkerDefinition
from forma_core.workspaces.design_briefs import DesignBrief
from forma_core.workspaces.projects import ProjectStateError, ProjectStateService
from forma_core.workspaces.reverse_engineering import (
    SUPPORTED_IMAGE_MEDIA_TYPES,
    ReverseEngineeringArtifactReference,
    ReverseEngineeringError,
    ReverseEngineeringReport,
    ReverseEngineeringReportDraft,
    inspect_inline_image,
)


REVERSE_ENGINEERING_WORKER_ID = "reverse-engineering-worker"
REVERSE_ENGINEERING_CAPABILITY_ID = "artifact.reverse-engineer"
REVERSE_ENGINEERING_INPUT_VERSION = "artifact-reference.v1"
REVERSE_ENGINEERING_OUTPUT_VERSION = "reverse-engineering-findings.v1"


class ReverseEngineeringWorkerPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact: ReverseEngineeringArtifactReference
    design_brief: DesignBrief


class ReverseEngineeringEngine(Protocol):
    def inspect(
        self,
        artifact: ReverseEngineeringArtifactReference,
        design_brief: DesignBrief,
    ) -> ReverseEngineeringReportDraft | Awaitable[ReverseEngineeringReportDraft]: ...


class InlineImageInspectionEngine:
    """Local baseline that extracts defensible raster evidence without claiming semantic vision."""

    def inspect(
        self,
        artifact: ReverseEngineeringArtifactReference,
        design_brief: DesignBrief,
    ) -> ReverseEngineeringReportDraft:
        return inspect_inline_image(artifact, design_brief)


ProgressReporter = Callable[[WorkerProgress], Awaitable[None]]


class ReverseEngineeringWorker:
    def __init__(
        self,
        project_state: ProjectStateService,
        engine: ReverseEngineeringEngine | None = None,
    ) -> None:
        self._project_state = project_state
        self._engine = engine or InlineImageInspectionEngine()

    def worker_definition(self) -> WorkerDefinition:
        return WorkerDefinition(
            worker_id=REVERSE_ENGINEERING_WORKER_ID,
            name="Forma Reverse-Engineering Worker",
            worker_version="1.0.0",
            capabilities=[WorkerCapability(
                capability_id=REVERSE_ENGINEERING_CAPABILITY_ID,
                description="Inspect a supplied artifact and return evidence-linked structured inferences.",
                supported_input_versions=[REVERSE_ENGINEERING_INPUT_VERSION],
                supported_output_versions=[REVERSE_ENGINEERING_OUTPUT_VERSION],
                metadata={"supported_media_types": sorted(SUPPORTED_IMAGE_MEDIA_TYPES)},
            )],
        )

    async def execute(self, request: WorkerRequest, report_progress: ProgressReporter) -> WorkerResult:
        try:
            payload = ReverseEngineeringWorkerPayload.model_validate(request.payload)
            _require_request_identity(request, payload.design_brief)
            owner = str(request.metadata.get("execution_owner_user_id") or "").strip()
            if not owner:
                raise ReverseEngineeringError(
                    "reverse_engineering_owner_missing",
                    "Reverse-engineering execution is missing its owner scope.",
                )
            payload.design_brief = self._project_state.require_frozen_design_brief(
                payload.design_brief,
                owner,
            )
        except ValidationError as exc:
            errors = [
                {"location": list(item["loc"]), "type": item["type"], "message": item["msg"]}
                for item in exc.errors(include_url=False, include_input=False)
            ]
            return _failure_result(
                request,
                ReverseEngineeringError(
                    "invalid_reverse_engineering_request",
                    "Reverse-engineering payload is invalid.",
                    context={"validation_errors": errors},
                ),
                retryable=False,
            )
        except (ProjectStateError, ReverseEngineeringError, ValueError) as exc:
            return _failure_result(request, exc, retryable=False)

        try:
            await report_progress(WorkerProgress(
                **_worker_context(request),
                sequence=1,
                status="running",
                percent_complete=15,
                message=f"Inspecting artifact {payload.artifact.artifact_id}.",
            ))
            candidate = self._engine.inspect(payload.artifact, payload.design_brief)
            draft = await candidate if inspect.isawaitable(candidate) else candidate
            try:
                draft = ReverseEngineeringReportDraft.model_validate(draft)
            except ValidationError as exc:
                raise ReverseEngineeringError(
                    "invalid_reverse_engineering_output",
                    "Reverse-engineering engine returned an invalid findings contract.",
                    retryable=True,
                    context={"validation_error_count": exc.error_count()},
                ) from exc
            report = ReverseEngineeringReport(
                **draft.model_dump(),
                project_id=request.project_id,
                project_revision=request.project_revision,
                design_brief_id=request.design_brief_id,
                design_brief_version=request.design_brief_version,
            )
            await report_progress(WorkerProgress(
                **_worker_context(request),
                sequence=2,
                status="running",
                percent_complete=90,
                message="Validated evidence links and uncertainty declarations.",
            ))
        except ReverseEngineeringError as exc:
            return _failure_result(request, exc, retryable=exc.retryable)
        except Exception as exc:
            return _failure_result(request, exc, retryable=True)
        return _success_result(request, report)


def build_reverse_engineering_request(
    design_brief: DesignBrief,
    artifact: ReverseEngineeringArtifactReference,
    *,
    project_revision: int,
    job_id: str,
    correlation_id: str,
) -> WorkerRequest:
    return WorkerRequest(
        contract_version=WORKER_CONTRACT_VERSION,
        project_id=design_brief.project_id,
        project_revision=project_revision,
        design_brief_id=design_brief.design_brief_id,
        design_brief_version=design_brief.brief_version,
        job_id=job_id,
        correlation_id=correlation_id,
        worker_id=REVERSE_ENGINEERING_WORKER_ID,
        capability_id=REVERSE_ENGINEERING_CAPABILITY_ID,
        input_contract_version=REVERSE_ENGINEERING_INPUT_VERSION,
        payload=ReverseEngineeringWorkerPayload(
            artifact=artifact,
            design_brief=design_brief,
        ).model_dump(mode="json"),
    )


def _require_request_identity(request: WorkerRequest, brief: DesignBrief) -> None:
    if (
        brief.project_id != request.project_id
        or brief.design_brief_id != request.design_brief_id
        or brief.brief_version != request.design_brief_version
    ):
        raise ReverseEngineeringError(
            "reverse_engineering_context_mismatch",
            "Reverse-engineering request identity does not match its frozen DesignBrief.",
        )


def _success_result(request: WorkerRequest, report: ReverseEngineeringReport) -> WorkerResult:
    context = _worker_context(request)
    artifact = WorkerArtifact(
        **context,
        artifact_id=f"reverse-engineering-{request.job_id}",
        kind="reverse-engineering-findings",
        uri=f"forma://worker-plans/{request.correlation_id}/jobs/{request.job_id}/result",
        media_type="application/vnd.forma.reverse-engineering-findings+json",
        checksum=report.artifact.content_sha256,
        metadata={
            "source_artifact_id": report.artifact.artifact_id,
            "finding_count": len(report.findings),
            "ambiguous": report.ambiguous,
        },
    )
    return WorkerResult(
        **context,
        output_contract_version=REVERSE_ENGINEERING_OUTPUT_VERSION,
        status=WorkerResultStatus.SUCCEEDED,
        output={
            "reverse_engineering_report": report.model_dump(mode="json"),
            "evidence": [item.model_dump(mode="json") for item in report.evidence],
            "findings": [item.model_dump(mode="json") for item in report.findings],
            "ambiguous": report.ambiguous,
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
        code=str(getattr(exc, "code", "reverse_engineering_failed")),
        message=str(getattr(exc, "message", "") or str(exc) or exc.__class__.__name__),
        retryable=retryable,
        details={
            "exception_type": exc.__class__.__name__,
            "context": dict(getattr(exc, "context", {}) or {}),
        },
    )
    return WorkerResult(
        **context,
        output_contract_version=REVERSE_ENGINEERING_OUTPUT_VERSION,
        status=WorkerResultStatus.FAILED,
        error=error,
    )


__all__ = [
    "REVERSE_ENGINEERING_CAPABILITY_ID",
    "REVERSE_ENGINEERING_INPUT_VERSION",
    "REVERSE_ENGINEERING_OUTPUT_VERSION",
    "REVERSE_ENGINEERING_WORKER_ID",
    "InlineImageInspectionEngine",
    "ReverseEngineeringEngine",
    "ReverseEngineeringWorker",
    "ReverseEngineeringWorkerPayload",
    "build_reverse_engineering_request",
]
