# Worker contracts and capability registry

Specialized workers exchange versioned envelopes through `blueprint_core.workers`. These contracts define the boundary between orchestration and worker implementations; the dependency-aware execution lifecycle is documented in [worker orchestration](worker-orchestration.md).

The worker registry is intentionally separate from the Lattice agent registry:

- Lattice cards describe discoverable domain agents, tools, and handoffs.
- Worker definitions declare executable capabilities and compatible payload versions.
- `WorkerOrchestrator` validates every `WorkerRequest` through `WorkerRegistry` before invoking worker code.

## Envelope version

Every `WorkerRequest`, `WorkerProgress`, `WorkerResult`, `WorkerArtifact`, and `WorkerError` requires `contract_version: "1.0"`. Unsupported envelope versions fail Pydantic validation with error type `unsupported_worker_contract_version`.

Every envelope carries the same execution context:

- `project_id` and `project_revision`
- `design_brief_id` and `design_brief_version`
- `job_id` and `correlation_id`
- `worker_id` and `capability_id`

Artifacts and errors embedded in a result must have exactly the same context as that result.

## Payload compatibility

Envelope versions and capability payload versions evolve independently:

- `WorkerRequest.input_contract_version` identifies the request payload schema.
- `WorkerResult.output_contract_version` identifies the result payload schema.
- Each `WorkerCapability` declares `supported_input_versions` and `supported_output_versions`.

The registry compares those values before execution or result acceptance. A mismatch raises `WorkerRegistryError` with code `incompatible_worker_contract_version` and structured context containing the worker, capability, direction, requested version, and supported versions.

## Declaring and validating a worker

```python
from blueprint_core.workers import (
    WorkerCapability,
    WorkerDefinition,
    WorkerRegistry,
)

electrical = WorkerDefinition(
    worker_id="electrical-worker",
    name="Electrical Worker",
    worker_version="1.0.0",
    capabilities=[
        WorkerCapability(
            capability_id="electrical.plan",
            description="Create a validated electrical plan.",
            supported_input_versions=["design-brief.v1"],
            supported_output_versions=["electrical-plan.v1"],
        )
    ],
)

registry = WorkerRegistry([electrical])
resolution = registry.validate_request(request)
# Invoke the resolved worker only after validation succeeds.
```

A concrete worker can instead implement `worker_definition()` and register itself. Duplicate worker IDs, unknown workers, and capabilities not declared by the selected worker fail with structured registry errors.

## Contract evolution

- Additive payload changes should introduce a new capability input or output version when consumers need to distinguish behavior.
- Breaking envelope changes require a new worker `contract_version` and corresponding model support.
- Existing versions remain declared while active callers or stored job records depend on them.
- Registry compatibility tests must cover each newly supported version before it is used by an orchestrator.
