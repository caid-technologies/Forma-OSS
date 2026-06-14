import base64
import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_IMAGE_TEXT_MODEL = "gpt-4o-mini"
DEFAULT_OLLAMA_IMAGE_TEXT_MODEL = "llava:latest"
DEFAULT_IMAGE_TEXT_TIMEOUT_SECONDS = 120.0
DEFAULT_IMAGE_TEXT_PROMPT = (
    "Describe the uploaded hardware reference image for a hardware design agent. "
    "Focus on visible device type, enclosure, display, controls, ports, sensors, connectors, "
    "wiring, labels, materials, scale cues, and safety-relevant details. Keep it concise."
)


@dataclass
class ImageTextExtraction:
    text: str
    provider: str
    model: str
    prompt: str


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
        logger.warning("Invalid image text timeout value %r; using %.1fs.", raw_value, default)
        return default


def _first_env_int(names: List[str]) -> Optional[int]:
    raw_value = _first_env(names)
    if raw_value is None:
        return None
    try:
        return int(raw_value)
    except ValueError:
        logger.warning("Invalid image text integer value %r; ignoring it.", raw_value)
        return None


def _first_env_optional_float(names: List[str]) -> Optional[float]:
    raw_value = _first_env(names)
    if raw_value is None:
        return None
    if raw_value.strip().lower() in {"default", "none", "omit"}:
        return None
    try:
        return float(raw_value)
    except ValueError:
        logger.warning("Invalid image text float value %r; ignoring it.", raw_value)
        return None


def _image_data_url(image_bytes: bytes, image_mime_type: Optional[str]) -> str:
    mime_type = image_mime_type or "image/png"
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _extract_text_from_chat_response(response: Dict[str, Any]) -> str:
    choices = response.get("choices") or []
    if not choices:
        return ""

    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for part in content:
            if not isinstance(part, dict):
                continue
            text = part.get("text") or part.get("content")
            if isinstance(text, str):
                parts.append(text)
        return "\n".join(parts).strip()
    return ""


class ImageTextProvider:
    provider_name = "none"
    model_name = "none"
    is_configured = False
    enabled = False

    def get_debug_config(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "enabled": self.enabled,
            "configured": self.is_configured,
            "model_name": self.model_name,
        }

    def extract_text(self, image_bytes: bytes, image_mime_type: Optional[str], user_prompt: str = "") -> Optional[ImageTextExtraction]:
        raise NotImplementedError


class NoImageTextProvider(ImageTextProvider):
    provider_name = "none"
    model_name = "none"

    def __init__(self, reason: str = "Image text extraction is disabled.") -> None:
        self.reason = reason
        self.enabled = False
        self.is_configured = False

    def get_debug_config(self) -> Dict[str, Any]:
        return {
            **super().get_debug_config(),
            "reason": self.reason,
        }

    def extract_text(self, image_bytes: bytes, image_mime_type: Optional[str], user_prompt: str = "") -> Optional[ImageTextExtraction]:
        return None


