from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request

from backend.auth import require_user_api_key, user_api_key_auth_configured
from blueprint_core import database


def _request(headers: list[tuple[bytes, bytes]]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/v1/me",
            "headers": headers,
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )


class PublicApiAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        database.init_db()

    def test_user_api_key_auth_reports_configured(self) -> None:
        with patch.dict(os.environ, {"BLUEPRINT_USER_API_KEYS": "docs=bp_test_secret"}, clear=False):
            self.assertTrue(user_api_key_auth_configured())

    def test_user_api_key_accepts_bearer_token(self) -> None:
        with patch.dict(os.environ, {"BLUEPRINT_USER_API_KEYS": "docs=bp_test_secret"}, clear=False):
            principal = asyncio.run(
                require_user_api_key(_request([(b"authorization", b"Bearer bp_test_secret")]))
            )

        self.assertEqual("docs", principal.key_id)
        self.assertEqual("api:docs", principal.owner_user_id)

    def test_user_api_key_accepts_x_api_key(self) -> None:
        with patch.dict(os.environ, {"BLUEPRINT_USER_API_KEYS": "docs=bp_test_secret"}, clear=False):
            principal = asyncio.run(require_user_api_key(_request([(b"x-api-key", b"bp_test_secret")])))

        self.assertEqual("docs", principal.key_id)

    def test_user_api_key_rejects_invalid_key(self) -> None:
        with patch.dict(os.environ, {"BLUEPRINT_USER_API_KEYS": "docs=bp_test_secret"}, clear=False):
            with self.assertRaises(HTTPException) as context:
                asyncio.run(require_user_api_key(_request([(b"authorization", b"Bearer wrong")])))

        self.assertEqual(401, context.exception.status_code)

    def test_user_api_key_rejects_unknown_key_when_env_fallback_is_not_configured(self) -> None:
        with patch.dict(os.environ, {"BLUEPRINT_USER_API_KEYS": "", "BLUEPRINT_API_KEYS": ""}, clear=False):
            with self.assertRaises(HTTPException) as context:
                asyncio.run(require_user_api_key(_request([(b"authorization", b"Bearer bp_test_secret")])))

        self.assertEqual(401, context.exception.status_code)

    def test_env_fallback_keys_are_ignored_in_deployed_mode_by_default(self) -> None:
        with patch.dict(
            os.environ,
            {
                "BLUEPRINT_DEPLOYMENT": "true",
                "BLUEPRINT_ALLOW_ENV_USER_API_KEYS": "",
                "BLUEPRINT_API_KEY_PEPPER": "unit-test-pepper",
                "BLUEPRINT_USER_API_KEYS": "docs=bp_test_secret",
            },
            clear=False,
        ):
            self.assertFalse(user_api_key_auth_configured())
            with self.assertRaises(HTTPException) as context:
                asyncio.run(require_user_api_key(_request([(b"authorization", b"Bearer bp_test_secret")])))

        self.assertEqual(401, context.exception.status_code)

    def test_managed_key_creation_requires_pepper_in_deployed_mode(self) -> None:
        with patch.dict(
            os.environ,
            {
                "BLUEPRINT_DEPLOYMENT": "true",
                "BLUEPRINT_API_KEY_PEPPER": "",
                "API_KEY_PEPPER": "",
                "BLUEPRINT_ALLOW_UNPEPPERED_API_KEY_HASHES": "",
            },
            clear=False,
        ):
            with self.assertRaises(RuntimeError):
                database.create_user_api_key(owner_user_id="user_test_no_pepper", name="No pepper")

    def test_managed_key_authenticates_with_pepper_in_deployed_mode(self) -> None:
        with patch.dict(
            os.environ,
            {
                "BLUEPRINT_DEPLOYMENT": "true",
                "BLUEPRINT_API_KEY_PEPPER": "unit-test-pepper",
                "BLUEPRINT_USER_API_KEYS": "",
                "BLUEPRINT_API_KEYS": "",
            },
            clear=False,
        ):
            record, secret = database.create_user_api_key(owner_user_id="user_test_pepper", name="Peppered key")
            principal = asyncio.run(require_user_api_key(_request([(b"authorization", f"Bearer {secret}".encode())])))

        self.assertEqual(record.key_id, principal.key_id)
        self.assertEqual("user_test_pepper", principal.owner_user_id)

    def test_database_api_key_authenticates_and_records_use(self) -> None:
        record, secret = database.create_user_api_key(owner_user_id="user_test_auth", name="Unit test key")

        with patch.dict(os.environ, {"BLUEPRINT_USER_API_KEYS": "", "BLUEPRINT_API_KEYS": ""}, clear=False):
            principal = asyncio.run(require_user_api_key(_request([(b"authorization", f"Bearer {secret}".encode())])))

        self.assertEqual(record.key_id, principal.key_id)
        self.assertEqual("user_test_auth", principal.owner_user_id)
        updated = database.get_user_api_key_for_owner("user_test_auth", record.key_id)
        self.assertIsNotNone(updated)
        assert updated is not None
        self.assertEqual(1, updated.daily_usage_count)
        self.assertIsNotNone(updated.last_used_at)

    def test_revoked_database_api_key_is_rejected(self) -> None:
        record, secret = database.create_user_api_key(owner_user_id="user_test_revoke", name="Revoked key")
        self.assertTrue(database.revoke_user_api_key("user_test_revoke", record.key_id))

        with patch.dict(os.environ, {"BLUEPRINT_USER_API_KEYS": "", "BLUEPRINT_API_KEYS": ""}, clear=False):
            with self.assertRaises(HTTPException) as context:
                asyncio.run(require_user_api_key(_request([(b"x-api-key", secret.encode())])))

        self.assertEqual(401, context.exception.status_code)


if __name__ == "__main__":
    unittest.main()
