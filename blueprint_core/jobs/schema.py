"""Database schema contract owned by the jobs domain."""

from blueprint_core.persistence.base import TableContract


JOB_TABLE_CONTRACT = TableContract(
    "a2a_jobs",
    (
        "job_id",
        "message_id",
        "correlation_id",
        "action",
        "sender",
        "recipient",
        "status",
        "server_owned",
        "created_at",
        "updated_at",
        "started_at",
        "completed_at",
        "payload_json",
        "result_summary_json",
        "source_usage_json",
        "progress_events_json",
        "error",
        "error_debug_json",
    ),
)
