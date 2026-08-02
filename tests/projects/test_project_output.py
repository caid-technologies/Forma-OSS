from __future__ import annotations

import unittest

from blueprint_core.image_providers import GeneratedImage
from blueprint_core.workspaces.projects.models import HardwareIR, ProjectOverview
from blueprint_core.workspaces.projects.output import attach_product_image


class ProjectOutputTests(unittest.TestCase):
    def test_generated_image_is_attached_inline_when_storage_skips_upload(self) -> None:
        ir = HardwareIR(
            overview=ProjectOverview(
                title="Test project",
                description="A test",
                difficulty="Beginner",
                category="IoT",
            ),
            assembly_metadata={
                "project_id": "29f2853c-ba3e-425a-b4c2-60f91cd2398b",
                "revision": 2,
                "image_output_requested": True,
                "image_output_status": "succeeded",
                "product_image_data": "data:image/png;base64,b2xk",
                "product_inside_image_data": "data:image/png;base64,b2xkLWluc2lkZQ==",
                "product_visual_sequence": [{"view_id": "inside", "data": "old"}],
                "product_visual_sequence_count": 1,
                "operation_statuses": [
                    {"id": "image_generation", "status": "succeeded"},
                    {"id": "image_storage", "status": "succeeded"},
                ],
            },
        )
        image = GeneratedImage(
            data_url="data:image/png;base64,ZmFrZQ==",
            provider="gmi",
            model="gpt-image-2",
            size="1024x1024",
            prompt="render",
            output_format="png",
            view_id="case",
            label="Case",
        )

        class FakeProvider:
            def get_debug_config(self):
                return {
                    "provider": "gmi",
                    "model_name": "gpt-image-2",
                    "enabled": True,
                    "configured": True,
                }

            def generate_project_image_sequence(self, _prompt, _ir):
                return [image]

        def inline_storage(*_args, **_kwargs):
            return {"product_case_image_storage_enabled": False}

        attach_product_image(
            "test prompt",
            ir,
            generate_image=True,
            provider_factory=lambda **_kwargs: FakeProvider(),
            storage_handler=inline_storage,
        )

        metadata = ir.assembly_metadata
        self.assertEqual("succeeded", metadata["image_output_status"])
        self.assertEqual(image.data_url, metadata["product_image_data"])
        self.assertEqual(image.data_url, metadata["product_visual_sequence"][0]["data"])
        self.assertEqual(1, metadata["product_visual_sequence_count"])
        self.assertEqual(2, metadata["image_output_project_revision"])
        self.assertNotIn("product_inside_image_data", metadata)
        self.assertEqual(
            ["image_generation", "image_storage"],
            [operation["id"] for operation in metadata["operation_statuses"]],
        )

    def test_failed_visual_refresh_does_not_keep_stale_images(self) -> None:
        ir = HardwareIR(
            overview=ProjectOverview(
                title="Test project",
                description="A test",
                difficulty="Beginner",
                category="IoT",
            ),
            assembly_metadata={
                "project_id": "29f2853c-ba3e-425a-b4c2-60f91cd2398b",
                "revision": 3,
                "image_output_requested": True,
                "product_image_data": "data:image/png;base64,b2xk",
                "product_visual_sequence": [{"view_id": "case", "data": "old"}],
            },
        )

        class UnconfiguredProvider:
            def get_debug_config(self):
                return {
                    "provider": "gmi",
                    "model_name": "gpt-image-2",
                    "enabled": True,
                    "configured": False,
                    "reason": "provider unavailable",
                }

        attach_product_image(
            "test prompt",
            ir,
            generate_image=True,
            provider_factory=lambda **_kwargs: UnconfiguredProvider(),
        )

        metadata = ir.assembly_metadata
        self.assertEqual("failed", metadata["image_output_status"])
        self.assertEqual(3, metadata["image_output_project_revision"])
        self.assertNotIn("product_image_data", metadata)
        self.assertNotIn("product_visual_sequence", metadata)


if __name__ == "__main__":
    unittest.main()
