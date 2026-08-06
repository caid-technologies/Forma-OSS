from __future__ import annotations

import unittest

from blueprint_core.agents.system_architecture import (
    build_default_system_architecture,
    compact_component_catalog,
    compact_component_context,
    compact_net_context,
    find_system_node,
    hydrate_catalog_components,
    system_context,
)
from blueprint_core.workspaces.projects.models import (
    ComponentInstance,
    ConnectionNet,
    FunctionalRequirements,
    PinReference,
    ProjectOverview,
    SystemArchitecture,
)
from blueprint_core.workspaces.projects.objects import namespace_payload


class SystemArchitectureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.overview = ProjectOverview(
            title="Desk Monitor",
            description="A compact environmental monitor.",
            difficulty="Beginner",
            category="IoT",
        )
        self.requirements = FunctionalRequirements(
            requirements=["Measure room temperature", "Display a warning"],
            power_needs="USB-C 5 V input with regulated 3.3 V logic",
            operating_voltage=3.3,
            physical_constraints=["Desktop enclosure under 100 mm wide"],
        )

    def test_default_tree_separates_disciplines_and_explains_power(self) -> None:
        architecture = build_default_system_architecture(self.overview, self.requirements)

        self.assertEqual("product", architecture.root.system_id)
        self.assertIsNotNone(find_system_node(architecture, "electrical"))
        self.assertIsNotNone(find_system_node(architecture, "mechanical"))
        power = find_system_node(architecture, "electrical.power")
        self.assertIsNotNone(power)
        assert power is not None
        self.assertIn("energy", power.purpose.lower())
        self.assertEqual("power/electrical agent", power.detail_owner)

    def test_branch_projection_excludes_sibling_systems(self) -> None:
        architecture = build_default_system_architecture(self.overview, self.requirements)

        context = system_context(architecture, "mechanical")

        self.assertEqual("mechanical", context["system"]["system_id"])
        self.assertNotIn("electrical.power", str(context))

    def test_compact_context_hides_pins_but_hydration_restores_them(self) -> None:
        pin = {"pin_id": "3V3", "name": "3.3 V", "pin_type": "Power", "voltage": 3.3}
        catalog = [
            {
                "part_number": "MCU-1",
                "name": "Controller",
                "category": "Microcontroller",
                "description": "Controller board",
                "price": 4.5,
                "pins": [pin],
                "use_cases": ["control"],
            }
        ]
        selected = ComponentInstance(
            ref_des="U1",
            part_number="MCU-1",
            name="placeholder",
            category="placeholder",
            rationale="Runs the product.",
            pins=[],
        )

        compact_catalog = compact_component_catalog(catalog)
        hydrated = hydrate_catalog_components([selected], catalog)
        compact_components = compact_component_context(hydrated)

        self.assertNotIn("pins", compact_catalog[0])
        self.assertEqual(["Power"], compact_catalog[0]["available_interfaces"])
        self.assertEqual("3V3", hydrated[0].pins[0].pin_id)
        self.assertNotIn("pins", compact_components[0])

    def test_compact_net_context_keeps_components_not_pin_ids(self) -> None:
        net = ConnectionNet(
            net_id="NET_3V3",
            name="Logic Rail",
            net_type="Power",
            voltage=3.3,
            pins=[PinReference(ref_des="U1", pin_id="3V3"), PinReference(ref_des="S1", pin_id="VCC")],
        )

        compact = compact_net_context([net])

        self.assertEqual(["U1", "S1"], compact[0]["component_refs"])
        self.assertNotIn("pin_id", compact[0])
        self.assertNotIn("VCC", str(compact))

    def test_architecture_has_a_project_namespace(self) -> None:
        architecture = build_default_system_architecture(self.overview, self.requirements)
        payload = namespace_payload(
            {
                "overview": self.overview.model_dump(),
                "requirements": self.requirements.model_dump(),
                "system_architecture": architecture.model_dump(),
            },
            "product.architecture",
        )

        self.assertEqual("product", payload["system_architecture"]["root"]["system_id"])

    def test_dotted_id_shorthand_is_normalized_into_typed_architecture_objects(self) -> None:
        architecture = SystemArchitecture.model_validate({
            "summary": "A compact system tree.",
            "root": {
                "system_id": "product",
                "name": "Product",
                "domain": "product",
                "purpose": "Coordinates the complete product.",
                "interfaces": ["mechanical.enclosure"],
                "children": ["electrical.power", "firmware.control_logic"],
            },
        })

        self.assertEqual("mechanical.enclosure", architecture.root.interfaces[0].connects_to)
        self.assertEqual("Mechanical Enclosure interface", architecture.root.interfaces[0].name)
        self.assertEqual(["electrical.power", "firmware.control_logic"], [
            child.system_id for child in architecture.root.children
        ])
        self.assertEqual(["electrical", "firmware"], [child.domain for child in architecture.root.children])


if __name__ == "__main__":
    unittest.main()
