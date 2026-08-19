"""Feature-flagged adapter from Forma's current provider to the new engine."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from forma_core.design_generation.completeness import DesignPlanningService
from forma_core.design_generation.components import (
    ComponentDefinitionValidator,
    ComponentEnrichmentService,
    PartSelectionService,
)
from forma_core.design_generation.intent import (
    CallableStructuredGenerator,
    IntentService,
    MachineIntent,
)
from forma_core.design_generation.repository import (
    InMemoryDesignGenerationRepository,
    ProjectFragments,
)
from forma_core.design_generation.state_machine.engine import DesignGenerationEngine
from forma_core.workspaces.projects.models import (
    ComponentInstance,
    ConnectionNet,
    PartDefinition,
    PinMappingEntry,
    component_detail_payload,
)

INTENT_FIRST_GENERATION_ENV = "FORMA_INTENT_FIRST_GENERATION"


class WiringDraft(BaseModel):
    """Bounded wiring output produced after the BOM is committed."""

    nets: list[ConnectionNet] = Field(default_factory=list)
    pin_mappings: list[PinMappingEntry] = Field(default_factory=list)


class StructuredWiringService:
    """Generate wiring only after the independently committed BOM is available."""

    def __init__(self, generator: CallableStructuredGenerator) -> None:
        self.generator = generator

    def generate_wiring(
        self,
        project_id: str,
        intent: MachineIntent,
        definitions: list[PartDefinition],
        instances: list[ComponentInstance],
    ) -> ProjectFragments:
        by_id = {item.part_definition_id: item for item in definitions}
        hydrated = [item.model_copy(deep=True) for item in instances]
        for instance in hydrated:
            definition = by_id[str(instance.part_definition_id)]
            instance.part_number = definition.part_number
            instance.name = definition.name
            instance.category = definition.category
            instance.unit_price = definition.unit_price
            instance.sourcing_url = definition.sourcing_url
            instance.pins = list(definition.pins)
        raw = self.generator.generate(
            "Generate safe low-voltage wiring for these already-selected component instances. Return only "
            "connection nets and controller pin mappings. Do not regenerate components, the BOM, intent, "
            "application IDs, timestamps, provider metadata, or a complete project. A failure here must not "
            "change the supplied BOM.\n\n"
            f"Intent constraints: {json.dumps(intent.constraints)}\n"
            f"Components: {json.dumps([component_detail_payload(item) for item in hydrated], indent=2)}",
            WiringDraft,
        )
        draft = raw if isinstance(raw, WiringDraft) else WiringDraft.model_validate(raw)
        return ProjectFragments(nets=draft.nets, pin_mappings=draft.pin_mappings)


def build_intent_first_engine(
    provider_call: Any,
    *,
    checkpoint: Any = None,
    project_id: str | None = None,
    snapshot: dict[str, object] | None = None,
) -> DesignGenerationEngine:
    """Construct the vertical slice while keeping the current provider boundary."""

    generator = CallableStructuredGenerator(provider_call)
    repository = InMemoryDesignGenerationRepository(checkpoint=checkpoint)
    if project_id is not None and snapshot is not None:
        repository.restore(project_id, snapshot)
    return DesignGenerationEngine(
        repository=repository,
        intent_service=IntentService(generator),
        planning_service=DesignPlanningService(generator),
        selection_service=PartSelectionService(generator),
        enrichment_service=ComponentEnrichmentService(generator),
        component_validator=ComponentDefinitionValidator(),
        wiring_service=StructuredWiringService(generator),
    )


def snapshot_from_generation_run(generation_run: object) -> dict[str, object] | None:
    """Extract an intent-first repository snapshot from worker metadata."""

    if not isinstance(generation_run, dict):
        return None
    records = generation_run.get("records")
    record = records.get("intent_first_state") if isinstance(records, dict) else None
    snapshot = record.get("output") if isinstance(record, dict) else None
    return snapshot if isinstance(snapshot, dict) else None


__all__ = [
    "INTENT_FIRST_GENERATION_ENV",
    "StructuredWiringService",
    "build_intent_first_engine",
    "snapshot_from_generation_run",
]
