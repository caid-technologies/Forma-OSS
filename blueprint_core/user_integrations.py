from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional


DEFAULT_CONFIG_DIR = ".blueprint"
DEFAULT_CONFIG_FILENAME = "user-integrations.json"
CONFIG_PATH_ENV_NAMES = (
    "BLUEPRINT_USER_INTEGRATIONS_PATH",
    "BLUEPRINT_USER_CONFIG_PATH",
)
CONFIG_DIR_ENV_NAMES = (
    "BLUEPRINT_USER_CONFIG_DIR",
    "BLUEPRINT_LOCAL_CONFIG_DIR",
)


@dataclass(frozen=True)
class IntegrationFieldDefinition:
    id: str
    label: str
    env_names: tuple[str, ...]
    secret: bool = False
    placeholder: str = ""
    help: str = ""


@dataclass(frozen=True)
class IntegrationDefinition:
    id: str
    label: str
    description: str
    fields: tuple[IntegrationFieldDefinition, ...]

    def field_by_id(self, field_id: str) -> IntegrationFieldDefinition:
        for field_definition in self.fields:
            if field_definition.id == field_id:
                return field_definition
        raise KeyError(f"Unknown field {field_id!r} for integration {self.id!r}.")


@dataclass
class StoredIntegrationField:
    id: str
    value: str

    @classmethod
    def from_raw(cls, raw: object) -> Optional["StoredIntegrationField"]:
        if not isinstance(raw, dict):
            return None
        field_id = str(raw.get("id") or "").strip()
        value = raw.get("value")
        if not field_id or value is None:
            return None
        return cls(id=field_id, value=str(value))

    def as_json(self) -> dict[str, str]:
        return {"id": self.id, "value": self.value}


@dataclass
class StoredIntegration:
    id: str
    enabled: bool = True
    fields: list[StoredIntegrationField] = field(default_factory=list)
    updated_at: str = ""

    @classmethod
    def from_raw(cls, raw: object) -> Optional["StoredIntegration"]:
        if not isinstance(raw, dict):
            return None
        integration_id = str(raw.get("id") or "").strip()
        if not integration_id:
            return None
        fields = [
            parsed
            for parsed in (StoredIntegrationField.from_raw(item) for item in raw.get("fields") or [])
            if parsed is not None
        ]
        return cls(
            id=integration_id,
            enabled=bool(raw.get("enabled", True)),
            fields=fields,
            updated_at=str(raw.get("updated_at") or ""),
        )

    def field_value(self, field_id: str) -> Optional[str]:
        for stored_field in self.fields:
            if stored_field.id == field_id:
                return stored_field.value
        return None

    def set_field(self, field_id: str, value: str) -> None:
        trimmed_value = value.strip()
        self.clear_field(field_id)
        if trimmed_value:
            self.fields.append(StoredIntegrationField(id=field_id, value=trimmed_value))

    def clear_field(self, field_id: str) -> None:
        self.fields = [stored_field for stored_field in self.fields if stored_field.id != field_id]

    def as_json(self) -> dict[str, object]:
        return {
            "id": self.id,
            "enabled": self.enabled,
            "fields": [stored_field.as_json() for stored_field in self.fields],
            "updated_at": self.updated_at,
        }


@dataclass
class UserIntegrationConfig:
    version: int = 1
    updated_at: str = ""
    integrations: list[StoredIntegration] = field(default_factory=list)

    @classmethod
    def from_raw(cls, raw: object) -> "UserIntegrationConfig":
        if not isinstance(raw, dict):
            return cls()
        integrations = [
            parsed
            for parsed in (StoredIntegration.from_raw(item) for item in raw.get("integrations") or [])
            if parsed is not None
        ]
        return cls(
            version=int(raw.get("version") or 1),
            updated_at=str(raw.get("updated_at") or ""),
            integrations=integrations,
        )

    def integration_by_id(self, integration_id: str) -> Optional[StoredIntegration]:
        for integration in self.integrations:
            if integration.id == integration_id:
                return integration
        return None

    def ensure_integration(self, integration_id: str) -> StoredIntegration:
        existing = self.integration_by_id(integration_id)
        if existing is not None:
            return existing
        created = StoredIntegration(id=integration_id)
        self.integrations.append(created)
        return created

    def as_json(self) -> dict[str, object]:
        return {
            "version": self.version,
            "updated_at": self.updated_at,
            "integrations": [integration.as_json() for integration in self.integrations],
        }


