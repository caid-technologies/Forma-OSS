"""Redis-backed cache for project gallery response payloads.

The cache is deliberately optional. Deployments without ``REDIS_URL`` use the
database exactly as before, and Redis errors never fail project reads or writes.
"""

from __future__ import annotations

import hashlib
import json
import logging
from blueprint_core.config import config
import threading
import time
from typing import Any, Optional

from blueprint_core.config.runtime import blueprint_dev_mode_enabled


logger = logging.getLogger(__name__)

_DEFAULT_TTL_SECONDS = 60
_DEFAULT_SOCKET_TIMEOUT_SECONDS = 0.25
_FAILURE_COOLDOWN_SECONDS = 30.0
_VERSION_KEY_SUFFIX = "version"

_client: Any = None
_client_url: Optional[str] = None
_client_lock = threading.Lock()
_disabled_until = 0.0


def require_project_list_cache_config() -> None:
    """Require explicit Redis settings outside development mode."""
    if blueprint_dev_mode_enabled():
        return

    missing = [
        name
        for name in ("REDIS_URL", "REDIS_CACHE_PREFIX")
        if not config.get(name, "").strip()
    ]
    if not missing:
        return

    names = ", ".join(missing)
    message = (
        "BLUEPRINT_DEV_MODE=false requires Redis project caching. "
        f"Set the following server-only environment variables: {names}."
    )
    logger.critical(message)
    raise RuntimeError(message)


def _bounded_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(config.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(value, maximum))


def _cache_ttl_seconds() -> int:
    return int(_bounded_float("PROJECTS_CACHE_TTL_SECONDS", _DEFAULT_TTL_SECONDS, 1, 3600))


def _cache_prefix() -> str:
    configured = config.get("REDIS_CACHE_PREFIX", "blueprint").strip().strip(":")
    return configured or "blueprint"


def _version_key() -> str:
    return f"{_cache_prefix()}:project-lists:{_VERSION_KEY_SUFFIX}"


def _get_redis_client() -> Any:
    """Return a lazy Redis client without importing redis for uncached installs."""
    global _client, _client_url

    redis_url = config.get("REDIS_URL", "").strip()
    if not redis_url:
        return None
    if _client is not None and _client_url == redis_url:
        return _client

    with _client_lock:
        if _client is not None and _client_url == redis_url:
            return _client
        try:
            import redis
        except ImportError:
            logger.warning("REDIS_URL is configured but the redis package is not installed; project caching is disabled.")
            return None

        timeout = _bounded_float(
            "REDIS_SOCKET_TIMEOUT_SECONDS",
            _DEFAULT_SOCKET_TIMEOUT_SECONDS,
            0.05,
            5.0,
        )
        _client = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=timeout,
            socket_timeout=timeout,
            health_check_interval=30,
        )
        _client_url = redis_url
        return _client


def _available_client() -> Any:
    if time.monotonic() < _disabled_until:
        return None
    return _get_redis_client()


def _record_failure(operation: str, exc: Exception) -> None:
    global _disabled_until
    _disabled_until = time.monotonic() + _FAILURE_COOLDOWN_SECONDS
    logger.warning(
        "Redis project cache %s failed; using the database for %.0f seconds: %s",
        operation,
        _FAILURE_COOLDOWN_SECONDS,
        exc,
    )


def _current_generation(client: Any) -> str:
    value = client.get(_version_key())
    return str(value) if value is not None else "0"


def _identity_key(owner_user_id: Optional[str]) -> str:
    identity = owner_user_id.strip() if isinstance(owner_user_id, str) and owner_user_id.strip() else "anonymous"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def _data_key(scope: str, owner_user_id: Optional[str], generation: str) -> str:
    normalized_scope = "mine" if scope == "mine" else "public"
    return f"{_cache_prefix()}:project-lists:v{generation}:{normalized_scope}:{_identity_key(owner_user_id)}"


def get_cached_project_list(
    scope: str,
    owner_user_id: Optional[str],
) -> tuple[Optional[list[dict[str, Any]]], Optional[str]]:
    """Return a cached response and the generation token used for that lookup."""
    client = _available_client()
    if client is None:
        return None, None
    try:
        generation = _current_generation(client)
        raw_value = client.get(_data_key(scope, owner_user_id, generation))
        if raw_value is None:
            return None, generation
        decoded = json.loads(raw_value)
        if not isinstance(decoded, list) or any(not isinstance(item, dict) for item in decoded):
            raise ValueError("cached project list has an invalid shape")
        return decoded, generation
    except Exception as exc:
        _record_failure("read", exc)
        return None, None


def cache_project_list(
    scope: str,
    owner_user_id: Optional[str],
    projects: list[dict[str, Any]],
    generation: Optional[str],
) -> None:
    """Cache a project list under the generation observed before its DB read.

    Reusing the lookup generation prevents a concurrent write from placing a
    stale database result into the newly invalidated cache generation.
    """
    if generation is None:
        return
    client = _available_client()
    if client is None:
        return
    try:
        client.set(
            _data_key(scope, owner_user_id, generation),
            json.dumps(projects, separators=(",", ":"), ensure_ascii=False),
            ex=_cache_ttl_seconds(),
        )
    except Exception as exc:
        _record_failure("write", exc)


def invalidate_project_lists() -> None:
    """Move all project-list readers to a fresh cache generation."""
    client = _available_client()
    if client is None:
        return
    try:
        client.incr(_version_key())
    except Exception as exc:
        _record_failure("invalidation", exc)
