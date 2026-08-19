"""Bounded generation of obligations and abstract component roles."""

from __future__ import annotations

import json
from collections.abc import Callable
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from forma_core.design_generation.completeness.models import (
    BomGapReview,
    ComponentRole,
    ComponentRoleDraft,
    DesignObligation,
    DesignObligationDraft,
    SubsystemPlan,
    SubsystemPlanDraft,
)
from forma_core.design_generation.intent.models import MachineIntent
from forma_core.design_generation.intent.service import StructuredGenerator
from forma_core.workspaces.projects.models import PartDefinition


class ObligationDraftList(BaseModel):
    """Structured provider envelope for obligation drafts."""

    model_config = ConfigDict(extra="forbid")
    obligations: list[DesignObligationDraft] = Field(default_factory=list)


class ComponentRoleDraftList(BaseModel):
    """Structured provider envelope for component-role drafts."""

    model_config = ConfigDict(extra="forbid")
    roles: list[ComponentRoleDraft] = Field(default_factory=list)


class BomGapReviewDraft(BaseModel):
    """Bounded provider review containing only missing procurement roles."""

    model_config = ConfigDict(extra="forbid")
    is_complete: bool
    missing_roles: list[ComponentRoleDraft] = Field(default_factory=list)


class SubsystemPlanDraftList(BaseModel):
    """Structured provider envelope for subsystem drafts."""

    model_config = ConfigDict(extra="forbid")
    subsystems: list[SubsystemPlanDraft] = Field(default_factory=list)


