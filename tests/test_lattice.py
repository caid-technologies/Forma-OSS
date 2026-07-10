from __future__ import annotations

import unittest

from blueprint_core.lattice import (
    LatticeRegistry,
    LatticeRunRecord,
    LatticeSchemaContract,
)
from blueprint_core.lattice_agents import default_namespace_agent_cards, namespace_contract_id
from fabricator import (
    FabricatorPlan,
    FabricatorQuestion,
    fabricator_lattice_card,
)


class LatticeTests(unittest.TestCase):
    def test_schema_contract_can_be_declared_from_pydantic_models(self) -> None:
        contract = LatticeSchemaContract.from_models(
            id="test.fabricator.plan",
            name="Test Fabricator Plan",
            purpose="Exercise Lattice schema generation.",
            input_model=FabricatorQuestion,
            output_model=FabricatorPlan,
        )

        self.assertEqual("declared", contract.schema_kind)
        self.assertEqual("FabricatorQuestion", contract.input_schema["title"])
        self.assertEqual("FabricatorPlan", contract.output_schema["title"])

    def test_registry_can_find_fabricator_by_domain_and_capability(self) -> None:
        registry = LatticeRegistry([fabricator_lattice_card()])

        by_namespace = registry.find(namespace="product.fabricator")
        by_domain = registry.find(domain="fabrication")
        by_capability = registry.find(capability="primitive")

        self.assertEqual(["fabricator"], [card.agent_id for card in by_namespace])
        self.assertEqual(["fabricator"], [card.agent_id for card in by_domain])
        self.assertEqual(["fabricator"], [card.agent_id for card in by_capability])
        self.assertEqual("Lattice", registry.manifest()["name"])

    def test_blueprint_project_namespaces_are_lattice_agents(self) -> None:
        registry = LatticeRegistry(default_namespace_agent_cards())

        mech = registry.get("product.mech")
        bom = registry.get("product.bom")

        self.assertEqual("product.mech", mech.namespace)
        self.assertEqual("product.bom", bom.namespace)
        self.assertEqual(namespace_contract_id("product.mech"), mech.contracts[0].id)
        self.assertEqual(["product.bom"], [card.agent_id for card in registry.find(namespace="product.bom")])

    def test_run_record_links_action_to_card_and_contract(self) -> None:
        card = fabricator_lattice_card()
        record = LatticeRunRecord.completed(
            agent_card=card,
            action="fabricator.plan",
            contract_id=card.contracts[0].id,
            input_payload={"material": "cellulose"},
            output_payload={"candidate_workflow_count": 1},
        )

        self.assertEqual("lattice.run_record", record.record_type)
        self.assertEqual("fabricator", record.agent_id)
        self.assertEqual("completed", record.status)
        self.assertEqual("fabricator.plan.v0", record.contract_id)
        self.assertIsNotNone(record.completed_at)


if __name__ == "__main__":
    unittest.main()
