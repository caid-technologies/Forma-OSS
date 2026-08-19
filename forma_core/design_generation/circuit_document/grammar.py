"""Deterministic line-oriented grammar for :class:`CircuitDocument`.

Supported lines are ``MACHINE``, ``GOAL``, ``CONSTRAINT``, ``BLOCK``,
``ROLE``, ``PART``, ``NET``, and ``OPEN``. Blank lines are ignored. Every
other nonblank line is parsed strictly; malformed or unknown records are never
discarded. Serialization uses fixed record-type order and semantic-key order
while retaining each validated record's exact source text.
"""

from __future__ import annotations

import re
from collections import Counter

from forma_core.design_generation.circuit_document.models import (
    CircuitDocument,
    CircuitRecord,
    GoalRecord,
    KeyValueRecord,
    MachineRecord,
    NetRecord,
    ParsedCircuitDocument,
    PartRecord,
    RecordType,
    RoleImportance,
    RoleRecord,
    RoleStatus,
    record_key,
)
from forma_core.design_generation.circuit_document.validation import (
    CircuitDocumentValidationError,
    validate_cross_references,
)

_SEMANTIC_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_PART_REFERENCE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
_ORDER = {record_type: index for index, record_type in enumerate(RecordType)}


def _require_key(value: str, *, label: str) -> str:
    value = value.strip()
    if not _SEMANTIC_KEY.fullmatch(value):
        raise CircuitDocumentValidationError(
            [f"Invalid {label} semantic key '{value}'."]
        )
    return value


def _split_fields(line: str, expected: int) -> list[str]:
    fields = re.split(r"\s*\|\s*", line)
    if len(fields) != expected or any(not item.strip() for item in fields):
        raise CircuitDocumentValidationError(
            [f"Malformed {line.split(maxsplit=1)[0]} record: '{line}'."]
        )
    return [item.strip() for item in fields]


def parse_record_line(line: str) -> CircuitRecord:
    """Parse one complete nonblank record without cross-record validation."""

    raw = line.rstrip("\r\n")
    stripped = raw.strip()
    if not stripped:
        raise CircuitDocumentValidationError(["A record line cannot be blank."])
    record_name, _, remainder = stripped.partition(" ")
    try:
        record_type = RecordType(record_name)
    except ValueError as error:
        raise CircuitDocumentValidationError(
            [f"Unknown record type '{record_name}'."]
        ) from error

    if record_type == RecordType.MACHINE:
        return MachineRecord(name=_require_key(remainder, label="MACHINE"), raw=raw)
    if record_type == RecordType.GOAL:
        if not remainder.strip() or "|" in remainder:
            raise CircuitDocumentValidationError([f"Malformed GOAL record: '{raw}'."])
        return GoalRecord(description=remainder.strip(), raw=raw)
    if record_type in {RecordType.CONSTRAINT, RecordType.BLOCK, RecordType.OPEN}:
        head, value = _split_fields(stripped, 2)
        _, _, key = head.partition(" ")
        return KeyValueRecord(
            record_type=record_type,
            key=_require_key(key, label=record_type.value),
            value=value,
            raw=raw,
        )
    if record_type == RecordType.ROLE:
        head, importance, status, selection = _split_fields(stripped, 4)
        _, _, key = head.partition(" ")
        try:
            parsed_importance = RoleImportance(importance)
            parsed_status = RoleStatus(status)
        except ValueError as error:
            raise CircuitDocumentValidationError(
                [f"Invalid ROLE field in '{raw}'."]
            ) from error
        return RoleRecord(
            key=_require_key(key, label="ROLE"),
            importance=parsed_importance,
            status=parsed_status,
            selection=selection,
            raw=raw,
        )
    if record_type == RecordType.PART:
        head, role_field, part_field, quantity_field = _split_fields(stripped, 4)
        _, _, reference = head.partition(" ")
        reference = reference.strip()
        if not _PART_REFERENCE.fullmatch(reference):
            raise CircuitDocumentValidationError(
                [f"Invalid PART reference '{reference}'."]
            )
        if (
            not role_field.startswith("role=")
            or not part_field.startswith("part=")
            or not quantity_field.startswith("qty=")
        ):
            raise CircuitDocumentValidationError([f"Malformed PART fields in '{raw}'."])
        role_key = _require_key(role_field.removeprefix("role="), label="PART role")
        part_number = part_field.removeprefix("part=").strip()
        try:
            quantity = int(quantity_field.removeprefix("qty="))
        except ValueError as error:
            raise CircuitDocumentValidationError(
                [f"Invalid PART quantity in '{raw}'."]
            ) from error
        if quantity < 1 or not part_number:
            raise CircuitDocumentValidationError([f"Invalid PART fields in '{raw}'."])
        return PartRecord(
            reference=reference,
            role_key=role_key,
            part_number=part_number,
            quantity=quantity,
            raw=raw,
        )
    head, endpoints = _split_fields(stripped, 2)
    _, _, name = head.partition(" ")
    endpoint_tokens = tuple(endpoints.split())
    if not endpoint_tokens:
        raise CircuitDocumentValidationError([f"NET '{name}' has no endpoints."])
    return NetRecord(
        name=_require_key(name, label="NET"), endpoints=endpoint_tokens, raw=raw
    )


def parse_document(document: CircuitDocument) -> ParsedCircuitDocument:
    """Parse and fully validate a circuit document."""

    records: list[CircuitRecord] = []
    errors: list[str] = []
    for line_number, line in enumerate(document.text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(parse_record_line(line))
        except CircuitDocumentValidationError as error:
            errors.extend(f"line {line_number}: {item}" for item in error.errors)
    if errors:
        raise CircuitDocumentValidationError(errors)

    singleton_counts = Counter(record.record_type for record in records)
    for singleton in (RecordType.MACHINE, RecordType.GOAL):
        if singleton_counts[singleton] != 1:
            errors.append(
                f"Document must contain exactly one {singleton.value} record."
            )
    seen: set[tuple[RecordType, str]] = set()
    for record in records:
        identity = (record.record_type, record_key(record))
        if identity in seen:
            errors.append(f"Duplicate {record.record_type.value} key '{identity[1]}'.")
        seen.add(identity)
    if errors:
        raise CircuitDocumentValidationError(errors)
    parsed = ParsedCircuitDocument(records=tuple(records))
    validate_cross_references(parsed)
    return parsed


def serialize_records(
    records: tuple[CircuitRecord, ...] | list[CircuitRecord],
) -> CircuitDocument:
    """Serialize records in deterministic type/key order without rewriting lines."""

    ordered = sorted(
        records,
        key=lambda item: (_ORDER[item.record_type], record_key(item).casefold()),
    )
    return CircuitDocument(text="\n".join(record.raw for record in ordered))


def serialize_document(parsed: ParsedCircuitDocument) -> CircuitDocument:
    """Serialize a parsed document deterministically."""

    return serialize_records(parsed.records)


__all__ = [
    "parse_document",
    "parse_record_line",
    "serialize_document",
    "serialize_records",
]
