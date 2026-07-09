from __future__ import annotations

import os
import tempfile
import unittest
from contextlib import contextmanager
from typing import Any, Iterator

from backend.job_store import JobMetadataStore
from blueprint_core.debug import api_error_detail, exception_debug_payload, redact_debug_value


DEBUG_ENV_KEYS = ("BLUEPRINT_DEBUG", "BLUEPRINT_DEBUG_MODE", "API_DEBUG", "DEBUG")


class FakeSupabaseResponse:
    def __init__(self, data: list[dict[str, Any]] | None = None) -> None:
        self.data = data or []


class FakeSupabaseQuery:
    def __init__(
        self,
        client: "FakeSupabaseClient",
        operation: str,
        payload: dict[str, Any] | None = None,
        columns: str = "*",
    ) -> None:
        self.client = client
        self.operation = operation
        self.payload = payload or {}
        self.columns = columns
        self.eq_field: str | None = None
        self.eq_value: Any = None

    def eq(self, field: str, value: Any) -> "FakeSupabaseQuery":
        self.eq_field = field
        self.eq_value = value
        return self

    def limit(self, _limit: int) -> "FakeSupabaseQuery":
        return self

    def order(self, *_args: Any, **_kwargs: Any) -> "FakeSupabaseQuery":
        return self

    def execute(self) -> FakeSupabaseResponse:
        if self.operation == "select":
            if self.eq_field == "job_id" and self.eq_value in self.client.rows:
                return FakeSupabaseResponse([self.client.rows[self.eq_value]])
            return FakeSupabaseResponse([])

        self.client.mutations.append(dict(self.payload))
        for column in self.client.missing_columns:
            if column in self.payload:
                raise RuntimeError(f"{{'message': \"Could not find the '{column}' column of 'a2a_jobs' in the schema cache\", 'code': 'PGRST204'}}")

        if self.operation == "upsert":
            self.client.rows[self.payload["job_id"]] = dict(self.payload)
        elif self.operation == "update" and self.eq_field == "job_id":
            self.client.rows.setdefault(self.eq_value, {"job_id": self.eq_value}).update(self.payload)
        return FakeSupabaseResponse([dict(self.payload)])


class FakeSupabaseTable:
    def __init__(self, client: "FakeSupabaseClient") -> None:
        self.client = client

    def select(self, columns: str) -> FakeSupabaseQuery:
        return FakeSupabaseQuery(self.client, "select", columns=columns)

    def upsert(self, payload: dict[str, Any], on_conflict: str | None = None) -> FakeSupabaseQuery:
        return FakeSupabaseQuery(self.client, "upsert", payload=payload)

    def update(self, payload: dict[str, Any]) -> FakeSupabaseQuery:
        return FakeSupabaseQuery(self.client, "update", payload=payload)


class FakeSupabaseClient:
    def __init__(self, missing_columns: set[str]) -> None:
        self.missing_columns = missing_columns
        self.mutations: list[dict[str, Any]] = []
        self.rows: dict[str, dict[str, Any]] = {}

    def table(self, _name: str) -> FakeSupabaseTable:
        return FakeSupabaseTable(self)


@contextmanager
def isolated_debug_env(**overrides: str) -> Iterator[None]:
    old_values = {key: os.environ.get(key) for key in DEBUG_ENV_KEYS}
    try:
        for key in DEBUG_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ.update(overrides)
        yield
    finally:
        for key in DEBUG_ENV_KEYS:
            os.environ.pop(key, None)
            if old_values[key] is not None:
                os.environ[key] = old_values[key] or ""


class DebugModeTests(unittest.TestCase):
    def test_debug_mode_flag_enables_api_trace_payload(self) -> None:
        with isolated_debug_env(BLUEPRINT_DEBUG="true"):
            try:
                raise RuntimeError("provider failed with api_key=sk-testsecret123456")
            except RuntimeError as exc:
                detail = api_error_detail(
                    code="generation_failed",
                    message=str(exc),
                    exc=exc,
                    job_id="job_test",
                    provider="openai",
                    model="gpt-5.5",
                    context={"api_key": "sk-testsecret123456", "prompt": "blink an LED"},
                )

        self.assertEqual("generation_failed", detail["code"])
        self.assertEqual("job_test", detail["job_id"])
        self.assertIn("debug", detail)
        self.assertEqual("RuntimeError", detail["debug"]["error_type"])
        self.assertIn("Traceback", detail["debug"]["traceback"])
        self.assertNotIn("sk-testsecret123456", str(detail))
        self.assertEqual("<redacted>", detail["debug"]["context"]["api_key"])

    def test_debug_payload_is_omitted_when_debug_mode_is_off(self) -> None:
        with isolated_debug_env():
            try:
                raise RuntimeError("plain failure")
            except RuntimeError as exc:
                detail = api_error_detail(code="generation_failed", message=str(exc), exc=exc)

        self.assertNotIn("debug", detail)

    def test_redact_debug_value_redacts_nested_secret_keys(self) -> None:
        redacted = redact_debug_value({"nested": {"token": "abc123456789"}, "ok": "visible"})

        self.assertEqual("<redacted>", redacted["nested"]["token"])
        self.assertEqual("visible", redacted["ok"])

    def test_failed_job_persists_debug_payload_when_provided(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db") as file:
            store = JobMetadataStore(file.name, backend="sqlite")
            store.create_job(
                job_id="job_debug_test",
                message_id="msg_debug_test",
                correlation_id=None,
                action="blueprint.generate_project",
                sender="test",
                recipient="blueprint",
                payload={"prompt": "blink an LED", "image_data": "data:image/png;base64,abc"},
                server_owned=True,
            )
            try:
                raise ValueError("bad runtime")
            except ValueError as exc:
                store.mark_failed("job_debug_test", str(exc), exception_debug_payload(exc, context={"api_key": "sk-testsecret123456"}))

            job = store.get_job("job_debug_test")

        self.assertIsNotNone(job)
        assert job is not None
        self.assertEqual("failed", job["status"])
        self.assertEqual("bad runtime", job["error"])
        self.assertEqual("ValueError", job["error_debug"]["error_type"])
        self.assertEqual("<redacted>", job["error_debug"]["context"]["api_key"])
        self.assertEqual("<redacted>", job["payload"]["image_data"])

    def test_supabase_create_job_retries_without_missing_optional_debug_column(self) -> None:
        client = FakeSupabaseClient(missing_columns={"error_debug_json"})
        store = JobMetadataStore(backend="supabase")
        store.backend = "supabase"
        store._client = client

        job = store.create_job(
            job_id="job_supabase_schema_drift",
            message_id="msg_supabase_schema_drift",
            correlation_id=None,
            action="blueprint.generate_project",
            sender="test",
            recipient="blueprint",
            payload={"prompt": "blink an LED"},
            server_owned=True,
        )

        self.assertEqual("queued", job["status"])
        self.assertIn("error_debug_json", client.mutations[0])
        self.assertNotIn("error_debug_json", client.mutations[-1])
        self.assertIn("error_debug_json", store._supabase_unavailable_columns)


if __name__ == "__main__":
    unittest.main()
