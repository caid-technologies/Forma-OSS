from __future__ import annotations

import unittest
from types import SimpleNamespace

from pydantic import BaseModel

from blueprint_core.agents.orchestrator import HardwarePipelineOrchestrator
from blueprint_core.agents.web_research_workflow import WebResearchHardwarePipeline
from blueprint_core.external_sources import ExternalSourceLibrary, ExternalSourceRecord
from blueprint_core.pipeline import (
    agent_pipeline_step,
    current_agent_pipeline_step_id,
    list_agent_pipeline_steps,
    observe_agent_pipeline,
    pipeline_workflow_id,
)


class TinyStructuredResponse(BaseModel):
    value: str


class FakeStructuredProvider:
    provider_name = "fake-provider"
    model_name = "fake-model"

    def generate_structured(self, prompt, schema_class, image_bytes=None, image_mime_type=None):
        return schema_class(value="ok")


class FakeResearchClient:
    provider_name = "firecrawl"
    config = SimpleNamespace(timeout_seconds=12)

    def research(self, queries):
        return ExternalSourceLibrary(
            provider="firecrawl",
            configured=True,
            searches_attempted=len(list(queries)),
            sources=[
                ExternalSourceRecord(
                    title="Sensor source",
                    url="https://example.com/sensor",
                    content="I2C sensor module reference.",
                    provider="firecrawl",
                    metadata={
                        "domain": "example.com",
                        "relevance_reason": "Matched search terms: sensor. Source domain: example.com.",
                        "matched_query_terms": ["sensor"],
                    },
                )
            ],
        )


class PipelineMetadataTests(unittest.TestCase):
    def test_default_pipeline_exposes_public_agent_steps(self) -> None:
        steps = list_agent_pipeline_steps("default")

        self.assertGreaterEqual(len(steps), 7)
        self.assertEqual("safety_guardrail", steps[0]["id"])
        self.assertEqual("context_clarifier", steps[1]["id"])
        self.assertTrue(any(step["agent"] == "Wiring/Netlist Agent" for step in steps))
        self.assertTrue(all("description" in step for step in steps))

    def test_web_research_pipeline_exposes_research_steps(self) -> None:
        steps = list_agent_pipeline_steps("web_research")

        self.assertTrue(any(step["id"] == "external_research" for step in steps))
        self.assertTrue(any(step["id"] == "completeness_audit" for step in steps))
        self.assertTrue(any(step["id"] == "context_clarifier" for step in steps))

    def test_websearch_alias_exposes_research_steps(self) -> None:
        self.assertEqual("web_research", pipeline_workflow_id("websearch"))
        steps = list_agent_pipeline_steps("websearch")

        self.assertTrue(any(step["id"] == "external_research" for step in steps))
        self.assertTrue(any(step["id"] == "completeness_audit" for step in steps))

    def test_pipeline_step_observer_emits_core_metadata_events(self) -> None:
        events = []

        with observe_agent_pipeline(events.append):
            with agent_pipeline_step("websearch", "external_research", details={"query_count": 3}):
                pass

        self.assertEqual(["started", "completed"], [event.status for event in events])
        self.assertEqual("web_research", events[0].workflow)
        self.assertEqual("external_research", events[0].step_id)
        self.assertEqual("External Source Research Agent", events[0].agent)
        self.assertEqual({"query_count": 3}, events[0].details)
        self.assertIn("duration_ms", events[1].details)
        self.assertGreaterEqual(events[1].details["duration_ms"], 0)

    def test_pipeline_step_exposes_current_step_context(self) -> None:
        observed_step_ids = []

        self.assertIsNone(current_agent_pipeline_step_id())
        with agent_pipeline_step("default", "requirements"):
            observed_step_ids.append(current_agent_pipeline_step_id())

        self.assertEqual(["requirements"], observed_step_ids)
        self.assertIsNone(current_agent_pipeline_step_id())

    def test_default_orchestrator_llm_call_emits_provider_progress_events(self) -> None:
        orchestrator = HardwarePipelineOrchestrator.__new__(HardwarePipelineOrchestrator)
        orchestrator.use_simulation = False
        orchestrator.llm_provider = FakeStructuredProvider()
        orchestrator.runtime_config = SimpleNamespace(
            provider="fake-runtime",
            model="fake-runtime-model",
            requested_provider=None,
            requested_model=None,
        )
        orchestrator.model_name = "fake-model"
        events = []

        with observe_agent_pipeline(events.append):
            with agent_pipeline_step("default", "requirements"):
                result = orchestrator._call_llm_structured("hello", TinyStructuredResponse)

        self.assertEqual("ok", result.value)
        statuses = [event.status for event in events]
        self.assertEqual(
            ["started", "agent_note", "provider_request_started", "provider_response_received", "completed"],
            statuses,
        )
        note_event = events[1]
        self.assertEqual("requirements", note_event.step_id)
        self.assertIn("extracting operating needs", note_event.details["note"])
        provider_event = events[2]
        self.assertEqual("requirements", provider_event.step_id)
        self.assertEqual("TinyStructuredResponse", provider_event.details["schema"])
        self.assertEqual("fake-provider", provider_event.details["provider"])

    def test_web_research_emits_firecrawl_source_progress_events(self) -> None:
        workflow = WebResearchHardwarePipeline.__new__(WebResearchHardwarePipeline)
        workflow.research_client = FakeResearchClient()
        events = []

        with observe_agent_pipeline(events.append):
            research = workflow._research(["sensor module reference"])

        self.assertEqual(1, len(research.sources))
        statuses = [event.status for event in events]
        self.assertIn("agent_note", statuses)
        self.assertIn("source_found", statuses)
        source_event = next(event for event in events if event.status == "source_found")
        self.assertEqual("https://example.com/sensor", source_event.details["url"])
        self.assertEqual("example.com", source_event.details["domain"])
        self.assertIn("Matched search terms", source_event.details["relevance_reason"])

    def test_optional_image_step_is_explicitly_included(self) -> None:
        steps = list_agent_pipeline_steps("default", include_image=True)

        self.assertEqual("image_generation", steps[-1]["id"])
        self.assertTrue(steps[-1]["optional"])

    def test_unknown_workflow_falls_back_to_default(self) -> None:
        self.assertEqual("default", pipeline_workflow_id("does-not-exist"))


if __name__ == "__main__":
    unittest.main()
