import os
import unittest
from unittest.mock import patch

from blueprint_core.config.contract import resolve_runtime_contract


class RuntimeContractTests(unittest.TestCase):
    def test_contract_owns_runtime_image_workflow_and_setup_decisions(self) -> None:
        environment = {
            "BLUEPRINT_DEV_MODE": "true",
            "LLM_PROVIDER": "cloudflare",
            "LLM_MODEL": "@cf/google/gemma-4-26b-a4b-it",
            "LLM_ALLOWED_PROVIDERS": "cloudflare,openai",
            "CLOUDFLARE_API_TOKEN": "cf-token",
            "CLOUDFLARE_ACCOUNT_ID": "account-id",
            "CLOUDFLARE_MODEL": "@cf/google/gemma-4-26b-a4b-it",
            "OPENAI_API_KEY": "openai-token",
            "OPENAI_MODEL": "gpt-provider-specific",
        }
        with patch.dict(os.environ, environment, clear=True):
            contract = resolve_runtime_contract(
                llm_config={"live_generation_enabled": True, "validation_error": None},
                image_config={
                    "default_enabled": True,
                    "request_capable": True,
                    "request_provider": "gmi",
                    "request_model_name": "gpt-image-2",
                    "reason": None,
                },
                workflows=[
                    {"id": "default", "label": "Catalog", "description": "Catalog"},
                    {"id": "web_research", "label": "Web Research", "description": "Research"},
                ],
            )

        self.assertEqual(1, contract["contract_version"])
        self.assertEqual("backend", contract["authority"])
        self.assertEqual("web_research", contract["workflow"]["default_id"])
        self.assertTrue(contract["images"]["generate_by_default"])
        self.assertFalse(contract["provider_setup"]["required"])
        self.assertEqual(
            ("cloudflare", "@cf/google/gemma-4-26b-a4b-it"),
            (
                contract["generation"]["selected_llm"]["provider"],
                contract["generation"]["selected_llm"]["model"],
            ),
        )
        openai_models = [
            option["model"]
            for option in contract["generation"]["llm_options"]
            if option["provider"] == "openai"
        ]
        self.assertIn("gpt-provider-specific", openai_models)
        self.assertNotIn("@cf/google/gemma-4-26b-a4b-it", openai_models)

    def test_contract_reports_provider_setup_requirements(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            contract = resolve_runtime_contract(
                llm_config={
                    "live_generation_enabled": False,
                    "validation_error": "No live provider is configured.",
                },
                image_config={
                    "default_enabled": False,
                    "request_capable": False,
                    "provider": "none",
                    "reason": "Image provider API key is missing.",
                },
                workflows=[{"id": "default", "label": "Catalog", "description": "Catalog"}],
            )

        self.assertFalse(contract["generation"]["ready"])
        self.assertFalse(contract["generation"]["available"])
        self.assertTrue(contract["provider_setup"]["required"])
        self.assertTrue(contract["provider_setup"]["llm_required"])
        self.assertTrue(contract["provider_setup"]["image_required"])

    def test_config_can_select_catalog_as_the_default_workflow(self) -> None:
        with patch.dict(os.environ, {"BLUEPRINT_DEFAULT_GENERATION_WORKFLOW": "default"}, clear=True):
            contract = resolve_runtime_contract(
                llm_config={"live_generation_enabled": True, "validation_error": None},
                image_config={"request_capable": True},
                workflows=[
                    {"id": "default", "label": "Catalog", "description": "Catalog"},
                    {"id": "web_research", "label": "Web Research", "description": "Research"},
                ],
            )

        self.assertEqual("default", contract["workflow"]["default_id"])


if __name__ == "__main__":
    unittest.main()
