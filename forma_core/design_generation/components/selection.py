"""One-role-at-a-time physical part selection."""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field

from forma_core.design_generation.completeness.models import ComponentRole
from forma_core.design_generation.intent.service import StructuredGenerator
from forma_core.workspaces.projects.models import PartDefinition


class PartSelectionCandidateDraft(BaseModel):
    """Bounded agent decision with no application-owned relationship IDs."""

    model_config = ConfigDict(extra="forbid")

    manufacturer: str | None = None
    manufacturer_part_number: str = Field(min_length=1)
    name: str | None = None
    category: str = "Component"
    description: str = Field(min_length=1)
    quantity: int = Field(default=1, ge=1)
    selection_reason: str = Field(min_length=1)
    source_url: str | None = None

    @property
    def identity_key(self) -> tuple[str, str]:
        return (
            (self.manufacturer or "").strip().casefold(),
            self.manufacturer_part_number.strip().casefold(),
        )


class PartSelectionDraft(PartSelectionCandidateDraft):
    """Application-normalized selection traced to exactly one component role."""

    role_id: str = Field(min_length=1)


class PartSelectionService:
    """Give the model only the current role and materially relevant context."""

    def __init__(self, generator: StructuredGenerator) -> None:
        self.generator = generator

    def select_part(
        self,
        role: ComponentRole,
        intent_constraints: list[str],
        selected_dependencies: list[PartDefinition],
    ) -> PartSelectionDraft:
        """Select one candidate for one role using only intent-derived context."""

        existing = [
            {
                "manufacturer": item.manufacturer,
                "part_number": item.part_number,
                "name": item.name,
                "category": item.category,
                "electrical_specs": item.electrical_specs,
            }
            for item in selected_dependencies
        ]
        raw = self.generator.generate(
            "Select one real or engineering-specified physical part for exactly one abstract component role. "
            "Return selection identity and rationale only. Do not return pins, full specifications, wiring, "
            "reference designators, IDs, timestamps, BOM rows, or a complete project.\n\n"
            f"Role: {role.model_dump_json(exclude={'status', 'selected_definition_id', 'failure_reason'})}\n"
            f"Relevant machine constraints: {json.dumps(intent_constraints)}\n"
            f"Already selected dependency parts: {json.dumps(existing, indent=2)}",
            PartSelectionCandidateDraft,
        )
        draft = (
            raw
            if isinstance(raw, PartSelectionCandidateDraft)
            else PartSelectionCandidateDraft.model_validate(raw)
        )
        return PartSelectionDraft(role_id=role.role_id, **draft.model_dump())
