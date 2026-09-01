from fastapi import HTTPException, status

from forma_core.config.runtime import (
    HOSTED_CHAT_UNAVAILABLE_MESSAGE,
    HostedChatUnavailableError,
    ensure_hosted_chat_enabled,
)


HOSTED_CHAT_UNAVAILABLE_CODE = "hosted_chat_unavailable"


def require_hosted_chat_enabled() -> None:
    """Reject hosted chat mutations while preserving read-only project access."""
    try:
        ensure_hosted_chat_enabled()
    except HostedChatUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": HOSTED_CHAT_UNAVAILABLE_CODE,
                "message": HOSTED_CHAT_UNAVAILABLE_MESSAGE,
            },
        ) from exc


__all__ = ["HOSTED_CHAT_UNAVAILABLE_CODE", "require_hosted_chat_enabled"]
