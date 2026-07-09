from __future__ import annotations

import os
import re
import traceback
from typing import Any, Dict, Optional


DEBUG_ENV_VARS = ("BLUEPRINT_DEBUG", "BLUEPRINT_DEBUG_MODE", "API_DEBUG", "DEBUG")
SECRET_KEY_PATTERN = re.compile(r"(api[_-]?key|authorization|bearer|password|secret|token|credential)", re.IGNORECASE)
SECRET_TEXT_PATTERNS = [
    re.compile(r"\b(sk-proj-[A-Za-z0-9._-]{8,})"),
    re.compile(r"\b(sk-[A-Za-z0-9._-]{8,})"),
    re.compile(r"\b(sk-lf-[A-Za-z0-9._-]{8,})"),
    re.compile(r"\b(pk-lf-[A-Za-z0-9._-]{8,})"),
    re.compile(r"\b(rpa_[A-Za-z0-9._-]{8,})"),
    re.compile(r"\b(nvapi-[A-Za-z0-9._-]{8,})"),
    re.compile(r"\b(fc-[A-Za-z0-9._-]{8,})"),
    re.compile(r"(?i)(api[_-]?key|authorization|bearer|password|secret|token)\s*[:=]\s*([^\s,'\"]{8,})"),
]


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def debug_mode_enabled() -> bool:
    return any(_env_bool(name) for name in DEBUG_ENV_VARS)


def get_debug_mode_config() -> Dict[str, Any]:
    return {
        "enabled": debug_mode_enabled(),
        "env_vars": [name for name in DEBUG_ENV_VARS if os.getenv(name) is not None],
    }


def redact_debug_value(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: Dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if SECRET_KEY_PATTERN.search(key_text):
                redacted[key] = "<redacted>"
            else:
                redacted[key] = redact_debug_value(item)
        return redacted
    if isinstance(value, list):
        return [redact_debug_value(item) for item in value]
    if isinstance(value, tuple):
        return [redact_debug_value(item) for item in value]
    if isinstance(value, str):
        return redact_debug_text(value)
    return value


def redact_debug_text(value: str) -> str:
    redacted = value
    for pattern in SECRET_TEXT_PATTERNS:
        if pattern.groups >= 2:
            redacted = pattern.sub(lambda match: f"{match.group(1)}=<redacted>", redacted)
        else:
            redacted = pattern.sub("<redacted>", redacted)
    return redacted


def exception_debug_payload(
    exc: BaseException,
    *,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "error_type": exc.__class__.__name__,
        "error": redact_debug_text(str(exc)),
        "traceback": redact_debug_text("".join(traceback.format_exception(type(exc), exc, exc.__traceback__))),
    }
    if context:
        payload["context"] = redact_debug_value(context)
    return payload


def api_error_detail(
    *,
    code: str,
    message: str,
    exc: Optional[BaseException] = None,
    job_id: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    detail: Dict[str, Any] = {
        "code": code,
        "message": redact_debug_text(message),
    }
    if job_id:
        detail["job_id"] = job_id
    if provider:
        detail["provider"] = provider
    if model:
        detail["model"] = model
    if debug_mode_enabled() and exc is not None:
        detail["debug"] = exception_debug_payload(exc, context=context)
    elif debug_mode_enabled() and context:
        detail["debug"] = {"context": redact_debug_value(context)}
    return detail
