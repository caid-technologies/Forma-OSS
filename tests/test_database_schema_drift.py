from __future__ import annotations

import unittest
from contextlib import contextmanager
from typing import Any, Iterator

from blueprint_core import database


PROJECT_ID = "611fd725-3dc2-4add-b830-02aa1c3fe775"


class FakeSupabaseResponse:
    def __init__(self, data: list[dict[str, Any]] | None = None) -> None:
        self.data = data or []


class FakeSupabaseQuery:
    def __init__(
        self,
        client: "FakeSupabaseClient",
        table_name: str,
        operation: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.client = client
        self.table_name = table_name
        self.operation = operation
        self.payload = payload or {}
        self.eq_field: str | None = None
        self.eq_value: Any = None

    def eq(self, field: str, value: Any) -> "FakeSupabaseQuery":
        self.eq_field = field
        self.eq_value = value
        return self

    def execute(self) -> FakeSupabaseResponse:
        self.client.mutations.append(
            {
                "operation": self.operation,
                "table": self.table_name,
                "payload": dict(self.payload),
            }
        )
        for column in self.client.missing_columns:
            if column in self.payload:
                raise RuntimeError(
                    "{'message': \"Could not find the "
                    f"'{column}' column of '{self.table_name}' in the schema cache\", "
                    "'code': 'PGRST204', 'hint': None, 'details': None}"
                )
        return FakeSupabaseResponse([dict(self.payload)])


class FakeSupabaseTable:
    def __init__(self, client: "FakeSupabaseClient", name: str) -> None:
        self.client = client
        self.name = name

    def insert(self, payload: dict[str, Any]) -> FakeSupabaseQuery:
        return FakeSupabaseQuery(self.client, self.name, "insert", payload)

    def update(self, payload: dict[str, Any]) -> FakeSupabaseQuery:
        return FakeSupabaseQuery(self.client, self.name, "update", payload)


class FakeSupabaseClient:
    def __init__(self, missing_columns: set[str]) -> None:
        self.missing_columns = missing_columns
        self.mutations: list[dict[str, Any]] = []

    def table(self, name: str) -> FakeSupabaseTable:
        return FakeSupabaseTable(self, name)


@contextmanager
def supabase_backend(client: FakeSupabaseClient) -> Iterator[None]:
    original_backend = database.DATABASE_BACKEND
    original_client = database._SUPABASE_CLIENT
    try:
        database.DATABASE_BACKEND = "supabase"
        database._SUPABASE_CLIENT = client
        yield
    finally:
        database.DATABASE_BACKEND = original_backend
        database._SUPABASE_CLIENT = original_client


class DatabaseSchemaDriftTests(unittest.TestCase):
    def test_save_generated_project_retries_without_chat_id_for_postgrest_schema_cache(self) -> None:
        client = FakeSupabaseClient(missing_columns={"chat_id"})

        with supabase_backend(client):
            database.save_generated_project(
                project_id=PROJECT_ID,
                title="LED Controller",
                prompt="Blink an LED",
                hardware_ir={"assembly_metadata": {"chat_id": "chat_123"}},
                created_at="2026-07-08T15:07:57Z",
                chat_id="chat_123",
            )

        self.assertIn("chat_id", client.mutations[0]["payload"])
        self.assertNotIn("chat_id", client.mutations[-1]["payload"])

    def test_update_generated_project_retries_without_chat_id_for_postgrest_schema_cache(self) -> None:
        client = FakeSupabaseClient(missing_columns={"chat_id"})

        with supabase_backend(client):
            updated = database.update_generated_project_hardware_ir(
                PROJECT_ID,
                {"assembly_metadata": {"chat_id": "chat_123"}},
            )

        self.assertTrue(updated)
        self.assertIn("chat_id", client.mutations[0]["payload"])
        self.assertNotIn("chat_id", client.mutations[-1]["payload"])


if __name__ == "__main__":
    unittest.main()
