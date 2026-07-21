from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.routing import APIRoute

from backend.auth import require_deployed_clerk_auth
from backend.user_integrations_api import get_user_integrations, router, update_user_integration, IntegrationUpdateRequest


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


if __name__ == "__main__":
    unittest.main()
