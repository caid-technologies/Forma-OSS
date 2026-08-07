from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

from blueprint_core.jobs.migrations import migrate_job_schema


def migrate_sqlite_schema(engine: Engine, *, import_legacy_jobs: bool = True) -> None:
    """Upgrade the local application schema and delegate job-owned migrations."""

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
        if "status" not in project_columns:
            connection.execute(
                text("ALTER TABLE generated_projects ADD COLUMN status VARCHAR NOT NULL DEFAULT 'active'")
            )
        for column, column_type in (
            ("deleted_at", "VARCHAR"),
            ("deletion_requested_by", "VARCHAR"),
            ("purge_after", "VARCHAR"),
            ("purge_started_at", "VARCHAR"),
            ("purge_completed_at", "VARCHAR"),
            ("deletion_error", "TEXT"),
        ):
            if column not in project_columns:
                connection.execute(text(f"ALTER TABLE generated_projects ADD COLUMN {column} {column_type}"))
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_generated_projects_chat_id ON generated_projects (chat_id)")
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_generated_projects_owner_user_id ON generated_projects (owner_user_id)")
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_generated_projects_visibility ON generated_projects (visibility)")
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_generated_projects_status ON generated_projects (status)")
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_generated_projects_purge_after ON generated_projects (purge_after)")
        )

    migrate_job_schema(engine, import_legacy_jobs=import_legacy_jobs)
