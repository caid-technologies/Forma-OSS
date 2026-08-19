from __future__ import annotations

import threading
from typing import Any

from forma_core.persistence.base import DatabaseProvider
from forma_core.persistence.schema import APPLICATION_SCHEMA


class SupabaseProvider(DatabaseProvider):
    backend = "supabase"

    def __init__(self, *, source: str, url: str, client: Any) -> None:
        self.source = source
        self.url = url
        self.client = client
        self._initialize_lock = threading.Lock()
        self._initialized = False

    def initialize(self) -> None:
        with self._initialize_lock:
            if self._initialized:
                return
            for table in APPLICATION_SCHEMA:
                self.client.table(table.name).select(table.projection).limit(1).execute()
            self._initialized = True

    def describe(self) -> dict[str, Any]:
        config = super().describe()
        config.update({"client": "supabase-py"})
        return config
