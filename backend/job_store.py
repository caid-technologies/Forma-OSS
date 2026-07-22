import json
import logging
import os
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from blueprint_core.job_source_usage import infer_source_usage
from blueprint_core.pipeline import PipelineCancelledError
from blueprint_core.runtime import blueprint_dev_mode_enabled

load_dotenv()

DEFAULT_JOB_DB_PATH = "./blueprint_jobs.db"
OPTIONAL_SUPABASE_COLUMNS = {"source_usage_json", "error_debug_json", "progress_events_json"}
logger = logging.getLogger(__name__)


class JobCancelledError(PipelineCancelledError):
    """Raised inside a worker when its persisted job was cancelled."""


TERMINAL_JOB_STATUSES = {"succeeded", "failed", "cancelled", "canceled"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _job_db_path() -> str:
    return os.getenv("JOB_METADATA_DB_PATH", DEFAULT_JOB_DB_PATH)


def _job_metadata_backend() -> str:
    if blueprint_dev_mode_enabled():
        return "sqlite"
    value = os.getenv("JOB_METADATA_BACKEND", "auto").strip().lower()
    if value in {"auto", "supabase", "database", "db"}:
        return "supabase" if value != "auto" else "auto"
    if value in {"sqlite", "sqlite3"}:
        return "sqlite"
    return "auto"


def _json_default(value: Any) -> str:
    return str(value)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, default=_json_default, separators=(",", ":"))


def _json_loads(value: Optional[str]) -> Any:
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _redact_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    redacted = dict(payload or {})
    if redacted.get("image_data"):
        redacted["image_data"] = "<redacted>"
        redacted["image_data_present"] = True
    return redacted


def _operation_summary(operations: List[Dict[str, Any]]) -> Dict[str, Any]:
    failed = sum(1 for operation in operations if operation.get("status") == "failed")
    succeeded = sum(1 for operation in operations if operation.get("status") == "succeeded")
    pending = sum(1 for operation in operations if operation.get("status") == "pending")
    not_requested = sum(1 for operation in operations if operation.get("status") == "not_requested")
    return {
        "total": len(operations),
        "failed": failed,
        "succeeded": succeeded,
        "pending": pending,
        "not_requested": not_requested,
        "ok": failed == 0,
    }