class DesignPlanningService:
    """Expand intent without choosing physical parts or detailed metadata."""

    def __init__(
        self,
        generator: StructuredGenerator,
        *,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.generator = generator
        self.id_factory = id_factory or (lambda: str(uuid4()))

    def expand_obligations(self, intent: MachineIntent) -> list[DesignObligation]:
        """Derive obligations and ensure each required capability is covered."""

        raw = self.generator.generate(
            "Expand every capability into explicit functional, electrical, mechanical, interface, power, "
            "safety, or manufacturing obligations. Every required capability must have at least one. "
            "Do not choose components, part numbers, pins, wiring, IDs, or metadata.\n\n"
            f"Machine intent:\n{intent.model_dump_json(indent=2, exclude={'intent_id', 'project_id', 'source_prompt'})}",
            ObligationDraftList,
        )
        drafts = (
            raw
            if isinstance(raw, ObligationDraftList)
            else ObligationDraftList.model_validate(raw)
        )
        canonical_capabilities = {
            capability.casefold(): capability
            for capability in intent.required_capabilities
        }
        obligations = [
            DesignObligation(
                obligation_id=self.id_factory(),
                **draft.model_copy(
                    update={
                        "capability_name": canonical_capabilities[
                            draft.capability_name.casefold()
                        ]
                    }
                ).model_dump(),
            )
            for draft in drafts.obligations
            if draft.capability_name.casefold() in canonical_capabilities
        ]
        covered = {item.capability_name.casefold() for item in obligations}
        for capability in intent.required_capabilities:
            if capability.casefold() not in covered:
                obligations.append(
                    DesignObligation(
                        obligation_id=self.id_factory(),
                        capability_name=capability,
                        description=capability,
                        obligation_type="functional",
                        criticality="required",
                    )
                )
        return obligations

    def plan_subsystems(
        self,
        intent: MachineIntent,
        obligations: list[DesignObligation],
    ) -> list[SubsystemPlan]:
        """Group obligations into functional systems before planning roles."""

        raw = self.generator.generate(
            "Group these design obligations into concise functional subsystems. Do not choose components, "
            "part numbers, pins, wiring, sourcing, or IDs. Relate subsystems to obligations by copying "
            "obligation descriptions exactly.\n\n"
            f"Machine intent: {intent.model_dump_json(exclude={'intent_id', 'project_id', 'source_prompt'})}\n"
            f"Obligations: {json.dumps([item.model_dump(exclude={'obligation_id', 'status', 'satisfied_by_ids', 'failure_reason'}) for item in obligations], indent=2)}",
            SubsystemPlanDraftList,
        )
        drafts = (
            raw
            if isinstance(raw, SubsystemPlanDraftList)
            else SubsystemPlanDraftList.model_validate(raw)
        )
        by_description = {
            item.description.casefold(): item.obligation_id for item in obligations
        }
        subsystems = [
            SubsystemPlan(
                subsystem_id=self.id_factory(),
                name=draft.name,
                purpose=draft.purpose,
                obligation_ids=list(
                    dict.fromkeys(
                        by_description[description.casefold()]
                        for description in draft.obligation_descriptions
                        if description.casefold() in by_description
                    )
                ),
            )
            for draft in drafts.subsystems
        ]
        covered_obligation_ids = {
            obligation_id
            for subsystem in subsystems
            for obligation_id in subsystem.obligation_ids
        }
        uncovered_obligation_ids = [
            item.obligation_id
            for item in obligations
            if item.obligation_id not in covered_obligation_ids
        ]
        if uncovered_obligation_ids:
            subsystems.append(
                SubsystemPlan(
                    subsystem_id=self.id_factory(),
                    name="Unassigned requirements",
                    purpose="Hold obligations not assigned by subsystem planning.",
                    obligation_ids=uncovered_obligation_ids,
                )
            )
        return subsystems

    def plan_component_roles(
        self,
        intent: MachineIntent,
        obligations: list[DesignObligation],
        subsystems: list[SubsystemPlan],
    ) -> list[ComponentRole]:
        """Derive abstract roles from intent, obligations, and subsystems."""

        obligation_payload = [
            item.model_dump(
                exclude={
                    "obligation_id",
                    "status",
                    "satisfied_by_ids",
                    "failure_reason",
                }
            )
            for item in obligations
        ]
        raw = self.generator.generate(
            "Plan an implementation-ready procurement BOM as abstract component roles. A role must represent "
            "a physical item that will later be selected and purchased or fabricated, not merely a functional "
            "block. Cover the primary functions and the support circuitry needed to assemble and operate the "
            "machine: power entry and conversion, protection, required decoupling and bulk capacitance, bias "
            "and pull resistors, clocking when external, programming/debug access, connectors and interconnect, "
            "fabrication substrate, enclosure, mounting, and fasteners. Do not inflate the BOM with parts already "
            "integrated into a justified module, but do not assume support parts are integrated unless the role "
            "explicitly requires an integrated module. Do not select manufacturers, physical part numbers, pins, "
            "sourcing, reference designators, or IDs. Relate every role to obligations by copying their descriptions "
            "exactly.\n\n"
            f"Machine intent: {intent.model_dump_json(exclude={'intent_id', 'project_id', 'source_prompt'})}\n"
            f"Obligations: {json.dumps(obligation_payload, indent=2)}\n"
            f"Subsystems: {json.dumps([item.model_dump(exclude={'subsystem_id'}) for item in subsystems], indent=2)}",
            ComponentRoleDraftList,
        )
        drafts = (
            raw
            if isinstance(raw, ComponentRoleDraftList)
            else ComponentRoleDraftList.model_validate(raw)
        )
        return self._canonicalize_roles(drafts.roles, obligations, subsystems)

    def audit_component_roles(
        self,
        intent: MachineIntent,
        obligations: list[DesignObligation],
        subsystems: list[SubsystemPlan],
        roles: list[ComponentRole],
        selected_definitions: list[PartDefinition],
    ) -> BomGapReview:
        """Find procurement gaps after real parts have been selected."""

        obligation_payload = [
            item.model_dump(
                exclude={
                    "obligation_id",
                    "status",
                    "satisfied_by_ids",
                    "failure_reason",
                }
            )
            for item in obligations
        ]
        role_payload = [
            item.model_dump(
                exclude={
                    "role_id",
                    "subsystem_id",
                    "obligation_ids",
                    "selected_definition_id",
                    "failure_reason",
                }
            )
            for item in roles
        ]
        definition_payload = [
            {
                "manufacturer": item.manufacturer,
                "part_number": item.part_number,
                "name": item.name,
                "category": item.category,
                "description": item.description,
            }
            for item in selected_definitions
        ]
        raw = self.generator.generate(
            "Act as a strict BOM-completeness reviewer for an implementation-ready low-voltage hardware build. "
            "Return only genuinely missing physical procurement roles; do not rewrite or duplicate existing roles. "
            "Use the selected part identities to distinguish integrated modules from bare devices. Check the entire "
            "power path from input connector through protection and regulation, mandatory datasheet support parts, "
            "decoupling and bulk capacitors, interface pull-ups or level shifting, programming/debug access, physical "
            "interconnect, PCB or prototyping substrate, enclosure, mounting, and fasteners. A BOM is complete only "
            "when the listed items can be assembled into the requested machine without undeclared electrical or "
            "mechanical parts. Do not add optional accessories or inflate part count. Copy obligation descriptions "
            "exactly when relating each missing role. Set is_complete true only when no missing roles remain.\n\n"
            f"Machine intent: {intent.model_dump_json(exclude={'intent_id', 'project_id', 'source_prompt'})}\n"
            f"Obligations: {json.dumps(obligation_payload, indent=2)}\n"
            f"Subsystems: {json.dumps([item.model_dump(exclude={'subsystem_id', 'obligation_ids'}) for item in subsystems], indent=2)}\n"
            f"Existing roles: {json.dumps(role_payload, indent=2)}\n"
            f"Selected parts: {json.dumps(definition_payload, indent=2)}",
            BomGapReviewDraft,
        )
        draft = (
            raw
            if isinstance(raw, BomGapReviewDraft)
            else BomGapReviewDraft.model_validate(raw)
        )
        missing_roles = self._canonicalize_roles(
            draft.missing_roles,
            obligations,
            subsystems,
            existing_roles=roles,
        )
        return BomGapReview(
            is_complete=draft.is_complete and not missing_roles,
            missing_roles=missing_roles,
        )

    def _canonicalize_roles(
        self,
        drafts: list[ComponentRoleDraft],
        obligations: list[DesignObligation],
        subsystems: list[SubsystemPlan],
        *,
        existing_roles: list[ComponentRole] | None = None,
    ) -> list[ComponentRole]:
        """Assign IDs and canonical relationships to bounded role drafts."""

        existing_roles = existing_roles or []
        existing_keys = {
            (item.name.strip().casefold(), item.function.strip().casefold())
            for item in existing_roles
        }
        unique_drafts: list[ComponentRoleDraft] = []
        seen = set(existing_keys)
        for draft in drafts:
            key = (draft.name.strip().casefold(), draft.function.strip().casefold())
            if key in seen:
                continue
            seen.add(key)
            unique_drafts.append(draft)

        by_description = {
            item.description.casefold(): item.obligation_id for item in obligations
        }
        subsystem_id_by_name = {
            item.name.casefold(): item.subsystem_id for item in subsystems
        }
        default_subsystem = subsystems[0] if subsystems else None
        role_ids = [self.id_factory() for _ in unique_drafts]
        role_id_by_name = {
            item.name.casefold(): item.role_id for item in existing_roles
        }
        role_id_by_name.update(
            {
                draft.name.casefold(): role_id
                for draft, role_id in zip(unique_drafts, role_ids)
            }
        )
        return [
            ComponentRole(
                role_id=role_id,
                subsystem_id=(
                    subsystem_id_by_name.get(draft.subsystem_name.casefold())
                    or (
                        default_subsystem.subsystem_id
                        if default_subsystem is not None
                        else None
                    )
                ),
                subsystem_name=(
                    draft.subsystem_name
                    if draft.subsystem_name.casefold() in subsystem_id_by_name
                    else (
                        default_subsystem.name
                        if default_subsystem is not None
                        else draft.subsystem_name
                    )
                ),
                name=draft.name,
                function=draft.function,
                obligation_ids=list(
                    dict.fromkeys(
                        by_description[description.casefold()]
                        for description in draft.obligation_descriptions
                        if description.casefold() in by_description
                    )
                ),
                requirements=draft.requirements,
                quantity=draft.quantity,
                depends_on_role_ids=list(
                    dict.fromkeys(
                        role_id_by_name[name.casefold()]
                        for name in draft.depends_on_role_names
                        if name.casefold() in role_id_by_name
                    )
                ),
            )
            for draft, role_id in zip(unique_drafts, role_ids)
        ]
