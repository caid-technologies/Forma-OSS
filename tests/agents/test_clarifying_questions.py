from __future__ import annotations

import unittest

from forma_core.agents.clarification import ContextClarifierAgent
from forma_core.workspaces.projects.models import ClarifyingQuestionsRequest


class ContextClarifierAgentTests(unittest.TestCase):
    def test_sensor_prompt_gets_controller_shape_and_power_questions(self) -> None:
        response = ContextClarifierAgent().ask(
            ClarifyingQuestionsRequest(prompt="Build an ESP32 sensor node with a display")
        )

        self.assertTrue(response.should_ask)
        self.assertEqual("Context Clarifier Agent", response.agent)
        self.assertEqual(["controller_modules", "physical_form", "power"], [question.id for question in response.questions])
        shape_question = response.questions[1]
        self.assertIn("shape", shape_question.question.lower())
        self.assertIn("Open frame", shape_question.suggestions)

    def test_every_project_domain_asks_about_physical_form(self) -> None:
        prompts = [
            "Build a microfluidic water assay cartridge",
            "Build a self-deploying field tent",
            "Build an ESP32 sensor node",
            "Build a useful desk tool",
        ]

        for prompt in prompts:
            with self.subTest(prompt=prompt):
                response = ContextClarifierAgent().ask(ClarifyingQuestionsRequest(prompt=prompt, force=True))
                self.assertIn("physical_form", [question.id for question in response.questions])

    def test_reference_image_shape_question_mentions_preserving_silhouette(self) -> None:
        response = ContextClarifierAgent().ask(
            ClarifyingQuestionsRequest(prompt="", has_image=True, force=True)
        )

        shape_question = next(question for question in response.questions if question.id == "physical_form")
        self.assertIn("preserve the reference silhouette", shape_question.placeholder.lower())

    def test_existing_human_context_skips_questions(self) -> None:
        response = ContextClarifierAgent().ask(
            ClarifyingQuestionsRequest(
                prompt="Build a sensor node\n\nHUMAN-IN-THE-LOOP CONTEXT:\n- Power: USB-C 5V"
            )
        )

        self.assertFalse(response.should_ask)
        self.assertEqual([], response.questions)

    def test_user_can_skip_questions(self) -> None:
        response = ContextClarifierAgent().ask(
            ClarifyingQuestionsRequest(prompt="Build a plant monitor, do not ask questions")
        )

        self.assertFalse(response.should_ask)
        self.assertIn("skip", response.reason.lower())


if __name__ == "__main__":
    unittest.main()
