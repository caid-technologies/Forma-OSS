"""Small contracts for the experimental line-oriented circuit document.

Only :class:`CircuitDocument` is agent-facing. Parsed records are immutable,
application-owned views used by grammar, validation, patches, and projections.
They deliberately contain no project identity, provider, workflow, or runtime
metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class CircuitDocument(BaseModel):
    """Compressed agent-facing representation of a machine design."""

    model_config = ConfigDict(extra="forbid")

    text: str


class RecordType(StrEnum):
    """Supported line-oriented record types in serialization order."""

    MACHINE = "MACHINE"
    GOAL = "GOAL"
    CONSTRAINT = "CONSTRAINT"
    BLOCK = "BLOCK"
    ROLE = "ROLE"
    PART = "PART"
    NET = "NET"
    OPEN = "OPEN"


class RoleImportance(StrEnum):
    """Whether a physical role is mandatory or optional."""

    REQUIRED = "required"
    PREFERRED = "preferred"


class RoleStatus(StrEnum):
    """Resolution state supported by a ROLE record."""

    SELECTED = "selected"
    UNRESOLVED = "unresolved"
    INVALID = "invalid"
    DEFERRED = "deferred"


@dataclass(frozen=True)
class MachineRecord:
    name: str
    raw: str
    record_type: RecordType = RecordType.MACHINE


@dataclass(frozen=True)
class GoalRecord:
    description: str
    raw: str
    record_type: RecordType = RecordType.GOAL


@dataclass(frozen=True)
class KeyValueRecord:
    record_type: RecordType
    key: str
    value: str
    raw: str


@dataclass(frozen=True)
class RoleRecord:
    key: str
    importance: RoleImportance
    status: RoleStatus
    selection: str
    raw: str
    record_type: RecordType = RecordType.ROLE


@dataclass(frozen=True)
class PartRecord:
    reference: str
    role_key: str
    part_number: str
    quantity: int
    raw: str
    record_type: RecordType = RecordType.PART


@dataclass(frozen=True)
class NetRecord:
    name: str
    endpoints: tuple[str, ...]
    raw: str
    record_type: RecordType = RecordType.NET


CircuitRecord = (
    MachineRecord | GoalRecord | KeyValueRecord | RoleRecord | PartRecord | NetRecord
)


@dataclass(frozen=True)
class ParsedCircuitDocument:
    """Validated ordered record collection produced by the deterministic parser."""

    records: tuple[CircuitRecord, ...]


def record_key(record: CircuitRecord) -> str:
    """Return the semantic patch and duplicate-detection key for one record."""

    if isinstance(record, MachineRecord):
        return record.name
    if isinstance(record, GoalRecord):
        return "goal"
    if isinstance(record, KeyValueRecord):
        return record.key
    if isinstance(record, RoleRecord):
        return record.key
    if isinstance(record, PartRecord):
        return record.reference
    return record.name


__all__ = [
    "CircuitDocument",
    "CircuitRecord",
    "GoalRecord",
    "KeyValueRecord",
    "MachineRecord",
    "NetRecord",
    "ParsedCircuitDocument",
    "PartRecord",
    "RecordType",
    "RoleImportance",
    "RoleRecord",
    "RoleStatus",
    "record_key",
]
