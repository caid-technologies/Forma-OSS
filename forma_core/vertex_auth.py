"""Google Cloud credentials for Vertex AI across local ADC and Vercel OIDC."""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any

from google.auth import identity_pool
from google.auth.exceptions import RefreshError

from forma_core.config import config


_VERTEX_OIDC_TOKEN: ContextVar[str | None] = ContextVar("vertex_oidc_token", default=None)
_CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
_SUBJECT_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:jwt"


def bind_vertex_oidc_token(token: str | None) -> Token[str | None]:
    """Bind the Vercel-issued request token for provider construction in this context."""

    return _VERTEX_OIDC_TOKEN.set(str(token or "").strip() or None)


def reset_vertex_oidc_token(token: Token[str | None]) -> None:
    _VERTEX_OIDC_TOKEN.reset(token)


def current_vertex_oidc_token() -> str | None:
    """Return a request token, falling back to Vercel's local/build-time variable."""

    return _VERTEX_OIDC_TOKEN.get() or str(config.get("VERCEL_OIDC_TOKEN") or "").strip() or None


class VercelOidcContextMiddleware:
    """Expose Vercel's runtime OIDC header through the active async context."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        oidc_token = None
        if scope.get("type") in {"http", "websocket"}:
            headers = {
                key.lower(): value
                for key, value in scope.get("headers", [])
                if isinstance(key, bytes) and isinstance(value, bytes)
            }
            raw_token = headers.get(b"x-vercel-oidc-token")
            oidc_token = raw_token.decode("utf-8", errors="ignore") if raw_token else None

        context_token = bind_vertex_oidc_token(oidc_token)
        try:
            await self.app(scope, receive, send)
        finally:
            reset_vertex_oidc_token(context_token)


class _VercelOidcTokenSupplier(identity_pool.SubjectTokenSupplier):
    def get_subject_token(self, context: Any, request: Any) -> str:
        del context, request
        token = current_vertex_oidc_token()
        if not token:
            raise RefreshError("Vercel OIDC token is unavailable for Vertex AI authentication.")
        return token


def build_vertex_credentials() -> identity_pool.Credentials | None:
    """Build short-lived GCP credentials when Vercel workload identity is configured."""

    project_number = str(config.get("GCP_PROJECT_NUMBER") or "").strip()
    service_account_email = str(config.get("GCP_SERVICE_ACCOUNT_EMAIL") or "").strip()
    pool_id = str(config.get("GCP_WORKLOAD_IDENTITY_POOL_ID") or "").strip()
    provider_id = str(config.get("GCP_WORKLOAD_IDENTITY_POOL_PROVIDER_ID") or "").strip()
    if not all((project_number, service_account_email, pool_id, provider_id, current_vertex_oidc_token())):
        return None

    audience = (
        f"//iam.googleapis.com/projects/{project_number}/locations/global/"
        f"workloadIdentityPools/{pool_id}/providers/{provider_id}"
    )
    impersonation_url = (
        "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/"
        f"{service_account_email}:generateAccessToken"
    )
    return identity_pool.Credentials(
        audience=audience,
        subject_token_type=_SUBJECT_TOKEN_TYPE,
        subject_token_supplier=_VercelOidcTokenSupplier(),
        service_account_impersonation_url=impersonation_url,
        scopes=[_CLOUD_PLATFORM_SCOPE],
    )
