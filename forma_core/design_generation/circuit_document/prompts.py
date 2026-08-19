"""Bounded prompt construction for circuit-document generation and repair."""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict

from forma_core.design_generation.circuit_document.models import CircuitDocument
from forma_core.design_generation.circuit_document.projections import CircuitProjections
from forma_core.design_generation.intent.models import MachineIntent


class CircuitPatchDraft(BaseModel):
    """Agent-produced patch text with no runtime or persistence metadata."""

    model_config = ConfigDict(extra="forbid")

    text: str


def _semantic_intent(intent: MachineIntent) -> dict[str, object]:
    return intent.model_dump(exclude={"intent_id", "project_id", "source_prompt"})


def build_initial_document_prompt(intent: MachineIntent) -> str:
    """Build initial context from normalized intent, never the original prompt."""

    return (
        "Create a compact line-oriented CircuitDocument for this normalized machine intent. "
        "Return only the document text. Use exactly one MACHINE and GOAL, then CONSTRAINT, "
        "BLOCK, ROLE, PART, NET, and OPEN records where justified. Use stable semantic keys. "
        "Every physical item needed for a build must have a ROLE; select exact manufacturer "
        "part numbers only when supported, otherwise mark the role unresolved and add an OPEN. "
        "Prioritize a complete, high-quality BOM over descriptive metadata. For applicable "
        "USB-powered embedded designs explicitly consider connector configuration, protection, "
        "regulation, input/output capacitance, controller decoupling and reset, sensor support, "
        "bus pull-ups, display support, programming controls, PCB, enclosure, and mounting.\n\n"
        "Grammar:\n"
        "MACHINE <semantic-name>\nGOAL <description>\n"
        "CONSTRAINT <semantic-key> | <value>\nBLOCK <semantic-key> | <description>\n"
        "ROLE <semantic-key> | <required-or-preferred> | "
        "<selected|unresolved|invalid|deferred> | <selection-or-description>\n"
        "PART <reference> | role=<role-key> | part=<manufacturer-part-number> | qty=<quantity>\n"
        "NET <semantic-name> | <space-separated-endpoints>\n"
        "OPEN <semantic-key> | <description>\n\n"
        f"Normalized intent: {json.dumps(_semantic_intent(intent), sort_keys=True)}"
    )


def build_targeted_patch_prompt(
    *,
    document: CircuitDocument,
    target_key: str,
    intent: MachineIntent,
    projections: CircuitProjections,
    evidence: list[str],
    validation_failures: list[str] | None = None,
) -> str:
    """Build focused repair context with no HardwareIR or operational records."""

    target_root = target_key.split(".", 1)[0]
    relevant_roots = {target_root}
    if target_root in {"bus", "display", "programming", "sensing"}:
        relevant_roots.update({"control", "power"})
    elif target_root in {"control", "usb"}:
        relevant_roots.add("power")
    selections = [
        {"role": role.key, "selection": role.selection}
        for role in projections.roles
        if role.status.value == "selected"
        and role.key.split(".", 1)[0] in relevant_roots
    ]
    context = {
        "target": target_key,
        "intent_constraints": intent.constraints,
        "material_selections": selections,
        "targeted_evidence": evidence,
        "preceding_validation_failures": validation_failures or [],
    }
    return (
        "Resolve exactly the named target using the smallest atomic CircuitDocument patch. "
        "Return patch text only. Supported operations are ADD <complete-record>, REPLACE "
        "<record-type> <record-key> | <complete-replacement-record>, REMOVE <record-type> "
        "<record-key>, and RESOLVE <open-key>. Do not regenerate the document or introduce "
        "unrelated changes.\n\n"
        f"CircuitDocument:\n{document.text}\n\n"
        f"Focused context: {json.dumps(context, sort_keys=True)}"
    )


__all__ = [
    "CircuitPatchDraft",
    "build_initial_document_prompt",
    "build_targeted_patch_prompt",
]
