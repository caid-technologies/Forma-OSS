"""Readable experimental generation flow centered on CircuitDocument."""

from __future__ import annotations

from typing import Protocol

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
    CircuitProjections,
    CircuitProjectionService,
    PartProjection,
    normalize_part_number,
)
from forma_core.design_generation.circuit_document.prompts import (
    CircuitPatchDraft,
    build_initial_document_prompt,
    build_targeted_patch_prompt,
)
from forma_core.design_generation.circuit_document.repository import (
    CircuitDocumentRepository,
)
from forma_core.design_generation.circuit_document.validation import (
    CircuitDocumentValidationError,
)
from forma_core.design_generation.components.enrichment import (
    ComponentEnrichmentService,
)
from forma_core.design_generation.components.selection import PartSelectionDraft
from forma_core.design_generation.components.validation import (
    ComponentDefinitionValidator,
)
from forma_core.design_generation.intent.models import MachineIntent
from forma_core.design_generation.intent.service import (
    IntentService,
    StructuredGenerator,
)
from forma_core.design_generation.repository import DesignGenerationRepository
from forma_core.design_generation.state_machine.models import (
    GenerationCompleteness,
    GenerationFailureSummary,
    GenerationOptions,
    GenerationStatus,
    ProjectGenerationResult,
)
from forma_core.workspaces.projects.models import PartDefinition


class TargetEvidenceService(Protocol):
    """Target-scoped research boundary; implementations must not load full projects."""

    def load_targeted_evidence(self, target_key: str) -> list[str]: ...


class EmptyTargetEvidenceService:
    """Offline/default evidence source used when no targeted research is configured."""

    def load_targeted_evidence(self, target_key: str) -> list[str]:
        del target_key
        return []


