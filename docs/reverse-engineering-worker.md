# Reverse-Engineering worker

The Reverse-Engineering worker owns the `artifact.reverse-engineer` capability. It inspects one supplied artifact with exact frozen DesignBrief context and returns `reverse-engineering-findings.v1` without writing to canonical project state.

## Contract

The `artifact-reference.v1` payload contains a supported artifact reference and the frozen DesignBrief:

```json
{
  "artifact": {
    "artifact_id": "uploaded-reference",
    "kind": "uploaded_image",
    "uri": "data:image/png;base64,...",
    "media_type": "image/png",
    "label": "reference.png"
  },
  "design_brief": {
    "schema_version": "1.0"
  }
}
```

The baseline `InlineImageInspectionEngine` accepts bounded inline PNG, JPEG, and WebP images. It verifies the declared type against decoded bytes, enforces byte and pixel limits, and extracts image properties, tonal range, and foreground bounds. A richer semantic or provider-backed vision engine can implement the same `ReverseEngineeringEngine` protocol later.

## Findings

The result deliberately separates:

- `evidence`: observed artifact facts or exact DesignBrief context, including the observation method;
- `findings`: structure, function, or property inferences linked to evidence IDs;
- `confidence`: `high`, `medium`, or `low` for each inference;
- `uncertainties`: unresolved limits on every inference and on the report overall.

Visually uniform or low-contrast input succeeds as an ambiguous report instead of inventing structure. Unsupported media, invalid bytes, type mismatches, and unavailable content return stable structured worker errors.

The worker result includes only an artifact summary and SHA-256 digest; it does not echo inline image content. The result is persisted by `WorkerOrchestrator`, so a dependent worker receives the validated report through its `dependency_results` payload.

## State boundary

The worker verifies that its DesignBrief matches the persisted owner-scoped snapshot. It never calls a project-state write method and does not replace components, systems, artifacts, or assumptions. Any downstream worker that proposes a state change must do so through its own explicit capability and revision boundary.
