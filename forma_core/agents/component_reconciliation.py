"""Deterministic reconciliation for catalog parts explicitly named by a user."""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

from forma_core.workspaces.projects.models import ComponentInstance


_PREFIX_BY_CATEGORY = {
    "microcontroller": "U",
    "sensor": "SEN",
    "actuator": "ACT",
    "display": "DISP",
    "power": "PWR",
    "communication": "COM",
}
_IGNORED_PART_TOKENS = {"generic", "plug"}
_NAMED_COMPONENT_TOKENS = {"display", "led", "relay", "sensor", "servo"}


def _tokens(value: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for token in re.findall(r"[a-z0-9]+", value.lower()):
        resistance = re.fullmatch(r"(\d+)r", token)
        if resistance:
            tokens.extend((resistance.group(1), "ohm"))
        else:
            tokens.append(token)
    return tuple(tokens)


def _part_is_explicitly_requested(prompt: str, part_number: str) -> bool:
    prompt_tokens = set(_tokens(prompt))
    part_tokens = tuple(token for token in _tokens(part_number) if token not in _IGNORED_PART_TOKENS)
    if not part_tokens:
        return False
    normalized_prompt = "".join(_tokens(prompt))
    normalized_part = "".join(part_tokens)
    if normalized_part and normalized_part in normalized_prompt:
        return True
    distinctive = any(any(character.isdigit() for character in token) for token in part_tokens) or any(
        token in _NAMED_COMPONENT_TOKENS for token in part_tokens
    )
    return set(part_tokens).issubset(prompt_tokens) and distinctive


def _ref_des_prefix(template: Mapping[str, Any]) -> str:
    category = str(template.get("category") or "").strip().lower()
    if category == "passives":
        text = f"{template.get('part_number') or ''} {template.get('name') or ''}".lower()
        return "LED" if "led" in text else "R" if "resistor" in text else "P"
    return _PREFIX_BY_CATEGORY.get(category, "C")


def _next_ref_des(prefix: str, used: set[str]) -> str:
    index = 1
    while f"{prefix}{index}" in used:
        index += 1
    return f"{prefix}{index}"


def reconcile_explicit_catalog_components(
    prompt: str,
    components: Iterable[ComponentInstance],
    catalog: Iterable[Mapping[str, Any]],
) -> tuple[list[ComponentInstance], list[str]]:
    """Add exact catalog parts named in the prompt when the model omitted them."""
    reconciled = list(components)
    selected_parts = {component.part_number for component in reconciled}
    used_refs = {component.ref_des for component in reconciled}
    added: list[str] = []
    for template in catalog:
        part_number = str(template.get("part_number") or "").strip()
        if not part_number or part_number in selected_parts:
            continue
        if not _part_is_explicitly_requested(prompt, part_number):
            continue
        prefix = _ref_des_prefix(template)
        ref_des = _next_ref_des(prefix, used_refs)
        component = ComponentInstance(
            ref_des=ref_des,
            part_number=part_number,
            name=str(template.get("name") or part_number),
            category=str(template.get("category") or "Component"),
            unit_price=float(template.get("price") or template.get("unit_price") or 0.0),
            sourcing_url=template.get("sourcing_url"),
            rationale="Explicitly requested catalog part; restored by deterministic component reconciliation.",
            pins=template.get("pins") or [],
        )
        reconciled.append(component)
        selected_parts.add(part_number)
        used_refs.add(ref_des)
        added.append(part_number)
    return reconciled, added


__all__ = ["reconcile_explicit_catalog_components"]
