"""Readable policy for selecting one bounded unresolved role."""

from __future__ import annotations

from forma_core.design_generation.completeness.models import (
    ComponentRole,
    DesignObligation,
    ObligationStatus,
)

_FOUNDATION_TERMS = (
    "power",
    "supply",
    "regulat",
    "controller",
    "processor",
    "microcontroller",
)


def select_next_role(
    roles: list[ComponentRole],
    obligations: list[DesignObligation],
    attempt_counts: dict[str, int] | None = None,
) -> ComponentRole | None:
    """Prefer required, foundational, high-coverage, and unattempted roles."""

    attempts = attempt_counts or {}
    obligations_by_id = {item.obligation_id: item for item in obligations}
    role_by_id = {item.role_id: item for item in roles}

    candidates: list[tuple[tuple[int, int, int, int, int], ComponentRole]] = []
    for index, role in enumerate(roles):
        if role.status != ObligationStatus.UNRESOLVED:
            continue
        if any(
            role_by_id.get(dependency_id) is not None
            and role_by_id[dependency_id].status != ObligationStatus.RESOLVED
            for dependency_id in role.depends_on_role_ids
        ):
            continue
        linked = [
            obligations_by_id[item]
            for item in role.obligation_ids
            if item in obligations_by_id
        ]
        required = any(item.criticality == "required" for item in linked)
        label = f"{role.subsystem_name} {role.name} {role.function}".lower()
        foundational = any(term in label for term in _FOUNDATION_TERMS)
        candidates.append(
            (
                (
                    0 if required else 1,
                    0 if foundational else 1,
                    -len(role.obligation_ids),
                    0 if attempts.get(role.role_id, 0) == 0 else 1,
                    index,
                ),
                role,
            )
        )
    return min(candidates, key=lambda item: item[0])[1] if candidates else None
