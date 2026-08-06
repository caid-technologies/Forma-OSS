# Validation worker

The Validation worker owns the `project.validate` capability. It evaluates one exact canonical project revision against its frozen DesignBrief and persists an immutable `validation-findings.v1` report.

## Contract

The worker accepts `project-revision.v1`. Its optional payload selects baseline checks or links a revalidation to an older report:

```json
{
  "requested_checks": ["constraints", "consistency", "assumptions", "criteria"],
  "revalidation_of_report_id": null
}
```

The default rule-based engine checks declared constraints, internal component/net consistency, unresolved questions and assumptions, and DesignBrief validation criteria. An unknown or unsupported check produces a `skipped` finding instead of being treated as a pass.

Each finding carries the exact project revision and DesignBrief identity, criterion, status, severity, affected artifact when available, evidence, and suggested remediation. Status is one of `passed`, `warning`, `failed`, or `skipped`; severity is independently represented as `info`, `warning`, or `error`.

## Revision safety and persistence

`ProjectStateService.get_revision()` loads the requested revision rather than substituting the latest project state. `ValidationReportService` atomically stores findings in `project_validation_reports`, whose `(project_id, project_revision)` foreign key targets `project_revisions`. The insert also verifies the owner and frozen DesignBrief identity.

Reports are immutable and source-job idempotent. Replaying a completed job returns the same report. A revalidation request may reference an older report for the same project, but its new findings attach only to the changed revision; the earlier report remains on its original revision.

`build_validation_request()` is the downstream workflow boundary for requesting validation or revalidation without copying mutable project state into the worker payload.

The baseline evaluator is intentionally not a complete engineering simulator. Domain-specific criteria it cannot support are explicitly skipped and include routing or manual-review remediation.
