"""Intent-first, progressively persisted hardware design generation."""

from forma_core.design_generation.compiler import HardwareIRCompiler
from forma_core.design_generation.completeness import (
    BomGapReview,
    BomLineTrace,
    CompletenessLedger,
    ComponentRole,
    ComponentRoleDraft,
    DesignCompleteness,
    DesignObligation,
    DesignObligationDraft,
    DesignPlanningService,
    ObligationStatus,
    SubsystemPlan,
    SubsystemPlanDraft,
    select_next_role,
)
from forma_core.design_generation.components import (
    ComponentDefinitionValidator,
    ComponentEnrichmentService,
    ComponentValidationResult,
    PartEnrichmentDraft,
    PartSelectionCandidateDraft,
    PartSelectionDraft,
    PartSelectionService,
)
from forma_core.design_generation.intent import (
    IntentService,
    MachineIntent,
    MachineIntentDraft,
)
from forma_core.design_generation.repository import (
    DesignCheckpointError,
    DesignGenerationRepository,
    InMemoryDesignGenerationRepository,
    ProjectFragments,
)
from forma_core.design_generation.service import (
    ProjectGenerationRun,
    ProjectGenerationService,
)
from forma_core.design_generation.state_machine.engine import DesignGenerationEngine
from forma_core.design_generation.state_machine.models import (
    DesignGenerationState,
    GenerationCompleteness,
    GenerationFailure,
    GenerationFailureSummary,
    GenerationOptions,
    GenerationPhase,
    GenerationStatus,
    ProjectGenerationResult,
)

__all__ = [
    "BomGapReview",
    "BomLineTrace",
    "CompletenessLedger",
    "ComponentDefinitionValidator",
    "ComponentEnrichmentService",
    "ComponentRole",
    "ComponentRoleDraft",
    "ComponentValidationResult",
    "DesignCheckpointError",
    "DesignCompleteness",
    "DesignGenerationEngine",
    "DesignGenerationRepository",
    "DesignGenerationState",
    "DesignObligation",
    "DesignObligationDraft",
    "DesignPlanningService",
    "GenerationCompleteness",
    "GenerationFailure",
    "GenerationFailureSummary",
    "GenerationOptions",
    "GenerationPhase",
    "GenerationStatus",
    "HardwareIRCompiler",
    "InMemoryDesignGenerationRepository",
    "IntentService",
    "MachineIntent",
    "MachineIntentDraft",
    "ObligationStatus",
    "PartEnrichmentDraft",
    "PartSelectionCandidateDraft",
    "PartSelectionDraft",
    "PartSelectionService",
    "ProjectFragments",
    "ProjectGenerationResult",
    "ProjectGenerationRun",
    "ProjectGenerationService",
    "SubsystemPlan",
    "SubsystemPlanDraft",
    "select_next_role",
]
