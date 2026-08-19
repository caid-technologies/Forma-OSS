from __future__ import annotations

import inspect
import unittest

from pydantic import ValidationError

from forma_core.design_generation import (
    BomGapReview,
    ComponentDefinitionValidator,
    ComponentRole,
    ComponentValidationResult,
    DesignCheckpointError,
    DesignGenerationEngine,
    DesignGenerationState,
    DesignObligation,
    DesignPlanningService,
    GenerationOptions,
    GenerationPhase,
    GenerationStatus,
    InMemoryDesignGenerationRepository,
    MachineIntent,
    MachineIntentDraft,
    ObligationStatus,
    PartSelectionDraft,
    ProjectGenerationService,
    SubsystemPlan,
)
from forma_core.workspaces.projects.models import PartDefinition


def machine_intent(project_id: str) -> MachineIntent:
    return MachineIntent(
        intent_id="intent-1",
        project_id=project_id,
        source_prompt="Build a monitor",
        purpose="Desktop environmental monitor",
        users=["desktop user"],
        operating_environment=["indoors"],
        required_capabilities=["Control", "Sense", "Indicate"],
        inputs=["temperature", "humidity"],
        outputs=["OLED status"],
        constraints=["5V USB power"],
        success_conditions=["readings are visible"],
    )


def obligations() -> list[DesignObligation]:
    return [
        DesignObligation(
            obligation_id=f"obligation-{name.lower()}",
            capability_name=name,
            description=description,
            obligation_type="functional",
        )
        for name, description in [
            ("Control", "Process readings"),
            ("Sense", "Measure temperature"),
            ("Indicate", "Show status"),
        ]
    ]


def subsystems() -> list[SubsystemPlan]:
    return [
        SubsystemPlan(
            subsystem_id="subsystem-monitor",
            name="monitor",
            purpose="Sense, process, and display the environment",
            obligation_ids=[item.obligation_id for item in obligations()],
        )
    ]


def roles() -> list[ComponentRole]:
    return [
        ComponentRole(
            role_id="role-controller",
            subsystem_id="subsystem-monitor",
            subsystem_name="monitor",
            name="Main controller",
            function="Process readings",
            obligation_ids=["obligation-control"],
        ),
        ComponentRole(
            role_id="role-sensor",
            subsystem_id="subsystem-monitor",
            subsystem_name="monitor",
            name="Temperature sensor",
            function="Measure temperature",
            obligation_ids=["obligation-sense"],
        ),
        ComponentRole(
            role_id="role-led",
            subsystem_id="subsystem-monitor",
            subsystem_name="monitor",
            name="Status LED",
            function="Show status",
            obligation_ids=["obligation-indicate"],
        ),
    ]


class FakeIntentService:
    def __init__(self, project_id: str) -> None:
        self.intent = machine_intent(project_id)
        self.generate_calls = 0
        self.create_calls = 0

    def generate(self, *, prompt: str) -> MachineIntentDraft:
        self.generate_calls += 1
        return MachineIntentDraft.model_validate(
            self.intent.model_dump(exclude={"intent_id", "project_id", "source_prompt"})
        )

    def create_intent(
        self, *, project_id: str, source_prompt: str, draft: MachineIntentDraft
    ) -> MachineIntent:
        self.create_calls += 1
        return MachineIntent(
            intent_id=self.intent.intent_id,
            project_id=project_id,
            source_prompt=source_prompt,
            **draft.model_dump(),
        )


class FakePlanningService:
    def __init__(self) -> None:
        self.expand_calls = 0
        self.subsystem_calls = 0
        self.plan_calls = 0
        self.audit_calls = 0

    def expand_obligations(self, intent: MachineIntent) -> list[DesignObligation]:
        self.expand_calls += 1
        return [item.model_copy(deep=True) for item in obligations()]

    def plan_subsystems(
        self,
        intent: MachineIntent,
        design_obligations: list[DesignObligation],
    ) -> list[SubsystemPlan]:
        self.subsystem_calls += 1
        return [item.model_copy(deep=True) for item in subsystems()]

    def plan_component_roles(
        self,
        intent: MachineIntent,
        design_obligations: list[DesignObligation],
        planned_subsystems: list[SubsystemPlan],
    ) -> list[ComponentRole]:
        self.plan_calls += 1
        return [item.model_copy(deep=True) for item in roles()]

    def audit_component_roles(
        self,
        intent,
        design_obligations,
        planned_subsystems,
        component_roles,
        selected_definitions,
    ) -> BomGapReview:
        self.audit_calls += 1
        return BomGapReview(is_complete=True)


