"""Validation errors and cross-record checks for circuit documents."""

from __future__ import annotations

import re

from forma_core.design_generation.circuit_document.models import (
    NetRecord,
    ParsedCircuitDocument,
    PartRecord,
    RoleRecord,
)


class CircuitDocumentValidationError(ValueError):
    """Explicit focused errors suitable for a subsequent repair prompt."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def expanded_references(reference: str, quantity: int) -> tuple[str, ...]:
    """Expand a numeric reference range or deterministically enumerate a quantity."""

    match = re.fullmatch(
        r"([A-Za-z][A-Za-z0-9_]*)?(\d+)-([A-Za-z][A-Za-z0-9_]*)?(\d+)", reference
    )
    if match:
        first_prefix = match.group(1) or ""
        last_prefix = match.group(3) or first_prefix
        first = int(match.group(2))
        last = int(match.group(4))
        if first_prefix != last_prefix or last < first:
            raise CircuitDocumentValidationError(
                [f"Invalid PART reference range '{reference}'."]
            )
        refs = tuple(f"{first_prefix}{index}" for index in range(first, last + 1))
        if len(refs) != quantity:
            raise CircuitDocumentValidationError(
                [
                    f"PART '{reference}' range contains {len(refs)} references but qty is {quantity}."
                ]
            )
        return refs
    if quantity == 1:
        return (reference,)
    return tuple(f"{reference}.{index}" for index in range(1, quantity + 1))


def validate_cross_references(parsed: ParsedCircuitDocument) -> None:
    """Reject unknown role references and locally resolvable unknown net endpoints."""

    roles = {record.key for record in parsed.records if isinstance(record, RoleRecord)}
    parts = [record for record in parsed.records if isinstance(record, PartRecord)]
    errors = [
        f"PART '{part.reference}' references unknown role '{part.role_key}'."
        for part in parts
        if part.role_key not in roles
    ]
    local_references: set[str] = set()
    for part in parts:
        try:
            local_references.update(expanded_references(part.reference, part.quantity))
        except CircuitDocumentValidationError as error:
            errors.extend(error.errors)
    for net in (record for record in parsed.records if isinstance(record, NetRecord)):
        for endpoint in net.endpoints:
            if "=" in endpoint or "." not in endpoint:
                continue
            reference = endpoint.rsplit(".", 1)[0]
            if reference not in local_references:
                errors.append(
                    f"NET '{net.name}' references unknown local part reference '{reference}'."
                )
    if errors:
        raise CircuitDocumentValidationError(errors)


__all__ = [
    "CircuitDocumentValidationError",
    "expanded_references",
    "validate_cross_references",
]
