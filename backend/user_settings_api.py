from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.auth import UserContext, require_user_context
from blueprint_core.database import get_user_settings, set_user_model_training_preference
from blueprint_core.debug import api_error_detail


router = APIRouter(prefix="/user/settings", tags=["user"])
logger = logging.getLogger(__name__)


class DataUsagePreferenceUpdateRequest(BaseModel):
    allow_model_training: bool


def _owner_user_id(user_context: UserContext) -> str:
    owner_user_id = str(user_context.owner_user_id or "").strip()
    if not owner_user_id:
        raise HTTPException(status_code=401, detail="Sign in to manage data usage preferences.")
    return owner_user_id


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _data_usage_payload(settings: Any | None) -> dict[str, object]:
    opted_out = bool(getattr(settings, "model_training_opt_out", False))
    return {
        "allow_model_training": not opted_out,
        "model_training_opt_out": opted_out,
        "source": "user" if settings is not None else "default",
        "created_at": getattr(settings, "created_at", None),
        "updated_at": getattr(settings, "updated_at", None),
    }


def _settings_error(operation: str, owner_user_id: str, exc: Exception) -> HTTPException:
    logger.exception(
        "User data usage preference %s failed: owner_user_id=%s error_type=%s",
        operation,
        owner_user_id,
        type(exc).__name__,
    )
    return HTTPException(
        status_code=500,
        detail=api_error_detail(
            code=f"user_data_usage_{operation}_failed",
            message=f"Data usage preference {operation} failed.",
            exc=exc,
            context={"owner_user_id": owner_user_id, "operation": operation},
        ),
    )


@router.get("/data-usage")
def get_data_usage_preference(
    user_context: UserContext = Depends(require_user_context),
) -> dict[str, object]:
    owner_user_id = _owner_user_id(user_context)
    try:
        return _data_usage_payload(get_user_settings(owner_user_id))
    except Exception as exc:
        raise _settings_error("load", owner_user_id, exc) from exc


@router.put("/data-usage")
def update_data_usage_preference(
    request: DataUsagePreferenceUpdateRequest,
    user_context: UserContext = Depends(require_user_context),
) -> dict[str, object]:
    owner_user_id = _owner_user_id(user_context)
    try:
        settings = set_user_model_training_preference(
            owner_user_id,
            allow_model_training=request.allow_model_training,
            updated_at=_timestamp(),
        )
    except Exception as exc:
        raise _settings_error("save", owner_user_id, exc) from exc
    logger.info(
        "User data usage preference saved: owner_user_id=%s model_training_opt_out=%s",
        owner_user_id,
        not request.allow_model_training,
    )
    return _data_usage_payload(settings)
