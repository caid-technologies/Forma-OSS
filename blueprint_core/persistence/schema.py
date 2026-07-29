from __future__ import annotations

from typing import Tuple

from blueprint_core.jobs.schema import JOB_TABLE_CONTRACT
from blueprint_core.persistence.base import TableContract

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
    JOB_TABLE_CONTRACT,
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
    TableContract(
        "user_settings",
        ("id", "owner_user_id", "model_training_opt_out", "created_at", "updated_at"),
    ),
)
