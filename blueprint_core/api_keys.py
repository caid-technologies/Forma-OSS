from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from blueprint_core.runtime_config import deployment_mode_enabled, env_bool


DEFAULT_API_KEY_SCOPES = ("generate:project", "read:job")
DEFAULT_RATE_LIMIT_PER_MINUTE = 30
DEFAULT_DAILY_QUOTA = 100
API_KEY_SECRET_PREFIX = "bp_live_"
API_KEY_PREFIX_CHARS = 18
API_KEY_ID_CHARS = 12
SCOPE_PATTERN = re.compile(r"^[a-z][a-z0-9_:-]{1,63}$")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def current_usage_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def normalize_api_key_name(value: Optional[str]) -> str:
    normalized = str(value or "").strip()
    return normalized[:80] or "Untitled API key"


def normalize_api_key_scopes(scopes: Optional[Iterable[Any]]) -> list[str]:
    normalized: list[str] = []
    for scope in scopes or DEFAULT_API_KEY_SCOPES:
        value = str(scope or "").strip().lower()
        if value and SCOPE_PATTERN.fullmatch(value) and value not in normalized:
            normalized.append(value)
    return normalized or list(DEFAULT_API_KEY_SCOPES)


def generate_api_key_secret() -> str:
    return f"{API_KEY_SECRET_PREFIX}{secrets.token_urlsafe(32)}"


def api_key_secret_prefix(secret: str) -> str:
    return secret[:API_KEY_PREFIX_CHARS]


def api_key_pepper() -> str:
    return (os.getenv("BLUEPRINT_API_KEY_PEPPER") or os.getenv("API_KEY_PEPPER") or "").strip()


def managed_api_key_pepper_required() -> bool:
    if env_bool("BLUEPRINT_REQUIRE_API_KEY_PEPPER"):
        return True
    if env_bool("BLUEPRINT_ALLOW_UNPEPPERED_API_KEY_HASHES"):
        return False
    return deployment_mode_enabled() or bool(os.getenv("VERCEL") == "1" or os.getenv("VERCEL_ENV"))


def api_key_hash_algorithm() -> str:
    return "hmac-sha256" if api_key_pepper() else "sha256"


def validate_managed_api_key_hashing_config() -> None:
    if managed_api_key_pepper_required() and not api_key_pepper():
        raise RuntimeError(
            "BLUEPRINT_API_KEY_PEPPER is required for managed user API keys in deployed environments."
        )


def api_key_hash(secret: str, *, require_production_pepper: bool = True) -> str:
    normalized = str(secret or "").strip()
    if require_production_pepper:
        validate_managed_api_key_hashing_config()
    pepper = os.getenv("BLUEPRINT_API_KEY_PEPPER") or os.getenv("API_KEY_PEPPER") or ""
    if pepper:
        return hmac.new(pepper.encode("utf-8"), normalized.encode("utf-8"), hashlib.sha256).hexdigest()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def api_key_id_from_hash(key_hash: str) -> str:
    return f"key_{key_hash[:API_KEY_ID_CHARS]}"


def safe_int(value: Any, default: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def api_key_public_payload(record: Any, *, include_secret: Optional[str] = None) -> dict[str, Any]:
    payload = {
        "key_id": getattr(record, "key_id", None),
        "name": getattr(record, "name", None),
        "key_prefix": getattr(record, "key_prefix", None),
        "scopes": list(getattr(record, "scopes", None) or []),
        "status": getattr(record, "status", None),
        "rate_limit_per_minute": getattr(record, "rate_limit_per_minute", None),
        "daily_quota": getattr(record, "daily_quota", None),
        "daily_usage_date": getattr(record, "daily_usage_date", None),
        "daily_usage_count": getattr(record, "daily_usage_count", None),
        "created_at": getattr(record, "created_at", None),
        "last_used_at": getattr(record, "last_used_at", None),
        "expires_at": getattr(record, "expires_at", None),
        "revoked_at": getattr(record, "revoked_at", None),
    }
    if include_secret is not None:
        payload["secret"] = include_secret
    return payload