class GapFindingPlanningService(FakePlanningService):
    def audit_component_roles(
        self,
        intent,
        design_obligations,
        planned_subsystems,
        component_roles,
        selected_definitions,
    ) -> BomGapReview:
        self.audit_calls += 1
        if self.audit_calls > 1:
            return BomGapReview(is_complete=True)
        return BomGapReview(
            is_complete=False,
            missing_roles=[
                ComponentRole(
                    role_id=f"role-{slug}",
                    subsystem_id="subsystem-monitor",
                    subsystem_name="monitor",
                    name=name,
                    function=function,
                    obligation_ids=["obligation-control"],
                    requirements=[requirement],
                )
                for slug, name, function, requirement in [
                    (
                        "usb-protection",
                        "USB input protection",
                        "Protect the powered electronics from USB transients",
                        "low-capacitance transient suppression",
                    ),
                    (
                        "bulk-capacitor",
                        "Power bulk capacitor",
                        "Stabilize the incoming power rail",
                        "sized for load transients",
                    ),
                    (
                        "decoupling-capacitor",
                        "Controller decoupling capacitor",
                        "Decouple the controller supply locally",
                        "placed at the controller supply pins",
                    ),
                    (
                        "programming-connector",
                        "Programming connector",
                        "Provide firmware programming and debug access",
                        "compatible with the controller interface",
                    ),
                    (
                        "assembly-substrate",
                        "Assembly substrate",
                        "Physically carry and interconnect the electronics",
                        "compact prototyping or fabricated PCB substrate",
                    ),
                ]
            ],
        )


class FakeSelectionService:
    def __init__(self, same_part: bool = False) -> None:
        self.calls: list[str] = []
        self.constraints_seen: list[list[str]] = []
        self.same_part = same_part

    def select_part(
        self, role, intent_constraints, selected_definitions
    ) -> PartSelectionDraft:
        self.calls.append(role.role_id)
        self.constraints_seen.append(list(intent_constraints))
        part = "SHARED-1" if self.same_part else role.role_id.upper()
        return PartSelectionDraft(
            role_id=role.role_id,
            manufacturer="Forma Test",
            manufacturer_part_number=part,
            name=role.name,
            category="Module",
            description=role.function,
            selection_reason=f"Fulfills {role.name}",
        )


class ReplacementSelectionService(FakeSelectionService):
    def select_part(
        self, role, intent_constraints, selected_definitions
    ) -> PartSelectionDraft:
        self.calls.append(role.role_id)
        self.constraints_seen.append(list(intent_constraints))
        attempt = self.calls.count(role.role_id)
        suffix = "BAD" if role.role_id == "role-sensor" and attempt == 1 else "GOOD"
        return PartSelectionDraft(
            role_id=role.role_id,
            manufacturer="Forma Test",
            manufacturer_part_number=f"{role.role_id.upper()}-{suffix}",
            name=role.name,
            category="Module",
            description=role.function,
            selection_reason=f"Fulfills {role.name}",
        )


class RejectBadPartValidator(ComponentDefinitionValidator):
    def validate_component(
        self, definition: PartDefinition
    ) -> ComponentValidationResult:
        if definition.part_number.endswith("-BAD"):
            return ComponentValidationResult(
                is_valid=False, errors=["candidate is incompatible"]
            )
        return super().validate_component(definition)


class FakeEnrichmentService:
    def __init__(self, failing_roles: set[str] | None = None) -> None:
        self.failing_roles = failing_roles or set()
        self.calls: list[str] = []

    def enrich_component(self, selection: PartSelectionDraft) -> PartDefinition:
        self.calls.append(selection.role_id)
        if selection.role_id in self.failing_roles:
            raise ValueError(f"Could not enrich {selection.role_id}")
        return PartDefinition(
            part_definition_id=f"definition-{selection.manufacturer_part_number.lower()}",
            manufacturer=selection.manufacturer,
            part_number=selection.manufacturer_part_number,
            name=selection.name,
            category=selection.category,
            description=selection.description,
        )


class RecordingRepository(InMemoryDesignGenerationRepository):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[str] = []
        self.committed_lines: list[str] = []

    def save_intent(self, intent) -> None:
        super().save_intent(intent)
        self.events.append("intent")

    def save_state(self, state) -> None:
        super().save_state(state)
        self.events.append("state")

    def save_bom_line(self, project_id, line) -> None:
        super().save_bom_line(project_id, line)
        self.committed_lines.append(line.line_id)


class FailingWiringService:
    def generate_wiring(self, project_id, intent, definitions, instances):
        raise TimeoutError("wiring timed out")


