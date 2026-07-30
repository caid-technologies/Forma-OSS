import os
import unittest
from unittest.mock import patch

from blueprint_core.debug import api_error_detail, runtime_safe_error_message


class ApiErrorVisibilityTests(unittest.TestCase):
    def test_deployment_error_hides_provider_and_model_names(self) -> None:
        message = (
            "Project iteration failed for provider=nebius "
            "model=nvidia/nemotron-3-super-120b-a12b: "
            "nebius response did not include text content."
        )

        with patch.dict(os.environ, {"BLUEPRINT_DEV_MODE": "false"}):
            detail = api_error_detail(
                code="llm_output_invalid",
                message=message,
                provider="nebius",
                model="nvidia/nemotron-3-super-120b-a12b",
            )

        self.assertEqual(
            "Project iteration failed: model provider response did not include text content.",
            detail["message"],
        )
        self.assertNotIn("provider", detail)
        self.assertNotIn("model", detail)
        self.assertNotIn("nebius", str(detail).lower())
        self.assertNotIn("nemotron", str(detail).lower())

    def test_development_error_preserves_runtime_diagnostics(self) -> None:
        message = "Generation failed for provider=nebius model=nvidia/nemotron: empty response."

        with patch.dict(os.environ, {"BLUEPRINT_DEV_MODE": "true"}):
            detail = api_error_detail(
                code="llm_output_invalid",
                message=message,
                provider="nebius",
                model="nvidia/nemotron",
            )
            safe_message = runtime_safe_error_message(
                message,
                provider="nebius",
                model="nvidia/nemotron",
            )

        self.assertEqual(message, safe_message)
        self.assertEqual(message, detail["message"])
        self.assertEqual("nebius", detail["provider"])
        self.assertEqual("nvidia/nemotron", detail["model"])


if __name__ == "__main__":
    unittest.main()
