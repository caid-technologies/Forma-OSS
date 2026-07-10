from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import unittest


ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]


def run_module(module_name: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", module_name, *args],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        check=True,
    )


class FabricatorCliTests(unittest.TestCase):
    def test_fabricator_default_plan_outputs_structured_json(self) -> None:
        completed = run_module(
            "fabricator",
            "--material",
            "alumina ceramic powder",
            "--amount",
            "2 kg",
            "--available-equipment",
            "inventory database, furnace, microscope",
        )

        payload = json.loads(completed.stdout)

        self.assertEqual("local", payload["mode"])
        self.assertIn("fabricator_plan", payload)
        self.assertEqual("lattice.run_record", payload["lattice_run"]["record_type"])
        self.assertEqual("fabricator.plan.v0", payload["lattice_run"]["contract_id"])
        workflow = payload["fabricator_plan"]["candidate_workflows"][0]
        self.assertEqual("functional material formulations", workflow["product_family"])
        self.assertEqual("fabricator-initialize", payload["fabricator_plan"]["blueprint_mcp_handoff"][0]["id"])

    def test_fabricator_prompt_command_uses_correct_name(self) -> None:
        completed = run_module("fabricator", "prompt", "--material", "cellulose acetate offcuts")

        self.assertIn("You are Fabricator", completed.stdout)
        self.assertNotIn("Fibricator", completed.stdout)

    def test_fabricator_root_help_lists_subcommands(self) -> None:
        completed = run_module("fabricator", "--help")

        self.assertIn("plan", completed.stdout)
        self.assertIn("prompt", completed.stdout)
        self.assertIn("mcp-tools", completed.stdout)
        self.assertIn("card", completed.stdout)

    def test_fabricator_card_command_outputs_lattice_agent_card(self) -> None:
        completed = run_module("fabricator", "card")

        payload = json.loads(completed.stdout)

        self.assertEqual("lattice.agent_card", payload["card_type"])
        self.assertEqual("fabricator", payload["agent_id"])
        self.assertEqual("product.fabricator", payload["namespace"])
        self.assertEqual("fabricator.plan.v0", payload["contracts"][0]["id"])
        self.assertIn("Primitive-to-product planning", [item["label"] for item in payload["capabilities"]])

    def test_fibricator_shim_still_runs(self) -> None:
        completed = run_module("fibricator", "prompt", "--material", "cellulose acetate offcuts")

        self.assertIn("You are Fabricator", completed.stdout)

    def test_fabricator_package_exports_schemas(self) -> None:
        import fabricator

        self.assertIs(fabricator.FabricatorPlan, fabricator.FibricatorPlan)
        self.assertTrue(callable(fabricator.main))


if __name__ == "__main__":
    unittest.main()
