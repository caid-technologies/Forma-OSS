from __future__ import annotations

import tempfile
import unittest

from backend.job_store import JobMetadataStore
from blueprint_core.models import GenerateProjectRequest


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
        self.assertEqual("ongoing", job["runtime"]["state"])
        self.assertTrue(job["runtime"]["ongoing"])
        self.assertFalse(job["runtime"]["terminal"])
        self.assertEqual("Intent Parser Agent", job["runtime"]["current_agent"])
        self.assertIn("Intent Parser Agent is working on", job["agent_thinking"])

    def test_sqlite_job_runtime_reports_provider_thinking_for_running_job(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db") as file:
            store = JobMetadataStore(file.name, backend="sqlite")
            store.create_job(
                job_id="job_frontend_provider_progress",
                message_id="msg_frontend_provider_progress",
                correlation_id=None,
                action="blueprint.generate_project",
                sender="frontend",
                recipient="blueprint",
                payload={"prompt": "blink an LED", "workflow": "default"},
                server_owned=True,
            )
            store.mark_running("job_frontend_provider_progress")
            store.append_progress_event(
                "job_frontend_provider_progress",
                {
                    "workflow": "default",
                    "step_id": "wiring_netlist",
                    "status": "provider_request_started",
                    "agent": "Wiring/Netlist Agent",
                    "label": "Drafting nets and pin mappings",
                    "description": "Connecting components.",
                    "details": {
                        "provider": "fake-provider",
                        "model": "fake-model",
                        "schema": "WiringWrapper",
                    },
                },
            )

            job = store.get_job("job_frontend_provider_progress")

        self.assertIsNotNone(job)
        assert job is not None
        self.assertEqual("running", job["status"])
        self.assertEqual("ongoing", job["runtime"]["outcome"])
        self.assertEqual("wiring_netlist", job["runtime"]["current_step_id"])
        self.assertEqual("provider_request_started", job["runtime"]["current_status"])
        self.assertIn("Wiring/Netlist Agent is waiting", job["runtime"]["thinking"]["summary"])
        self.assertIn("fake-provider/fake-model", job["runtime"]["thinking"]["summary"])

    def test_sqlite_job_runtime_prefers_agent_note_as_thinking_summary(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db") as file:
            store = JobMetadataStore(file.name, backend="sqlite")
            store.create_job(
                job_id="job_frontend_agent_note",
                message_id="msg_frontend_agent_note",
                correlation_id=None,
                action="blueprint.generate_project",
                sender="frontend",
                recipient="blueprint",
                payload={"prompt": "blink an LED", "workflow": "default"},
                server_owned=True,
            )
            store.mark_running("job_frontend_agent_note")
            store.append_progress_event(
                "job_frontend_agent_note",
                {
                    "workflow": "default",
                    "step_id": "component_selection",
                    "status": "agent_note",
                    "agent": "Component Selection Agent",
                    "label": "Selecting compatible parts",
                    "description": "Choosing catalog components.",
                    "details": {
                        "note": "I am comparing the requirements against the component catalog.",
                    },
                },
            )

            job = store.get_job("job_frontend_agent_note")

        self.assertIsNotNone(job)
        assert job is not None
        self.assertEqual(
            "I am comparing the requirements against the component catalog.",
            job["runtime"]["thinking"]["summary"],
        )
        self.assertEqual(job["runtime"]["thinking"]["summary"], job["agent_thinking"])

    def test_sqlite_job_runtime_reports_firecrawl_source_relevance(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db") as file:
            store = JobMetadataStore(file.name, backend="sqlite")
            store.create_job(
                job_id="job_firecrawl_source",
                message_id="msg_firecrawl_source",
                correlation_id=None,
                action="blueprint.generate_project",
                sender="frontend",
                recipient="blueprint",
                payload={"prompt": "water sensor", "workflow": "web_research", "external_source_provider": "firecrawl"},
                server_owned=True,
            )
            store.mark_running("job_firecrawl_source")
            store.append_progress_event(
                "job_firecrawl_source",
                {
                    "workflow": "web_research",
                    "step_id": "external_research",
                    "status": "source_found",
                    "agent": "External Source Research Agent",
                    "label": "Gathering source context",
                    "description": "Searching for reference designs.",
                    "details": {
                        "provider": "firecrawl",
                        "title": "Water sensor reference",
                        "url": "https://example.com/water-sensor",
                        "domain": "example.com",
                        "relevance_reason": "Matched search terms: water, sensor. Source domain: example.com.",
                    },
                },
            )

            job = store.get_job("job_firecrawl_source")

        self.assertIsNotNone(job)
        assert job is not None
        self.assertIn("Water sensor reference", job["agent_thinking"])
        self.assertIn("Matched search terms", job["agent_thinking"])

    def test_sqlite_job_runtime_reports_success_and_failure_outcomes(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db") as file:
            store = JobMetadataStore(file.name, backend="sqlite")
            store.create_job(
                job_id="job_success",
                message_id="msg_success",
                correlation_id=None,
                action="blueprint.generate_project",
                sender="frontend",
                recipient="blueprint",
                payload={"prompt": "blink an LED", "workflow": "default"},
                server_owned=True,
            )
            store.mark_succeeded("job_success", {"ok": True})

            store.create_job(
                job_id="job_failure",
                message_id="msg_failure",
                correlation_id=None,
                action="blueprint.generate_project",
                sender="frontend",
                recipient="blueprint",
                payload={"prompt": "blink an LED", "workflow": "default"},
                server_owned=True,
            )
            store.mark_failed("job_failure", "provider exploded")

            success = store.get_job("job_success")
            failure = store.get_job("job_failure")

        self.assertIsNotNone(success)
        self.assertIsNotNone(failure)
        assert success is not None
        assert failure is not None
        self.assertEqual("successful", success["runtime"]["outcome"])
        self.assertTrue(success["runtime"]["successful"])
        self.assertTrue(success["runtime"]["terminal"])
        self.assertEqual("failed", failure["runtime"]["outcome"])
        self.assertTrue(failure["runtime"]["failed"])
        self.assertTrue(failure["runtime"]["terminal"])
        self.assertIn("provider exploded", failure["runtime"]["thinking"]["summary"])

    def test_generate_request_accepts_safe_client_job_id(self) -> None:
        request = GenerateProjectRequest(prompt="blink", client_job_id="job_frontend_abc-123")

        self.assertEqual("job_frontend_abc-123", request.client_job_id)

    def test_generate_request_accepts_external_source_provider(self) -> None:
        request = GenerateProjectRequest(prompt="blink", workflow="web_research", external_source_provider="Firecrawl")

        self.assertEqual("firecrawl", request.external_source_provider)

    def test_generate_request_accepts_tavily_external_source_provider(self) -> None:
        request = GenerateProjectRequest(prompt="blink", workflow="web_research", external_source_provider="Tavily")

        self.assertEqual("tavily", request.external_source_provider)

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
