from __future__ import annotations

import unittest
from itertools import count

from pydantic import BaseModel

from forma_core import FormaClient
from forma_core.design_generation.circuit_document.benchmark import (
    ENVIRONMENTAL_MONITOR_DOCUMENT,
    environmental_monitor_benchmark_report,
)
from forma_core.design_generation.circuit_document.compiler import (
    CircuitDocumentCompiler,
)
from forma_core.design_generation.circuit_document.grammar import (
    parse_document,
    serialize_document,
)
from forma_core.design_generation.circuit_document.models import CircuitDocument
from forma_core.design_generation.circuit_document.patches import CircuitPatchService
from forma_core.design_generation.circuit_document.projections import (
    CircuitProjectionService,
)
from forma_core.design_generation.circuit_document.prompts import (
    build_initial_document_prompt,
    build_targeted_patch_prompt,
)
from forma_core.design_generation.circuit_document.repository import (
    InMemoryCircuitDocumentRepository,
)
from forma_core.design_generation.circuit_document.service import (
    CircuitDocumentGenerationService,
)
from forma_core.design_generation.circuit_document.validation import (
    CircuitDocumentValidationError,
)
from forma_core.design_generation.components.enrichment import (
    ComponentEnrichmentService,
    PartEnrichmentDraft,
)
from forma_core.design_generation.components.selection import PartSelectionDraft
from forma_core.design_generation.components.validation import (
    ComponentDefinitionValidator,
)
from forma_core.design_generation.intent.models import MachineIntent, MachineIntentDraft
from forma_core.design_generation.intent.service import IntentService
from forma_core.design_generation.repository import InMemoryDesignGenerationRepository
from forma_core.design_generation.state_machine.models import (
    GenerationCompleteness,
    GenerationOptions,
    GenerationStatus,
    ProjectGenerationResult,
)
from forma_core.workspaces.projects.models import HardwareIR, PartDefinition

BASE_TEXT = """MACHINE test-machine
GOAL sense a value
CONSTRAINT power.logic | 3V3
BLOCK sensing | digital sensor
ROLE sensing.sensor | required | selected | SENSOR-1
ROLE power.decoupling | preferred | selected | 100nF
PART C1 | role=power.decoupling | part=CAP-100N | qty=1
PART U1 | role=sensing.sensor | part=SENSOR-1 | qty=1
NET DATA | U1.DATA C1.1"""
BASE_DOCUMENT = CircuitDocument(text=BASE_TEXT)


def intent() -> MachineIntent:
    return MachineIntent(
        intent_id="intent-1",
        project_id="project-1",
        source_prompt="ORIGINAL_PROMPT_MUST_NOT_REPEAT",
        purpose="sense a value",
        required_capabilities=["sense"],
        constraints=["3.3V logic"],
    )


def definition(part_number: str, definition_id: str) -> PartDefinition:
    return PartDefinition(
        part_definition_id=definition_id,
        part_number=part_number,
        name=part_number,
        category="Component",
    )