INTEGRATION_DEFINITIONS: tuple[IntegrationDefinition, ...] = (
    IntegrationDefinition(
        id="runtime",
        label="Runtime Defaults",
        description="Default provider/model choices used when a job does not pass explicit runtime settings.",
        fields=(
            IntegrationFieldDefinition("llm_provider", "LLM provider", ("LLM_PROVIDER",), placeholder="openai"),
            IntegrationFieldDefinition("llm_model", "LLM model", ("LLM_MODEL",), placeholder="gpt-5.5"),
            IntegrationFieldDefinition("image_provider", "Image provider", ("IMAGE_PROVIDER",), placeholder="openai"),
            IntegrationFieldDefinition("image_model", "Image model", ("IMAGE_MODEL", "OPENAI_IMAGE_MODEL"), placeholder="gpt-image-2"),
            IntegrationFieldDefinition("external_source_provider", "Search provider", ("EXTERNAL_SOURCE_PROVIDER",), placeholder="firecrawl"),
        ),
    ),
    IntegrationDefinition(
        id="openai",
        label="OpenAI",
        description="Text, image, and streaming jobs that use OpenAI-compatible OpenAI endpoints.",
        fields=(
            IntegrationFieldDefinition("api_key", "API key", ("OPENAI_API_KEY", "OPENAI_IMAGE_API_KEY"), secret=True, placeholder="sk-..."),
            IntegrationFieldDefinition("base_url", "Base URL", ("OPENAI_BASE_URL", "OPENAI_IMAGE_BASE_URL"), placeholder="https://api.openai.com/v1"),
            IntegrationFieldDefinition("model", "Default text model", ("OPENAI_MODEL", "OPENAI_STREAM_MODEL"), placeholder="gpt-5.5"),
            IntegrationFieldDefinition("image_model", "Default image model", ("OPENAI_IMAGE_MODEL", "IMAGE_MODEL"), placeholder="gpt-image-2"),
            IntegrationFieldDefinition("image_size", "Image size", ("OPENAI_IMAGE_SIZE", "IMAGE_SIZE"), placeholder="1024x1024"),
            IntegrationFieldDefinition("timeout_seconds", "Timeout seconds", ("OPENAI_TIMEOUT_SECONDS", "OPENAI_STREAM_TIMEOUT_SECONDS"), placeholder="1200"),
        ),
    ),
    IntegrationDefinition(
        id="baseten",
        label="Baseten",
        description="OpenAI-compatible Baseten Model APIs.",
        fields=(
            IntegrationFieldDefinition("api_key", "API key", ("BASETEN_API_KEY",), secret=True, placeholder="baseten key"),
            IntegrationFieldDefinition("base_url", "Base URL", ("BASETEN_BASE_URL",), placeholder="https://inference.baseten.co/v1"),
            IntegrationFieldDefinition("model", "Default model", ("BASETEN_MODEL", "BASETEN_STREAM_MODEL"), placeholder="deepseek-ai/DeepSeek-V4-Pro"),
            IntegrationFieldDefinition("timeout_seconds", "Timeout seconds", ("BASETEN_TIMEOUT_SECONDS", "BASETEN_STREAM_TIMEOUT_SECONDS"), placeholder="1200"),
            IntegrationFieldDefinition("max_tokens", "Max tokens", ("BASETEN_MAX_TOKENS", "BASETEN_STREAM_MAX_OUTPUT_TOKENS"), placeholder="4000"),
        ),
    ),
    IntegrationDefinition(
        id="runpod",
        label="Runpod",
        description="Runpod OpenAI-compatible endpoints and serverless endpoints.",
        fields=(
            IntegrationFieldDefinition("api_key", "API key", ("RUNPOD_API_KEY",), secret=True, placeholder="rpa_..."),
            IntegrationFieldDefinition("openai_base_url", "OpenAI base URL", ("RUNPOD_OPENAI_BASE_URL", "RUNPOD_BASE_URL"), placeholder="https://api.runpod.ai/v2/<endpoint>/openai/v1"),
            IntegrationFieldDefinition("endpoint_id", "Serverless endpoint ID", ("RUNPOD_ENDPOINT_ID",), placeholder="endpoint id"),
            IntegrationFieldDefinition("endpoint_url", "Serverless endpoint URL", ("RUNPOD_ENDPOINT_URL",), placeholder="https://api.runpod.ai/v2/<endpoint>"),
            IntegrationFieldDefinition("model", "Default model", ("RUNPOD_OPENAI_MODEL", "RUNPOD_MODEL"), placeholder="caid-technologies/parti-base"),
            IntegrationFieldDefinition("timeout_seconds", "Timeout seconds", ("RUNPOD_TIMEOUT_SECONDS", "RUNPOD_POLL_TIMEOUT_SECONDS"), placeholder="1200"),
        ),
    ),
    IntegrationDefinition(
        id="gmi",
        label="GMI Cloud",
        description="GMI/Fable LLM access plus GMI Cloud image/video generation settings.",
        fields=(
            IntegrationFieldDefinition("api_key", "API key", ("GMI_API_KEY", "GMI_CLOUD_API_KEY", "GMICLOUD_API_KEY"), secret=True, placeholder="gmi key"),
            IntegrationFieldDefinition("llm_base_url", "LLM base URL", ("GMI_BASE_URL",), placeholder="https://api.gmi-serving.com/v1"),
            IntegrationFieldDefinition("video_base_url", "Video base URL", ("GMI_CLOUD_BASE_URL", "GMICLOUD_BASE_URL"), placeholder="https://console.gmicloud.ai"),
            IntegrationFieldDefinition("model", "Default LLM model", ("GMI_MODEL", "GMI_STREAM_MODEL", "GMI_CLOUD_MODEL", "GMICLOUD_MODEL"), placeholder="anthropic/claude-fable-5"),
            IntegrationFieldDefinition("image_to_video_model", "Image-to-video model", ("GMI_CLOUD_IMAGE_TO_VIDEO_MODEL",), placeholder="kling-v3-image-to-video"),
            IntegrationFieldDefinition("timeout_seconds", "Timeout seconds", ("GMI_TIMEOUT_SECONDS", "GMI_STREAM_TIMEOUT_SECONDS", "GMI_CLOUD_TIMEOUT_SECONDS"), placeholder="1200"),
        ),
    ),
    IntegrationDefinition(
        id="huggingface",
        label="Hugging Face",
        description="Hugging Face Router models and artifact upload configuration.",
        fields=(
            IntegrationFieldDefinition("api_key", "Token", ("HF_TOKEN", "HUGGINGFACE_API_KEY", "HUGGINGFACE_HUB_TOKEN", "HF_API_TOKEN"), secret=True, placeholder="hf_..."),
            IntegrationFieldDefinition("base_url", "Router base URL", ("HUGGINGFACE_BASE_URL", "HF_BASE_URL"), placeholder="https://router.huggingface.co/v1"),
            IntegrationFieldDefinition("model", "Default model", ("HUGGINGFACE_MODEL", "HF_MODEL"), placeholder="Qwen/Qwen2.5-72B-Instruct:deepinfra"),
            IntegrationFieldDefinition("artifact_repo_id", "Artifact repo", ("HF_ARTIFACT_REPO_ID", "HUGGINGFACE_ARTIFACT_REPO_ID", "HF_DATASET_REPO_ID"), placeholder="user/dataset"),
            IntegrationFieldDefinition("timeout_seconds", "Timeout seconds", ("HUGGINGFACE_TIMEOUT_SECONDS", "HF_TIMEOUT_SECONDS"), placeholder="1200"),
        ),
    ),
    IntegrationDefinition(
        id="nvidia",
        label="NVIDIA Build",
        description="NVIDIA NIM/OpenAI-compatible model routing.",
        fields=(
            IntegrationFieldDefinition("api_key", "API key", ("NVIDIA_API_KEY", "NVIDIA_NIM_API_KEY", "NIM_API_KEY"), secret=True, placeholder="nvapi-..."),
            IntegrationFieldDefinition("base_url", "Base URL", ("NVIDIA_BASE_URL", "NVIDIA_NIM_BASE_URL", "NIM_BASE_URL"), placeholder="https://integrate.api.nvidia.com/v1"),
            IntegrationFieldDefinition("model", "Default model", ("NVIDIA_MODEL", "NVIDIA_NIM_MODEL", "NIM_MODEL"), placeholder="qwen/qwen2.5-coder-32b-instruct"),
            IntegrationFieldDefinition("timeout_seconds", "Timeout seconds", ("NVIDIA_TIMEOUT_SECONDS", "NVIDIA_NIM_TIMEOUT_SECONDS", "NIM_TIMEOUT_SECONDS"), placeholder="1200"),
        ),
    ),
    IntegrationDefinition(
        id="gemini",
        label="Gemini",
        description="Google Gemini structured generation.",
        fields=(
            IntegrationFieldDefinition("api_key", "API key", ("GEMINI_API_KEY", "GOOGLE_API_KEY"), secret=True, placeholder="AIza..."),
            IntegrationFieldDefinition("model", "Default model", ("GEMINI_MODEL",), placeholder="gemini-3.5-flash"),
            IntegrationFieldDefinition("fallback_model", "Fallback model", ("GEMINI_FALLBACK_MODEL",), placeholder="gemini-2.5-flash"),
        ),
    ),
    IntegrationDefinition(
        id="firecrawl",
        label="Firecrawl",
        description="Firecrawl MCP search and page extraction.",
        fields=(
            IntegrationFieldDefinition("api_key", "API key", ("FIRECRAWL_API_KEY",), secret=True, placeholder="fc-..."),
            IntegrationFieldDefinition("mcp_command", "MCP command", ("FIRECRAWL_MCP_COMMAND",), placeholder="npx -y firecrawl-mcp"),
            IntegrationFieldDefinition("search_limit", "Search limit", ("FIRECRAWL_SEARCH_LIMIT",), placeholder="3"),
            IntegrationFieldDefinition("timeout_seconds", "Timeout seconds", ("FIRECRAWL_MCP_TIMEOUT_SECONDS",), placeholder="45"),
        ),
    ),
    IntegrationDefinition(
        id="ollama",
        label="Ollama",
        description="Local OpenAI-compatible Ollama endpoints.",
        fields=(
            IntegrationFieldDefinition("base_url", "OpenAI base URL", ("OLLAMA_OPENAI_BASE_URL",), placeholder="http://127.0.0.1:11434/v1"),
            IntegrationFieldDefinition("model", "Default model", ("OLLAMA_BLUEPRINT_MODEL",), placeholder="qwen3:0.6b"),
        ),
    ),
)

