# DesignBrief

`DesignBrief` is Forma's canonical, validated handoff from conversational context to downstream planning and execution. It records what the user wants without defining chat-agent behavior, readiness scoring, or worker execution.

## Version model

Two independent versions are recorded:

- `schema_version` identifies the payload contract. The first supported contract is `1.0`.
- `brief_version` identifies an immutable snapshot for one project. Creating an update appends the next integer version and records `previous_version`; it never overwrites an older payload.

All snapshots for a project retain one stable `design_brief_id`. Every snapshot also stores its `project_id`, originating `conversation_id`, owner, and creation time.

## DesignBrief v1

Client-authored fields are:

```json
{
  "schema_version": "1.0",
  "conversation_id": "chat-123",
  "intent": "Design a compact environmental monitor",
  "summary": "A battery-powered monitor with a local display",
  "requirements": ["Measure temperature and humidity"],
  "constraints": ["Fit within a 100 mm enclosure"],
  "references": [
    {
      "reference_id": "uploaded-reference-1",
      "kind": "uploaded_image",
      "label": "Existing enclosure",
      "uri": "s3://design-inputs/enclosure.png",
      "media_type": "image/png",
      "metadata": {}
    }
  ],
  "requested_outputs": ["wiring", "bom", "enclosure"],
  "validation_criteria": ["Sensor readings update every second"],
  "unresolved_questions": ["What battery life is required?"],
  "assumptions": ["Indoor operating conditions"],
  "readiness": "needs_clarification"
}
```

The server adds `design_brief_id`, `project_id`, `brief_version`, `previous_version`, and `created_at`. Readiness is an explicit state (`draft`, `needs_clarification`, or `ready`), not a computed score.

## API

Authenticated callers use:

- `POST /projects/{project_id}/design-briefs` to append a snapshot.
- `GET /projects/{project_id}/design-briefs` to list snapshots in version order.
- `GET /projects/{project_id}/design-briefs/latest` to retrieve the newest snapshot.
- `GET /projects/{project_id}/design-briefs/{brief_version}` to retrieve an exact snapshot.

An unsupported schema version returns HTTP 422 with error type `unsupported_design_brief_schema_version`. Missing or inaccessible briefs return a structured `design_brief_not_found` response without revealing another user's project.

## Compatibility rules

- Readers must select behavior by `schema_version`, not `brief_version`.
- Existing schema versions remain readable after a new version is introduced.
- Additive optional fields may be introduced in a minor schema revision. Required-field changes, removals, or semantic changes require a new major schema version.
- A new schema version requires domain validation, persistence round-trip tests, API error tests, migration review, and an update to this document before it is accepted.
- Stored snapshots are immutable. Normal corrections always create another `brief_version`.

The hosted table is backend-only: browser roles have no direct access, and the authenticated API applies owner scoping.
