import logging

from fastapi import APIRouter, HTTPException, Query

from blueprint_core.logs import backend_log_payload

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/logs/backend")
def backend_logs_endpoint(
    lines: int = Query(250, ge=1, le=1000, description="Number of recent backend log lines to return."),
    max_bytes: int = Query(500_000, ge=4096, le=2_000_000, description="Maximum bytes to scan from the end of the log file."),
):
    """Returns recent backend log lines without exposing raw credentials."""
    try:
        return backend_log_payload(line_limit=lines, byte_limit=max_bytes)
    except Exception as exc:
        logger.exception("Backend log read failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Backend log read failed: {str(exc)}") from exc
