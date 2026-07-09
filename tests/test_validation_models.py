from __future__ import annotations

import unittest

from blueprint_core.models import (
    ComponentInstance,
    ConnectionNet,
    GenerateProjectRequest,
    IterateProjectRequest,
    PinDefinition,
    PinReference,
)
from blueprint_core.validation import validate_circuit


class ValidationAndModelTests(unittest.TestCase):
    def test_generation_request_strips_optional_runtime_selector_fields(self) -> None:
        request = GenerateProjectRequest(
            prompt="plant watering monitor",
            provider=" openai ",
            model=" gpt-5.5 ",
            chat_id=" chat-123 ",
            source_project_id=" source-456 ",
        )

        self.assertEqual("openai", request.provider)
        self.assertEqual("gpt-5.5", request.model)
        self.assertEqual("chat-123", request.chat_id)
        self.assertEqual("source-456", request.source_project_id)

    def test_iteration_request_strips_optional_runtime_selector_fields(self) -> None:
        request = IterateProjectRequest(
            instruction="  add battery charging  ",
            namespace=" Product.Mech ",
            provider=" openai ",
            model=" gpt-5.5 ",
        )

        self.assertEqual("add battery charging", request.instruction)
        self.assertEqual("Product.Mech", request.namespace)
        self.assertEqual("openai", request.provider)
        self.assertEqual("gpt-5.5", request.model)

    def test_validate_circuit_flags_power_to_ground_short(self) -> None:
        components = [
            ComponentInstance(
                ref_des="U1",
                part_number="MCU",
                name="Microcontroller",
                category="Microcontroller",
                rationale="Controller",
                pins=[
                    PinDefinition(pin_id="3V3", name="3.3V", pin_type="Power", voltage=3.3),
                    PinDefinition(pin_id="GND", name="Ground", pin_type="Ground", voltage=0.0),
                ],
            )
        ]
        nets = [
            ConnectionNet(
                net_id="NET_SHORT",
                name="Accidental short",
                net_type="Power",
                voltage=3.3,
                pins=[
                    PinReference(ref_des="U1", pin_id="3V3"),
                    PinReference(ref_des="U1", pin_id="GND"),
                ],
            )
        ]

        issues = validate_circuit(components, nets)

        self.assertTrue(any(issue.severity == "CRITICAL" for issue in issues))
        self.assertTrue(any(issue.category == "Short Circuit" for issue in issues))


if __name__ == "__main__":
    unittest.main()
