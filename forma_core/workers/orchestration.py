"""Dependency-aware, restart-safe orchestration for specialized workers."""

from __future__ import annotations

import asyncio
import inspect
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Protocol, Sequence
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from forma_core.workers.contracts import (
    NonEmptyString,
    WorkerError,
    WorkerProgress,
    WorkerRequest,
    WorkerResult,
    WorkerResultStatus,
)
from forma_core.workers.registry import WorkerDefinitionProvider, WorkerRegistry, WorkerRegistryError
from forma_core.workspaces.workflow import (
    ProjectWorkflowService,
    ProjectWorkflowState,
    WorkflowActorType,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OrchestrationTaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class WorkerPlanStatus(str, Enum):
    PLANNED = "planned"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_JOB_STATUSES = frozenset({
    OrchestrationTaskStatus.SUCCEEDED,
    OrchestrationTaskStatus.PARTIAL,
    OrchestrationTaskStatus.FAILED,
    OrchestrationTaskStatus.BLOCKED,
    OrchestrationTaskStatus.CANCELLED,
})
TERMINAL_PLAN_STATUSES = frozenset({
    WorkerPlanStatus.SUCCEEDED,
    WorkerPlanStatus.PARTIAL,
    WorkerPlanStatus.FAILED,
    WorkerPlanStatus.CANCELLED,
})


class OrchestrationTaskState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request: WorkerRequest
    status: OrchestrationTaskStatus = OrchestrationTaskStatus.QUEUED
    progress: list[WorkerProgress] = Field(default_factory=list)
    result: WorkerResult | None = None
    error: WorkerError | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class WorkerExecutionPlan(BaseModel):
    """The complete durable state needed to inspect or resume one worker graph."""

    model_config = ConfigDict(extra="forbid")

    plan_id: NonEmptyString = Field(default_factory=lambda: f"plan_{uuid4().hex}")
    owner_user_id: NonEmptyString
    project_id: str
    correlation_id: NonEmptyString
    attempt: int = Field(default=1, ge=1)
    status: WorkerPlanStatus = WorkerPlanStatus.PLANNED
    max_concurrency: int = Field(default=4, ge=1, le=64)
    jobs: dict[str, OrchestrationTaskState]
    aggregate: dict[str, dict[str, Any]] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    completed_at: datetime | None = None

    @model_validator(mode="after")
    def job_keys_match_requests(self) -> "WorkerExecutionPlan":
        for job_id, job in self.jobs.items():
            if job.request.job_id != job_id:
                raise ValueError("Worker execution plan job keys must match request job_id values.")
        return self


class WorkerPlanningError(ValueError):
    def __init__(self, code: str, message: str, *, context: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.context = context or {}

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "context": dict(self.context)}


class WorkerPlanRepository(Protocol):
    def insert_worker_execution_plan(self, record: dict[str, Any]) -> Any: ...
    def get_worker_execution_plan(self, plan_id: str, owner_user_id: str) -> Any | None: ...
    def update_worker_execution_plan(
        self,
        plan_id: str,
        owner_user_id: str,
        updates: dict[str, Any],
    ) -> Any | None: ...


ProgressReporter = Callable[[WorkerProgress], Awaitable[None]]


class WorkerExecutor(WorkerDefinitionProvider, Protocol):
    def execute(
        self,
        request: WorkerRequest,
        report_progress: ProgressReporter,
    ) -> WorkerResult | Awaitable[WorkerResult]: ...


def _record_to_plan(record: Any) -> WorkerExecutionPlan:
    payload = getattr(record, "state_json", None)
    if not isinstance(payload, dict):
        raise RuntimeError("Persisted worker execution plan state is invalid.")
    return WorkerExecutionPlan.model_validate(payload)


def _generation_run_from_progress(progress: list[WorkerProgress]) -> dict[str, Any] | None:
    records: dict[str, dict[str, Any]] = {}
    generation_run_id = None
    workflow = None
    retry_stage = None
    status = None
    for item in progress:
        checkpoint = item.metadata.get("generation_stage_checkpoint")
        if not isinstance(checkpoint, dict):
            continue
        generation_run_id = checkpoint.get("generation_run_id") or generation_run_id
        workflow = checkpoint.get("workflow") or workflow
        retry_stage = checkpoint.get("retry_stage") or retry_stage
        status = checkpoint.get("status") or status
        record = checkpoint.get("record")
        if isinstance(record, dict) and record.get("stage_id"):
            records[str(record["stage_id"])] = record
    if not generation_run_id or not records:
        return None
    return {
        "generation_run_id": generation_run_id,
        "workflow": workflow or "default",
        "retry_stage": retry_stage,
        "status": status or "running",
        "records": records,
    }


def _preserved_retry_progress(
    progress: list[WorkerProgress],
    invalidated_stage_ids: set[str],
) -> list[WorkerProgress]:
    preserved: list[WorkerProgress] = []
    for item in progress:
        checkpoint = item.metadata.get("generation_stage_checkpoint")
        if isinstance(checkpoint, dict):
            record = checkpoint.get("record")
            stage_id = str(record.get("stage_id") or "") if isinstance(record, dict) else ""
            if stage_id and stage_id not in invalidated_stage_ids:
                preserved.append(item)
            continue
        event = item.metadata.get("pipeline_event")
        if not isinstance(event, dict):
            continue
        stage_id = str(event.get("step_id") or "")
        if stage_id in invalidated_stage_ids:
            continue
        if str(event.get("status") or "").lower() in {"completed", "skipped"}:
            preserved.append(item)
    return preserved


class WorkerOrchestrator:
    """Validate a worker DAG, execute ready jobs concurrently, and persist every state change."""

    def __init__(
        self,
        repository: WorkerPlanRepository,
        workers: Sequence[WorkerExecutor],
        *,
        workflow_service: ProjectWorkflowService | None = None,
        cancellation_check: Callable[[], bool] | None = None,
    ) -> None:
        self._repository = repository
        self._workers = {worker.worker_definition().worker_id: worker for worker in workers}
        self._registry = WorkerRegistry(list(workers))
        self._workflow = workflow_service or ProjectWorkflowService(repository)
        self._cancellation_check = cancellation_check
        self._state_lock = asyncio.Lock()

    def create_plan(
        self,
        requests: Sequence[WorkerRequest],
        owner_user_id: str,
        *,
        max_concurrency: int = 4,
        plan_id: str | None = None,
    ) -> WorkerExecutionPlan:
        normalized_owner = str(owner_user_id or "").strip()
        if not normalized_owner:
            raise WorkerPlanningError("owner_required", "owner_user_id is required.")
        if not requests:
            raise WorkerPlanningError("empty_worker_plan", "A worker plan requires at least one job.")

        jobs: dict[str, OrchestrationTaskState] = {}
        first = requests[0]
        identity = (
            first.project_id,
            first.project_revision,
            first.design_brief_id,
            first.design_brief_version,
            first.correlation_id,
        )
        for request in requests:
            if request.job_id in jobs:
                raise WorkerPlanningError(
                    "duplicate_worker_job",
                    f"Worker job '{request.job_id}' appears more than once.",
                    context={"job_id": request.job_id},
                )
            request_identity = (
                request.project_id,
                request.project_revision,
                request.design_brief_id,
                request.design_brief_version,
                request.correlation_id,
            )
            if request_identity != identity:
                raise WorkerPlanningError(
                    "mixed_worker_context",
                    "All worker jobs in a plan must share project, revision, brief, and correlation context.",
                    context={"job_id": request.job_id},
                )
            try:
                self._registry.validate_request(request)
            except WorkerRegistryError as exc:
                raise WorkerPlanningError(exc.code, exc.message, context=exc.context) from exc
            if request.worker_id not in self._workers:
                raise WorkerPlanningError(
                    "worker_not_executable",
                    f"Worker '{request.worker_id}' is registered but has no executor.",
                    context={"worker_id": request.worker_id},
                )
            jobs[request.job_id] = OrchestrationTaskState(request=request)

        self._validate_graph(jobs)
        plan = WorkerExecutionPlan(
            plan_id=str(plan_id or f"plan_{uuid4().hex}").strip(),
            owner_user_id=normalized_owner,
            project_id=str(first.project_id),
            correlation_id=first.correlation_id,
            max_concurrency=max_concurrency,
            jobs=jobs,
        )
        self._repository.insert_worker_execution_plan(self._record(plan))
        return plan

    @staticmethod
    def _validate_graph(jobs: dict[str, OrchestrationTaskState]) -> None:
        indegree = {job_id: 0 for job_id in jobs}
        dependents: dict[str, list[str]] = {job_id: [] for job_id in jobs}
        for job_id, job in jobs.items():
            seen: set[str] = set()
            for dependency in job.request.dependencies:
                dependency_job = jobs.get(dependency.job_id)
                if dependency_job is None:
                    raise WorkerPlanningError(
                        "missing_worker_dependency",
                        f"Worker job '{job_id}' depends on missing job '{dependency.job_id}'.",
                        context={"job_id": job_id, "dependency_job_id": dependency.job_id},
                    )
                if dependency.job_id in seen:
                    raise WorkerPlanningError(
                        "duplicate_worker_dependency",
                        f"Worker job '{job_id}' declares dependency '{dependency.job_id}' more than once.",
                        context={"job_id": job_id, "dependency_job_id": dependency.job_id},
                    )
                seen.add(dependency.job_id)
                target = dependency_job.request
                if dependency.worker_id and dependency.worker_id != target.worker_id:
                    raise WorkerPlanningError(
                        "worker_dependency_identity_mismatch",
                        f"Dependency '{dependency.dependency_id}' worker_id does not match its target job.",
                        context={"job_id": job_id, "dependency_job_id": dependency.job_id},
                    )
                if dependency.capability_id and dependency.capability_id != target.capability_id:
                    raise WorkerPlanningError(
                        "worker_dependency_identity_mismatch",
                        f"Dependency '{dependency.dependency_id}' capability_id does not match its target job.",
                        context={"job_id": job_id, "dependency_job_id": dependency.job_id},
                    )
                indegree[job_id] += 1
                dependents[dependency.job_id].append(job_id)

        ready = [job_id for job_id, degree in indegree.items() if degree == 0]
        visited = 0
        while ready:
            current = ready.pop()
            visited += 1
            for dependent in dependents[current]:
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    ready.append(dependent)
        if visited != len(jobs):
            cyclic_jobs = sorted(job_id for job_id, degree in indegree.items() if degree > 0)
            raise WorkerPlanningError(
                "cyclic_worker_dependencies",
                "Worker dependency graph contains a cycle.",
                context={"job_ids": cyclic_jobs},
            )

    def get_plan(self, plan_id: str, owner_user_id: str) -> WorkerExecutionPlan:
        record = self._repository.get_worker_execution_plan(plan_id, owner_user_id)
        if record is None:
            raise WorkerPlanningError("worker_plan_not_found", "Worker execution plan not found.")
        return _record_to_plan(record)

    async def execute(self, plan_id: str, owner_user_id: str) -> WorkerExecutionPlan:
        plan = self.get_plan(plan_id, owner_user_id)
        if plan.status in TERMINAL_PLAN_STATUSES:
            await self._advance_workflow(plan)
            return plan

        for job in plan.jobs.values():
            if job.status == OrchestrationTaskStatus.RUNNING:
                job.status = OrchestrationTaskStatus.QUEUED
                job.started_at = None
        plan.status = WorkerPlanStatus.RUNNING
        await self._persist(plan)

        while True:
            changed = self._block_unsatisfied_jobs(plan)
            if changed:
                await self._persist(plan)
            ready = self._ready_jobs(plan)
            if not ready:
                break
            semaphore = asyncio.Semaphore(plan.max_concurrency)
            await asyncio.gather(*(self._execute_job(plan, job_id, semaphore) for job_id in ready))

        unfinished = [job_id for job_id, job in plan.jobs.items() if job.status not in TERMINAL_JOB_STATUSES]
        if unfinished:
            raise RuntimeError(f"Worker plan stalled with unfinished jobs: {', '.join(sorted(unfinished))}.")

        plan.aggregate = {
            job_id: job.result.model_dump(mode="json")
            for job_id, job in plan.jobs.items()
            if job.status in {OrchestrationTaskStatus.SUCCEEDED, OrchestrationTaskStatus.PARTIAL}
            and job.result is not None
        }
        plan.status = (
            WorkerPlanStatus.CANCELLED
            if any(job.status == OrchestrationTaskStatus.CANCELLED for job in plan.jobs.values())
            else WorkerPlanStatus.SUCCEEDED
            if all(job.status == OrchestrationTaskStatus.SUCCEEDED for job in plan.jobs.values())
            else WorkerPlanStatus.PARTIAL
            if any(job.status == OrchestrationTaskStatus.PARTIAL for job in plan.jobs.values())
            else WorkerPlanStatus.FAILED
        )
        plan.completed_at = _utc_now()
        await self._persist(plan)
        await self._advance_workflow(plan)
        return plan

    async def cancel(self, plan_id: str, owner_user_id: str) -> WorkerExecutionPlan:
        plan = self.get_plan(plan_id, owner_user_id)
        if plan.status in TERMINAL_PLAN_STATUSES:
            return plan

        for job in plan.jobs.values():
            if job.status in TERMINAL_JOB_STATUSES:
                continue
            result = self._cancelled_result(job.request)
            job.status = OrchestrationTaskStatus.CANCELLED
            job.result = result
            job.error = result.error
            job.completed_at = result.completed_at
        plan.aggregate = {}
        plan.status = WorkerPlanStatus.CANCELLED
        plan.completed_at = _utc_now()
        await self._persist(plan)
        await self._advance_workflow(plan)
        return plan

    async def reset(self, plan_id: str, owner_user_id: str) -> WorkerExecutionPlan:
        """Reset failed work so a user can make another execution attempt."""

        plan = self.get_plan(plan_id, owner_user_id)
        if plan.status not in {WorkerPlanStatus.FAILED, WorkerPlanStatus.PARTIAL}:
            raise WorkerPlanningError(
                "worker_plan_not_failed",
                "Only a failed worker plan can be reset.",
                context={"plan_id": plan.plan_id, "status": plan.status.value},
            )

        for job in plan.jobs.values():
            if job.status not in {
                OrchestrationTaskStatus.PARTIAL,
                OrchestrationTaskStatus.FAILED,
                OrchestrationTaskStatus.BLOCKED,
            }:
                continue
            retry_context = (
                job.result.metadata.get("generation_retry")
                if job.result is not None and isinstance(job.result.metadata, dict)
                else None
            )
            job.status = OrchestrationTaskStatus.QUEUED
            if isinstance(retry_context, dict):
                invalidated = {
                    str(stage_id)
                    for stage_id in (retry_context.get("invalidated_stage_ids") or [])
                }
                job.progress = _preserved_retry_progress(job.progress, invalidated)
                job.request = job.request.model_copy(update={
                    "metadata": {
                        **job.request.metadata,
                        "prior_generation_run": retry_context.get("prior_generation_run"),
                        "retry_stage": retry_context.get("retry_stage"),
                    }
                })
            else:
                job.progress = []
            job.result = None
            job.error = None
            job.started_at = None
            job.completed_at = None

        plan.attempt += 1
        plan.status = WorkerPlanStatus.PLANNED
        plan.aggregate = {}
        plan.completed_at = None
        self._workflow.transition(
            plan.project_id,
            plan.owner_user_id,
            ProjectWorkflowState.BUILDING,
            actor_type=WorkflowActorType.USER,
            actor_id=plan.owner_user_id,
            reason=f"User reset failed worker execution plan {plan.plan_id} for another attempt.",
            idempotency_key=f"worker-plan:{plan.plan_id}:attempt:{plan.attempt}:reset",
        )
        await self._persist(plan)
        return plan

    async def reset_job(self, plan_id: str, owner_user_id: str, job_id: str) -> WorkerExecutionPlan:
        """Retry one failed stage plus only the downstream work invalidated by it."""

        plan = self.get_plan(plan_id, owner_user_id)
        target = plan.jobs.get(job_id)
        if target is None:
            raise WorkerPlanningError("worker_job_not_found", f"Worker job '{job_id}' was not found.")
        if target.status not in {OrchestrationTaskStatus.FAILED, OrchestrationTaskStatus.PARTIAL}:
            raise WorkerPlanningError(
                "worker_job_not_failed",
                "Only a failed worker job can be retried independently.",
                context={"job_id": job_id, "status": target.status.value},
            )

        invalidated = {job_id}
        changed = True
        while changed:
            changed = False
            for candidate_id, candidate in plan.jobs.items():
                if candidate_id in invalidated:
                    continue
                if any(dependency.job_id in invalidated for dependency in candidate.request.dependencies):
                    invalidated.add(candidate_id)
                    changed = True

        for candidate_id in invalidated:
            job = plan.jobs[candidate_id]
            job.status = OrchestrationTaskStatus.QUEUED
            job.progress = []
            job.result = None
            job.error = None
            job.started_at = None
            job.completed_at = None
        plan.attempt += 1
        plan.status = WorkerPlanStatus.PLANNED
        plan.aggregate = {
            candidate_id: job.result.model_dump(mode="json")
            for candidate_id, job in plan.jobs.items()
            if candidate_id not in invalidated
            and job.status in {OrchestrationTaskStatus.SUCCEEDED, OrchestrationTaskStatus.PARTIAL}
            and job.result is not None
        }
        plan.completed_at = None
        self._workflow.transition(
            plan.project_id,
            plan.owner_user_id,
            ProjectWorkflowState.BUILDING,
            actor_type=WorkflowActorType.USER,
            actor_id=plan.owner_user_id,
            reason=f"User retried worker job {job_id} in execution plan {plan.plan_id}.",
            idempotency_key=f"worker-plan:{plan.plan_id}:attempt:{plan.attempt}:retry:{job_id}",
        )
        await self._persist(plan)
        return plan

    def _ready_jobs(self, plan: WorkerExecutionPlan) -> list[str]:
        ready: list[str] = []
        for job_id, job in plan.jobs.items():
            if job.status != OrchestrationTaskStatus.QUEUED:
                continue
            dependencies = [plan.jobs[item.job_id] for item in job.request.dependencies]
            if all(dependency.status in TERMINAL_JOB_STATUSES for dependency in dependencies):
                ready.append(job_id)
        return ready

    @staticmethod
    def _block_unsatisfied_jobs(plan: WorkerExecutionPlan) -> bool:
        changed = False
        for job in plan.jobs.values():
            if job.status != OrchestrationTaskStatus.QUEUED:
                continue
            required_failures = [
                dependency.job_id
                for dependency in job.request.dependencies
                if dependency.required
                and plan.jobs[dependency.job_id].status in {
                    OrchestrationTaskStatus.FAILED,
                    OrchestrationTaskStatus.PARTIAL,
                    OrchestrationTaskStatus.BLOCKED,
                }
            ]
            if not required_failures:
                continue
            job.status = OrchestrationTaskStatus.BLOCKED
            job.completed_at = _utc_now()
            job.error = WorkerError(
                **job.request.model_dump(
                    include={
                        "contract_version", "project_id", "project_revision", "design_brief_id",
                        "design_brief_version", "job_id", "correlation_id", "worker_id", "capability_id",
                    }
                ),
                code="required_dependency_failed",
                message="One or more required worker dependencies did not succeed.",
                details={"dependency_job_ids": required_failures},
            )
            changed = True
        return changed

    async def _execute_job(
        self,
        plan: WorkerExecutionPlan,
        job_id: str,
        semaphore: asyncio.Semaphore,
    ) -> None:
        async with semaphore:
            async with self._state_lock:
                job = plan.jobs[job_id]
                job.status = OrchestrationTaskStatus.RUNNING
                job.started_at = _utc_now()
                await self._persist_unlocked(plan)

            request = self._request_with_dependency_results(plan, job.request)

            async def report_progress(progress: WorkerProgress) -> None:
                if progress.context_identity() != request.context_identity():
                    raise ValueError("Worker progress context must match its request.")
                async with self._state_lock:
                    state = plan.jobs[job_id]
                    if state.progress and progress.sequence <= state.progress[-1].sequence:
                        raise ValueError("Worker progress sequence values must increase.")
                    state.progress.append(progress)
                    await self._persist_unlocked(plan)

            try:
                candidate = self._workers[request.worker_id].execute(request, report_progress)
                result = await candidate if inspect.isawaitable(candidate) else candidate
                result = WorkerResult.model_validate(result)
                if result.context_identity() != request.context_identity():
                    raise ValueError("Worker result context must match its request.")
                self._registry.validate_result(result)
            except Exception as exc:
                result = self._failure_result(request, exc)

            async with self._state_lock:
                state = plan.jobs[job_id]
                state.result = result
                state.error = result.error
                state.status = (
                    OrchestrationTaskStatus.SUCCEEDED
                    if result.status == WorkerResultStatus.SUCCEEDED
                    else OrchestrationTaskStatus.PARTIAL
                    if result.status == WorkerResultStatus.PARTIAL
                    else OrchestrationTaskStatus.CANCELLED
                    if result.status == WorkerResultStatus.CANCELLED
                    else OrchestrationTaskStatus.FAILED
                )
                if result.status == WorkerResultStatus.CANCELLED:
                    plan.status = WorkerPlanStatus.CANCELLED
                    plan.completed_at = result.completed_at
                state.completed_at = result.completed_at
                await self._persist_unlocked(plan)

    def _request_with_dependency_results(
        self,
        plan: WorkerExecutionPlan,
        request: WorkerRequest,
    ) -> WorkerRequest:
        dependency_results = {
            dependency.job_id: (
                plan.jobs[dependency.job_id].result.model_dump(mode="json")
                if plan.jobs[dependency.job_id].result is not None
                else None
            )
            for dependency in request.dependencies
        }
        task_progress = plan.jobs[request.job_id].progress
        checkpoint_run = _generation_run_from_progress(task_progress)
        return request.model_copy(update={
            "payload": (
                {**request.payload, "dependency_results": dependency_results}
                if request.dependencies
                else dict(request.payload)
            ),
            "metadata": {
                **request.metadata,
                "execution_owner_user_id": plan.owner_user_id,
                "execution_attempt": plan.attempt,
                "progress_sequence_start": max(
                    (progress.sequence for progress in task_progress),
                    default=0,
                ),
                **(
                    {"prior_generation_run": checkpoint_run}
                    if checkpoint_run is not None and not isinstance(request.metadata.get("prior_generation_run"), dict)
                    else {}
                ),
                **(
                    {"pipeline_cancellation_check": self._cancellation_check}
                    if self._cancellation_check is not None
                    else {}
                ),
            },
        })

    def _failure_result(self, request: WorkerRequest, exc: Exception) -> WorkerResult:
        resolution = self._registry.resolve(request.worker_id, request.capability_id)
        context = request.model_dump(
            include={
                "contract_version", "project_id", "project_revision", "design_brief_id",
                "design_brief_version", "job_id", "correlation_id", "worker_id", "capability_id",
            }
        )
        error = WorkerError(
            **context,
            code="worker_execution_failed",
            message=str(exc) or exc.__class__.__name__,
            retryable=False,
            details={"exception_type": exc.__class__.__name__},
        )
        return WorkerResult(
            **context,
            output_contract_version=resolution.capability.supported_output_versions[0],
            status=WorkerResultStatus.FAILED,
            error=error,
        )

    def _cancelled_result(self, request: WorkerRequest) -> WorkerResult:
        resolution = self._registry.resolve(request.worker_id, request.capability_id)
        context = request.model_dump(
            include={
                "contract_version", "project_id", "project_revision", "design_brief_id",
                "design_brief_version", "job_id", "correlation_id", "worker_id", "capability_id",
            }
        )
        error = WorkerError(
            **context,
            code="worker_cancelled",
            message="Build stopped by the user.",
            retryable=True,
        )
        return WorkerResult(
            **context,
            output_contract_version=resolution.capability.supported_output_versions[0],
            status=WorkerResultStatus.CANCELLED,
            error=error,
        )

    async def _advance_workflow(self, plan: WorkerExecutionPlan) -> None:
        self._workflow.transition(
            plan.project_id,
            plan.owner_user_id,
            ProjectWorkflowState.AWAITING_FEEDBACK,
            actor_type=WorkflowActorType.SYSTEM,
            actor_id="worker-orchestrator",
            reason=f"Worker execution plan {plan.plan_id} reached a terminal result.",
            idempotency_key=f"worker-plan:{plan.plan_id}:attempt:{plan.attempt}:terminal",
        )

    async def _persist(self, plan: WorkerExecutionPlan) -> None:
        async with self._state_lock:
            await self._persist_unlocked(plan)

    async def _persist_unlocked(self, plan: WorkerExecutionPlan) -> None:
        existing = self._repository.get_worker_execution_plan(plan.plan_id, plan.owner_user_id)
        if existing is not None:
            persisted = _record_to_plan(existing)
            if persisted.status == WorkerPlanStatus.CANCELLED and plan.status != WorkerPlanStatus.CANCELLED:
                return
        plan.updated_at = _utc_now()
        updated = self._repository.update_worker_execution_plan(
            plan.plan_id,
            plan.owner_user_id,
            {
                "status": plan.status.value,
                "state_json": plan.model_dump(mode="json"),
                "updated_at": plan.updated_at.isoformat(),
                "completed_at": plan.completed_at.isoformat() if plan.completed_at else None,
            },
        )
        if updated is None:
            raise RuntimeError(f"Worker execution plan '{plan.plan_id}' could not be persisted.")

    @staticmethod
    def _record(plan: WorkerExecutionPlan) -> dict[str, Any]:
        return {
            "id": plan.plan_id,
            "project_id": plan.project_id,
            "owner_user_id": plan.owner_user_id,
            "correlation_id": plan.correlation_id,
            "status": plan.status.value,
            "max_concurrency": plan.max_concurrency,
            "state_json": plan.model_dump(mode="json"),
            "created_at": plan.created_at.isoformat(),
            "updated_at": plan.updated_at.isoformat(),
            "completed_at": plan.completed_at.isoformat() if plan.completed_at else None,
        }


__all__ = [
    "ProgressReporter",
    "OrchestrationTaskState",
    "OrchestrationTaskStatus",
    "TERMINAL_JOB_STATUSES",
    "TERMINAL_PLAN_STATUSES",
    "WorkerExecutionPlan",
    "WorkerExecutor",
    "WorkerOrchestrator",
    "WorkerPlanRepository",
    "WorkerPlanStatus",
    "WorkerPlanningError",
]
