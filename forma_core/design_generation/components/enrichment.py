"""Late enrichment of a selected part into the canonical part definition."""

from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from forma_core.design_generation.components.selection import PartSelectionDraft
from forma_core.design_generation.intent.service import StructuredGenerator
from forma_core.workspaces.projects.models import PartDefinition, PinDefinition


class PartEnrichmentDraft(BaseModel):
    """Shared physical metadata returned only after a part is selected."""

    model_config = ConfigDict(extra="forbid")

    electrical_specs: dict[str, object] = Field(default_factory=dict)
    pins: list[PinDefinition] = Field(default_factory=list)
    dimensions_mm: dict[str, float] = Field(default_factory=dict)
    datasheet_url: str | None = None
    sourcing_url: str | None = None
    sourcing_offers: list[dict[str, object]] = Field(default_factory=list)
    unit_price: float = Field(default=0.0, ge=0.0)


class ComponentEnrichmentService:
    """Resolve specifications and pins independently from part selection."""

    def __init__(
        self,
        generator: StructuredGenerator,
        *,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.generator = generator
        self.id_factory = id_factory or (lambda: str(uuid4()))

    def enrich_component(
        self,
        selection: PartSelectionDraft,
    ) -> PartDefinition:
        """Resolve detailed canonical part metadata after selection."""

        raw = self.generator.generate(
            "Enrich this already-selected physical part. Return shared specifications, complete physical pin "
            "definitions where applicable, dimensions, datasheet and sourcing references, and price. Do not "
            "create application IDs, reference designators, instances, quantities, BOM rows, wiring, or "
            "workflow metadata. Every returned pin must have a stable pin_id, name, and pin_type.\n\n"
            f"Selection: {selection.model_dump_json(exclude={'role_id'})}",
            PartEnrichmentDraft,
        )
        draft = (
            raw
            if isinstance(raw, PartEnrichmentDraft)
            else PartEnrichmentDraft.model_validate(raw)
        )
        return PartDefinition(
            part_definition_id=self.id_factory(),
            manufacturer=selection.manufacturer,
            part_number=selection.manufacturer_part_number,
            name=selection.name or selection.description,
            category=selection.category,
            description=selection.description,
            electrical_specs=draft.electrical_specs,
            pins=draft.pins,
            dimensions_mm=draft.dimensions_mm,
            datasheet_url=draft.datasheet_url,
            sourcing_url=draft.sourcing_url or selection.source_url,
            sourcing_offers=draft.sourcing_offers,
            unit_price=draft.unit_price,
        )
