"""Deterministic CircuitDocument to canonical HardwareIR compiler."""

from __future__ import annotations

import re

from forma_core.design_generation.circuit_document.models import CircuitDocument
from forma_core.design_generation.circuit_document.projections import (
    CircuitProjections,
    normalize_part_number,
)
from forma_core.design_generation.intent.models import MachineIntent
from forma_core.workspaces.projects.models import (
    ComponentInstance,
    ConnectionNet,
    FunctionalRequirements,
    HardwareIR,
    PartDefinition,
    PinReference,
    ProjectOverview,
    derive_bom_line_items,
)


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").upper() or "ITEM"


def _operating_voltage(constraints: list[str], projected: dict[str, str]) -> float:
    values = [projected.get("power.logic", ""), *constraints, *projected.values()]
    for value in values:
        match = re.search(r"(?<!\d)(\d+(?:\.\d+)?)\s*[Vv](?!\w)", value)
        if match:
            voltage = float(match.group(1))
            if voltage <= 5.0:
                return voltage
        if "3v3" in value.casefold():
            return 3.3
    return 3.3


def _net_voltage(name: str, operating_voltage: float) -> float:
    normalized = name.upper()
    split_notation = re.search(r"(?<!\d)(\d+)V(\d+)(?!\d)", normalized)
    if split_notation:
        return float(f"{split_notation.group(1)}.{split_notation.group(2)}")
    decimal_notation = re.search(r"(?<!\d)(\d+(?:\.\d+)?)V(?!\w)", normalized)
    if decimal_notation:
        return float(decimal_notation.group(1))
    return operating_voltage


def _net_type(name: str) -> str:
    folded = name.casefold()
    if folded in {"gnd", "ground"}:
        return "Ground"
    if any(token in folded for token in ("3v3", "5v", "vcc", "vdd", "power")):
        return "Power"
    if "i2c" in folded or "sda" in folded or "scl" in folded:
        return "I2C"
    if "uart" in folded or "tx" in folded or "rx" in folded:
        return "UART"
    return "Digital"


class CircuitDocumentCompiler:
    """Compile available, validated work without any provider/model call."""

    def compile_partial_hardware_ir(
        self,
        *,
        intent: MachineIntent,
        document: CircuitDocument,
        projections: CircuitProjections,
        enriched_parts: list[PartDefinition],
        enrichment_failure_count: int = 0,
    ) -> HardwareIR:
        del document  # validated source is represented by the supplied projections
        definitions_by_part = {
            normalize_part_number(item.part_number): item for item in enriched_parts
        }
        instances: list[ComponentInstance] = []
        missing_definition_count = 0
        for part in projections.parts:
            definition = definitions_by_part.get(
                normalize_part_number(part.part_number)
            )
            if definition is None:
                missing_definition_count += 1
                continue
            for reference in part.instance_refs:
                instances.append(
                    ComponentInstance(
                        ref_des=reference,
                        part_definition_id=definition.part_definition_id,
                        rationale=f"Selected for circuit role {part.role_key}",
                        configuration={"role_key": part.role_key},
                    )
                )
        used_definition_ids = {
            str(instance.part_definition_id) for instance in instances
        }
        definitions = sorted(
            (
                item
                for item in enriched_parts
                if item.part_definition_id in used_definition_ids
            ),
            key=lambda item: item.part_definition_id,
        )
        instances.sort(key=lambda item: item.ref_des)
        bom = derive_bom_line_items(definitions, instances)
        bom.sort(key=lambda item: item.line_id)

        instance_refs = {item.ref_des for item in instances}
        definition_by_instance = {
            item.ref_des: next(
                definition
                for definition in definitions
                if definition.part_definition_id == item.part_definition_id
            )
            for item in instances
        }
        nets: list[ConnectionNet] = []
        operating_voltage = _operating_voltage(
            intent.constraints, projections.constraints
        )
        for projected_net in projections.nets:
            pins: list[PinReference] = []
            for endpoint in projected_net.endpoints:
                if "=" in endpoint or "." not in endpoint:
                    continue
                reference, pin_id = endpoint.rsplit(".", 1)
                if reference in instance_refs:
                    known_pins = {
                        pin.pin_id for pin in definition_by_instance[reference].pins
                    }
                    if not known_pins or pin_id in known_pins:
                        pins.append(PinReference(ref_des=reference, pin_id=pin_id))
            nets.append(
                ConnectionNet(
                    net_id=f"NET_{_slug(projected_net.name)}",
                    name=projected_net.name,
                    net_type=_net_type(projected_net.name),
                    voltage=(
                        _net_voltage(projected_net.name, operating_voltage)
                        if _net_type(projected_net.name) == "Power"
                        else None
                    ),
                    pins=pins,
                )
            )
        unresolved = projections.completeness
        selected_role_keys = {
            role.key for role in projections.roles if role.status.value == "selected"
        }
        selected_roles_without_parts = selected_role_keys - {
            part.role_key for part in projections.parts
        }
        complete = not any(
            (
                unresolved.unresolved_role_count,
                unresolved.invalid_role_count,
                unresolved.deferred_role_count,
                unresolved.open_issue_count,
                enrichment_failure_count,
                missing_definition_count,
                len(selected_roles_without_parts),
            )
        )
        return HardwareIR(
            overview=ProjectOverview(
                title=projections.machine_goal.machine.replace("-", " ").title(),
                description=projections.machine_goal.goal,
                difficulty="To be assessed",
                estimated_cost=round(sum(item.extended_price for item in bom), 2),
                category="Hardware",
            ),
            requirements=FunctionalRequirements(
                requirements=list(intent.required_capabilities),
                power_needs=projections.constraints.get(
                    "power.input", "To be resolved"
                ),
                operating_voltage=operating_voltage,
                physical_constraints=list(intent.operating_environment),
                safety_notes=[
                    item for item in intent.constraints if "safe" in item.casefold()
                ],
                missing_info=[
                    *intent.unresolved_questions,
                    *projections.open_obligations.values(),
                ],
            ),
            part_definitions=definitions,
            components=instances,
            bom=bom,
            nets=nets,
            constraints=list(intent.constraints),
            assembly_metadata={"generation_strategy": "circuit_document"},
            is_valid=complete,
        )


__all__ = ["CircuitDocumentCompiler"]
