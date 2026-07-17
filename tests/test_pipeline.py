from __future__ import annotations

import unittest

from blueprint_core.pipeline import (
    agent_pipeline_step,
    external_source_response_status,
    list_agent_pipeline_steps,
    observe_agent_pipeline,
    pipeline_workflow_id,
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

    def test_recoverable_external_source_error_is_not_failed_status(self) -> None:
        self.assertEqual("provider_response_received", external_source_response_status(None))
        self.assertEqual("provider_response_unavailable", external_source_response_status("Firecrawl timed out."))

    def test_optional_image_step_is_explicitly_included(self) -> None:
        steps = list_agent_pipeline_steps("default", include_image=True)

        self.assertEqual("image_generation", steps[-1]["id"])
        self.assertTrue(steps[-1]["optional"])

    def test_unknown_workflow_falls_back_to_default(self) -> None:
        self.assertEqual("default", pipeline_workflow_id("does-not-exist"))


if __name__ == "__main__":
    unittest.main()
