# Worker orchestration

`WorkerOrchestrator` runs a validated graph of specialized worker requests. It is intentionally downstream of context gathering and build initiation: workers receive the frozen project, revision, and DesignBrief identity from `WorkerRequest`, not the raw conversation.

## Planning

`create_plan()` validates the complete graph before persisting or executing it:

- every worker and capability exists in `WorkerRegistry`
- request payload versions are supported
- job IDs are unique
- dependency targets exist and optional worker/capability identities match
- all requests share project, revision, DesignBrief, and correlation context
- the dependency graph is acyclic

Planning failures raise `WorkerPlanningError` with stable codes and structured context. No worker is invoked when planning fails.

## Execution

Ready jobs run concurrently up to the plan's `max_concurrency`. A job becomes ready only after all declared dependencies reach a terminal state. Required dependency failures block the dependent job; advisory dependency failures are included in `dependency_results` and allow it to continue.

Workers implement `worker_definition()` plus `execute(request, report_progress)`. Their progress and terminal results must preserve the request identity and declare compatible output versions. Exceptions and invalid results become durable `WorkerError` records.

Successful and partial outputs are aggregated by job ID from validated `WorkerResult` values. `PARTIAL` is terminal and retains successful artifacts alongside a structured error. The orchestrator does not reinterpret the original conversation.

## Persistence and recovery

The `worker_execution_plans` record contains the validated requests and every job's status, progress events, result, artifacts, and error, along with the aggregate output. A new orchestrator instance can reload and resume a plan after process restart. Completed jobs are retained; jobs that were running when the process stopped are safely requeued.

`reset_job()` retries one failed or partial job and resets only its transitive dependents. Successful upstream and independent results remain persisted and are not executed again.

When all jobs are terminal, the project workflow advances from `building` to `awaiting_feedback` with an idempotent system transition. Both successful and failed terminal plans preserve their results for feedback and diagnosis.

Production capabilities on this boundary include the [Generation worker](generation-worker.md), which persists canonical project revision 1 from a frozen DesignBrief; the [Validation worker](validation-worker.md), which persists actionable findings against an exact revision; and the [Reverse-Engineering worker](reverse-engineering-worker.md), which produces evidence-linked artifact findings without mutating project state.
