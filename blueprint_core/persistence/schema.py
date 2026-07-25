from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class TableContract:
    name: str
    required_columns: Tuple[str, ...]

    @property
    def projection(self) -> str:
        return ",".join(self.required_columns)


# This is the schema surface used through both the local SQLite provider and
# the hosted Supabase provider. A Supabase startup projection checks columns as
# well as table visibility, so schema drift fails at startup rather than during
# an unrelated request.
APPLICATION_SCHEMA: Tuple[TableContract, ...] = (
    TableContract(
        "component_templates",
        ("id", "part_number", "name", "category", "description", "price", "sourcing_url", "pins", "use_cases"),
    ),
    TableContract(
        "generated_projects",
        ("id", "project_id", "chat_id", "owner_user_id", "visibility", "title", "prompt", "hardware_ir", "created_at"),
    ),
    TableContract(
        "project_chats",
        ("id", "chat_id", "owner_user_id", "title", "messages", "created_at", "updated_at"),
    ),
    TableContract(
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
    ),
    TableContract(
        "alpha_signups",
        ("id", "name", "email", "organization", "additional_info", "source", "metadata_json", "created_at"),
    ),
    TableContract(
        "user_integration_configs",
        ("owner_user_id", "encrypted_config", "encryption_key_id", "version", "created_at", "updated_at"),
    ),
    TableContract(
        "workspace_integration_configs",
        ("config_key", "encrypted_config", "encryption_key_id", "version", "created_at", "updated_at"),
    ),
)
