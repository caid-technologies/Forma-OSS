from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from blueprint_core.user_integrations import (
    UserIntegrationStore,
    integration_status_payload,
)
from backend.auth import clerk_user_id, require_deployed_clerk_auth
from blueprint_core.debug import api_error_detail, redact_debug_text


router = APIRouter(prefix="/user", tags=["user"])
logger = logging.getLogger(__name__)


class IntegrationUpdateRequest(BaseModel):
    enabled: Optional[bool] = None
    fields: dict[str, Optional[str]] = Field(default_factory=dict)
    clear_fields: list[str] = Field(default_factory=list)


def _store_for_auth(auth_claims: Any) -> UserIntegrationStore:
    return UserIntegrationStore.for_user(clerk_user_id(auth_claims))


def _storage_label(store: UserIntegrationStore) -> str:
    return str(getattr(store, "storage_label", getattr(store, "path", "unknown")))


def _unexpected_storage_error(
    *,
    operation: str,
    store: UserIntegrationStore,
    auth_claims: Any,
    exc: Exception,
    integration_id: Optional[str] = None,
) -> HTTPException:
    owner_user_id = clerk_user_id(auth_claims)
    logger.exception(
        "User integration %s failed: owner_user_id=%s integration_id=%s storage=%s error_type=%s",
        operation,
        owner_user_id,
        integration_id,
        _storage_label(store),
        type(exc).__name__,
    )
    cause = redact_debug_text(str(exc)).strip()
    message = f"Provider settings {operation} failed"
    if cause:
        message = f"{message}: {cause}"
    return HTTPException(
        status_code=500,
        detail=api_error_detail(
            code=f"user_integrations_{operation}_failed",
            message=message,
            exc=exc,
            context={
                "owner_user_id": owner_user_id,
                "integration_id": integration_id,
                "storage": _storage_label(store),
                "operation": operation,
            },
        ),
    )


@router.get("/integrations")
def get_user_integrations(auth_claims: Any = Depends(require_deployed_clerk_auth)) -> dict[str, object]:
    store = _store_for_auth(auth_claims)
    try:
        return integration_status_payload(store)
    except Exception as exc:
        raise _unexpected_storage_error(
            operation="load",
            store=store,
            auth_claims=auth_claims,
            exc=exc,
        ) from exc


@router.post("/integrations/reload")
def reload_user_integrations(auth_claims: Any = Depends(require_deployed_clerk_auth)) -> dict[str, object]:
    store = _store_for_auth(auth_claims)
    try:
        return integration_status_payload(store)
    except Exception as exc:
        raise _unexpected_storage_error(
            operation="reload",
            store=store,
            auth_claims=auth_claims,
            exc=exc,
        ) from exc


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
    except ValueError as exc:
        logger.warning(
            "User integration update rejected: owner_user_id=%s integration_id=%s storage=%s error=%s",
            clerk_user_id(auth_claims),
            integration_id,
            _storage_label(store),
            redact_debug_text(str(exc)),
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError as exc:
        logger.warning(
            "User integration update target not found: owner_user_id=%s integration_id=%s storage=%s error=%s",
            clerk_user_id(auth_claims),
            integration_id,
            _storage_label(store),
            redact_debug_text(str(exc)),
        )
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise _unexpected_storage_error(
            operation="save",
            store=store,
            auth_claims=auth_claims,
            exc=exc,
            integration_id=integration_id,
        ) from exc
    logger.info(
        "User integration update persisted: owner_user_id=%s integration_id=%s storage=%s "
        "enabled=%s field_ids=%s clear_fields=%s",
        clerk_user_id(auth_claims),
        integration_id,
        _storage_label(store),
        request.enabled,
        sorted(request.fields),
        sorted(request.clear_fields),
    )
    try:
        return integration_status_payload(store)
    except Exception as exc:
        raise _unexpected_storage_error(
            operation="post_save_reload",
            store=store,
            auth_claims=auth_claims,
            exc=exc,
            integration_id=integration_id,
        ) from exc


@router.delete("/integrations/{integration_id}")
def clear_user_integration(
    integration_id: str,
    auth_claims: Any = Depends(require_deployed_clerk_auth),
) -> dict[str, object]:
    store = _store_for_auth(auth_claims)
    try:
        store.clear_integration(integration_id)
    except KeyError as exc:
        logger.warning(
            "User integration clear target not found: owner_user_id=%s integration_id=%s storage=%s error=%s",
            clerk_user_id(auth_claims),
            integration_id,
            _storage_label(store),
            redact_debug_text(str(exc)),
        )
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise _unexpected_storage_error(
            operation="clear",
            store=store,
            auth_claims=auth_claims,
            exc=exc,
            integration_id=integration_id,
        ) from exc
    logger.info(
        "User integration clear persisted: owner_user_id=%s integration_id=%s storage=%s",
        clerk_user_id(auth_claims),
        integration_id,
        _storage_label(store),
    )
    try:
        return integration_status_payload(store)
    except Exception as exc:
        raise _unexpected_storage_error(
            operation="post_clear_reload",
            store=store,
            auth_claims=auth_claims,
            exc=exc,
            integration_id=integration_id,
        ) from exc
