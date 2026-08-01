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

Successful outputs are aggregated by job ID from validated `WorkerResult` values. The orchestrator does not reinterpret the original conversation.

## Persistence and recovery

The `worker_execution_plans` record contains the validated requests and every job's status, progress events, result, artifacts, and error, along with the aggregate output. A new orchestrator instance can reload and resume a plan after process restart. Completed jobs are retained; jobs that were running when the process stopped are safely requeued.

When all jobs are terminal, the project workflow advances from `building` to `awaiting_feedback` with an idempotent system transition. Both successful and failed terminal plans preserve their results for feedback and diagnosis.
