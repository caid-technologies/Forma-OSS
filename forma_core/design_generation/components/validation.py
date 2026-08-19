"""Independent validation for a single enriched component definition."""

from __future__ import annotations

from pydantic import BaseModel, Field

from forma_core.workspaces.projects.models import PartDefinition


class ComponentValidationResult(BaseModel):
    """Local validation outcome for one enriched component definition."""

    is_valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ComponentDefinitionValidator:
    """Validate local identity and pin integrity without touching the project."""

    def validate_component(
        self, definition: PartDefinition
    ) -> ComponentValidationResult:
        """Check the minimum identity and electrical metadata for one part."""

        errors: list[str] = []
        warnings: list[str] = []
        if not definition.part_number.strip():
            errors.append("The part definition has no usable part number.")
        if not definition.name.strip():
            errors.append("The part definition has no usable name.")
        pin_ids = [pin.pin_id.strip() for pin in definition.pins]
        if any(not pin_id for pin_id in pin_ids):
            errors.append("Every pin must have a non-empty pin_id.")
        if len(pin_ids) != len(set(pin_ids)):
            errors.append("Pin IDs must be unique within a part definition.")
        if not definition.pins and definition.category.casefold() not in {
            "mechanical",
            "enclosure",
            "hardware",
            "cable",
            "mounting",
        }:
            warnings.append("No pin metadata is available for this electrical part.")
        return ComponentValidationResult(
            is_valid=not errors, errors=errors, warnings=warnings
        )
