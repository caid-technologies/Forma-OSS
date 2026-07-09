import base64
import json
import logging
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    genai = None
    genai_types = None


logger = logging.getLogger(__name__)

DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
DEFAULT_GEMINI_FALLBACK_MODEL = "gemini-2.5-flash"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_TIMEOUT_SECONDS = 90.0
DEFAULT_OPENAI_TIMEOUT_SECONDS = 300.0
DEFAULT_RUNPOD_TIMEOUT_SECONDS = 1200.0
DEFAULT_RUNPOD_POLL_TIMEOUT_SECONDS = 1200.0
DEFAULT_BASETEN_MODEL = "deepseek-ai/DeepSeek-V4-Pro"
DEFAULT_GMI_MODEL = "anthropic/claude-fable-5"
DEFAULT_HUGGINGFACE_MODEL = "Qwen/Qwen2.5-Coder-3B-Instruct:nscale"
DEFAULT_NVIDIA_MODEL = "meta/llama-3.1-8b-instruct"
DEFAULT_BASETEN_BASE_URL = "https://inference.baseten.co/v1"
DEFAULT_GMI_BASE_URL = "https://api.gmi-serving.com/v1"
DEFAULT_HUGGINGFACE_BASE_URL = "https://router.huggingface.co/v1"
DEFAULT_NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_HTTP_USER_AGENT = "Blueprint-OSS/0.1"


class LLMProviderConfigError(RuntimeError):
    """Raised when provider configuration prevents live generation."""


class LLMProviderOutputError(RuntimeError):
    """Raised when a live provider returns unusable structured output."""


SUPPORTED_LLM_PROVIDERS = {
    "baseten",
    "gemini",
    "gmi",
    "huggingface",
    "nvidia",
    "openai",
    "openai-compatible",
    "runpod",
    "runpod-serverless",
    "simulation",
}
SIMULATION_PROVIDER_ALIASES = {"simulation", "simulated", "offline", "none", "mock"}
PROVIDER_ALIASES = {
    "baseten-model-apis": "baseten",
    "baseten-frontier": "baseten",
    "build-nvidia": "nvidia",
    "nvidia-build": "nvidia",
    "nvidia-nim": "nvidia",
    "nim": "nvidia",
    "google": "gemini",
    "google-genai": "gemini",
    "gmi-cloud": "gmi",
    "gmi_cloud": "gmi",
    "gmicloud": "gmi",
    "gemicloud": "gmi",
    "gmi-serving": "gmi",
    "hf": "huggingface",
    "hugging-face": "huggingface",
    "huggingface-inference": "huggingface",
    "huggingface-router": "huggingface",
    "compatible": "openai-compatible",
    "openai_compatible": "openai-compatible",
    "runpod-openai": "runpod",
    "runpod-openai-compatible": "runpod",
    "runpod-vllm": "runpod",
    "runpod_serverless": "runpod-serverless",
    **{alias: "simulation" for alias in SIMULATION_PROVIDER_ALIASES},
}


@dataclass
class LLMProviderValidation:
    provider: str
    requested_model: str
    actual_model: Optional[str]
    requested_model_available: bool
    strict_mode: bool
    fallback_active: bool
    fallback_model: Optional[str] = None
    validation_error: Optional[str] = None
    model_availability_checked: bool = False
    live_generation_enabled: bool = True

    def as_debug_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "requested_model": self.requested_model,
            "actual_model": self.actual_model,
            "requested_model_available": self.requested_model_available,
            "model_availability_checked": self.model_availability_checked,
            "strict_mode": self.strict_mode,
            "fallback_active": self.fallback_active,
            "fallback_model": self.fallback_model,
            "validation_error": self.validation_error,
            "live_generation_enabled": self.live_generation_enabled,
        }


@dataclass(frozen=True)
class LLMRuntimeConfig:
    provider: str
    model: str
    requested_provider: Optional[str] = None
    requested_model: Optional[str] = None
    provider_overridden: bool = False
    model_overridden: bool = False
    allowed_providers: Optional[List[str]] = None
    allowed_models: Optional[List[str]] = None

    def as_debug_dict(self) -> Dict[str, Any]:
        return {
            "runtime_provider": self.provider,
            "runtime_model": self.model,
            "requested_provider_override": self.requested_provider,
            "requested_model_override": self.requested_model,
            "provider_overridden": self.provider_overridden,
            "model_overridden": self.model_overridden,
            "allowed_providers": self.allowed_providers,
            "allowed_models": self.allowed_models,
        }


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name)
    if value is None:
        return default
    stripped = value.strip()
    return stripped if stripped else default


def _first_env(names: List[str], default: Optional[str] = None) -> Optional[str]:
    for name in names:
        value = _env(name)
        if value is not None:
            return value
    return default


def _parse_csv_env(names: List[str]) -> Optional[List[str]]:
    raw_value = _first_env(names)
    if raw_value is None:
        return None
    values = [item.strip() for item in raw_value.split(",") if item.strip()]
    return values


