from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.routing import APIRoute

from backend.auth import require_deployed_clerk_auth
from backend.user_integrations_api import (
    ImageModelTestRequest,
    IntegrationUpdateRequest,
    get_user_integrations,
    _store_for_auth,
    image_model_test_available,
    router,
    test_image_model,
    update_user_integration,
)
from blueprint_core.user_integrations import SupabaseUserIntegrationStore, SupabaseWorkspaceIntegrationStore


class BrokenIntegrationStore:
    storage_label = "supabase:user_integration_configs/user_test"
    path = "supabase:user_integration_configs/user_test"

    def load(self):
        raise RuntimeError("Stored provider settings were encrypted with a different BLUEPRINT_USER_SECRETS_KEY.")

    def update_integration(self, *_args, **_kwargs):
        raise RuntimeError("Supabase write failed")


class PersistThenBrokenReloadStore(BrokenIntegrationStore):
    def update_integration(self, *_args, **_kwargs):
        return None


class UserIntegrationsApiAuthTests(unittest.TestCase):
    def test_local_mode_uses_encrypted_workspace_store_even_if_clerk_claims_are_present(self) -> None:
        workspace_store = SupabaseWorkspaceIntegrationStore()
        with patch.dict(os.environ, {"BLUEPRINT_AUTH_MODE": "local"}, clear=False), patch(
            "backend.user_integrations_api.default_integration_store",
            return_value=workspace_store,
        ):
            self.assertIs(workspace_store, _store_for_auth({"sub": "user_should_be_ignored"}))

    def test_clerk_mode_uses_authenticated_user_store(self) -> None:
        user_store = SupabaseUserIntegrationStore("user_test")
        with patch.dict(os.environ, {"BLUEPRINT_AUTH_MODE": "clerk"}, clear=False), patch(
            "backend.user_integrations_api.UserIntegrationStore.for_user",
            return_value=user_store,
        ) as for_user:
            self.assertIs(user_store, _store_for_auth({"sub": "user_test"}))
        for_user.assert_called_once_with("user_test")

    def test_user_integration_routes_require_deployed_auth(self) -> None:
        routes = [route for route in router.routes if isinstance(route, APIRoute)]
        self.assertGreaterEqual(len(routes), 4)

        for route in routes:
            dependency_calls = {dependency.call for dependency in route.dependant.dependencies}
            self.assertIn(require_deployed_clerk_auth, dependency_calls, route.path)

    def test_load_failure_is_logged_and_returned_as_structured_error(self) -> None:
        with patch("backend.user_integrations_api._store_for_auth", return_value=BrokenIntegrationStore()):
            with self.assertLogs("backend.user_integrations_api", level="ERROR") as logs:
                with self.assertRaises(HTTPException) as raised:
                    get_user_integrations({"sub": "user_test"})

        self.assertEqual(500, raised.exception.status_code)
        self.assertEqual("user_integrations_load_failed", raised.exception.detail["code"])
        self.assertIn("different BLUEPRINT_USER_SECRETS_KEY", raised.exception.detail["message"])
        self.assertIn("owner_user_id=user_test", "\n".join(logs.output))
        self.assertIn("error_type=RuntimeError", "\n".join(logs.output))

    def test_save_failure_is_logged_and_returned_as_structured_error(self) -> None:
        request = IntegrationUpdateRequest(enabled=True, fields={"api_key": "test-secret"})
        with patch("backend.user_integrations_api._store_for_auth", return_value=BrokenIntegrationStore()):
            with self.assertLogs("backend.user_integrations_api", level="ERROR") as logs:
                with self.assertRaises(HTTPException) as raised:
                    update_user_integration("anthropic", request, {"sub": "user_test"})

        self.assertEqual(500, raised.exception.status_code)
        self.assertEqual("user_integrations_save_failed", raised.exception.detail["code"])
        self.assertIn("Supabase write failed", raised.exception.detail["message"])
        self.assertIn("integration_id=anthropic", "\n".join(logs.output))
        self.assertNotIn("test-secret", "\n".join(logs.output))

    def test_post_save_reload_failure_is_distinguished_from_write_failure(self) -> None:
        request = IntegrationUpdateRequest(enabled=True, fields={"api_key": "test-secret"})
        with patch("backend.user_integrations_api._store_for_auth", return_value=PersistThenBrokenReloadStore()):
            with self.assertLogs("backend.user_integrations_api", level="INFO") as logs:
                with self.assertRaises(HTTPException) as raised:
                    update_user_integration("anthropic", request, {"sub": "user_test"})

        output = "\n".join(logs.output)
        self.assertEqual(500, raised.exception.status_code)
        self.assertEqual("user_integrations_post_save_reload_failed", raised.exception.detail["code"])
        self.assertIn("update persisted", output)
        self.assertIn("post_save_reload failed", output)
        self.assertNotIn("test-secret", output)

    def test_image_model_test_is_limited_to_local_and_preview(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(image_model_test_available())
        with patch.dict(os.environ, {"VERCEL": "1", "VERCEL_ENV": "preview"}, clear=True):
            self.assertTrue(image_model_test_available())
        with patch.dict(os.environ, {"VERCEL": "1", "VERCEL_ENV": "production"}, clear=True):
            self.assertFalse(image_model_test_available())
        with patch.dict(os.environ, {"BLUEPRINT_DEPLOYMENT": "true"}, clear=True):
            self.assertFalse(image_model_test_available())

    def test_image_model_test_calls_provider_directly(self) -> None:
        class FakeProvider:
            provider_name = "gmi"
            model_name = "seedream-5.0-pro"

            def get_debug_config(self):
                return {"provider": "gmi", "model_name": self.model_name, "configured": True, "api_key": "must-redact"}

            def generate_test_image(self, prompt):
                self.prompt = prompt
                return SimpleNamespace(
                    provider="gmi",
                    model=self.model_name,
                    size="2048x2048",
                    output_format="jpeg",
                    prompt=prompt,
                    prompt_original_length=len(prompt),
                    prompt_final_length=len(prompt),
                    prompt_compacted=False,
                    data_url="data:image/jpeg;base64,ZmFrZQ==",
                )

        provider = FakeProvider()
        request = ImageModelTestRequest(provider="gmi", model="seedream-5.0-pro", prompt="  test render  ")
        with patch.dict(os.environ, {}, clear=True), patch(
            "backend.user_integrations_api._store_for_auth", return_value=object()
        ), patch("backend.user_integrations_api.apply_user_integrations_to_environment"), patch(
            "backend.user_integrations_api.build_image_provider", return_value=provider
        ):
            response = test_image_model(request, {"sub": "user_test"})

        self.assertTrue(response["ok"])
        self.assertEqual("test render", provider.prompt)
        self.assertEqual("data:image/jpeg;base64,ZmFrZQ==", response["image_data_url"])
        self.assertEqual("<redacted>", response["config"]["api_key"])

    def test_image_model_test_route_is_hidden_in_production(self) -> None:
        request = ImageModelTestRequest(provider="gmi", model="seedream-5.0-pro", prompt="test render")
        with patch.dict(os.environ, {"VERCEL": "1", "VERCEL_ENV": "production"}, clear=True):
            with self.assertRaises(HTTPException) as raised:
                test_image_model(request, {"sub": "user_test"})

        self.assertEqual(404, raised.exception.status_code)


if __name__ == "__main__":
    unittest.main()
