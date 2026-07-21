import base64
import html
import io
import json
import logging
import os
import uuid
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

from blueprint_core.prompt_compaction import (
    DEFAULT_IMAGE_PROMPT_TARGET_CHARS,
    OPENAI_IMAGE_PROMPT_MAX_CHARS,
    PromptCompactionAgent,
    PromptCompactionResult,
)

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_OPENAI_IMAGE_MODEL = "gpt-image-2"
DEFAULT_GMI_IMAGE_BASE_URL = "https://console.gmicloud.ai/api/v1/ie/requestqueue/apikey/requests/v1"
DEFAULT_GMI_IMAGE_MODEL = "gpt-image-2"
DEFAULT_GMI_IMAGE_QUALITY = "medium"
DEFAULT_TOGETHER_IMAGE_BASE_URL = "https://api.together.ai/v1"
DEFAULT_TOGETHER_IMAGE_MODEL = "openai/gpt-image-2"
DEFAULT_TOGETHER_IMAGE_STEPS = 4
DEFAULT_IMAGE_SIZE = "1024x1024"
DEFAULT_IMAGE_TIMEOUT_SECONDS = 120.0
HUGGINGFACE_IMAGE_PROMPT_MAX_CHARS = 6000
HUGGINGFACE_IMAGE_PROMPT_TARGET_CHARS = 4000


@dataclass
class GeneratedImage:
    data_url: str
    provider: str
    model: str
    size: str
    prompt: str
    output_format: str = "png"
    view_id: str = "product"
    label: str = "Product render"
    reference_view_id: Optional[str] = None
    prompt_original_length: Optional[int] = None
    prompt_final_length: Optional[int] = None
    prompt_compacted: bool = False
    prompt_compaction_strategy: str = "none"
    model_revision: Optional[str] = None
    inference_provider: Optional[str] = None
    model_license: Optional[str] = None


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
        logger.warning("Invalid image timeout value %r; using %.1fs.", raw_value, default)
        return default


def _first_env_int(names: List[str], default: int) -> int:
    raw_value = _first_env(names)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError:
        logger.warning("Invalid image integer config value %r; using %s.", raw_value, default)
        return default


