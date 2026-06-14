import logging
import os
import sys
from typing import Optional


_CONFIGURED = False


def configure_logging(level_name: Optional[str] = None) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    requested_level = (level_name or os.getenv("LOG_LEVEL") or "INFO").strip().upper()
    level = getattr(logging, requested_level, logging.INFO)
    log_format = os.getenv(
        "LOG_FORMAT",
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    log_file = os.getenv("BACKEND_LOG_FILE")
    if log_file:
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=level,
        format=log_format,
        handlers=handlers,
        force=True,
    )
    logging.captureWarnings(True)

    for logger_name in ("backend", "uvicorn.error"):
        logging.getLogger(logger_name).setLevel(level)

    _CONFIGURED = True
    logging.getLogger(__name__).info("Backend logging configured at %s level.", logging.getLevelName(level))
