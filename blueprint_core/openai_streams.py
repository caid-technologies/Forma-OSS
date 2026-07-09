from __future__ import annotations

import ast
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from blueprint_core.continuous_agents import JsonlStreamStore


DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_STREAM_MODEL = "gpt-5.5"
DEFAULT_OPENAI_STREAM_PROMPT = "Write one concise sentence about a blue electromechanical device."
DEFAULT_OPENAI_STREAM_TIMEOUT_SECONDS = 300.0
DEFAULT_OPENAI_STREAM_MAX_OUTPUT_TOKENS = 1600
DEFAULT_BASETEN_BASE_URL = "https://inference.baseten.co/v1"
DEFAULT_BASETEN_STREAM_MODEL = "zai-org/GLM-5.2"
DEFAULT_GMI_BASE_URL = "https://api.gmi-serving.com/v1"
DEFAULT_GMI_STREAM_MODEL = "anthropic/claude-fable-5"
DEFAULT_OPENAI_COMPATIBLE_CHAT_TEMPERATURE = 0.2
DEFAULT_HTTP_USER_AGENT = "Blueprint-OSS/0.1"


def http_user_agent() -> str:
    return os.getenv("LLM_USER_AGENT", DEFAULT_HTTP_USER_AGENT)


class OpenAIStreamConfigError(RuntimeError):
    pass


class OpenAIStreamRequestError(RuntimeError):
    def __init__(self, method: str, url: str, status_code: int | None, message: str) -> None:
        status = f"HTTP {status_code}" if status_code is not None else "request failed"
        super().__init__(f"{method} {url} returned {status}: {message}")


@dataclass(frozen=True)
class ServerSentEvent:
    event: Optional[str]
    data: str


@dataclass(frozen=True)
class OpenAITextStreamChunk:
    sequence: int
    content: str
    done: bool
    response_event_type: str
    response_id: Optional[str] = None
    error_message: Optional[str] = None


@dataclass(frozen=True)
class OpenAIStreamConfig:
    api_key: str
    model: str = DEFAULT_OPENAI_STREAM_MODEL
    base_url: str = DEFAULT_OPENAI_BASE_URL
    prompt: str = DEFAULT_OPENAI_STREAM_PROMPT
    timeout_seconds: float = DEFAULT_OPENAI_STREAM_TIMEOUT_SECONDS
    max_output_tokens: int = DEFAULT_OPENAI_STREAM_MAX_OUTPUT_TOKENS
    project_id: Optional[str] = None
    organization_id: Optional[str] = None
    instructions: Optional[str] = None

    @classmethod
    def from_env_file(
        cls,
        env_file: Path,
        *,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        prompt: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
        instructions: Optional[str] = None,
    ) -> "OpenAIStreamConfig":
        env = merged_env(env_file)
        api_key = first_env(env, "OPENAI_API_KEY", "LLM_API_KEY")
        if not api_key:
            raise OpenAIStreamConfigError("Missing OPENAI_API_KEY in .env or process environment.")

        resolved_model = model or first_env(env, "OPENAI_STREAM_MODEL", "OPENAI_MODEL", "LLM_MODEL") or DEFAULT_OPENAI_STREAM_MODEL
        resolved_base_url = normalize_base_url(base_url or first_env(env, "OPENAI_BASE_URL") or DEFAULT_OPENAI_BASE_URL)
        resolved_prompt = prompt or first_env(env, "OPENAI_STREAM_PROMPT") or DEFAULT_OPENAI_STREAM_PROMPT
        resolved_timeout = timeout_seconds or float_env(env, DEFAULT_OPENAI_STREAM_TIMEOUT_SECONDS, "OPENAI_STREAM_TIMEOUT_SECONDS", "OPENAI_TIMEOUT_SECONDS", "LLM_TIMEOUT_SECONDS")
        resolved_max_output_tokens = max_output_tokens or int_env(
            env,
            DEFAULT_OPENAI_STREAM_MAX_OUTPUT_TOKENS,
            "OPENAI_STREAM_MAX_OUTPUT_TOKENS",
            "OPENAI_TEST_MAX_OUTPUT_TOKENS",
        )

        return cls(
            api_key=api_key,
            model=resolved_model,
            base_url=resolved_base_url,
            prompt=resolved_prompt,
            timeout_seconds=resolved_timeout,
            max_output_tokens=resolved_max_output_tokens,
            project_id=first_env(env, "OPENAI_PROJECT_ID"),
            organization_id=first_env(env, "OPENAI_ORG_ID", "OPENAI_ORGANIZATION"),
            instructions=instructions or first_env(env, "OPENAI_STREAM_INSTRUCTIONS"),
        )

    def response_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/responses"

    def headers(self) -> Mapping[str, str]:
        headers = {
            "Accept": "text/event-stream",
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": http_user_agent(),
        }
        if self.project_id:
            headers["OpenAI-Project"] = self.project_id
        if self.organization_id:
            headers["OpenAI-Organization"] = self.organization_id
        return headers

    def request_payload(self) -> Mapping[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "input": self.prompt,
            "stream": True,
            "max_output_tokens": self.max_output_tokens,
        }
        if self.instructions:
            payload["instructions"] = self.instructions
        return payload


