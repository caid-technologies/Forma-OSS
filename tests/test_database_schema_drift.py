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
        self.eqs: list[tuple[str, Any]] = []

    def eq(self, field: str, value: Any) -> "FakeSupabaseQuery":
        self.eqs.append((field, value))
        return self

    def order(self, field: str, desc: bool = False) -> "FakeSupabaseQuery":
        return self

    def execute(self) -> FakeSupabaseResponse:
        self.client.mutations.append(
            {
                "operation": self.operation,
                "table": self.table_name,
                "payload": dict(self.payload),
                "eqs": list(self.eqs),
            }
        )
        if self.operation == "select":
            referenced = {column.strip() for column in self.payload.get("columns", "").split(",")}
        else:
            referenced = set(self.payload)
        referenced.update(field for field, _ in self.eqs)
        for column in self.client.missing_columns:
            if column in referenced:
                raise RuntimeError(
                    "{'message': \"Could not find the "
                    f"'{column}' column of '{self.table_name}' in the schema cache\", "
                    "'code': 'PGRST204', 'hint': None, 'details': None}"
                )
        if self.operation == "select":
            return FakeSupabaseResponse([dict(row) for row in self.client.select_rows])
        return FakeSupabaseResponse([dict(self.payload)])


class FakeSupabaseTable:
    def __init__(self, client: "FakeSupabaseClient", name: str) -> None:
        self.client = client
        self.name = name

    def insert(self, payload: dict[str, Any]) -> FakeSupabaseQuery:
        return FakeSupabaseQuery(self.client, self.name, "insert", payload)

    def update(self, payload: dict[str, Any]) -> FakeSupabaseQuery:
        return FakeSupabaseQuery(self.client, self.name, "update", payload)

    def select(self, columns: str) -> FakeSupabaseQuery:
        return FakeSupabaseQuery(self.client, self.name, "select", {"columns": columns})

    def delete(self) -> FakeSupabaseQuery:
        return FakeSupabaseQuery(self.client, self.name, "delete")


class FakeSupabaseClient:
    def __init__(self, missing_columns: set[str], select_rows: list[dict[str, Any]] | None = None) -> None:
        self.missing_columns = missing_columns
        self.select_rows = select_rows or []
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

    def test_save_generated_project_retries_without_owner_id_for_postgrest_schema_cache(self) -> None:
        client = FakeSupabaseClient(missing_columns={"owner_id"})

        with supabase_backend(client):
            database.save_generated_project(
                project_id=PROJECT_ID,
                title="LED Controller",
                prompt="Blink an LED",
                hardware_ir={"assembly_metadata": {}},
                created_at="2026-07-08T15:07:57Z",
                owner_id="user_123",
            )

        self.assertIn("owner_id", client.mutations[0]["payload"])
        self.assertNotIn("owner_id", client.mutations[-1]["payload"])

    def test_save_generated_project_retries_without_all_missing_optional_columns(self) -> None:
        client = FakeSupabaseClient(missing_columns={"chat_id", "owner_id"})

        with supabase_backend(client):
            database.save_generated_project(
                project_id=PROJECT_ID,
                title="LED Controller",
                prompt="Blink an LED",
                hardware_ir={"assembly_metadata": {"chat_id": "chat_123"}},
                created_at="2026-07-08T15:07:57Z",
                chat_id="chat_123",
                owner_id="user_123",
            )

        final_payload = client.mutations[-1]["payload"]
        self.assertNotIn("chat_id", final_payload)
        self.assertNotIn("owner_id", final_payload)
        self.assertEqual(final_payload["project_id"], PROJECT_ID)

    def test_owner_scoped_list_fails_closed_when_owner_id_column_missing(self) -> None:
        client = FakeSupabaseClient(
            missing_columns={"owner_id"},
            select_rows=[{"id": 1, "project_id": PROJECT_ID, "title": "LED", "prompt": "p", "created_at": "now"}],
        )

        with supabase_backend(client):
            projects = database.list_generated_projects(owner_id="user_123")

        self.assertEqual(projects, [])

    def test_unfiltered_list_retries_without_owner_id_column(self) -> None:
        client = FakeSupabaseClient(
            missing_columns={"owner_id"},
            select_rows=[{"id": 1, "project_id": PROJECT_ID, "chat_id": None, "title": "LED", "prompt": "p", "created_at": "now"}],
        )

        with supabase_backend(client):
            projects = database.list_generated_projects()

        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0].project_id, PROJECT_ID)

    def test_delete_generated_project_scopes_by_project_and_owner(self) -> None:
        client = FakeSupabaseClient(missing_columns=set())

        with supabase_backend(client):
            deleted = database.delete_generated_project(PROJECT_ID, owner_id="user_123")

        self.assertTrue(deleted)
        self.assertEqual(client.mutations[-1]["operation"], "delete")
        self.assertEqual(
            client.mutations[-1]["eqs"],
            [("project_id", PROJECT_ID), ("owner_id", "user_123")],
        )

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
