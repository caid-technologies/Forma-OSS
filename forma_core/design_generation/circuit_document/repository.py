"""Revision persistence boundary for validated circuit documents."""

from __future__ import annotations

from copy import deepcopy
from typing import Protocol

from forma_core.design_generation.circuit_document.grammar import parse_document
from forma_core.design_generation.circuit_document.models import CircuitDocument


class CircuitDocumentRepository(Protocol):
    def save_document(self, project_id: str, document: CircuitDocument) -> int: ...
    def get_document(self, project_id: str) -> CircuitDocument | None: ...
    def get_revisions(self, project_id: str) -> list[CircuitDocument]: ...


class InMemoryCircuitDocumentRepository:
    """Reference revision store for successfully validated documents."""

    def __init__(self) -> None:
        self._revisions: dict[str, list[CircuitDocument]] = {}

    def save_document(self, project_id: str, document: CircuitDocument) -> int:
        parse_document(document)
        revisions = self._revisions.setdefault(project_id, [])
        revisions.append(deepcopy(document))
        revision = len(revisions)
        return revision

    def get_document(self, project_id: str) -> CircuitDocument | None:
        revisions = self._revisions.get(project_id, [])
        return deepcopy(revisions[-1]) if revisions else None

    def get_revisions(self, project_id: str) -> list[CircuitDocument]:
        return deepcopy(self._revisions.get(project_id, []))


__all__ = ["CircuitDocumentRepository", "InMemoryCircuitDocumentRepository"]
