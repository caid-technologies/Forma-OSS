"""Public SDK client for Forma project generation."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Self
from uuid import uuid4

from forma_core.design_generation.service import (
    ProjectGenerationRun,
    ProjectGenerationService,
)
from forma_core.design_generation.state_machine.engine import DesignGenerationEngine
from forma_core.design_generation.state_machine.models import (
    GenerationCompleteness,
    GenerationOptions,
    GenerationStatus,
    ProjectGenerationResult,
)
from forma_core.workspaces.projects.models import HardwareIR

EngineFactory = Callable[[GenerationOptions], DesignGenerationEngine]
LegacyRunner = Callable[[str, GenerationOptions], HardwareIR]


def _configured_engine_factory(options: GenerationOptions) -> DesignGenerationEngine:
    from forma_core.agents.orchestrator import HardwarePipelineOrchestrator
    from forma_core.design_generation.factory import build_intent_first_engine

    orchestrator = HardwarePipelineOrchestrator(
        provider_name=options.provider_name,
        model_name=options.model_name,
        persist_project=False,
    )
    orchestrator.validate_configured_model()
    return build_intent_first_engine(orchestrator._call_llm_structured)


def _configured_legacy_runner(prompt: str, options: GenerationOptions) -> HardwareIR:
    from forma_core.agents.orchestrator import HardwarePipelineOrchestrator

    orchestrator = HardwarePipelineOrchestrator(
        provider_name=options.provider_name,
        model_name=options.model_name,
        persist_project=False,
    )
    return orchestrator.generate_project(prompt)


class LegacyProjectGenerationRun:
    """Small run handle for the isolated pre-intent generation pipeline."""

    def __init__(
        self, *, project_id: str, run_id: str, future: Future[ProjectGenerationResult]
    ) -> None:
        self.project_id = project_id
        self.run_id = run_id
        self._future = future

    @property
    def is_terminal(self) -> bool:
        return self._future.done()

    def result(self) -> ProjectGenerationResult:
        if not self._future.done():
            raise RuntimeError("Generation has not reached a terminal state.")
        return self._future.result()

    def wait(self, timeout: float | None = None) -> ProjectGenerationResult:
        return self._future.result(timeout=timeout)

    def get_project(self) -> HardwareIR | None:
        return self.result().project if self.is_terminal else None


class FormaProjects:
    """Project-scoped SDK operations."""

    def __init__(
        self,
        *,
        engine_factory: EngineFactory,
        legacy_runner: LegacyRunner,
        executor: ThreadPoolExecutor,
        provider_name: str | None = None,
        model_name: str | None = None,
    ) -> None:
        self._engine_factory = engine_factory
        self._legacy_runner = legacy_runner
        self._executor = executor
        self._provider_name = provider_name
        self._model_name = model_name

    def start_generation(
        self,
        *,
        prompt: str,
        strategy: str = "intent_first",
        options: GenerationOptions | None = None,
    ) -> ProjectGenerationRun | LegacyProjectGenerationRun:
        """Start generation using the intent-first or isolated legacy strategy."""

        resolved = options or GenerationOptions()
        resolved = resolved.model_copy(
            update={
                "provider_name": resolved.provider_name or self._provider_name,
                "model_name": resolved.model_name or self._model_name,
            }
        )
        if strategy == "intent_first":
            service = ProjectGenerationService(
                lambda: self._engine_factory(resolved),
                executor=self._executor,
            )
            return service.start(prompt=prompt, options=resolved)
        if strategy == "legacy":
            project_id = str(uuid4())
            run_id = str(uuid4())
            future = self._executor.submit(
                _run_legacy_generation,
                self._legacy_runner,
                prompt,
                resolved,
                project_id,
                run_id,
            )
            return LegacyProjectGenerationRun(
                project_id=project_id, run_id=run_id, future=future
            )
        raise ValueError("strategy must be 'intent_first' or 'legacy'.")


class FormaClient:
    """Configured entry point for the public Forma Python SDK."""

    def __init__(
        self,
        *,
        engine_factory: EngineFactory | None = None,
        legacy_runner: LegacyRunner | None = None,
        provider_name: str | None = None,
        model_name: str | None = None,
        max_workers: int = 4,
    ) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="forma-client-generation",
        )
        self.projects = FormaProjects(
            engine_factory=engine_factory or _configured_engine_factory,
            legacy_runner=legacy_runner or _configured_legacy_runner,
            executor=self._executor,
            provider_name=provider_name,
            model_name=model_name,
        )

    @classmethod
    def from_config(
        cls,
        *,
        provider_name: str | None = None,
        model_name: str | None = None,
        max_workers: int = 4,
    ) -> FormaClient:
        """Create a client using Forma's normal environment configuration."""

        return cls(
            provider_name=provider_name,
            model_name=model_name,
            max_workers=max_workers,
        )

    def close(self) -> None:
        self._executor.shutdown(wait=True)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def _run_legacy_generation(
    runner: LegacyRunner,
    prompt: str,
    options: GenerationOptions,
    project_id: str,
    run_id: str,
) -> ProjectGenerationResult:
    project = runner(prompt, options)
    metadata = project.assembly_metadata or {}
    raw_status = str(
        metadata.get("generation_status") or metadata.get("status") or "succeeded"
    ).casefold()
    if raw_status in {"failed", "error"}:
        status = GenerationStatus.FAILED
    elif raw_status in {"partial", "degraded"}:
        status = GenerationStatus.PARTIAL
    else:
        status = GenerationStatus.COMPLETE
    return ProjectGenerationResult(
        run_id=run_id,
        project_id=project_id,
        status=status,
        project=project,
        completeness=GenerationCompleteness(
            valid_bom_line_count=len(project.bom),
            physical_component_count=len(project.components),
        ),
    )


__all__ = ["FormaClient", "FormaProjects", "LegacyProjectGenerationRun"]
