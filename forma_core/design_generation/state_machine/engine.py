"""Explicit intent-first generation controller."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol
from uuid import uuid4

from forma_core.design_generation.compiler import HardwareIRCompiler
from forma_core.design_generation.completeness.ledger import CompletenessLedger
from forma_core.design_generation.completeness.models import (
    BomGapReview,
    BomLineTrace,
    ComponentRole,
    DesignObligation,
    ObligationStatus,
    SubsystemPlan,
)
from forma_core.design_generation.completeness.policy import select_next_role
from forma_core.design_generation.components.selection import PartSelectionDraft
from forma_core.design_generation.components.validation import ComponentValidationResult
from forma_core.design_generation.intent.models import MachineIntent, MachineIntentDraft
from forma_core.design_generation.repository import (
    DesignCheckpointError,
    DesignGenerationRepository,
    ProjectFragments,
)
from forma_core.design_generation.state_machine.models import (
    DesignGenerationState,
    GenerationCompleteness,
    GenerationFailure,
    GenerationFailureSummary,
    GenerationOptions,
    GenerationPhase,
    GenerationStatus,
    ProjectGenerationResult,
)
from forma_core.workspaces.projects.models import (
    ComponentInstance,
    HardwareIR,
    PartDefinition,
    derive_bom_line_items,
)


class IntentOperations(Protocol):
    """Intent operations used only by the prompt-consuming feature boundary."""

    def generate(self, *, prompt: str) -> MachineIntentDraft: ...
    def create_intent(
        self,
        *,
        project_id: str,
        source_prompt: str,
        draft: MachineIntentDraft,
    ) -> MachineIntent: ...


class PlanningOperations(Protocol):
    def expand_obligations(self, intent: MachineIntent) -> list[DesignObligation]: ...
    def plan_subsystems(
        self,
        intent: MachineIntent,
        obligations: list[DesignObligation],
    ) -> list[SubsystemPlan]: ...
    def plan_component_roles(
        self,
        intent: MachineIntent,
        obligations: list[DesignObligation],
        subsystems: list[SubsystemPlan],
    ) -> list[ComponentRole]: ...

    def audit_component_roles(
        self,
        intent: MachineIntent,
        obligations: list[DesignObligation],
        subsystems: list[SubsystemPlan],
        roles: list[ComponentRole],
        selected_definitions: list[PartDefinition],
    ) -> BomGapReview: ...


class SelectionOperations(Protocol):
    def select_part(
        self,
        role: ComponentRole,
        intent_constraints: list[str],
        selected_dependencies: list[PartDefinition],
    ) -> PartSelectionDraft: ...


class EnrichmentOperations(Protocol):
    def enrich_component(self, selection: PartSelectionDraft) -> PartDefinition: ...


class ComponentValidationOperations(Protocol):
    def validate_component(
        self, definition: PartDefinition
    ) -> ComponentValidationResult: ...


class WiringOperations(Protocol):
    def generate_wiring(
        self,
        project_id: str,
        intent: MachineIntent,
        definitions: list[PartDefinition],
        instances: list[ComponentInstance],
    ) -> ProjectFragments: ...


class ProjectValidationOperations(Protocol):
    def validate_project(self, project: HardwareIR) -> HardwareIR: ...


class DesignGenerationEngine:
    """Resolve and persist one bounded component role at a time."""

    def __init__(
        self,
        *,
        repository: DesignGenerationRepository,
        intent_service: IntentOperations,
        planning_service: PlanningOperations,
        selection_service: SelectionOperations,
        enrichment_service: EnrichmentOperations,
        component_validator: ComponentValidationOperations,
        compiler: HardwareIRCompiler | None = None,
        wiring_service: WiringOperations | None = None,
        project_validator: ProjectValidationOperations | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.repository = repository
        self.intent_service = intent_service
        self.planning_service = planning_service
        self.selection_service = selection_service
        self.enrichment_service = enrichment_service
        self.component_validator = component_validator
        self.compiler = compiler or HardwareIRCompiler(repository)
        self.wiring_service = wiring_service
        self.project_validator = project_validator
        self.id_factory = id_factory or (lambda: str(uuid4()))

    def start(
        self,
        *,
        run_id: str,
        project_id: str,
        intent_id: str,
        options: GenerationOptions | None = None,
    ) -> ProjectGenerationResult:
        """Start a new run from an already persisted canonical intent ID."""

        options = options or GenerationOptions()
        state = DesignGenerationState(
            run_id=run_id,
            project_id=project_id,
            intent_id=intent_id,
            phase=GenerationPhase.EXPAND_OBLIGATIONS,
            status=GenerationStatus.RUNNING,
        )
        self.repository.save_state(state)
        try:
            intent = self.repository.get_intent_by_id(intent_id)
            if intent is None or intent.project_id != project_id:
                raise ValueError(
                    f"Machine intent '{intent_id}' was not found for project '{project_id}'."
                )
            obligations = self.expand_obligations(intent, state)
            subsystems = self.plan_subsystems(intent, obligations, state)
            roles = self.plan_component_roles(intent, obligations, subsystems, state)
            if len(roles) > options.max_component_roles:
                for role in roles[options.max_component_roles :]:
                    CompletenessLedger.defer_role(
                        role,
                        obligations,
                        f"Generation role limit of {options.max_component_roles} was reached.",
                    )
                self.repository.save_obligations(project_id, obligations)
                self.repository.save_component_roles(project_id, roles)
            return self._resolve_available_roles(state, intent, options)
        except Exception as error:
            if _must_propagate(error):
                raise
            self._record_failure(state, state.phase, None, error, recoverable=False)
            state.phase = GenerationPhase.FAILED
            state.status = GenerationStatus.FAILED
            self.repository.save_state(state)
            return self._result(state, None)

    def run(
        self,
        project_id: str,
        intent_id: str,
        *,
        run_id: str | None = None,
        options: GenerationOptions | None = None,
    ) -> HardwareIR:
        """Run intent-first generation synchronously and require usable output."""

        result = self.start(
            run_id=run_id or self.id_factory(),
            project_id=project_id,
            intent_id=intent_id,
            options=options,
        )
        if result.project is None:
            message = (
                result.failures[-1].message
                if result.failures
                else "No usable project state was created."
            )
            raise RuntimeError(message)
        return result.project

    def generate(
        self,
        project_id: str,
        intent_id: str,
        *,
        options: GenerationOptions | None = None,
    ) -> HardwareIR:
        return self.run(project_id, intent_id, options=options)

    def create_machine_intent(self, *, project_id: str, prompt: str) -> MachineIntent:
        """Feature boundary: turn the raw prompt into persisted canonical intent."""

        self.repository.initialize_project(project_id)
        draft = self.intent_service.generate(prompt=prompt)
        intent = self.intent_service.create_intent(
            project_id=project_id,
            source_prompt=prompt,
            draft=draft,
        )
        self.repository.save_intent(intent)
        return intent

    def resume(
        self,
        project_id: str,
        *,
        retry_deferred_roles: bool = True,
        retry_blocked_roles: bool = False,
        options: GenerationOptions | None = None,
    ) -> ProjectGenerationResult:
        """Resume eligible roles using the intent referenced by durable state."""

        state = self.repository.get_state(project_id)
        intent = (
            self.repository.get_intent_by_id(state.intent_id)
            if state is not None and state.intent_id
            else None
        )
        if state is None or intent is None:
            raise ValueError(
                f"Project '{project_id}' has no resumable design-generation state."
            )
        obligations = self.repository.get_obligations(project_id)
        if not obligations:
            obligations = self.expand_obligations(intent, state)
        subsystems = self.repository.get_subsystems(project_id)
        if not subsystems:
            subsystems = self.plan_subsystems(intent, obligations, state)
        roles = self.repository.get_component_roles(project_id)
        if not roles:
            roles = self.plan_component_roles(intent, obligations, subsystems, state)
        reset_statuses = {ObligationStatus.DEFERRED} if retry_deferred_roles else set()
        if retry_blocked_roles:
            reset_statuses.add(ObligationStatus.BLOCKED)
        reset_obligation_ids: set[str] = set()
        for role in roles:
            if (
                role.status == ObligationStatus.IN_PROGRESS
                or role.status in reset_statuses
            ):
                role.status = ObligationStatus.UNRESOLVED
                role.failure_reason = None
                state.attempt_counts[role.role_id] = 0
                reset_obligation_ids.update(role.obligation_ids)
        for obligation in obligations:
            if obligation.obligation_id in reset_obligation_ids and (
                obligation.status == ObligationStatus.IN_PROGRESS
                or obligation.status in reset_statuses
            ):
                obligation.status = ObligationStatus.UNRESOLVED
                obligation.failure_reason = None
        state.status = GenerationStatus.RUNNING
        state.phase = GenerationPhase.SELECT_COMPONENT
        self.repository.save_obligations(project_id, obligations)
        self.repository.save_component_roles(project_id, roles)
        self.repository.save_state(state)
        return self._resolve_available_roles(
            state, intent, options or GenerationOptions()
        )

    def expand_obligations(
        self,
        intent: MachineIntent,
        state: DesignGenerationState,
    ) -> list[DesignObligation]:
        """Derive and persist obligations from canonical machine intent."""

        self._transition(state, GenerationPhase.EXPAND_OBLIGATIONS)
        obligations = self.planning_service.expand_obligations(intent)
        self.repository.save_obligations(intent.project_id, obligations)
        return obligations

    def plan_subsystems(
        self,
        intent: MachineIntent,
        obligations: list[DesignObligation],
        state: DesignGenerationState,
    ) -> list[SubsystemPlan]:
        self._transition(state, GenerationPhase.PLAN_ARCHITECTURE)
        subsystems = self.planning_service.plan_subsystems(intent, obligations)
        self.repository.save_subsystems(intent.project_id, subsystems)
        return subsystems

    def plan_component_roles(
        self,
        intent: MachineIntent,
        obligations: list[DesignObligation],
        subsystems: list[SubsystemPlan],
        state: DesignGenerationState,
    ) -> list[ComponentRole]:
        """Derive and persist abstract roles without selecting physical parts."""

        self._transition(state, GenerationPhase.PLAN_ARCHITECTURE)
        roles = self.planning_service.plan_component_roles(
            intent, obligations, subsystems
        )
        state.pending_role_ids = [item.role_id for item in roles]
        self.repository.save_component_roles(intent.project_id, roles)
        self.repository.save_state(state)
        return roles

    def audit_bom(
        self,
        intent: MachineIntent,
        state: DesignGenerationState,
        options: GenerationOptions,
    ) -> BomGapReview:
        """Review selected parts and persist any missing procurement roles."""

        self._transition(state, GenerationPhase.AUDIT_BOM)
        project_id = intent.project_id
        obligations = self.repository.get_obligations(project_id)
        roles = self.repository.get_component_roles(project_id)
        review = self.planning_service.audit_component_roles(
            intent,
            obligations,
            self.repository.get_subsystems(project_id),
            roles,
            self.repository.get_definitions(project_id),
        )
        state.bom_audit_pass_count += 1
        state.bom_audit_complete = review.is_complete and not review.missing_roles
        if review.missing_roles:
            available_slots = max(0, options.max_component_roles - len(roles))
            accepted = review.missing_roles[:available_slots]
            deferred = review.missing_roles[available_slots:]
            for role in deferred:
                CompletenessLedger.defer_role(
                    role,
                    obligations,
                    f"Generation role limit of {options.max_component_roles} was reached during BOM review.",
                )
            roles.extend([*accepted, *deferred])
            state.pending_role_ids.extend(item.role_id for item in accepted)
            self.repository.save_obligations(project_id, obligations)
            self.repository.save_component_roles(project_id, roles)
        self.repository.save_state(state)
        return review

    def select_next_role(
        self, project_id: str, state: DesignGenerationState
    ) -> ComponentRole | None:
        return select_next_role(
            self.repository.get_component_roles(project_id),
            self.repository.get_obligations(project_id),
            state.attempt_counts,
        )

    def select_part(
        self,
        intent: MachineIntent,
        role: ComponentRole,
        state: DesignGenerationState,
    ) -> PartSelectionDraft:
        """Select and persist one role-bound candidate part."""

        self._transition(state, GenerationPhase.SELECT_COMPONENT, role.role_id)
        prior = self.repository.get_selection(intent.project_id, role.role_id)
        if prior is not None:
            return prior
        selected_dependencies: list[PartDefinition] = []
        for dependency_role_id in role.depends_on_role_ids:
            dependency_selection = self.repository.get_selection(
                intent.project_id, dependency_role_id
            )
            if dependency_selection is None:
                continue
            definition = self.repository.find_definition(
                intent.project_id,
                dependency_selection.manufacturer,
                dependency_selection.manufacturer_part_number,
            )
            if definition is not None:
                selected_dependencies.append(definition)
        selection = self.selection_service.select_part(
            role,
            intent.constraints,
            selected_dependencies,
        )
        self.repository.save_selection(intent.project_id, role.role_id, selection)
        return selection

    def enrich_component(
        self,
        project_id: str,
        role: ComponentRole,
        selection: PartSelectionDraft,
        state: DesignGenerationState,
    ) -> PartDefinition:
        """Load or enrich one shared canonical part definition."""

        self._transition(state, GenerationPhase.ENRICH_COMPONENT, role.role_id)
        existing = self.repository.find_definition(
            project_id,
            selection.manufacturer,
            selection.manufacturer_part_number,
        )
        return existing or self.enrichment_service.enrich_component(selection)

    def validate_component(
        self,
        definition: PartDefinition,
        role: ComponentRole,
        state: DesignGenerationState,
    ) -> ComponentValidationResult:
        self._transition(state, GenerationPhase.VALIDATE_COMPONENT, role.role_id)
        return self.component_validator.validate_component(definition)

    def commit_component(
        self,
        project_id: str,
        role: ComponentRole,
        selection: PartSelectionDraft,
        definition: PartDefinition,
        state: DesignGenerationState,
    ) -> None:
        """Atomically add instances, BOM data, and capability traceability."""

        self._transition(state, GenerationPhase.COMMIT_COMPONENT, role.role_id)
        if selection.role_id != role.role_id:
            raise ValueError(
                f"Part selection for role '{selection.role_id}' cannot commit role '{role.role_id}'."
            )
        self.repository.save_definition(project_id, definition)
        existing = self.repository.get_instances(project_id)
        quantity = max(role.quantity, selection.quantity)
        prefix = _reference_prefix(definition.category)
        used_refs = {item.ref_des for item in existing}
        instances: list[ComponentInstance] = []
        next_index = 1
        while len(instances) < quantity:
            ref_des = f"{prefix}{next_index}"
            next_index += 1
            if ref_des in used_refs:
                continue
            used_refs.add(ref_des)
            instances.append(
                ComponentInstance(
                    ref_des=ref_des,
                    part_definition_id=definition.part_definition_id,
                    rationale=selection.selection_reason,
                    configuration={"role_id": role.role_id},
                )
            )
        self.repository.save_instances(project_id, instances)
        all_instances = self.repository.get_instances(project_id)
        all_definitions = self.repository.get_definitions(project_id)
        line = next(
            item
            for item in derive_bom_line_items(all_definitions, all_instances)
            if item.part_definition_id == definition.part_definition_id
        )
        self.repository.save_bom_line(project_id, line)

        obligations = self.repository.get_obligations(project_id)
        roles = self.repository.get_component_roles(project_id)
        persisted_role = next(item for item in roles if item.role_id == role.role_id)
        CompletenessLedger.resolve_role(
            persisted_role,
            obligations,
            definition_id=definition.part_definition_id,
            instance_ids=[item.ref_des for item in instances],
        )
        self.repository.save_obligations(project_id, obligations)
        self.repository.save_component_roles(project_id, roles)
        trace_role_ids = list(
            dict.fromkeys(
                str(item.configuration.get("role_id"))
                for item in all_instances
                if item.part_definition_id == definition.part_definition_id
                and item.configuration.get("role_id")
            )
        )
        roles_by_id = {item.role_id: item for item in roles}
        obligation_ids = list(
            dict.fromkeys(
                obligation_id
                for trace_role_id in trace_role_ids
                for traced_role in [roles_by_id.get(trace_role_id)]
                if traced_role is not None
                for obligation_id in traced_role.obligation_ids
            )
        )
        obligations_by_id = {item.obligation_id: item for item in obligations}
        self.repository.save_bom_trace(
            project_id,
            BomLineTrace(
                line_id=line.line_id,
                role_ids=trace_role_ids,
                obligation_ids=obligation_ids,
                required_capabilities=list(
                    dict.fromkeys(
                        obligations_by_id[item].capability_name
                        for item in obligation_ids
                        if item in obligations_by_id
                    )
                ),
            ),
        )
        self.assess_completeness(project_id, state)

    def assess_completeness(
        self, project_id: str, state: DesignGenerationState
    ) -> None:
        """Persist trace-aware capability and obligation coverage."""

        self._transition(state, GenerationPhase.ASSESS_COMPLETENESS)
        intent = self.repository.get_intent(project_id)
        state.completeness = CompletenessLedger.assess(
            self.repository.get_obligations(project_id),
            self.repository.get_bom_lines(project_id),
            self.repository.get_instances(project_id),
            self.repository.get_bom_traces(project_id),
            intent.required_capabilities if intent is not None else [],
        )
        roles = self.repository.get_component_roles(project_id)
        state.pending_role_ids = [
            item.role_id for item in roles if item.status == ObligationStatus.UNRESOLVED
        ]
        state.completed_role_ids = [
            item.role_id for item in roles if item.status == ObligationStatus.RESOLVED
        ]
        state.deferred_role_ids = [
            item.role_id for item in roles if item.status == ObligationStatus.DEFERRED
        ]
        state.blocked_role_ids = [
            item.role_id for item in roles if item.status == ObligationStatus.BLOCKED
        ]
        state.current_role_id = None
        self.repository.save_state(state)

    def compile_hardware_ir(
        self, project_id: str, state: DesignGenerationState
    ) -> HardwareIR:
        """Compile the currently persisted intent-first project artifacts."""

        self._transition(state, GenerationPhase.COMPILE_PROJECT)
        return self.compiler.compile_hardware_ir(project_id)

    def _resolve_available_roles(
        self,
        state: DesignGenerationState,
        intent: MachineIntent,
        options: GenerationOptions,
    ) -> ProjectGenerationResult:
        project_id = intent.project_id
        while True:
            while role := self.select_next_role(project_id, state):
                roles = self.repository.get_component_roles(project_id)
                persisted_role = next(
                    item for item in roles if item.role_id == role.role_id
                )
                persisted_role.status = ObligationStatus.IN_PROGRESS
                self.repository.save_component_roles(project_id, roles)
                state.attempt_counts[role.role_id] = (
                    state.attempt_counts.get(role.role_id, 0) + 1
                )
                self.repository.save_state(state)
                try:
                    selection = self.select_part(intent, persisted_role, state)
                    definition = self.enrich_component(
                        project_id, persisted_role, selection, state
                    )
                    validation = self.validate_component(
                        definition, persisted_role, state
                    )
                    if not validation.is_valid:
                        raise ValueError(
                            "; ".join(validation.errors)
                            or "Component definition validation failed."
                        )
                    self.commit_component(
                        project_id, persisted_role, selection, definition, state
                    )
                except Exception as error:
                    if _must_propagate(error):
                        raise
                    self._handle_role_failure(state, persisted_role, error, options)

            self._block_dependency_deadlocks(project_id)
            self.assess_completeness(project_id, state)
            if (
                state.bom_audit_complete
                or state.bom_audit_pass_count >= options.max_bom_audit_passes
            ):
                break
            try:
                review = self.audit_bom(intent, state, options)
            except Exception as error:
                if _must_propagate(error):
                    raise
                self._record_failure(
                    state, GenerationPhase.AUDIT_BOM, project_id, error
                )
                break
            if not review.missing_roles:
                break

        self.assess_completeness(project_id, state)
        if self.wiring_service is not None and self.repository.get_instances(
            project_id
        ):
            try:
                self._transition(state, GenerationPhase.GENERATE_WIRING)
                fragments = self.wiring_service.generate_wiring(
                    project_id,
                    intent,
                    self.repository.get_definitions(project_id),
                    self.repository.get_instances(project_id),
                )
                self.repository.save_fragments(project_id, fragments)
            except Exception as error:
                if _must_propagate(error):
                    raise
                self._record_failure(
                    state, GenerationPhase.GENERATE_WIRING, project_id, error
                )

        project: HardwareIR | None = None
        try:
            project = self.compile_hardware_ir(project_id, state)
            if self.project_validator is not None:
                self._transition(state, GenerationPhase.VALIDATE_PROJECT)
                project = self.project_validator.validate_project(project)
        except Exception as error:
            if _must_propagate(error):
                raise
            self._record_failure(
                state,
                GenerationPhase.COMPILE_PROJECT,
                project_id,
                error,
                recoverable=False,
            )

        unresolved = (
            state.completeness.unresolved_obligation_count
            + state.completeness.deferred_obligation_count
            + state.completeness.blocked_obligation_count
            + len(state.pending_role_ids)
            + len(state.deferred_role_ids)
            + len(state.blocked_role_ids)
            + len(intent.unresolved_questions)
            + (0 if state.bom_audit_complete else 1)
        )
        wiring_failed = any(
            item.phase == GenerationPhase.GENERATE_WIRING for item in state.failures
        )
        if project is None:
            state.status = GenerationStatus.FAILED
            state.phase = GenerationPhase.FAILED
        elif (
            unresolved
            or wiring_failed
            or not state.completeness.physical_component_count
        ):
            state.status = (
                GenerationStatus.PARTIAL
                if options.allow_partial
                else GenerationStatus.FAILED
            )
            state.phase = (
                GenerationPhase.PARTIAL
                if options.allow_partial
                else GenerationPhase.FAILED
            )
        else:
            state.status = GenerationStatus.COMPLETE
            state.phase = GenerationPhase.COMPLETE
        self.repository.save_state(state)
        return self._result(state, project)

    def _handle_role_failure(
        self,
        state: DesignGenerationState,
        role: ComponentRole,
        error: Exception,
        options: GenerationOptions,
    ) -> None:
        attempt = state.attempt_counts[role.role_id]
        self._record_failure(
            state, state.phase, role.role_id, error, attempt_count=attempt
        )
        roles = self.repository.get_component_roles(state.project_id)
        obligations = self.repository.get_obligations(state.project_id)
        persisted_role = next(item for item in roles if item.role_id == role.role_id)
        if attempt >= options.max_role_attempts:
            CompletenessLedger.defer_role(persisted_role, obligations, str(error))
        else:
            persisted_role.status = ObligationStatus.UNRESOLVED
            persisted_role.failure_reason = str(error)
            if state.phase == GenerationPhase.VALIDATE_COMPONENT:
                # A locally invalid definition should permit a different part
                # candidate on retry. Enrichment failures retain their already
                # selected candidate so only that definition is retried.
                self.repository.delete_selection(state.project_id, role.role_id)
        self.repository.save_component_roles(state.project_id, roles)
        self.repository.save_obligations(state.project_id, obligations)
        self.repository.save_state(state)

    def _block_dependency_deadlocks(self, project_id: str) -> None:
        roles = self.repository.get_component_roles(project_id)
        obligations = self.repository.get_obligations(project_id)
        role_by_id = {item.role_id: item for item in roles}
        changed = False
        for role in roles:
            if role.status != ObligationStatus.UNRESOLVED:
                continue
            failed_dependencies = [
                role_by_id[item]
                for item in role.depends_on_role_ids
                if item in role_by_id
                and role_by_id[item].status
                in {ObligationStatus.DEFERRED, ObligationStatus.BLOCKED}
            ]
            if failed_dependencies:
                reason = "Blocked by unresolved role(s): " + ", ".join(
                    item.name for item in failed_dependencies
                )
                CompletenessLedger.defer_role(role, obligations, reason, blocked=True)
                changed = True
        if changed:
            self.repository.save_component_roles(project_id, roles)
            self.repository.save_obligations(project_id, obligations)

    def _transition(
        self,
        state: DesignGenerationState,
        phase: GenerationPhase,
        current_role_id: str | None = None,
    ) -> None:
        state.phase = phase
        state.current_role_id = current_role_id
        self.repository.save_state(state)

    def _record_failure(
        self,
        state: DesignGenerationState,
        phase: GenerationPhase,
        target_id: str | None,
        error: Exception,
        *,
        attempt_count: int = 1,
        recoverable: bool = True,
    ) -> None:
        state.failures.append(
            GenerationFailure(
                failure_id=self.id_factory(),
                phase=phase,
                target_id=target_id,
                error_code=error.__class__.__name__,
                message=str(error),
                attempt_count=attempt_count,
                recoverable=recoverable,
            )
        )
        self.repository.save_state(state)

    def _result(
        self, state: DesignGenerationState, project: HardwareIR | None
    ) -> ProjectGenerationResult:
        return ProjectGenerationResult(
            run_id=state.run_id,
            project_id=state.project_id,
            status=state.status,
            project=project,
            completeness=GenerationCompleteness.model_validate(
                state.completeness.model_dump()
            ),
            failures=[
                GenerationFailureSummary(
                    phase=item.phase.value,
                    target_id=item.target_id,
                    error_code=item.error_code,
                    message=item.message,
                    recoverable=item.recoverable,
                )
                for item in state.failures
            ],
            bom_traces=self.repository.get_bom_traces(state.project_id),
        )


def _reference_prefix(category: str) -> str:
    normalized = category.casefold()
    if "resistor" in normalized:
        return "R"
    if "capacitor" in normalized:
        return "C"
    if "diode" in normalized or "led" in normalized:
        return "D"
    if "connector" in normalized or "header" in normalized:
        return "J"
    if "sensor" in normalized:
        return "SEN"
    if "switch" in normalized or "button" in normalized:
        return "SW"
    if "mechanical" in normalized or "mount" in normalized or "enclosure" in normalized:
        return "M"
    return "U"


def _must_propagate(error: Exception) -> bool:
    return (
        isinstance(error, DesignCheckpointError)
        or error.__class__.__name__ == "PipelineCancelledError"
    )


__all__ = ["DesignGenerationEngine"]
