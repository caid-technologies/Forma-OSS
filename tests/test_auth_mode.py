from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from starlette.requests import Request

from backend.auth import optional_deployed_clerk_auth, require_deployed_clerk_auth
from backend.auth_mode import blueprint_auth_mode
from blueprint_core.user_integrations import require_user_secrets_key


def request_with_authorization(value: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"authorization", value.encode("utf-8"))],
        }
    )


class AuthModeTests(unittest.IsolatedAsyncioTestCase):
    def test_auth_mode_requires_an_explicit_valid_value(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertLogs("backend.auth_mode", level="CRITICAL"):
                with self.assertRaisesRegex(RuntimeError, "BLUEPRINT_AUTH_MODE is required"):
                    blueprint_auth_mode()
        with patch.dict(os.environ, {"BLUEPRINT_AUTH_MODE": "local"}, clear=True):
            self.assertEqual("local", blueprint_auth_mode())
        with patch.dict(os.environ, {"BLUEPRINT_AUTH_MODE": "optional"}, clear=True):
            with self.assertLogs("backend.auth_mode", level="CRITICAL"):
                with self.assertRaisesRegex(RuntimeError, "Expected 'local' or 'clerk'"):
                    blueprint_auth_mode()

    async def test_local_mode_ignores_bearer_tokens(self) -> None:
        request = request_with_authorization("Bearer invalid-token")
        with patch.dict(os.environ, {"BLUEPRINT_AUTH_MODE": "local"}, clear=True):
            self.assertIsNone(await require_deployed_clerk_auth(request))
            self.assertIsNone(await optional_deployed_clerk_auth(request))

    def test_missing_user_secrets_key_logs_and_raises(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertLogs("blueprint_core.user_integrations", level="CRITICAL") as logs:
                with self.assertRaisesRegex(RuntimeError, "BLUEPRINT_USER_SECRETS_KEY is required"):
                    require_user_secrets_key()
        self.assertIn("required at runtime", "\n".join(logs.output))

    async def test_backend_startup_fails_before_database_initialization_without_key(self) -> None:
        from backend import main

        with patch.dict(os.environ, {"BLUEPRINT_USER_SECRETS_KEY": ""}, clear=False), patch.object(
            main, "init_db"
        ) as init_db:
            with self.assertLogs("blueprint_core.user_integrations", level="CRITICAL"):
                with self.assertRaisesRegex(RuntimeError, "BLUEPRINT_USER_SECRETS_KEY is required"):
                    await main.startup_event()
        init_db.assert_not_called()


if __name__ == "__main__":
    unittest.main()
