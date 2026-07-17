from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.auth import require_deployed_user_id
from blueprint_core.database import get_user_settings, upsert_user_settings, user_settings_public_payload


router = APIRouter(prefix="/user/settings", tags=["user-settings"])


class UserSettingsUpdateRequest(BaseModel):
    model_training_opt_out: bool | None = None


@router.get("")
def get_user_settings_endpoint(owner_user_id: str = Depends(require_deployed_user_id)) -> dict[str, object]:
    return user_settings_public_payload(get_user_settings(owner_user_id))


@router.put("")
def update_user_settings_endpoint(
    request: UserSettingsUpdateRequest,
    owner_user_id: str = Depends(require_deployed_user_id),
) -> dict[str, object]:
    settings = upsert_user_settings(
        owner_user_id,
        model_training_opt_out=request.model_training_opt_out,
    )
    return user_settings_public_payload(settings)

