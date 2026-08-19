"""Small deterministic read projections over a validated circuit document."""

from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel, Field

from forma_core.design_generation.circuit_document.grammar import parse_document
from forma_core.design_generation.circuit_document.models import (
    CircuitDocument,
    GoalRecord,
    KeyValueRecord,
    MachineRecord,
    NetRecord,
    PartRecord,
    RecordType,
    RoleImportance,
    RoleRecord,
    RoleStatus,
)
from forma_core.design_generation.circuit_document.validation import expanded_references


class MachineGoalProjection(BaseModel):
    machine: str
    goal: str


class RoleProjection(BaseModel):
    key: str
    importance: RoleImportance
    status: RoleStatus
    selection: str


class PartProjection(BaseModel):
    reference: str
    role_key: str
    part_number: str
    quantity: int
    instance_refs: list[str]


class BomProjectionLine(BaseModel):
    normalized_part_number: str
    part_number: str
    quantity: int
    instance_refs: list[str]
    role_keys: list[str]


class NetProjection(BaseModel):
    name: str
    endpoints: list[str]


class CircuitCompleteness(BaseModel):
    required_role_count: int = 0
    selected_role_count: int = 0
    unresolved_role_count: int = 0
    invalid_role_count: int = 0
    deferred_role_count: int = 0
    open_issue_count: int = 0
    raw_bom_line_count: int = 0
    physical_component_quantity: int = 0

    @property
    def required_role_coverage(self) -> float:
        if not self.required_role_count:
            return 1.0
        return self.selected_role_count / self.required_role_count


class CircuitProjections(BaseModel):
    machine_goal: MachineGoalProjection
    constraints: dict[str, str] = Field(default_factory=dict)
    blocks: dict[str, str] = Field(default_factory=dict)
    roles: list[RoleProjection] = Field(default_factory=list)
    parts: list[PartProjection] = Field(default_factory=list)
    bom: list[BomProjectionLine] = Field(default_factory=list)
    nets: list[NetProjection] = Field(default_factory=list)
    open_obligations: dict[str, str] = Field(default_factory=dict)
    completeness: CircuitCompleteness = Field(default_factory=CircuitCompleteness)


def normalize_part_number(value: str) -> str:
    """Normalize manufacturer identity without inventing a second catalog."""

    return "".join(value.strip().casefold().split())


class CircuitProjectionService:
    """Build disposable typed views from the textual source of truth."""

    def build(self, document: CircuitDocument) -> CircuitProjections:
        parsed = parse_document(document)
        machine = next(
            item for item in parsed.records if isinstance(item, MachineRecord)
        )
        goal = next(item for item in parsed.records if isinstance(item, GoalRecord))
        key_values = [
            item for item in parsed.records if isinstance(item, KeyValueRecord)
        ]
        role_records = [item for item in parsed.records if isinstance(item, RoleRecord)]
        selected_roles = {
            item.key for item in role_records if item.status == RoleStatus.SELECTED
        }
        part_records = [item for item in parsed.records if isinstance(item, PartRecord)]

        parts = [
            PartProjection(
                reference=item.reference,
                role_key=item.role_key,
                part_number=item.part_number,
                quantity=item.quantity,
                instance_refs=list(expanded_references(item.reference, item.quantity)),
            )
            for item in part_records
            if item.role_key in selected_roles
        ]
        grouped: dict[str, list[PartProjection]] = defaultdict(list)
        for part in parts:
            grouped[normalize_part_number(part.part_number)].append(part)
        bom = [
            BomProjectionLine(
                normalized_part_number=key,
                part_number=items[0].part_number,
                quantity=sum(item.quantity for item in items),
                instance_refs=[ref for item in items for ref in item.instance_refs],
                role_keys=sorted({item.role_key for item in items}),
            )
            for key, items in sorted(grouped.items())
        ]
        required = [
            item for item in role_records if item.importance == RoleImportance.REQUIRED
        ]
        completeness = CircuitCompleteness(
            required_role_count=len(required),
            selected_role_count=sum(
                item.status == RoleStatus.SELECTED for item in required
            ),
            unresolved_role_count=sum(
                item.status == RoleStatus.UNRESOLVED for item in required
            ),
            invalid_role_count=sum(
                item.status == RoleStatus.INVALID for item in required
            ),
            deferred_role_count=sum(
                item.status == RoleStatus.DEFERRED for item in required
            ),
            open_issue_count=sum(
                item.record_type == RecordType.OPEN for item in key_values
            ),
            raw_bom_line_count=len(parts),
            physical_component_quantity=sum(item.quantity for item in parts),
        )
        return CircuitProjections(
            machine_goal=MachineGoalProjection(
                machine=machine.name, goal=goal.description
            ),
            constraints={
                item.key: item.value
                for item in key_values
                if item.record_type == RecordType.CONSTRAINT
            },
            blocks={
                item.key: item.value
                for item in key_values
                if item.record_type == RecordType.BLOCK
            },
            roles=[
                RoleProjection(
                    key=item.key,
                    importance=item.importance,
                    status=item.status,
                    selection=item.selection,
                )
                for item in role_records
            ],
            parts=parts,
            bom=bom,
            nets=[
                NetProjection(name=item.name, endpoints=list(item.endpoints))
                for item in parsed.records
                if isinstance(item, NetRecord)
            ],
            open_obligations={
                item.key: item.value
                for item in key_values
                if item.record_type == RecordType.OPEN
            },
            completeness=completeness,
        )


__all__ = [
    "BomProjectionLine",
    "CircuitCompleteness",
    "CircuitProjectionService",
    "CircuitProjections",
    "PartProjection",
    "normalize_part_number",
]
