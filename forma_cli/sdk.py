"""Typed, dependency-light Forma API client used by the CLI."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field

from forma_cli.config import api_url
from forma_cli.credentials import CredentialStore, SESSION_KEY


class FormaAPIError(RuntimeError):
    """An HTTP or transport failure returned by the Forma API."""

    def __init__(self, message: str, *, status_code: int | None = None, detail: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class TokenSet(BaseModel):
    model_config = ConfigDict(extra="ignore")

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = Field(default=3600, ge=1)


class DeviceAuthorization(BaseModel):
    model_config = ConfigDict(extra="ignore")

    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int = Field(ge=1)
    interval: int = Field(default=5, ge=1)


class DevicePollResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: str
    message: str | None = None


class AccountIdentity(BaseModel):
    model_config = ConfigDict(extra="allow")

    subject: str
    provider: str
    email: str | None = None
    display_name: str | None = None
    api_url: str


class CloudProjectSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    project_id: str
    workspace_id: str | None = None
    title: str = ""
    revision_id: str | None = None
    revision: int | None = None
    parent_revision_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class CloudProjectRevision(BaseModel):
    model_config = ConfigDict(extra="allow")

    revision_id: str
    project_id: str
    revision: int
    parent_revision_id: str | None = None
    manifest: dict[str, Any]
    created_at: str | None = None


class ManagedCredentialMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider: str
    credential_id: str | None = None
    label: str | None = None
    masked_value: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    configured: bool = False


@dataclass
class FormaAPIClient:
    """Call Forma endpoints without importing backend handlers or Supabase."""

    base_url: str | None = None
    credential_store: CredentialStore | None = None
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        self.base_url = (self.base_url or api_url()).rstrip("/")
        self.credential_store = self.credential_store or CredentialStore()

    @property
    def _store(self) -> CredentialStore:
        assert self.credential_store is not None
        return self.credential_store

    def _saved_tokens(self) -> TokenSet | None:
        payload = self._store.get_json(SESSION_KEY)
        return TokenSet.model_validate(payload) if payload else None

    def _save_tokens(self, tokens: TokenSet) -> TokenSet:
        self._store.set_json(SESSION_KEY, tokens.model_dump(mode="json"))
        return tokens

    def _request(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: Mapping[str, Any] | None = None,
        authenticated: bool = False,
        retry_refresh: bool = True,
    ) -> Any:
        headers = {
            "Accept": "application/json",
            "User-Agent": "forma-oss-cli/0.1",
        }
        tokens = self._saved_tokens() if authenticated else None
        if authenticated:
            if tokens is None:
                raise FormaAPIError("Sign in with `forma-oss login` before using cloud commands.")
            headers["Authorization"] = f"{tokens.token_type} {tokens.access_token}"
        body = json.dumps(dict(payload)).encode("utf-8") if payload is not None else None
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = Request(f"{self.base_url}/{path.lstrip('/')}", data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
        except HTTPError as exc:
            raw = exc.read()
            detail = self._decode_json(raw)
            if exc.code == 401 and authenticated and retry_refresh and tokens and tokens.refresh_token:
                try:
                    self.refresh(tokens.refresh_token)
                except FormaAPIError:
                    pass
                else:
                    return self._request(
                        path,
                        method=method,
                        payload=payload,
                        authenticated=authenticated,
                        retry_refresh=False,
                    )
            raise FormaAPIError(
                self._error_message(detail, fallback=f"Forma API request failed ({exc.code})."),
                status_code=exc.code,
                detail=detail,
            ) from exc
        except URLError as exc:
            raise FormaAPIError(f"Could not reach Forma API at {self.base_url}: {exc.reason}") from exc
        except OSError as exc:
            raise FormaAPIError(f"Could not reach Forma API at {self.base_url}: {exc}") from exc
        return self._decode_json(raw)

    @staticmethod
    def _decode_json(raw: bytes) -> Any:
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise FormaAPIError("Forma API returned an invalid JSON response.") from exc

    @staticmethod
    def _error_message(detail: Any, *, fallback: str) -> str:
        if isinstance(detail, dict):
            message = detail.get("message") or detail.get("detail")
            if isinstance(message, str) and message.strip():
                return message.strip()
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
        return fallback

    def request_device_authorization(self) -> DeviceAuthorization:
        return DeviceAuthorization.model_validate(
            self._request("/cli/device/authorize", method="POST", payload={"client_name": "forma-oss"})
        )

    def poll_device_authorization(self, device_code: str) -> DevicePollResult:
        return DevicePollResult.model_validate(
            self._request("/cli/device/poll", method="POST", payload={"device_code": device_code})
        )

    def exchange_device_code(self, device_code: str) -> TokenSet:
        return self._save_tokens(
            TokenSet.model_validate(
                self._request("/cli/device/token", method="POST", payload={"device_code": device_code})
            )
        )

    def refresh(self, refresh_token: str | None = None) -> TokenSet:
        token = refresh_token or (self._saved_tokens().refresh_token if self._saved_tokens() else "")
        if not token:
            raise FormaAPIError("No refresh token is available; sign in again.")
        return self._save_tokens(
            TokenSet.model_validate(
                self._request("/cli/token/refresh", method="POST", payload={"refresh_token": token})
            )
        )

    def revoke(self) -> None:
        tokens = self._saved_tokens()
        if tokens:
            try:
                self._request(
                    "/cli/token/revoke",
                    method="POST",
                    payload={"refresh_token": tokens.refresh_token},
                    authenticated=True,
                    retry_refresh=False,
                )
            finally:
                self._store.delete(SESSION_KEY)

    def whoami(self) -> AccountIdentity:
        return AccountIdentity.model_validate(self._request("/cli/whoami", authenticated=True))

    def list_projects(self) -> list[CloudProjectSummary]:
        payload = self._request("/cli/projects", authenticated=True)
        items = payload.get("items", payload) if isinstance(payload, dict) else payload
        return [CloudProjectSummary.model_validate(item) for item in items or []]

    def push_project(
        self,
        manifest: Mapping[str, Any],
        *,
        parent_revision_id: str | None = None,
    ) -> CloudProjectRevision:
        payload = self._request(
            "/cli/projects/push",
            method="POST",
            payload={"manifest": dict(manifest), "parent_revision_id": parent_revision_id},
            authenticated=True,
        )
        return CloudProjectRevision.model_validate(payload)

    def pull_project(self, project_id: str, revision_id: str | None = None) -> CloudProjectRevision:
        path = f"/cli/projects/{quote(project_id, safe='')}"
        if revision_id:
            path += f"/revisions/{quote(revision_id, safe='')}"
        payload = self._request(path, authenticated=True)
        return CloudProjectRevision.model_validate(payload)

    def list_keys(self) -> list[ManagedCredentialMetadata]:
        payload = self._request("/cli/credentials", authenticated=True)
        items = payload.get("items", payload) if isinstance(payload, dict) else payload
        return [ManagedCredentialMetadata.model_validate(item) for item in items or []]

    def set_key(self, provider: str, value: str, *, label: str | None = None) -> ManagedCredentialMetadata:
        payload = self._request(
            "/cli/credentials",
            method="POST",
            payload={"provider": provider, "value": value, "label": label},
            authenticated=True,
        )
        return ManagedCredentialMetadata.model_validate(payload)

    def remove_key(self, provider: str) -> None:
        self._request(f"/cli/credentials/{quote(provider, safe='')}", method="DELETE", authenticated=True)


__all__ = [
    "AccountIdentity",
    "CloudProjectRevision",
    "CloudProjectSummary",
    "DeviceAuthorization",
    "DevicePollResult",
    "FormaAPIClient",
    "FormaAPIError",
    "ManagedCredentialMetadata",
    "TokenSet",
]
