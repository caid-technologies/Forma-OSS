from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Optional


SUCCESS_STATUSES = {"succeeded", "success", "completed", "complete", "done"}
FAILED_STATUSES = {"failed", "failure", "error"}


def _utc_datetime(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso_hour(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:00:00Z")


def summarize_job_metrics(
    rows: Iterable[Dict[str, Any]],
    *,
    now: Optional[datetime] = None,
    days: int = 7,
    hours: int = 24,
) -> Dict[str, Any]:
    """Aggregate persisted job timestamps into UTC admin dashboard metrics."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    days = max(1, min(int(days), 31))
    hours = max(1, min(int(hours), 168))

    today = current.replace(hour=0, minute=0, second=0, microsecond=0)
    daily_start = today - timedelta(days=days - 1)
    current_hour = current.replace(minute=0, second=0, microsecond=0)
    hourly_start = current_hour - timedelta(hours=hours - 1)
    last_hour_start = current - timedelta(hours=1)

    daily_counts = {
        (daily_start + timedelta(days=index)).date().isoformat(): 0
        for index in range(days)
    }
    hourly_counts = {
        _iso_hour(hourly_start + timedelta(hours=index)): 0
        for index in range(hours)
    }
    failed_jobs = 0
    completed_jobs = 0
    jobs_last_hour = 0

    for row in rows:
        created_at = _utc_datetime(row.get("created_at"))
        if created_at is None or created_at > current:
            continue

        if created_at >= daily_start:
            day_key = created_at.date().isoformat()
            if day_key in daily_counts:
                daily_counts[day_key] += 1
            status = str(row.get("status") or "").strip().lower()
            if status in SUCCESS_STATUSES:
                completed_jobs += 1
            elif status in FAILED_STATUSES:
                completed_jobs += 1
                failed_jobs += 1

        if created_at >= hourly_start:
            hour_key = _iso_hour(created_at.replace(minute=0, second=0, microsecond=0))
            if hour_key in hourly_counts:
                hourly_counts[hour_key] += 1

        if created_at >= last_hour_start:
            jobs_last_hour += 1

    daily = [{"period": period, "count": count} for period, count in daily_counts.items()]
    hourly = [{"period": period, "count": count} for period, count in hourly_counts.items()]
    return {
        "generated_at": current.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "timezone": "UTC",
        "window_days": days,
        "window_hours": hours,
        "total_jobs": sum(daily_counts.values()),
        "jobs_today": daily_counts.get(today.date().isoformat(), 0),
        "jobs_last_hour": jobs_last_hour,
        "completed_jobs": completed_jobs,
        "failed_jobs": failed_jobs,
        "failure_rate": round((failed_jobs / completed_jobs) * 100, 1) if completed_jobs else 0.0,
        "daily": daily,
        "hourly": hourly,
    }


__all__ = ["FAILED_STATUSES", "SUCCESS_STATUSES", "summarize_job_metrics"]
