import base64
import hashlib
import json
import os
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Dict, List, Optional, Set
from urllib import request as urllib_request

import jwt
from fastapi import HTTPException, Request, status
from jwt import PyJWKClient


def _truthy(value: Optional[str]) -> bool:
    return bool(value and value.strip().lower() in {"1", "true", "yes", "on"})


def _csv_env(name: str) -> Set[str]:
    return {
        item.strip()
        for item in (os.getenv(name) or "").replace("\n", ",").split(",")
        if item.strip()
    }


def deployed_auth_required() -> bool:
    explicit = os.getenv("BLUEPRINT_AUTH_REQUIRED")
    if explicit is not None:
        return _truthy(explicit)
    return os.getenv("VERCEL") == "1" or bool(os.getenv("VERCEL_ENV"))


def _deployed_runtime() -> bool:
    return deployed_auth_required() or _truthy(os.getenv("BLUEPRINT_DEPLOYMENT")) or _truthy(os.getenv("BLUEPRINT_DEPLOYMENT_MODE"))


def env_user_api_keys_allowed() -> bool:
    if _truthy(os.getenv("BLUEPRINT_ALLOW_ENV_USER_API_KEYS")):
        return True
    return not _deployed_runtime()


def _issuer_from_publishable_key(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    key = value.strip()
    for prefix in ("pk_test_", "pk_live_"):
        if not key.startswith(prefix):
            continue
        encoded = key.removeprefix(prefix)
        encoded = encoded.split("$", 1)[0]
        padding = "=" * (-len(encoded) % 4)
        try:
            decoded = base64.b64decode(f"{encoded}{padding}").decode("utf-8").strip().strip("$")
        except Exception:
            return None
        if not decoded:
            return None
        return decoded if decoded.startswith("https://") else f"https://{decoded}"
    return None


def clerk_issuer() -> Optional[str]:
    issuer = (
        os.getenv("CLERK_JWT_ISSUER")
        or os.getenv("CLERK_ISSUER")
        or os.getenv("CLERK_FRONTEND_API_URL")
        or _issuer_from_publishable_key(os.getenv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY") or os.getenv("CLERK_PUBLISHABLE_KEY"))
    )
    if not issuer:
        return None
    return issuer.rstrip("/")


@lru_cache(maxsize=8)
def _jwk_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url)


def verify_clerk_bearer_token(token: str) -> Dict[str, Any]:
    issuer = clerk_issuer()
    if not issuer:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Auth is required, but Clerk issuer is not configured.",
        )
    try:
        signing_key = _jwk_client(f"{issuer}/.well-known/jwks.json").get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=issuer,
            options={"verify_aud": False},
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired Clerk session.") from exc


def _clerk_secret_key() -> Optional[str]:
    value = os.getenv("CLERK_SECRET_KEY")
    return value.strip() if value and value.strip() else None


def _primary_email_local_part(user: Dict[str, Any]) -> Optional[str]:
    email = _primary_email_address(user)
    if not email:
        return None
    local_part = email.split("@", 1)[0].strip()
    return local_part or None


def _primary_email_address(user: Dict[str, Any]) -> Optional[str]:
    primary_email_id = user.get("primary_email_address_id")
    email_addresses = user.get("email_addresses")
    if not isinstance(email_addresses, list):
        return None
    primary = None
    for item in email_addresses:
        if not isinstance(item, dict):
            continue
        if primary_email_id and item.get("id") == primary_email_id:
            primary = item
            break
        if primary is None:
            primary = item
    email = primary.get("email_address") if isinstance(primary, dict) else None
    if not isinstance(email, str) or "@" not in email:
        return None
    return email.strip().lower()


def _display_name_from_clerk_user(user: Dict[str, Any]) -> Optional[str]:
    username = user.get("username")
    if isinstance(username, str) and username.strip():
        return username.strip()

    first_name = user.get("first_name")
    last_name = user.get("last_name")
    full_name = " ".join(
        part.strip()
        for part in (first_name, last_name)
        if isinstance(part, str) and part.strip()
    )
    if full_name:
        return full_name

    return _primary_email_local_part(user)