class ForbiddenGenerator:
    def generate(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
        raise AssertionError(f"Unexpected generation for {schema.__name__}: {prompt}")


class SelectiveEnrichment:
    def enrich_component(self, selection: PartSelectionDraft) -> PartDefinition:
        part_number = selection.manufacturer_part_number
        if part_number == "BAD-PART":
            raise RuntimeError("targeted enrichment failed")
        return definition(part_number, f"def-{part_number.casefold()}")


class FlowGenerator:
    def __init__(self, *, fail_patches: bool = False) -> None:
        self.fail_patches = fail_patches

    def generate(self, _prompt: str, schema: type[BaseModel]) -> BaseModel:
        if schema is MachineIntentDraft:
            return MachineIntentDraft(
                purpose="sense a value",
                required_capabilities=["sense"],
                constraints=["3.3V logic"],
            )
        if schema is CircuitDocument:
            text = BASE_TEXT
            if self.fail_patches:
                text = text.replace(
                    "ROLE sensing.sensor | required | selected | SENSOR-1",
                    "ROLE sensing.sensor | required | unresolved | exact sensor needed",
                )
            return CircuitDocument(text=text)
        if schema is PartEnrichmentDraft:
            return PartEnrichmentDraft()
        raise RuntimeError("focused patch provider failure")


class CircuitDocumentTests(unittest.TestCase):
    def test_01_valid_document_parsing(self) -> None:
        parsed = parse_document(BASE_DOCUMENT)
        self.assertEqual(9, len(parsed.records))

    def test_02_parse_serialize_round_trip(self) -> None:
        parsed = parse_document(BASE_DOCUMENT)
        serialized = serialize_document(parsed)
        reparsed = parse_document(serialized)
        self.assertEqual(serialized, serialize_document(reparsed))

    def test_03_duplicate_record_rejection(self) -> None:
        with self.assertRaisesRegex(CircuitDocumentValidationError, "Duplicate ROLE"):
            parse_document(
                CircuitDocument(
                    text=BASE_TEXT
                    + "\nROLE sensing.sensor | required | selected | OTHER"
                )
            )

    def test_04_invalid_role_status_rejection(self) -> None:
        with self.assertRaisesRegex(CircuitDocumentValidationError, "Invalid ROLE"):
            parse_document(
                CircuitDocument(
                    text=BASE_TEXT.replace(
                        "required | selected", "required | fabricated", 1
                    )
                )
            )

    def test_05_invalid_quantity_rejection(self) -> None:
        with self.assertRaisesRegex(
            CircuitDocumentValidationError, "Invalid PART fields"
        ):
            parse_document(CircuitDocument(text=BASE_TEXT.replace("qty=1", "qty=0", 1)))

    def test_06_unknown_role_reference_rejection(self) -> None:
        with self.assertRaisesRegex(CircuitDocumentValidationError, "unknown role"):
            parse_document(
                CircuitDocument(
                    text=BASE_TEXT.replace("role=power.decoupling", "role=missing.role")
                )
            )

    def test_07_unknown_part_reference_in_net_rejection(self) -> None:
        with self.assertRaisesRegex(
            CircuitDocumentValidationError, "unknown local part"
        ):
            parse_document(
                CircuitDocument(text=BASE_TEXT.replace("U1.DATA", "U9.DATA"))
            )

    def test_08_successful_atomic_patch(self) -> None:
        result = CircuitPatchService().validate_and_apply(
            BASE_DOCUMENT,
            "ADD OPEN verify.sensor | verify selected sensor\n"
            "REPLACE ROLE sensing.sensor | ROLE sensing.sensor | required | selected | SENSOR-2",
        )
        self.assertIn("OPEN verify.sensor", result.text)
        self.assertIn("selected | SENSOR-2", result.text)

    def test_09_complete_patch_rollback(self) -> None:
        repository = InMemoryCircuitDocumentRepository()
        repository.save_document("p", BASE_DOCUMENT)
        with self.assertRaises(CircuitDocumentValidationError):
            CircuitPatchService().validate_and_apply(
                BASE_DOCUMENT,
                "ADD OPEN valid.issue | temporary\nREMOVE PART MISSING",
            )
        self.assertEqual([BASE_DOCUMENT], repository.get_revisions("p"))

    def test_10_replace_preserves_unrelated_lines(self) -> None:
        result = CircuitPatchService().validate_and_apply(
            BASE_DOCUMENT,
            "REPLACE ROLE sensing.sensor | ROLE sensing.sensor | required | selected | SENSOR-2",
        )
        for line in BASE_TEXT.splitlines():
            if not line.startswith("ROLE sensing.sensor"):
                self.assertIn(line, result.text.splitlines())

    def test_11_resolve_open_item(self) -> None:
        document = CircuitDocument(text=BASE_TEXT + "\nOPEN verify.sensor | verify it")
        result = CircuitPatchService().validate_and_apply(
            document, "RESOLVE verify.sensor"
        )
        self.assertNotIn("OPEN verify.sensor", result.text)

    def test_12_missing_open_item_rejection(self) -> None:
        with self.assertRaisesRegex(CircuitDocumentValidationError, "does not exist"):
            CircuitPatchService().validate_and_apply(BASE_DOCUMENT, "RESOLVE missing")

    def test_13_bom_projection_and_quantity(self) -> None:
        projection = CircuitProjectionService().build(ENVIRONMENTAL_MONITOR_DOCUMENT)
        report = environmental_monitor_benchmark_report()
        self.assertEqual(24, report.physical_quantity)
        self.assertEqual(
            4,
            next(
                item for item in projection.parts if item.reference == "H1-H4"
            ).quantity,
        )

    def test_14_duplicate_part_number_normalization(self) -> None:
        projection = CircuitProjectionService().build(BASE_DOCUMENT)
        result = CircuitPatchService().validate_and_apply(
            BASE_DOCUMENT,
            "ADD ROLE power.extra | preferred | selected | cap\n"
            "ADD PART C2 | role=power.extra | part=cap-100n | qty=1",
        )
        projection = CircuitProjectionService().build(result)
        cap = next(
            item for item in projection.bom if item.normalized_part_number == "cap-100n"
        )
        self.assertEqual(2, cap.quantity)
        self.assertEqual(2, len(projection.bom))

    def test_15_completeness_projection(self) -> None:
        document = CircuitDocument(
            text=BASE_TEXT
            + "\nROLE power.regulator | required | unresolved | exact part needed"
            + "\nROLE display | required | invalid | voltage mismatch"
            + "\nROLE enclosure | required | deferred | dimensions needed"
            + "\nOPEN verify | verify design"
        )
        completeness = CircuitProjectionService().build(document).completeness
        self.assertEqual(4, completeness.required_role_count)
        self.assertEqual(1, completeness.selected_role_count)
        self.assertEqual(1, completeness.unresolved_role_count)
        self.assertEqual(1, completeness.invalid_role_count)
        self.assertEqual(1, completeness.deferred_role_count)
        self.assertEqual(1, completeness.open_issue_count)
        self.assertEqual(2, completeness.raw_bom_line_count)

    def test_16_partial_work_survives_enrichment_failure(self) -> None:
        document = CircuitDocument(
            text=BASE_TEXT
            + "\nROLE display.oled | required | selected | BAD-PART"
            + "\nPART D1 | role=display.oled | part=BAD-PART | qty=1"
        )
        component_repository = InMemoryDesignGenerationRepository()
        component_repository.initialize_project("project-1")
        service = CircuitDocumentGenerationService(
            generator=ForbiddenGenerator(),
            intent_service=IntentService(ForbiddenGenerator()),
            document_repository=InMemoryCircuitDocumentRepository(),
            component_repository=component_repository,
            enrichment_service=SelectiveEnrichment(),  # type: ignore[arg-type]
            component_validator=ComponentDefinitionValidator(),
        )
        projections = CircuitProjectionService().build(document)
        definitions, failures = service.enrich_selected_parts(
            "project-1", projections.parts
        )
        project = CircuitDocumentCompiler().compile_partial_hardware_ir(
            intent=intent(),
            document=document,
            projections=projections,
            enriched_parts=definitions,
            enrichment_failure_count=len(failures),
        )
        self.assertEqual(1, len(failures))
        self.assertEqual(["C1", "U1"], [item.ref_des for item in project.components])
        self.assertFalse(project.is_valid)

    def test_17_deterministic_hardware_ir_compilation(self) -> None:
        projections = CircuitProjectionService().build(BASE_DOCUMENT)
        definitions = [
            definition("CAP-100N", "def-cap"),
            definition("SENSOR-1", "def-sensor"),
        ]
        compiler = CircuitDocumentCompiler()
        first = compiler.compile_partial_hardware_ir(
            intent=intent(),
            document=BASE_DOCUMENT,
            projections=projections,
            enriched_parts=definitions,
        )
        second = compiler.compile_partial_hardware_ir(
            intent=intent(),
            document=BASE_DOCUMENT,
            projections=projections,
            enriched_parts=definitions,
        )
        self.assertEqual(first.model_dump(), second.model_dump())
        self.assertEqual(2, len(first.bom))

    def test_18_legacy_path_compatibility(self) -> None:
        legacy_project = HardwareIR(assembly_metadata={"generation_status": "partial"})

        def legacy(_prompt: str, _options: GenerationOptions) -> HardwareIR:
            return legacy_project

        def forbidden_circuit(
            _prompt: str,
            _options: GenerationOptions,
            _project_id: str,
            _run_id: str,
        ) -> ProjectGenerationResult:
            raise AssertionError("Circuit strategy should not run")

        client = FormaClient(
            legacy_runner=legacy, circuit_document_runner=forbidden_circuit
        )
        try:
            result = client.projects.start_generation(
                prompt="legacy", strategy="legacy"
            ).wait()
        finally:
            client.close()
        self.assertEqual(GenerationStatus.PARTIAL, result.status)
        self.assertIsNotNone(result.project)

    def test_19_prompt_context_excludes_hardware_ir_and_metadata(self) -> None:
        projections = CircuitProjectionService().build(BASE_DOCUMENT)
        initial = build_initial_document_prompt(intent())
        targeted = build_targeted_patch_prompt(
            document=BASE_DOCUMENT,
            target_key="sensing.sensor",
            intent=intent(),
            projections=projections,
            evidence=["TARGET_DATASHEET_FACT"],
            validation_failures=["FOCUSED_ERROR"],
        )
        for prompt in (initial, targeted):
            self.assertNotIn("ORIGINAL_PROMPT_MUST_NOT_REPEAT", prompt)
            self.assertNotIn("part_definitions", prompt)
            self.assertNotIn("assembly_metadata", prompt)
        self.assertIn("TARGET_DATASHEET_FACT", targeted)
        self.assertIn("FOCUSED_ERROR", targeted)

    def test_explicit_circuit_document_sdk_strategy(self) -> None:
        expected = ProjectGenerationResult(
            run_id="ignored",
            project_id="ignored",
            status=GenerationStatus.PARTIAL,
            project=HardwareIR(is_valid=False),
            completeness=GenerationCompleteness(),
        )

        def circuit(
            _prompt: str,
            _options: GenerationOptions,
            project_id: str,
            run_id: str,
        ) -> ProjectGenerationResult:
            return expected.model_copy(
                update={"project_id": project_id, "run_id": run_id}
            )

        client = FormaClient(circuit_document_runner=circuit)
        try:
            result = client.projects.start_generation(
                prompt="circuit", strategy="circuit_document"
            ).wait()
        finally:
            client.close()
        self.assertEqual(GenerationStatus.PARTIAL, result.status)

    def test_complete_offline_service_flow(self) -> None:
        generator = FlowGenerator()
        document_repository = InMemoryCircuitDocumentRepository()
        component_repository = InMemoryDesignGenerationRepository()
        ids = count(1)
        service = CircuitDocumentGenerationService(
            generator=generator,
            intent_service=IntentService(generator, id_factory=lambda: "intent-flow"),
            document_repository=document_repository,
            component_repository=component_repository,
            enrichment_service=ComponentEnrichmentService(
                generator, id_factory=lambda: f"definition-{next(ids)}"
            ),
            component_validator=ComponentDefinitionValidator(),
        )
        result = service.generate(
            prompt="raw request",
            project_id="project-flow",
            run_id="run-flow",
            options=GenerationOptions(),
        )
        self.assertEqual(GenerationStatus.COMPLETE, result.status)
        self.assertEqual(2, len(result.project.bom if result.project else []))
        self.assertEqual(1, len(document_repository.get_revisions("project-flow")))

    def test_patch_provider_failure_returns_committed_partial_project(self) -> None:
        generator = FlowGenerator(fail_patches=True)
        document_repository = InMemoryCircuitDocumentRepository()
        component_repository = InMemoryDesignGenerationRepository()
        service = CircuitDocumentGenerationService(
            generator=generator,
            intent_service=IntentService(
                generator, id_factory=lambda: "intent-partial"
            ),
            document_repository=document_repository,
            component_repository=component_repository,
            enrichment_service=ComponentEnrichmentService(
                generator, id_factory=lambda: "definition-cap"
            ),
            component_validator=ComponentDefinitionValidator(),
        )
        result = service.generate(
            prompt="raw request",
            project_id="project-partial",
            run_id="run-partial",
            options=GenerationOptions(max_circuit_patches=1),
        )
        self.assertEqual(GenerationStatus.PARTIAL, result.status)
        self.assertEqual(["C1"], [item.ref_des for item in result.project.components])
        self.assertEqual("sensing.sensor", result.failures[0].target_id)
        self.assertEqual(1, len(document_repository.get_revisions("project-partial")))


if __name__ == "__main__":
    unittest.main()
