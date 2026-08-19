from __future__ import annotations

import unittest
from unittest.mock import patch

from forma_core import FormaClient
from forma_core.design_generation import (
    DesignGenerationState,
    GenerationCompleteness,
    GenerationPhase,
    GenerationStatus,
    InMemoryDesignGenerationRepository,
    MachineIntent,
    ProjectGenerationResult,
)
from forma_core.workspaces.projects.models import HardwareIR, ProjectOverview


class FakeClientGenerationEngine:
    def __init__(self) -> None:
        self.repository = InMemoryDesignGenerationRepository()
        self.prompts: list[str] = []

    def create_machine_intent(self, *, project_id, prompt) -> MachineIntent:
        self.prompts.append(prompt)
        self.repository.initialize_project(project_id)
        intent = MachineIntent(
            intent_id="intent-client",
            project_id=project_id,
            source_prompt=prompt,
            purpose="Desktop environmental monitor",
            required_capabilities=["sense", "display"],
        )
        self.repository.save_intent(intent)
        return intent

    def start(
        self, *, project_id, intent_id, run_id, options
    ) -> ProjectGenerationResult:
        completeness = GenerationCompleteness(
            required_obligation_count=2,
            resolved_obligation_count=2,
            valid_bom_line_count=3,
            physical_component_count=3,
        )
        self.repository.save_state(
            DesignGenerationState(
                run_id=run_id,
                project_id=project_id,
                intent_id=intent_id,
                phase=GenerationPhase.COMPLETE,
                status=GenerationStatus.COMPLETE,
                completeness=completeness,
            )
        )
        return ProjectGenerationResult(
            run_id=run_id,
            project_id=project_id,
            status=GenerationStatus.COMPLETE,
            project=HardwareIR(
                overview=ProjectOverview(
                    title="Desktop environmental monitor",
                    description="ESP32 environmental monitor",
                    difficulty="Intermediate",
                    category="IoT",
                )
            ),
            completeness=completeness,
        )


class FormaClientTests(unittest.TestCase):
    def test_documented_from_config_generation_flow_is_valid(self) -> None:
        engine = FakeClientGenerationEngine()
        with patch("forma_core.client._configured_engine_factory", return_value=engine):
            client = FormaClient.from_config()
            try:
                run = client.projects.start_generation(
                    prompt=(
                        "Design a compact desktop environmental monitor using an ESP32, "
                        "a temperature and humidity sensor, an OLED, and USB-C power."
                    ),
                )
                result = run.wait()
            finally:
                client.close()

        self.assertEqual(GenerationStatus.COMPLETE, result.status)
        self.assertEqual(3, result.completeness.valid_bom_line_count)
        self.assertEqual(2, result.completeness.resolved_obligation_count)
        self.assertIsNotNone(result.project)
        self.assertIn("ESP32", engine.prompts[0])
        self.assertIsNotNone(engine.repository.get_intent(run.project_id))

    def test_legacy_strategy_uses_only_the_legacy_runner(self) -> None:
        calls: list[str] = []

        def legacy(prompt, _options):
            calls.append(prompt)
            return HardwareIR(
                overview=ProjectOverview(
                    title="Legacy monitor",
                    description="Legacy path",
                    difficulty="Intermediate",
                    category="IoT",
                )
            )

        def forbidden_engine(_options):
            raise AssertionError("intent-first engine must not be built")

        client = FormaClient(engine_factory=forbidden_engine, legacy_runner=legacy)
        try:
            result = client.projects.start_generation(
                prompt="legacy request", strategy="legacy"
            ).wait(timeout=2)
        finally:
            client.close()

        self.assertEqual(["legacy request"], calls)
        self.assertEqual(GenerationStatus.COMPLETE, result.status)


if __name__ == "__main__":
    unittest.main()