@lru_cache(maxsize=512)
def clerk_user_profile(user_id: str) -> Optional[Dict[str, Optional[str]]]:
    normalized_user_id = str(user_id or "").strip()
    secret_key = _clerk_secret_key()
    if not normalized_user_id or not secret_key:
        return None

    url = f"https://api.clerk.com/v1/users/{normalized_user_id}"
    request = urllib_request.Request(
        url,
        headers={
            "Authorization": f"Bearer {secret_key}",
            "Accept": "application/json",
            "User-Agent": "Blueprint/1.0 (+https://github.com/caid-technologies/blueprint-oss)",
        },
        method="GET",
    )
    try:
        with urllib_request.urlopen(request, timeout=4) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None

    image_url = payload.get("image_url")
    return {
        "display_name": _display_name_from_clerk_user(payload),
        "email": _primary_email_address(payload),
        "image_url": image_url.strip() if isinstance(image_url, str) and image_url.strip().startswith(("http://", "https://")) else None,
    }


def clerk_user_display_name(user_id: str) -> Optional[str]:
    profile = clerk_user_profile(user_id)
    return profile.get("display_name") if profile else None


def clerk_user_image_url(user_id: str) -> Optional[str]:
    profile = clerk_user_profile(user_id)
    return profile.get("image_url") if profile else None


def clerk_user_email(user_id: str) -> Optional[str]:
    profile = clerk_user_profile(user_id)
    return profile.get("email") if profile else None


def _request_bearer_token(request: Request) -> Optional[str]:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        return None
    normalized = token.strip()
    return normalized or None


@dataclass(frozen=True)
class UserApiKeyPrincipal:
    key_id: str
    owner_user_id: str
    scopes: List[str]
    rate_limit_per_minute: Optional[int] = None
    daily_quota: Optional[int] = None


_API_KEY_RATE_LIMIT_EVENTS: Dict[str, List[float]] = {}


def _api_key_id(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:12]


def _configured_user_api_keys() -> Dict[str, UserApiKeyPrincipal]:
    if not env_user_api_keys_allowed():
        return {}
    raw = os.getenv("BLUEPRINT_USER_API_KEYS") or os.getenv("BLUEPRINT_API_KEYS") or ""
    credentials: Dict[str, UserApiKeyPrincipal] = {}
    for item in raw.replace("\n", ",").split(","):
        entry = item.strip()
        if not entry:
            continue

        label: Optional[str] = None
        secret = entry
        for separator in ("=", ":"):
            if separator not in entry:
                continue
            candidate_label, candidate_secret = entry.split(separator, 1)
            if candidate_label.strip() and candidate_secret.strip():
                label = candidate_label.strip()
                secret = candidate_secret.strip()
                break

        if not secret:
            continue
        key_id = label or _api_key_id(secret)
        credentials[secret] = UserApiKeyPrincipal(key_id=key_id, owner_user_id=f"api:{key_id}", scopes=["*"])
    return credentials


def user_api_key_auth_configured() -> bool:
    return bool(_configured_user_api_keys())


def _request_user_api_key(request: Request) -> Optional[str]:
    header_key = (
        request.headers.get("x-blueprint-api-key")
        or request.headers.get("x-api-key")
    )
    if header_key and header_key.strip():
        return header_key.strip()
    return _request_bearer_token(request)


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _api_key_is_expired(value: Any) -> bool:
    expires_at = _parse_iso_datetime(value)
    return bool(expires_at and expires_at <= datetime.now(timezone.utc))


def _enforce_in_memory_rate_limit(key_id: str, limit: Optional[int]) -> None:
    if not limit or limit <= 0:
        return
    now = time.time()
    window_start = now - 60.0
    events = [event for event in _API_KEY_RATE_LIMIT_EVENTS.get(key_id, []) if event >= window_start]
    if len(events) >= limit:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="API key rate limit exceeded.")
    events.append(now)
    _API_KEY_RATE_LIMIT_EVENTS[key_id] = events


