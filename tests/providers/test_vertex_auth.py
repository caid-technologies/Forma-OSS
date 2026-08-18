from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import patch

from google.auth import identity_pool

from blueprint_core.vertex_auth import (
    VercelOidcContextMiddleware,
    _VercelOidcTokenSupplier,
    bind_vertex_oidc_token,
    build_vertex_credentials,
    current_vertex_oidc_token,
    reset_vertex_oidc_token,
)


class VertexAuthTests(unittest.TestCase):
    def test_builds_workload_identity_credentials_from_vercel_configuration(self) -> None:
        environment = {
            "GCP_PROJECT_NUMBER": "123456789",
            "GCP_SERVICE_ACCOUNT_EMAIL": "vertex@example.iam.gserviceaccount.com",
            "GCP_WORKLOAD_IDENTITY_POOL_ID": "vercel",
            "GCP_WORKLOAD_IDENTITY_POOL_PROVIDER_ID": "vercel",
        }
        context_token = bind_vertex_oidc_token("signed-vercel-token")
        try:
            with patch.dict(os.environ, environment, clear=True):
                credentials = build_vertex_credentials()
        finally:
            reset_vertex_oidc_token(context_token)

        self.assertIsInstance(credentials, identity_pool.Credentials)
        assert credentials is not None
        self.assertEqual("vertex@example.iam.gserviceaccount.com", credentials.service_account_email)

    def test_missing_workload_identity_configuration_keeps_adc_fallback(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(build_vertex_credentials())

    def test_subject_supplier_reads_the_request_context(self) -> None:
        context_token = bind_vertex_oidc_token("request-token")
        try:
            token = _VercelOidcTokenSupplier().get_subject_token(None, None)
        finally:
            reset_vertex_oidc_token(context_token)

        self.assertEqual("request-token", token)
        self.assertIsNone(current_vertex_oidc_token())

    def test_middleware_binds_and_resets_vercel_header(self) -> None:
        observed: list[str | None] = []

        async def inner(scope, receive, send):
            del scope, receive, send
            observed.append(current_vertex_oidc_token())

        middleware = VercelOidcContextMiddleware(inner)

        async def invoke() -> None:
            await middleware(
                {
                    "type": "http",
                    "headers": [(b"x-vercel-oidc-token", b"runtime-token")],
                },
                None,
                None,
            )

        asyncio.run(invoke())

        self.assertEqual(["runtime-token"], observed)
        self.assertIsNone(current_vertex_oidc_token())


if __name__ == "__main__":
    unittest.main()