def _parse_json_mapping_env(names: List[str]) -> Dict[str, Any]:
    raw_value = _first_env(names)
    if raw_value is None:
        return {}
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise LLMProviderConfigError(f"{names[0]} must be valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise LLMProviderConfigError(f"{names[0]} must be a JSON object mapping model names to endpoint ids or URLs.")
    return parsed


def normalize_llm_provider_name(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip().lower().replace("_", "-")
    if not normalized:
        return None
    return PROVIDER_ALIASES.get(normalized, normalized)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _first_env_bool(names: List[str], default: bool = False) -> bool:
    for name in names:
        if os.getenv(name) is not None:
            return _env_bool(name, default)
    return default


def _first_env_float(names: List[str], default: float) -> float:
    raw_value = _first_env(names)
    if raw_value is None:
        return default
    try:
        return float(raw_value)
    except ValueError:
        logger.warning("Invalid timeout value %r; using %.1fs.", raw_value, default)
        return default


def _first_env_optional_float(names: List[str], default: Optional[float] = None) -> Optional[float]:
    raw_value = _first_env(names)
    if raw_value is None:
        return default

    if raw_value.strip().lower() in {"default", "none", "omit"}:
        return None

    try:
        return float(raw_value)
    except ValueError:
        logger.warning("Invalid float value %r; using %r.", raw_value, default)
        return default


def _first_env_optional_string(
    names: List[str],
    default: Optional[str] = None,
    omit_values: Optional[List[str]] = None,
) -> Optional[str]:
    raw_value = _first_env(names)
    if raw_value is None:
        return default

    value = raw_value.strip()
    if omit_values and value.lower() in omit_values:
        return None
    return value


def _first_env_int(names: List[str]) -> Optional[int]:
    raw_value = _first_env(names)
    if raw_value is None:
        return None
    try:
        return int(raw_value)
    except ValueError:
        logger.warning("Invalid integer value %r; ignoring it.", raw_value)
        return None


def _default_provider_name() -> str:
    provider_name = normalize_llm_provider_name(_env("LLM_PROVIDER"))
    if provider_name:
        return provider_name
    if _first_env(["RUNPOD_API_KEY"]) and _first_env(["RUNPOD_OPENAI_BASE_URL", "RUNPOD_BASE_URL"]):
        return "runpod"
    if _first_env(["RUNPOD_API_KEY"]) and _first_env(["RUNPOD_ENDPOINT_ID", "RUNPOD_ENDPOINT_URL"]):
        return "runpod-serverless"
    if _first_env(["GEMINI_API_KEY", "GOOGLE_API_KEY"]):
        return "gemini"
    if _first_env(["LLM_BASE_URL", "OPENAI_BASE_URL"]):
        return "openai-compatible"
    if _first_env(["OPENAI_API_KEY", "LLM_API_KEY"]):
        return "openai"
    if _first_env(["BASETEN_API_KEY"]) and _first_env(["BASETEN_BASE_URL"], DEFAULT_BASETEN_BASE_URL):
        return "baseten"
    if _first_env(["GMI_API_KEY", "GMI_CLOUD_API_KEY", "GMICLOUD_API_KEY"]) and _first_env(
        ["GMI_BASE_URL", "GMI_CLOUD_BASE_URL", "GMICLOUD_BASE_URL"],
        DEFAULT_GMI_BASE_URL,
    ):
        return "gmi"
    if _first_env(["HUGGINGFACE_API_KEY", "HUGGINGFACE_HUB_TOKEN", "HF_TOKEN", "HF_API_TOKEN"]) and _first_env(
        ["HUGGINGFACE_BASE_URL", "HF_BASE_URL"],
        DEFAULT_HUGGINGFACE_BASE_URL,
    ):
        return "huggingface"
    if _first_env(["NVIDIA_API_KEY", "NVIDIA_NIM_API_KEY", "NIM_API_KEY"]) and _first_env(
        ["NVIDIA_BASE_URL", "NVIDIA_NIM_BASE_URL", "NIM_BASE_URL"],
        DEFAULT_NVIDIA_BASE_URL,
    ):
        return "nvidia"
    return "simulation"


def _configured_provider_names(default_provider: str) -> List[str]:
    providers = {default_provider, "simulation"}
    if _first_env(["BASETEN_API_KEY"]) and _first_env(["BASETEN_BASE_URL", "LLM_BASE_URL"], DEFAULT_BASETEN_BASE_URL):
        providers.add("baseten")
    if _first_env(["GMI_API_KEY", "GMI_CLOUD_API_KEY", "GMICLOUD_API_KEY"]) and _first_env(
        ["GMI_BASE_URL", "GMI_CLOUD_BASE_URL", "GMICLOUD_BASE_URL"],
        DEFAULT_GMI_BASE_URL,
    ):
        providers.add("gmi")
    if _first_env(["HUGGINGFACE_API_KEY", "HUGGINGFACE_HUB_TOKEN", "HF_TOKEN", "HF_API_TOKEN"]) and _first_env(
        ["HUGGINGFACE_BASE_URL", "HF_BASE_URL"],
        DEFAULT_HUGGINGFACE_BASE_URL,
    ):
        providers.add("huggingface")
    if _first_env(["NVIDIA_API_KEY", "NVIDIA_NIM_API_KEY", "NIM_API_KEY"]) and _first_env(
        ["NVIDIA_BASE_URL", "NVIDIA_NIM_BASE_URL", "NIM_BASE_URL", "LLM_BASE_URL"],
        DEFAULT_NVIDIA_BASE_URL,
    ):
        providers.add("nvidia")
    if _first_env(["RUNPOD_API_KEY"]) and _first_env(["RUNPOD_OPENAI_BASE_URL", "RUNPOD_BASE_URL", "LLM_BASE_URL"]):
        providers.add("runpod")
    if _first_env(["RUNPOD_API_KEY"]) and _first_env(["RUNPOD_ENDPOINT_ID", "RUNPOD_ENDPOINT_URL"]):
        providers.add("runpod-serverless")
    if _first_env(["GEMINI_API_KEY", "GOOGLE_API_KEY"]):
        providers.add("gemini")
    if _first_env(["OPENAI_API_KEY", "LLM_API_KEY"]):
        providers.add("openai")
    if _first_env(["LLM_BASE_URL", "OPENAI_BASE_URL"]):
        providers.add("openai-compatible")
    return sorted(provider for provider in providers if provider in SUPPORTED_LLM_PROVIDERS)


def _allowed_provider_names(default_provider: str) -> Optional[List[str]]:
    configured = _parse_csv_env(["LLM_ALLOWED_PROVIDERS", "ALLOWED_LLM_PROVIDERS"])
    if configured is None:
        return _configured_provider_names(default_provider)
    allowed: List[str] = []
    for provider in configured:
        normalized = normalize_llm_provider_name(provider)
        if normalized:
            allowed.append(normalized)
    return sorted(set(allowed))


def _default_model_for_provider(provider_name: str) -> str:
    if provider_name == "baseten":
        return _first_env(["BASETEN_MODEL", "LLM_MODEL"], DEFAULT_BASETEN_MODEL) or DEFAULT_BASETEN_MODEL
    if provider_name == "gemini":
        return _first_env(["LLM_MODEL", "GEMINI_MODEL"], DEFAULT_GEMINI_MODEL) or DEFAULT_GEMINI_MODEL
    if provider_name == "gmi":
        return _normalize_model_for_provider(
            provider_name,
            _first_env(["GMI_MODEL", "GMI_CLOUD_MODEL", "GMICLOUD_MODEL", "LLM_MODEL"], DEFAULT_GMI_MODEL) or DEFAULT_GMI_MODEL,
        )
    if provider_name == "huggingface":
        return _first_env(["HUGGINGFACE_MODEL", "HF_MODEL"], DEFAULT_HUGGINGFACE_MODEL) or DEFAULT_HUGGINGFACE_MODEL
    if provider_name == "nvidia":
        return _first_env(["NVIDIA_MODEL", "NVIDIA_NIM_MODEL", "NIM_MODEL", "LLM_MODEL"], DEFAULT_NVIDIA_MODEL) or DEFAULT_NVIDIA_MODEL
    if provider_name == "openai":
        return _first_env(["OPENAI_MODEL", "LLM_MODEL"], DEFAULT_OPENAI_MODEL) or DEFAULT_OPENAI_MODEL
    if provider_name == "openai-compatible":
        return _first_env(["LLM_MODEL", "OPENAI_MODEL"], DEFAULT_OPENAI_MODEL) or DEFAULT_OPENAI_MODEL
    if provider_name == "runpod":
        return _first_env(["RUNPOD_OPENAI_MODEL", "LLM_MODEL", "RUNPOD_MODEL"], "runpod-default") or "runpod-default"
    if provider_name == "runpod-serverless":
        return _first_env(["RUNPOD_SERVERLESS_MODEL", "RUNPOD_MODEL", "LLM_MODEL"], "runpod-serverless") or "runpod-serverless"
    return "simulation"


def _fallback_model_for_provider(provider_name: str) -> Optional[str]:
    if provider_name == "baseten":
        return _first_env(["BASETEN_FALLBACK_MODEL", "LLM_FALLBACK_MODEL"])
    if provider_name == "gemini":
        return _first_env(["LLM_FALLBACK_MODEL", "GEMINI_FALLBACK_MODEL"], DEFAULT_GEMINI_FALLBACK_MODEL)
    if provider_name == "gmi":
        fallback = _first_env(["GMI_FALLBACK_MODEL", "GMI_CLOUD_FALLBACK_MODEL", "GMICLOUD_FALLBACK_MODEL", "LLM_FALLBACK_MODEL"])
        return _normalize_model_for_provider(provider_name, fallback) if fallback else None
    if provider_name == "huggingface":
        return _first_env(["HUGGINGFACE_FALLBACK_MODEL", "HF_FALLBACK_MODEL"])
    if provider_name == "nvidia":
        return _first_env(["NVIDIA_FALLBACK_MODEL", "NVIDIA_NIM_FALLBACK_MODEL", "NIM_FALLBACK_MODEL", "LLM_FALLBACK_MODEL"])
    if provider_name == "openai":
        return _first_env(["OPENAI_FALLBACK_MODEL", "LLM_FALLBACK_MODEL"])
    if provider_name == "openai-compatible":
        return _first_env(["LLM_FALLBACK_MODEL", "OPENAI_FALLBACK_MODEL"])
    if provider_name == "runpod":
        return _first_env(["RUNPOD_OPENAI_FALLBACK_MODEL", "RUNPOD_FALLBACK_MODEL", "LLM_FALLBACK_MODEL"])
    if provider_name == "runpod-serverless":
        return _first_env(["RUNPOD_FALLBACK_MODEL", "LLM_FALLBACK_MODEL"])
    return None


def _model_endpoint_map() -> Dict[str, Any]:
    return _parse_json_mapping_env(["RUNPOD_MODEL_ENDPOINTS", "RUNPOD_ENDPOINTS_BY_MODEL"])


def _normalize_model_for_provider(provider_name: str, model_name: Optional[str]) -> str:
    model = (model_name or "").strip()
    if provider_name != "gmi" or not model:
        return model

    lowered = model.lower()
    for prefix in ("gmi/", "gmi-cloud/", "gmicloud/", "gemicloud/"):
        if lowered.startswith(prefix):
            model = model[len(prefix) :]
            lowered = model.lower()
            break

    aliases = {
        "fable": DEFAULT_GMI_MODEL,
        "fable-5": DEFAULT_GMI_MODEL,
        "claude-fable-5": DEFAULT_GMI_MODEL,
    }
    return aliases.get(lowered, model)


def _allowed_model_names(provider_name: str, default_model: str) -> Optional[List[str]]:
    env_names = ["LLM_ALLOWED_MODELS", "ALLOWED_LLM_MODELS"]
    if provider_name == "baseten":
        env_names = ["BASETEN_ALLOWED_MODELS", "ALLOWED_BASETEN_MODELS", *env_names]
    elif provider_name == "gmi":
        env_names = ["GMI_ALLOWED_MODELS", "GMI_CLOUD_ALLOWED_MODELS", "GMICLOUD_ALLOWED_MODELS", "ALLOWED_GMI_MODELS", *env_names]
    elif provider_name == "huggingface":
        env_names = ["HUGGINGFACE_ALLOWED_MODELS", "HF_ALLOWED_MODELS", "ALLOWED_HUGGINGFACE_MODELS", *env_names]
    elif provider_name == "openai":
        env_names = ["OPENAI_ALLOWED_MODELS", "ALLOWED_OPENAI_MODELS", *env_names]
    elif provider_name == "openai-compatible":
        env_names = [
            "OPENAI_COMPATIBLE_ALLOWED_MODELS",
            "LLM_COMPATIBLE_ALLOWED_MODELS",
            "ALLOWED_OPENAI_COMPATIBLE_MODELS",
            *env_names,
        ]
    elif provider_name == "gemini":
        env_names = ["GEMINI_ALLOWED_MODELS", "ALLOWED_GEMINI_MODELS", *env_names]
    elif provider_name == "nvidia":
        env_names = ["NVIDIA_ALLOWED_MODELS", "NVIDIA_NIM_ALLOWED_MODELS", "NIM_ALLOWED_MODELS", *env_names]
    elif provider_name in {"runpod", "runpod-serverless"}:
        env_names = ["RUNPOD_ALLOWED_MODELS", "ALLOWED_RUNPOD_MODELS", *env_names]

    configured = _parse_csv_env(env_names)
    if configured is not None:
        return sorted(set(_normalize_model_for_provider(provider_name, model) for model in configured))

    defaults = {default_model}
    fallback = _fallback_model_for_provider(provider_name)
    if fallback:
        defaults.add(fallback)
    if provider_name == "runpod-serverless":
        defaults.update(str(model_name) for model_name in _model_endpoint_map().keys())
    return sorted(model for model in defaults if model)


def resolve_llm_runtime_config(
    provider_name: Optional[str] = None,
    model_name: Optional[str] = None,
) -> LLMRuntimeConfig:
    default_provider = _default_provider_name()
    provider = normalize_llm_provider_name(provider_name) or default_provider
    if provider not in SUPPORTED_LLM_PROVIDERS:
        raise LLMProviderConfigError(
            f"Unsupported LLM provider '{provider}'. Supported providers are "
            f"{', '.join(sorted(SUPPORTED_LLM_PROVIDERS))}."
        )

    allowed_providers = _allowed_provider_names(default_provider)
    if allowed_providers is not None and provider not in allowed_providers:
        raise LLMProviderConfigError(
            f"Provider '{provider}' is not allowed for runtime selection. "
            "Set LLM_ALLOWED_PROVIDERS to include it."
        )

    default_model = _default_model_for_provider(provider)
    requested_model = model_name.strip() if isinstance(model_name, str) else None
    requested_model = requested_model or None
    model = _normalize_model_for_provider(provider, requested_model or default_model)
    allowed_models = _allowed_model_names(provider, default_model)
    if allowed_models is not None and model not in allowed_models:
        raise LLMProviderConfigError(
            f"Model '{model}' is not allowed for provider '{provider}'. "
            f"Set {provider.upper().replace('-', '_')}_ALLOWED_MODELS to include it."
        )

    return LLMRuntimeConfig(
        provider=provider,
        model=model,
        requested_provider=provider_name.strip() if isinstance(provider_name, str) and provider_name.strip() else None,
        requested_model=requested_model,
        provider_overridden=bool(provider_name and provider != default_provider),
        model_overridden=bool(requested_model),
        allowed_providers=allowed_providers,
        allowed_models=allowed_models,
    )


def get_llm_runtime_debug_config() -> Dict[str, Any]:
    return resolve_llm_runtime_config().as_debug_dict()


def _normalize_model_name(model_name: str) -> str:
    return model_name.strip().removeprefix("models/")


def _model_is_available(model_name: str, available_models: List[str]) -> bool:
    requested = _normalize_model_name(model_name)
    return any(_normalize_model_name(candidate) == requested for candidate in available_models)


def _schema_name(schema_class: Any) -> str:
    raw_name = getattr(schema_class, "__name__", "StructuredResponse")
    return "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in raw_name)


def _strip_json_markdown(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _extract_json_document(text: str) -> Optional[str]:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char not in {"{", "["}:
            continue
        try:
            _, end_index = decoder.raw_decode(text[index:])
            return text[index:index + end_index]
        except json.JSONDecodeError:
            continue
    return None


def _validate_structured_json(response_text: str, schema_class: Any) -> Any:
    try:
        return schema_class.model_validate_json(response_text)
    except Exception as first_error:
        cleaned = _strip_json_markdown(response_text)
        if cleaned != response_text:
            try:
                return schema_class.model_validate_json(cleaned)
            except Exception:
                pass

        extracted = _extract_json_document(cleaned)
        if extracted:
            try:
                return schema_class.model_validate_json(extracted)
            except Exception:
                pass

        raise first_error


class StructuredLLMProvider:
    provider_name = "base"
    requested_model = "simulation"
    fallback_model: Optional[str] = None
    strict_mode = False
    model_name = "simulation"
    is_configured = False

    def validate_configured_model(self, *, raise_on_strict: bool = True) -> LLMProviderValidation:
        raise NotImplementedError

    def get_debug_config(self) -> Dict[str, Any]:
        return self.validate_configured_model(raise_on_strict=False).as_debug_dict()

    def generate_structured(
        self,
        prompt: str,
        schema_class: Any,
        image_bytes: Optional[bytes] = None,
        image_mime_type: Optional[str] = None,
    ) -> Any:
        raise NotImplementedError


class SimulationProvider(StructuredLLMProvider):
    provider_name = "simulation"
    requested_model = "simulation"
    model_name = "simulation"
    is_configured = False

    def __init__(self, validation_error: Optional[str] = None):
        self.validation_error = validation_error or "No live LLM provider is configured; simulation mode is active."
        self._validation: Optional[LLMProviderValidation] = None

    def validate_configured_model(self, *, raise_on_strict: bool = True) -> LLMProviderValidation:
        if not self._validation:
            self._validation = LLMProviderValidation(
                provider=self.provider_name,
                requested_model=self.requested_model,
                actual_model=None,
                requested_model_available=False,
                strict_mode=False,
                fallback_active=False,
                fallback_model=None,
                validation_error=self.validation_error,
                live_generation_enabled=False,
            )
        return self._validation

    def generate_structured(
        self,
        prompt: str,
        schema_class: Any,
        image_bytes: Optional[bytes] = None,
        image_mime_type: Optional[str] = None,
    ) -> Any:
        raise RuntimeError("Simulation provider cannot generate live structured responses.")


class GeminiProvider(StructuredLLMProvider):
    provider_name = "gemini"

    def __init__(self, model_name: Optional[str] = None):
        self.api_key = _first_env(["GEMINI_API_KEY", "GOOGLE_API_KEY", "LLM_API_KEY"])
        self.requested_model = model_name or _first_env(["LLM_MODEL", "GEMINI_MODEL"], DEFAULT_GEMINI_MODEL) or DEFAULT_GEMINI_MODEL
        self.fallback_model = (
            _first_env(["LLM_FALLBACK_MODEL", "GEMINI_FALLBACK_MODEL"], DEFAULT_GEMINI_FALLBACK_MODEL)
            or DEFAULT_GEMINI_FALLBACK_MODEL
        )
        self.strict_mode = _first_env_bool(["STRICT_LLM", "STRICT_GEMINI"], default=True)
        self.model_name = self.requested_model
        self.client = None
        self.init_error: Optional[str] = None
        self._validation: Optional[LLMProviderValidation] = None

        if self.api_key and genai:
            try:
                self.client = genai.Client(api_key=self.api_key)
                logger.info("Gemini LLM provider initialized successfully.")
            except Exception as exc:
                self.init_error = f"Error initializing Gemini provider: {exc}"
                logger.error(self.init_error)
        elif self.api_key and not genai:
            self.init_error = "Gemini API key is set, but google-genai is unavailable."
            logger.warning("%s Running in simulated/fallback mode.", self.init_error)
        else:
            self.init_error = "No Gemini API key found."
            logger.warning("%s Live Gemini generation is disabled.", self.init_error)

        self.is_configured = self.client is not None

    def _list_generate_content_models(self) -> List[str]:
        if self.client is None:
            return []

        available_models: List[str] = []
        for model in self.client.models.list():
            name = getattr(model, "name", None)
            if not name:
                continue

            supported_actions = getattr(model, "supported_actions", None)
            if supported_actions is None and isinstance(model, dict):
                supported_actions = model.get("supportedActions") or model.get("supported_actions")
            supported_actions = supported_actions or []

            if "generateContent" in supported_actions:
                available_models.append(name)

        return available_models

    def validate_configured_model(self, *, raise_on_strict: bool = True) -> LLMProviderValidation:
        if self._validation:
            if raise_on_strict and self._validation.validation_error and self.strict_mode:
                raise LLMProviderConfigError(self._validation.validation_error)
            return self._validation

        if self.client is None:
            self._validation = LLMProviderValidation(
                provider=self.provider_name,
                requested_model=self.requested_model,
                actual_model=None,
                requested_model_available=False,
                strict_mode=self.strict_mode,
                fallback_active=False,
                fallback_model=self.fallback_model,
                validation_error=f"{self.init_error or 'Gemini provider is not configured'} Simulation mode is active.",
                live_generation_enabled=False,
            )
            return self._validation

        try:
            available_models = self._list_generate_content_models()
        except Exception as exc:
            validation_error = f"Unable to validate Gemini model availability: {exc}"
            actual_model = self.fallback_model if not self.strict_mode else None
            self._validation = LLMProviderValidation(
                provider=self.provider_name,
                requested_model=self.requested_model,
                actual_model=actual_model,
                requested_model_available=False,
                strict_mode=self.strict_mode,
                fallback_active=not self.strict_mode,
                fallback_model=self.fallback_model,
                validation_error=validation_error,
                model_availability_checked=True,
            )
            if self.strict_mode and raise_on_strict:
                raise LLMProviderConfigError(validation_error)
            self.model_name = actual_model or self.requested_model
            return self._validation

        requested_available = _model_is_available(self.requested_model, available_models)
        if requested_available:
            self.model_name = self.requested_model
            self._validation = LLMProviderValidation(
                provider=self.provider_name,
                requested_model=self.requested_model,
                actual_model=self.model_name,
                requested_model_available=True,
                strict_mode=self.strict_mode,
                fallback_active=False,
                fallback_model=self.fallback_model,
                model_availability_checked=True,
            )
            return self._validation

        if self.strict_mode:
            validation_error = (
                f"Configured Gemini model {self.requested_model} is not available for this API key/provider. "
                "Check available models or configure a valid Gemini model ID."
            )
            self._validation = LLMProviderValidation(
                provider=self.provider_name,
                requested_model=self.requested_model,
                actual_model=None,
                requested_model_available=False,
                strict_mode=True,
                fallback_active=False,
                fallback_model=self.fallback_model,
                validation_error=validation_error,
                model_availability_checked=True,
            )
            if raise_on_strict:
                raise LLMProviderConfigError(validation_error)
            return self._validation

        fallback_available = _model_is_available(self.fallback_model, available_models)
        if not fallback_available:
            validation_error = (
                f"Configured Gemini model {self.requested_model} is not available, and fallback model "
                f"{self.fallback_model} is not available for this API key/provider."
            )
            self._validation = LLMProviderValidation(
                provider=self.provider_name,
                requested_model=self.requested_model,
                actual_model=None,
                requested_model_available=False,
                strict_mode=False,
                fallback_active=False,
                fallback_model=self.fallback_model,
                validation_error=validation_error,
                model_availability_checked=True,
            )
            raise LLMProviderConfigError(validation_error)

        self.model_name = self.fallback_model
        self._validation = LLMProviderValidation(
            provider=self.provider_name,
            requested_model=self.requested_model,
            actual_model=self.model_name,
            requested_model_available=False,
            strict_mode=False,
            fallback_active=True,
            fallback_model=self.fallback_model,
            model_availability_checked=True,
        )
        return self._validation

    def generate_structured(
        self,
        prompt: str,
        schema_class: Any,
        image_bytes: Optional[bytes] = None,
        image_mime_type: Optional[str] = None,
    ) -> Any:
        if self.client is None or genai_types is None:
            raise RuntimeError("Gemini provider is not configured.")

        contents = []
        if image_bytes and image_mime_type:
            contents.append(genai_types.Part.from_bytes(data=image_bytes, mime_type=image_mime_type))
        contents.append(prompt)

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=contents,
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema_class,
                temperature=0.2,
            ),
        )
        return _validate_structured_json(response.text, schema_class)


class OpenAICompatibleProvider(StructuredLLMProvider):
    def __init__(self, provider_name: str = "openai", model_name: Optional[str] = None):
        normalized_provider = normalize_llm_provider_name(provider_name) or "openai"
        if normalized_provider in {"baseten", "gmi", "huggingface", "nvidia", "openai", "runpod"}:
            self.provider_name = normalized_provider
        else:
            self.provider_name = "openai-compatible"
        if self.provider_name == "baseten":
            api_key_names = ["BASETEN_API_KEY", "LLM_API_KEY"]
            base_url_names = ["BASETEN_BASE_URL", "LLM_BASE_URL"]
            model_names = ["BASETEN_MODEL", "LLM_MODEL"]
            fallback_model_names = ["BASETEN_FALLBACK_MODEL", "LLM_FALLBACK_MODEL"]
            strict_names = ["STRICT_BASETEN", "STRICT_LLM"]
            validate_model_names = ["BASETEN_VALIDATE_MODELS", "LLM_VALIDATE_MODELS"]
            response_format_names = ["BASETEN_RESPONSE_FORMAT", "LLM_RESPONSE_FORMAT"]
            timeout_names = ["BASETEN_TIMEOUT_SECONDS", "LLM_TIMEOUT_SECONDS"]
            max_tokens_names = ["BASETEN_MAX_TOKENS", "LLM_MAX_TOKENS"]
            temperature_names = ["BASETEN_TEMPERATURE", "LLM_TEMPERATURE"]
            reasoning_effort_names = ["BASETEN_REASONING_EFFORT", "LLM_REASONING_EFFORT"]
            allow_no_api_key_names = ["BASETEN_ALLOW_NO_API_KEY", "LLM_ALLOW_NO_API_KEY"]
            default_model_name = DEFAULT_BASETEN_MODEL
            default_base_url = DEFAULT_BASETEN_BASE_URL
            default_timeout_seconds = DEFAULT_OPENAI_TIMEOUT_SECONDS
        elif self.provider_name == "gmi":
            api_key_names = ["GMI_API_KEY", "GMI_CLOUD_API_KEY", "GMICLOUD_API_KEY", "LLM_API_KEY"]
            base_url_names = ["GMI_BASE_URL", "GMI_CLOUD_BASE_URL", "GMICLOUD_BASE_URL"]
            model_names = ["GMI_MODEL", "GMI_CLOUD_MODEL", "GMICLOUD_MODEL", "LLM_MODEL"]
            fallback_model_names = ["GMI_FALLBACK_MODEL", "GMI_CLOUD_FALLBACK_MODEL", "GMICLOUD_FALLBACK_MODEL", "LLM_FALLBACK_MODEL"]
            strict_names = ["STRICT_GMI", "STRICT_GMI_CLOUD", "STRICT_GMICLOUD", "STRICT_LLM"]
            validate_model_names = ["GMI_VALIDATE_MODELS", "GMI_CLOUD_VALIDATE_MODELS", "GMICLOUD_VALIDATE_MODELS", "LLM_VALIDATE_MODELS"]
            response_format_names = ["GMI_RESPONSE_FORMAT", "GMI_CLOUD_RESPONSE_FORMAT", "GMICLOUD_RESPONSE_FORMAT", "LLM_RESPONSE_FORMAT"]
            timeout_names = ["GMI_TIMEOUT_SECONDS", "GMI_CLOUD_TIMEOUT_SECONDS", "GMICLOUD_TIMEOUT_SECONDS", "LLM_TIMEOUT_SECONDS"]
            max_tokens_names = ["GMI_MAX_TOKENS", "GMI_CLOUD_MAX_TOKENS", "GMICLOUD_MAX_TOKENS", "LLM_MAX_TOKENS"]
            temperature_names = ["GMI_TEMPERATURE", "GMI_CLOUD_TEMPERATURE", "GMICLOUD_TEMPERATURE"]
            reasoning_effort_names = ["GMI_REASONING_EFFORT", "GMI_CLOUD_REASONING_EFFORT", "GMICLOUD_REASONING_EFFORT", "LLM_REASONING_EFFORT"]
            allow_no_api_key_names = ["GMI_ALLOW_NO_API_KEY", "GMI_CLOUD_ALLOW_NO_API_KEY", "GMICLOUD_ALLOW_NO_API_KEY", "LLM_ALLOW_NO_API_KEY"]
            default_model_name = DEFAULT_GMI_MODEL
            default_base_url = DEFAULT_GMI_BASE_URL
            default_timeout_seconds = DEFAULT_OPENAI_TIMEOUT_SECONDS
        elif self.provider_name == "huggingface":
            api_key_names = ["HUGGINGFACE_API_KEY", "HUGGINGFACE_HUB_TOKEN", "HF_TOKEN", "HF_API_TOKEN"]
            base_url_names = ["HUGGINGFACE_BASE_URL", "HF_BASE_URL"]
            model_names = ["HUGGINGFACE_MODEL", "HF_MODEL"]
            fallback_model_names = ["HUGGINGFACE_FALLBACK_MODEL", "HF_FALLBACK_MODEL"]
            strict_names = ["STRICT_HUGGINGFACE", "STRICT_HF", "STRICT_LLM"]
            validate_model_names = ["HUGGINGFACE_VALIDATE_MODELS", "HF_VALIDATE_MODELS", "LLM_VALIDATE_MODELS"]
            response_format_names = ["HUGGINGFACE_RESPONSE_FORMAT", "HF_RESPONSE_FORMAT", "LLM_RESPONSE_FORMAT"]
            timeout_names = ["HUGGINGFACE_TIMEOUT_SECONDS", "HF_TIMEOUT_SECONDS", "LLM_TIMEOUT_SECONDS"]
            max_tokens_names = ["HUGGINGFACE_MAX_TOKENS", "HF_MAX_TOKENS", "LLM_MAX_TOKENS"]
            temperature_names = ["HUGGINGFACE_TEMPERATURE", "HF_TEMPERATURE", "LLM_TEMPERATURE"]
            reasoning_effort_names = ["HUGGINGFACE_REASONING_EFFORT", "HF_REASONING_EFFORT", "LLM_REASONING_EFFORT"]
            allow_no_api_key_names = ["HUGGINGFACE_ALLOW_NO_API_KEY", "HF_ALLOW_NO_API_KEY"]
            default_model_name = DEFAULT_HUGGINGFACE_MODEL
            default_base_url = DEFAULT_HUGGINGFACE_BASE_URL
            default_timeout_seconds = DEFAULT_OPENAI_TIMEOUT_SECONDS
        elif self.provider_name == "nvidia":
            api_key_names = ["NVIDIA_API_KEY", "NVIDIA_NIM_API_KEY", "NIM_API_KEY", "LLM_API_KEY"]
            base_url_names = ["NVIDIA_BASE_URL", "NVIDIA_NIM_BASE_URL", "NIM_BASE_URL", "LLM_BASE_URL"]
            model_names = ["NVIDIA_MODEL", "NVIDIA_NIM_MODEL", "NIM_MODEL", "LLM_MODEL"]
            fallback_model_names = ["NVIDIA_FALLBACK_MODEL", "NVIDIA_NIM_FALLBACK_MODEL", "NIM_FALLBACK_MODEL", "LLM_FALLBACK_MODEL"]
            strict_names = ["STRICT_NVIDIA", "STRICT_NVIDIA_NIM", "STRICT_NIM", "STRICT_LLM"]
            validate_model_names = ["NVIDIA_VALIDATE_MODELS", "NVIDIA_NIM_VALIDATE_MODELS", "NIM_VALIDATE_MODELS", "LLM_VALIDATE_MODELS"]
            response_format_names = ["NVIDIA_RESPONSE_FORMAT", "NVIDIA_NIM_RESPONSE_FORMAT", "NIM_RESPONSE_FORMAT", "LLM_RESPONSE_FORMAT"]
            timeout_names = ["NVIDIA_TIMEOUT_SECONDS", "NVIDIA_NIM_TIMEOUT_SECONDS", "NIM_TIMEOUT_SECONDS", "LLM_TIMEOUT_SECONDS"]
            max_tokens_names = ["NVIDIA_MAX_TOKENS", "NVIDIA_NIM_MAX_TOKENS", "NIM_MAX_TOKENS", "LLM_MAX_TOKENS"]
            temperature_names = ["NVIDIA_TEMPERATURE", "NVIDIA_NIM_TEMPERATURE", "NIM_TEMPERATURE", "LLM_TEMPERATURE"]
            reasoning_effort_names = ["NVIDIA_REASONING_EFFORT", "NVIDIA_NIM_REASONING_EFFORT", "NIM_REASONING_EFFORT", "LLM_REASONING_EFFORT"]
            allow_no_api_key_names = ["NVIDIA_ALLOW_NO_API_KEY", "NVIDIA_NIM_ALLOW_NO_API_KEY", "NIM_ALLOW_NO_API_KEY", "LLM_ALLOW_NO_API_KEY"]
            default_model_name = DEFAULT_NVIDIA_MODEL
            default_base_url = DEFAULT_NVIDIA_BASE_URL
            default_timeout_seconds = DEFAULT_OPENAI_TIMEOUT_SECONDS
        elif self.provider_name == "openai":
            api_key_names = ["OPENAI_API_KEY", "LLM_API_KEY"]
            base_url_names = ["OPENAI_BASE_URL"]
            model_names = ["OPENAI_MODEL", "LLM_MODEL"]
            fallback_model_names = ["OPENAI_FALLBACK_MODEL", "LLM_FALLBACK_MODEL"]
            strict_names = ["STRICT_OPENAI", "STRICT_LLM"]
            validate_model_names = ["OPENAI_VALIDATE_MODELS", "LLM_VALIDATE_MODELS"]
            response_format_names = ["OPENAI_RESPONSE_FORMAT", "LLM_RESPONSE_FORMAT"]
            timeout_names = ["OPENAI_TIMEOUT_SECONDS", "LLM_TIMEOUT_SECONDS"]
            max_tokens_names = ["OPENAI_MAX_TOKENS", "LLM_MAX_TOKENS"]
            temperature_names = ["OPENAI_TEMPERATURE", "LLM_TEMPERATURE"]
            reasoning_effort_names = ["OPENAI_REASONING_EFFORT", "LLM_REASONING_EFFORT"]
            allow_no_api_key_names = ["OPENAI_ALLOW_NO_API_KEY", "LLM_ALLOW_NO_API_KEY"]
            default_model_name = DEFAULT_OPENAI_MODEL
            default_base_url = "https://api.openai.com/v1"
            default_timeout_seconds = DEFAULT_OPENAI_TIMEOUT_SECONDS
        elif self.provider_name == "runpod":
            api_key_names = ["RUNPOD_API_KEY", "LLM_API_KEY"]
            base_url_names = ["RUNPOD_OPENAI_BASE_URL", "RUNPOD_BASE_URL", "LLM_BASE_URL"]
            model_names = ["RUNPOD_OPENAI_MODEL", "LLM_MODEL", "RUNPOD_MODEL"]
            fallback_model_names = ["RUNPOD_OPENAI_FALLBACK_MODEL", "RUNPOD_FALLBACK_MODEL", "LLM_FALLBACK_MODEL"]
            strict_names = ["STRICT_RUNPOD", "STRICT_LLM"]
            validate_model_names = ["RUNPOD_VALIDATE_MODELS", "LLM_VALIDATE_MODELS"]
            response_format_names = ["RUNPOD_RESPONSE_FORMAT", "LLM_RESPONSE_FORMAT"]
            timeout_names = ["RUNPOD_TIMEOUT_SECONDS", "LLM_TIMEOUT_SECONDS"]
            max_tokens_names = ["RUNPOD_MAX_TOKENS", "LLM_MAX_TOKENS"]
            temperature_names = ["RUNPOD_TEMPERATURE", "LLM_TEMPERATURE"]
            reasoning_effort_names = ["RUNPOD_REASONING_EFFORT", "LLM_REASONING_EFFORT"]
            allow_no_api_key_names = ["RUNPOD_ALLOW_NO_API_KEY", "LLM_ALLOW_NO_API_KEY"]
            default_model_name = "runpod-default"
            default_base_url = None
            default_timeout_seconds = DEFAULT_RUNPOD_TIMEOUT_SECONDS
        else:
            api_key_names = ["LLM_API_KEY", "OPENAI_API_KEY"]
            base_url_names = ["LLM_BASE_URL", "OPENAI_BASE_URL"]
            model_names = ["LLM_MODEL", "OPENAI_MODEL"]
            fallback_model_names = ["LLM_FALLBACK_MODEL", "OPENAI_FALLBACK_MODEL"]
            strict_names = ["STRICT_LLM", "STRICT_OPENAI"]
            validate_model_names = ["LLM_VALIDATE_MODELS", "OPENAI_VALIDATE_MODELS"]
            response_format_names = ["LLM_RESPONSE_FORMAT", "OPENAI_RESPONSE_FORMAT"]
            timeout_names = ["LLM_TIMEOUT_SECONDS", "OPENAI_TIMEOUT_SECONDS"]
            max_tokens_names = ["LLM_MAX_TOKENS", "OPENAI_MAX_TOKENS"]
            temperature_names = ["LLM_TEMPERATURE", "OPENAI_TEMPERATURE"]
            reasoning_effort_names = ["LLM_REASONING_EFFORT", "OPENAI_REASONING_EFFORT"]
            allow_no_api_key_names = ["LLM_ALLOW_NO_API_KEY", "OPENAI_ALLOW_NO_API_KEY"]
            default_model_name = DEFAULT_OPENAI_MODEL
            default_base_url = None
            default_timeout_seconds = DEFAULT_TIMEOUT_SECONDS

        self.api_key = _first_env(api_key_names)
        self.organization_id = _first_env(["OPENAI_ORG_ID", "OPENAI_ORGANIZATION", "OPENAI_ORGANIZATION_ID"])
        self.project_id = _first_env(["OPENAI_PROJECT_ID", "OPENAI_PROJECT"])
        configured_base_url = _first_env(base_url_names)
        self.base_url = (configured_base_url or default_base_url or "").rstrip("/")
        self.requested_model = _normalize_model_for_provider(
            self.provider_name,
            model_name or _first_env(model_names, default_model_name) or default_model_name,
        )
        raw_fallback_model = _first_env(fallback_model_names)
        self.fallback_model = _normalize_model_for_provider(self.provider_name, raw_fallback_model) if raw_fallback_model else None
        self.strict_mode = _first_env_bool(strict_names, default=True)
        self.validate_models = _first_env_bool(validate_model_names, default=False)
        default_response_format = "json_schema" if self.provider_name == "openai" else "json_object"
        self.response_format = (
            _first_env(response_format_names, default_response_format)
            or default_response_format
        ).strip().lower().replace("-", "_")
        self.timeout_seconds = _first_env_float(timeout_names, default_timeout_seconds)
        self.max_tokens = _first_env_int(max_tokens_names)
        self.temperature = _first_env_optional_float(
            temperature_names,
            default=None if self.provider_name in {"gmi", "openai"} else 0.2,
        )
        self.reasoning_effort = _first_env_optional_string(
            reasoning_effort_names,
            omit_values=["default", "omit"],
        )
        self.allow_no_api_key = _first_env_bool(
            allow_no_api_key_names,
            default=self.provider_name == "openai-compatible" and configured_base_url is not None,
        )
        self.model_name = self.requested_model
        self._validation: Optional[LLMProviderValidation] = None

        self.is_configured = bool(self.base_url and (self.api_key or self.allow_no_api_key))
        if self.is_configured:
            logger.info("%s LLM provider initialized for model %s.", self.provider_name, self.requested_model)
        else:
            logger.warning("%s LLM provider is missing an API key or base URL.", self.provider_name)

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": os.getenv("LLM_USER_AGENT", DEFAULT_HTTP_USER_AGENT),
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self.provider_name == "openai":
            if self.organization_id:
                headers["OpenAI-Organization"] = self.organization_id
            if self.project_id:
                headers["OpenAI-Project"] = self.project_id
        return headers

    def _request_json(self, path: str, method: str = "GET", payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(url, data=data, headers=self._headers(), method=method)

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{self.provider_name} request failed with HTTP {exc.code}: {detail[:500]}") from exc
        except (socket.timeout, TimeoutError) as exc:
            timeout_hint = self._timeout_hint()
            raise RuntimeError(
                f"{self.provider_name} request timed out after {self.timeout_seconds:.1f}s while reading {path}. "
                f"{timeout_hint}"
            ) from exc
        except urllib.error.URLError as exc:
            if isinstance(getattr(exc, "reason", None), (socket.timeout, TimeoutError)):
                timeout_hint = self._timeout_hint()
                raise RuntimeError(
                    f"{self.provider_name} request timed out after {self.timeout_seconds:.1f}s while reading {path}. "
                    f"{timeout_hint}"
                ) from exc
            raise RuntimeError(f"{self.provider_name} request failed: {exc}") from exc

        if not body.strip():
            return {}
        return json.loads(body)

    def _timeout_hint(self) -> str:
        if self.provider_name == "baseten":
            return "Increase BASETEN_TIMEOUT_SECONDS/LLM_TIMEOUT_SECONDS or use a lower-latency model/settings."
        if self.provider_name == "huggingface":
            return "Increase HUGGINGFACE_TIMEOUT_SECONDS/HF_TIMEOUT_SECONDS/LLM_TIMEOUT_SECONDS or use a lower-latency model/settings."
        if self.provider_name == "gmi":
            return "Increase GMI_TIMEOUT_SECONDS/GMI_CLOUD_TIMEOUT_SECONDS/LLM_TIMEOUT_SECONDS or use a lower-latency model/settings."
        if self.provider_name == "nvidia":
            return "Increase NVIDIA_TIMEOUT_SECONDS/LLM_TIMEOUT_SECONDS or use a lower-latency model/settings."
        if self.provider_name == "runpod":
            return "Increase RUNPOD_TIMEOUT_SECONDS for long Runpod jobs."
        return "Increase OPENAI_TIMEOUT_SECONDS/LLM_TIMEOUT_SECONDS or use a lower-latency model/settings."

    def _configuration_hint(self) -> str:
        if self.provider_name == "baseten":
            return "Set BASETEN_API_KEY. BASETEN_BASE_URL defaults to https://inference.baseten.co/v1."
        if self.provider_name == "huggingface":
            return "Set HF_TOKEN, HUGGINGFACE_API_KEY, or HUGGINGFACE_HUB_TOKEN. HUGGINGFACE_BASE_URL defaults to https://router.huggingface.co/v1."
        if self.provider_name == "gmi":
            return "Set GMI_API_KEY or GMI_CLOUD_API_KEY. GMI_BASE_URL defaults to https://api.gmi-serving.com/v1."
        if self.provider_name == "nvidia":
            return "Set NVIDIA_API_KEY. NVIDIA_BASE_URL defaults to https://integrate.api.nvidia.com/v1."
        if self.provider_name == "runpod":
            return "Set RUNPOD_API_KEY plus RUNPOD_OPENAI_BASE_URL or RUNPOD_BASE_URL."
        if self.provider_name == "openai":
            return "Set OPENAI_API_KEY."
        return "Set LLM_API_KEY and LLM_BASE_URL, or set LLM_ALLOW_NO_API_KEY=true for a local OpenAI-compatible endpoint."

    def _list_models(self) -> List[str]:
        payload = self._request_json("models")
        data = payload.get("data", [])
        if not isinstance(data, list):
            return []

        models = []
        for item in data:
            if isinstance(item, dict):
                model_id = item.get("id") or item.get("name")
                if model_id:
                    models.append(model_id)
            elif isinstance(item, str):
                models.append(item)
        return models

    def validate_configured_model(self, *, raise_on_strict: bool = True) -> LLMProviderValidation:
        if self._validation:
            if raise_on_strict and self._validation.validation_error and self.strict_mode:
                raise LLMProviderConfigError(self._validation.validation_error)
            return self._validation

        if not self.is_configured:
            self._validation = LLMProviderValidation(
                provider=self.provider_name,
                requested_model=self.requested_model,
                actual_model=None,
                requested_model_available=False,
                strict_mode=self.strict_mode,
                fallback_active=False,
                fallback_model=self.fallback_model,
                validation_error=f"{self.provider_name} provider is not configured. {self._configuration_hint()}",
                live_generation_enabled=False,
            )
            return self._validation

        if not self.validate_models:
            self.model_name = self.requested_model
            self._validation = LLMProviderValidation(
                provider=self.provider_name,
                requested_model=self.requested_model,
                actual_model=self.model_name,
                requested_model_available=True,
                strict_mode=self.strict_mode,
                fallback_active=False,
                fallback_model=self.fallback_model,
                model_availability_checked=False,
            )
            return self._validation

        try:
            available_models = self._list_models()
        except Exception as exc:
            validation_error = f"Unable to validate {self.provider_name} model availability: {exc}"
            actual_model = self.fallback_model if (self.fallback_model and not self.strict_mode) else None
            self._validation = LLMProviderValidation(
                provider=self.provider_name,
                requested_model=self.requested_model,
                actual_model=actual_model,
                requested_model_available=False,
                strict_mode=self.strict_mode,
                fallback_active=bool(actual_model),
                fallback_model=self.fallback_model,
                validation_error=validation_error,
                model_availability_checked=True,
            )
            if self.strict_mode and raise_on_strict:
                raise LLMProviderConfigError(validation_error)
            self.model_name = actual_model or self.requested_model
            return self._validation

        requested_available = _model_is_available(self.requested_model, available_models)
        if requested_available:
            self.model_name = self.requested_model
            self._validation = LLMProviderValidation(
                provider=self.provider_name,
                requested_model=self.requested_model,
                actual_model=self.model_name,
                requested_model_available=True,
                strict_mode=self.strict_mode,
                fallback_active=False,
                fallback_model=self.fallback_model,
                model_availability_checked=True,
            )
            return self._validation

        if self.strict_mode or not self.fallback_model:
            validation_error = (
                f"Configured {self.provider_name} model {self.requested_model} is not available for this endpoint."
            )
            self._validation = LLMProviderValidation(
                provider=self.provider_name,
                requested_model=self.requested_model,
                actual_model=None,
                requested_model_available=False,
                strict_mode=self.strict_mode,
                fallback_active=False,
                fallback_model=self.fallback_model,
                validation_error=validation_error,
                model_availability_checked=True,
            )
            if raise_on_strict:
                raise LLMProviderConfigError(validation_error)
            return self._validation

        fallback_available = _model_is_available(self.fallback_model, available_models)
        if not fallback_available:
            validation_error = (
                f"Configured {self.provider_name} model {self.requested_model} is not available, and fallback model "
                f"{self.fallback_model} is not available for this endpoint."
            )
            self._validation = LLMProviderValidation(
                provider=self.provider_name,
                requested_model=self.requested_model,
                actual_model=None,
                requested_model_available=False,
                strict_mode=False,
                fallback_active=False,
                fallback_model=self.fallback_model,
                validation_error=validation_error,
                model_availability_checked=True,
            )
            raise LLMProviderConfigError(validation_error)

        self.model_name = self.fallback_model
        self._validation = LLMProviderValidation(
            provider=self.provider_name,
            requested_model=self.requested_model,
            actual_model=self.model_name,
            requested_model_available=False,
            strict_mode=False,
            fallback_active=True,
            fallback_model=self.fallback_model,
            model_availability_checked=True,
        )
        return self._validation

    def _build_structured_prompt(self, prompt: str, schema_class: Any) -> str:
        schema_json = json.dumps(schema_class.model_json_schema(), indent=2)
        return (
            f"{prompt}\n\n"
            "Return only valid JSON. The JSON must conform to this schema:\n"
            f"{schema_json}"
        )

    def _build_user_content(
        self,
        prompt: str,
        schema_class: Any,
        image_bytes: Optional[bytes],
        image_mime_type: Optional[str],
    ) -> Any:
        structured_prompt = self._build_structured_prompt(prompt, schema_class)
        if not image_bytes or not image_mime_type:
            return structured_prompt

        data = base64.b64encode(image_bytes).decode("ascii")
        return [
            {"type": "text", "text": structured_prompt},
            {"type": "image_url", "image_url": {"url": f"data:{image_mime_type};base64,{data}"}},
        ]

    def generate_structured(
        self,
        prompt: str,
        schema_class: Any,
        image_bytes: Optional[bytes] = None,
        image_mime_type: Optional[str] = None,
    ) -> Any:
        if not self.is_configured:
            raise RuntimeError(f"{self.provider_name} provider is not configured.")

        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": "You produce concise, valid JSON only. Do not include markdown or commentary.",
                },
                {
                    "role": "user",
                    "content": self._build_user_content(prompt, schema_class, image_bytes, image_mime_type),
                },
            ],
        }
        if self.temperature is not None:
            payload["temperature"] = self.temperature

        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort

        if self.max_tokens:
            if self.provider_name == "openai":
                payload["max_completion_tokens"] = self.max_tokens
            else:
                payload["max_tokens"] = self.max_tokens

        if self.response_format == "json_schema":
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": _schema_name(schema_class),
                    "schema": schema_class.model_json_schema(),
                    "strict": False,
                },
            }
        elif self.response_format != "none":
            payload["response_format"] = {"type": "json_object"}

        response = self._request_json("chat/completions", method="POST", payload=payload)
        choices = response.get("choices") or []
        if not choices:
            raise RuntimeError(f"{self.provider_name} response did not include any choices.")

        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError(f"{self.provider_name} response did not include text content.")

        return _validate_structured_json(content, schema_class)


