"""Database provider, schema, and migration infrastructure.

Application modules should depend on the provider contract exposed here instead
of selecting SQLite or Supabase themselves.
"""

from blueprint_core.persistence.base import DatabaseProvider, DatabaseSchemaError
from blueprint_core.persistence.models import Base
from blueprint_core.persistence.schema import APPLICATION_SCHEMA

__all__ = [
    "APPLICATION_SCHEMA",
    "Base",
    "DatabaseProvider",
    "DatabaseSchemaError",
]
