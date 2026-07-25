from __future__ import annotations

import json
import logging
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine, make_url

from blueprint_core.job_source_usage import infer_source_usage


logger = logging.getLogger(__name__)
DEFAULT_LEGACY_JOB_DB_PATH = "./blueprint_jobs.db"


def _json_loads(value: Optional[str]) -> Any:
    if value is None or not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _json_dumps(value: Any) -> str:
    return json.dumps(value, default=str, separators=(",", ":"))


def legacy_job_database_path() -> str:
    return os.getenv("JOB_METADATA_DB_PATH", DEFAULT_LEGACY_JOB_DB_PATH)


def migrate_sqlite_schema(engine: Engine, *, import_legacy_jobs: bool = True) -> None:
    """Upgrade the complete local schema owned by the primary database."""

    with engine.begin() as connection:
        project_columns = {
            row[1]
            for row in connection.exec_driver_sql("PRAGMA table_info(generated_projects)").fetchall()
        }
        if "chat_id" not in project_columns:
            connection.execute(text("ALTER TABLE generated_projects ADD COLUMN chat_id VARCHAR"))
        if "owner_user_id" not in project_columns:
            connection.execute(text("ALTER TABLE generated_projects ADD COLUMN owner_user_id VARCHAR"))
        if "visibility" not in project_columns:
            connection.execute(
                text("ALTER TABLE generated_projects ADD COLUMN visibility VARCHAR NOT NULL DEFAULT 'public'")
            )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_generated_projects_chat_id ON generated_projects (chat_id)")
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_generated_projects_owner_user_id ON generated_projects (owner_user_id)")
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_generated_projects_visibility ON generated_projects (visibility)")
        )

        job_columns = {
            row[1]
            for row in connection.exec_driver_sql("PRAGMA table_info(a2a_jobs)").fetchall()
        }
        for column in ("source_usage_json", "error_debug_json", "progress_events_json"):
            if column not in job_columns:
                connection.execute(text(f"ALTER TABLE a2a_jobs ADD COLUMN {column} TEXT"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_a2a_jobs_sender ON a2a_jobs (sender)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_a2a_jobs_status ON a2a_jobs (status)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_a2a_jobs_created_at ON a2a_jobs (created_at)"))

    if import_legacy_jobs:
        import_legacy_job_database(engine, legacy_job_database_path())

    with engine.begin() as connection:
        rows = connection.exec_driver_sql(
            """
            SELECT job_id, action, payload_json, result_summary_json, source_usage_json
            FROM a2a_jobs
            WHERE source_usage_json IS NULL OR source_usage_json = ''
            """
        ).fetchall()
        for row in rows:
            source_usage = infer_source_usage(
                action=row[1],
                payload=_json_loads(row[2]) or {},
                result_summary=_json_loads(row[3]) or {},
            )
            if source_usage:
                connection.exec_driver_sql(
                    "UPDATE a2a_jobs SET source_usage_json = ? WHERE job_id = ?",
                    (_json_dumps(source_usage), row[0]),
                )


def import_legacy_job_database(engine: Engine, legacy_path: Optional[str]) -> int:
    """Copy jobs from the retired standalone SQLite file without overwriting rows."""

    target_database = make_url(str(engine.url)).database
    if not legacy_path or target_database in {None, "", ":memory:"}:
        return 0

    source_path = Path(legacy_path).expanduser().resolve()
    target_path = Path(target_database).expanduser().resolve()
    if source_path == target_path or not source_path.is_file():
        return 0

    with closing(sqlite3.connect(str(source_path))) as source:
        table_exists = source.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'a2a_jobs'"
        ).fetchone()
        if not table_exists:
            return 0
        source_columns = {row[1] for row in source.execute("PRAGMA table_info(a2a_jobs)").fetchall()}
        target_columns = {
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
        }
        columns = [column for column in target_columns if column in source_columns]
        required = {
            "job_id",
            "message_id",
            "action",
            "sender",
            "recipient",
            "status",
            "server_owned",
            "created_at",
            "updated_at",
        }
        if not required.issubset(columns):
            logger.warning("Skipping legacy job import from %s because required columns are missing.", source_path)
            return 0
        ordered_columns = sorted(columns)
        quoted_columns = ", ".join(f'"{column}"' for column in ordered_columns)
        placeholders = ", ".join("?" for _ in ordered_columns)
        source_rows = source.execute(f"SELECT {quoted_columns} FROM a2a_jobs").fetchall()

    if not source_rows:
        return 0

    target = engine.raw_connection()
    try:
        before = target.total_changes
        target.executemany(
            f"INSERT OR IGNORE INTO a2a_jobs ({quoted_columns}) VALUES ({placeholders})",
            source_rows,
        )
        target.commit()
        imported = target.total_changes - before
    except Exception:
        target.rollback()
        raise
    finally:
        target.close()

    if imported:
        logger.info(
            "Imported %s legacy A2A job rows from %s into the primary SQLite database. "
            "The legacy file was retained.",
            imported,
            source_path,
        )
    return imported
