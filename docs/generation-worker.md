# Generation worker

The Generation worker owns the `project.generate` capability. It converts one persisted, frozen `DesignBrief` into canonical project revision 1 and never reads raw conversation text.

## Contract

The worker accepts `design-brief.v1` with this payload:

```json
{
  "design_brief": { "schema_version": "1.0" }
}
```

The complete DesignBrief identity and payload must match the persisted snapshot selected by `WorkerRequest.project_id`, `design_brief_id`, and `design_brief_version`. Additional payload fields are rejected, so chat transcripts and undeclared research context cannot silently enter generation. Declared references remain part of the frozen brief.

The `project-revision.v1` result identifies:

- the complete canonical `HardwareIR` state;
- structured components and functional systems;
- every generated artifact reference;
- every declared or generation-time assumption;
- the exact project, revision, DesignBrief, and source job identities.

Web-research generation also exposes a durable `generation_run` in Hardware IR metadata. Every artifact-producing stage records its dependencies, status, attempt, input artifact references, output, error, and timestamps. Successful stages reuse `ProjectArtifact` references with stable Forma URIs and SHA-256 checksums, which flow into worker artifacts. The project record is created before structured generation, and each successful output is checkpointed before dependent work starts.

Stage failures produce `PARTIAL` when useful artifacts remain. Required dependents become `BLOCKED`, while independent work continues; for example, mechanical generation can complete after wiring fails. Project readiness (`draft`, `partial`, `core_ready`, or `complete`) is independent from the overall job result.

## Shared project-state boundary

`ProjectStateService` is the only write boundary used by the worker. Initial revisions are immutable, owner-scoped, and atomically inserted into `project_revisions`. A generated state that names another project or a revision other than 1 is rejected.

The source worker job is an idempotency identity. Replaying a successful job returns the same revision instead of generating a duplicate. A conflicting source job or stale initial write fails before overwriting state.

## Errors

Failures use `WorkerError` inside a failed `WorkerResult`. Invalid payloads, mismatched frozen briefs, and cross-project writes are non-retryable. Provider and transient persistence failures are marked retryable. The orchestrator persists both shapes with the execution plan and advances the terminal workflow to `awaiting_feedback`.

`HardwareIRGenerationEngine` adapts the existing structured generation pipeline with its legacy direct database write disabled. The engine receives only a prompt constructed from the frozen DesignBrief; the Generation worker commits the returned state through `ProjectStateService`.

## Intent-first generation preview

Set `FORMA_INTENT_FIRST_GENERATION=true` to route the default Generation
worker through the intent-first preview. It first persists a minimal machine
intent and explicit design obligations, plans abstract component roles, then
selects, enriches, validates, and commits one role at a time. Canonical
`PartDefinition`, `ComponentInstance`, and `BOMLineItem` models are reused;
application code owns IDs, reference designators, and BOM aggregation.
After initial physical selections, a bounded BOM-completeness review checks the
chosen modules and devices for missing electrical, interconnect, fabrication,
and mechanical support items. Any gaps become new traced component roles and
are selected and committed before wiring; the run remains partial if the
review cannot confirm an implementation-ready procurement BOM.

The preview is disabled by default until fixed-prompt benchmarks show improved
valid BOM yield without a higher generation failure rate. Safety-blocked and
simulation requests continue through the established pipeline. Generation
state and provider retry details remain outside `HardwareIR`; its compiler
constructs the available project deterministically from repository records.
Every repository mutation is mirrored into the worker plan's durable stage
checkpoint, so a retry restores committed definitions, instances, and BOM rows
instead of regenerating them.

`WorkerResultStatus.PARTIAL` carries both preserved artifacts and stage failure details. A named failed stage can be retried without rerunning successful upstream or independent stages; only that stage and its transitive dependents are invalidated. Attempt history remains in the stage record, and replaying the same retry job is idempotent.

The default conversation/context build uses the same stage records. Checkpoints are persisted inside the durable worker plan before dependent calls begin, partial and root-failure revisions remain inspectable, and plan reset carries the prior generation run into the next attempt. Completed upstream and independent pipeline events remain visible in the UI instead of resetting progress to zero. If a serverless execution request ends before the plan is terminal, the client reconnects to the same plan and resumes from its latest checkpoint.
