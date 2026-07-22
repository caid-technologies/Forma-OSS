from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from blueprint_core.agents.orchestrator import HardwarePipelineOrchestrator
from blueprint_core.pipeline import (
    PipelineCancelledError,
    agent_pipeline_step,
    ensure_agent_pipeline_active,
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

    def test_optional_image_step_is_explicitly_included(self) -> None:
        steps = list_agent_pipeline_steps("default", include_image=True)

        self.assertEqual("image_generation", steps[-1]["id"])
        self.assertTrue(steps[-1]["optional"])

    def test_pipeline_cancellation_check_blocks_persistence_work(self) -> None:
        with observe_agent_pipeline(lambda event: None, cancellation_check=lambda: True):
            with self.assertRaises(PipelineCancelledError):
                ensure_agent_pipeline_active()

    def test_cancelled_live_pipeline_does_not_enter_simulation_fallback(self) -> None:
        orchestrator = HardwarePipelineOrchestrator.__new__(HardwarePipelineOrchestrator)
        orchestrator._active_generation_metadata = {}
        orchestrator.use_simulation = False
        orchestrator.llm_provider = SimpleNamespace(provider_name="anthropic", model_name="claude-sonnet-5")
        orchestrator.runtime_config = SimpleNamespace(
            provider="anthropic",
            model="claude-sonnet-5",
            requested_provider="anthropic",
            requested_model="claude-sonnet-5",
            provider_overridden=False,
            model_overridden=False,
        )
        orchestrator.validate_configured_model = Mock(
            return_value=SimpleNamespace(provider="anthropic", actual_model="claude-sonnet-5")
        )
        orchestrator._call_llm_structured = Mock(side_effect=PipelineCancelledError("cancelled"))
        orchestrator._generate_simulated_project = Mock()

        with self.assertRaises(PipelineCancelledError):
            orchestrator.generate_project("environment monitor")

        orchestrator._generate_simulated_project.assert_not_called()

    def test_unknown_workflow_falls_back_to_default(self) -> None:
        self.assertEqual("default", pipeline_workflow_id("does-not-exist"))


if __name__ == "__main__":
    unittest.main()
