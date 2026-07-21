from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from blueprint_core.user_integrations import (
    UserIntegrationStore,
    apply_user_integrations_to_environment,
    integration_status_payload,
)
from backend.auth import clerk_user_id, require_deployed_clerk_auth


router = APIRouter(prefix="/user", tags=["user"])


class IntegrationUpdateRequest(BaseModel):
    enabled: Optional[bool] = None
    fields: dict[str, Optional[str]] = Field(default_factory=dict)
    clear_fields: list[str] = Field(default_factory=list)


def _store_for_auth(auth_claims: Any) -> UserIntegrationStore:
    return UserIntegrationStore.for_user(clerk_user_id(auth_claims))


@router.get("/integrations")
def get_user_integrations(auth_claims: Any = Depends(require_deployed_clerk_auth)) -> dict[str, object]:
    return integration_status_payload(_store_for_auth(auth_claims))


@router.post("/integrations/reload")
def reload_user_integrations(auth_claims: Any = Depends(require_deployed_clerk_auth)) -> dict[str, object]:
    store = _store_for_auth(auth_claims)
    apply_user_integrations_to_environment(store)
    return integration_status_payload(store)


@router.put("/integrations/{integration_id}")
def update_user_integration(
    integration_id: str,
    request: IntegrationUpdateRequest,
    auth_claims: Any = Depends(require_deployed_clerk_auth),
) -> dict[str, object]:
    store = _store_for_auth(auth_claims)
    try:
        store.update_integration(
            integration_id,
            enabled=request.enabled,
            field_values=request.fields,
            clear_fields=request.clear_fields,
        )
        apply_user_integrations_to_environment(store)
        return integration_status_payload(store)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/integrations/{integration_id}")
def clear_user_integration(
    integration_id: str,
    auth_claims: Any = Depends(require_deployed_clerk_auth),
) -> dict[str, object]:
    store = _store_for_auth(auth_claims)
    try:
        store.clear_integration(integration_id)
        apply_user_integrations_to_environment(store)
        return integration_status_payload(store)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