class OpenAICompatibleImageTextProvider(ImageTextProvider):
    def __init__(self, provider_name: str = "openai-compatible") -> None:
        normalized_provider = provider_name.strip().lower().replace("_", "-")
        self.provider_name = "openai" if normalized_provider == "openai" else "openai-compatible"
        self.enabled = True

        if self.provider_name == "openai":
            api_key_names = ["IMAGE_TEXT_API_KEY", "OPENAI_API_KEY", "LLM_API_KEY"]
            base_url_names = ["IMAGE_TEXT_BASE_URL", "OPENAI_BASE_URL", "LLM_BASE_URL"]
            model_names = ["IMAGE_TEXT_MODEL", "OPENAI_IMAGE_TEXT_MODEL", "OPENAI_MODEL", "LLM_MODEL"]
            allow_no_api_key_names = ["IMAGE_TEXT_ALLOW_NO_API_KEY", "OPENAI_ALLOW_NO_API_KEY", "LLM_ALLOW_NO_API_KEY"]
        else:
            api_key_names = ["IMAGE_TEXT_API_KEY", "LLM_API_KEY", "OPENAI_API_KEY"]
            base_url_names = ["IMAGE_TEXT_BASE_URL", "LLM_BASE_URL", "OPENAI_BASE_URL"]
            model_names = ["IMAGE_TEXT_MODEL", "LLM_MODEL", "OPENAI_MODEL"]
            allow_no_api_key_names = ["IMAGE_TEXT_ALLOW_NO_API_KEY", "LLM_ALLOW_NO_API_KEY", "OPENAI_ALLOW_NO_API_KEY"]

        configured_base_url = _first_env(base_url_names)
        default_base_url = "https://api.openai.com/v1" if self.provider_name == "openai" else None
        self.base_url = (configured_base_url or default_base_url or "").rstrip("/")
        self.api_key = _first_env(api_key_names)
        self.model_name = _first_env(model_names, DEFAULT_IMAGE_TEXT_MODEL) or DEFAULT_IMAGE_TEXT_MODEL
        self.prompt = _first_env(["IMAGE_TEXT_PROMPT"], DEFAULT_IMAGE_TEXT_PROMPT) or DEFAULT_IMAGE_TEXT_PROMPT
        self.timeout_seconds = _first_env_float(["IMAGE_TEXT_TIMEOUT_SECONDS", "LLM_TIMEOUT_SECONDS"], DEFAULT_IMAGE_TEXT_TIMEOUT_SECONDS)
        self.max_tokens = _first_env_int(["IMAGE_TEXT_MAX_TOKENS"])
        self.temperature = _first_env_optional_float(["IMAGE_TEXT_TEMPERATURE"])
        self.allow_no_api_key = _first_env_bool(
            allow_no_api_key_names,
            default=self.provider_name != "openai" and configured_base_url is not None,
        )
        self.is_configured = bool(self.base_url and (self.api_key or self.allow_no_api_key))

    def get_debug_config(self) -> Dict[str, Any]:
        reason = None
        if not self.base_url:
            reason = "Image text provider base URL is missing."
        elif not self.api_key and not self.allow_no_api_key:
            reason = "Image text provider API key is missing."

        return {
            **super().get_debug_config(),
            "base_url": self.base_url,
            "reason": reason,
        }

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
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
            raise RuntimeError(f"{self.provider_name} image text request failed with HTTP {exc.code}: {detail[:500]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"{self.provider_name} image text request failed: {exc}") from exc

        if not body.strip():
            return {}
        return json.loads(body)

    def extract_text(self, image_bytes: bytes, image_mime_type: Optional[str], user_prompt: str = "") -> Optional[ImageTextExtraction]:
        if not self.is_configured:
            return None

        prompt = self.prompt
        if user_prompt:
            prompt = f"{prompt}\n\nUser prompt context: {user_prompt.strip()[:500]}"

        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": _image_data_url(image_bytes, image_mime_type)}},
                    ],
                }
            ],
        }
        if self.max_tokens:
            payload["max_tokens"] = self.max_tokens
        if self.temperature is not None:
            payload["temperature"] = self.temperature

        response = self._request_json("chat/completions", method="POST", payload=payload)
        text = _extract_text_from_chat_response(response)
        if not text:
            raise RuntimeError(f"{self.provider_name} image text response did not include text content.")

        return ImageTextExtraction(text=text, provider=self.provider_name, model=self.model_name, prompt=prompt)