def _truncate(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."


def _limit_list(values: List[Any], limit: int, item_limit: int = 140) -> List[str]:
    result: List[str] = []
    for value in values:
        text = _truncate(value, item_limit)
        if text:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _model_supports_gpt_image_params(model_name: str) -> bool:
    return model_name.strip().lower().startswith("gpt-image")


def _together_model_supports_flux_params(model_name: str) -> bool:
    return model_name.strip().lower().startswith("black-forest-labs/flux")


def _mime_for_output_format(output_format: str) -> str:
    normalized = (output_format or "png").strip().lower()
    if normalized == "jpg":
        normalized = "jpeg"
    if normalized in {"jpeg", "png", "webp"}:
        return f"image/{normalized}"
    return "image/png"


class ImageProvider:
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

    def generate_project_image(self, user_prompt: str, ir: Any) -> Optional[GeneratedImage]:
        raise NotImplementedError

    def generate_project_image_sequence(self, user_prompt: str, ir: Any) -> List[GeneratedImage]:
        image = self.generate_project_image(user_prompt, ir)
        return [image] if image else []


class NoImageProvider(ImageProvider):
    provider_name = "none"
    model_name = "none"

    def __init__(self, reason: str = "Image output is disabled.") -> None:
        self.reason = reason
        self.enabled = False
        self.is_configured = False

    def get_debug_config(self) -> Dict[str, Any]:
        return {
            **super().get_debug_config(),
            "reason": self.reason,
        }

    def generate_project_image(self, user_prompt: str, ir: Any) -> Optional[GeneratedImage]:
        return None


class OpenAIImageProvider(ImageProvider):
    def __init__(self, provider_name: str = "openai", enabled: bool = True, force_enabled: bool = False) -> None:
        normalized_provider = provider_name.strip().lower().replace("_", "-")
        self.provider_name = "openai-compatible" if normalized_provider != "openai" else "openai"
        self.enabled = enabled or force_enabled

        if self.provider_name == "openai":
            api_key_names = ["OPENAI_IMAGE_API_KEY", "OPENAI_API_KEY"]
            base_url_names = ["OPENAI_IMAGE_BASE_URL", "OPENAI_BASE_URL"]
            model_names = ["OPENAI_IMAGE_MODEL", "IMAGE_MODEL"]
            timeout_names = ["OPENAI_IMAGE_TIMEOUT_SECONDS", "IMAGE_TIMEOUT_SECONDS"]
            allow_no_api_key_names = ["OPENAI_IMAGE_ALLOW_NO_API_KEY"]
        else:
            api_key_names = ["IMAGE_API_KEY", "OPENAI_IMAGE_API_KEY", "LLM_API_KEY", "OPENAI_API_KEY"]
            base_url_names = ["IMAGE_BASE_URL", "OPENAI_IMAGE_BASE_URL", "LLM_BASE_URL", "OPENAI_BASE_URL"]
            model_names = ["IMAGE_MODEL", "OPENAI_IMAGE_MODEL"]
            timeout_names = ["IMAGE_TIMEOUT_SECONDS", "OPENAI_IMAGE_TIMEOUT_SECONDS"]
            allow_no_api_key_names = ["IMAGE_ALLOW_NO_API_KEY", "OPENAI_IMAGE_ALLOW_NO_API_KEY", "LLM_ALLOW_NO_API_KEY"]

        configured_base_url = _first_env(base_url_names)
        default_base_url = "https://api.openai.com/v1" if self.provider_name == "openai" else None
        self.base_url = (configured_base_url or default_base_url or "").rstrip("/")
        self.api_key = _first_env(api_key_names)
        self.organization_id = _first_env(["OPENAI_ORG_ID", "OPENAI_ORGANIZATION", "OPENAI_ORGANIZATION_ID"])
        self.project_id = _first_env(["OPENAI_PROJECT_ID", "OPENAI_PROJECT"])
        self.model_name = _first_env(model_names, DEFAULT_OPENAI_IMAGE_MODEL) or DEFAULT_OPENAI_IMAGE_MODEL
        self.size = _first_env(["OPENAI_IMAGE_SIZE", "IMAGE_SIZE"], DEFAULT_IMAGE_SIZE) or DEFAULT_IMAGE_SIZE
        self.quality = _first_env(["OPENAI_IMAGE_QUALITY", "IMAGE_QUALITY"])
        self.output_format = _first_env(["OPENAI_IMAGE_OUTPUT_FORMAT", "IMAGE_OUTPUT_FORMAT"], "png") or "png"
        self.timeout_seconds = _first_env_float(timeout_names, DEFAULT_IMAGE_TIMEOUT_SECONDS)
        self.prompt_max_chars = _first_env_int(
            ["OPENAI_IMAGE_PROMPT_MAX_CHARS", "IMAGE_PROMPT_MAX_CHARS"],
            OPENAI_IMAGE_PROMPT_MAX_CHARS,
        )
        self.prompt_target_chars = _first_env_int(
            ["OPENAI_IMAGE_PROMPT_TARGET_CHARS", "IMAGE_PROMPT_TARGET_CHARS"],
            DEFAULT_IMAGE_PROMPT_TARGET_CHARS,
        )
        self.prompt_compactor = PromptCompactionAgent()
        self.allow_no_api_key = _first_env_bool(
            allow_no_api_key_names,
            default=self.provider_name != "openai" and configured_base_url is not None,
        )
        self.is_configured = bool(self.enabled and self.base_url and (self.api_key or self.allow_no_api_key))

    def get_debug_config(self) -> Dict[str, Any]:
        reason = None
        if not self.enabled:
            reason = "Image output is disabled."
        elif not self.base_url:
            reason = "Image provider base URL is missing."
        elif not self.api_key and not self.allow_no_api_key:
            reason = "Image provider API key is missing."

        return {
            **super().get_debug_config(),
            "base_url": self.base_url,
            "size": self.size,
            "quality": self.quality,
            "output_format": self.output_format,
            "prompt_max_chars": self.prompt_max_chars,
            "prompt_target_chars": self.prompt_target_chars,
            "reason": reason,
        }

    def _headers(self, content_type: Optional[str] = "application/json") -> Dict[str, str]:
        headers: Dict[str, str] = {
            "Accept": "application/json",
            "User-Agent": "Blueprint-OSS/1.0",
        }
        if content_type:
            headers["Content-Type"] = content_type
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
            raise RuntimeError(f"{self.provider_name} image request failed with HTTP {exc.code}: {detail[:500]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"{self.provider_name} image request failed: {exc}") from exc

        if not body.strip():
            return {}
        return json.loads(body)

    def _request_multipart(
        self,
        path: str,
        fields: Dict[str, Any],
        files: List[Tuple[str, str, bytes, str]],
    ) -> Dict[str, Any]:
        boundary = f"----BlueprintImageBoundary{uuid.uuid4().hex}"
        body_parts: List[bytes] = []

        for name, value in fields.items():
            if value is None:
                continue
            body_parts.extend(
                [
                    f"--{boundary}\r\n".encode("utf-8"),
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                    str(value).encode("utf-8"),
                    b"\r\n",
                ]
            )

        for field_name, filename, content, content_type in files:
            body_parts.extend(
                [
                    f"--{boundary}\r\n".encode("utf-8"),
                    (
                        f'Content-Disposition: form-data; name="{field_name}"; '
                        f'filename="{filename}"\r\n'
                    ).encode("utf-8"),
                    f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
                    content,
                    b"\r\n",
                ]
            )

        body_parts.append(f"--{boundary}--\r\n".encode("utf-8"))
        body = b"".join(body_parts)
        request = urllib.request.Request(
            f"{self.base_url}/{path.lstrip('/')}",
            data=body,
            headers=self._headers(f"multipart/form-data; boundary={boundary}"),
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{self.provider_name} image edit request failed with HTTP {exc.code}: {detail[:500]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"{self.provider_name} image edit request failed: {exc}") from exc

        return json.loads(raw_body) if raw_body.strip() else {}

    def generate_project_image(self, user_prompt: str, ir: Any) -> Optional[GeneratedImage]:
        if not self.is_configured:
            return None

        image_prompt = build_project_image_prompt(user_prompt, ir)
        return self._generate_image_from_prompt(
            image_prompt,
            view_id="case",
            label="Exterior case render",
            reference_view_id=None,
        )

    def generate_project_image_sequence(self, user_prompt: str, ir: Any) -> List[GeneratedImage]:
        if not self.is_configured:
            return []

        prompts = build_project_image_sequence_prompts(user_prompt, ir)
        sequence: List[GeneratedImage] = []
        previous: Optional[GeneratedImage] = None

        for item in prompts:
            view_id = item["view_id"]
            label = item["label"]
            prompt = item["prompt"]
            if item.get("generation_mode") == "deterministic_svg":
                prompt_result = self._compact_image_prompt(prompt, view_id=view_id)
                image = build_project_layout_diagram_image(
                    user_prompt,
                    ir,
                    prompt=prompt_result.prompt,
                    reference_view_id="visual_spec",
                    prompt_compaction_result=prompt_result,
                )
                sequence.append(image)
                previous = image
                continue

            reference_view_id = previous.view_id if previous else None
            try:
                if previous:
                    image = self._edit_image_from_prompt(
                        prompt,
                        previous,
                        view_id=view_id,
                        label=label,
                        reference_view_id=reference_view_id,
                    )
                else:
                    image = self._generate_image_from_prompt(
                        prompt,
                        view_id=view_id,
                        label=label,
                        reference_view_id=None,
                    )
            except Exception as exc:
                if not previous:
                    raise
                logger.warning("Image-to-image stage %s failed; falling back to text generation: %s", view_id, exc)
                image = self._generate_image_from_prompt(
                    prompt,
                    view_id=view_id,
                    label=label,
                    reference_view_id=reference_view_id,
                )
            sequence.append(image)
            previous = image

        return sequence

    def _generate_image_from_prompt(
        self,
        image_prompt: str,
        *,
        view_id: str,
        label: str,
        reference_view_id: Optional[str],
    ) -> GeneratedImage:
        prompt_result = self._compact_image_prompt(image_prompt, view_id=view_id)
        payload: Dict[str, Any] = {
            "model": self.model_name,
            "prompt": prompt_result.prompt,
            "size": self.size,
            "n": 1,
        }

        if _model_supports_gpt_image_params(self.model_name):
            if self.quality:
                payload["quality"] = self.quality
            if self.output_format:
                payload["output_format"] = self.output_format

        response = self._request_json("images/generations", method="POST", payload=payload)
        item = _first_image_item(response)
        if not item:
            raise RuntimeError(f"{self.provider_name} image response did not include image data.")

        return GeneratedImage(
            data_url=_image_data_url_from_item(item, self.output_format, self.provider_name),
            provider=self.provider_name,
            model=self.model_name,
            size=self.size,
            prompt=prompt_result.prompt,
            output_format=self.output_format,
            view_id=view_id,
            label=label,
            reference_view_id=reference_view_id,
            prompt_original_length=prompt_result.original_length,
            prompt_final_length=prompt_result.final_length,
            prompt_compacted=prompt_result.was_compacted,
            prompt_compaction_strategy=prompt_result.strategy,
        )

    def _edit_image_from_prompt(
        self,
        image_prompt: str,
        reference_image: GeneratedImage,
        *,
        view_id: str,
        label: str,
        reference_view_id: Optional[str],
    ) -> GeneratedImage:
        prompt_result = self._compact_image_prompt(image_prompt, view_id=view_id)
        reference_bytes, reference_content_type = _image_bytes_from_data(reference_image.data_url)
        fields: Dict[str, Any] = {
            "model": self.model_name,
            "prompt": prompt_result.prompt,
            "size": self.size,
            "n": 1,
        }
        if _model_supports_gpt_image_params(self.model_name):
            if self.quality:
                fields["quality"] = self.quality
            if self.output_format:
                fields["output_format"] = self.output_format

        response = self._request_multipart(
            "images/edits",
            fields,
            [("image", f"{reference_image.view_id or 'reference'}.png", reference_bytes, reference_content_type)],
        )
        item = _first_image_item(response)
        if not item:
            raise RuntimeError(f"{self.provider_name} image edit response did not include image data.")

        return GeneratedImage(
            data_url=_image_data_url_from_item(item, self.output_format, self.provider_name),
            provider=self.provider_name,
            model=self.model_name,
            size=self.size,
            prompt=prompt_result.prompt,
            output_format=self.output_format,
            view_id=view_id,
            label=label,
            reference_view_id=reference_view_id,
            prompt_original_length=prompt_result.original_length,
            prompt_final_length=prompt_result.final_length,
            prompt_compacted=prompt_result.was_compacted,
            prompt_compaction_strategy=prompt_result.strategy,
        )

    def _compact_image_prompt(self, image_prompt: str, *, view_id: str) -> PromptCompactionResult:
        result = self.prompt_compactor.compact_if_needed(
            image_prompt,
            max_chars=self.prompt_max_chars,
            target_chars=self.prompt_target_chars,
            label=f"image prompt {view_id}",
        )
        if result.was_compacted:
            logger.info(
                "Image prompt for %s compacted from %s to %s characters.",
                view_id,
                result.original_length,
                result.final_length,
        )
        return result


class GMIImageProvider(OpenAIImageProvider):
    def __init__(self, enabled: bool = True, force_enabled: bool = False) -> None:
        ImageProvider.__init__(self)
        self.provider_name = "gmi"
        self.enabled = enabled or force_enabled
        self.base_url = (
            _first_env(
                [
                    "GMI_IMAGE_BASE_URL",
                    "GMI_CLOUD_IMAGE_BASE_URL",
                    "GMICLOUD_IMAGE_BASE_URL",
                    "GMI_BASE_URL",
                ],
                DEFAULT_GMI_IMAGE_BASE_URL,
            )
            or DEFAULT_GMI_IMAGE_BASE_URL
        ).rstrip("/")
        self.api_key = _first_env(["GMI_IMAGE_API_KEY", "GMI_API_KEY", "GMI_CLOUD_API_KEY", "GMICLOUD_API_KEY"])
        self.organization_id = None
        self.project_id = None
        self.model_name = (
            _first_env(["GMI_IMAGE_MODEL", "GMI_CLOUD_IMAGE_MODEL", "GMICLOUD_IMAGE_MODEL", "IMAGE_MODEL"], DEFAULT_GMI_IMAGE_MODEL)
            or DEFAULT_GMI_IMAGE_MODEL
        )
        self.size = _first_env(["GMI_IMAGE_SIZE", "GMI_CLOUD_IMAGE_SIZE", "GMICLOUD_IMAGE_SIZE", "IMAGE_SIZE"], DEFAULT_IMAGE_SIZE) or DEFAULT_IMAGE_SIZE
        self.quality = _first_env(
            ["GMI_IMAGE_QUALITY", "GMI_CLOUD_IMAGE_QUALITY", "GMICLOUD_IMAGE_QUALITY", "IMAGE_QUALITY"],
            DEFAULT_GMI_IMAGE_QUALITY,
        )
        self.output_format = (
            _first_env(["GMI_IMAGE_OUTPUT_FORMAT", "GMI_CLOUD_IMAGE_OUTPUT_FORMAT", "GMICLOUD_IMAGE_OUTPUT_FORMAT", "IMAGE_OUTPUT_FORMAT"], "png")
            or "png"
        )
        self.timeout_seconds = _first_env_float(
            ["GMI_IMAGE_TIMEOUT_SECONDS", "GMI_CLOUD_IMAGE_TIMEOUT_SECONDS", "GMICLOUD_IMAGE_TIMEOUT_SECONDS", "IMAGE_TIMEOUT_SECONDS"],
            DEFAULT_IMAGE_TIMEOUT_SECONDS,
        )
        self.prompt_max_chars = _first_env_int(["GMI_IMAGE_PROMPT_MAX_CHARS", "IMAGE_PROMPT_MAX_CHARS"], OPENAI_IMAGE_PROMPT_MAX_CHARS)
        self.prompt_target_chars = _first_env_int(
            ["GMI_IMAGE_PROMPT_TARGET_CHARS", "IMAGE_PROMPT_TARGET_CHARS"],
            DEFAULT_IMAGE_PROMPT_TARGET_CHARS,
        )
        self.prompt_compactor = PromptCompactionAgent()
        self.allow_no_api_key = _first_env_bool(["GMI_IMAGE_ALLOW_NO_API_KEY", "IMAGE_ALLOW_NO_API_KEY"], default=False)
        self.is_configured = bool(self.enabled and self.base_url and self.model_name and (self.api_key or self.allow_no_api_key))

    def get_debug_config(self) -> Dict[str, Any]:
        reason = None
        if not self.enabled:
            reason = "Image output is disabled."
        elif not self.base_url:
            reason = "GMI image base URL is missing."
        elif not self.model_name:
            reason = "GMI image model is missing."
        elif not self.api_key and not self.allow_no_api_key:
            reason = "GMI image API key is missing."

        return {
            **ImageProvider.get_debug_config(self),
            "base_url": self.base_url,
            "size": self.size,
            "quality": self.quality,
            "output_format": self.output_format,
            "prompt_max_chars": self.prompt_max_chars,
            "prompt_target_chars": self.prompt_target_chars,
            "reason": reason,
        }


class TogetherImageProvider(OpenAIImageProvider):
    def __init__(self, enabled: bool = True, force_enabled: bool = False) -> None:
        ImageProvider.__init__(self)
        self.provider_name = "together"
        self.enabled = enabled or force_enabled
        self.base_url = (
            _first_env(["TOGETHER_IMAGE_BASE_URL", "TOGETHER_BASE_URL"], DEFAULT_TOGETHER_IMAGE_BASE_URL)
            or DEFAULT_TOGETHER_IMAGE_BASE_URL
        ).rstrip("/")
        self.api_key = _first_env(["TOGETHER_IMAGE_API_KEY", "TOGETHER_API_KEY"])
        self.organization_id = None
        self.project_id = None
        self.model_name = (
            _first_env(["TOGETHER_IMAGE_MODEL", "TOGETHER_MODEL", "IMAGE_MODEL"], DEFAULT_TOGETHER_IMAGE_MODEL)
            or DEFAULT_TOGETHER_IMAGE_MODEL
        )
        self.size = _first_env(["TOGETHER_IMAGE_SIZE", "IMAGE_SIZE"], DEFAULT_IMAGE_SIZE) or DEFAULT_IMAGE_SIZE
        default_steps = DEFAULT_TOGETHER_IMAGE_STEPS if _together_model_supports_flux_params(self.model_name) else 0
        self.num_inference_steps = _first_env_int(["TOGETHER_IMAGE_STEPS", "TOGETHER_IMAGE_NUM_INFERENCE_STEPS", "IMAGE_STEPS"], default_steps)
        self.output_format = _first_env(["TOGETHER_IMAGE_OUTPUT_FORMAT", "IMAGE_OUTPUT_FORMAT"], "png") or "png"
        self.timeout_seconds = _first_env_float(["TOGETHER_IMAGE_TIMEOUT_SECONDS", "IMAGE_TIMEOUT_SECONDS"], DEFAULT_IMAGE_TIMEOUT_SECONDS)
        self.prompt_max_chars = _first_env_int(["TOGETHER_IMAGE_PROMPT_MAX_CHARS", "IMAGE_PROMPT_MAX_CHARS"], HUGGINGFACE_IMAGE_PROMPT_MAX_CHARS)
        self.prompt_target_chars = _first_env_int(
            ["TOGETHER_IMAGE_PROMPT_TARGET_CHARS", "IMAGE_PROMPT_TARGET_CHARS"],
            HUGGINGFACE_IMAGE_PROMPT_TARGET_CHARS,
        )
        self.prompt_compactor = PromptCompactionAgent()
        self.allow_no_api_key = _first_env_bool(["TOGETHER_IMAGE_ALLOW_NO_API_KEY", "IMAGE_ALLOW_NO_API_KEY"], default=False)
        self.is_configured = bool(self.enabled and self.base_url and self.model_name and (self.api_key or self.allow_no_api_key))

    def _size_dimensions(self) -> Tuple[Optional[int], Optional[int]]:
        normalized = (self.size or "").strip().lower()
        if "x" not in normalized:
            return None, None
        width_raw, height_raw = normalized.split("x", 1)
        try:
            return int(width_raw), int(height_raw)
        except ValueError:
            return None, None

    def get_debug_config(self) -> Dict[str, Any]:
        reason = None
        if not self.enabled:
            reason = "Image output is disabled."
        elif not self.base_url:
            reason = "Together AI image base URL is missing."
        elif not self.model_name:
            reason = "Together AI image model is missing."
        elif not self.api_key and not self.allow_no_api_key:
            reason = "Together AI image API key is missing."

        return {
            **ImageProvider.get_debug_config(self),
            "base_url": self.base_url,
            "size": self.size,
            "steps": self.num_inference_steps if _together_model_supports_flux_params(self.model_name) else None,
            "output_format": self.output_format,
            "prompt_max_chars": self.prompt_max_chars,
            "prompt_target_chars": self.prompt_target_chars,
            "reason": reason,
        }

    def _generate_image_from_prompt(
        self,
        image_prompt: str,
        *,
        view_id: str,
        label: str,
        reference_view_id: Optional[str],
    ) -> GeneratedImage:
        prompt_result = self._compact_image_prompt(image_prompt, view_id=view_id)
        width, height = self._size_dimensions()
        payload: Dict[str, Any] = {
            "model": self.model_name,
            "prompt": prompt_result.prompt,
        }
        if _together_model_supports_flux_params(self.model_name):
            payload["n"] = 1
            payload["response_format"] = "base64"
            payload["output_format"] = self.output_format
            if width and height:
                payload["width"] = width
                payload["height"] = height
            if self.num_inference_steps:
                payload["steps"] = self.num_inference_steps

        response = self._request_json("images/generations", method="POST", payload=payload)
        item = _first_image_item(response)
        if not item:
            raise RuntimeError("Together AI image response did not include image data.")

        return GeneratedImage(
            data_url=_image_data_url_from_item(item, self.output_format, self.provider_name),
            provider=self.provider_name,
            model=self.model_name,
            size=self.size,
            prompt=prompt_result.prompt,
            output_format=self.output_format,
            view_id=view_id,
            label=label,
            reference_view_id=reference_view_id,
            prompt_original_length=prompt_result.original_length,
            prompt_final_length=prompt_result.final_length,
            prompt_compacted=prompt_result.was_compacted,
            prompt_compaction_strategy=prompt_result.strategy,
        )

    def generate_project_image_sequence(self, user_prompt: str, ir: Any) -> List[GeneratedImage]:
        if not self.is_configured:
            return []
        sequence: List[GeneratedImage] = []
        for item in build_project_image_sequence_prompts(user_prompt, ir):
            if item.get("generation_mode") == "deterministic_svg":
                prompt_result = self._compact_image_prompt(item["prompt"], view_id=item["view_id"])
                sequence.append(
                    build_project_layout_diagram_image(
                        user_prompt,
                        ir,
                        prompt=prompt_result.prompt,
                        reference_view_id="visual_spec",
                        prompt_compaction_result=prompt_result,
                    )
                )
                continue
            sequence.append(
                self._generate_image_from_prompt(
                    item["prompt"],
                    view_id=item["view_id"],
                    label=item["label"],
                    reference_view_id=None,
                )
            )
        return sequence


class HuggingFaceImageProvider(ImageProvider):
    provider_name = "huggingface"

    def __init__(self, enabled: bool = True, force_enabled: bool = False) -> None:
        self.enabled = enabled or force_enabled
        self.api_key = _first_env(["HUGGINGFACE_IMAGE_API_KEY", "HF_IMAGE_TOKEN", "HF_TOKEN", "HUGGINGFACE_API_KEY", "HUGGINGFACE_HUB_TOKEN", "HF_API_TOKEN"])
        self.model_name = _first_env(["HUGGINGFACE_IMAGE_MODEL", "HF_IMAGE_MODEL", "IMAGE_MODEL"], "black-forest-labs/FLUX.1-schnell") or "black-forest-labs/FLUX.1-schnell"
        self.inference_provider = _first_env(["HUGGINGFACE_IMAGE_INFERENCE_PROVIDER", "HF_IMAGE_INFERENCE_PROVIDER", "HUGGINGFACE_INFERENCE_PROVIDER", "HF_INFERENCE_PROVIDER"])
        self.model_revision = _first_env(["HUGGINGFACE_IMAGE_MODEL_REVISION", "HF_IMAGE_MODEL_REVISION", "HUGGINGFACE_MODEL_REVISION", "HF_MODEL_REVISION"])
        self.model_license = _first_env(["HUGGINGFACE_IMAGE_MODEL_LICENSE", "HF_IMAGE_MODEL_LICENSE", "HUGGINGFACE_MODEL_LICENSE", "HF_MODEL_LICENSE"])
        self.gated_models_enabled = _first_env_bool(["HUGGINGFACE_IMAGE_GATED_MODELS_ENABLED", "HF_IMAGE_GATED_MODELS_ENABLED", "HUGGINGFACE_GATED_MODELS_ENABLED", "HF_GATED_MODELS_ENABLED"])
        self.size = _first_env(["HUGGINGFACE_IMAGE_SIZE", "HF_IMAGE_SIZE", "IMAGE_SIZE"], DEFAULT_IMAGE_SIZE) or DEFAULT_IMAGE_SIZE
        self.guidance_scale = _first_env_float(["HUGGINGFACE_IMAGE_GUIDANCE_SCALE", "HF_IMAGE_GUIDANCE_SCALE"], 0.0)
        self.num_inference_steps = _first_env_int(["HUGGINGFACE_IMAGE_STEPS", "HF_IMAGE_STEPS"], 0)
        self.negative_prompt = _first_env(["HUGGINGFACE_IMAGE_NEGATIVE_PROMPT", "HF_IMAGE_NEGATIVE_PROMPT"])
        self.seed = _first_env_int(["HUGGINGFACE_IMAGE_SEED", "HF_IMAGE_SEED"], 0)
        self.output_format = _first_env(["HUGGINGFACE_IMAGE_OUTPUT_FORMAT", "HF_IMAGE_OUTPUT_FORMAT", "IMAGE_OUTPUT_FORMAT"], "png") or "png"
        self.timeout_seconds = _first_env_float(["HUGGINGFACE_IMAGE_TIMEOUT_SECONDS", "HF_IMAGE_TIMEOUT_SECONDS", "IMAGE_TIMEOUT_SECONDS"], DEFAULT_IMAGE_TIMEOUT_SECONDS)
        self.prompt_max_chars = _first_env_int(
            ["HUGGINGFACE_IMAGE_PROMPT_MAX_CHARS", "HF_IMAGE_PROMPT_MAX_CHARS", "IMAGE_PROMPT_MAX_CHARS"],
            HUGGINGFACE_IMAGE_PROMPT_MAX_CHARS,
        )
        self.prompt_target_chars = _first_env_int(
            ["HUGGINGFACE_IMAGE_PROMPT_TARGET_CHARS", "HF_IMAGE_PROMPT_TARGET_CHARS", "IMAGE_PROMPT_TARGET_CHARS"],
            HUGGINGFACE_IMAGE_PROMPT_TARGET_CHARS,
        )
        self.prompt_compactor = PromptCompactionAgent()
        self.is_configured = bool(self.enabled and self.api_key and self.model_name and (self.gated_models_enabled or not self._looks_gated_model()))

    def _looks_gated_model(self) -> bool:
        model = self.model_name.strip().lower()
        return "flux.1-dev" in model or "gated" in model

    def _size_dimensions(self) -> Tuple[Optional[int], Optional[int]]:
        normalized = (self.size or "").strip().lower()
        if "x" not in normalized:
            return None, None
        width_raw, height_raw = normalized.split("x", 1)
        try:
            return int(width_raw), int(height_raw)
        except ValueError:
            return None, None

    def get_debug_config(self) -> Dict[str, Any]:
        reason = None
        if not self.enabled:
            reason = "Image output is disabled."
        elif not self.api_key:
            reason = "Hugging Face image token is missing."
        elif not self.model_name:
            reason = "Hugging Face image model is missing."
        elif self._looks_gated_model() and not self.gated_models_enabled:
            reason = "Hugging Face gated image models are disabled until user access, terms, and license checks are confirmed."

        return {
            **super().get_debug_config(),
            "size": self.size,
            "output_format": self.output_format,
            "inference_provider": self.inference_provider,
            "model_revision": self.model_revision,
            "model_license": self.model_license,
            "gated_models_enabled": self.gated_models_enabled,
            "prompt_max_chars": self.prompt_max_chars,
            "prompt_target_chars": self.prompt_target_chars,
            "reason": reason,
        }

    def _compact_image_prompt(self, image_prompt: str, *, view_id: str) -> PromptCompactionResult:
        return self.prompt_compactor.compact_if_needed(
            image_prompt,
            max_chars=self.prompt_max_chars,
            target_chars=self.prompt_target_chars,
            label=f"huggingface image prompt {view_id}",
        )

    def _client(self) -> Any:
        try:
            from huggingface_hub import InferenceClient
        except ImportError as exc:
            raise RuntimeError("Hugging Face image generation requires huggingface-hub. Install the huggingface extra.") from exc
        kwargs: Dict[str, Any] = {"api_key": self.api_key, "timeout": self.timeout_seconds}
        if self.inference_provider:
            kwargs["provider"] = self.inference_provider
        return InferenceClient(**kwargs)

    def _image_to_data_url(self, image: Any) -> str:
        if isinstance(image, bytes):
            encoded = base64.b64encode(image).decode("ascii")
            return f"data:{_mime_for_output_format(self.output_format)};base64,{encoded}"
        if isinstance(image, str):
            if image.startswith("data:"):
                return image
            return f"data:{_mime_for_output_format(self.output_format)};base64,{image}"
        if hasattr(image, "save"):
            buffer = io.BytesIO()
            pil_format = "JPEG" if self.output_format.lower() in {"jpg", "jpeg"} else self.output_format.upper()
            image.save(buffer, format=pil_format)
            encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
            return f"data:{_mime_for_output_format(self.output_format)};base64,{encoded}"
        raise RuntimeError("Hugging Face image response did not include image bytes.")

    def _generate_image_from_prompt(
        self,
        image_prompt: str,
        *,
        view_id: str,
        label: str,
        reference_view_id: Optional[str],
    ) -> GeneratedImage:
        prompt_result = self._compact_image_prompt(image_prompt, view_id=view_id)
        width, height = self._size_dimensions()
        parameters: Dict[str, Any] = {}
        if width and height:
            parameters["width"] = width
            parameters["height"] = height
        if self.guidance_scale:
            parameters["guidance_scale"] = self.guidance_scale
        if self.num_inference_steps:
            parameters["num_inference_steps"] = self.num_inference_steps
        if self.negative_prompt:
            parameters["negative_prompt"] = self.negative_prompt
        if self.seed:
            parameters["seed"] = self.seed

        logger.info(
            "Requesting Hugging Face image: model=%s provider=%s view=%s size=%s timeout=%s",
            self.model_name,
            self.inference_provider or "auto",
            view_id,
            self.size,
            self.timeout_seconds,
        )
        image = self._client().text_to_image(
            prompt_result.prompt,
            model=self.model_name,
            **parameters,
        )
        logger.info(
            "Hugging Face image response received: model=%s provider=%s view=%s response_type=%s",
            self.model_name,
            self.inference_provider or "auto",
            view_id,
            type(image).__name__,
        )
        return GeneratedImage(
            data_url=self._image_to_data_url(image),
            provider=self.provider_name,
            model=self.model_name,
            size=self.size,
            prompt=prompt_result.prompt,
            output_format=self.output_format,
            view_id=view_id,
            label=label,
            reference_view_id=reference_view_id,
            prompt_original_length=prompt_result.original_length,
            prompt_final_length=prompt_result.final_length,
            prompt_compacted=prompt_result.was_compacted,
            prompt_compaction_strategy=prompt_result.strategy,
            model_revision=self.model_revision,
            inference_provider=self.inference_provider,
            model_license=self.model_license,
        )

    def generate_project_image(self, user_prompt: str, ir: Any) -> Optional[GeneratedImage]:
        if not self.is_configured:
            return None
        image_prompt = build_project_image_prompt(user_prompt, ir)
        return self._generate_image_from_prompt(
            image_prompt,
            view_id="case",
            label="Exterior case render",
            reference_view_id=None,
        )

    def generate_project_image_sequence(self, user_prompt: str, ir: Any) -> List[GeneratedImage]:
        if not self.is_configured:
            return []
        sequence: List[GeneratedImage] = []
        for item in build_project_image_sequence_prompts(user_prompt, ir):
            if item.get("generation_mode") == "deterministic_svg":
                prompt_result = self._compact_image_prompt(item["prompt"], view_id=item["view_id"])
                sequence.append(
                    build_project_layout_diagram_image(
                        user_prompt,
                        ir,
                        prompt=prompt_result.prompt,
                        reference_view_id="visual_spec",
                        prompt_compaction_result=prompt_result,
                    )
                )
                continue
            sequence.append(
                self._generate_image_from_prompt(
                    item["prompt"],
                    view_id=item["view_id"],
                    label=item["label"],
                    reference_view_id=None,
                )
            )
        return sequence


def _image_data_url_from_item(item: Dict[str, Any], output_format: str, provider_name: str) -> str:
    b64_json = item.get("b64_json") or item.get("base64") or item.get("image_base64")
    if isinstance(b64_json, str) and b64_json.strip():
        mime_type = _mime_for_output_format(output_format)
        return f"data:{mime_type};base64,{b64_json.strip()}"

    url = item.get("url")
    if not isinstance(url, str) or not url.strip():
        raise RuntimeError(f"{provider_name} image response did not include b64_json or url.")
    return url.strip()


def _image_bytes_from_data(image_data: str) -> Tuple[bytes, str]:
    image_data = (image_data or "").strip()
    if not image_data:
        raise ValueError("Reference image data is empty.")

    if image_data.startswith(("http://", "https://")):
        request = urllib.request.Request(image_data, headers={"User-Agent": "Blueprint-OSS/1.0"})
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read(), response.headers.get_content_type() or "image/png"

    content_type = "image/png"
    base64_data = image_data
    if "," in image_data:
        header, base64_data = image_data.split(",", 1)
        if header.startswith("data:") and ";base64" in header:
            content_type = header.removeprefix("data:").split(";", 1)[0] or content_type

    return base64.b64decode(base64_data.strip()), content_type


def _first_image_item(response: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    data = response.get("data")
    if isinstance(data, list) and data:
        first = data[0]
        return first if isinstance(first, dict) else None

    output = response.get("output")
    if isinstance(output, list):
        for item in output:
            if isinstance(item, dict) and any(key in item for key in {"b64_json", "base64", "image_base64", "url"}):
                return item
            if isinstance(item, dict):
                nested = item.get("content")
                if isinstance(nested, list):
                    for nested_item in nested:
                        if isinstance(nested_item, dict) and any(
                            key in nested_item for key in {"b64_json", "base64", "image_base64", "url"}
                        ):
                            return nested_item
    return None


def build_project_image_prompt(user_prompt: str, ir: Any) -> str:
    overview = getattr(ir, "overview", None)
    mechanical = getattr(ir, "mechanical", None)
    title = getattr(overview, "title", "Hardware concept")
    description = getattr(overview, "description", user_prompt)
    components = getattr(ir, "components", []) or []
    constraints = getattr(ir, "constraints", []) or []
    fabrication_notes = getattr(ir, "fabrication_notes", []) or []

    component_lines = _limit_list(
        [
            " ".join(
                item
                for item in [
                    getattr(component, "ref_des", ""),
                    getattr(component, "name", ""),
                    f"({getattr(component, 'category', '')})" if getattr(component, "category", "") else "",
                ]
                if item
            )
            for component in components
        ],
        limit=12,
    )

    dimensions = ""
    render_dimensions = getattr(mechanical, "render_dimensions", None)
    if render_dimensions:
        dimensions = (
            f"{getattr(render_dimensions, 'x_mm', '?')}mm wide x "
            f"{getattr(render_dimensions, 'y_mm', '?')}mm deep x "
            f"{getattr(render_dimensions, 'z_mm', '?')}mm tall"
        )

    prompt_parts = [
        "Create a clean realistic product concept render for a safe low-voltage maker electronics build.",
        "Show the assembled physical device, enclosure, visible controls, display openings, ports, and any exposed low-voltage modules that belong in the design.",
        "Do not include text, labels, watermarks, logos, hands, people, wiring diagrams, schematic symbols, high-voltage equipment, medical devices, or weapons.",
        "Use a neutral studio background, believable materials, and a three-quarter product view.",
        f"Project title: {_truncate(title, 120)}",
        f"Project description: {_truncate(description, 300)}",
        f"User prompt: {_truncate(user_prompt, 220)}",
    ]

    if component_lines:
        prompt_parts.append("Main parts: " + "; ".join(component_lines))
    if constraints:
        prompt_parts.append("Design constraints: " + "; ".join(_limit_list(constraints, 8)))
    if fabrication_notes:
        prompt_parts.append("Fabrication notes: " + "; ".join(_limit_list(fabrication_notes, 5)))
    if dimensions:
        prompt_parts.append(f"Approximate device envelope: {dimensions}.")

    return "\n".join(prompt_parts)


def _attr_or_key(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _number_or_none(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _vector_dict(value: Any) -> Optional[Dict[str, float]]:
    if not value:
        return None
    x_mm = _number_or_none(_attr_or_key(value, "x_mm"))
    y_mm = _number_or_none(_attr_or_key(value, "y_mm"))
    z_mm = _number_or_none(_attr_or_key(value, "z_mm"))
    if x_mm is None or y_mm is None or z_mm is None:
        return None
    return {"x_mm": x_mm, "y_mm": y_mm, "z_mm": z_mm}


def _dimension_text(dimensions: Optional[Dict[str, float]], *, label: str) -> str:
    if not dimensions:
        return f"{label}: unspecified; do not invent numeric dimension callouts."
    return (
        f"{label}: {dimensions['x_mm']} mm W x "
        f"{dimensions['y_mm']} mm D x {dimensions['z_mm']} mm H"
    )


def _internal_dimensions(external: Optional[Dict[str, float]]) -> Optional[Dict[str, float]]:
    if not external:
        return None
    return {
        "x_mm": round(max(1.0, external["x_mm"] - 4.0), 2),
        "y_mm": round(max(1.0, external["y_mm"] - 4.0), 2),
        "z_mm": round(max(1.0, external["z_mm"] - 8.0), 2),
    }


def _component_records(ir: Any, limit: int = 18) -> List[Dict[str, Any]]:
    components = getattr(ir, "components", []) or []
    records = []
    for component in components[:limit]:
        records.append(
            {
                "ref_des": _attr_or_key(component, "ref_des", ""),
                "name": _attr_or_key(component, "name", ""),
                "part_number": _attr_or_key(component, "part_number", ""),
                "category": _attr_or_key(component, "category", ""),
                "quantity": _attr_or_key(component, "quantity", 1),
            }
        )
    return records


def _component_placement_records(ir: Any, limit: int = 24) -> List[Dict[str, Any]]:
    mechanical = getattr(ir, "mechanical", None)
    placements = getattr(mechanical, "component_placements", []) or []
    records = []
    for placement in placements[:limit]:
        records.append(
            {
                "ref_des": _attr_or_key(placement, "ref_des", ""),
                "label": _attr_or_key(placement, "label"),
                "category": _attr_or_key(placement, "category"),
                "layer": _attr_or_key(placement, "layer"),
                "position_mm": _vector_dict(_attr_or_key(placement, "position")),
                "size_mm": _vector_dict(_attr_or_key(placement, "size")),
                "mounting_face": _attr_or_key(placement, "mounting_face"),
                "notes": _truncate(_attr_or_key(placement, "notes", ""), 180),
            }
        )
    return records


def _component_record_text(component: Dict[str, Any]) -> str:
    return " ".join(
        str(component.get(key, ""))
        for key in ("ref_des", "name", "part_number", "category")
        if component.get(key)
    ).lower()


def _visual_role(component: Dict[str, Any]) -> str:
    text = _component_record_text(component)
    category = str(component.get("category") or "").lower()
    if any(token in text for token in ["oled", "display", "screen", "lcd", "tft"]):
        return "display"
    if any(token in text for token in ["knob", "potentiometer", "encoder", "button", "switch", "joystick"]):
        return "user_control"
    if any(token in text for token in ["usb", "dc jack", "barrel jack", "power input", "connector"]):
        return "external_port"
    if "sensor" in category or any(token in text for token in ["temperature", "temp", "humidity", "pressure", "sensor"]):
        return "sensor"
    if any(token in text for token in ["mosfet", "driver", "relay", "motor driver"]):
        return "driver_stage"
    if any(token in text for token in ["fan", "blower"]):
        return "fan_actuator"
    if "microcontroller" in category or any(token in text for token in ["raspberry pi", "pico", "esp32", "arduino", "mcu"]):
        return "controller_board"
    if any(token in text for token in ["pcb", "perf", "proto", "breadboard"]):
        return "carrier_board"
    if any(token in text for token in ["standoff", "insert", "screw", "fastener"]):
        return "mounting_hardware"
    return category or "electrical_component"


def _mounting_zone(component: Dict[str, Any], placement: Optional[Dict[str, Any]]) -> str:
    text = _component_record_text(component)
    role = _visual_role(component)
    explicit_face = ""
    if placement:
        explicit_face = str(placement.get("mounting_face") or "").strip().lower().replace("-", "_").replace(" ", "_")

    if role in {"display", "user_control"}:
        return "top_lid_operator_panel"
    if role == "fan_actuator":
        return "right_wall_exhaust"
    if role == "external_port" or any(token in text for token in ["usb", "5v dc", "dc in", "power input"]):
        return "front_wall_edge"
    if role == "sensor":
        return "air_inlet_zone_away_from_heat_sources"
    if explicit_face in {"lid", "top", "cover", "top_panel", "operator_panel"}:
        return "top_lid_operator_panel"
    if explicit_face in {"floor", "bottom", "base", "internal"}:
        return "bottom_shell_floor"
    if explicit_face in {"front", "front_wall"}:
        return "front_wall_edge"
    if explicit_face in {"back", "rear", "back_wall", "rear_wall"}:
        return "rear_wall"
    if explicit_face in {"left", "left_wall"}:
        return "left_wall"
    if explicit_face in {"right", "right_wall"}:
        return "right_wall"
    if role in {"controller_board", "driver_stage", "carrier_board"}:
        return "bottom_shell_floor"
    return "bottom_shell_floor"


def _component_subsystem(component: Dict[str, Any], role: Optional[str] = None) -> str:
    role = role or _visual_role(component)
    text = _component_record_text(component)
    category = str(component.get("category") or "").lower()
    if role in {"display", "user_control"}:
        return "ui"
    if role == "controller_board":
        return "control"
    if role in {"driver_stage", "external_port"} or category == "power" or any(
        token in text for token in ["regulator", "charger", "fuse", "polyfuse", "mosfet", "terminal", "power"]
    ):
        return "power_driver"
    if role == "sensor":
        return "sensing"
    if role == "fan_actuator" or any(token in text for token in ["fan", "blower", "air", "vent", "filter"]):
        return "airflow"
    if role in {"carrier_board", "mounting_hardware"} or category in {"mechanical", "3d print"}:
        return "mechanical"
    return "support"


def _orientation_metadata(component: Dict[str, Any], role: str, mounting_zone: str) -> Dict[str, str]:
    if mounting_zone == "top_lid_operator_panel":
        return {
            "mounted_on": "top_lid_operator_panel",
            "facing_normal": "+Z",
            "visible_side": "front/operator side",
            "service_side": "underside visible when lid is removed",
            "view_preference": "top_down_lid_window",
            "render_rule": "keep this component attached to the lid plane; do not rotate it to face the camera in bottom-shell views",
        }
    if mounting_zone == "front_wall_edge":
        return {
            "mounted_on": "front_wall",
            "facing_normal": "-Y",
            "visible_side": "front edge",
            "service_side": "inside wall wiring side",
            "view_preference": "top_down_edge_or_front_inset",
            "render_rule": "keep this component on the front wall edge; do not lay it flat on the PCB floor",
        }
    if mounting_zone == "right_wall_exhaust":
        return {
            "mounted_on": "right_wall",
            "facing_normal": "+X",
            "visible_side": "right exterior wall",
            "service_side": "inside wall wiring side",
            "view_preference": "top_down_edge_or_side_inset",
            "render_rule": "keep fan/airflow hardware on the right wall; do not rotate the fan to face upward unless shown as an inset",
        }
    if mounting_zone == "left_wall":
        return {
            "mounted_on": "left_wall",
            "facing_normal": "-X",
            "visible_side": "left exterior wall",
            "service_side": "inside wall wiring side",
            "view_preference": "top_down_edge_or_side_inset",
            "render_rule": "keep this component on the left wall edge; do not lay it flat on the PCB floor",
        }
    if mounting_zone in {"rear_wall", "back_wall"}:
        return {
            "mounted_on": "rear_wall",
            "facing_normal": "+Y",
            "visible_side": "rear exterior wall",
            "service_side": "inside wall wiring side",
            "view_preference": "top_down_edge_or_rear_inset",
            "render_rule": "keep this component on the rear wall edge; do not lay it flat on the PCB floor",
        }
    if mounting_zone == "air_inlet_zone_away_from_heat_sources":
        return {
            "mounted_on": "intake_or_sensor_zone",
            "facing_normal": "air_path",
            "visible_side": "airflow exposure side",
            "service_side": "sensor board wiring side",
            "view_preference": "top_down_transparent_air_path",
            "render_rule": "keep sensors in the airflow/intake zone and away from hot driver components",
        }
    if role == "mounting_hardware":
        return {
            "mounted_on": "enclosure_structure",
            "facing_normal": "+Z",
            "visible_side": "fastener head or insert opening",
            "service_side": "structural interface",
            "view_preference": "top_down_structural_reference",
            "render_rule": "show as structural reference hardware, not as an electrical module",
        }
    return {
        "mounted_on": "bottom_shell_floor",
        "facing_normal": "+Z",
        "visible_side": "component top side",
        "service_side": "solder or wiring underside",
        "view_preference": "top_down_floor_window",
        "render_rule": "prefer top-down visibility; keep this component on the bottom-shell floor plane and do not tilt it toward the camera",
    }


def _net_records(ir: Any, limit: int = 18) -> List[Dict[str, Any]]:
    nets = getattr(ir, "nets", []) or []
    records = []
    for net in nets[:limit]:
        pins = []
        for pin in (_attr_or_key(net, "pins", []) or [])[:8]:
            pins.append(
                {
                    "ref_des": _attr_or_key(pin, "ref_des", ""),
                    "pin_id": _attr_or_key(pin, "pin_id", ""),
                }
            )
        records.append(
            {
                "net_id": _attr_or_key(net, "net_id", ""),
                "name": _attr_or_key(net, "name", ""),
                "net_type": _attr_or_key(net, "net_type", ""),
                "voltage": _attr_or_key(net, "voltage", None),
                "pins": pins,
            }
        )
    return records


def _assembly_component_records(
    components: List[Dict[str, Any]],
    placements: List[Dict[str, Any]],
    limit: int = 24,
) -> List[Dict[str, Any]]:
    placements_by_ref = {
        str(placement.get("ref_des") or ""): placement
        for placement in placements
        if placement.get("ref_des")
    }
    records = []
    for component in components[:limit]:
        ref_des = str(component.get("ref_des") or "")
        placement = placements_by_ref.get(ref_des)
        role = _visual_role(component)
        mounting_zone = _mounting_zone(component, placement)
        orientation = _orientation_metadata(component, role, mounting_zone)
        records.append(
            {
                "ref_des": ref_des,
                "name": component.get("name", ""),
                "visual_role": role,
                "subsystem": _component_subsystem(component, role),
                "mounting_zone": mounting_zone,
                "mounted_on": orientation["mounted_on"],
                "facing_normal": orientation["facing_normal"],
                "visible_side": orientation["visible_side"],
                "service_side": orientation["service_side"],
                "view_preference": orientation["view_preference"],
                "render_rule": orientation["render_rule"],
                "position_mm": (placement or {}).get("position_mm"),
                "size_mm": (placement or {}).get("size_mm"),
                "mounting_face_source": (placement or {}).get("mounting_face"),
            }
        )
    return records


def _orientation_landmarks(assembly_components: List[Dict[str, Any]]) -> List[str]:
    roles = {str(component.get("visual_role") or "") for component in assembly_components}
    zones = {str(component.get("mounting_zone") or "") for component in assembly_components}
    landmarks = [
        "Coordinate frame is fixed for every view: X is left/right width, Y is front/back depth, Z is bottom/top height.",
        "In top-down diagrams, the front edge is the lower edge of the page and the rear edge is the upper edge.",
        "Do not mirror, rotate, or swap left/right/front/back between images.",
        "The enclosure bottom shell, lid, ports, side walls, and internal electronics are separate parts with separate visibility states.",
    ]
    if "front_wall_edge" in zones:
        landmarks.append("Front wall landmark: external power/USB/input ports stay on the same front edge in all views.")
    if "right_wall_exhaust" in zones or "fan_actuator" in roles:
        landmarks.append("Right wall landmark: fan/exhaust stays on the same right-side wall and airflow points outward.")
    if "top_lid_operator_panel" in zones:
        landmarks.append("Top/lid landmark: display, knob, buttons, and switches stay attached to the lid/operator panel.")
    if "sensor" in roles:
        landmarks.append("Sensor landmark: air/ambient sensors stay near intake/venting and away from fan exhaust or hot driver stages.")
    return landmarks


def _control_loop_visual_requirements(user_prompt: str, ir: Any, nets: List[Dict[str, Any]]) -> List[str]:
    overview = getattr(ir, "overview", None)
    requirements = getattr(ir, "requirements", None)
    haystack_parts = [
        user_prompt,
        getattr(overview, "title", ""),
        getattr(overview, "description", ""),
        " ".join(getattr(requirements, "requirements", []) or []),
        " ".join(getattr(ir, "constraints", []) or []),
        " ".join(net.get("name", "") for net in nets),
        " ".join(net.get("net_type", "") for net in nets),
    ]
    haystack = " ".join(haystack_parts).lower()
    if not any(token in haystack for token in ["closed-loop", "closed loop", "feedback", "pid", "pwm", "setpoint"]):
        return []
    return [
        "Closed-loop visuals must separate the measured feedback path from the control output path.",
        "Show the measured variable sensor or feedback signal returning to the controller when present in the IR.",
        "Show the controller output path to the actuator or driver stage, such as PWM to a fan or motor driver, when present in the IR.",
        "Do not imply closed-loop speed control unless a feedback sensor, tach signal, or measured output path is visible or explicitly labeled from the spec.",
    ]


def _net_names_matching(nets: List[Dict[str, Any]], tokens: List[str], limit: int = 6) -> List[str]:
    matches: List[str] = []
    for net in nets:
        text = f"{net.get('net_id', '')} {net.get('name', '')} {net.get('net_type', '')}".lower()
        if any(token in text for token in tokens):
            label = " ".join(str(net.get(key) or "") for key in ("net_id", "name", "net_type")).strip()
            if label:
                matches.append(_truncate(label, 90))
        if len(matches) >= limit:
            break
    return matches


def _contract_for_subsystem(
    subsystem: str,
    components: List[Dict[str, Any]],
    nets: List[Dict[str, Any]],
) -> Dict[str, Any]:
    component_refs = [str(component.get("ref_des") or "") for component in components if component.get("ref_des")]
    mounted_on = sorted({str(component.get("mounted_on") or "") for component in components if component.get("mounted_on")})
    facing_normals = sorted({str(component.get("facing_normal") or "") for component in components if component.get("facing_normal")})
    role_text = " ".join(str(component.get("visual_role") or "") for component in components).lower()

    contracts: Dict[str, Dict[str, Any]] = {
        "ui": {
            "purpose": "Expose human-readable status and user setpoint/control inputs without changing internal component placement.",
            "inputs": ["user action", "status data from controller"],
            "outputs": ["setpoint/control input to controller", "displayed status to user"],
            "physical_interfaces": ["top lid/operator panel cutouts", "lid underside wiring/service loop", "display/control mounting features"],
            "placement_constraints": [
                "UI components stay on the lid/operator panel plane.",
                "Display apertures and knob/button shafts align to lid cutouts.",
                "Leave a service loop so the lid can be opened without stressing wiring.",
            ],
            "failure_modes": ["misaligned lid cutouts", "lid wiring blocks closure", "controls duplicated on PCB floor"],
            "verification_checks": [
                "UI appears in a lid/UI subsystem window, not flattened into the PCB floor.",
                "Controls keep facing_normal +Z unless an underside/service inset is explicitly shown.",
            ],
        },
        "control": {
            "purpose": "Run firmware/control logic and coordinate sensor readings, user inputs, display state, and actuator commands.",
            "inputs": ["sensor measurements", "user setpoint/control input", "feedback nets when present"],
            "outputs": ["display/status data", "driver enable/PWM/control nets"],
            "physical_interfaces": ["bottom-shell standoffs", "programming/power access", "signal harness to lid, sensors, and drivers"],
            "placement_constraints": [
                "Controller stays on the bottom-shell floor plane unless explicitly specified otherwise.",
                "Route signal wiring without crossing high-current driver paths unnecessarily.",
                "Keep access to USB/programming connector if the component has one.",
            ],
            "failure_modes": ["controller hidden under lid geometry", "signal paths omitted", "board rotated to face camera instead of +Z"],
            "verification_checks": [
                "Controller is visible in the assembly reference or control subsystem window.",
                "Control outputs and feedback inputs are represented when supported by nets.",
            ],
        },
        "power_driver": {
            "purpose": "Accept low-voltage input, protect/regulate power, and drive actuators from controller outputs.",
            "inputs": ["external low-voltage power", "controller command/PWM/enable nets"],
            "outputs": ["regulated rails", "switched actuator power", "driver status/feedback when present"],
            "physical_interfaces": ["front/edge power connector", "bottom-shell driver board area", "actuator terminal/wiring path"],
            "placement_constraints": [
                "Power ports stay on their wall/edge plane.",
                "Driver components stay clear of heat-sensitive sensors.",
                "High-current wiring should be short and mechanically restrained.",
            ],
            "failure_modes": ["power connector drawn on wrong side", "driver merged with fan", "hot driver placed near ambient sensor"],
            "verification_checks": [
                "Power/driver path is distinct from sensing and UI subsystems.",
                "Port facing normals and edge placement are preserved.",
            ],
        },
        "sensing": {
            "purpose": "Measure the controlled or observed variable without being corrupted by heat, airflow shortcuts, or enclosure geometry.",
            "inputs": ["ambient/process condition", "power and signal bus from controller"],
            "outputs": ["sensor measurement/feedback signal to controller"],
            "physical_interfaces": ["intake/vent exposure", "sensor board mount", "signal harness to controller"],
            "placement_constraints": [
                "Sensors stay exposed to the intended medium or airflow path.",
                "Keep ambient sensors upstream of fan exhaust and away from heat-generating drivers.",
                "Do not bury sensors under an opaque lid or PCB.",
            ],
            "failure_modes": ["sensor placed near exhaust/hot driver", "air path not visible", "feedback sensor missing in closed-loop design"],
            "verification_checks": [
                "Sensor has a visible exposure/air path when relevant.",
                "Feedback path to controller is represented when closed-loop behavior is claimed.",
            ],
        },
        "airflow": {
            "purpose": "Move air through the enclosure or process path in the intended direction.",
            "inputs": ["driver power/control", "intake air path"],
            "outputs": ["exhaust airflow", "tach/feedback signal when present"],
            "physical_interfaces": ["fan wall cutout", "intake/exhaust vents", "filter/duct/grille interfaces"],
            "placement_constraints": [
                "Fan remains on the specified wall plane and points outward for exhaust unless the spec says otherwise.",
                "Intake and exhaust paths must not be blocked by PCB, wiring, or lid features.",
                "Fan orientation should preserve facing_normal instead of being rotated upward for the camera.",
            ],
            "failure_modes": ["fan shown flat on PCB", "airflow direction ambiguous", "vents missing or blocked"],
            "verification_checks": [
                "Fan/air path appears in airflow or wall subsystem window.",
                "Airflow direction and relevant feedback/tach path are visible when supported.",
            ],
        },
        "mechanical": {
            "purpose": "Hold the enclosure, standoffs, panels, hardware, and service access relationships together.",
            "inputs": ["component envelopes", "mounting/clearance needs", "assembly/service requirements"],
            "outputs": ["stable enclosure and mounting structure"],
            "physical_interfaces": ["bottom shell", "lid", "side walls", "standoffs", "fasteners", "cutouts"],
            "placement_constraints": [
                "Do not fuse lid, shell, PCB, and internals into one surface.",
                "Keep service states distinct: closed, transparent inspection, lid open/removed, subsystem layout.",
                "Show mounting hardware as structure rather than as electrical parts.",
            ],
            "failure_modes": ["case surface blended with internals", "lid controls duplicated on bottom shell", "mounting hardware mistaken for circuit modules"],
            "verification_checks": [
                "Lid, bottom shell, walls, and PCB are visually distinct.",
                "Transparent/ghosted views preserve enclosure orientation and component mounting planes.",
            ],
        },
        "support": {
            "purpose": "Provide secondary electrical or mechanical support functions not captured by primary subsystems.",
            "inputs": ["power/signal connections as listed in the IR"],
            "outputs": ["support function to primary subsystems"],
            "physical_interfaces": ["local PCB/wire harness/mounting feature"],
            "placement_constraints": ["Keep support parts near the subsystem they support when possible."],
            "failure_modes": ["unexplained floating component", "support part duplicated across windows"],
            "verification_checks": ["Support components appear once and remain tied to a nearby parent subsystem."],
        },
    }

    contract = dict(contracts.get(subsystem, contracts["support"]))
    contract["component_refs"] = component_refs
    contract["mounted_on"] = mounted_on
    contract["facing_normals"] = facing_normals
    if subsystem in {"control", "power_driver", "airflow"} or "pwm" in role_text:
        contract["relevant_nets"] = _net_names_matching(nets, ["pwm", "enable", "control", "fan", "driver", "tach"])
    elif subsystem == "sensing":
        contract["relevant_nets"] = _net_names_matching(nets, ["sensor", "feedback", "tach", "i2c", "spi", "analog", "adc"])
    elif subsystem == "ui":
        contract["relevant_nets"] = _net_names_matching(nets, ["display", "button", "encoder", "set", "i2c", "spi", "analog"])
    else:
        contract["relevant_nets"] = _net_names_matching(nets, ["power", "ground", "gnd", "vcc", "5v", "3v3"])
    contract["assembly_states"] = [
        "closed exterior",
        "transparent top-down inspection",
        "service access with relevant panel or shell separated",
    ]
    return contract


def _subsystem_records(assembly_components: List[Dict[str, Any]], nets: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    nets = nets or []
    subsystem_labels = {
        "ui": "UI and human interface",
        "control": "Controller and logic",
        "power_driver": "Power input and driver stage",
        "sensing": "Sensors and feedback",
        "airflow": "Airflow and actuator path",
        "mechanical": "Mechanical structure",
        "support": "Support electronics",
    }
    order = ["ui", "control", "power_driver", "sensing", "airflow", "mechanical", "support"]
    grouped: Dict[str, List[Dict[str, Any]]] = {key: [] for key in order}
    for component in assembly_components:
        subsystem = str(component.get("subsystem") or "support")
        grouped.setdefault(subsystem, []).append(component)

    records: List[Dict[str, Any]] = []
    for subsystem in [*order, *sorted(key for key in grouped if key not in order)]:
        components = grouped.get(subsystem) or []
        if not components:
            continue
        mounting_zones = sorted({str(component.get("mounting_zone") or "") for component in components if component.get("mounting_zone")})
        facing_normals = sorted({str(component.get("facing_normal") or "") for component in components if component.get("facing_normal")})
        records.append(
            {
                "id": subsystem,
                "label": subsystem_labels.get(subsystem, subsystem.replace("_", " ").title()),
                "component_refs": [component.get("ref_des") for component in components if component.get("ref_des")],
                "mounting_zones": mounting_zones,
                "facing_normals": facing_normals,
                "contract": _contract_for_subsystem(subsystem, components, nets),
                "view_preference": "top_down_transparent_subsystem_window",
                "layout_rule": "draw this subsystem in its own physical layout window; preserve each component's mounted_on and facing_normal metadata",
            }
        )
    return records


def _refs_for_subsystem(assembly_components: List[Dict[str, Any]], subsystem: str) -> List[str]:
    return [
        str(component.get("ref_des") or "")
        for component in assembly_components
        if component.get("subsystem") == subsystem and component.get("ref_des")
    ]


def _physical_dependency_graph(assembly_components: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    edges: List[Dict[str, Any]] = []
    subsystem_edges = [
        ("ui", "control", "user setpoint/status interface", "UI harness must bridge lid plane to controller without forcing components onto the wrong plane."),
        ("sensing", "control", "measurement/feedback interface", "Sensor placement must expose the measured variable and route signal wiring back to controller."),
        ("control", "power_driver", "command/PWM/enable interface", "Driver command path must remain visually distinct from high-current wiring."),
        ("power_driver", "airflow", "actuator power interface", "Driver output should route to fan/actuator without blocking airflow or service access."),
        ("airflow", "sensing", "process/air path relationship", "Airflow path should not corrupt sensor readings unless that is the intended feedback measurement."),
        ("mechanical", "ui", "panel/cutout support", "Lid cutouts and UI components must align."),
        ("mechanical", "control", "standoff/support", "PCB/controller must be mounted to bottom shell or carrier structure."),
        ("mechanical", "airflow", "wall cutout/support", "Fan, vents, and duct features must align to side-wall openings."),
    ]
    present = {str(component.get("subsystem") or "") for component in assembly_components}
    for source, target, interface, check in subsystem_edges:
        if source in present and target in present:
            edges.append(
                {
                    "source_subsystem": source,
                    "target_subsystem": target,
                    "interface": interface,
                    "design_check": check,
                    "source_refs": _refs_for_subsystem(assembly_components, source),
                    "target_refs": _refs_for_subsystem(assembly_components, target),
                }
            )

    for component in assembly_components:
        ref_des = component.get("ref_des")
        if not ref_des:
            continue
        edges.append(
            {
                "source_subsystem": "mechanical",
                "target_ref_des": ref_des,
                "interface": f"mounts {ref_des} on {component.get('mounted_on') or component.get('mounting_zone')}",
                "design_check": component.get("render_rule") or "preserve component mounting plane and orientation",
            }
        )
    return edges[:28]


def _controlled_variables_from_text(text: str) -> List[str]:
    candidates = [
        ("temperature", ["temp", "thermal", "heater", "cooling"]),
        ("humidity", ["humidity", "moisture", "dry"]),
        ("airflow", ["airflow", "air flow", "fan", "blower", "wind"]),
        ("fan speed", ["rpm", "tach", "fan speed"]),
        ("pressure", ["pressure", "vacuum"]),
        ("light level", ["light", "lux"]),
        ("voltage/current", ["current", "battery", "discharge", "pack voltage"]),
        ("position", ["servo", "position", "linear actuator"]),
    ]
    found = [label for label, tokens in candidates if any(token in text for token in tokens)]
    return found or ["project state"]


def _behavior_control_model(
    user_prompt: str,
    assembly_components: List[Dict[str, Any]],
    nets: List[Dict[str, Any]],
) -> Dict[str, Any]:
    overview_text = " ".join(
        [
            user_prompt,
            " ".join(str(component.get("name") or "") for component in assembly_components),
            " ".join(str(net.get("name") or "") for net in nets),
            " ".join(str(net.get("net_type") or "") for net in nets),
        ]
    ).lower()
    sensors = [component for component in assembly_components if component.get("subsystem") == "sensing"]
    ui = [component for component in assembly_components if component.get("subsystem") == "ui"]
    controllers = [component for component in assembly_components if component.get("subsystem") == "control"]
    drivers = [component for component in assembly_components if component.get("subsystem") == "power_driver"]
    actuators = [component for component in assembly_components if component.get("subsystem") == "airflow"]
    feedback_nets = _net_names_matching(nets, ["feedback", "tach", "sensor", "adc", "analog", "i2c", "spi"], limit=8)
    output_nets = _net_names_matching(nets, ["pwm", "enable", "control", "driver", "fan", "motor", "relay"], limit=8)
    is_closed_loop = any(token in overview_text for token in ["closed-loop", "closed loop", "feedback", "pid", "tach", "setpoint"])
    return {
        "control_model_type": "closed_loop" if is_closed_loop else "open_loop_or_monitoring",
        "controlled_variables": _controlled_variables_from_text(overview_text),
        "setpoint_sources": [component.get("ref_des") for component in ui if component.get("ref_des")],
        "measurement_sources": [component.get("ref_des") for component in sensors if component.get("ref_des")],
        "controller_refs": [component.get("ref_des") for component in controllers if component.get("ref_des")],
        "driver_refs": [component.get("ref_des") for component in drivers if component.get("ref_des")],
        "actuator_refs": [component.get("ref_des") for component in actuators if component.get("ref_des")],
        "feedback_nets": feedback_nets,
        "control_output_nets": output_nets,
        "visual_requirements": [
            "Show the measured variable source, controller, driver/output path, and actuator as separate roles when present.",
            "If closed-loop behavior is claimed, show a feedback path returning to the controller or mark feedback as missing.",
            "Keep behavior arrows separate from physical mounting planes so the image does not relocate components to simplify the loop.",
        ],
        "missing_feedback_warning": bool(is_closed_loop and not feedback_nets and not sensors),
    }


def _assembly_state_records() -> List[Dict[str, Any]]:
    return [
        {
            "id": "closed_exterior",
            "purpose": "Product-like exterior validation.",
            "visible": ["opaque exterior enclosure", "external controls", "ports", "vents", "fasteners"],
            "hidden": ["internal boards and wiring"],
            "verification_checks": ["dimensions shown from spec", "no internals visible through opaque shell"],
        },
        {
            "id": "transparent_top_down_inspection",
            "purpose": "Check physical placement without rotating components toward the camera.",
            "visible": ["ghosted enclosure", "true component mounting planes", "subsystem grouping cues"],
            "hidden": ["opaque lid covering internals", "camera-facing fake rotations"],
            "verification_checks": ["front/right orientation preserved", "mounted_on and facing_normal respected"],
        },
        {
            "id": "service_access",
            "purpose": "Confirm assembly and maintenance access.",
            "visible": ["lid underside", "bottom-shell floor", "wall-service wiring side", "fasteners/standoffs"],
            "hidden": ["fused shell/lid/PCB geometry"],
            "verification_checks": ["lid wiring service loop", "ports/fans accessible from correct wall"],
        },
    ]


def _design_assembly_model(
    user_prompt: str,
    components: List[Dict[str, Any]],
    placements: List[Dict[str, Any]],
    nets: List[Dict[str, Any]],
    external_dimensions: Optional[Dict[str, float]],
    internal_dimensions: Optional[Dict[str, float]],
) -> Dict[str, Any]:
    assembly_components = _assembly_component_records(components, placements)
    subsystem_decomposition = _subsystem_records(assembly_components, nets)
    dependency_graph = _physical_dependency_graph(assembly_components)
    behavior_control = _behavior_control_model(user_prompt, assembly_components, nets)
    return {
        "modeling_method": "single canonical assembly with design intent, subsystem contracts, and derived view states",
        "coordinate_frame": {
            "origin": "center of enclosure envelope",
            "x_axis": "width, left negative to right positive",
            "y_axis": "depth, front negative to rear positive",
            "z_axis": "height, bottom negative to top positive",
            "diagram_orientation": "top-down +Z view with the front edge at the bottom of the page",
        },
        "dimensions_mm": {
            "external": external_dimensions,
            "internal_usable": internal_dimensions,
        },
        "assembly_parts": [
            "bottom shell or base tub",
            "top lid/operator panel",
            "internal PCB or carrier board",
            "panel-mounted controls and display",
            "side-wall ports, vents, and fan openings",
            "mounting hardware and wire harnesses",
        ],
        "component_mounting_zones": assembly_components,
        "subsystem_decomposition": subsystem_decomposition,
        "physical_dependency_graph": dependency_graph,
        "behavior_control_model": behavior_control,
        "assembly_states": _assembly_state_records(),
        "orientation_landmarks": _orientation_landmarks(assembly_components),
        "derived_view_states": {
            "case": {
                "camera": "three-quarter exterior product render",
                "visible": ["bottom shell exterior", "top lid exterior", "external controls", "ports", "vents", "fasteners"],
                "hidden": ["internal electronics", "internal wiring", "bottom-shell floor components"],
                "rule": "closed assembled product only; do not reveal internals.",
            },
            "inside": {
                "camera": "top-down or near top-down transparent assembly render",
                "visible": [
                    "transparent or ghosted enclosure shell",
                    "true component mounting planes",
                    "bottom-shell floor electronics facing +Z",
                    "lid-mounted UI as lid plane or ghosted lid overlay",
                    "wall-mounted ports, fan, vents, and sensors on their side-wall planes",
                    "subsystem grouping cues",
                ],
                "hidden": ["opaque exterior top surface covering the internals", "camera-facing rotated electronics"],
                "rule": "prefer top-down transparent views; keep every component on its mounted_on plane and facing_normal.",
            },
        },
        "continuity_checks": [
            "Every view is the same assembly, not a redesigned device.",
            "Only camera angle and part visibility may change between stages.",
            "Keep all ports, fan openings, vents, controls, display, mounting holes, and PCB positions on their assigned sides.",
            "Do not duplicate components across lid and bottom shell unless the spec lists multiple instances.",
            "Do not draw internals underneath an opaque lid surface.",
            "Do not rotate components to face the camera; preserve facing_normal unless an inset explicitly shows the service side.",
        ],
    }


def _cad_source_records(ir: Any, limit: int = 8) -> List[Dict[str, Any]]:
    mechanical = getattr(ir, "mechanical", None)
    cad_sources = getattr(mechanical, "cad_sources", []) or []
    records = []
    for source in cad_sources[:limit]:
        records.append(
            {
                "name": _attr_or_key(source, "name", ""),
                "source_type": _attr_or_key(source, "source_type", ""),
                "url": _attr_or_key(source, "url", ""),
                "file_formats": _attr_or_key(source, "file_formats", []) or [],
                "license": _attr_or_key(source, "license"),
                "notes": _truncate(_attr_or_key(source, "notes", ""), 180),
            }
        )
    return records


def build_project_visual_spec(user_prompt: str, ir: Any) -> Dict[str, Any]:
    overview = getattr(ir, "overview", None)
    mechanical = getattr(ir, "mechanical", None)
    metadata = getattr(ir, "assembly_metadata", None) or {}
    external_dimensions = _vector_dict(getattr(mechanical, "render_dimensions", None))
    if not external_dimensions and isinstance(metadata, dict):
        external_dimensions = _vector_dict(metadata.get("render_dimensions"))
    internal_dimensions = _internal_dimensions(external_dimensions)
    components = _component_records(ir)
    placements = _component_placement_records(ir)
    nets = _net_records(ir)
    assembly_model = _design_assembly_model(user_prompt, components, placements, nets, external_dimensions, internal_dimensions)
    allowed_labels = sorted(
        {
            label
            for component in components
            for label in (component.get("ref_des"), component.get("name"), component.get("part_number"))
            if label
        }.union(
            {
                label
                for net in nets
                for label in (net.get("net_id"), net.get("name"), net.get("net_type"))
                if label
            }
        )
    )
    return {
        "spec_version": "0.4",
        "title": getattr(overview, "title", "Hardware concept"),
        "description": getattr(overview, "description", user_prompt),
        "source_prompt": user_prompt,
        "external_dimensions_mm": external_dimensions,
        "internal_usable_dimensions_mm": internal_dimensions,
        "external_dimensions_text": _dimension_text(external_dimensions, label="External dimensions"),
        "internal_dimensions_text": _dimension_text(internal_dimensions, label="Internal usable dimensions"),
        "enclosure_type": getattr(mechanical, "enclosure_type", "custom compact enclosure"),
        "mounting_guidance": getattr(mechanical, "mounting_guidance", "internal standoffs and panel-mounted controls"),
        "components": components,
        "component_placements": placements,
        "connection_nets": nets,
        "design_assembly_model": assembly_model,
        "subsystems": assembly_model["subsystem_decomposition"],
        "physical_dependency_graph": assembly_model["physical_dependency_graph"],
        "behavior_control_model": assembly_model["behavior_control_model"],
        "assembly_states": assembly_model["assembly_states"],
        "control_loop_visual_requirements": _control_loop_visual_requirements(user_prompt, ir, nets),
        "cad_sources": _cad_source_records(ir),
        "fabrication_notes": _limit_list(getattr(ir, "fabrication_notes", []) or [], 8),
        "constraints": _limit_list(getattr(ir, "constraints", []) or [], 10),
        "allowed_visual_labels": allowed_labels,
        "truth_rules": [
            "Use only these dimensions for all numeric dimension callouts.",
            "Use only listed component refs, names, part numbers, CAD sources, and placements.",
            "Use the design_assembly_model as the source of truth for orientation, part visibility, and component mounting zones.",
            "Preserve every component's subsystem, mounted_on plane, and facing_normal metadata in generated physical layouts.",
            "Preserve subsystem contracts: purpose, inputs, outputs, physical interfaces, placement constraints, dependencies, and verification checks.",
            "Do not invent vendor part numbers, enclosure models, tolerances, wall thickness, mounting hardware, or dimensions.",
            "If a detail is not present in this spec, show it generically or omit the label.",
        ],
    }


def _spec_prompt_text(spec: Dict[str, Any]) -> str:
    assembly_model = spec["design_assembly_model"]
    compact_spec = {
        "title": spec["title"],
        "description": spec["description"],
        "external_dimensions_mm": spec["external_dimensions_mm"],
        "internal_usable_dimensions_mm": spec["internal_usable_dimensions_mm"],
        "enclosure_type": spec["enclosure_type"],
        "mounting_guidance": spec["mounting_guidance"],
        "components": spec["components"],
        "component_placements": spec["component_placements"],
        "connection_nets": spec["connection_nets"],
        "subsystems": spec["subsystems"],
        "physical_dependency_graph": spec["physical_dependency_graph"],
        "behavior_control_model": spec["behavior_control_model"],
        "assembly_states": spec["assembly_states"],
        "design_assembly_model": {
            "modeling_method": assembly_model["modeling_method"],
            "coordinate_frame": assembly_model["coordinate_frame"],
            "component_mounting_zones": assembly_model["component_mounting_zones"],
            "subsystem_decomposition": assembly_model["subsystem_decomposition"],
            "physical_dependency_graph": assembly_model["physical_dependency_graph"],
            "behavior_control_model": assembly_model["behavior_control_model"],
            "assembly_states": assembly_model["assembly_states"],
            "orientation_landmarks": assembly_model["orientation_landmarks"],
            "derived_view_states": assembly_model["derived_view_states"],
            "continuity_checks": assembly_model["continuity_checks"],
        },
        "control_loop_visual_requirements": spec["control_loop_visual_requirements"],
        "cad_sources": spec["cad_sources"],
        "fabrication_notes": spec["fabrication_notes"],
        "constraints": spec["constraints"],
        "allowed_visual_labels": spec["allowed_visual_labels"],
        "truth_rules": spec["truth_rules"],
    }
    return json.dumps(compact_spec, separators=(",", ":"))


def build_project_image_sequence_prompts(user_prompt: str, ir: Any) -> List[Dict[str, Any]]:
    spec = build_project_visual_spec(user_prompt, ir)
    spec_text = _spec_prompt_text(spec)
    shared = [
        "Canonical Visual Design Spec, generated from the Hardware IR:",
        spec_text,
        f"Fixed dimensions for every view: {spec['external_dimensions_text']}; {spec['internal_dimensions_text']}.",
        "Traditional design rule: this is one assembly model with derived view states, not three independent product concepts.",
        "Keep the same object identity, proportions, port positions, display/control layout, material, and scale across all images.",
        "Only the camera angle and part visibility state may change between stages.",
        "The visual sequence must not drift from the Canonical Visual Design Spec.",
        "Respect the fixed coordinate frame and orientation landmarks from design_assembly_model.",
        "Keep the enclosure lid, bottom shell, side walls, PCB, controls, display, fan, ports, vents, standoffs, and wiring as distinct physical parts.",
        "Use subsystem_decomposition to organize physical layouts into UI, control, power/driver, sensing, airflow, mechanical, and support windows when applicable.",
        "Use subsystem contracts to preserve purpose, inputs, outputs, physical interfaces, placement constraints, failure modes, and verification checks.",
        "Use physical_dependency_graph and behavior_control_model to keep layout, wiring, airflow, and feedback relationships coherent.",
        "Preserve each component's mounted_on plane and facing_normal; do not rotate electronics to face the camera for aesthetics.",
        "Prefer top-down transparent or ghosted enclosure views for internal inspection rather than dramatic perspective views.",
        "Do not fuse an exterior lid/top surface with internal electronics, and do not place internals under an opaque closed lid.",
        "Do not add labels, dimensions, enclosure models, hardware kit contents, tolerances, or component names unless they appear in the spec.",
        "Safe low-voltage maker electronics only. No hands, people, watermarks, brand logos, weapons, medical equipment, or mains-voltage hazards.",
    ]

    shared_text = "\n".join(shared)
    return [
        {
            "view_id": "case",
            "label": "Case exterior",
            "prompt": "\n".join(
                [
                    "Stage 1 of 2: create the exterior case render.",
                    shared_text,
                    "Use the case view state from design_assembly_model.",
                    "Render a realistic closed enclosure/case only: visible screen/window openings, buttons, knobs, ports, seams, fillets, screw bosses if visible, and panel cutouts.",
                    "The lid/operator panel is installed and opaque except for display windows, cutouts, ports, vents, or controls that are explicitly visible externally.",
                    "Use consistent orientation landmarks: front wall remains front, right wall remains right, and top/lid controls stay on the top/lid.",
                    "Dimension callouts must exactly match the external_dimensions_mm values in the spec. If external_dimensions_mm is null, do not draw numeric dimension callouts.",
                    "Use a clean neutral studio background and a three-quarter view. Do not show internal electronics in this stage.",
                ]
            ),
        },
        {
            "view_id": "inside",
            "label": "Transparent top-down assembly",
            "prompt": "\n".join(
                [
                    "Stage 2 of 2: image-to-image from the case render into a transparent top-down assembly inspection view.",
                    shared_text,
                    "Use the inside view state from design_assembly_model.",
                    "Use the previous exterior case as the exact same enclosure, now shown from a top-down or near top-down orthographic inspection angle.",
                    "Make the enclosure shell transparent or ghosted at roughly 15-25% opacity so the bottom shell floor, side walls, lid plane, and component mounting planes are all visible.",
                    "Do not roll, invert, mirror, or flip the enclosure. Keep the same front edge, right wall, left wall, and rear wall orientation from the exterior render.",
                    "Show the bottom shell interior as an upward-facing open tub viewed from above; the electronics must sit on the same bottom-shell floor plane and share the same perspective.",
                    "Do not show the case exterior underside facing upward while the electronics face upward. The visible cavity, side walls, standoffs, and electronics must all agree on one coordinate frame.",
                    "Use each component's mounted_on, facing_normal, visible_side, view_preference, and render_rule metadata. Floor boards face +Z, lid controls remain on the lid plane, wall components remain on side-wall planes.",
                    "Do not rotate wall-mounted fans, ports, or lid-mounted displays to face the camera; use transparent shell visibility, ghosting, or small true-plane insets instead.",
                    "Show subtle subsystem grouping cues for UI, control, power/driver, sensing, airflow, and mechanical subsystems without adding unsupported labels.",
                    "Respect subsystem placement constraints: sensors stay exposed to the intended medium, hot drivers stay away from sensors, ports align with wall cutouts, airflow paths remain unblocked, and service loops remain plausible.",
                    "For behavior/control systems, preserve the measured variable source, controller, driver/output path, actuator, and feedback path from behavior_control_model.",
                    "The opaque lid/top surface must not cover or blend into internal electronics.",
                    "Keep lid-mounted display, knob, button, and switch parts attached to the separate lid/operator panel or show their underside/cables clearly; do not relocate them onto the bottom shell unless their mounting_zone says so.",
                    "Keep floor-mounted boards, drivers, power modules, terminals, standoffs, and wiring on the bottom shell floor.",
                    "Show only the electronics and placements listed in the spec: mounted boards, display module, buttons, encoder/knob, power board, connectors, wiring harnesses, standoffs, screws, cable routing, and clearance.",
                    "Dimension callouts must exactly match external_dimensions_mm and internal_usable_dimensions_mm. Preserve exterior port, vent, fan, and control positions from the case render.",
                    "Use a realistic three-quarter product view with the internal electronics clearly visible.",
                ]
            ),
        },
    ]


def _svg_escape(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _svg_data_url(svg: str) -> str:
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def _fmt_mm(value: Any) -> str:
    number = _number_or_none(value)
    if number is None:
        return "?"
    if float(number).is_integer():
        return str(int(number))
    return f"{number:.1f}".rstrip("0").rstrip(".")


def _visual_label(component: Dict[str, Any], limit: int = 32) -> str:
    ref_des = str(component.get("ref_des") or "").strip()
    name = str(component.get("name") or "").strip()
    if ref_des and name:
        return _truncate(f"{ref_des} {name}", limit)
    return _truncate(ref_des or name or "Component", limit)


def _role_style(role: str) -> Dict[str, str]:
    styles = {
        "controller_board": {"fill": "#2f9e44", "stroke": "#14532d"},
        "carrier_board": {"fill": "#6aa84f", "stroke": "#31572c"},
        "display": {"fill": "#1e3a8a", "stroke": "#0f172a"},
        "user_control": {"fill": "#525252", "stroke": "#171717"},
        "external_port": {"fill": "#94a3b8", "stroke": "#334155"},
        "fan_actuator": {"fill": "#111827", "stroke": "#475569"},
        "sensor": {"fill": "#38bdf8", "stroke": "#0369a1"},
        "driver_stage": {"fill": "#f97316", "stroke": "#9a3412"},
        "mounting_hardware": {"fill": "#fbbf24", "stroke": "#92400e"},
        "power": {"fill": "#a78bfa", "stroke": "#5b21b6"},
    }
    return styles.get(role, {"fill": "#cbd5e1", "stroke": "#475569"})


def _component_position(
    component: Dict[str, Any],
    index: int,
    total: int,
    *,
    box_x: float,
    box_y: float,
    box_w: float,
    box_h: float,
    scale: float,
) -> Tuple[float, float]:
    zone = str(component.get("mounting_zone") or "")
    position = component.get("position_mm")
    margin = 24.0
    if isinstance(position, dict):
        x_mm = _number_or_none(position.get("x_mm"))
        y_mm = _number_or_none(position.get("y_mm"))
        if x_mm is not None and y_mm is not None:
            x = box_x + box_w / 2 + x_mm * scale
            y = box_y + box_h / 2 - y_mm * scale
            return (
                min(max(x, box_x + margin), box_x + box_w - margin),
                min(max(y, box_y + margin), box_y + box_h - margin),
            )

    slot = index / max(1, total - 1)
    if zone == "front_wall_edge":
        return box_x + box_w * (0.24 + slot * 0.52), box_y + box_h - 18
    if zone in {"rear_wall", "back_wall"}:
        return box_x + box_w * (0.24 + slot * 0.52), box_y + 18
    if zone == "right_wall_exhaust":
        return box_x + box_w - 24, box_y + box_h * (0.30 + slot * 0.40)
    if zone == "left_wall":
        return box_x + 24, box_y + box_h * (0.30 + slot * 0.40)
    if zone == "air_inlet_zone_away_from_heat_sources":
        return box_x + box_w * 0.18, box_y + box_h * (0.28 + slot * 0.34)

    columns = 3
    row = index // columns
    col = index % columns
    rows = max(1, (total + columns - 1) // columns)
    x = box_x + box_w * (0.25 + 0.25 * col)
    y = box_y + box_h * (0.32 + 0.38 * (row / max(1, rows - 1)))
    if total <= columns:
        y = box_y + box_h * 0.52
    return x, y


def _component_footprint(
    component: Dict[str, Any],
    *,
    scale: float,
    default_w: float,
    default_h: float,
    maximum: float = 110.0,
) -> Tuple[float, float]:
    size = component.get("size_mm")
    if isinstance(size, dict):
        x_mm = _number_or_none(size.get("x_mm"))
        y_mm = _number_or_none(size.get("y_mm"))
        z_mm = _number_or_none(size.get("z_mm"))
        if x_mm is not None and y_mm is not None:
            role = str(component.get("visual_role") or "")
            if role == "fan_actuator" and z_mm is not None:
                side = min(max(z_mm * scale, 42), maximum)
                return side, side
            return min(max(x_mm * scale, 34), maximum), min(max(y_mm * scale, 22), maximum)
    return default_w, default_h


def _draw_dimension_arrow(
    parts: List[str],
    *,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    label: str,
    text_x: float,
    text_y: float,
) -> None:
    parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#111827" stroke-width="1.5" marker-start="url(#arrow)" marker-end="url(#arrow)"/>')
    parts.append(f'<text x="{text_x:.1f}" y="{text_y:.1f}" class="dim">{_svg_escape(label)}</text>')


def _draw_component(
    parts: List[str],
    component: Dict[str, Any],
    *,
    x: float,
    y: float,
    w: float,
    h: float,
    label_inside: bool = False,
) -> None:
    role = str(component.get("visual_role") or "")
    style = _role_style(role)
    ref_des = _svg_escape(component.get("ref_des") or "")
    label = _svg_escape(_visual_label(component, 28))

    if role in {"fan_actuator", "user_control", "mounting_hardware"}:
        radius = max(8.0, min(w, h) / 2)
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" fill="{style["fill"]}" stroke="{style["stroke"]}" stroke-width="2"/>')
        if role == "fan_actuator":
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{max(4.0, radius * 0.35):.1f}" fill="#334155" stroke="#64748b" stroke-width="1"/>')
            for angle in (0, 90, 180, 270):
                parts.append(f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{x + radius * 0.72:.1f}" y2="{y:.1f}" stroke="#94a3b8" stroke-width="3" transform="rotate({angle} {x:.1f} {y:.1f})"/>')
        parts.append(f'<text x="{x:.1f}" y="{y + radius + 15:.1f}" class="label" text-anchor="middle">{ref_des}</text>')
        return

    rx = min(8.0, max(2.0, min(w, h) * 0.12))
    parts.append(f'<rect x="{x - w / 2:.1f}" y="{y - h / 2:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx:.1f}" fill="{style["fill"]}" stroke="{style["stroke"]}" stroke-width="2"/>')
    if role in {"controller_board", "carrier_board"}:
        pin_count = 10
        for index in range(pin_count):
            px = x - w / 2 + 8 + index * max(3.0, (w - 16) / max(1, pin_count - 1))
            parts.append(f'<circle cx="{px:.1f}" cy="{y - h / 2 + 5:.1f}" r="2" fill="#fef3c7" stroke="#78350f" stroke-width="0.5"/>')
            parts.append(f'<circle cx="{px:.1f}" cy="{y + h / 2 - 5:.1f}" r="2" fill="#fef3c7" stroke="#78350f" stroke-width="0.5"/>')
    if label_inside:
        parts.append(f'<text x="{x:.1f}" y="{y - 3:.1f}" class="component-inverse" text-anchor="middle">{ref_des}</text>')
        parts.append(f'<text x="{x:.1f}" y="{y + 13:.1f}" class="component-inverse small" text-anchor="middle">{_svg_escape(_truncate(str(component.get("name") or ""), 16))}</text>')
    else:
        parts.append(f'<text x="{x:.1f}" y="{y + h / 2 + 15:.1f}" class="label" text-anchor="middle">{label}</text>')


def _group_components_by_mounting_zone(assembly_components: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    lid_components = [
        component
        for component in assembly_components
        if str(component.get("mounting_zone") or "") == "top_lid_operator_panel"
    ]
    lid_refs = {component.get("ref_des") for component in lid_components}
    bottom_components = [
        component
        for component in assembly_components
        if component.get("ref_des") not in lid_refs
    ]
    return bottom_components, lid_components


def _draw_layer_window(
    parts: List[str],
    *,
    x: float,
    y: float,
    w: float,
    h: float,
    title: str,
    subtitle: str,
    accent: str,
) -> Tuple[float, float, float, float]:
    parts.append(f'<rect x="{x + 4:.1f}" y="{y + 6:.1f}" width="{w:.1f}" height="{h:.1f}" rx="14" fill="#cbd5e1" opacity="0.45"/>')
    parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="14" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.5"/>')
    parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="42" rx="14" fill="#111827"/>')
    parts.append(f'<path d="M{x:.1f} {y + 28:.1f} H{x + w:.1f} V{y + 42:.1f} H{x:.1f} Z" fill="#111827"/>')
    parts.append(f'<rect x="{x:.1f}" y="{y + 40:.1f}" width="{w:.1f}" height="4" fill="{accent}"/>')
    parts.append(f'<text x="{x + 18:.1f}" y="{y + 25:.1f}" class="window-title">{_svg_escape(title)}</text>')
    parts.append(f'<text x="{x + w - 18:.1f}" y="{y + 25:.1f}" class="window-subtitle" text-anchor="end">{_svg_escape(subtitle)}</text>')
    return x + 18, y + 60, w - 36, h - 78


def _component_zone(component: Dict[str, Any]) -> str:
    return str(component.get("mounting_zone") or "bottom_shell_floor")


def build_project_layout_diagram_image(
    user_prompt: str,
    ir: Any,
    *,
    prompt: Optional[str] = None,
    reference_view_id: Optional[str] = None,
    prompt_compaction_result: Optional[PromptCompactionResult] = None,
) -> GeneratedImage:
    spec = build_project_visual_spec(user_prompt, ir)
    assembly_model = spec["design_assembly_model"]
    dimensions = spec.get("external_dimensions_mm") or {"x_mm": 120.0, "y_mm": 80.0, "z_mm": 40.0}
    width_mm = max(1.0, float(dimensions.get("x_mm") or 120.0))
    depth_mm = max(1.0, float(dimensions.get("y_mm") or 80.0))
    height_mm = max(1.0, float(dimensions.get("z_mm") or 40.0))
    internal = spec.get("internal_usable_dimensions_mm") or {}
    assembly_components = assembly_model.get("component_mounting_zones", [])
    bottom_components, lid_components = _group_components_by_mounting_zone(assembly_components)
    ui_components = [component for component in assembly_components if component.get("subsystem") == "ui"]
    sensing_components = [component for component in assembly_components if component.get("subsystem") == "sensing"]
    airflow_components = [component for component in assembly_components if component.get("subsystem") == "airflow"]
    wall_zones = {"front_wall_edge", "right_wall_exhaust", "left_wall", "rear_wall", "back_wall", "air_inlet_zone_away_from_heat_sources"}
    wall_components = [component for component in bottom_components if _component_zone(component) in wall_zones]
    floor_components = [component for component in bottom_components if _component_zone(component) not in wall_zones]
    if not floor_components:
        floor_components = [
            component
            for component in bottom_components
            if component.get("visual_role") not in {"external_port", "fan_actuator"}
        ]

    canvas_w = 1024
    canvas_h = 1024
    parts: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{canvas_w}" height="{canvas_h}" viewBox="0 0 {canvas_w} {canvas_h}">',
        "<defs>",
        '<marker id="arrow" markerWidth="8" markerHeight="8" refX="4" refY="4" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L8,4 L0,8 Z" fill="#111827"/></marker>',
        "<style>",
        "text{font-family:Inter,Arial,Helvetica,sans-serif;fill:#111827}.title{font-size:28px;font-weight:800}.subtitle{font-size:13px;font-weight:700;letter-spacing:.08em}.dim{font-size:12px;font-weight:800;text-anchor:middle}.label{font-size:11px;font-weight:800}.small{font-size:10px}.note{font-size:12px}.component-inverse{font-size:11px;font-weight:800;fill:#f8fafc}.section{font-size:13px;font-weight:900;letter-spacing:.06em}.muted{fill:#475569}.net{font-size:11px}.tiny{font-size:9px}.window-title{fill:#f8fafc;font-size:13px;font-weight:900;letter-spacing:.08em}.window-subtitle{fill:#cbd5e1;font-size:10px;font-weight:800;letter-spacing:.08em}.chip{font-size:10px;font-weight:800}",
        "</style>",
        "</defs>",
        '<rect x="0" y="0" width="1024" height="1024" fill="#eef2f7"/>',
    ]

    title = _svg_escape(spec.get("title") or "Component Layout Diagram")
    parts.append(f'<text x="40" y="44" class="title">{title}</text>')
    parts.append('<text x="40" y="72" class="subtitle muted">SUBSYSTEM PHYSICAL LAYOUT SHEET - GENERATED FROM HARDWARE IR</text>')
    parts.append(
        f'<text x="40" y="98" class="note muted">External {_fmt_mm(width_mm)} mm W x {_fmt_mm(depth_mm)} mm D x {_fmt_mm(height_mm)} mm H'
        f' / internal usable {_fmt_mm(internal.get("x_mm"))} mm W x {_fmt_mm(internal.get("y_mm"))} mm D x {_fmt_mm(internal.get("z_mm"))} mm H'
        ' / transparent top-down reference / front edge is bottom</text>'
    )

    shell_cx, shell_cy, shell_cw, shell_ch = _draw_layer_window(
        parts,
        x=36,
        y=124,
        w=610,
        h=446,
        title="ASSEMBLY MAP / SUBSYSTEM POSITIONS",
        subtitle="TRANSPARENT CASE",
        accent="#22c55e",
    )
    lid_cx, lid_cy, lid_cw, lid_ch = _draw_layer_window(
        parts,
        x=672,
        y=124,
        w=316,
        h=210,
        title="UI SUBSYSTEM",
        subtitle="LID PLANE",
        accent="#38bdf8",
    )
    wall_cx, wall_cy, wall_cw, wall_ch = _draw_layer_window(
        parts,
        x=672,
        y=360,
        w=316,
        h=210,
        title="SENSING + AIRFLOW",
        subtitle="WALLS / PATH",
        accent="#f97316",
    )
    net_cx, net_cy, net_cw, net_ch = _draw_layer_window(
        parts,
        x=36,
        y=604,
        w=610,
        h=286,
        title="CONTROL + POWER/DRIVER",
        subtitle="NETS + LOOP",
        accent="#a855f7",
    )
    ref_cx, ref_cy, ref_cw, ref_ch = _draw_layer_window(
        parts,
        x=672,
        y=604,
        w=316,
        h=286,
        title="SUBSYSTEM SUMMARY",
        subtitle="RULES",
        accent="#facc15",
    )

    scale = min((shell_cw - 84) / width_mm, (shell_ch - 86) / depth_mm)
    shell_w = width_mm * scale
    shell_h = depth_mm * scale
    shell_x = shell_cx + (shell_cw - shell_w) / 2
    shell_y = shell_cy + 30 + (shell_ch - 70 - shell_h) / 2

    _draw_dimension_arrow(
        parts,
        x1=shell_x,
        y1=shell_y - 22,
        x2=shell_x + shell_w,
        y2=shell_y - 22,
        label=f"{_fmt_mm(width_mm)} mm W",
        text_x=shell_x + shell_w / 2,
        text_y=shell_y - 30,
    )
    _draw_dimension_arrow(
        parts,
        x1=shell_x - 24,
        y1=shell_y,
        x2=shell_x - 24,
        y2=shell_y + shell_h,
        label=f"{_fmt_mm(depth_mm)} mm D",
        text_x=shell_x - 42,
        text_y=shell_y + shell_h / 2,
    )
    parts.append(f'<rect x="{shell_x:.1f}" y="{shell_y:.1f}" width="{shell_w:.1f}" height="{shell_h:.1f}" rx="22" fill="#e2e8f0" opacity=".68" stroke="#0f172a" stroke-width="2.5"/>')
    parts.append(f'<rect x="{shell_x + 15:.1f}" y="{shell_y + 15:.1f}" width="{shell_w - 30:.1f}" height="{shell_h - 30:.1f}" rx="15" fill="#f8fafc" stroke="#94a3b8" stroke-width="1.25" stroke-dasharray="7 5"/>')
    parts.append(f'<rect x="{shell_x + 24:.1f}" y="{shell_y + shell_h - 30:.1f}" width="{shell_w - 48:.1f}" height="5" rx="2.5" fill="#0f172a" opacity=".22"/>')
    parts.append(f'<text x="{shell_x + shell_w / 2:.1f}" y="{shell_y + shell_h - 13:.1f}" class="tiny muted" text-anchor="middle">FRONT EDGE / GHOSTED ENCLOSURE / TRUE MOUNTING PLANES</text>')

    bottom_points: Dict[str, Tuple[float, float]] = {}
    zone_counts: Dict[str, int] = {}
    zone_indices: Dict[str, int] = {}
    for component in floor_components:
        zone = str(component.get("mounting_zone") or "bottom_shell_floor")
        zone_counts[zone] = zone_counts.get(zone, 0) + 1
    for index, component in enumerate(floor_components):
        zone = str(component.get("mounting_zone") or "bottom_shell_floor")
        zone_index = zone_indices.get(zone, 0)
        zone_indices[zone] = zone_index + 1
        x, y = _component_position(
            component,
            zone_index,
            zone_counts.get(zone, 1),
            box_x=shell_x + 18,
            box_y=shell_y + 18,
            box_w=shell_w - 36,
            box_h=shell_h - 36,
            scale=scale,
        )
        bottom_points[str(component.get("ref_des") or index)] = (x, y)
        w, h = _component_footprint(component, scale=scale, default_w=68, default_h=34, maximum=94)
        _draw_component(parts, component, x=x, y=y, w=w, h=h, label_inside=str(component.get("visual_role")) in {"controller_board", "carrier_board", "display"})

    for sx, sy in [
        (shell_x + 22, shell_y + 22),
        (shell_x + shell_w - 22, shell_y + 22),
        (shell_x + 22, shell_y + shell_h - 22),
        (shell_x + shell_w - 22, shell_y + shell_h - 22),
    ]:
        parts.append(f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="10" fill="#fde68a" stroke="#92400e" stroke-width="2"/>')
        parts.append(f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="4" fill="#92400e"/>')

    lid_shell_w = min(lid_cw - 36, width_mm * min((lid_cw - 44) / width_mm, (lid_ch - 56) / depth_mm))
    lid_shell_h = min(lid_ch - 54, depth_mm * min((lid_cw - 44) / width_mm, (lid_ch - 56) / depth_mm))
    lid_shell_x = lid_cx + (lid_cw - lid_shell_w) / 2
    lid_shell_y = lid_cy + 34
    parts.append(f'<rect x="{lid_shell_x:.1f}" y="{lid_shell_y:.1f}" width="{lid_shell_w:.1f}" height="{lid_shell_h:.1f}" rx="12" fill="#f8fafc" stroke="#0f172a" stroke-width="1.4" stroke-dasharray="6 4"/>')
    parts.append(f'<text x="{lid_cx:.1f}" y="{lid_cy + 16:.1f}" class="note muted">UI parts keep lid-plane facing metadata.</text>')
    ui_window_components = ui_components or lid_components
    if ui_window_components:
        lid_scale = min((lid_shell_w - 34) / width_mm, (lid_shell_h - 34) / depth_mm)
        for index, component in enumerate(ui_window_components):
            position = component.get("position_mm")
            if isinstance(position, dict) and _number_or_none(position.get("x_mm")) is not None and _number_or_none(position.get("y_mm")) is not None:
                x = lid_shell_x + lid_shell_w / 2 + float(position.get("x_mm")) * lid_scale
                y = lid_shell_y + lid_shell_h / 2 - float(position.get("y_mm")) * lid_scale
            else:
                x = lid_shell_x + 42 + index * min(74, (lid_shell_w - 84) / max(1, len(ui_window_components) - 1))
                y = lid_shell_y + lid_shell_h / 2
            x = min(max(x, lid_shell_x + 30), lid_shell_x + lid_shell_w - 30)
            y = min(max(y, lid_shell_y + 24), lid_shell_y + lid_shell_h - 24)
            w, h = _component_footprint(component, scale=lid_scale, default_w=50, default_h=28, maximum=64)
            _draw_component(parts, component, x=x, y=y, w=w, h=h, label_inside=str(component.get("visual_role")) == "display")
    else:
        parts.append(f'<text x="{lid_cx:.1f}" y="{lid_cy + 72:.1f}" class="note muted">No UI subsystem components in IR.</text>')

    wall_groups = [
        ("POWER / I/O", "front_wall_edge", "#64748b"),
        ("AIRFLOW", "right_wall_exhaust", "#f97316"),
        ("SENSING", "air_inlet_zone_away_from_heat_sources", "#38bdf8"),
        ("REAR / AUX", "rear_wall", "#94a3b8"),
    ]
    parts.append(f'<text x="{wall_cx:.1f}" y="{wall_cy + 16:.1f}" class="note muted">Subsystems keep wall/air-path facing normals.</text>')
    for index, (label, zone, color) in enumerate(wall_groups):
        row_y = wall_cy + 36 + index * 34
        parts.append(f'<rect x="{wall_cx:.1f}" y="{row_y:.1f}" width="{wall_cw:.1f}" height="26" rx="7" fill="#f8fafc" stroke="#cbd5e1" stroke-width="1"/>')
        parts.append(f'<rect x="{wall_cx:.1f}" y="{row_y:.1f}" width="74" height="26" rx="7" fill="{color}"/>')
        parts.append(f'<text x="{wall_cx + 37:.1f}" y="{row_y + 17:.1f}" class="chip" fill="#ffffff" text-anchor="middle">{_svg_escape(label)}</text>')
        zone_items = [component for component in wall_components if _component_zone(component) == zone or (zone == "rear_wall" and _component_zone(component) == "back_wall")]
        if zone == "right_wall_exhaust":
            zone_items.extend(component for component in airflow_components if component not in zone_items)
        if zone == "air_inlet_zone_away_from_heat_sources":
            zone_items.extend(component for component in sensing_components if component not in zone_items)
        if zone_items:
            text = " / ".join(f"{_visual_label(component, 14)} {component.get('facing_normal') or ''}" for component in zone_items[:3])
        else:
            text = "no assigned components"
        parts.append(f'<text x="{wall_cx + 86:.1f}" y="{row_y + 17:.1f}" class="note">{_svg_escape(text)}</text>')

    controller = next((component for component in floor_components if component.get("visual_role") == "controller_board"), None)
    driver = next((component for component in floor_components if component.get("visual_role") == "driver_stage"), None)
    fan = next((component for component in wall_components if component.get("visual_role") == "fan_actuator"), None)
    sensor = next((component for component in wall_components + floor_components if component.get("visual_role") == "sensor"), None)
    behavior = spec.get("behavior_control_model") or {}
    block_y = net_cy + 42
    block_specs = [
        ("SENSOR / FEEDBACK", sensor, "#38bdf8"),
        ("CONTROLLER", controller, "#22c55e"),
        ("DRIVER", driver, "#f97316"),
        ("ACTUATOR", fan, "#111827"),
    ]
    block_w = 122
    gap = 22
    block_points: List[Tuple[float, float]] = []
    for index, (label, component, color) in enumerate(block_specs):
        x = net_cx + index * (block_w + gap)
        parts.append(f'<rect x="{x:.1f}" y="{block_y:.1f}" width="{block_w:.1f}" height="58" rx="10" fill="#f8fafc" stroke="{color}" stroke-width="2"/>')
        parts.append(f'<text x="{x + block_w / 2:.1f}" y="{block_y + 22:.1f}" class="tiny" text-anchor="middle">{_svg_escape(label)}</text>')
        parts.append(f'<text x="{x + block_w / 2:.1f}" y="{block_y + 42:.1f}" class="label" text-anchor="middle">{_svg_escape(_visual_label(component or {}, 18) if component else "not specified")}</text>')
        block_points.append((x + block_w, block_y + 29))
        if index < len(block_specs) - 1:
            parts.append(f'<line x1="{x + block_w:.1f}" y1="{block_y + 29:.1f}" x2="{x + block_w + gap - 4:.1f}" y2="{block_y + 29:.1f}" stroke="#334155" stroke-width="2" marker-end="url(#arrow)"/>')
    parts.append(f'<path d="M{net_cx + block_w * 3 + gap * 3 + block_w / 2:.1f} {block_y + 68:.1f} C{net_cx + 420:.1f} {block_y + 116:.1f},{net_cx + 140:.1f} {block_y + 116:.1f},{net_cx + 62:.1f} {block_y + 68:.1f}" fill="none" stroke="#0284c7" stroke-width="2.4" stroke-dasharray="8 5" marker-end="url(#arrow)"/>')
    parts.append(f'<text x="{net_cx + 230:.1f}" y="{block_y + 120:.1f}" class="label" fill="#075985" text-anchor="middle">feedback path when supported by nets</text>')
    controlled_variables = ", ".join(str(item) for item in (behavior.get("controlled_variables") or [])[:3])
    control_type = str(behavior.get("control_model_type") or "control model")
    parts.append(f'<text x="{net_cx:.1f}" y="{block_y + 146:.1f}" class="note muted">{_svg_escape(_truncate(f"{control_type}: {controlled_variables}", 82))}</text>')

    nets = spec.get("connection_nets") or []
    control_nets = [
        net
        for net in nets
        if any(token in f'{net.get("name", "")} {net.get("net_type", "")}'.lower() for token in ["pwm", "tach", "feedback", "sensor", "i2c", "analog"])
    ][:7]
    if not control_nets:
        control_nets = nets[:7]
    if control_nets:
        for index, net in enumerate(control_nets):
            y = net_cy + 188 + index * 14
            pins = ", ".join(
                f'{pin.get("ref_des")}:{pin.get("pin_id")}'
                for pin in (net.get("pins") or [])[:4]
                if pin.get("ref_des") or pin.get("pin_id")
            )
            line = _truncate(f'{net.get("net_id") or ""}  {net.get("name") or ""}  [{net.get("net_type") or ""}]  {pins}', 88)
            parts.append(f'<text x="{net_cx:.1f}" y="{y:.1f}" class="net">{_svg_escape(line)}</text>')
    else:
        parts.append(f'<text x="{net_cx:.1f}" y="{net_cy + 188:.1f}" class="note muted">No connection nets present in IR.</text>')

    subsystem_colors = {
        "ui": "#38bdf8",
        "control": "#22c55e",
        "power_driver": "#a855f7",
        "sensing": "#06b6d4",
        "airflow": "#f97316",
        "mechanical": "#facc15",
        "support": "#94a3b8",
    }
    subsystem_rows = (spec.get("subsystems") or [])[:4]
    for index, subsystem in enumerate(subsystem_rows):
        y = ref_cy + 6 + index * 38
        label = subsystem.get("label") or subsystem.get("id") or "Subsystem"
        count = len(subsystem.get("component_refs") or [])
        color = subsystem_colors.get(str(subsystem.get("id") or ""), "#94a3b8")
        contract = subsystem.get("contract") if isinstance(subsystem.get("contract"), dict) else {}
        purpose = _truncate(contract.get("purpose", ""), 46)
        parts.append(f'<rect x="{ref_cx:.1f}" y="{y:.1f}" width="{ref_cw:.1f}" height="32" rx="7" fill="#f8fafc" stroke="#e2e8f0"/>')
        parts.append(f'<circle cx="{ref_cx + 13:.1f}" cy="{y + 12:.1f}" r="5" fill="{color}"/>')
        parts.append(f'<text x="{ref_cx + 28:.1f}" y="{y + 14:.1f}" class="note">{_svg_escape(label)}</text>')
        parts.append(f'<text x="{ref_cx + ref_cw - 12:.1f}" y="{y + 14:.1f}" class="label" text-anchor="end">{count}</text>')
        if purpose:
            parts.append(f'<text x="{ref_cx + 28:.1f}" y="{y + 27:.1f}" class="small muted">{_svg_escape(purpose)}</text>')
    rules = [
        "Contracts include purpose, interfaces, constraints, checks.",
        "Each component preserves mounted_on and facing_normal.",
        "Dependencies/feedback are relationships, not relocation excuses.",
        "Dimensions come only from the visual spec.",
    ]
    for index, rule in enumerate(rules):
        parts.append(f'<text x="{ref_cx:.1f}" y="{ref_cy + 170 + index * 18:.1f}" class="note muted">- {_svg_escape(rule)}</text>')

    parts.append("</svg>")
    svg = "\n".join(parts)
    return GeneratedImage(
        data_url=_svg_data_url(svg),
        provider="blueprint-layout",
        model="deterministic-subsystem-svg-v1",
        size=f"{canvas_w}x{canvas_h}",
        prompt=prompt or "Deterministic layout sheet generated from the canonical visual spec.",
        output_format="svg+xml",
        view_id="diagram",
        label="Layout diagram",
        reference_view_id=reference_view_id,
        prompt_original_length=prompt_compaction_result.original_length if prompt_compaction_result else None,
        prompt_final_length=prompt_compaction_result.final_length if prompt_compaction_result else None,
        prompt_compacted=prompt_compaction_result.was_compacted if prompt_compaction_result else False,
        prompt_compaction_strategy=prompt_compaction_result.strategy if prompt_compaction_result else "none",
    )


def build_image_provider(force_enabled: bool = False) -> ImageProvider:
    provider_name = (_env("IMAGE_PROVIDER") or "").strip().lower().replace("_", "-")
    enabled_default = bool(provider_name and provider_name not in {"none", "disabled", "off", "false", "simulation", "mock"})
    enabled = _first_env_bool(["IMAGE_OUTPUT_ENABLED", "OPENAI_IMAGE_OUTPUT_ENABLED"], default=enabled_default)

    if not enabled and not force_enabled:
        return NoImageProvider()

    if not provider_name:
        if _first_env(["OPENAI_IMAGE_API_KEY", "OPENAI_API_KEY"]):
            provider_name = "openai"
        elif _first_env(["GMI_IMAGE_API_KEY", "GMI_API_KEY", "GMI_CLOUD_API_KEY", "GMICLOUD_API_KEY"]):
            provider_name = "gmi"
        elif _first_env(["TOGETHER_IMAGE_API_KEY", "TOGETHER_API_KEY"]):
            provider_name = "together"
        elif _first_env(["HUGGINGFACE_IMAGE_API_KEY", "HF_IMAGE_TOKEN", "HF_TOKEN", "HUGGINGFACE_API_KEY"]) and _first_env(["HUGGINGFACE_IMAGE_MODEL", "HF_IMAGE_MODEL"]):
            provider_name = "huggingface"
        elif _first_env(["IMAGE_BASE_URL", "OPENAI_IMAGE_BASE_URL", "LLM_BASE_URL", "OPENAI_BASE_URL"]):
            provider_name = "openai-compatible"
        else:
            return NoImageProvider("Image output is enabled, but no image provider configuration was found.")

    if provider_name in {"none", "disabled", "off", "false", "simulation", "mock"}:
        return NoImageProvider()
    if provider_name in {"openai", "openai-compatible", "compatible"}:
        return OpenAIImageProvider(provider_name=provider_name, enabled=enabled, force_enabled=force_enabled)
    if provider_name in {"gmi", "gmi-cloud", "gmicloud", "gemicloud"}:
        return GMIImageProvider(enabled=enabled, force_enabled=force_enabled)
    if provider_name in {"together", "together-ai", "togetherai"}:
        return TogetherImageProvider(enabled=enabled, force_enabled=force_enabled)
    if provider_name in {"huggingface", "hugging-face", "hf"}:
        return HuggingFaceImageProvider(enabled=enabled, force_enabled=force_enabled)

    logger.warning("Unsupported IMAGE_PROVIDER %r; image output is disabled.", provider_name)
    return NoImageProvider(
        f"Unsupported IMAGE_PROVIDER '{provider_name}'. Supported providers are openai, openai-compatible, gmi, together, huggingface, and none."
    )


def get_image_output_debug_config() -> Dict[str, Any]:
    default_config = build_image_provider().get_debug_config()
    request_config = build_image_provider(force_enabled=True).get_debug_config()
    return {
        **default_config,
        "default_enabled": default_config.get("enabled", False),
        "request_capable": bool(request_config.get("configured")),
        "request_provider": request_config.get("provider"),
        "request_model_name": request_config.get("model_name"),
    }
