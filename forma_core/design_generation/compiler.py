"""Deterministic adapter from persisted generation objects to HardwareIR."""

from __future__ import annotations

from forma_core.design_generation.repository import DesignGenerationRepository
from forma_core.workspaces.projects.models import (
    FunctionalRequirements,
    HardwareIR,
    ProjectOverview,
)


class HardwareIRCompiler:
    """Compile available domain data without any model/provider call."""

    def __init__(self, repository: DesignGenerationRepository) -> None:
        self.repository = repository

    def compile_hardware_ir(self, project_id: str) -> HardwareIR:
        """Compile persisted intent-first artifacts without provider calls."""

        intent = self.repository.get_intent(project_id)
        if intent is None:
            raise ValueError(f"Project '{project_id}' has no persisted machine intent.")
        definitions = self.repository.get_definitions(project_id)
        instances = self.repository.get_instances(project_id)
        bom = self.repository.get_bom_lines(project_id)
        fragments = self.repository.get_fragments(project_id)
        power_constraints = [
            item
            for item in intent.constraints
            if "power" in item.casefold() or "volt" in item.casefold()
        ]
        return HardwareIR(
            overview=ProjectOverview(
                title=intent.purpose[:120],
                description=intent.purpose,
                difficulty="To be assessed",
                estimated_cost=round(sum(item.extended_price for item in bom), 2),
                category="Hardware",
            ),
            requirements=FunctionalRequirements(
                requirements=list(intent.required_capabilities),
                power_needs="; ".join(power_constraints) or "To be resolved",
                physical_constraints=list(intent.operating_environment),
                safety_notes=[
                    item for item in intent.constraints if "safe" in item.casefold()
                ],
                missing_info=list(intent.unresolved_questions),
            ),
            part_definitions=definitions,
            components=instances,
            bom=bom,
            nets=fragments.nets,
            pin_mappings=fragments.pin_mappings,
            assembly=fragments.assembly,
            constraints=list(intent.constraints),
            assembly_metadata={},
            is_valid=True,
        )
