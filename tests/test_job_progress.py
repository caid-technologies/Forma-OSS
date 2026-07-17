from __future__ import annotations

import asyncio
import tempfile
import unittest

from backend.job_store import JobMetadataStore
from blueprint_core.llm_providers import StructuredLLMProvider
from blueprint_core.models import GenerateProjectRequest
from pydantic import BaseModel


class AsyncWrapperResult(BaseModel):
    value: str


class FakeStructuredProvider(StructuredLLMProvider):
    def generate_structured(self, prompt, schema_class, image_bytes=None, image_mime_type=None):
        return schema_class(value=prompt)


class JobProgressTests(unittest.TestCase):
    def test_sqlite_job_store_persists_progress_events(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db") as file:
            store = JobMetadataStore(file.name, backend="sqlite")
            store.create_job(
                job_id="job_frontend_progress",
                message_id="msg_frontend_progress",
                correlation_id=None,
                action="blueprint.generate_project",
                sender="frontend",
                recipient="blueprint",
                payload={"prompt": "blink an LED", "workflow": "default"},
                server_owned=True,
            )

            store.append_progress_event(
                "job_frontend_progress",
                {
                    "workflow": "default",
                    "step_id": "intent_parser",
                    "status": "started",
                    "agent": "Intent Parser Agent",
                    "label": "Parsing the hardware idea",
                    "description": "Converting the prompt into a project title, category, and build intent.",
                },
            )
            job = store.get_job("job_frontend_progress")

        self.assertIsNotNone(job)
        assert job is not None
        self.assertEqual(1, len(job["progress_events"]))
        self.assertEqual("intent_parser", job["progress_events"][0]["step_id"])
        self.assertIn("observed_at", job["progress_events"][0])

    def test_generate_request_accepts_safe_client_job_id(self) -> None:
        request = GenerateProjectRequest(prompt="blink", client_job_id="job_frontend_abc-123")

        self.assertEqual("job_frontend_abc-123", request.client_job_id)

    def test_generate_request_accepts_external_source_provider(self) -> None:
        request = GenerateProjectRequest(prompt="blink", workflow="web_research", external_source_provider="Firecrawl")

        self.assertEqual("firecrawl", request.external_source_provider)

    def test_generate_request_accepts_async_generation_flag(self) -> None:
        request = GenerateProjectRequest(prompt="blink", async_generation=True)

        self.assertTrue(request.async_generation)

    def test_structured_provider_async_wrapper_returns_result(self) -> None:
        provider = FakeStructuredProvider()

        result = asyncio.run(provider.generate_structured_async("blink", AsyncWrapperResult))

        self.assertEqual("blink", result.value)

    def test_generate_request_maps_legacy_external_source_provider_to_firecrawl(self) -> None:
        request = GenerateProjectRequest(prompt="blink", workflow="web_research", external_source_provider="auto")

        self.assertEqual("firecrawl", request.external_source_provider)

    def test_generate_request_rejects_unknown_external_source_provider(self) -> None:
        with self.assertRaises(ValueError):
            GenerateProjectRequest(prompt="blink", workflow="web_research", external_source_provider="duckduckgo")

    def test_generate_request_rejects_unsafe_client_job_id(self) -> None:
        with self.assertRaises(ValueError):
            GenerateProjectRequest(prompt="blink", client_job_id="../bad")


if __name__ == "__main__":
    unittest.main()
