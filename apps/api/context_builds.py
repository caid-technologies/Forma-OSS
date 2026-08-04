from __future__ import annotations

import asyncio
import logging
from threading import Thread

from blueprint_core.database import (
    create_project_generation_plan,
    evaluate_project_readiness,
    execute_project_generation_plan,
    initiate_project_build,
)
from blueprint_core.workspaces.context import ContextBuildExecution
from blueprint_core.workspaces.readiness import BuildMode, ReadinessStatus
from blueprint_core.workspaces.workflow import ProjectWorkflow


logger = logging.getLogger(__name__)


DEFAULT_AGENT_ASSUMPTION = (
    "Build agents may resolve the remaining non-critical choices using safe prototype defaults "
    "and must record those choices as assumptions."
)


class ContextBuildDispatcher:
    """Turn conversational permission to proceed into a durable worker execution plan."""

    def start(
        self,
        project_id: str,
        owner_user_id: str,
        conversation_id: str,
    ) -> tuple[ContextBuildExecution, ProjectWorkflow]:
        readiness = evaluate_project_readiness(project_id, owner_user_id)
        mode = BuildMode.BUILD if readiness.status == ReadinessStatus.READY else BuildMode.BUILD_ANYWAY
        assumptions = [] if mode == BuildMode.BUILD else [DEFAULT_AGENT_ASSUMPTION]
        outcome = initiate_project_build(
            project_id,
            owner_user_id,
            mode=mode,
            actor_id=owner_user_id,
            assumptions=assumptions,
            idempotency_key=f"conversation-build:{conversation_id}",
        )
        plan = create_project_generation_plan(outcome.build, owner_user_id)
        job_id = next(iter(plan.jobs))
        if plan.status.value == "planned":
            self._launch(plan.plan_id, owner_user_id)
        return (
            ContextBuildExecution(
                build_id=outcome.build.build_id,
                plan_id=plan.plan_id,
                job_id=job_id,
                status=plan.status.value,
            ),
            outcome.workflow,
        )

    @staticmethod
    def _launch(plan_id: str, owner_user_id: str) -> None:
        """Run independently of the HTTP response lifecycle so the UI can begin polling immediately."""

        def run() -> None:
            try:
                asyncio.run(execute_project_generation_plan(plan_id, owner_user_id))
            except Exception:
                logger.exception("Detached generation plan failed: plan_id=%s", plan_id)

        Thread(target=run, name=f"forma-build-{plan_id}", daemon=True).start()


def context_build_dispatcher() -> ContextBuildDispatcher:
    return ContextBuildDispatcher()


__all__ = ["ContextBuildDispatcher", "context_build_dispatcher"]
