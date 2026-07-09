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
    reason = generation_unavailable_reason(llm_config)
    if reason:
        config["generation_unavailable_reason"] = reason
    return config


def _runtime_value(llm_config: Dict[str, Any], key: str) -> Any:
    runtime = llm_config.get("runtime")
    if isinstance(runtime, dict) and runtime.get(key) is not None:
        return runtime.get(key)
    return llm_config.get(key)


def generation_unavailable_reason(llm_config: Dict[str, Any]) -> Optional[str]:
    validation_error = llm_config.get("validation_error")
    if isinstance(validation_error, str) and validation_error.strip():
        return validation_error.strip()

    if not bool(llm_config.get("live_generation_enabled")):
        provider = _runtime_value(llm_config, "runtime_provider") or llm_config.get("provider") or "selected provider"
        model = _runtime_value(llm_config, "runtime_model") or llm_config.get("requested_model") or "selected model"
        return f"{provider}/{model} is not configured for live generation."

    return None


def generation_unavailable_message(llm_config: Dict[str, Any]) -> str:
    reason = generation_unavailable_reason(llm_config)
    if reason:
        provider = _runtime_value(llm_config, "runtime_provider") or llm_config.get("provider") or "selected provider"
        model = _runtime_value(llm_config, "runtime_model") or llm_config.get("requested_model") or "selected model"
        return f"Generation cannot run with {provider}/{model}: {reason}"
    return ALPHA_GENERATION_UNAVAILABLE_MESSAGE


def generation_unavailable_detail(llm_config: Dict[str, Any]) -> Dict[str, Any]:
    reason = generation_unavailable_reason(llm_config)
    provider = _runtime_value(llm_config, "runtime_provider") or llm_config.get("provider")
    model = _runtime_value(llm_config, "runtime_model") or llm_config.get("requested_model")
    return {
        "code": "llm_generation_unavailable" if reason else "alpha_generation_unavailable",
        "message": generation_unavailable_message(llm_config),
        "reason": reason,
        "provider": provider,
        "model": model,
        "live_generation_enabled": bool(llm_config.get("live_generation_enabled")),
    }
