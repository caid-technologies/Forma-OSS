import os
from typing import Any, Dict, Optional


ALPHA_GENERATION_UNAVAILABLE_MESSAGE = "Generation is not available in this alpha deployment yet."


class AlphaGenerationUnavailableError(RuntimeError):
    """Raised when deployment mode should route users to the alpha signup flow."""


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def blueprint_dev_mode_enabled() -> bool:
    return env_bool("BLUEPRINT_DEV_MODE")


def deployment_mode_enabled() -> bool:
    return any(
        env_bool(name)
        for name in (
            "BLUEPRINT_DEPLOYMENT",
            "BLUEPRINT_DEPLOYMENT_MODE",
            "DEPLOYMENT",
            "DEPLOYMENT_MODE",
            "NEXT_PUBLIC_BLUEPRINT_DEPLOYMENT",
        )
    )


def deployment_runtime_config(
    llm_config: Dict[str, Any],
    *,
    signup_storage: Optional[str] = None,
) -> Dict[str, Any]:
    deployment_enabled = deployment_mode_enabled()
    live_generation_enabled = bool(llm_config.get("live_generation_enabled"))
    config = {
        "enabled": deployment_enabled,
        "alpha_generation_gate_active": deployment_enabled and not live_generation_enabled,
        "generation_available": (not deployment_enabled) or live_generation_enabled,
    }
    if signup_storage:
        config["signup_storage"] = signup_storage
    return config