class OllamaImageTextProvider(ImageTextProvider):
    provider_name = "ollama"

    def __init__(self) -> None:
        self.enabled = True
        self.base_url = (_first_env(["IMAGE_TEXT_BASE_URL", "OLLAMA_BASE_URL"], "http://localhost:11434") or "").rstrip("/")
        self.model_name = (
            _first_env(["IMAGE_TEXT_MODEL", "OLLAMA_IMAGE_TEXT_MODEL"], DEFAULT_OLLAMA_IMAGE_TEXT_MODEL)
            or DEFAULT_OLLAMA_IMAGE_TEXT_MODEL
        )
        self.prompt = _first_env(["IMAGE_TEXT_PROMPT"], DEFAULT_IMAGE_TEXT_PROMPT) or DEFAULT_IMAGE_TEXT_PROMPT
        self.timeout_seconds = _first_env_float(["IMAGE_TEXT_TIMEOUT_SECONDS", "OLLAMA_TIMEOUT_SECONDS"], DEFAULT_IMAGE_TEXT_TIMEOUT_SECONDS)
        self.num_predict = _first_env_int(["IMAGE_TEXT_MAX_TOKENS", "OLLAMA_IMAGE_TEXT_NUM_PREDICT"])
        self.temperature = _first_env_optional_float(["IMAGE_TEXT_TEMPERATURE", "OLLAMA_IMAGE_TEXT_TEMPERATURE"])
        self.is_configured = bool(self.base_url and self.model_name)

    def get_debug_config(self) -> Dict[str, Any]:
        return {
            **super().get_debug_config(),
            "base_url": self.base_url,
            "reason": None if self.is_configured else "Ollama image text provider is missing a base URL or model.",
        }

    def _request_json(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/api/generate"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"ollama image text request failed with HTTP {exc.code}: {detail[:500]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"ollama image text request failed: {exc}") from exc

        if not body.strip():
            return {}
        return json.loads(body)

    def extract_text(self, image_bytes: bytes, image_mime_type: Optional[str], user_prompt: str = "") -> Optional[ImageTextExtraction]:
        if not self.is_configured:
            return None

        prompt = self.prompt
        if user_prompt:
            prompt = f"{prompt}\n\nUser prompt context: {user_prompt.strip()[:500]}"

        options: Dict[str, Any] = {}
        if self.num_predict:
            options["num_predict"] = self.num_predict
        if self.temperature is not None:
            options["temperature"] = self.temperature

        payload: Dict[str, Any] = {
            "model": self.model_name,
            "prompt": prompt,
            "images": [base64.b64encode(image_bytes).decode("ascii")],
            "stream": False,
        }
        if options:
            payload["options"] = options

        response = self._request_json(payload)
        text = response.get("response")
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("ollama image text response did not include text content.")

        return ImageTextExtraction(text=text.strip(), provider=self.provider_name, model=self.model_name, prompt=prompt)


def build_image_text_provider() -> ImageTextProvider:
    provider_name = (_env("IMAGE_TEXT_PROVIDER") or "").strip().lower().replace("_", "-")
    if not provider_name:
        if _first_env(["OLLAMA_IMAGE_TEXT_MODEL"]):
            provider_name = "ollama"
        elif _first_env(["IMAGE_TEXT_BASE_URL", "IMAGE_TEXT_MODEL"]):
            provider_name = "openai-compatible"
        else:
            return NoImageTextProvider()

    if provider_name in {"none", "disabled", "off", "false", "simulation", "mock"}:
        return NoImageTextProvider()
    if provider_name in {"openai", "openai-compatible", "compatible", "local", "local-openai", "local-openai-compatible"}:
        return OpenAICompatibleImageTextProvider(provider_name=provider_name)
    if provider_name in {"ollama", "local-ollama"}:
        return OllamaImageTextProvider()

    logger.warning("Unsupported IMAGE_TEXT_PROVIDER %r; image text extraction is disabled.", provider_name)
    return NoImageTextProvider(
        f"Unsupported IMAGE_TEXT_PROVIDER '{provider_name}'. Supported providers are openai, openai-compatible, local, ollama, and none."
    )


def get_image_text_debug_config() -> Dict[str, Any]:
    provider = build_image_text_provider()
    return provider.get_debug_config()
