from __future__ import annotations

import os
import tempfile
import unittest
from contextlib import contextmanager
from typing import Iterator

from backend.firecrawl_webhooks_api import extract_firecrawl_job_id, firecrawl_webhook_event
from backend.job_store import JobMetadataStore


@contextmanager
def isolated_firecrawl_webhook_env(**overrides: str) -> Iterator[None]:
    keys = ("FIRECRAWL_WEBHOOK_SECRET", "BLUEPRINT_FIRECRAWL_WEBHOOK_SECRET")
    old_values = {key: os.environ.get(key) for key in keys}
    try:
        for key in keys:
            os.environ.pop(key, None)
        os.environ.update(overrides)
        yield
    finally:
        for key in keys:
            os.environ.pop(key, None)
            if old_values[key] is not None:
                os.environ[key] = old_values[key] or ""


class FirecrawlWebhookTests(unittest.TestCase):
    def test_extract_firecrawl_job_id_reads_metadata(self) -> None:
        payload = {"data": {"metadata": {"blueprint_job_id": "job_frontend_firecrawl"}}}

        self.assertEqual("job_frontend_firecrawl", extract_firecrawl_job_id(payload))

    def test_firecrawl_webhook_page_event_maps_to_source_found(self) -> None:
        job = {"payload": {"prompt": "water sensor module"}}
        event = firecrawl_webhook_event(
            {
                "type": "crawl.page",
                "id": "crawl_123",
                "data": {
                    "title": "Water sensor reference",
                    "url": "https://example.com/water-sensor",
                    "markdown": "Water sensor module wiring details.",
                },
            },
            job,
        )

        self.assertEqual("source_found", event["status"])
        self.assertEqual("external_research", event["step_id"])
        self.assertEqual("example.com", event["details"]["domain"])
        self.assertIn("water", event["details"]["matched_query_terms"])
        self.assertIn("Source domain: example.com", event["details"]["relevance_reason"])

    def test_firecrawl_webhook_progress_can_be_persisted_to_job(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db") as file:
            store = JobMetadataStore(file.name, backend="sqlite")
            store.create_job(
                job_id="job_firecrawl_webhook",
                message_id="msg_firecrawl_webhook",
                correlation_id=None,
                action="blueprint.generate_project",
                sender="frontend",
                recipient="blueprint",
                payload={"prompt": "water sensor", "workflow": "web_research"},
                server_owned=True,
            )
            event = firecrawl_webhook_event(
                {
                    "type": "crawl.page",
                    "data": {
                        "title": "Water sensor reference",
                        "url": "https://example.com/water-sensor",
                        "markdown": "Water sensor source.",
                    },
                },
                store.get_job("job_firecrawl_webhook"),
            )
            store.append_progress_event("job_firecrawl_webhook", event)

            job = store.get_job("job_firecrawl_webhook")

        self.assertIsNotNone(job)
        assert job is not None
        self.assertEqual("source_found", job["progress_events"][-1]["status"])
        self.assertIn("Water sensor reference", job["agent_thinking"])

    def test_webhook_endpoint_rejects_bad_secret(self) -> None:
        with isolated_firecrawl_webhook_env(FIRECRAWL_WEBHOOK_SECRET="expected"):
            from fastapi import HTTPException
            from starlette.datastructures import Headers

            class FakeRequest:
                headers = Headers({"x-blueprint-webhook-secret": "wrong"})

            from backend.firecrawl_webhooks_api import _require_webhook_secret

            with self.assertRaises(HTTPException):
                _require_webhook_secret(FakeRequest())  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