@dataclass(frozen=True)
class OpenAICompatibleChatConfig:
    provider_name: str
    api_key: str
    model: str
    base_url: str
    prompt: str
    timeout_seconds: float = DEFAULT_OPENAI_STREAM_TIMEOUT_SECONDS
    max_output_tokens: int = DEFAULT_OPENAI_STREAM_MAX_OUTPUT_TOKENS
    instructions: Optional[str] = None
    temperature: Optional[float] = DEFAULT_OPENAI_COMPATIBLE_CHAT_TEMPERATURE

    @classmethod
    def from_env_file(
        cls,
        env_file: Path,
        *,
        provider_name: str,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        prompt: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
        instructions: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> "OpenAICompatibleChatConfig":
        env = merged_env(env_file)
        provider = normalize_stream_provider_name(provider_name)
        if provider not in {"baseten", "gmi"}:
            raise OpenAIStreamConfigError(f"Unsupported OpenAI-compatible stream provider {provider_name!r}.")

        if provider == "baseten":
            api_key_names = ("BASETEN_API_KEY", "LLM_API_KEY")
            base_url_names = ("BASETEN_BASE_URL", "LLM_BASE_URL")
            model_names = ("BASETEN_STREAM_MODEL", "BASETEN_MODEL", "LLM_MODEL")
            timeout_names = ("BASETEN_STREAM_TIMEOUT_SECONDS", "BASETEN_TIMEOUT_SECONDS", "LLM_TIMEOUT_SECONDS")
            max_output_names = ("BASETEN_STREAM_MAX_OUTPUT_TOKENS", "BASETEN_MAX_TOKENS", "LLM_MAX_TOKENS")
            temperature_names = ("BASETEN_STREAM_TEMPERATURE", "BASETEN_TEMPERATURE", "LLM_TEMPERATURE")
            default_model = DEFAULT_BASETEN_STREAM_MODEL
            default_base_url = DEFAULT_BASETEN_BASE_URL
            default_temperature = DEFAULT_OPENAI_COMPATIBLE_CHAT_TEMPERATURE
            missing_key_message = "Missing BASETEN_API_KEY in .env or process environment."
        else:
            api_key_names = ("GMI_API_KEY", "GMI_CLOUD_API_KEY", "GMICLOUD_API_KEY", "LLM_API_KEY")
            base_url_names = ("GMI_BASE_URL", "GMI_CLOUD_BASE_URL", "GMICLOUD_BASE_URL")
            model_names = ("GMI_STREAM_MODEL", "GMI_MODEL", "GMI_CLOUD_MODEL", "GMICLOUD_MODEL", "LLM_MODEL")
            timeout_names = ("GMI_STREAM_TIMEOUT_SECONDS", "GMI_TIMEOUT_SECONDS", "GMI_CLOUD_TIMEOUT_SECONDS", "GMICLOUD_TIMEOUT_SECONDS", "LLM_TIMEOUT_SECONDS")
            max_output_names = ("GMI_STREAM_MAX_OUTPUT_TOKENS", "GMI_MAX_TOKENS", "GMI_CLOUD_MAX_TOKENS", "GMICLOUD_MAX_TOKENS", "LLM_MAX_TOKENS")
            temperature_names = ("GMI_STREAM_TEMPERATURE", "GMI_TEMPERATURE", "GMI_CLOUD_TEMPERATURE", "GMICLOUD_TEMPERATURE")
            default_model = DEFAULT_GMI_STREAM_MODEL
            default_base_url = DEFAULT_GMI_BASE_URL
            default_temperature = None
            missing_key_message = "Missing GMI_API_KEY or GMI_CLOUD_API_KEY in .env or process environment."

        api_key = first_env(env, *api_key_names)
        if not api_key:
            raise OpenAIStreamConfigError(missing_key_message)

        resolved_model = model_name_for_provider(
            provider,
            model or first_env(env, *model_names) or default_model,
        )
        resolved_base_url = normalize_base_url(base_url or first_env(env, *base_url_names) or default_base_url)
        resolved_prompt = prompt or DEFAULT_OPENAI_STREAM_PROMPT
        resolved_timeout = timeout_seconds or float_env(
            env,
            DEFAULT_OPENAI_STREAM_TIMEOUT_SECONDS,
            *timeout_names,
        )
        resolved_max_output_tokens = max_output_tokens or int_env(
            env,
            DEFAULT_OPENAI_STREAM_MAX_OUTPUT_TOKENS,
            *max_output_names,
        )
        resolved_temperature = (
            temperature
            if temperature is not None
            else optional_float_env(
                env,
                default_temperature,
                *temperature_names,
            )
        )

        return cls(
            provider_name=provider,
            api_key=api_key,
            model=resolved_model,
            base_url=resolved_base_url,
            prompt=resolved_prompt,
            timeout_seconds=resolved_timeout,
            max_output_tokens=resolved_max_output_tokens,
            instructions=instructions,
            temperature=resolved_temperature,
        )

    def chat_completions_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"

    def headers(self) -> Mapping[str, str]:
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": http_user_agent(),
        }

    def request_payload(self) -> Mapping[str, Any]:
        messages: list[dict[str, str]] = []
        if self.instructions:
            messages.append({"role": "system", "content": self.instructions})
        else:
            messages.append({"role": "system", "content": "You are a concise engineering assistant. Return useful text, not markdown fences."})
        messages.append({"role": "user", "content": self.prompt})

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_output_tokens,
        }
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        return payload