class RunpodServerlessProvider(StructuredLLMProvider):
    provider_name = "runpod-serverless"

    def __init__(self, model_name: Optional[str] = None):
        self.api_key = _first_env(["RUNPOD_API_KEY"])
        self.requested_model = model_name or _first_env(["RUNPOD_MODEL", "LLM_MODEL"], "runpod-default") or "runpod-default"
        self.fallback_model = _first_env(["RUNPOD_FALLBACK_MODEL", "LLM_FALLBACK_MODEL"])
        self.strict_mode = _first_env_bool(["STRICT_RUNPOD", "STRICT_LLM"], default=True)
        self.timeout_seconds = _first_env_float(["RUNPOD_TIMEOUT_SECONDS"], DEFAULT_RUNPOD_TIMEOUT_SECONDS)
        self.wait_ms = _first_env_int(["RUNPOD_WAIT_MS", "RUNPOD_RUNSYNC_WAIT_MS"]) or 90_000
        self.poll_timeout_seconds = _first_env_float(["RUNPOD_POLL_TIMEOUT_SECONDS"], DEFAULT_RUNPOD_POLL_TIMEOUT_SECONDS)
        self.poll_interval_seconds = max(1.0, _first_env_float(["RUNPOD_POLL_INTERVAL_SECONDS"], 5.0))
        self.execution_timeout_ms = _first_env_int(["RUNPOD_EXECUTION_TIMEOUT_MS"])
        self.ttl_ms = _first_env_int(["RUNPOD_TTL_MS"])
        self.temperature = _first_env_optional_float(["RUNPOD_TEMPERATURE", "LLM_TEMPERATURE"], default=None)
        self.input_template = _first_env(["RUNPOD_INPUT_TEMPLATE"])
        self.model_endpoint_map = _model_endpoint_map()
        self.endpoint_base_url = self._resolve_endpoint_base_url(self.requested_model)
        self.model_name = self.requested_model
        self._validation: Optional[LLMProviderValidation] = None
        self.is_configured = bool(self.api_key and self.endpoint_base_url)
        if self.is_configured:
            logger.info("Runpod Serverless provider initialized for model %s.", self.requested_model)
        else:
            logger.warning("Runpod Serverless provider is missing RUNPOD_API_KEY or endpoint configuration.")

    def _resolve_endpoint_base_url(self, model_name: str) -> str:
        endpoint_config = self.model_endpoint_map.get(model_name)
        endpoint_url: Optional[str] = None
        endpoint_id: Optional[str] = None
        if isinstance(endpoint_config, str):
            if endpoint_config.startswith("http://") or endpoint_config.startswith("https://"):
                endpoint_url = endpoint_config
            else:
                endpoint_id = endpoint_config
        elif isinstance(endpoint_config, dict):
            raw_url = endpoint_config.get("endpoint_url") or endpoint_config.get("url")
            raw_id = endpoint_config.get("endpoint_id") or endpoint_config.get("id")
            endpoint_url = str(raw_url) if raw_url else None
            endpoint_id = str(raw_id) if raw_id else None

        endpoint_url = endpoint_url or _first_env(["RUNPOD_ENDPOINT_URL"])
        endpoint_id = endpoint_id or _first_env(["RUNPOD_ENDPOINT_ID"])

        if endpoint_url:
            parsed = urllib.parse.urlparse(endpoint_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise LLMProviderConfigError(f"RUNPOD_ENDPOINT_URL must be absolute, got {endpoint_url!r}.")
            path_parts = [part for part in parsed.path.split("/") if part]
            if len(path_parts) >= 2 and path_parts[0] == "v2":
                runpod_endpoint_id = urllib.parse.unquote(path_parts[1])
                return urllib.parse.urlunparse(
                    (parsed.scheme, parsed.netloc, f"/v2/{urllib.parse.quote(runpod_endpoint_id, safe='')}", "", "", "")
                ).rstrip("/")
            return endpoint_url.rstrip("/")

        if endpoint_id:
            return f"https://api.runpod.ai/v2/{urllib.parse.quote(endpoint_id, safe='')}"
        return ""

    def validate_configured_model(self, *, raise_on_strict: bool = True) -> LLMProviderValidation:
        if self._validation:
            if raise_on_strict and self._validation.validation_error and self.strict_mode:
                raise LLMProviderConfigError(self._validation.validation_error)
            return self._validation

        if not self.is_configured:
            self._validation = LLMProviderValidation(
                provider=self.provider_name,
                requested_model=self.requested_model,
                actual_model=None,
                requested_model_available=False,
                strict_mode=self.strict_mode,
                fallback_active=False,
                fallback_model=self.fallback_model,
                validation_error=(
                    "Runpod provider is not configured. Set RUNPOD_API_KEY plus RUNPOD_ENDPOINT_ID, "
                    "RUNPOD_ENDPOINT_URL, or RUNPOD_MODEL_ENDPOINTS."
                ),
                live_generation_enabled=False,
            )
            return self._validation

        self.model_name = self.requested_model
        self._validation = LLMProviderValidation(
            provider=self.provider_name,
            requested_model=self.requested_model,
            actual_model=self.model_name,
            requested_model_available=True,
            strict_mode=self.strict_mode,
            fallback_active=False,
            fallback_model=self.fallback_model,
            model_availability_checked=False,
        )
        return self._validation

    def _headers(self) -> Dict[str, str]:
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _request_json(self, path: str, method: str = "GET", payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.endpoint_base_url}/{path.lstrip('/')}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(url, data=data, headers=self._headers(), method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Runpod request failed with HTTP {exc.code}: {detail[:500]}") from exc
        except (socket.timeout, TimeoutError) as exc:
            raise RuntimeError(
                f"Runpod request timed out after {self.timeout_seconds:.1f}s while reading {path}. "
                "Increase RUNPOD_TIMEOUT_SECONDS. For queued jobs, also increase RUNPOD_POLL_TIMEOUT_SECONDS, "
                "RUNPOD_EXECUTION_TIMEOUT_MS, and RUNPOD_TTL_MS."
            ) from exc
        except urllib.error.URLError as exc:
            if isinstance(getattr(exc, "reason", None), (socket.timeout, TimeoutError)):
                raise RuntimeError(
                    f"Runpod request timed out after {self.timeout_seconds:.1f}s while reading {path}. "
                    "Increase RUNPOD_TIMEOUT_SECONDS. For queued jobs, also increase RUNPOD_POLL_TIMEOUT_SECONDS, "
                    "RUNPOD_EXECUTION_TIMEOUT_MS, and RUNPOD_TTL_MS."
                ) from exc
            raise RuntimeError(f"Runpod request failed: {exc}") from exc

        if not body.strip():
            return {}
        return json.loads(body)

    def _apply_template(self, value: Any, *, prompt: str, schema_json: str) -> Any:
        if isinstance(value, dict):
            return {key: self._apply_template(item, prompt=prompt, schema_json=schema_json) for key, item in value.items()}
        if isinstance(value, list):
            return [self._apply_template(item, prompt=prompt, schema_json=schema_json) for item in value]
        if isinstance(value, str):
            return value.replace("{prompt}", prompt).replace("{model}", self.model_name).replace("{schema}", schema_json)
        return value

    def _build_run_payload(self, prompt: str, schema_class: Any) -> Dict[str, Any]:
        schema_json = json.dumps(schema_class.model_json_schema(), indent=2)
        if self.input_template:
            try:
                parsed_template = json.loads(self.input_template)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"RUNPOD_INPUT_TEMPLATE must be valid JSON: {exc}") from exc
            parsed_template = self._apply_template(parsed_template, prompt=prompt, schema_json=schema_json)
            payload = parsed_template if isinstance(parsed_template, dict) and "input" in parsed_template else {"input": parsed_template}
        else:
            payload = {
                "input": {
                    "prompt": prompt,
                    "model": self.model_name,
                }
            }
            if self.temperature is not None:
                payload["input"]["temperature"] = self.temperature

        policy: Dict[str, Any] = {}
        if isinstance(payload.get("policy"), dict):
            policy.update(payload["policy"])
        if self.execution_timeout_ms is not None:
            policy.setdefault("executionTimeout", self.execution_timeout_ms)
        if self.ttl_ms is not None:
            policy.setdefault("ttl", self.ttl_ms)
        if policy:
            payload["policy"] = policy
        return payload

    def _poll_status(self, job_id: str) -> Dict[str, Any]:
        deadline = time.monotonic() + self.poll_timeout_seconds
        last_result: Dict[str, Any] = {"id": job_id, "status": "IN_QUEUE"}
        while time.monotonic() < deadline:
            time.sleep(min(self.poll_interval_seconds, max(0.0, deadline - time.monotonic())))
            last_result = self._request_json(f"status/{urllib.parse.quote(job_id, safe='')}")
            status = str(last_result.get("status") or "")
            if status in {"COMPLETED", "FAILED", "ERROR", "TIMED_OUT", "CANCELLED"}:
                return last_result
        return last_result

    def _extract_structured_output(self, value: Any) -> Any:
        if isinstance(value, dict):
            if "choices" in value:
                choices = value.get("choices") or []
                if choices and isinstance(choices[0], dict):
                    message = choices[0].get("message") or {}
                    if isinstance(message, dict) and "content" in message:
                        return self._extract_structured_output(message["content"])
            if "output_text" in value:
                return value["output_text"]
            if "content" in value:
                return self._extract_structured_output(value["content"])
            if "text" in value:
                return value["text"]
            if "response" in value:
                return self._extract_structured_output(value["response"])
            if "result" in value:
                return self._extract_structured_output(value["result"])
            return value
        if isinstance(value, list):
            if len(value) == 1:
                return self._extract_structured_output(value[0])
            text_parts = []
            for item in value:
                extracted = self._extract_structured_output(item)
                if isinstance(extracted, str):
                    text_parts.append(extracted)
            if text_parts:
                return "".join(text_parts)
            return value
        return value

    def generate_structured(
        self,
        prompt: str,
        schema_class: Any,
        image_bytes: Optional[bytes] = None,
        image_mime_type: Optional[str] = None,
    ) -> Any:
        if image_bytes or image_mime_type:
            raise RuntimeError("Runpod provider does not support reference images through the generic adapter.")
        if not self.is_configured:
            raise RuntimeError("Runpod provider is not configured.")

        structured_prompt = (
            f"{prompt}\n\n"
            "Return only valid JSON. The JSON must conform to this schema:\n"
            f"{json.dumps(schema_class.model_json_schema(), indent=2)}"
        )
        payload = self._build_run_payload(structured_prompt, schema_class)
        wait_ms = max(1_000, min(300_000, self.wait_ms))
        result = self._request_json(f"runsync?wait={wait_ms}", method="POST", payload=payload)
        status = str(result.get("status") or "")
        if status in {"IN_QUEUE", "IN_PROGRESS"} and result.get("id"):
            result = self._poll_status(str(result["id"]))
            status = str(result.get("status") or "")
        if status != "COMPLETED":
            raise RuntimeError(f"Runpod job did not complete successfully; status={status or 'unknown'}.")

        output = self._extract_structured_output(result.get("output"))
        if isinstance(output, str):
            return _validate_structured_json(output, schema_class)
        return schema_class.model_validate(output)


def build_llm_provider(
    provider_name: Optional[str] = None,
    model_name: Optional[str] = None,
    runtime_config: Optional[LLMRuntimeConfig] = None,
) -> StructuredLLMProvider:
    runtime = runtime_config or resolve_llm_runtime_config(provider_name=provider_name, model_name=model_name)
    if runtime.provider == "gemini":
        return GeminiProvider(model_name=runtime.model)
    if runtime.provider in {"baseten", "gmi", "huggingface", "nvidia", "openai", "openai-compatible"}:
        return OpenAICompatibleProvider(provider_name=runtime.provider, model_name=runtime.model)
    if runtime.provider == "runpod":
        return OpenAICompatibleProvider(provider_name="runpod", model_name=runtime.model)
    if runtime.provider == "runpod-serverless":
        return RunpodServerlessProvider(model_name=runtime.model)
    if runtime.provider == "simulation":
        return SimulationProvider()

    message = (
        f"Unsupported LLM_PROVIDER '{runtime.provider}'. Supported providers are "
        "baseten, gemini, gmi, huggingface, nvidia, openai, openai-compatible, runpod, runpod-serverless, and simulation."
    )
    logger.warning(message)
    return SimulationProvider(validation_error=message)
