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

## Shared project-state boundary

`ProjectStateService` is the only write boundary used by the worker. Initial revisions are immutable, owner-scoped, and atomically inserted into `project_revisions`. A generated state that names another project or a revision other than 1 is rejected.

The source worker job is an idempotency identity. Replaying a successful job returns the same revision instead of generating a duplicate. A conflicting source job or stale initial write fails before overwriting state.

## Errors

Failures use `WorkerError` inside a failed `WorkerResult`. Invalid payloads, mismatched frozen briefs, and cross-project writes are non-retryable. Provider and transient persistence failures are marked retryable. The orchestrator persists both shapes with the execution plan and advances the terminal workflow to `awaiting_feedback`.

`HardwareIRGenerationEngine` adapts the existing structured generation pipeline with its legacy direct database write disabled. The engine receives only a prompt constructed from the frozen DesignBrief; the Generation worker commits the returned state through `ProjectStateService`.
