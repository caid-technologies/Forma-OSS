"""Construction adapter for the experimental CircuitDocument strategy."""

from __future__ import annotations

from typing import Any

from forma_core.design_generation.circuit_document.repository import (
    InMemoryCircuitDocumentRepository,
)
from forma_core.design_generation.circuit_document.service import (
    CircuitDocumentGenerationService,
)
from forma_core.design_generation.components import (
    ComponentDefinitionValidator,
    ComponentEnrichmentService,
)
from forma_core.design_generation.intent import (
    CallableStructuredGenerator,
    IntentService,
)
from forma_core.design_generation.repository import InMemoryDesignGenerationRepository


def build_circuit_document_service(
    provider_call: Any,
) -> CircuitDocumentGenerationService:
    generator = CallableStructuredGenerator(provider_call)
    return CircuitDocumentGenerationService(
        generator=generator,
        intent_service=IntentService(generator),
        document_repository=InMemoryCircuitDocumentRepository(),
        component_repository=InMemoryDesignGenerationRepository(),
        enrichment_service=ComponentEnrichmentService(generator),
        component_validator=ComponentDefinitionValidator(),
    )


__all__ = ["build_circuit_document_service"]
