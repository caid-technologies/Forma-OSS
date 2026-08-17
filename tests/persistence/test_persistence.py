from __future__ import annotations

import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path

from forma_core.jobs.store import JobMetadataStore
from forma_core import database
from forma_core.persistence import APPLICATION_SCHEMA
from forma_core.jobs.migrations import import_legacy_job_database
from forma_core.persistence.providers import SupabaseProvider, create_sqlite_provider
from forma_core.persistence.repositories import SqlAlchemyRepository


class PersistenceArchitectureTests(unittest.TestCase):
    def test_supabase_provider_checks_complete_schema_contract(self) -> None:
        client = _SchemaClient()
        provider = SupabaseProvider(source="test", url="https://example.supabase.co", client=client)

        provider.initialize()

        self.assertEqual([table.name for table in APPLICATION_SCHEMA], list(client.projections))
        self.assertIn("error_debug_json", client.projections["a2a_jobs"])
        self.assertIn("visibility", client.projections["generated_projects"])
        self.assertIn("model_training_opt_out", client.projections["user_settings"])

    def test_supabase_provider_propagates_original_readiness_error(self) -> None:
        failure = ConnectionError("[Errno 111] Connection refused")
        client = _SchemaClient(
            failing_table="component_templates",
            failure=failure,
        )
        provider = SupabaseProvider(source="test", url="http://127.0.0.1:54321", client=client)

        with self.assertRaises(ConnectionError) as raised:
            provider.initialize()

        self.assertIs(raised.exception, failure)

    def test_default_job_store_uses_primary_database_provider(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provider = create_sqlite_provider(
                source="test primary",
                url=f"sqlite:///{Path(directory) / 'forma.db'}",
                import_legacy_jobs=False,
            )
            assert provider.session_factory is not None
            original_provider = database._DATABASE_PROVIDER
            original_repository = database._DATABASE_REPOSITORY
            try:
                database._DATABASE_PROVIDER = provider
                database._DATABASE_REPOSITORY = SqlAlchemyRepository(provider.session_factory)
                provider.initialize()
                store = JobMetadataStore(backend="sqlite")
                job_id = f"job_shared_{uuid.uuid4().hex}"

                store.create_job(
                    job_id=job_id,
                    message_id=f"msg_{uuid.uuid4().hex}",
                    correlation_id=None,
                    action="forma.generate_project",
                    sender="test",
                    recipient="forma",
                    payload={"prompt": "shared database"},
                    server_owned=True,
                )

                assert provider.engine is not None
                with provider.engine.connect() as connection:
                    stored_job_id = connection.exec_driver_sql(
                        "SELECT job_id FROM a2a_jobs WHERE job_id = ?",
                        (job_id,),
                    ).scalar_one()
            finally:
                database._DATABASE_PROVIDER = original_provider
                database._DATABASE_REPOSITORY = original_repository

        self.assertEqual(job_id, stored_job_id)
        self.assertEqual("primary", store.get_config()["scope"])

    def test_database_facade_delegates_project_and_chat_work_to_selected_repository(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provider = create_sqlite_provider(
                source="test primary",
                url=f"sqlite:///{Path(directory) / 'forma.db'}",
                import_legacy_jobs=False,
            )
            assert provider.session_factory is not None
            repository = SqlAlchemyRepository(provider.session_factory)
            provider.initialize()
            original_repository = database._DATABASE_REPOSITORY
            try:
                database._DATABASE_REPOSITORY = repository
                project_id = str(uuid.uuid4())
                database.save_generated_project(
                    project_id=project_id,
                    title="Shared persistence",
                    prompt="exercise repository routing",
                    hardware_ir={"assembly_metadata": {"chat_id": "chat_shared"}},
                    created_at="2026-07-25T12:00:00Z",
                    chat_id="chat_shared",
                    owner_user_id="user_shared",
                    visibility="private",
                )

                project = database.get_generated_project(project_id)
                chat = database.get_project_chat("chat_shared", "user_shared")
                deleted = database.delete_project_chat("chat_shared", "user_shared")
                project_after_chat_delete = database.get_generated_project(project_id)
            finally:
                database._DATABASE_REPOSITORY = original_repository

        self.assertIsNotNone(project)
        self.assertEqual("private", project.visibility)
        self.assertIsNotNone(chat)
        self.assertTrue(deleted)
        self.assertIsNone(project_after_chat_delete.chat_id)

    def test_legacy_job_import_is_idempotent_and_does_not_overwrite_primary_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            primary_path = Path(directory) / "forma.db"
            legacy_path = Path(directory) / "forma_jobs.db"
            provider = create_sqlite_provider(
                source="test",
                url=f"sqlite:///{primary_path}",
                import_legacy_jobs=False,
            )
            provider.initialize()
            self._create_legacy_job_database(legacy_path)

            assert provider.engine is not None
            imported_first = import_legacy_job_database(provider.engine, str(legacy_path))
            imported_second = import_legacy_job_database(provider.engine, str(legacy_path))

            with provider.engine.connect() as connection:
                row = connection.exec_driver_sql(
                    "SELECT status, payload_json FROM a2a_jobs WHERE job_id = 'job_legacy'"
                ).one()

        self.assertEqual(1, imported_first)
        self.assertEqual(0, imported_second)
        self.assertEqual("succeeded", row[0])
        self.assertIn("legacy", row[1])

    def test_user_training_preference_is_queryable_by_owner_and_opt_out_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provider = create_sqlite_provider(
                source="test primary",
                url=f"sqlite:///{Path(directory) / 'forma.db'}",
                import_legacy_jobs=False,
            )
            assert provider.session_factory is not None
            repository = SqlAlchemyRepository(provider.session_factory)
            provider.initialize()
            original_repository = database._DATABASE_REPOSITORY
            try:
                database._DATABASE_REPOSITORY = repository
                default_settings = database.get_user_settings("user_default")
                opted_out = database.set_user_model_training_preference(
                    "user_opted_out",
                    allow_model_training=False,
                    updated_at="2026-07-27T20:00:00Z",
                )
                database.set_user_model_training_preference(
                    "user_allowed",
                    allow_model_training=True,
                    updated_at="2026-07-27T20:01:00Z",
                )
                opted_out_ids = database.list_model_training_opt_out_user_ids()
            finally:
                database._DATABASE_REPOSITORY = original_repository

        self.assertIsNone(default_settings)
        self.assertTrue(opted_out.model_training_opt_out)
        self.assertEqual(["user_opted_out"], opted_out_ids)

    @staticmethod
    def _create_legacy_job_database(path: Path) -> None:
        with sqlite3.connect(path) as connection:
            connection.execute(
                """
                CREATE TABLE a2a_jobs (
                    job_id TEXT PRIMARY KEY,
                    message_id TEXT NOT NULL,
                    correlation_id TEXT,
                    action TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    status TEXT NOT NULL,
                    server_owned INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    payload_json TEXT,
                    result_summary_json TEXT,
                    error TEXT
                )
                """
            )
            connection.execute(
                """
                INSERT INTO a2a_jobs (
                    job_id, message_id, action, sender, recipient, status,
                    server_owned, created_at, updated_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "job_legacy",
                    "msg_legacy",
                    "forma.generate_project",
                    "test",
                    "forma",
                    "succeeded",
                    1,
                    "2026-07-01T00:00:00Z",
                    "2026-07-01T00:00:01Z",
                    '{"prompt":"legacy"}',
                ),
            )


class _SchemaResponse:
    data: list[dict[str, object]] = []


class _SchemaQuery:
    def __init__(self, client: "_SchemaClient", table: str) -> None:
        self._client = client
        self._table = table

    def select(self, projection: str) -> "_SchemaQuery":
        self._client.projections[self._table] = projection
        return self

    def limit(self, _limit: int) -> "_SchemaQuery":
        return self

    def execute(self) -> _SchemaResponse:
        if self._client.failing_table == self._table:
            raise self._client.failure
        return _SchemaResponse()


class _SchemaClient:
    def __init__(
        self,
        failing_table: str | None = None,
        failure: Exception | None = None,
    ) -> None:
        self.failing_table = failing_table
        self.failure = failure or RuntimeError("missing table or column")
        self.projections: dict[str, str] = {}

    def table(self, table: str) -> _SchemaQuery:
        return _SchemaQuery(self, table)


if __name__ == "__main__":
    unittest.main()