class OpenAIResponsesStreamer:
    def __init__(self, config: OpenAIStreamConfig) -> None:
        self.config = config

    def stream_text(self) -> Iterable[OpenAITextStreamChunk]:
        request = urllib.request.Request(
            url=self.config.response_url(),
            data=json.dumps(self.config.request_payload(), separators=(",", ":")).encode("utf-8"),
            headers=dict(self.config.headers()),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                yield from self._chunks_from_lines(response)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise OpenAIStreamRequestError("POST", self.config.response_url(), exc.code, compact_openai_error(body)) from exc
        except urllib.error.URLError as exc:
            raise OpenAIStreamRequestError("POST", self.config.response_url(), None, str(exc.reason)) from exc
        except TimeoutError as exc:
            raise OpenAIStreamRequestError("POST", self.config.response_url(), None, f"timed out after {self.config.timeout_seconds:.1f}s") from exc

    def _chunks_from_lines(self, response: Any) -> Iterable[OpenAITextStreamChunk]:
        sequence = 0
        for event in iter_sse_events(response):
            chunk = openai_chunk_from_sse(event, sequence=sequence + 1)
            if chunk is None:
                continue
            sequence = chunk.sequence
            yield chunk


class OpenAICompatibleChatCompletionsStreamer:
    def __init__(self, config: OpenAICompatibleChatConfig) -> None:
        self.config = config

    def stream_text(self) -> Iterable[OpenAITextStreamChunk]:
        url = self.config.chat_completions_url()
        request = urllib.request.Request(
            url=url,
            data=json.dumps(self.config.request_payload(), separators=(",", ":")).encode("utf-8"),
            headers=dict(self.config.headers()),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                body = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise OpenAIStreamRequestError("POST", url, exc.code, compact_openai_error(body)) from exc
        except urllib.error.URLError as exc:
            raise OpenAIStreamRequestError("POST", url, None, str(exc.reason)) from exc
        except TimeoutError as exc:
            raise OpenAIStreamRequestError("POST", url, None, f"timed out after {self.config.timeout_seconds:.1f}s") from exc

        yield from chat_completion_chunks(body, provider_name=self.config.provider_name)


class OpenAIStreamEventWriter:
    def __init__(
        self,
        store: JsonlStreamStore,
        *,
        provider_name: str = "openai",
        event_provider_name: str | None = None,
        endpoint_path: str = "responses",
    ) -> None:
        self.store = store
        self.provider_name = normalize_stream_provider_name(provider_name)
        self.event_provider_name = stream_provider_slug(event_provider_name or self.provider_name)
        self.endpoint_path = endpoint_path.strip("/") or "responses"

    def append(
        self,
        chunk: OpenAITextStreamChunk,
        *,
        model: str,
        base_url: str,
        job_id: str | None = None,
        job_index: int | None = None,
        prompt_revision: int | None = None,
    ) -> str:
        self.store.ensure()
        event_id = f"{self.event_provider_name}-{uuid.uuid4().hex}"
        if chunk.error_message:
            status = "failed"
        elif chunk.done:
            status = "completed"
        else:
            status = "delta"
        kind = f"llm.{self.event_provider_name}.{status}"
        payload = {
            "schema_version": 1,
            "event_id": event_id,
            "observed_at_unix_ms": now_ms(),
            "kind": kind,
            "source": {
                "provider": self.provider_name,
                "source_type": "llm.stream",
                "name": model,
                "uri": f"{base_url.rstrip('/')}/{self.endpoint_path}",
            },
            "payload": {
                "model": model,
                "sequence": chunk.sequence,
                "content": chunk.content,
                "done": chunk.done,
                "response_event_type": chunk.response_event_type,
                "response_id": chunk.response_id,
            },
            "metadata": {
                "job_id": job_id,
                "job_index": job_index,
                "openai_response_id": chunk.response_id,
                "provider_response_id": chunk.response_id,
                "prompt_revision": prompt_revision,
                "error_message": chunk.error_message,
            },
        }
        with self.store.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
            handle.flush()
        return event_id


def now_ms() -> int:
    return int(time.time() * 1000)


def iter_sse_events(lines: Iterable[bytes]) -> Iterable[ServerSentEvent]:
    event_name: str | None = None
    data_lines: list[str] = []
    for raw_line in lines:
        line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
        if not line:
            if data_lines:
                yield ServerSentEvent(event=event_name, data="\n".join(data_lines))
            event_name = None
            data_lines = []
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        value = value[1:] if value.startswith(" ") else value
        if field == "event":
            event_name = value
        elif field == "data":
            data_lines.append(value)
    if data_lines:
        yield ServerSentEvent(event=event_name, data="\n".join(data_lines))


def openai_chunk_from_sse(event: ServerSentEvent, *, sequence: int) -> OpenAITextStreamChunk | None:
    if event.data.strip() == "[DONE]":
        return OpenAITextStreamChunk(sequence=sequence, content="", done=True, response_event_type="done")
    try:
        payload = json.loads(event.data)
    except json.JSONDecodeError:
        return OpenAITextStreamChunk(
            sequence=sequence,
            content="",
            done=True,
            response_event_type=event.event or "invalid_json",
            error_message=f"Invalid OpenAI stream JSON: {event.data[:240]}",
        )
    if not isinstance(payload, dict):
        return None

    event_type = str(payload.get("type") or event.event or "")
    response_id = extract_response_id(payload)

    if event_type == "response.output_text.delta":
        return OpenAITextStreamChunk(
            sequence=sequence,
            content=str(payload.get("delta") or ""),
            done=False,
            response_event_type=event_type,
            response_id=response_id,
        )
    if event_type in {"response.completed", "response.incomplete"}:
        return OpenAITextStreamChunk(
            sequence=sequence,
            content="",
            done=True,
            response_event_type=event_type,
            response_id=response_id,
            error_message=incomplete_error_message(payload) if event_type == "response.incomplete" else None,
        )
    if event_type in {"response.failed", "error"}:
        return OpenAITextStreamChunk(
            sequence=sequence,
            content="",
            done=True,
            response_event_type=event_type,
            response_id=response_id,
            error_message=extract_error_message(payload),
        )
    return None


def extract_response_id(payload: Mapping[str, Any]) -> str | None:
    response = payload.get("response")
    if isinstance(response, dict) and response.get("id"):
        return str(response["id"])
    for key in ("response_id", "id"):
        value = payload.get(key)
        if value:
            return str(value)
    return None


def chat_completion_chunks(body: str, *, provider_name: str) -> Iterable[OpenAITextStreamChunk]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise OpenAIStreamRequestError("POST", "chat/completions", None, f"Invalid {provider_name} JSON response: {exc}") from exc
    if not isinstance(payload, dict):
        raise OpenAIStreamRequestError("POST", "chat/completions", None, f"{provider_name} response was not a JSON object.")

    text, finish_reason, response_id = chat_completion_text(payload)
    error_message = None
    if not text.strip():
        error_message = f"{provider_name} response did not include text content."
    elif finish_reason == "length":
        error_message = f"{provider_name} chat completion stopped at max_tokens. Increase the job max_output_tokens value."

    if text:
        yield OpenAITextStreamChunk(
            sequence=1,
            content=text,
            done=False,
            response_event_type="chat.completion.message",
            response_id=response_id,
        )
    yield OpenAITextStreamChunk(
        sequence=2 if text else 1,
        content="",
        done=True,
        response_event_type=f"chat.completion.{finish_reason or 'completed'}",
        response_id=response_id,
        error_message=error_message,
    )


def chat_completion_text(payload: Mapping[str, Any]) -> tuple[str, str | None, str | None]:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return "", None, str(payload.get("id")) if payload.get("id") else None
    first_choice = choices[0] if isinstance(choices[0], dict) else {}
    message = first_choice.get("message") if isinstance(first_choice, dict) else {}
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    text = content if isinstance(content, str) else ""
    finish_reason = first_choice.get("finish_reason") if isinstance(first_choice, dict) else None
    response_id = payload.get("id")
    return text, str(finish_reason) if finish_reason else None, str(response_id) if response_id else None


def extract_error_message(payload: Mapping[str, Any]) -> str:
    error = payload.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if message:
            return str(message)
        return json.dumps(error, sort_keys=True)
    if error:
        return str(error)
    return json.dumps(payload, sort_keys=True)[:1000]


def incomplete_error_message(payload: Mapping[str, Any]) -> str | None:
    response = payload.get("response")
    if isinstance(response, dict):
        incomplete = response.get("incomplete_details")
        if isinstance(incomplete, dict):
            reason = str(incomplete.get("reason") or "unknown")
            if reason == "max_output_tokens":
                return "OpenAI response incomplete: max_output_tokens. Increase --max-output-tokens or the job max_output_tokens value."
            return f"OpenAI response incomplete: {json.dumps(incomplete, sort_keys=True)}"
        if incomplete:
            return f"OpenAI response incomplete: {incomplete}"
    return "OpenAI response incomplete."


def compact_openai_error(body: str) -> str:
    stripped = body.strip()
    if not stripped:
        return "<empty response>"
    if "error code: 1010" in stripped.lower() or "error 1010" in stripped.lower():
        return (
            "provider edge/WAF denied the request with error code 1010. "
            "For GMI Cloud this usually means the request was blocked before model inference; "
            "check API key/model access and contact GMI support if curl with the same key also fails. "
            f"body={stripped[:500]}"
        )
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return stripped[:1000]
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            parts = [error.get("message"), error.get("type"), error.get("code")]
            return " | ".join(str(part) for part in parts if part) or json.dumps(error, sort_keys=True)
    return json.dumps(payload, sort_keys=True)[:1000]


def merged_env(env_file: Path) -> Mapping[str, str]:
    env = dict(os.environ)
    if env_file.exists():
        env.update(load_env_file(env_file))
    return env


def load_env_file(path: Path) -> Mapping[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        if key.strip():
            values[key.strip()] = parse_env_value(raw_value)
    return values


def parse_env_value(raw_value: str) -> str:
    value = strip_inline_comment(raw_value)
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        try:
            return str(ast.literal_eval(value))
        except (SyntaxError, ValueError):
            return value[1:-1]
    return value


def strip_inline_comment(value: str) -> str:
    quote: str | None = None
    escaped = False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote == '"':
            escaped = True
            continue
        if char in {"'", '"'}:
            if quote is None:
                quote = char
            elif quote == char:
                quote = None
            continue
        if char == "#" and quote is None and (index == 0 or value[index - 1].isspace()):
            return value[:index].strip()
    return value.strip()


def first_env(env: Mapping[str, str], *names: str) -> str | None:
    for name in names:
        value = env.get(name)
        if value and value.strip():
            return value.strip()
    return None


def float_env(env: Mapping[str, str], default: float, *names: str) -> float:
    value = first_env(env, *names)
    if not value:
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise OpenAIStreamConfigError(f"{names[0]} must be a number, got {value!r}") from exc


def int_env(env: Mapping[str, str], default: int, *names: str) -> int:
    value = first_env(env, *names)
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise OpenAIStreamConfigError(f"{names[0]} must be an integer, got {value!r}") from exc


def optional_float_env(env: Mapping[str, str], default: float | None, *names: str) -> float | None:
    value = first_env(env, *names)
    if not value:
        return default
    if value.lower() in {"default", "none", "null", "omit"}:
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise OpenAIStreamConfigError(f"{names[0]} must be a number, got {value!r}") from exc


def normalize_base_url(value: str) -> str:
    base_url = value.strip().rstrip("/") or DEFAULT_OPENAI_BASE_URL
    parsed = urllib.parse.urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise OpenAIStreamConfigError(f"OPENAI_BASE_URL must be an absolute URL, got {base_url!r}")
    return base_url


def normalize_stream_provider_name(value: str | None) -> str:
    provider = (value or "openai").strip().lower().replace("_", "-")
    aliases = {
        "base10": "baseten",
        "base-ten": "baseten",
        "baseten-model-apis": "baseten",
        "gmi-cloud": "gmi",
        "gmi_cloud": "gmi",
        "gmicloud": "gmi",
        "gemicloud": "gmi",
        "gmi-serving": "gmi",
    }
    return aliases.get(provider, provider or "openai")


def stream_provider_slug(value: str | None) -> str:
    provider = normalize_stream_provider_name(value)
    return "".join(char if char.isalnum() else "-" for char in provider).strip("-") or "provider"


def model_name_for_provider(provider_name: str | None, model: str | None) -> str:
    resolved_provider = normalize_stream_provider_name(provider_name)
    resolved_model = (model or "").strip()
    prefixes = {f"{resolved_provider}/", f"{stream_provider_slug(resolved_provider)}/"}
    if resolved_provider == "gmi":
        prefixes.update({"gmi-cloud/", "gmicloud/", "gemicloud/", "gmi-serving/"})
    for prefix in prefixes:
        if resolved_model.lower().startswith(prefix.lower()):
            resolved_model = resolved_model[len(prefix) :]
            break
    if resolved_provider == "gmi":
        aliases = {
            "fable": DEFAULT_GMI_STREAM_MODEL,
            "fable-5": DEFAULT_GMI_STREAM_MODEL,
            "claude-fable-5": DEFAULT_GMI_STREAM_MODEL,
        }
        return aliases.get(resolved_model.lower(), resolved_model)
    return resolved_model


__all__ = [
    "DEFAULT_BASETEN_BASE_URL",
    "DEFAULT_BASETEN_STREAM_MODEL",
    "DEFAULT_GMI_BASE_URL",
    "DEFAULT_GMI_STREAM_MODEL",
    "DEFAULT_OPENAI_BASE_URL",
    "DEFAULT_OPENAI_STREAM_MODEL",
    "DEFAULT_OPENAI_STREAM_PROMPT",
    "OpenAICompatibleChatCompletionsStreamer",
    "OpenAICompatibleChatConfig",
    "OpenAIResponsesStreamer",
    "OpenAIStreamConfig",
    "OpenAIStreamConfigError",
    "OpenAIStreamEventWriter",
    "OpenAIStreamRequestError",
    "OpenAITextStreamChunk",
    "ServerSentEvent",
    "chat_completion_chunks",
    "chat_completion_text",
    "iter_sse_events",
    "model_name_for_provider",
    "normalize_stream_provider_name",
    "openai_chunk_from_sse",
]
