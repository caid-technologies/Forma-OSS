"""Tests for Clerk auth enforcement (backend/auth.py)."""

import asyncio
import base64
import os
import time
import unittest
from types import SimpleNamespace
from unittest import mock

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from backend import auth as backend_auth
from backend.auth import (
    AuthError,
    ClerkAuthMiddleware,
    clerk_jwks_url,
    validate_auth_startup,
    verify_clerk_token,
)
from blueprint_core.runtime_config import deployment_runtime_config

JWKS_URL = "https://clerk.example.com/.well-known/jwks.json"

# Every env var that influences auth behavior, defaulted to "disabled" so tests
# are hermetic regardless of the developer's shell/.env state.
BASE_ENV = {
    "BLUEPRINT_DEPLOYMENT": "",
    "BLUEPRINT_DEPLOYMENT_MODE": "",
    "DEPLOYMENT": "",
    "DEPLOYMENT_MODE": "",
    "NEXT_PUBLIC_BLUEPRINT_DEPLOYMENT": "",
    "BLUEPRINT_DISABLE_AUTH": "",
    "CLERK_JWKS_URL": "",
    "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY": "",
    "CLERK_AUTHORIZED_PARTIES": "",
}


def env(**overrides):
    values = {**BASE_ENV, **overrides}
    return mock.patch.dict(os.environ, values)


def auth_on_env(**overrides):
    return env(BLUEPRINT_DEPLOYMENT="true", CLERK_JWKS_URL=JWKS_URL, **overrides)


class RecordingApp:
    """Inner ASGI app that records whether/with what scope it was called."""

    def __init__(self):
        self.called = False
        self.scope = None

    async def __call__(self, scope, receive, send):
        self.called = True
        self.scope = scope
        if scope["type"] == "http":
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})


class ClerkAuthTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.private_pem = cls.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        cls.public_pem = cls.private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    def setUp(self):
        stub_client = SimpleNamespace(
            get_signing_key_from_jwt=lambda token: SimpleNamespace(key=self.public_pem)
        )
        patcher = mock.patch.object(backend_auth, "_jwks_client", return_value=stub_client)
        patcher.start()
        self.addCleanup(patcher.stop)

    def make_token(self, **claims):
        now = int(time.time())
        payload = {"sub": "user_123", "iat": now, "exp": now + 120, **claims}
        payload = {k: v for k, v in payload.items() if v is not None}
        return jwt.encode(payload, self.private_pem, algorithm="RS256", headers={"kid": "test"})

    # -- helpers ------------------------------------------------------------

    def call_http(self, path="/projects", method="GET", headers=None):
        app = RecordingApp()
        middleware = ClerkAuthMiddleware(app)
        sent = []

        async def send(message):
            sent.append(message)

        async def receive():
            return {"type": "http.request", "body": b""}

        scope = {"type": "http", "method": method, "path": path, "headers": headers or []}
        asyncio.run(middleware(scope, receive, send))
        return app, sent

    def call_websocket(self, headers=None):
        app = RecordingApp()
        middleware = ClerkAuthMiddleware(app)
        sent = []

        async def send(message):
            sent.append(message)

        async def receive():
            return {"type": "websocket.connect"}

        scope = {"type": "websocket", "path": "/a2a/socket/agent-1", "headers": headers or []}
        asyncio.run(middleware(scope, receive, send))
        return app, sent

    @staticmethod
    def response_status(sent):
        return sent[0]["status"]


class VerifyClerkTokenTests(ClerkAuthTestCase):
    def test_valid_token(self):
        with auth_on_env():
            claims = verify_clerk_token(self.make_token())
        self.assertEqual(claims["sub"], "user_123")

    def test_expired_token(self):
        token = self.make_token(exp=int(time.time()) - 120)
        with auth_on_env():
            with self.assertRaises(AuthError) as ctx:
                verify_clerk_token(token)
        self.assertEqual(ctx.exception.code, "auth_required")
        self.assertEqual(ctx.exception.status_code, 401)

    def test_future_nbf_token(self):
        token = self.make_token(nbf=int(time.time()) + 600)
        with auth_on_env():
            with self.assertRaises(AuthError) as ctx:
                verify_clerk_token(token)
        self.assertEqual(ctx.exception.code, "auth_required")

    def test_wrong_azp_rejected(self):
        token = self.make_token(azp="https://evil.example.com")
        with auth_on_env(CLERK_AUTHORIZED_PARTIES="https://app.example.com"):
            with self.assertRaises(AuthError) as ctx:
                verify_clerk_token(token)
        self.assertEqual(ctx.exception.code, "auth_required")

    def test_matching_azp_accepted(self):
        token = self.make_token(azp="https://app.example.com")
        with auth_on_env(CLERK_AUTHORIZED_PARTIES="https://app.example.com, https://staging.example.com"):
            claims = verify_clerk_token(token)
        self.assertEqual(claims["azp"], "https://app.example.com")

    def test_absent_azp_accepted(self):
        with auth_on_env(CLERK_AUTHORIZED_PARTIES="https://app.example.com"):
            claims = verify_clerk_token(self.make_token())
        self.assertNotIn("azp", claims)

    def test_garbage_token(self):
        with auth_on_env():
            with self.assertRaises(AuthError) as ctx:
                verify_clerk_token("not-a-jwt")
        self.assertEqual(ctx.exception.code, "auth_required")

    def test_unconfigured_jwks_is_unavailable(self):
        with env(BLUEPRINT_DEPLOYMENT="true"):
            with self.assertRaises(AuthError) as ctx:
                verify_clerk_token(self.make_token())
        self.assertEqual(ctx.exception.code, "auth_unavailable")
        self.assertEqual(ctx.exception.status_code, 503)


