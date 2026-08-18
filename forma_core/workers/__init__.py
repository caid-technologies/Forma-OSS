from forma_core.workers.contracts import (
    WORKER_CONTRACT_VERSION,
    WorkerArtifact,
    WorkerContract,
    WorkerDependency,
    WorkerError,
    WorkerProgress,
    WorkerProgressStatus,
    WorkerRequest,
    WorkerResult,
    WorkerResultStatus,
)
from forma_core.workers.registry import (
    WORKER_REGISTRY_VERSION,
    WorkerCapability,
    WorkerDefinition,
    WorkerDefinitionProvider,
    WorkerRegistry,
    WorkerRegistryError,
    WorkerResolution,
)
from forma_core.workers.orchestration import (
    OrchestrationTaskState,
    OrchestrationTaskStatus,
    ProgressReporter,
    WorkerExecutionPlan,
    WorkerExecutor,
    WorkerOrchestrator,
    WorkerPlanStatus,
    WorkerPlanningError,
)
from forma_core.workers.generation import (
    GENERATION_CAPABILITY_ID,
    GENERATION_INPUT_VERSION,
    GENERATION_OUTPUT_VERSION,
    GENERATION_WORKER_ID,
    GenerationEngine,
    GenerationWorker,
    GenerationWorkerPayload,
    HardwareIRGenerationEngine,
    build_generation_draft,
)
from forma_core.workers.validation import (
    VALIDATION_CAPABILITY_ID,
    VALIDATION_INPUT_VERSION,
    VALIDATION_OUTPUT_VERSION,
    VALIDATION_WORKER_ID,
    RuleBasedValidationEngine,
    ValidationEngine,
    ValidationWorker,
    ValidationWorkerPayload,
    build_validation_request,
)
# The reverse-engineering worker pulls in Pillow (an optional "terminal" extra)
# transitively via forma_core.workspaces.reverse_engineering.analyzer, so it
# is re-exported lazily to keep Pillow optional for callers that only need
# other workers (e.g. generation).
_REVERSE_ENGINEERING_EXPORTS = frozenset(
    {
        "REVERSE_ENGINEERING_CAPABILITY_ID",
        "REVERSE_ENGINEERING_INPUT_VERSION",
        "REVERSE_ENGINEERING_OUTPUT_VERSION",
        "REVERSE_ENGINEERING_WORKER_ID",
        "InlineImageInspectionEngine",
        "ReverseEngineeringEngine",
        "ReverseEngineeringWorker",
        "ReverseEngineeringWorkerPayload",
        "build_reverse_engineering_request",
    }
)


def __getattr__(name: str):
    if name in _REVERSE_ENGINEERING_EXPORTS:
        from forma_core.workers import reverse_engineering

        return getattr(reverse_engineering, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "WORKER_CONTRACT_VERSION",
    "WORKER_REGISTRY_VERSION",
    "GENERATION_CAPABILITY_ID",
    "GENERATION_INPUT_VERSION",
    "GENERATION_OUTPUT_VERSION",
    "GENERATION_WORKER_ID",
    "GenerationEngine",
    "GenerationWorker",
    "GenerationWorkerPayload",
    "HardwareIRGenerationEngine",
    "InlineImageInspectionEngine",
    "REVERSE_ENGINEERING_CAPABILITY_ID",
    "REVERSE_ENGINEERING_INPUT_VERSION",
    "REVERSE_ENGINEERING_OUTPUT_VERSION",
    "REVERSE_ENGINEERING_WORKER_ID",
    "ReverseEngineeringEngine",
    "ReverseEngineeringWorker",
    "ReverseEngineeringWorkerPayload",
    "RuleBasedValidationEngine",
    "VALIDATION_CAPABILITY_ID",
    "VALIDATION_INPUT_VERSION",
    "VALIDATION_OUTPUT_VERSION",
    "VALIDATION_WORKER_ID",
    "ValidationEngine",
    "ValidationWorker",
    "ValidationWorkerPayload",
    "OrchestrationTaskState",
    "OrchestrationTaskStatus",
    "ProgressReporter",
    "WorkerArtifact",
    "WorkerCapability",
    "WorkerContract",
    "WorkerDefinition",
    "WorkerDefinitionProvider",
    "WorkerDependency",
    "WorkerError",
    "WorkerExecutionPlan",
    "WorkerExecutor",
    "WorkerOrchestrator",
    "WorkerPlanStatus",
    "WorkerPlanningError",
    "WorkerProgress",
    "WorkerProgressStatus",
    "WorkerRegistry",
    "WorkerRegistryError",
    "WorkerRequest",
    "WorkerResolution",
    "WorkerResult",
    "WorkerResultStatus",
    "build_generation_draft",
    "build_reverse_engineering_request",
    "build_validation_request",
]
