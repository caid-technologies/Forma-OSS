from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.routing import APIRoute

from backend.auth import UserContext, require_user_context
from backend.user_settings_api import (
    DataUsagePreferenceUpdateRequest,
    get_data_usage_preference,
    router,
    update_data_usage_preference,
)


USER_CONTEXT = UserContext(
    provider="hosted-test",
    subject="user_test",
    owner_user_id="user_test",
    is_authenticated=True,
    is_admin=False,
)


class UserSettingsApiTests(unittest.TestCase):
    def test_data_usage_routes_require_authenticated_user_context(self) -> None:
        routes = [route for route in router.routes if isinstance(route, APIRoute)]
        self.assertEqual(2, len(routes))
        for route in routes:
            dependency_calls = {dependency.call for dependency in route.dependant.dependencies}
            self.assertIn(require_user_context, dependency_calls, route.path)

    def test_missing_preference_uses_default_allow_state_without_writing(self) -> None:
        with patch("backend.user_settings_api.get_user_settings", return_value=None) as get_settings:
            payload = get_data_usage_preference(USER_CONTEXT)

        get_settings.assert_called_once_with("user_test")
        self.assertTrue(payload["allow_model_training"])
        self.assertFalse(payload["model_training_opt_out"])
        self.assertEqual("default", payload["source"])
        self.assertIsNone(payload["updated_at"])

    def test_user_can_opt_out_and_response_is_auditable(self) -> None:
        saved = SimpleNamespace(
            owner_user_id="user_test",
            model_training_opt_out=True,
            created_at="2026-07-27T20:00:00Z",
            updated_at="2026-07-27T20:00:00Z",
        )
        request = DataUsagePreferenceUpdateRequest(allow_model_training=False)
        with patch(
            "backend.user_settings_api.set_user_model_training_preference",
            return_value=saved,
        ) as save_preference:
            payload = update_data_usage_preference(request, USER_CONTEXT)

        kwargs = save_preference.call_args.kwargs
        self.assertEqual("user_test", save_preference.call_args.args[0])
        self.assertFalse(kwargs["allow_model_training"])
        self.assertTrue(str(kwargs["updated_at"]).endswith("Z"))
        self.assertFalse(payload["allow_model_training"])
        self.assertTrue(payload["model_training_opt_out"])
        self.assertEqual("user", payload["source"])
        self.assertEqual("2026-07-27T20:00:00Z", payload["updated_at"])


if __name__ == "__main__":
    unittest.main()