_DEFINITION_BY_ID = {definition.id: definition for definition in INTEGRATION_DEFINITIONS}
_APPLIED_ENV_VALUES: dict[str, str] = {}
_ORIGINAL_ENV_VALUES: dict[str, Optional[str]] = {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _configured_path() -> Optional[Path]:
    for env_name in CONFIG_PATH_ENV_NAMES:
        raw_value = os.getenv(env_name)
        if raw_value and raw_value.strip():
            return Path(raw_value.strip()).expanduser()
    for env_name in CONFIG_DIR_ENV_NAMES:
        raw_value = os.getenv(env_name)
        if raw_value and raw_value.strip():
            return Path(raw_value.strip()).expanduser() / DEFAULT_CONFIG_FILENAME
    return None


def default_user_integrations_path() -> Path:
    return _configured_path() or (_repo_root() / DEFAULT_CONFIG_DIR / DEFAULT_CONFIG_FILENAME)


def integration_definition_by_id(integration_id: str) -> IntegrationDefinition:
    definition = _DEFINITION_BY_ID.get(integration_id)
    if definition is None:
        raise KeyError(f"Unknown integration {integration_id!r}.")
    return definition


def list_integration_definitions() -> tuple[IntegrationDefinition, ...]:
    return INTEGRATION_DEFINITIONS


class UserIntegrationStore:
    def __init__(self, path: Optional[Path | str] = None) -> None:
        self.path = Path(path).expanduser() if path is not None else default_user_integrations_path()

    def load(self) -> UserIntegrationConfig:
        if not self.path.exists():
            return UserIntegrationConfig()
        try:
            with self.path.open("r", encoding="utf-8") as file:
                raw = json.load(file)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"User integrations config is invalid JSON: {self.path}") from exc
        return UserIntegrationConfig.from_raw(raw)

    def save(self, config: UserIntegrationConfig) -> UserIntegrationConfig:
        config.updated_at = _utc_now()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        with temp_path.open("w", encoding="utf-8") as file:
            json.dump(config.as_json(), file, indent=2, sort_keys=True)
            file.write("\n")
        os.replace(temp_path, self.path)
        try:
            self.path.chmod(0o600)
        except OSError:
            pass
        return config

    def update_integration(
        self,
        integration_id: str,
        *,
        enabled: Optional[bool] = None,
        field_values: Optional[dict[str, Optional[str]]] = None,
        clear_fields: Iterable[str] = (),
    ) -> UserIntegrationConfig:
        definition = integration_definition_by_id(integration_id)
        config = self.load()
        integration = config.ensure_integration(definition.id)
        if enabled is not None:
            integration.enabled = bool(enabled)

        for field_id in clear_fields:
            definition.field_by_id(field_id)
            integration.clear_field(field_id)

        for field_id, value in (field_values or {}).items():
            definition.field_by_id(field_id)
            if value is None or str(value).strip() == "":
                integration.clear_field(field_id)
            else:
                integration.set_field(field_id, str(value))

        integration.updated_at = _utc_now()
        return self.save(config)

    def clear_integration(self, integration_id: str) -> UserIntegrationConfig:
        integration_definition_by_id(integration_id)
        config = self.load()
        config.integrations = [integration for integration in config.integrations if integration.id != integration_id]
        return self.save(config)


