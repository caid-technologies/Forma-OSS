"""Atomic patch grammar and application for circuit documents.

All operations are parsed before any mutation. The candidate document is then
fully parsed and cross-reference validated before it is returned.
"""

from __future__ import annotations

from dataclasses import dataclass

from forma_core.design_generation.circuit_document.grammar import (
    parse_document,
    parse_record_line,
    serialize_records,
)
from forma_core.design_generation.circuit_document.models import (
    CircuitDocument,
    CircuitRecord,
    RecordType,
    record_key,
)
from forma_core.design_generation.circuit_document.validation import (
    CircuitDocumentValidationError,
)


@dataclass(frozen=True)
class AddOperation:
    record: CircuitRecord


@dataclass(frozen=True)
class ReplaceOperation:
    record_type: RecordType
    key: str
    replacement: CircuitRecord


@dataclass(frozen=True)
class RemoveOperation:
    record_type: RecordType
    key: str


@dataclass(frozen=True)
class ResolveOperation:
    key: str


PatchOperation = AddOperation | ReplaceOperation | RemoveOperation | ResolveOperation


def _parse_target(value: str, *, operation: str) -> tuple[RecordType, str]:
    fields = value.strip().split()
    if len(fields) != 2:
        raise CircuitDocumentValidationError(
            [f"{operation} requires a record type and semantic key."]
        )
    try:
        record_type = RecordType(fields[0])
    except ValueError as error:
        raise CircuitDocumentValidationError(
            [f"{operation} has unknown record type '{fields[0]}'."]
        ) from error
    return record_type, fields[1]


def parse_patch(patch_text: str) -> tuple[PatchOperation, ...]:
    """Parse a complete patch, reporting every syntactic failure together."""

    operations: list[PatchOperation] = []
    errors: list[str] = []
    for line_number, source_line in enumerate(patch_text.splitlines(), start=1):
        line = source_line.strip()
        if not line:
            continue
        operation, separator, remainder = line.partition(" ")
        try:
            if operation == "ADD" and separator:
                operations.append(AddOperation(parse_record_line(remainder)))
            elif operation == "REPLACE" and separator:
                target, pipe, replacement = remainder.partition("|")
                if not pipe or not replacement.strip():
                    raise CircuitDocumentValidationError(
                        ["REPLACE requires a complete replacement record after '|'."]
                    )
                record_type, key = _parse_target(target, operation="REPLACE")
                parsed_replacement = parse_record_line(replacement.strip())
                if (
                    parsed_replacement.record_type != record_type
                    or record_key(parsed_replacement) != key
                ):
                    raise CircuitDocumentValidationError(
                        [
                            "REPLACE target must match the replacement record type and key."
                        ]
                    )
                operations.append(
                    ReplaceOperation(record_type, key, parsed_replacement)
                )
            elif operation == "REMOVE" and separator:
                record_type, key = _parse_target(remainder, operation="REMOVE")
                operations.append(RemoveOperation(record_type, key))
            elif operation == "RESOLVE" and separator and len(remainder.split()) == 1:
                operations.append(ResolveOperation(remainder.strip()))
            else:
                raise CircuitDocumentValidationError(
                    [f"Unknown or malformed patch operation '{operation}'."]
                )
        except CircuitDocumentValidationError as error:
            errors.extend(f"line {line_number}: {item}" for item in error.errors)
    if not operations and not errors:
        errors.append("Patch contains no operations.")
    if errors:
        raise CircuitDocumentValidationError(errors)
    return tuple(operations)


class CircuitPatchService:
    """Validate and apply small circuit-document mutations atomically."""

    def validate_and_apply(
        self, document: CircuitDocument, patch_text: str
    ) -> CircuitDocument:
        parsed = parse_document(document)
        operations = parse_patch(patch_text)
        records = list(parsed.records)
        errors: list[str] = []

        for index, operation in enumerate(operations, start=1):
            identities = {
                (record.record_type, record_key(record)): position
                for position, record in enumerate(records)
            }
            if isinstance(operation, AddOperation):
                identity = (operation.record.record_type, record_key(operation.record))
                if identity in identities or operation.record.record_type in {
                    RecordType.MACHINE,
                    RecordType.GOAL,
                }:
                    errors.append(
                        f"operation {index}: ADD target {identity[0].value} "
                        f"'{identity[1]}' already exists."
                    )
                else:
                    records.append(operation.record)
            elif isinstance(operation, ReplaceOperation):
                identity = (operation.record_type, operation.key)
                if identity not in identities:
                    errors.append(
                        f"operation {index}: REPLACE target {operation.record_type.value} "
                        f"'{operation.key}' does not exist."
                    )
                else:
                    records[identities[identity]] = operation.replacement
            elif isinstance(operation, RemoveOperation):
                identity = (operation.record_type, operation.key)
                if identity not in identities:
                    errors.append(
                        f"operation {index}: REMOVE target {operation.record_type.value} "
                        f"'{operation.key}' does not exist."
                    )
                else:
                    records.pop(identities[identity])
            else:
                identity = (RecordType.OPEN, operation.key)
                if identity not in identities:
                    errors.append(
                        f"operation {index}: RESOLVE target OPEN '{operation.key}' does not exist."
                    )
                else:
                    records.pop(identities[identity])
        if errors:
            raise CircuitDocumentValidationError(errors)

        candidate = serialize_records(records)
        parse_document(candidate)
        return candidate


__all__ = ["CircuitPatchService", "PatchOperation", "parse_patch"]
