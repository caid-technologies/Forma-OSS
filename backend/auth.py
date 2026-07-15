"""Clerk authentication enforcement for hosted deployments.

Auth is only enforced when deployment mode is enabled (see
blueprint_core.runtime_config.auth_required_enabled). Self-hosted and local
development instances run without any Clerk configuration or auth checks.

The frontend and backend share an origin in hosted deployments (backend
reverse-proxied at /api), so the Clerk ``__session`` cookie flows to FastAPI
automatically and is verified here against Clerk's JWKS.
"""

import base64
import functools
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import jwt
from fastapi import HTTPException
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError, PyJWKClientError
from starlette.responses import JSONResponse

from blueprint_core.runtime import auth_required_enabled

logger = logging.getLogger(__name__)

SESSION_COOKIE_NAME = "__session"

# Paths (after /api prefix stripping) that stay reachable without a session.
PUBLIC_PATHS = {
    "/",
    "/debug/config",
    "/alpha-signups",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/docs/oauth2-redirect",
}


class AuthError(Exception):
    """Authentication failure with an API error code and HTTP status."""

    def __init__(self, code: str, message: str, status_code: int = 401) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def clerk_jwks_url() -> Optional[str]:
    """Resolve the Clerk JWKS URL.

    CLERK_JWKS_URL wins when set; otherwise the Frontend API host is derived
    from the publishable key (``pk_test_``/``pk_live_`` + base64("host$")).
    """
    explicit = os.getenv("CLERK_JWKS_URL", "").strip()
    if explicit:
        return explicit

    publishable = os.getenv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", "").strip()
    for prefix in ("pk_test_", "pk_live_"):
        if publishable.startswith(prefix):
            encoded = publishable[len(prefix):]
            padded = encoded + "=" * (-len(encoded) % 4)
            try:
                host = base64.b64decode(padded).decode("utf-8").rstrip("$").strip()
            except Exception:
                logger.warning("Could not decode Clerk publishable key to derive the JWKS URL.")
                return None
            if host:
                return f"https://{host}/.well-known/jwks.json"
    return None


def clerk_authorized_parties() -> List[str]:
    raw = os.getenv("CLERK_AUTHORIZED_PARTIES", "")
    return [party.strip() for party in raw.split(",") if party.strip()]


@functools.lru_cache(maxsize=4)
def _jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_keys=True, lifespan=3600)


def verify_clerk_token(token: str) -> Dict[str, Any]:
    """Verify a Clerk session JWT against the instance JWKS.

    Returns the verified claims. Raises AuthError with status 401 for invalid
    tokens and 503 when Clerk/JWKS is unreachable or unconfigured.
    """
    url = clerk_jwks_url()
    if not url:
        raise AuthError("auth_unavailable", "Authentication is not configured on this server.", 503)

    try:
        signing_key = _jwks_client(url).get_signing_key_from_jwt(token)
    except PyJWKClientConnectionError as exc:
        raise AuthError("auth_unavailable", "Authentication service is unavailable.", 503) from exc
    except (PyJWKClientError, jwt.InvalidTokenError) as exc:
        raise AuthError("auth_required", "Invalid session token.") from exc

    try:
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            leeway=10,
            options={"verify_aud": False},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("auth_required", "Session token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError("auth_required", "Invalid session token.") from exc

    parties = clerk_authorized_parties()
    azp = claims.get("azp")
    if parties and azp and azp not in parties:
        raise AuthError("auth_required", "Session token is not from an authorized party.")

    return claims


def _extract_token(headers: List[Tuple[bytes, bytes]]) -> Optional[str]:
    """Pull the Clerk session JWT from ASGI headers (cookie, then bearer)."""
    cookie_parts: List[str] = []
    bearer: Optional[str] = None
    for name, value in headers:
        if name == b"cookie":
            cookie_parts.append(value.decode("latin-1"))
        elif name == b"authorization" and bearer is None:
            decoded = value.decode("latin-1").strip()
            if decoded.lower().startswith("bearer "):
                bearer = decoded[7:].strip() or None

    for part in "; ".join(cookie_parts).split(";"):
        key, _, value = part.strip().partition("=")
        if key == SESSION_COOKIE_NAME and value:
            return value
    return bearer


class ClerkAuthMiddleware:
    """Raw ASGI middleware enforcing Clerk auth on HTTP and WebSocket scopes.

    Must be registered so it runs inside ApiPrefixCompatibilityMiddleware
    (i.e. added to the app *before* it) so paths are already /api-stripped.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") not in {"http", "websocket"} or not auth_required_enabled():
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if scope["type"] == "http" and (scope.get("method") == "OPTIONS" or path in PUBLIC_PATHS):
            await self.app(scope, receive, send)
            return

        token = _extract_token(scope.get("headers") or [])
        try:
            if not token:
                raise AuthError("auth_required", "Authentication required.")
            claims = verify_clerk_token(token)
        except AuthError as err:
            if scope["type"] == "websocket":
                await receive()  # consume websocket.connect
                await send({"type": "websocket.close", "code": 1008, "reason": err.code})
                return
            response = JSONResponse(
                {"detail": {"code": err.code, "message": err.message}},
                status_code=err.status_code,
            )
            await response(scope, receive, send)
            return

        scope = dict(scope)
        state = dict(scope.get("state") or {})
        state["clerk_claims"] = claims
        scope["state"] = state
        await self.app(scope, receive, send)


def current_owner_id(request: Any) -> Optional[str]:
    """Clerk user id (``sub``) from verified claims; None when auth is off/absent."""
    claims = (request.scope.get("state") or {}).get("clerk_claims") or {}
    sub = claims.get("sub")
    return str(sub) if sub else None


def ensure_project_access(project: Any, request: Any) -> None:
    """Raise 404 when auth is on and the project is not owned by the caller.

    Strictly private: foreign, unowned (legacy/A2A-created), and nonexistent
    projects are indistinguishable to non-owners. No-op when auth is off.
    """
    if not auth_required_enabled():
        return
    owner = current_owner_id(request)
    if not owner or getattr(project, "owner_id", None) != owner:
        raise HTTPException(status_code=404, detail="Project not found.")


def validate_auth_startup() -> None:
    """Fail fast when deployment mode requires auth but Clerk is unconfigured."""
    if not auth_required_enabled():
        return
    if not clerk_jwks_url():
        logger.critical(
            "Deployment mode is enabled but no Clerk configuration was found. "
            "Set CLERK_JWKS_URL or NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY, or set "
            "BLUEPRINT_DISABLE_AUTH=true to run deployment mode without auth."
        )
        raise RuntimeError("Clerk auth is required in deployment mode but is not configured.")
    if not clerk_authorized_parties():
        logger.warning(
            "CLERK_AUTHORIZED_PARTIES is not set; the JWT azp claim will not be validated."
        )