def mask_secret(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def _first_env(env_names: Iterable[str]) -> Optional[str]:
    for env_name in env_names:
        value = os.getenv(env_name)
        if value and value.strip():
            return value.strip()
    return None


def _desired_environment(config: UserIntegrationConfig) -> dict[str, str]:
    desired: dict[str, str] = {}
    for integration in config.integrations:
        if not integration.enabled:
            continue
        definition = _DEFINITION_BY_ID.get(integration.id)
        if definition is None:
            continue
        for field_definition in definition.fields:
            value = integration.field_value(field_definition.id)
            if not value:
                continue
            for env_name in field_definition.env_names:
                desired[env_name] = value
    return desired


def apply_user_integrations_to_environment(store: Optional[UserIntegrationStore] = None) -> UserIntegrationConfig:
    resolved_store = store or UserIntegrationStore()
    config = resolved_store.load()
    desired = _desired_environment(config)

    for env_name, applied_value in list(_APPLIED_ENV_VALUES.items()):
        if env_name in desired:
            continue
        if os.environ.get(env_name) == applied_value:
            original_value = _ORIGINAL_ENV_VALUES.pop(env_name, None)
            if original_value is None:
                os.environ.pop(env_name, None)
            else:
                os.environ[env_name] = original_value
        _APPLIED_ENV_VALUES.pop(env_name, None)

    for env_name, desired_value in desired.items():
        if env_name not in _ORIGINAL_ENV_VALUES:
            _ORIGINAL_ENV_VALUES[env_name] = os.environ.get(env_name)
        os.environ[env_name] = desired_value
        _APPLIED_ENV_VALUES[env_name] = desired_value

    return config


def _field_status_payload(
    integration: Optional[StoredIntegration],
    field_definition: IntegrationFieldDefinition,
) -> dict[str, object]:
    saved_value = integration.field_value(field_definition.id) if integration else None
    env_value = _first_env(field_definition.env_names)
    active_value = saved_value or env_value
    source = "saved" if saved_value else ("environment" if env_value else "unset")
    payload: dict[str, object] = {
        "id": field_definition.id,
        "label": field_definition.label,
        "env_names": list(field_definition.env_names),
        "secret": field_definition.secret,
        "placeholder": field_definition.placeholder,
        "help": field_definition.help,
        "configured": bool(active_value),
        "saved": bool(saved_value),
        "source": source,
    }
    if field_definition.secret:
        payload["masked_value"] = mask_secret(active_value)
        payload["value"] = None
    else:
        payload["masked_value"] = None
        payload["value"] = active_value
    return payload


def integration_status_payload(store: Optional[UserIntegrationStore] = None) -> dict[str, object]:
    resolved_store = store or UserIntegrationStore()
    config = apply_user_integrations_to_environment(resolved_store)
    integrations: list[dict[str, object]] = []
    for definition in INTEGRATION_DEFINITIONS:
        stored = config.integration_by_id(definition.id)
        configured_fields = [
            _field_status_payload(stored, field_definition)
            for field_definition in definition.fields
        ]
        integrations.append(
            {
                "id": definition.id,
                "label": definition.label,
                "description": definition.description,
                "enabled": stored.enabled if stored else True,
                "saved": stored is not None,
                "updated_at": stored.updated_at if stored else None,
                "configured": any(bool(field_payload["configured"]) for field_payload in configured_fields),
                "fields": configured_fields,
            }
        )
    return {
        "version": config.version,
        "config_path": str(resolved_store.path),
        "updated_at": config.updated_at,
        "integrations": integrations,
    }


__all__ = [
    "IntegrationDefinition",
    "IntegrationFieldDefinition",
    "StoredIntegration",
    "StoredIntegrationField",
    "UserIntegrationConfig",
    "UserIntegrationStore",
    "apply_user_integrations_to_environment",
    "default_user_integrations_path",
    "integration_definition_by_id",
    "integration_status_payload",
    "list_integration_definitions",
    "mask_secret",
]
