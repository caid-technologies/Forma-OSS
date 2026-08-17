from __future__ import annotations

import os
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request

from apps.api.auth import (
    LOCAL_USER_ID,
    UserContext,
    _github_username_from_clerk_user,
    optional_deployed_clerk_auth,
    optional_user_context,
    require_admin_user_context,
    require_deployed_clerk_auth,
    require_user_context,
)


def request_with_authorization(value: str | None = None) -> Request:
    headers = [] if value is None else [(b"authorization", value.encode("utf-8"))]
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": headers,
        }
    )


class UserContextTests(unittest.IsolatedAsyncioTestCase):
    def test_extracts_github_username_from_clerk_external_account(self) -> None:
        user = {
            "external_accounts": [
                {"provider": "oauth_google", "username": ""},
                {"provider": "oauth_github", "username": "@octocat"},
            ]
        }

        self.assertEqual("octocat", _github_username_from_clerk_user(user))

    def test_ignores_non_github_external_username(self) -> None:
        user = {"external_accounts": [{"provider": "oauth_google", "username": "google-user"}]}

        self.assertIsNone(_github_username_from_clerk_user(user))

    async def test_local_mode_resolves_a_stable_authenticated_admin(self) -> None:
        request = request_with_authorization("Bearer ignored-in-local-mode")

        with patch.dict(os.environ, {"FORMA_AUTH_MODE": "local"}, clear=True), patch(
            "apps.api.auth.verify_clerk_bearer_token"
        ) as verify_token:
            optional_context = await optional_user_context(request)
            required_context = await require_user_context(request)
            admin_context = await require_admin_user_context(request)

        for context in (optional_context, required_context, admin_context):
            self.assertEqual("local", context.provider)
            self.assertEqual(LOCAL_USER_ID, context.subject)
            self.assertEqual(LOCAL_USER_ID, context.owner_user_id)
            self.assertTrue(context.is_authenticated)
            self.assertTrue(context.is_admin)
            self.assertEqual({}, dict(context.claims))
        verify_token.assert_not_called()

    async def test_optional_clerk_mode_without_token_returns_anonymous_context(self) -> None:
        with patch.dict(os.environ, {"FORMA_AUTH_MODE": "clerk"}, clear=True):
            context = await optional_user_context(request_with_authorization())

        self.assertEqual("clerk", context.provider)
        self.assertIsNone(context.subject)
        self.assertIsNone(context.owner_user_id)
        self.assertFalse(context.is_authenticated)
        self.assertFalse(context.is_admin)
        self.assertEqual({}, dict(context.claims))

    async def test_clerk_token_resolves_subject_owner_claims_and_admin(self) -> None:
        claims = {"sub": "user_123", "public_metadata": {"role": "admin"}}
        request = request_with_authorization("Bearer valid-token")

        with patch.dict(os.environ, {"FORMA_AUTH_MODE": "clerk"}, clear=True), patch(
            "apps.api.auth.verify_clerk_bearer_token", return_value=claims
        ) as verify_token:
            context = await optional_user_context(request)

        verify_token.assert_called_once_with("valid-token")
        self.assertEqual("clerk", context.provider)
        self.assertEqual("user_123", context.subject)
        self.assertEqual("user_123", context.owner_user_id)
        self.assertTrue(context.is_authenticated)
        self.assertTrue(context.is_admin)
        self.assertEqual(claims, dict(context.claims))

    async def test_required_context_rejects_anonymous_clerk_request(self) -> None:
        with patch.dict(os.environ, {"FORMA_AUTH_MODE": "clerk"}, clear=True):
            with self.assertRaises(HTTPException) as raised:
                await require_user_context(request_with_authorization())

        self.assertEqual(401, raised.exception.status_code)

    async def test_admin_context_rejects_non_admin_clerk_user(self) -> None:
        request = request_with_authorization("Bearer valid-token")
        with patch.dict(os.environ, {"FORMA_AUTH_MODE": "clerk"}, clear=True), patch(
            "apps.api.auth.verify_clerk_bearer_token", return_value={"sub": "user_123"}
        ):
            with self.assertRaises(HTTPException) as raised:
                await require_admin_user_context(request)

        self.assertEqual(403, raised.exception.status_code)

    async def test_legacy_clerk_dependencies_keep_their_return_shapes(self) -> None:
        local_request = request_with_authorization("Bearer ignored")
        with patch.dict(os.environ, {"FORMA_AUTH_MODE": "local"}, clear=True):
            self.assertIsNone(await optional_deployed_clerk_auth(local_request))
            self.assertIsNone(await require_deployed_clerk_auth(local_request))

        clerk_request = request_with_authorization("Bearer valid-token")
        claims = {"sub": "user_123"}
        with patch.dict(os.environ, {"FORMA_AUTH_MODE": "clerk"}, clear=True), patch(
            "apps.api.auth.verify_clerk_bearer_token", return_value=claims
        ):
            self.assertEqual(claims, await optional_deployed_clerk_auth(clerk_request))
            self.assertEqual(claims, await require_deployed_clerk_auth(clerk_request))

    def test_user_context_is_frozen_and_copies_claims(self) -> None:
        claims = {"sub": "user_123"}
        context = UserContext(
            provider="clerk",
            subject="user_123",
            owner_user_id="user_123",
            is_authenticated=True,
            is_admin=False,
            claims=claims,
        )

        claims["sub"] = "changed"
        self.assertEqual("user_123", context.claims["sub"])
        with self.assertRaises(TypeError):
            context.claims["sub"] = "changed"  # type: ignore[index]
        with self.assertRaises(FrozenInstanceError):
            context.subject = "changed"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