class MiddlewareTests(ClerkAuthTestCase):
    def test_noop_when_deployment_mode_off(self):
        with env():
            app, _ = self.call_http("/projects")
        self.assertTrue(app.called)

    def test_noop_when_auth_disabled_escape_hatch(self):
        with env(BLUEPRINT_DEPLOYMENT="true", BLUEPRINT_DISABLE_AUTH="true"):
            app, _ = self.call_http("/projects")
        self.assertTrue(app.called)

    def test_public_paths_pass_without_token(self):
        with auth_on_env():
            for path in ("/", "/debug/config", "/alpha-signups", "/openapi.json", "/docs"):
                app, _ = self.call_http(path)
                self.assertTrue(app.called, f"expected {path} to be public")

    def test_options_preflight_passes_without_token(self):
        with auth_on_env():
            app, _ = self.call_http("/generate", method="OPTIONS")
        self.assertTrue(app.called)

    def test_protected_path_without_token_gets_401(self):
        with auth_on_env():
            app, sent = self.call_http("/projects")
        self.assertFalse(app.called)
        self.assertEqual(self.response_status(sent), 401)
        body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
        self.assertIn(b'"code":"auth_required"', body.replace(b" ", b""))

    def test_valid_session_cookie_passes(self):
        token = self.make_token()
        headers = [(b"cookie", f"foo=bar; __session={token}; theme=dark".encode())]
        with auth_on_env():
            app, _ = self.call_http("/projects", headers=headers)
        self.assertTrue(app.called)
        self.assertEqual(app.scope["state"]["clerk_claims"]["sub"], "user_123")

    def test_valid_bearer_token_passes(self):
        headers = [(b"authorization", f"Bearer {self.make_token()}".encode())]
        with auth_on_env():
            app, _ = self.call_http("/projects", headers=headers)
        self.assertTrue(app.called)

    def test_expired_cookie_gets_401(self):
        token = self.make_token(exp=int(time.time()) - 120)
        headers = [(b"cookie", f"__session={token}".encode())]
        with auth_on_env():
            app, sent = self.call_http("/projects", headers=headers)
        self.assertFalse(app.called)
        self.assertEqual(self.response_status(sent), 401)

    def test_websocket_without_token_closes_1008(self):
        with auth_on_env():
            app, sent = self.call_websocket()
        self.assertFalse(app.called)
        self.assertEqual(sent[0]["type"], "websocket.close")
        self.assertEqual(sent[0]["code"], 1008)

    def test_websocket_with_valid_cookie_passes(self):
        headers = [(b"cookie", f"__session={self.make_token()}".encode())]
        with auth_on_env():
            app, _ = self.call_websocket(headers=headers)
        self.assertTrue(app.called)


class ConfigTests(ClerkAuthTestCase):
    def test_jwks_url_derived_from_publishable_key(self):
        host = "foo-bar-12.clerk.accounts.dev$"
        key = "pk_test_" + base64.b64encode(host.encode()).decode().rstrip("=")
        with env(NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=key):
            self.assertEqual(
                clerk_jwks_url(),
                "https://foo-bar-12.clerk.accounts.dev/.well-known/jwks.json",
            )

    def test_explicit_jwks_url_wins(self):
        with env(CLERK_JWKS_URL=JWKS_URL, NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY="pk_test_whatever"):
            self.assertEqual(clerk_jwks_url(), JWKS_URL)

    def test_jwks_url_none_when_unconfigured(self):
        with env():
            self.assertIsNone(clerk_jwks_url())

    def test_deployment_runtime_config_reports_auth_required(self):
        with auth_on_env():
            config = deployment_runtime_config({})
        self.assertTrue(config["auth_required"])

        with env(BLUEPRINT_DEPLOYMENT="true", BLUEPRINT_DISABLE_AUTH="true"):
            config = deployment_runtime_config({})
        self.assertFalse(config["auth_required"])

        with env():
            config = deployment_runtime_config({})
        self.assertFalse(config["auth_required"])

    def test_startup_validation_raises_without_clerk_config(self):
        with env(BLUEPRINT_DEPLOYMENT="true"):
            with self.assertRaises(RuntimeError):
                validate_auth_startup()

    def test_startup_validation_passes_when_configured(self):
        with auth_on_env(CLERK_AUTHORIZED_PARTIES="https://app.example.com"):
            validate_auth_startup()

    def test_startup_validation_noop_when_auth_off(self):
        with env():
            validate_auth_startup()


if __name__ == "__main__":
    unittest.main()
