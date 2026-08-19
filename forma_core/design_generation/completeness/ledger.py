"""Deterministic completeness calculations and obligation transitions."""

from __future__ import annotations

from forma_core.design_generation.completeness.models import (
    BomLineTrace,
    ComponentRole,
    DesignCompleteness,
    DesignObligation,
    ObligationStatus,
)
from forma_core.workspaces.projects.models import BOMLineItem, ComponentInstance


class CompletenessLedger:
    """Apply local transitions and measure required-obligation coverage."""

    @staticmethod
    def resolve_role(
        role: ComponentRole,
        obligations: list[DesignObligation],
        *,
        definition_id: str,
        instance_ids: list[str],
    ) -> None:
        """Resolve a role and its linked obligations with committed instances."""

        role.status = ObligationStatus.RESOLVED
        role.selected_definition_id = definition_id
        role.failure_reason = None
        obligation_ids = set(role.obligation_ids)
        for obligation in obligations:
            if obligation.obligation_id not in obligation_ids:
                continue
            obligation.status = ObligationStatus.RESOLVED
            obligation.failure_reason = None
            obligation.satisfied_by_ids = list(
                dict.fromkeys([*obligation.satisfied_by_ids, *instance_ids])
            )

    @staticmethod
    def defer_role(
        role: ComponentRole,
        obligations: list[DesignObligation],
        reason: str,
        *,
        blocked: bool = False,
    ) -> None:
        """Defer or block one role and its still-unresolved obligations."""

        status = ObligationStatus.BLOCKED if blocked else ObligationStatus.DEFERRED
        role.status = status
        role.failure_reason = reason
        role_ids = {
            item.obligation_id
            for item in obligations
            if item.obligation_id in role.obligation_ids
        }
        for obligation in obligations:
            if (
                obligation.obligation_id in role_ids
                and obligation.status != ObligationStatus.RESOLVED
            ):
                obligation.status = status
                obligation.failure_reason = reason

    @staticmethod
    def assess(
        obligations: list[DesignObligation],
        bom_lines: list[BOMLineItem],
        instances: list[ComponentInstance],
        bom_traces: list[BomLineTrace] | None = None,
        required_capabilities: list[str] | None = None,
    ) -> DesignCompleteness:
        """Calculate trace-aware completeness from persisted project records."""

        required = [item for item in obligations if item.criticality == "required"]
        counts = {status: 0 for status in ObligationStatus}
        for item in required:
            counts[item.status] += 1
        traced_line_ids = {item.line_id for item in bom_traces or []}
        valid_bom_count = (
            sum(item.line_id in traced_line_ids for item in bom_lines)
            if bom_traces is not None
            else len(bom_lines)
        )
        required_capability_keys = {
            item.strip().casefold()
            for item in required_capabilities or []
            if item.strip()
        }
        traced_capability_keys = {
            capability.strip().casefold()
            for trace in bom_traces or []
            for capability in trace.required_capabilities
            if capability.strip()
        }
        return DesignCompleteness(
            required_capability_count=len(required_capability_keys),
            covered_capability_count=len(
                required_capability_keys & traced_capability_keys
            ),
            required_obligation_count=len(required),
            resolved_obligation_count=counts[ObligationStatus.RESOLVED],
            unresolved_obligation_count=(
                counts[ObligationStatus.UNRESOLVED]
                + counts[ObligationStatus.IN_PROGRESS]
            ),
            deferred_obligation_count=counts[ObligationStatus.DEFERRED],
            blocked_obligation_count=counts[ObligationStatus.BLOCKED],
            valid_bom_line_count=valid_bom_count,
            physical_component_count=len(instances),
        )
