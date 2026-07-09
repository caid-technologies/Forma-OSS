from __future__ import annotations

import unittest

from blueprint_core.clarifying_questions import ContextClarifierAgent
from blueprint_core.models import ClarifyingQuestionsRequest


class ContextClarifierAgentTests(unittest.TestCase):
    def test_sensor_prompt_gets_controller_power_output_questions(self) -> None:
        response = ContextClarifierAgent().ask(
            ClarifyingQuestionsRequest(prompt="Build an ESP32 sensor node with a display")
        )

        self.assertTrue(response.should_ask)
        self.assertEqual("Context Clarifier Agent", response.agent)
        self.assertEqual(["controller_modules", "power", "outputs"], [question.id for question in response.questions])

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
