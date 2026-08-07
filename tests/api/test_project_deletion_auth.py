from __future__ import annotations

import time
import unittest
import uuid
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request

from apps.api import auth


def _request() -> Request:
    return Request({"type": "http", "method": "DELETE", "path": "/projects/test", "headers": []})


def _context(issued_at: float) -> auth.UserContext:
    user_id = f"user-{uuid.uuid4()}"
    return auth.UserContext(
        provider="clerk",
        subject=user_id,
        owner_user_id=user_id,
        is_authenticated=True,
        is_admin=False,
        claims={"sub": user_id, "iat": issued_at},
    )


class ProjectDeletionAuthenticationTests(unittest.IsolatedAsyncioTestCase):
    async def test_recent_auth_accepts_a_fresh_token(self) -> None:
        context = _context(time.time() - 30)
        with patch.object(auth, "require_user_context", return_value=context):
            self.assertIs(context, await auth.require_recent_user_context(_request()))

    async def test_recent_auth_rejects_a_stale_token(self) -> None:
        context = _context(time.time() - 3600)
        with patch.object(auth, "require_user_context", return_value=context):
            with self.assertRaises(HTTPException) as raised:
                await auth.require_recent_user_context(_request())
        self.assertEqual(401, raised.exception.status_code)

    async def test_destructive_rate_limit_is_per_user(self) -> None:
        context = _context(time.time())
        with (
            patch.object(auth, "require_recent_user_context", return_value=context),
            patch.dict(
                "os.environ",
                {"DESTRUCTIVE_RATE_LIMIT_REQUESTS": "1", "DESTRUCTIVE_RATE_LIMIT_WINDOW_SECONDS": "300"},
            ),
        ):
            self.assertIs(context, await auth.require_destructive_user_context(_request()))
            with self.assertRaises(HTTPException) as raised:
                await auth.require_destructive_user_context(_request())
        self.assertEqual(429, raised.exception.status_code)


if __name__ == "__main__":
    unittest.main()
