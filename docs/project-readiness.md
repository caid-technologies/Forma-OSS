# Project readiness and build initiation

Forma evaluates the latest immutable `DesignBrief` before execution. The result is one of:

- `ready`: requirements, requested outputs, and validation criteria exist, with no unresolved questions.
- `not_ready`: only non-critical context is missing. Normal Build is rejected, while Build Anyway may proceed with explicit assumptions.
- `blocked`: a safety, dimensional, electrical, material, or manufacturing unknown remains. Neither Build nor Build Anyway can proceed.

Every result includes human-readable reasons and structured `unresolved_blockers` containing a stable code, category, source field, and critical flag.

## API

```text
GET  /projects/{project_id}/readiness
POST /projects/{project_id}/build
POST /projects/{project_id}/build-anyway
GET  /projects/{project_id}/build
```

Normal Build accepts an optional `idempotency_key`. Build Anyway also requires a non-empty `assumptions` list:

```json
{
  "idempotency_key": "build-from-chat-42",
  "assumptions": [
    "Produce wiring and a BOM in the first build",
    "Validate against a bench prototype"
  ]
}
```

Build Anyway appends a new DesignBrief version containing every supplied assumption. Successful initiation atomically:

1. freezes the full, exact DesignBrief snapshot and version;
2. stores the readiness result, assumptions, and warnings;
3. records the user-attributed workflow transition; and
4. enters `building`.

The `project_builds` record is the durable execution contract. Worker scheduling and frontend build controls are intentionally outside this layer.