def _database_api_key_principal(secret: str) -> Optional[UserApiKeyPrincipal]:
    try:
        from blueprint_core.api_keys import current_usage_date, validate_managed_api_key_hashing_config
        from blueprint_core.database import get_user_api_key_by_secret, record_user_api_key_use
    except Exception:
        return None

    try:
        validate_managed_api_key_hashing_config()
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    record = get_user_api_key_by_secret(secret)
    if not record:
        return None
    if getattr(record, "status", None) != "active" or getattr(record, "revoked_at", None):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key has been revoked.")
    if _api_key_is_expired(getattr(record, "expires_at", None)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key has expired.")

    key_id = str(getattr(record, "key_id", "") or "")
    daily_quota = getattr(record, "daily_quota", None)
    daily_usage_count = int(getattr(record, "daily_usage_count", 0) or 0)
    if getattr(record, "daily_usage_date", None) != current_usage_date():
        daily_usage_count = 0
    if daily_quota and daily_usage_count >= int(daily_quota):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="API key daily quota exceeded.")

    rate_limit = getattr(record, "rate_limit_per_minute", None)
    _enforce_in_memory_rate_limit(key_id, int(rate_limit) if rate_limit else None)
    updated = record_user_api_key_use(key_id) or record
    return UserApiKeyPrincipal(
        key_id=key_id,
        owner_user_id=str(getattr(updated, "owner_user_id", "") or ""),
        scopes=list(getattr(updated, "scopes", None) or []),
        rate_limit_per_minute=int(rate_limit) if rate_limit else None,
        daily_quota=int(daily_quota) if daily_quota else None,
    )


async def require_user_api_key(request: Request) -> UserApiKeyPrincipal:
    credentials = _configured_user_api_keys()
    supplied_key = _request_user_api_key(request)
    if not supplied_key:
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="User API access is not configured. Create an API key or set BLUEPRINT_USER_API_KEYS on the backend.",
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key required.")

    database_principal = _database_api_key_principal(supplied_key)
    if database_principal:
        return database_principal

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )

    for expected_key, principal in credentials.items():
        if secrets.compare_digest(supplied_key, expected_key):
            return principal

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key.")


async def require_deployed_clerk_auth(request: Request) -> Optional[Dict[str, Any]]:
    token = _request_bearer_token(request)
    if token:
        return verify_clerk_bearer_token(token)
    if not deployed_auth_required():
        return None
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in to use Blueprint generation.")


async def require_deployed_user_id(request: Request) -> str:
    auth_claims = await require_deployed_clerk_auth(request)
    user_id = clerk_user_id(auth_claims)
    if user_id:
        return user_id
    if not deployed_auth_required():
        return "local-dev-user"
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in to manage API keys.")


async def optional_deployed_clerk_auth(request: Request) -> Optional[Dict[str, Any]]:
    token = _request_bearer_token(request)
    if token:
        return verify_clerk_bearer_token(token)
    return None


def clerk_user_id(auth_claims: Optional[Dict[str, Any]]) -> Optional[str]:
    if not auth_claims:
        return None
    value = auth_claims.get("sub")
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def clerk_user_is_admin(auth_claims: Optional[Dict[str, Any]]) -> bool:
    if not deployed_auth_required():
        return True

    user_id = clerk_user_id(auth_claims)
    if not user_id:
        return False

    admin_user_ids = _csv_env("BLUEPRINT_ADMIN_USER_IDS") | _csv_env("CLERK_ADMIN_USER_IDS")
    if user_id in admin_user_ids:
        return True

    public_metadata = auth_claims.get("public_metadata") if isinstance(auth_claims, dict) else None
    private_metadata = auth_claims.get("private_metadata") if isinstance(auth_claims, dict) else None
    for metadata in (public_metadata, private_metadata):
        if isinstance(metadata, dict) and metadata.get("role") == "admin":
            return True
        if isinstance(metadata, dict) and metadata.get("admin") is True:
            return True

    admin_emails = {email.lower() for email in (_csv_env("BLUEPRINT_ADMIN_EMAILS") | _csv_env("CLERK_ADMIN_EMAILS"))}
    email = clerk_user_email(user_id)
    return bool(email and email.lower() in admin_emails)


async def require_deployed_admin_auth(request: Request) -> Optional[Dict[str, Any]]:
    auth_claims = await require_deployed_clerk_auth(request)
    if clerk_user_is_admin(auth_claims):
        return auth_claims
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access is required.")
