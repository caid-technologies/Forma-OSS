from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from blueprint_core.user_integrations import (
    UserIntegrationStore,
    apply_user_integrations_to_environment,
    integration_status_payload,
    user_integrations_file_store_allowed,
)


router = APIRouter(prefix="/user", tags=["user"])


class IntegrationUpdateRequest(BaseModel):
    enabled: Optional[bool] = None
    fields: dict[str, Optional[str]] = Field(default_factory=dict)
    clear_fields: list[str] = Field(default_factory=list)


def _require_writable_integration_store() -> None:
    if not user_integrations_file_store_allowed():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Writable provider integrations are disabled in deployed environments. "
                "Configure provider credentials through deployment secrets or enable "
                "BLUEPRINT_ALLOW_DEPLOYED_USER_INTEGRATIONS only with a real encrypted vault."
            ),
        )


@router.get("/integrations")
def get_user_integrations() -> dict[str, object]:
    return integration_status_payload()


@router.post("/integrations/reload")
def reload_user_integrations() -> dict[str, object]:
    _require_writable_integration_store()
    apply_user_integrations_to_environment()
    return integration_status_payload()


@router.put("/integrations/{integration_id}")
def update_user_integration(integration_id: str, request: IntegrationUpdateRequest) -> dict[str, object]:
    _require_writable_integration_store()
    store = UserIntegrationStore()
    try:
        store.update_integration(
            integration_id,
            enabled=request.enabled,
            field_values=request.fields,
            clear_fields=request.clear_fields,
        )
        apply_user_integrations_to_environment(store)
        return integration_status_payload(store)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/integrations/{integration_id}")
def clear_user_integration(integration_id: str) -> dict[str, object]:
    _require_writable_integration_store()
    store = UserIntegrationStore()
    try:
        store.clear_integration(integration_id)
        apply_user_integrations_to_environment(store)
        return integration_status_payload(store)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
