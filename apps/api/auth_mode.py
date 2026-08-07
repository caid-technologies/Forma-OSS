"""Explicit authentication mode for the Forma backend."""

from __future__ import annotations

import logging
from blueprint_core.config import config
from typing import Literal


logger = logging.getLogger(__name__)

AuthMode = Literal["local", "clerk"]
AUTH_MODE_ENV = "BLUEPRINT_AUTH_MODE"
AUTH_MODES = {"local", "clerk"}


def blueprint_auth_mode() -> AuthMode:
    """Return the explicitly configured authentication mode."""
    value = (config.get(AUTH_MODE_ENV) or "").strip().lower()
    if not value:
        message = f"{AUTH_MODE_ENV} is required. Expected 'local' or 'clerk'."
        logger.critical(message)
        raise RuntimeError(message)
    if value not in AUTH_MODES:
        message = (
            f"Invalid {AUTH_MODE_ENV}={value!r}. "
            "Expected 'local' or 'clerk'."
        )
        logger.critical(message)
        raise RuntimeError(message)
    return value  # type: ignore[return-value]


def clerk_auth_required() -> bool:
    return blueprint_auth_mode() == "clerk"


__all__ = ["AUTH_MODE_ENV", "AuthMode", "blueprint_auth_mode", "clerk_auth_required"]
