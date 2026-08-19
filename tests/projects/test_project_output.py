from __future__ import annotations

import unittest

from forma_core.image_providers import GeneratedImage
from forma_core.workspaces.projects.models import HardwareIR, ProjectOverview
from forma_core.workspaces.projects.output import attach_hardware_reference_image, attach_product_image


class ProjectOutputTests(unittest.TestCase):
    def test_generated_image_is_attached_inline_when_storage_skips_upload(self) -> None:
        ir = HardwareIR(
            overview=ProjectOverview(
                title="Test project",
                description="A test",
                difficulty="Beginner",
                category="IoT",
            ),
            assembly_metadata={"project_id": "29f2853c-ba3e-425a-b4c2-60f91cd2398b"},
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

    def test_hardware_reference_is_kept_inline_when_storage_skips_upload(self) -> None:
        ir = HardwareIR(
            overview=ProjectOverview(
                title="Test project",
                description="A test",
                difficulty="Beginner",
                category="IoT",
            ),
            assembly_metadata={"project_id": "29f2853c-ba3e-425a-b4c2-60f91cd2398b"},
        )

        attach_hardware_reference_image(
            ir,
            "data:image/png;base64,aW1hZ2U=",
            media_type="image/png",
            storage_handler=lambda *_args, **_kwargs: {"reference_image_storage_enabled": False},
        )

        self.assertEqual("data:image/png;base64,aW1hZ2U=", ir.assembly_metadata["reference_image_data"])
        self.assertEqual("image/png", ir.assembly_metadata["reference_image_content_type"])
        self.assertEqual("prompt_image", ir.assembly_metadata["input_mode"])

    def test_hardware_reference_does_not_replace_an_existing_stored_image(self) -> None:
        ir = HardwareIR(assembly_metadata={"reference_image_url": "https://example.test/ref.png"})

        attach_hardware_reference_image(ir, "data:image/png;base64,aW1hZ2U=")

        self.assertEqual("https://example.test/ref.png", ir.assembly_metadata["reference_image_url"])
        self.assertNotIn("reference_image_data", ir.assembly_metadata)


if __name__ == "__main__":
    unittest.main()
