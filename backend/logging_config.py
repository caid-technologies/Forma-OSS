import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, Tuple

from blueprint_core.debug import debug_mode_enabled
from blueprint_core.logs import resolve_backend_log_path


DEFAULT_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
DEFAULT_LOG_MAX_BYTES = 10_000_000
DEFAULT_LOG_BACKUP_COUNT = 5


class _LoggerNamespaceFilter(logging.Filter):
    def __init__(self, namespaces: Tuple[str, ...]) -> None:
        super().__init__()
        self.namespaces = namespaces

    def filter(self, record: logging.LogRecord) -> bool:
        if not self.namespaces:
            return True
        logger_name = record.name or ""
        return any(logger_name == namespace or logger_name.startswith(f"{namespace}.") for namespace in self.namespaces)


def _log_level(value: Optional[str]) -> int:
    if not value:
        return logging.INFO
    normalized = value.strip().upper()
    return getattr(logging, normalized, logging.INFO)


def _env_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        return int(raw_value)
    except ValueError:
        return default


def _log_namespaces() -> Tuple[str, ...]:
    raw_value = os.getenv("BACKEND_LOG_NAMESPACES") or os.getenv("BLUEPRINT_LOG_NAMESPACES") or ""
    if not raw_value.strip():
        return ()
    namespaces = []
    for namespace in re.split(r"[,\s]+", raw_value.strip()):
        normalized = namespace.strip().rstrip(".")
        if normalized and normalized != "*":
            namespaces.append(normalized)
    return tuple(dict.fromkeys(namespaces))


def _ensure_namespace_filter(handler: logging.Handler, namespaces: Tuple[str, ...]) -> None:
    if not namespaces:
        return
    if getattr(handler, "_blueprint_log_namespaces", None) == namespaces:
        return
    handler.addFilter(_LoggerNamespaceFilter(namespaces))
    handler._blueprint_log_namespaces = namespaces  # type: ignore[attr-defined]


def _handler_for_path(logger: logging.Logger, path: Path) -> Optional[logging.Handler]:
    target = str(path)
    for handler in logger.handlers:
        if getattr(handler, "_blueprint_log_file", None) == target:
            return handler
    return None


def _build_file_handler(
    path: Path,
    level: int,
    formatter: logging.Formatter,
    namespaces: Tuple[str, ...],
) -> RotatingFileHandler:
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        path,
        maxBytes=_env_int("BACKEND_LOG_MAX_BYTES", DEFAULT_LOG_MAX_BYTES),
        backupCount=_env_int("BACKEND_LOG_BACKUP_COUNT", DEFAULT_LOG_BACKUP_COUNT),
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(formatter)
    _ensure_namespace_filter(handler, namespaces)
    handler._blueprint_log_file = str(path)  # type: ignore[attr-defined]
    return handler


def _ensure_console_handler(
    root_logger: logging.Logger,
    level: int,
    formatter: logging.Formatter,
    namespaces: Tuple[str, ...],
) -> None:
    if root_logger.handlers:
        for handler in root_logger.handlers:
            handler.setLevel(min(handler.level or level, level))
            _ensure_namespace_filter(handler, namespaces)
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(formatter)
    _ensure_namespace_filter(handler, namespaces)
    root_logger.addHandler(handler)


def configure_backend_logging() -> None:
    """Configure Blueprint backend logging for console and optional file output."""
    level = _log_level(os.getenv("LOG_LEVEL") or ("DEBUG" if debug_mode_enabled() else None))
    formatter = logging.Formatter(os.getenv("BACKEND_LOG_FORMAT", DEFAULT_LOG_FORMAT))
    namespaces = _log_namespaces()
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    _ensure_console_handler(root_logger, level, formatter, namespaces)

    log_path = resolve_backend_log_path()
    if log_path is None:
        return

    # Uvicorn child loggers do not consistently propagate to root under uvicorn's
    # own logging config. Attach directly to the child loggers, but not to the
    # parent "uvicorn" logger; otherwise startup lines can be duplicated.
    uvicorn_error_logger = logging.getLogger("uvicorn.error")
    uvicorn_access_logger = logging.getLogger("uvicorn.access")
    uvicorn_error_logger.propagate = False
    uvicorn_access_logger.propagate = False
    target_loggers = [
        root_logger,
        uvicorn_error_logger,
        uvicorn_access_logger,
    ]
    for logger in target_loggers:
        logger.setLevel(level)
        if _handler_for_path(logger, log_path) is None:
            logger.addHandler(_build_file_handler(log_path, level, formatter, namespaces))

    logging.getLogger(__name__).info(
        "Backend logging configured; file=%s level=%s namespaces=%s",
        log_path,
        logging.getLevelName(level),
        ",".join(namespaces) if namespaces else "*",
    )
