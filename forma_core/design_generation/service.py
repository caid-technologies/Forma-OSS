"""Developer-facing run handle for intent-first project generation."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Executor, Future, ThreadPoolExecutor
from uuid import uuid4

from forma_core.design_generation.compiler import HardwareIRCompiler
from forma_core.design_generation.state_machine.engine import DesignGenerationEngine
from forma_core.design_generation.state_machine.models import (
    DesignGenerationState,
    GenerationOptions,
    GenerationPhase,
    ProjectGenerationResult,
)
from forma_core.workspaces.projects.models import HardwareIR


class ProjectGenerationRun:
    """Poll, inspect, and resume a generation without exposing workflow internals."""

    def __init__(
        self,
        *,
        project_id: str,
        run_id: str,
        intent_id: str,
        engine: DesignGenerationEngine,
        result: ProjectGenerationResult | None = None,
        future: Future[ProjectGenerationResult] | None = None,
        executor: Executor | None = None,
    ) -> None:
        self.project_id = project_id
        self._run_id = run_id
        self.intent_id = intent_id
        self.engine = engine
        self._result = result
        self._future = future
        self._executor = executor

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def is_terminal(self) -> bool:
        state = self.engine.repository.get_state(self.project_id)
        return bool(
            (state is not None and state.is_terminal)
            or (self._future is not None and self._future.done())
        )

    def refresh(self) -> DesignGenerationState:
        """Return the latest persisted state without waiting for completion."""

        state = self.engine.repository.get_state(self.project_id)
        if state is None:
            return DesignGenerationState(
                run_id=self._run_id,
                project_id=self.project_id,
                intent_id=self.intent_id,
                phase=GenerationPhase.EXPAND_OBLIGATIONS,
            )
        return state

    def get_project(self) -> HardwareIR | None:
        """Compile and return currently available partial project state."""

        if self.engine.repository.get_intent(self.project_id) is None:
            return None
        try:
            return HardwareIRCompiler(self.engine.repository).compile_hardware_ir(
                self.project_id
            )
        except ValueError:
            return None

    def result(self) -> ProjectGenerationResult:
        """Return the terminal result or raise while generation is running."""

        if self._result is not None:
            return self._result
        if self._future is None or not self._future.done():
            raise RuntimeError("Generation has not reached a terminal state.")
        self._result = self._future.result()
        return self._result

    def wait(self, timeout: float | None = None) -> ProjectGenerationResult:
        """Wait for terminal state without exposing callbacks or workflow IDs."""

        if self._result is None and self._future is not None:
            self._result = self._future.result(timeout=timeout)
        return self.result()

    def resume(
        self,
        *,
        retry_deferred_roles: bool = True,
        retry_blocked_roles: bool = False,
        options: GenerationOptions | None = None,
    ) -> ProjectGenerationRun:
        """Retry eligible roles from persisted intent-first state."""

        if not self.is_terminal:
            raise RuntimeError("Only a terminal partial or failed run can be resumed.")
        if self._executor is None:
            result = self.engine.resume(
                self.project_id,
                retry_deferred_roles=retry_deferred_roles,
                retry_blocked_roles=retry_blocked_roles,
                options=options,
            )
            return ProjectGenerationRun(
                project_id=self.project_id,
                run_id=self._run_id,
                intent_id=self.intent_id,
                engine=self.engine,
                result=result,
            )
        future = self._executor.submit(
            self.engine.resume,
            self.project_id,
            retry_deferred_roles=retry_deferred_roles,
            retry_blocked_roles=retry_blocked_roles,
            options=options,
        )
        return ProjectGenerationRun(
            project_id=self.project_id,
            run_id=self._run_id,
            intent_id=self.intent_id,
            engine=self.engine,
            future=future,
            executor=self._executor,
        )


class ProjectGenerationService:
    """Start explicit project-generation runs from a prompt and limits."""

    def __init__(
        self,
        engine_factory: Callable[[], DesignGenerationEngine],
        *,
        project_id_factory: Callable[[], str] | None = None,
        executor: Executor | None = None,
    ) -> None:
        self.engine_factory = engine_factory
        self.project_id_factory = project_id_factory or (lambda: str(uuid4()))
        self.executor = executor or ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="forma-design-generation"
        )
        self._owns_executor = executor is None

    def start(
        self,
        *,
        prompt: str,
        options: GenerationOptions | None = None,
    ) -> ProjectGenerationRun:
        """Persist canonical intent, then schedule the ID-only state engine."""

        engine = self.engine_factory()
        project_id = self.project_id_factory()
        run_id = str(uuid4())
        intent = engine.create_machine_intent(project_id=project_id, prompt=prompt)
        future = self.executor.submit(
            engine.start,
            project_id=project_id,
            intent_id=intent.intent_id,
            run_id=run_id,
            options=options,
        )
        return ProjectGenerationRun(
            project_id=project_id,
            run_id=run_id,
            intent_id=intent.intent_id,
            engine=engine,
            future=future,
            executor=self.executor,
        )

    def shutdown(self, *, wait: bool = True) -> None:
        if self._owns_executor and isinstance(self.executor, ThreadPoolExecutor):
            self.executor.shutdown(wait=wait)


__all__ = ["ProjectGenerationRun", "ProjectGenerationService"]