def _result_operation_statuses(project_ir: Dict[str, Any], metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_operations = metadata.get("operation_statuses")
    operations = [item for item in raw_operations if isinstance(item, dict)] if isinstance(raw_operations, list) else []
    operation_ids = {str(item.get("id") or "") for item in operations}
    if "hardware_generation" not in operation_ids:
        validation = project_ir.get("validation") or {}
        operations.insert(
            0,
            {
                "id": "hardware_generation",
                "label": "Hardware generation",
                "status": "succeeded",
                "provider": metadata.get("runtime_provider") or metadata.get("llm_provider"),
                "model": metadata.get("runtime_model") or metadata.get("model_name"),
                "details": {
                    "is_valid": project_ir.get("is_valid"),
                    "component_count": len(project_ir.get("components") or []),
                    "net_count": len(project_ir.get("nets") or []),
                    "critical_issue_count": len(validation.get("critical") or []),
                    "warning_issue_count": len(validation.get("warning") or []),
                },
            },
        )
    return operations


def summarize_result(result: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not result:
        return None

    project_ir = result.get("project_ir") if isinstance(result, dict) else None
    if not isinstance(project_ir, dict):
        return {"result_keys": sorted(result.keys()) if isinstance(result, dict) else []}

    overview = project_ir.get("overview") or {}
    metadata = project_ir.get("assembly_metadata") or {}
    validation = project_ir.get("validation") or {}
    source_usage = infer_source_usage(result=result)
    operation_statuses = _result_operation_statuses(project_ir, metadata)

    return {
        "project_id": metadata.get("project_id"),
        "chat_id": metadata.get("chat_id"),
        "source_project_id": metadata.get("source_project_id"),
        "title": overview.get("title"),
        "category": overview.get("category"),
        "estimated_cost": overview.get("estimated_cost"),
        "is_valid": project_ir.get("is_valid"),
        "component_count": len(project_ir.get("components") or []),
        "net_count": len(project_ir.get("nets") or []),
        "critical_issue_count": len(validation.get("critical") or []),
        "warning_issue_count": len(validation.get("warning") or []),
        "llm_provider": metadata.get("llm_provider"),
        "model_name": metadata.get("model_name"),
        "has_product_image": bool(metadata.get("product_image_data") or metadata.get("product_image_url")),
        "image_output_requested": metadata.get("image_output_requested"),
        "image_output_enabled": metadata.get("image_output_enabled"),
        "image_output_configured": metadata.get("image_output_configured"),
        "image_output_status": metadata.get("image_output_status"),
        "image_output_failed": metadata.get("image_output_failed"),
        "image_output_error": metadata.get("image_output_error") or metadata.get("product_image_error"),
        "image_output_error_type": metadata.get("image_output_error_type"),
        "image_output_reason": metadata.get("image_output_reason"),
        "image_output_debug": metadata.get("image_output_debug"),
        "image_output_generated_count": metadata.get("image_output_generated_count"),
        "product_image_provider": metadata.get("product_image_provider") or metadata.get("image_output_provider"),
        "product_image_model": metadata.get("product_image_model") or metadata.get("image_output_model"),
        "product_image_error": metadata.get("product_image_error"),
        "product_image_storage_error": metadata.get("product_image_storage_error") or metadata.get("product_case_image_storage_error"),
        "operation_statuses": operation_statuses,
        "operation_summary": _operation_summary(operation_statuses),
        "workflow": metadata.get("workflow"),
        "source_usage": source_usage,
        "pipeline": metadata.get("pipeline"),
    }


class JobMetadataStore:
    """Durable A2A job metadata store using Supabase client or SQLite."""

    def __init__(self, db_path: Optional[str] = None, backend: Optional[str] = None) -> None:
        self.db_path = db_path or _job_db_path()
        requested_backend = (backend or _job_metadata_backend()).strip().lower()
        if blueprint_dev_mode_enabled() or db_path is not None:
            requested_backend = "sqlite"
        self.requested_backend = requested_backend if requested_backend in {"auto", "supabase", "sqlite"} else "auto"
        self.backend = "unconfigured"
        self._client = None
        self._lock = threading.Lock()
        self._initialized = False
        self._supabase_unavailable_columns: set[str] = set()

    def _ensure_backend_configured(self) -> None:
        if self.backend != "unconfigured":
            return

        if self.requested_backend == "sqlite":
            self.backend = "sqlite"
            return

        from blueprint_core.database import DATABASE_BACKEND, get_supabase_client

        if DATABASE_BACKEND == "supabase":
            self.backend = "supabase"
            self._client = get_supabase_client()
            return

        if self.requested_backend == "supabase":
            raise RuntimeError("JOB_METADATA_BACKEND=supabase requires the main database backend to be Supabase.")

        self.backend = "sqlite"

    def get_config(self) -> Dict[str, Any]:
        self._ensure_backend_configured()
        if self.backend == "supabase":
            return {"backend": "supabase", "client": "supabase-py", "table": "a2a_jobs", "dev_mode": False}
        return {
            "backend": "sqlite",
            "path_env": "JOB_METADATA_DB_PATH",
            "path": self.db_path,
            "dev_mode": blueprint_dev_mode_enabled(),
        }

    def init_db(self) -> None:
        if self._initialized:
            return
        self._ensure_backend_configured()
        if self.backend == "supabase":
            self._client.table("a2a_jobs").select("job_id").limit(1).execute()
            self._initialized = True
            return

        directory = os.path.dirname(os.path.abspath(self.db_path))
        if directory:
            os.makedirs(directory, exist_ok=True)

        with closing(self._connect()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS a2a_jobs (
                    job_id TEXT PRIMARY KEY,
                    message_id TEXT NOT NULL,
                    correlation_id TEXT,
                    action TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    status TEXT NOT NULL,
                    server_owned INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    payload_json TEXT,
                    result_summary_json TEXT,
                    source_usage_json TEXT,
                    progress_events_json TEXT,
                    error TEXT,
                    error_debug_json TEXT
                )
                """
            )
            self._migrate_sqlite_schema(conn)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_a2a_jobs_sender ON a2a_jobs(sender)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_a2a_jobs_status ON a2a_jobs(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_a2a_jobs_created_at ON a2a_jobs(created_at)")
            conn.commit()
        self._initialized = True

    def _migrate_sqlite_schema(self, conn: sqlite3.Connection) -> None:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(a2a_jobs)").fetchall()}
        if "source_usage_json" not in columns:
            conn.execute("ALTER TABLE a2a_jobs ADD COLUMN source_usage_json TEXT")
        if "error_debug_json" not in columns:
            conn.execute("ALTER TABLE a2a_jobs ADD COLUMN error_debug_json TEXT")
        if "progress_events_json" not in columns:
            conn.execute("ALTER TABLE a2a_jobs ADD COLUMN progress_events_json TEXT")

        rows = conn.execute(
            """
            SELECT job_id, action, payload_json, result_summary_json, source_usage_json
            FROM a2a_jobs
            WHERE source_usage_json IS NULL OR source_usage_json = ''
            """
        ).fetchall()
        for row in rows:
            source_usage = infer_source_usage(
                action=row["action"],
                payload=_json_loads(row["payload_json"]) or {},
                result_summary=_json_loads(row["result_summary_json"]) or {},
            )
            if source_usage:
                conn.execute(
                    "UPDATE a2a_jobs SET source_usage_json = ? WHERE job_id = ?",
                    (_json_dumps(source_usage), row["job_id"]),
                )

    def create_job(
        self,
        *,
        job_id: str,
        message_id: str,
        correlation_id: Optional[str],
        action: str,
        sender: str,
        recipient: str,
        payload: Dict[str, Any],
        server_owned: bool,
        status: str = "queued",
    ) -> Dict[str, Any]:
        self.init_db()
        now = _utc_now()
        source_usage = infer_source_usage(action=action, payload=payload)
        if self.backend == "supabase":
            self._execute_supabase_mutation(
                lambda values: self._client.table("a2a_jobs").upsert(values, on_conflict="job_id"),
                {
                    "job_id": job_id,
                    "message_id": message_id,
                    "correlation_id": correlation_id,
                    "action": action,
                    "sender": sender,
                    "recipient": recipient,
                    "status": status,
                    "server_owned": server_owned,
                    "created_at": now,
                    "updated_at": now,
                    "started_at": None,
                    "completed_at": None,
                    "payload_json": _redact_payload(payload),
                    "result_summary_json": None,
                    "source_usage_json": source_usage,
                    "progress_events_json": [],
                    "error_debug_json": None,
                    "error": None,
                },
            )
            return self.get_job(job_id) or {}

        with self._locked_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO a2a_jobs (
                    job_id, message_id, correlation_id, action, sender, recipient, status,
                    server_owned, created_at, updated_at, payload_json, source_usage_json, progress_events_json, error_debug_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    message_id,
                    correlation_id,
                    action,
                    sender,
                    recipient,
                    status,
                    1 if server_owned else 0,
                    now,
                    now,
                    _json_dumps(_redact_payload(payload)),
                    _json_dumps(source_usage),
                    _json_dumps([]),
                    None,
                ),
            )
        return self.get_job(job_id) or {}

    def append_progress_event(self, job_id: str, event: Dict[str, Any]) -> None:
        self.init_db()
        now = _utc_now()
        event_payload = dict(event or {})
        event_payload.setdefault("observed_at", now)

        if self.backend == "supabase":
            current = self.get_job(job_id) or {}
            if str(current.get("status") or "").lower() in {"cancelled", "canceled"}:
                raise JobCancelledError(f"Job {job_id} was cancelled.")
            events = list(current.get("progress_events") or [])
            events.append(event_payload)
            self._execute_supabase_mutation(
                lambda values: self._client.table("a2a_jobs").update(values).eq("job_id", job_id),
                {
                    "updated_at": now,
                    "progress_events_json": events,
                },
            )
            return

        with self._locked_connection() as conn:
            row = conn.execute("SELECT status, progress_events_json FROM a2a_jobs WHERE job_id = ?", (job_id,)).fetchone()
            if row is None:
                return
            if str(row["status"] or "").lower() in {"cancelled", "canceled"}:
                raise JobCancelledError(f"Job {job_id} was cancelled.")
            events = _json_loads(row["progress_events_json"]) or []
            if not isinstance(events, list):
                events = []
            events.append(event_payload)
            conn.execute(
                """
                UPDATE a2a_jobs
                SET progress_events_json = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (_json_dumps(events), now, job_id),
            )

    def mark_running(self, job_id: str) -> None:
        self.init_db()
        now = _utc_now()
        if self.backend == "supabase":
            current = self.get_job(job_id) or {}
            current_status = str(current.get("status") or "").lower()
            if current_status in TERMINAL_JOB_STATUSES:
                return
            self._client.table("a2a_jobs").update(
                {
                    "status": "running",
                    "started_at": current.get("started_at") or now,
                    "updated_at": now,
                }
            ).eq("job_id", job_id).eq("status", current_status).execute()
            return

        with self._locked_connection() as conn:
            conn.execute(
                """
                UPDATE a2a_jobs
                SET status = ?, started_at = COALESCE(started_at, ?), updated_at = ?
                WHERE job_id = ? AND status NOT IN ('succeeded', 'failed', 'cancelled', 'canceled')
                """,
                ("running", now, now, job_id),
            )

    def mark_routed(self, job_id: str) -> None:
        self._update_status(job_id, "routed")

    def mark_succeeded(self, job_id: str, result: Optional[Dict[str, Any]]) -> None:
        self.init_db()
        now = _utc_now()
        result_summary = summarize_result(result)
        current = self.get_job(job_id) or {}
        if str(current.get("status") or "").lower() in {"cancelled", "canceled"}:
            return
        source_usage = infer_source_usage(
            action=current.get("action"),
            payload=current.get("payload"),
            result=result,
            result_summary=result_summary,
            current=current,
        )
        if self.backend == "supabase":
            self._execute_supabase_mutation(
                lambda values: self._client.table("a2a_jobs").update(values).eq("job_id", job_id).eq("status", str(current.get("status") or "")),
                {
                    "status": "succeeded",
                    "completed_at": now,
                    "updated_at": now,
                    "result_summary_json": result_summary,
                    "source_usage_json": source_usage,
                    "error_debug_json": None,
                    "error": None,
                },
            )
            return

        with self._locked_connection() as conn:
            conn.execute(
                """
                UPDATE a2a_jobs
                SET status = ?, completed_at = ?, updated_at = ?, result_summary_json = ?, source_usage_json = ?, error_debug_json = NULL, error = NULL
                WHERE job_id = ? AND status NOT IN ('cancelled', 'canceled')
                """,
                ("succeeded", now, now, _json_dumps(result_summary), _json_dumps(source_usage), job_id),
            )

    def mark_failed(self, job_id: str, error: str, error_debug: Optional[Dict[str, Any]] = None) -> None:
        self.init_db()
        now = _utc_now()
        if self.backend == "supabase":
            current = self.get_job(job_id) or {}
            if str(current.get("status") or "").lower() in {"cancelled", "canceled"}:
                return
            self._execute_supabase_mutation(
                lambda values: self._client.table("a2a_jobs").update(values).eq("job_id", job_id).eq("status", str(current.get("status") or "")),
                {
                    "status": "failed",
                    "completed_at": now,
                    "updated_at": now,
                    "error_debug_json": error_debug,
                    "error": error,
                },
            )
            return

        with self._locked_connection() as conn:
            conn.execute(
                """
                UPDATE a2a_jobs
                SET status = ?, completed_at = ?, updated_at = ?, error = ?, error_debug_json = ?
                WHERE job_id = ? AND status NOT IN ('cancelled', 'canceled')
                """,
                ("failed", now, now, error, _json_dumps(error_debug) if error_debug else None, job_id),
            )

    def mark_cancelled(self, job_id: str, reason: str = "Cancelled by user.") -> Optional[Dict[str, Any]]:
        """Cancel a queued or running job without overwriting completed jobs."""
        self.init_db()
        now = _utc_now()
        if self.backend == "supabase":
            current = self.get_job(job_id)
            current_status = str((current or {}).get("status") or "").lower()
            if not current or current_status in TERMINAL_JOB_STATUSES:
                return current
            self._client.table("a2a_jobs").update(
                {
                    "status": "cancelled",
                    "completed_at": now,
                    "updated_at": now,
                    "error": reason,
                }
            ).eq("job_id", job_id).eq("status", current_status).execute()
            return self.get_job(job_id)

        with self._locked_connection() as conn:
            conn.execute(
                """
                UPDATE a2a_jobs
                SET status = ?, completed_at = ?, updated_at = ?, error = ?
                WHERE job_id = ? AND status NOT IN ('succeeded', 'failed', 'cancelled', 'canceled')
                """,
                ("cancelled", now, now, reason, job_id),
            )
        return self.get_job(job_id)

    def is_cancelled(self, job_id: str) -> bool:
        job = self.get_job(job_id)
        return str((job or {}).get("status") or "").lower() in {"cancelled", "canceled"}

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        self.init_db()
        if self.backend == "supabase":
            rows = self._client.table("a2a_jobs").select("*").eq("job_id", job_id).limit(1).execute().data or []
            return self._row_to_dict(rows[0]) if rows else None

        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM a2a_jobs WHERE job_id = ?", (job_id,)).fetchone()
        return self._row_to_dict(row) if row else None

    def list_jobs(
        self,
        *,
        sender: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        self.init_db()
        limit = max(1, min(limit, 200))
        if self.backend == "supabase":
            query = self._client.table("a2a_jobs").select("*")
            if sender:
                query = query.eq("sender", sender)
            if status:
                query = query.eq("status", status)
            rows = query.order("created_at", desc=True).limit(limit).execute().data or []
            return [self._row_to_dict(row) for row in rows]

        clauses = []
        params: List[Any] = []
        if sender:
            clauses.append("sender = ?")
            params.append(sender)
        if status:
            clauses.append("status = ?")
            params.append(status)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)

        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"SELECT * FROM a2a_jobs {where} ORDER BY created_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def _update_status(self, job_id: str, status: str) -> None:
        self.init_db()
        now = _utc_now()
        if self.backend == "supabase":
            self._client.table("a2a_jobs").update({"status": status, "updated_at": now}).eq("job_id", job_id).execute()
            return

        with self._locked_connection() as conn:
            conn.execute(
                "UPDATE a2a_jobs SET status = ?, updated_at = ? WHERE job_id = ?",
                (status, now, job_id),
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _locked_connection(self) -> sqlite3.Connection:
        return _LockedConnection(self._lock, self._connect())

    def _execute_supabase_mutation(self, build_query: Any, payload: Dict[str, Any]) -> Any:
        """Run a Supabase write while tolerating optional metadata columns missing in older schemas."""
        while True:
            values = {
                key: value
                for key, value in payload.items()
                if key not in self._supabase_unavailable_columns
            }
            try:
                return build_query(values).execute()
            except Exception as exc:
                missing_column = _missing_optional_supabase_column(exc)
                if not missing_column or missing_column in self._supabase_unavailable_columns:
                    raise
                self._supabase_unavailable_columns.add(missing_column)
                logger.warning(
                    "Supabase a2a_jobs column %s is unavailable; retrying job metadata write without it. "
                    "Apply the latest migrations to persist this metadata.",
                    missing_column,
                )

    @staticmethod
    def _row_to_dict(row: Any) -> Dict[str, Any]:
        result = dict(row)
        result["server_owned"] = bool(result["server_owned"])
        payload = _json_loads(result.pop("payload_json", None)) or {}
        result_summary = _json_loads(result.pop("result_summary_json", None))
        source_usage = _json_loads(result.pop("source_usage_json", None)) or {}
        result["progress_events"] = _json_loads(result.pop("progress_events_json", None)) or []
        result["error_debug"] = _json_loads(result.pop("error_debug_json", None))
        result["payload"] = payload
        result["result_summary"] = result_summary
        result["source_usage"] = infer_source_usage(
            action=result.get("action"),
            payload=payload,
            result_summary=result_summary,
            current={"source_usage": source_usage},
        )
        return result


def _missing_optional_supabase_column(exc: Exception) -> Optional[str]:
    message = str(exc)
    if "PGRST204" not in message and "Could not find" not in message:
        return None
    for column in OPTIONAL_SUPABASE_COLUMNS:
        if f"'{column}' column" in message or f'"{column}" column' in message or f"'{column}'" in message:
            return column
    return None


class _LockedConnection:
    def __init__(self, lock: threading.Lock, conn: sqlite3.Connection) -> None:
        self.lock = lock
        self.conn = conn

    def __enter__(self) -> sqlite3.Connection:
        self.lock.acquire()
        return self.conn.__enter__()

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        try:
            self.conn.__exit__(exc_type, exc, tb)
            self.conn.close()
        finally:
            self.lock.release()


JOB_STORE = JobMetadataStore()