class IntentFirstGenerationTests(unittest.TestCase):
    project_id = "project-1"

    def engine(
        self,
        *,
        repository=None,
        planning=None,
        selection=None,
        enrichment=None,
        wiring=None,
        validator=None,
    ):
        intent = FakeIntentService(self.project_id)
        planning = planning or FakePlanningService()
        engine = DesignGenerationEngine(
            repository=repository or InMemoryDesignGenerationRepository(),
            intent_service=intent,
            planning_service=planning,
            selection_service=selection or FakeSelectionService(),
            enrichment_service=enrichment or FakeEnrichmentService(),
            component_validator=validator or ComponentDefinitionValidator(),
            wiring_service=wiring,
        )
        return engine, intent, planning

    def start(self, engine, *, options=None):
        intent = engine.create_machine_intent(
            project_id=self.project_id, prompt="Build a monitor"
        )
        return engine.start(
            run_id="run-1",
            project_id=self.project_id,
            intent_id=intent.intent_id,
            options=options,
        )

    def test_machine_intent_draft_accepts_exact_environmental_monitor_payload(
        self,
    ) -> None:
        payload = {
            "purpose": "Compact desktop environmental monitor",
            "users": ["office worker"],
            "operating_environment": ["indoor desktop"],
            "required_capabilities": [
                "measure temperature",
                "measure humidity",
                "display readings",
            ],
            "inputs": ["ambient temperature", "ambient humidity"],
            "outputs": ["OLED display"],
            "constraints": ["USB-C power", "ESP32"],
            "success_conditions": ["current readings remain visible"],
            "unresolved_questions": ["target enclosure dimensions"],
        }
        self.assertEqual(
            payload, MachineIntentDraft.model_validate(payload).model_dump()
        )
        with self.assertRaises(ValidationError):
            MachineIntentDraft.model_validate({**payload, "components": ["ESP32"]})

    def test_engine_requires_persisted_intent_id_and_has_no_prompt_parameter(
        self,
    ) -> None:
        self.assertNotIn(
            "prompt", inspect.signature(DesignGenerationEngine.start).parameters
        )
        engine, _, _ = self.engine()
        result = self.start(engine)
        self.assertEqual(
            "intent-1", engine.repository.get_state(self.project_id).intent_id
        )
        self.assertEqual(GenerationStatus.COMPLETE, result.status)

    def test_obligation_expansion_covers_every_required_capability(self) -> None:
        class EmptyObligationGenerator:
            def generate(self, _prompt, schema):
                return schema.model_validate({"obligations": []})

        planned = DesignPlanningService(
            EmptyObligationGenerator(), id_factory=iter(["o1", "o2", "o3"]).__next__
        ).expand_obligations(machine_intent(self.project_id))

        self.assertEqual(
            ["Control", "Sense", "Indicate"],
            [item.capability_name for item in planned],
        )

    def test_real_bom_review_uses_selected_parts_and_returns_traced_gap_roles(
        self,
    ) -> None:
        class ReviewGenerator:
            def __init__(self) -> None:
                self.prompt = ""

            def generate(self, prompt, schema):
                self.prompt = prompt
                return schema.model_validate(
                    {
                        "is_complete": False,
                        "missing_roles": [
                            {
                                "subsystem_name": "monitor",
                                "name": "I2C pull-up resistors",
                                "function": "Bias the shared I2C bus",
                                "obligation_descriptions": ["Measure temperature"],
                                "requirements": ["two correctly sized resistors"],
                                "quantity": 2,
                                "depends_on_role_names": ["Main controller"],
                            }
                        ],
                    }
                )

        generator = ReviewGenerator()
        review = DesignPlanningService(
            generator, id_factory=lambda: "role-pullups"
        ).audit_component_roles(
            machine_intent(self.project_id),
            obligations(),
            subsystems(),
            roles(),
            [
                PartDefinition(
                    part_definition_id="definition-controller",
                    manufacturer="Espressif",
                    part_number="ESP32-WROOM-32E",
                    name="ESP32 module",
                    category="Module",
                    description="Wi-Fi and Bluetooth MCU module",
                )
            ],
        )

        self.assertFalse(review.is_complete)
        self.assertEqual(["obligation-sense"], review.missing_roles[0].obligation_ids)
        self.assertEqual(
            ["role-controller"], review.missing_roles[0].depends_on_role_ids
        )
        self.assertIn("ESP32-WROOM-32E", generator.prompt)
        self.assertIn("decoupling", generator.prompt)
        self.assertNotIn("Build a monitor", generator.prompt)

    def test_service_persists_machine_intent_before_starting_state_engine(self) -> None:
        repository = RecordingRepository()
        engine, _, _ = self.engine(repository=repository)
        service = ProjectGenerationService(
            lambda: engine, project_id_factory=lambda: self.project_id
        )
        try:
            run = service.start(prompt="Build a monitor")
            result = run.wait(timeout=2)
        finally:
            service.shutdown()
        self.assertEqual("intent", repository.events[0])
        self.assertEqual("intent-1", run.intent_id)
        self.assertEqual(GenerationStatus.COMPLETE, result.status)

    def test_downstream_services_receive_intent_derived_context_not_raw_prompt(
        self,
    ) -> None:
        selection = FakeSelectionService()
        engine, _, _ = self.engine(selection=selection)
        self.start(engine)
        self.assertEqual([["5V USB power"]] * 3, selection.constraints_seen)

    def test_local_enrichment_failure_preserves_prior_and_later_bom_lines(self) -> None:
        repository = RecordingRepository()
        selection = FakeSelectionService()
        enrichment = FakeEnrichmentService({"role-sensor"})
        engine, _, _ = self.engine(
            repository=repository, selection=selection, enrichment=enrichment
        )
        result = self.start(engine, options=GenerationOptions(max_role_attempts=2))

        self.assertEqual(GenerationStatus.PARTIAL, result.status)
        self.assertEqual(2, result.completeness.valid_bom_line_count)
        self.assertEqual(2, result.completeness.physical_component_count)
        self.assertEqual(2, len(result.project.bom))
        self.assertEqual(
            ["role-controller", "role-sensor", "role-led"], selection.calls
        )
        self.assertEqual(2, enrichment.calls.count("role-sensor"))
        self.assertEqual(
            ObligationStatus.DEFERRED,
            repository.get_component_roles(self.project_id)[1].status,
        )
        self.assertGreaterEqual(len(repository.committed_lines), 2)

    def test_repeated_parts_reuse_definition_and_aggregate_traceability(self) -> None:
        repository = InMemoryDesignGenerationRepository()
        enrichment = FakeEnrichmentService()
        engine, _, _ = self.engine(
            repository=repository,
            selection=FakeSelectionService(same_part=True),
            enrichment=enrichment,
        )
        result = self.start(engine)

        self.assertEqual(GenerationStatus.COMPLETE, result.status)
        self.assertEqual(1, len(result.project.part_definitions))
        self.assertEqual(3, len(result.project.components))
        self.assertEqual(3, result.project.bom[0].quantity)
        self.assertEqual(1, len(enrichment.calls))
        self.assertEqual(1, len(result.bom_traces))
        self.assertEqual(
            {"Control", "Sense", "Indicate"},
            set(result.bom_traces[0].required_capabilities),
        )
        self.assertEqual(3, len(result.bom_traces[0].role_ids))

    def test_bom_gap_review_adds_and_resolves_missing_support_roles(self) -> None:
        planning = GapFindingPlanningService()
        engine, _, _ = self.engine(planning=planning)

        result = self.start(engine)

        self.assertEqual(GenerationStatus.COMPLETE, result.status)
        self.assertEqual(2, planning.audit_calls)
        self.assertGreater(len(result.project.bom), 7)
        self.assertTrue(
            any(item.name == "USB input protection" for item in result.project.bom)
        )
        self.assertTrue(engine.repository.get_state(self.project_id).bom_audit_complete)

    def test_invalid_candidate_is_replaced_without_restarting_other_roles(self) -> None:
        selection = ReplacementSelectionService()
        engine, intent, planning = self.engine(
            selection=selection, validator=RejectBadPartValidator()
        )
        result = self.start(engine, options=GenerationOptions(max_role_attempts=2))

        self.assertEqual(GenerationStatus.COMPLETE, result.status)
        self.assertEqual(2, selection.calls.count("role-sensor"))
        self.assertEqual(1, intent.generate_calls)
        self.assertEqual(1, planning.plan_calls)
        self.assertTrue(
            any(item.error_code == "ValueError" for item in result.failures)
        )

    def test_wiring_failure_returns_partial_project_with_complete_bom(self) -> None:
        engine, _, _ = self.engine(wiring=FailingWiringService())
        result = self.start(engine)
        self.assertEqual(GenerationStatus.PARTIAL, result.status)
        self.assertEqual(3, len(result.project.bom))
        self.assertTrue(
            any(item.phase == "generate_wiring" for item in result.failures)
        )

    def test_unresolved_intent_questions_produce_a_partial_result(self) -> None:
        engine, intent_service, _ = self.engine()
        intent_service.intent = intent_service.intent.model_copy(
            update={"unresolved_questions": ["What enclosure dimensions are required?"]}
        )

        result = self.start(engine)

        self.assertEqual(GenerationStatus.PARTIAL, result.status)
        self.assertEqual(
            ["What enclosure dimensions are required?"],
            engine.repository.get_intent(self.project_id).unresolved_questions,
        )

    def test_public_generation_run_supports_polling_wait_and_project_access(
        self,
    ) -> None:
        engine, _, _ = self.engine()
        service = ProjectGenerationService(
            lambda: engine, project_id_factory=lambda: self.project_id
        )
        try:
            run = service.start(prompt="Build a monitor")
            self.assertEqual(self.project_id, run.refresh().project_id)
            result = run.wait(timeout=2)
            self.assertTrue(run.is_terminal)
            self.assertEqual(GenerationStatus.COMPLETE, result.status)
            self.assertEqual(3, len(run.get_project().components))
        finally:
            service.shutdown()

    def test_resume_reuses_intent_obligations_selections_and_components(self) -> None:
        repository = InMemoryDesignGenerationRepository()
        selection = FakeSelectionService()
        enrichment = FakeEnrichmentService({"role-sensor"})
        engine, intent, planning = self.engine(
            repository=repository,
            selection=selection,
            enrichment=enrichment,
        )
        first = self.start(engine, options=GenerationOptions(max_role_attempts=1))
        self.assertEqual(GenerationStatus.PARTIAL, first.status)
        enrichment.failing_roles.clear()
        resumed = engine.resume(self.project_id, retry_deferred_roles=True)

        self.assertEqual(GenerationStatus.COMPLETE, resumed.status)
        self.assertEqual(1, intent.generate_calls)
        self.assertEqual(1, intent.create_calls)
        self.assertEqual(1, planning.expand_calls)
        self.assertEqual(1, planning.subsystem_calls)
        self.assertEqual(1, planning.plan_calls)
        self.assertEqual(1, selection.calls.count("role-sensor"))
        self.assertEqual(3, len(resumed.project.components))

    def test_resume_from_early_checkpoint_derives_state_from_existing_intent(
        self,
    ) -> None:
        engine, intent_service, planning = self.engine()
        intent = engine.create_machine_intent(
            project_id=self.project_id, prompt="Build a monitor"
        )
        engine.repository.save_state(
            DesignGenerationState(
                run_id="run-early",
                project_id=self.project_id,
                intent_id=intent.intent_id,
                phase=GenerationPhase.EXPAND_OBLIGATIONS,
                status=GenerationStatus.RUNNING,
            )
        )

        result = engine.resume(self.project_id)

        self.assertEqual(GenerationStatus.COMPLETE, result.status)
        self.assertEqual(1, intent_service.generate_calls)
        self.assertEqual(1, planning.expand_calls)
        self.assertEqual(1, planning.subsystem_calls)
        self.assertEqual(1, planning.plan_calls)

    def test_durable_checkpoint_restores_partial_bom_before_resume(self) -> None:
        checkpoints: list[dict[str, object]] = []
        repository = InMemoryDesignGenerationRepository(checkpoint=checkpoints.append)
        engine, _, _ = self.engine(
            repository=repository,
            enrichment=FakeEnrichmentService({"role-sensor"}),
        )
        partial = self.start(engine, options=GenerationOptions(max_role_attempts=1))
        self.assertEqual(GenerationStatus.PARTIAL, partial.status)

        restored_repository = InMemoryDesignGenerationRepository()
        restored_repository.restore(
            self.project_id, checkpoints[-1]["record"]["output"]
        )
        restored_engine, intent, planning = self.engine(repository=restored_repository)
        resumed = restored_engine.resume(self.project_id)

        self.assertEqual(GenerationStatus.COMPLETE, resumed.status)
        self.assertEqual(0, intent.generate_calls)
        self.assertEqual(0, planning.expand_calls)
        self.assertEqual(3, len(resumed.project.components))

    def test_checkpoint_failure_is_fatal_at_intent_persistence_boundary(self) -> None:
        def fail_checkpoint(_snapshot) -> None:
            raise ConnectionError("checkpoint store unavailable")

        engine, _, _ = self.engine(
            repository=InMemoryDesignGenerationRepository(checkpoint=fail_checkpoint)
        )
        with self.assertRaises(DesignCheckpointError):
            engine.create_machine_intent(
                project_id=self.project_id, prompt="Build a monitor"
            )


if __name__ == "__main__":
    unittest.main()