class CircuitDocumentGenerationService:
    """Explicit intent → document → patches → enrichment → compiler flow."""

    def __init__(
        self,
        *,
        generator: StructuredGenerator,
        intent_service: IntentService,
        document_repository: CircuitDocumentRepository,
        component_repository: DesignGenerationRepository,
        enrichment_service: ComponentEnrichmentService,
        component_validator: ComponentDefinitionValidator,
        evidence_service: TargetEvidenceService | None = None,
        patch_service: CircuitPatchService | None = None,
        projection_service: CircuitProjectionService | None = None,
        compiler: CircuitDocumentCompiler | None = None,
    ) -> None:
        self.generator = generator
        self.intent_service = intent_service
        self.document_repository = document_repository
        self.component_repository = component_repository
        self.enrichment_service = enrichment_service
        self.component_validator = component_validator
        self.evidence_service = evidence_service or EmptyTargetEvidenceService()
        self.patch_service = patch_service or CircuitPatchService()
        self.projection_service = projection_service or CircuitProjectionService()
        self.compiler = compiler or CircuitDocumentCompiler()

    def understand_intent(self, *, project_id: str, prompt: str) -> MachineIntent:
        draft = self.intent_service.generate(prompt=prompt)
        intent = self.intent_service.create_intent(
            project_id=project_id, source_prompt=prompt, draft=draft
        )
        self.component_repository.initialize_project(project_id)
        self.component_repository.save_intent(intent)
        return intent

    def create_initial_document(self, intent: MachineIntent) -> CircuitDocument:
        raw = self.generator.generate(
            build_initial_document_prompt(intent), CircuitDocument
        )
        document = (
            raw
            if isinstance(raw, CircuitDocument)
            else CircuitDocument.model_validate(raw)
        )
        return serialize_document(parse_document(document))

    def select_next_unresolved_target(
        self, projections: CircuitProjections
    ) -> str | None:
        part_roles = {part.role_key for part in projections.parts}
        for role in projections.roles:
            if role.status.value in {"unresolved", "invalid"}:
                return role.key
            if role.status.value == "selected" and role.key not in part_roles:
                return role.key
        return next(iter(projections.open_obligations), None)

    def load_targeted_evidence(self, target_key: str) -> list[str]:
        return self.evidence_service.load_targeted_evidence(target_key)

    def generate_patch(
        self,
        *,
        intent: MachineIntent,
        document: CircuitDocument,
        projections: CircuitProjections,
        target_key: str,
        evidence: list[str],
        validation_failures: list[str],
    ) -> str:
        raw = self.generator.generate(
            build_targeted_patch_prompt(
                document=document,
                target_key=target_key,
                intent=intent,
                projections=projections,
                evidence=evidence,
                validation_failures=validation_failures,
            ),
            CircuitPatchDraft,
        )
        draft = (
            raw
            if isinstance(raw, CircuitPatchDraft)
            else CircuitPatchDraft.model_validate(raw)
        )
        return draft.text

    @staticmethod
    def _part_category(part: PartProjection) -> str:
        mechanical_tokens = {"pcb", "enclosure", "mounting", "screw", "standoff"}
        return (
            "Mechanical"
            if any(token in part.role_key.casefold() for token in mechanical_tokens)
            else "Component"
        )

    def enrich_selected_parts(
        self, project_id: str, parts: list[PartProjection]
    ) -> tuple[list[PartDefinition], list[GenerationFailureSummary]]:
        definitions: dict[str, PartDefinition] = {}
        failures: list[GenerationFailureSummary] = []
        for part in parts:
            key = normalize_part_number(part.part_number)
            if key in definitions:
                continue
            existing = self.component_repository.find_definition(
                project_id, None, part.part_number
            )
            if existing is not None:
                definitions[key] = existing
                continue
            selection = PartSelectionDraft(
                role_id=part.role_key,
                manufacturer_part_number=part.part_number,
                name=part.part_number,
                category=self._part_category(part),
                description=f"Selected for circuit role {part.role_key}",
                quantity=part.quantity,
                selection_reason=f"Committed by CircuitDocument role {part.role_key}",
            )
            try:
                definition = self.enrichment_service.enrich_component(selection)
                validation = self.component_validator.validate_component(definition)
                if not validation.is_valid:
                    raise ValueError("; ".join(validation.errors))
                self.component_repository.save_definition(project_id, definition)
                definitions[key] = definition
            except Exception as error:  # noqa: BLE001 - isolate failures to this selected part
                failures.append(
                    GenerationFailureSummary(
                        phase="enrich_component",
                        target_id=part.role_key,
                        error_code="component_enrichment_failed",
                        message=str(error),
                        recoverable=True,
                    )
                )
        return list(definitions.values()), failures

    def generate(
        self,
        *,
        prompt: str,
        project_id: str,
        run_id: str,
        options: GenerationOptions,
    ) -> ProjectGenerationResult:
        intent = self.understand_intent(project_id=project_id, prompt=prompt)
        document = self.create_initial_document(intent)
        self.document_repository.save_document(project_id, document)
        patch_failures: list[GenerationFailureSummary] = []
        focused_errors: list[str] = []

        for _ in range(options.max_circuit_patches):
            projections = self.projection_service.build(document)
            target = self.select_next_unresolved_target(projections)
            if target is None:
                break
            try:
                evidence = self.load_targeted_evidence(target)
                patch_text = self.generate_patch(
                    intent=intent,
                    document=document,
                    projections=projections,
                    target_key=target,
                    evidence=evidence,
                    validation_failures=focused_errors,
                )
                candidate = self.patch_service.validate_and_apply(document, patch_text)
            except CircuitDocumentValidationError as error:
                focused_errors = error.errors
                continue
            except Exception as error:  # noqa: BLE001 - preserve committed partial work
                patch_failures.append(
                    GenerationFailureSummary(
                        phase="circuit_document_patch",
                        target_id=target,
                        error_code="target_resolution_failed",
                        message=str(error),
                        recoverable=True,
                    )
                )
                break
            document = candidate
            focused_errors = []
            self.document_repository.save_document(project_id, document)
        remaining_target = self.select_next_unresolved_target(
            self.projection_service.build(document)
        )
        if remaining_target is not None and not patch_failures:
            patch_failures.append(
                GenerationFailureSummary(
                    phase="circuit_document_patch",
                    target_id=remaining_target,
                    error_code="patch_limit_reached",
                    message=(
                        "CircuitDocument still has unresolved work after the patch limit."
                        + (
                            f" Last validation errors: {'; '.join(focused_errors)}"
                            if focused_errors
                            else ""
                        )
                    ),
                    recoverable=True,
                )
            )

        projections = self.projection_service.build(document)
        enriched_parts, enrichment_failures = self.enrich_selected_parts(
            project_id, projections.parts
        )
        failures = [*patch_failures, *enrichment_failures]
        project = self.compiler.compile_partial_hardware_ir(
            intent=intent,
            document=document,
            projections=projections,
            enriched_parts=enriched_parts,
            enrichment_failure_count=len(enrichment_failures),
        )
        completeness = projections.completeness
        status = (
            GenerationStatus.COMPLETE
            if project.is_valid and not failures
            else GenerationStatus.PARTIAL
        )
        return ProjectGenerationResult(
            run_id=run_id,
            project_id=project_id,
            status=status,
            project=project,
            completeness=GenerationCompleteness(
                required_capability_count=len(intent.required_capabilities),
                covered_capability_count=(
                    len(intent.required_capabilities)
                    if completeness.selected_role_count
                    else 0
                ),
                required_obligation_count=completeness.required_role_count,
                resolved_obligation_count=completeness.selected_role_count,
                unresolved_obligation_count=(
                    completeness.unresolved_role_count
                    + completeness.invalid_role_count
                    + completeness.open_issue_count
                ),
                deferred_obligation_count=completeness.deferred_role_count,
                blocked_obligation_count=completeness.invalid_role_count,
                valid_bom_line_count=len(project.bom),
                physical_component_count=len(project.components),
            ),
            failures=failures,
        )


__all__ = [
    "CircuitDocumentGenerationService",
    "EmptyTargetEvidenceService",
    "TargetEvidenceService",
]
