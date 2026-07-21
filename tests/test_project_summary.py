from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend import main


class ProjectSummaryTests(unittest.TestCase):
    def test_project_summary_includes_hydrated_product_image(self) -> None:
        project = SimpleNamespace(
            project_id="fd54de37-2fbb-485a-92e4-8bfaf4a2f08c",
            chat_id="chat_123",
            title="Low Voltage Desk Lamp",
            prompt="desk lamp",
            created_at="2026-07-21T14:08:00Z",
            owner_user_id="user_123",
            hardware_ir={
                "components": [{"ref_des": "D1"}, {"ref_des": "R1"}],
                "assembly_metadata": {
                    "image_output_status": "succeeded",
                    "product_image_model": "openai/gpt-image-2",
                    "product_case_image_s3_key": "images/project/product-case.png",
                    "product_visual_sequence": [
                        {
                            "view_id": "case",
                            "label": "Case exterior",
                            "s3_key": "images/project/product-case.png",
                        }
                    ],
                },
            },
        )
        hydrated = {
            **project.hardware_ir["assembly_metadata"],
            "product_case_image_url": "https://storage.example.test/signed-product-case.png",
            "product_case_image_content_type": "image/png",
            "product_visual_sequence": [
                {
                    "view_id": "case",
                    "label": "Case exterior",
                    "url": "https://storage.example.test/signed-product-case.png",
                    "content_type": "image/png",
                }
            ],
        }

        with patch.object(main, "creator_display_name", return_value="isayahc"), patch.object(
            main, "clerk_user_image_url", return_value=None
        ), patch.object(main, "hydrate_image_storage_metadata", return_value=hydrated):
            summary = main._project_summary_response(project, current_user_id="user_123")

        self.assertTrue(summary["has_product_image"])
        self.assertEqual("https://storage.example.test/signed-product-case.png", summary["product_image_url"])
        self.assertEqual("image/png", summary["product_image_content_type"])
        self.assertEqual("openai/gpt-image-2", summary["product_image_model"])
        self.assertEqual("succeeded", summary["image_output_status"])
        self.assertEqual("https://storage.example.test/signed-product-case.png", summary["product_visual_sequence"][0]["url"])

    def test_project_image_summary_endpoint_does_not_validate_full_ir(self) -> None:
        project = SimpleNamespace(
            project_id="fd54de37-2fbb-485a-92e4-8bfaf4a2f08c",
            chat_id="chat_123",
            title="Low Voltage Desk Lamp",
            prompt="desk lamp",
            created_at="2026-07-21T14:08:00Z",
            owner_user_id="user_123",
            hardware_ir={
                "components": [{"legacy_shape": "not a HardwareIR component"}],
                "assembly_metadata": {
                    "image_output_status": "succeeded",
                    "product_image_url": "https://storage.example.test/product.png",
                    "product_image_content_type": "image/png",
                },
            },
        )

        with patch.object(main, "get_generated_project", return_value=project), patch.object(
            main, "creator_display_name", return_value="isayahc"
        ), patch.object(main, "clerk_user_image_url", return_value=None), patch.object(
            main, "hydrate_image_storage_metadata", side_effect=lambda metadata, _project_id: metadata
        ), patch.object(main, "HardwareIR", side_effect=AssertionError("HardwareIR should not be constructed")):
            summary = main.get_project_image_summary_endpoint(project.project_id, _auth_claims=None)

        self.assertEqual(project.project_id, summary["project_id"])
        self.assertEqual("https://storage.example.test/product.png", summary["product_image_url"])
        self.assertTrue(summary["has_product_image"])


if __name__ == "__main__":
    unittest.main()
