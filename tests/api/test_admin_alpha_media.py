from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.routing import APIRoute

from apps.api import main
from apps.api.auth import UserContext, require_admin_user_context
from apps.api.video_providers import VideoGenerationResult


ADMIN = UserContext(
    provider="clerk",
    subject="admin-1",
    owner_user_id="admin-1",
    is_authenticated=True,
    is_admin=True,
    claims={"sub": "admin-1"},
)


def _project(*, metadata: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        project_id="project-1",
        owner_user_id="another-user",
        prompt="Build a compact sensor enclosure.",
        hardware_ir={
            "overview": {
                "title": "Sensor enclosure",
                "description": "A compact sensor product.",
                "difficulty": "Beginner",
                "category": "IoT",
            },
            "components": [],
            "assembly_metadata": {"project_id": "project-1", **(metadata or {})},
        },
    )


class AdminAlphaMediaTests(unittest.TestCase):
    def test_mutating_media_routes_require_admin_dependency(self) -> None:
        protected_routes = {
            ("/video/projects/{project_id}", "GET"),
            ("/video/image-to-video", "POST"),
            ("/video/video-to-video", "POST"),
            ("/video/image-to-video/status/{request_id}", "GET"),
            ("/projects/{project_id}/video-prompt", "GET"),
            ("/admin-alpha/projects/{project_id}/image", "POST"),
        }

        for path, method in protected_routes:
            with self.subTest(path=path, method=method):
                route = next(
                    route
                    for route in main.app.routes
                    if isinstance(route, APIRoute) and route.path == path and method in route.methods
                )
                dependencies = {dependency.call for dependency in route.dependant.dependencies}
                self.assertIn(require_admin_user_context, dependencies)

    def test_manual_image_generation_uses_one_gmi_gpt_image_and_persists_it(self) -> None:
        project = _project()

        class FakeProvider:
            def get_debug_config(self):
                return {"configured": True, "provider": "gmi", "model_name": main.ADMIN_ALPHA_GMI_IMAGE_MODEL}

        provider = FakeProvider()

        def attach_image(_prompt, ir, **kwargs):
            self.assertFalse(kwargs["generate_sequence"])
            self.assertIs(provider, kwargs["provider_factory"]())
            ir.assembly_metadata = {
                **(ir.assembly_metadata or {}),
                "image_output_status": "succeeded",
                "product_image_data": "data:image/png;base64,ZmFrZQ==",
                "product_image_provider": "gmi",
                "product_image_model": main.ADMIN_ALPHA_GMI_IMAGE_MODEL,
            }

        with patch.object(main, "get_generated_project", return_value=project), patch.object(
            main, "hydrate_image_storage_metadata", side_effect=lambda metadata, _project_id: metadata
        ), patch.object(main, "GMIImageProvider", return_value=provider) as provider_factory, patch.object(
            main, "attach_product_image", side_effect=attach_image
        ) as attach, patch.object(main, "update_generated_project_hardware_ir", return_value=True) as update:
            response = main.generate_admin_alpha_project_image_endpoint("project-1", _user=ADMIN)

        provider_factory.assert_called_once_with(
            force_enabled=True,
            model_name="gpt-image-2-generate",
        )
        attach.assert_called_once()
        update.assert_called_once()
        self.assertEqual("gmi", response["image"]["provider"])
        self.assertEqual("gpt-image-2-generate", response["image"]["model"])
        self.assertEqual("succeeded", response["project_ir"]["assembly_metadata"]["image_output_status"])

    def test_manual_image_generation_refuses_to_replace_an_existing_image(self) -> None:
        project = _project(metadata={"product_image_url": "https://images.example.test/product.png"})
        with patch.object(main, "get_generated_project", return_value=project), patch.object(
            main, "hydrate_image_storage_metadata", side_effect=lambda metadata, _project_id: metadata
        ), patch.object(main, "GMIImageProvider") as provider_factory:
            with self.assertRaises(HTTPException) as raised:
                main.generate_admin_alpha_project_image_endpoint("project-1", _user=ADMIN)

        self.assertEqual(409, raised.exception.status_code)
        provider_factory.assert_not_called()

    def test_admin_can_generate_video_for_a_project_owned_by_another_user(self) -> None:
        provider = SimpleNamespace(
            create_image_to_video=lambda **_kwargs: VideoGenerationResult(
                request_id="request-1",
                status="queued",
                video_urls=[],
                raw={},
            )
        )
        request = main.VideoImageToVideoRequest(
            projectId="project-1",
            image="https://images.example.test/product.png",
            prompt="Animate the documented assembly steps in order.",
            model=main.get_default_video_model(),
            duration="5",
            aspectRatio="16:9",
        )

        with patch.object(main, "get_generated_project", return_value=_project()), patch.object(
            main, "ensure_video_storage_configured"
        ), patch.object(main, "GMICloudProvider", return_value=provider):
            response = main.create_image_to_video_endpoint(request, _user=ADMIN)

        self.assertEqual("project-1", response["projectId"])
        self.assertEqual("request-1", response["requestId"])
        self.assertEqual("queued", response["status"])


if __name__ == "__main__":
    unittest.main()
