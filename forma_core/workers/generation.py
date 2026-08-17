"""Generation worker that turns one frozen DesignBrief into canonical project revision 1."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from forma_core.agents.pipeline import (
    AgentPipelineEvent,
    PipelineCancelledError,
    emit_agent_pipeline_event,
    list_agent_pipeline_steps,
    observe_agent_pipeline,
)
from forma_core.workers.contracts import (
    WorkerArtifact,
    WorkerError,
    WorkerProgress,
    WorkerRequest,
    WorkerResult,
    WorkerResultStatus,
)
from forma_core.workers.registry import WorkerCapability, WorkerDefinition
from forma_core.workspaces.design_briefs import DesignBrief
from forma_core.workspaces.projects import (
    ProjectArtifact,
    ProjectRevisionOutcome,
    ProjectRevisionDraft,
    ProjectStateError,
    ProjectStateService,
    ProjectSystem,
)
from forma_core.workspaces.projects.models import HardwareIR
from forma_core.workspaces.projects.output import attach_product_image


GENERATION_WORKER_ID = "generation-worker"
GENERATION_CAPABILITY_ID = "project.generate"
GENERATION_INPUT_VERSION = "design-brief.v1"
GENERATION_OUTPUT_VERSION = "project-revision.v1"


class GenerationWorkerPayload(BaseModel):
    """The Generation worker accepts no conversational input outside the frozen brief."""

    model_config = ConfigDict(extra="forbid")

    design_brief: DesignBrief


class GenerationEngine(Protocol):
    def generate(self, design_brief: DesignBrief) -> ProjectRevisionDraft | Awaitable[ProjectRevisionDraft]: ...


class HardwareIRGenerationEngine:
    """Adapter for the existing structured pipeline with legacy persistence disabled."""

    def __init__(
        self,
        *,
        provider_name: str | None = None,
        model_name: str | None = None,
        use_simulation: bool = False,
        generate_image: bool = True,
    ) -> None:
        self.provider_name = provider_name
        self.model_name = model_name
        self.use_simulation = use_simulation
        self.generate_image = generate_image

    def generate(self, design_brief: DesignBrief) -> ProjectRevisionDraft:
        from forma_core.agents.orchestrator import HardwarePipelineOrchestrator

        prompt = self._prompt(design_brief)
        orchestrator = HardwarePipelineOrchestrator(
            use_simulation=self.use_simulation,
            provider_name=self.provider_name,
            model_name=self.model_name,
            persist_project=False,
        )
        state = orchestrator.generate_project(
            prompt,
            generation_metadata={
                "project_id": str(design_brief.project_id),
                "design_brief_id": str(design_brief.design_brief_id),
                "design_brief_version": design_brief.brief_version,
            },
        )
        generation_error = (state.assembly_metadata or {}).get("generation_error")
        if generation_error or (state.assembly_metadata or {}).get("status") == "failed":
            message = generation_error.get("message") if isinstance(generation_error, dict) else None
            raise RuntimeError(str(message or "Structured hardware generation failed."))
        if self.generate_image:
            emit_agent_pipeline_event("default", "image_generation", "started")
        attach_product_image(prompt, state, generate_image=self.generate_image)
        if self.generate_image:
            image_status = (state.assembly_metadata or {}).get("image_output_status")
            emit_agent_pipeline_event(
                "default",
                "image_generation",
                "completed" if image_status == "succeeded" else "failed",
                details={
                    "image_output_status": image_status,
                    "provider": (state.assembly_metadata or {}).get("image_output_provider"),
                    "model": (state.assembly_metadata or {}).get("image_output_model"),
                },
            )
        return build_generation_draft(design_brief, state)

    @staticmethod
    def _prompt(design_brief: DesignBrief) -> str:
        return (
            "Generate an initial structured hardware project using only this frozen DesignBrief. "
            "Treat only the references declared inside the brief as reference inputs. Do not infer context "
            "from prior conversation or fetch undeclared sources.\n\n"
            f"Frozen DesignBrief:\n{design_brief.model_dump_json(indent=2)}"
        )


def build_generation_draft(design_brief: DesignBrief, state: HardwareIR) -> ProjectRevisionDraft:
    component_refs = [component.ref_des for component in state.components]
    systems = [
        ProjectSystem(
            system_id="system-primary",
            kind="hardware",
            name=(state.overview.title if state.overview else design_brief.summary),
            component_refs=component_refs,
        )
    ]
    for rail in state.power_rails:
        systems.append(ProjectSystem(
            system_id=f"power-{rail.rail_id}",
            kind="power",
            name=rail.rail_id,
            component_refs=[rail.source_component],
            metadata={"voltage": rail.voltage, "max_current_capacity_ma": rail.max_current_capacity_ma},
        ))
    for bus in state.buses:
        bus_components = sorted({
            pin.ref_des
            for net in state.nets
            if net.net_id in bus.nets
            for pin in net.pins
        })
        systems.append(ProjectSystem(
            system_id=f"bus-{bus.bus_id}",
            kind="bus",
            name=bus.bus_id,
            component_refs=bus_components,
            metadata={"bus_type": bus.bus_type, "net_ids": list(bus.nets)},
        ))

    revision_base = f"forma://projects/{design_brief.project_id}/revisions/1"
    artifacts = [
        ProjectArtifact(
            artifact_id="project-state",
            kind="project-state",
            uri=f"{revision_base}/state",
            media_type="application/vnd.forma.hardware-ir+json",
        )
    ]
    if state.components:
        artifacts.append(ProjectArtifact(
            artifact_id="bill-of-materials",
            kind="bom",
            uri=f"{revision_base}/bom",
            media_type="application/json",
        ))
    if state.nets:
        artifacts.append(ProjectArtifact(
            artifact_id="wiring-netlist",
            kind="wiring",
            uri=f"{revision_base}/wiring",
            media_type="application/json",
        ))
    if state.mechanical is not None:
        artifacts.append(ProjectArtifact(
            artifact_id="mechanical-plan",
            kind="mechanical",
            uri=f"{revision_base}/mechanical",
            media_type="application/json",
        ))
    if state.assembly:
        artifacts.append(ProjectArtifact(
            artifact_id="assembly-guide",
            kind="assembly",
            uri=f"{revision_base}/assembly",
            media_type="application/json",
        ))

    assumptions = list(dict.fromkeys([
        *design_brief.assumptions,
        "Generated component selections and topology remain provisional until validation.",
    ]))
    return ProjectRevisionDraft(
        state=state,
        components=list(state.components),
        systems=systems,
        artifacts=artifacts,
        assumptions=assumptions,
    )


ProgressReporter = Callable[[WorkerProgress], Awaitable[None]]


class GenerationWorker:
    """Registered worker implementation for the `project.generate` capability."""

    def __init__(
        self,
        state_service: ProjectStateService,
        engine: GenerationEngine | None = None,
    ) -> None:
        self._state = state_service
        self._engine = engine or HardwareIRGenerationEngine()

    def worker_definition(self) -> WorkerDefinition:
        return WorkerDefinition(
            worker_id=GENERATION_WORKER_ID,
            name="Forma Generation Worker",
            worker_version="1.0.0",
            capabilities=[
                WorkerCapability(
                    capability_id=GENERATION_CAPABILITY_ID,
                    description="Create initial canonical project state from a frozen DesignBrief.",
                    supported_input_versions=[GENERATION_INPUT_VERSION],
                    supported_output_versions=[GENERATION_OUTPUT_VERSION],
                )
            ],
        )

    async def execute(self, request: WorkerRequest, report_progress: ProgressReporter) -> WorkerResult:
        context = _worker_context(request)
        try:
            payload = GenerationWorkerPayload.model_validate(request.payload)
            _validate_request_identity(request, payload.design_brief)
            owner_user_id = str(request.metadata.get("execution_owner_user_id") or "").strip()
            if not owner_user_id:
                raise ProjectStateError(
                    "generation_owner_missing",
                    "Generation execution is missing its owner scope.",
                )
            payload.design_brief = self._state.require_frozen_design_brief(payload.design_brief, owner_user_id)
        except ValidationError as exc:
            return _failure_result(
                request,
                ProjectStateError("invalid_generation_request", "Generation payload is invalid.", context={
                    "validation_errors": exc.errors(include_url=False),
                }),
                retryable=False,
            )
        except (ProjectStateError, ValueError) as exc:
            return _failure_result(request, exc, retryable=False)

        replay = self._state.get_by_source_job(request.project_id, owner_user_id, request.job_id)
        if replay is not None:
            if (
                replay.design_brief_id != request.design_brief_id
                or replay.design_brief_version != request.design_brief_version
                or replay.revision != request.project_revision
            ):
                return _failure_result(
                    request,
                    ProjectStateError(
                        "project_revision_idempotency_conflict",
                        "The source job is already attached to a different project revision or DesignBrief.",
                    ),
                    retryable=False,
                )
            return _success_result(request, ProjectRevisionOutcome(revision=replay, idempotent_replay=True))

        cancellation_check = request.metadata.get("pipeline_cancellation_check")
        if not callable(cancellation_check):
            cancellation_check = None

        try:
            if cancellation_check is not None and cancellation_check():
                return _cancelled_result(request)
            progress_sequence = 1
            await report_progress(WorkerProgress(
                **context,
                sequence=progress_sequence,
                status="running",
                percent_complete=10,
                message="Generating structured project state from the frozen DesignBrief.",
            ))
            if isinstance(self._engine, HardwareIRGenerationEngine):
                event_loop = asyncio.get_running_loop()

                def generate_with_observation() -> ProjectRevisionDraft:
                    def record_pipeline_event(event: AgentPipelineEvent) -> None:
                        nonlocal progress_sequence
                        if cancellation_check is not None and cancellation_check():
                            raise PipelineCancelledError("Agent pipeline was cancelled.")
                        progress_sequence += 1
                        future = asyncio.run_coroutine_threadsafe(
                            report_progress(WorkerProgress(
                                **context,
                                sequence=progress_sequence,
                                status="running",
                                percent_complete=_pipeline_event_percent(event),
                                message=f"{event.label}: {event.status.replace('_', ' ')}",
                                metadata={"pipeline_event": event.as_dict()},
                            )),
                            event_loop,
                        )
                        future.result()

                    with observe_agent_pipeline(record_pipeline_event, cancellation_check=cancellation_check):
                        return self._engine.generate(payload.design_brief)

                candidate = await asyncio.to_thread(generate_with_observation)
                if cancellation_check is not None and cancellation_check():
                    raise PipelineCancelledError("Agent pipeline was cancelled.")
            else:
                candidate = self._engine.generate(payload.design_brief)
                if hasattr(candidate, "__await__"):
                    candidate = await candidate
            draft = ProjectRevisionDraft.model_validate(candidate)
            progress_sequence += 1
            await report_progress(WorkerProgress(
                **context,
                sequence=progress_sequence,
                status="running",
                percent_complete=80,
                message="Persisting initial project revision.",
            ))
            outcome = self._state.create_initial_revision(
                draft,
                project_id=request.project_id,
                owner_user_id=owner_user_id,
                design_brief_id=request.design_brief_id,
                design_brief_version=request.design_brief_version,
                source_job_id=request.job_id,
            )
        except PipelineCancelledError:
            return _cancelled_result(request)
        except ProjectStateError as exc:
            return _failure_result(request, exc, retryable=exc.retryable)
        except Exception as exc:
            return _failure_result(request, exc, retryable=True)

        return _success_result(request, outcome)


def _pipeline_event_percent(event: AgentPipelineEvent) -> float:
    steps = list_agent_pipeline_steps(event.workflow)
    index = next((index for index, step in enumerate(steps) if step.get("id") == event.step_id), 0)
    completed = index + (1 if event.status in {"completed", "skipped"} else 0)
    return min(75.0, max(10.0, 10.0 + (completed / max(len(steps), 1)) * 65.0))


def _cancelled_result(request: WorkerRequest) -> WorkerResult:
    context = _worker_context(request)
    error = WorkerError(
        **context,
        code="generation_cancelled",
        message="Build stopped by the user.",
        retryable=True,
    )
    return WorkerResult(
        **context,
        output_contract_version=GENERATION_OUTPUT_VERSION,
        status=WorkerResultStatus.CANCELLED,
        error=error,
    )


def _success_result(request: WorkerRequest, outcome: ProjectRevisionOutcome) -> WorkerResult:
    context = _worker_context(request)
    revision = outcome.revision
    artifacts = [
        WorkerArtifact(
            **context,
            artifact_id=artifact.artifact_id,
            kind=artifact.kind,
            uri=artifact.uri,
            media_type=artifact.media_type,
            checksum=artifact.checksum,
            metadata={
                **artifact.metadata,
                "project_revision": revision.revision,
                "design_brief_version": revision.design_brief_version,
            },
        )
        for artifact in revision.artifacts
    ]
    return WorkerResult(
        **context,
        output_contract_version=GENERATION_OUTPUT_VERSION,
        status=WorkerResultStatus.SUCCEEDED,
        output={
            "project_revision": revision.model_dump(mode="json"),
            "components": [item.model_dump(mode="json") for item in revision.components],
            "systems": [item.model_dump(mode="json") for item in revision.systems],
            "artifacts": [item.model_dump(mode="json") for item in revision.artifacts],
            "assumptions": list(revision.assumptions),
            "idempotent_replay": outcome.idempotent_replay,
        },
        artifacts=artifacts,
    )


def _validate_request_identity(request: WorkerRequest, brief: DesignBrief) -> None:
    if (
        brief.project_id != request.project_id
        or brief.design_brief_id != request.design_brief_id
        or brief.brief_version != request.design_brief_version
        or request.project_revision != 1
    ):
        raise ProjectStateError(
            "generation_context_mismatch",
            "Generation request identity does not match its frozen DesignBrief or initial revision.",
            context={
                "request_project_id": str(request.project_id),
                "brief_project_id": str(brief.project_id),
                "request_design_brief_id": str(request.design_brief_id),
                "brief_design_brief_id": str(brief.design_brief_id),
                "request_design_brief_version": request.design_brief_version,
                "brief_design_brief_version": brief.brief_version,
                "request_project_revision": request.project_revision,
            },
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
    code = getattr(exc, "code", "generation_failed")
    message = str(getattr(exc, "message", "") or str(exc) or exc.__class__.__name__)
    details = {
        "exception_type": exc.__class__.__name__,
        "context": dict(getattr(exc, "context", {}) or {}),
    }
    error = WorkerError(
        **context,
        code=code,
        message=message,
        retryable=retryable,
        details=details,
    )
    return WorkerResult(
        **context,
        output_contract_version=GENERATION_OUTPUT_VERSION,
        status=WorkerResultStatus.FAILED,
        error=error,
    )


__all__ = [
    "GENERATION_CAPABILITY_ID",
    "GENERATION_INPUT_VERSION",
    "GENERATION_OUTPUT_VERSION",
    "GENERATION_WORKER_ID",
    "GenerationEngine",
    "GenerationWorker",
    "GenerationWorkerPayload",
    "HardwareIRGenerationEngine",
    "build_generation_draft",
]
