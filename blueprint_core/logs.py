from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional


LOG_SECRET_PATTERNS = [
    re.compile(r"\b(sk-proj-[A-Za-z0-9._-]{12,})"),
    re.compile(r"\b(sk-[A-Za-z0-9._-]{12,})"),
    re.compile(r"\b(sk-lf-[A-Za-z0-9._-]{12,})"),
    re.compile(r"\b(pk-lf-[A-Za-z0-9._-]{12,})"),
    re.compile(r"\b(rpa_[A-Za-z0-9._-]{12,})"),
    re.compile(r"\b(nvapi-[A-Za-z0-9._-]{12,})"),
    re.compile(r"\b(fc-[A-Za-z0-9._-]{12,})"),
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def resolve_backend_log_path(
    *,
    env: Optional[Mapping[str, str]] = None,
    cwd: Optional[Path] = None,
) -> Optional[Path]:
    """Resolve BACKEND_LOG_FILE using the same semantics across API and scripts."""
    values = env if env is not None else os.environ
    raw_path = (values.get("BACKEND_LOG_FILE") or "").strip()
    if not raw_path:
        return None

    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = (cwd or Path.cwd()) / path
    return path.resolve()


def redact_log_line(line: str) -> str:
    redacted = line
    for pattern in LOG_SECRET_PATTERNS:
        redacted = pattern.sub("<redacted>", redacted)
    return redacted


def tail_log_file(path: Path, *, line_limit: int, byte_limit: int) -> dict[str, Any]:
    size_bytes = path.stat().st_size
    with path.open("rb") as handle:
        offset = max(0, size_bytes - byte_limit)
        handle.seek(offset)
        raw_bytes = handle.read(byte_limit)

    text = raw_bytes.decode("utf-8", errors="replace")
    if offset > 0:
        _, _, text = text.partition("\n")

    lines = [redact_log_line(line) for line in text.splitlines()]
    visible_lines = lines[-line_limit:]
    return {
        "size_bytes": size_bytes,
        "truncated": offset > 0 or len(lines) > len(visible_lines),
        "line_count": len(visible_lines),
        "lines": visible_lines,
    }


def backend_log_payload(
    *,
    line_limit: int = 250,
    byte_limit: int = 500_000,
    log_path: Optional[Path] = None,
    env: Optional[Mapping[str, str]] = None,
    cwd: Optional[Path] = None,
) -> dict[str, Any]:
    """Return the frontend/API payload for recent backend logs."""
    path = log_path or resolve_backend_log_path(env=env, cwd=cwd)
    if not path:
        return {
            "enabled": False,
            "configured": False,
            "path": None,
            "lines": [],
            "message": "BACKEND_LOG_FILE is not configured.",
            "updated_at": _utc_now(),
        }

    if not path.exists():
        return {
            "enabled": False,
            "configured": True,
            "path": str(path),
            "lines": [],
            "message": "Backend log file does not exist yet.",
            "updated_at": _utc_now(),
        }

    return {
        "enabled": True,
        "configured": True,
        "path": str(path),
        "updated_at": _utc_now(),
        **tail_log_file(path, line_limit=line_limit, byte_limit=byte_limit),
    }
