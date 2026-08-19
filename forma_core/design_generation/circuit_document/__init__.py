"""Experimental compact agent-facing machine-design representation."""

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
from forma_core.design_generation.circuit_document.service import (
    CircuitDocumentGenerationService,
)

__all__ = [
    "CircuitDocument",
    "CircuitDocumentCompiler",
    "CircuitDocumentGenerationService",
    "CircuitPatchService",
    "CircuitProjectionService",
    "parse_document",
    "serialize_document",
]
