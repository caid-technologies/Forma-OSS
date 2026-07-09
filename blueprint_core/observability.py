from __future__ import annotations

import json
import logging
import os
import sys
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

try:
    from langfuse import get_client, propagate_attributes
except ImportError as exc:  # pragma: no cover - exercised when optional dep is absent
    get_client = None
    propagate_attributes = None
    _LANGFUSE_IMPORT_ERROR = str(exc)
else:
    _LANGFUSE_IMPORT_ERROR = None


DEFAULT_MAX_FIELD_CHARS = 20000


class NoopObservation:
    def update(self, **_: Any) -> None:
        return None


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name)
    if value is None:
        return default
    stripped = value.strip()
    return stripped if stripped else default


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _max_field_chars() -> int:
    raw_value = _env("LANGFUSE_MAX_FIELD_CHARS")
    if raw_value is None:
        return DEFAULT_MAX_FIELD_CHARS
    try:
        return max(1000, int(raw_value))
    except ValueError:
        logger.warning("Invalid LANGFUSE_MAX_FIELD_CHARS=%r; using %s.", raw_value, DEFAULT_MAX_FIELD_CHARS)
        return DEFAULT_MAX_FIELD_CHARS


def _keys_configured() -> bool:
    return bool(_env("LANGFUSE_PUBLIC_KEY") and _env("LANGFUSE_SECRET_KEY"))


def langfuse_enabled() -> bool:
    if os.getenv("LANGFUSE_ENABLED") is not None:
        return _env_bool("LANGFUSE_ENABLED")
    return _keys_configured()


def get_langfuse_debug_config() -> Dict[str, Any]:
    enabled = langfuse_enabled()
    reason = None
    if os.getenv("LANGFUSE_ENABLED") is not None and not enabled:
        reason = "LANGFUSE_ENABLED is false."
    elif not enabled:
        reason = "Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY to enable tracing."
    elif get_client is None:
        reason = f"Langfuse SDK import failed: {_LANGFUSE_IMPORT_ERROR}"
    elif not _keys_configured():
        reason = "LANGFUSE_ENABLED is true, but Langfuse project keys are missing."

    return {
        "enabled": bool(enabled and get_client is not None and _keys_configured()),
        "installed": get_client is not None,
        "public_key_configured": bool(_env("LANGFUSE_PUBLIC_KEY")),
        "secret_key_configured": bool(_env("LANGFUSE_SECRET_KEY")),
        "base_url": _env("LANGFUSE_BASE_URL", "https://cloud.langfuse.com"),
        "environment": _env("LANGFUSE_TRACING_ENVIRONMENT"),
        "release": _env("LANGFUSE_TRACING_RELEASE"),
        "max_field_chars": _max_field_chars(),
        "reason": reason,
    }


def serialize_for_langfuse(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        value = value.model_dump()

    try:
        serialized = json.dumps(value, default=str)
    except TypeError:
        serialized = str(value)

    max_chars = _max_field_chars()
    if len(serialized) <= max_chars:
        try:
            return json.loads(serialized)
        except json.JSONDecodeError:
            return serialized

    return {
        "truncated": True,
        "chars": len(serialized),
        "preview": serialized[:max_chars],
    }


def _client_enabled() -> bool:
    return bool(langfuse_enabled() and get_client is not None and _keys_configured())


@contextmanager
def start_observation(
    *,
    name: str,
    as_type: str = "span",
    input: Any = None,
    model: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Iterator[Any]:
    if not _client_enabled():
        yield NoopObservation()
        return

    try:
        client = get_client()
        kwargs: Dict[str, Any] = {
            "as_type": as_type,
            "name": name,
        }
        serialized_input = serialize_for_langfuse(input)
        if serialized_input is not None:
            kwargs["input"] = serialized_input
        if model:
            kwargs["model"] = model
        if metadata:
            kwargs["metadata"] = serialize_for_langfuse(metadata)

        manager = client.start_as_current_observation(**kwargs)
        observation = manager.__enter__()
    except Exception as exc:  # pragma: no cover - defensive against SDK/env failures
        logger.warning("Langfuse observation %s could not start: %s", name, exc)
        yield NoopObservation()
        return

    exc_info = (None, None, None)
    try:
        yield observation
    except BaseException:
        exc_info = sys.exc_info()
        try:
            observation.update(
                metadata=serialize_for_langfuse(
                    {
                        "error_type": exc_info[0].__name__ if exc_info[0] else "Error",
                        "error": str(exc_info[1])[:1000] if exc_info[1] else "",
                    }
                )
            )
        except Exception:
            logger.debug("Langfuse observation error update failed.", exc_info=True)
        raise
    finally:
        try:
            manager.__exit__(*exc_info)
        except Exception as exc:  # pragma: no cover - defensive against SDK/env failures
            logger.warning("Langfuse observation %s could not close: %s", name, exc)


@contextmanager
def propagate_observation_attributes(
    *,
    trace_name: str,
    metadata: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None,
) -> Iterator[None]:
    if not _client_enabled() or propagate_attributes is None:
        yield
        return

    try:
        manager = propagate_attributes(
            trace_name=trace_name,
            metadata=serialize_for_langfuse(metadata or {}),
            tags=tags or [],
        )
        manager.__enter__()
    except Exception as exc:  # pragma: no cover - defensive against SDK/env failures
        logger.warning("Langfuse attribute propagation failed: %s", exc)
        yield
        return

    exc_info = (None, None, None)
    try:
        yield
    except BaseException:
        exc_info = sys.exc_info()
        raise
    finally:
        try:
            manager.__exit__(*exc_info)
        except Exception as exc:  # pragma: no cover - defensive against SDK/env failures
            logger.warning("Langfuse attribute propagation could not close: %s", exc)


def update_observation(observation: Any, **kwargs: Any) -> None:
    if observation is None:
        return

    payload = {
        key: serialize_for_langfuse(value)
        for key, value in kwargs.items()
        if value is not None
    }
    if not payload:
        return

    try:
        observation.update(**payload)
    except Exception:  # pragma: no cover - defensive against SDK/env failures
        logger.debug("Langfuse observation update failed.", exc_info=True)


def flush_langfuse() -> None:
    if not _client_enabled():
        return

    try:
        get_client().flush()
    except Exception as exc:  # pragma: no cover - defensive against SDK/env failures
        logger.warning("Langfuse flush failed: %s", exc)
