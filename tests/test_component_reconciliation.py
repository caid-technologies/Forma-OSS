from __future__ import annotations

import unittest

from blueprint_core.agents.component_reconciliation import reconcile_explicit_catalog_components
from blueprint_core.workspaces.projects.models import ComponentInstance


class ComponentReconciliationTests(unittest.TestCase):
    def test_restores_an_explicitly_requested_catalog_part(self) -> None:
        selected = [
            ComponentInstance(
                ref_des="U1",
                part_number="ESP32-WROOM-32D",
                name="ESP32",
                category="Microcontroller",
                rationale="Controller",
            )
        ]
        catalog = [
            {
                "part_number": "Resistor-10k",
                "name": "10k Ohm Metal Film Resistor",
                "category": "Passives",
                "price": 0.05,
                "pins": [],
            },
            {
                "part_number": "Resistor-220R",
                "name": "220 Ohm Resistor",
                "category": "Passives",
                "price": 0.05,
                "pins": [],
            },
            {
                "part_number": "LED-Red-Generic",
                "name": "Standard Red LED",
                "category": "Passives",
                "price": 0.05,
                "pins": [],
            },
            {
                "part_number": "USB-5V-Plug",
                "name": "5V USB Wall Power Supply",
                "category": "Power",
                "price": 5.0,
                "pins": [],
            },
            {
                "part_number": "Relay-5V-1Ch",
                "name": "Relay",
                "category": "Actuator",
                "price": 3.0,
                "pins": [],
            },
        ]

        components, added = reconcile_explicit_catalog_components(
            "Use an ESP32, a red LED with a 220-ohm resistor, a 10k pull-up resistor, and 5V USB power.",
            selected,
            catalog,
        )

        self.assertEqual(
            ["Resistor-10k", "Resistor-220R", "LED-Red-Generic", "USB-5V-Plug"],
            added,
        )
        self.assertEqual(
            ["R1", "R2", "LED1", "PWR1"],
            [component.ref_des for component in components[1:]],
        )

    def test_does_not_guess_unmentioned_parts(self) -> None:
        components, added = reconcile_explicit_catalog_components(
            "Use an ESP32.",
            [],
            [{"part_number": "Relay-5V-1Ch", "name": "Relay", "category": "Actuator"}],
        )

        self.assertEqual([], components)
        self.assertEqual([], added)


if __name__ == "__main__":
    unittest.main()
