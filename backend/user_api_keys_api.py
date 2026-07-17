from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.auth import require_deployed_user_id
from blueprint_core.api_keys import (
    DEFAULT_API_KEY_SCOPES,
    DEFAULT_DAILY_QUOTA,
    DEFAULT_RATE_LIMIT_PER_MINUTE,
    api_key_hash_algorithm,
    api_key_public_payload,
    api_key_pepper,
    managed_api_key_pepper_required,
    normalize_api_key_scopes,
)
from blueprint_core.database import create_user_api_key, list_user_api_keys, revoke_user_api_key


router = APIRouter(prefix="/user/api-keys", tags=["user-api-keys"])


class ApiKeyCreateRequest(BaseModel):
    name: str = Field("Untitled API key", min_length=1, max_length=80)
    scopes: list[str] = Field(default_factory=lambda: list(DEFAULT_API_KEY_SCOPES))
    rate_limit_per_minute: int = Field(DEFAULT_RATE_LIMIT_PER_MINUTE, ge=1, le=600)
    daily_quota: int = Field(DEFAULT_DAILY_QUOTA, ge=1, le=100000)
    expires_at: Optional[str] = None


def _payload(owner_user_id: str, *, created: Optional[Any] = None, secret: Optional[str] = None) -> dict[str, Any]:
    keys = [api_key_public_payload(record) for record in list_user_api_keys(owner_user_id)]
    response: dict[str, Any] = {
        "owner_user_id": owner_user_id,
        "defaults": {
            "scopes": list(DEFAULT_API_KEY_SCOPES),
            "rate_limit_per_minute": DEFAULT_RATE_LIMIT_PER_MINUTE,
            "daily_quota": DEFAULT_DAILY_QUOTA,
        },
        "keys": keys,
        "storage": {
            "secret_visibility": "one_time",
            "stored_secret": api_key_hash_algorithm(),
            "pepper_required": managed_api_key_pepper_required(),
            "pepper_configured": bool(api_key_pepper()),
            "encryption_note": "Generated API keys are not decryptable; production keys require BLUEPRINT_API_KEY_PEPPER and are rotated by creating a new key and revoking the old one.",
        },
    }
    if created is not None:
        response["created_key"] = api_key_public_payload(created, include_secret=secret)
    return response


@router.get("")
def list_api_keys_endpoint(owner_user_id: str = Depends(require_deployed_user_id)) -> dict[str, Any]:
    return _payload(owner_user_id)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_api_key_endpoint(
    request: ApiKeyCreateRequest,
    owner_user_id: str = Depends(require_deployed_user_id),
) -> dict[str, Any]:
    record, secret = create_user_api_key(
        owner_user_id=owner_user_id,
        name=request.name,
        scopes=normalize_api_key_scopes(request.scopes),
        rate_limit_per_minute=request.rate_limit_per_minute,
        daily_quota=request.daily_quota,
        expires_at=request.expires_at,
    )
    return _payload(owner_user_id, created=record, secret=secret)


@router.delete("/{key_id}")
def revoke_api_key_endpoint(
    key_id: str,
    owner_user_id: str = Depends(require_deployed_user_id),
) -> dict[str, Any]:
    if not revoke_user_api_key(owner_user_id, key_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found.")
    return _payload(owner_user_id)
