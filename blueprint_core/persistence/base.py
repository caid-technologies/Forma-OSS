from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class DatabaseSchemaError(RuntimeError):
    """The configured database does not satisfy the application schema contract."""


class DatabaseProvider(ABC):
    """Owns backend-specific connection, schema, and readiness behavior."""

    backend: str
    source: str
    url: str

    @abstractmethod
    def initialize(self) -> None:
        """Prepare or verify this provider's application schema."""

    def describe(self) -> Dict[str, Any]:
        return {
            "backend": self.backend,
            "source": self.source,
            "url": self.url,
        }
