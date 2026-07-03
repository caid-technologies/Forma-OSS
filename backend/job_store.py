import json
import os
import sqlite3
import threading
from contextlib import closing
from datetime import datetime
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from backend.job_source_usage import infer_source_usage
from backend.runtime_config import blueprint_dev_mode_enabled

load_dotenv()

DEFAULT_JOB_DB_PATH = "./blueprint_jobs.db"


def _utc_now() -> str:
    return datetime.utcnow().isoformat() + "Z"


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

    return {
        "project_id": metadata.get("project_id"),
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
        "product_image_provider": metadata.get("product_image_provider") or metadata.get("image_output_provider"),
        "product_image_model": metadata.get("product_image_model") or metadata.get("image_output_model"),
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

    def _ensure_backend_configured(self) -> None:
        if self.backend != "unconfigured":
            return

        if self.requested_backend == "sqlite":
            self.backend = "sqlite"
            return

        from backend.database import DATABASE_BACKEND, get_supabase_client

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
                    error TEXT
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
            self._client.table("a2a_jobs").upsert(
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
                    "error": None,
                },
                on_conflict="job_id",
            ).execute()
            return self.get_job(job_id) or {}

        with self._locked_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO a2a_jobs (
                    job_id, message_id, correlation_id, action, sender, recipient, status,
                    server_owned, created_at, updated_at, payload_json, source_usage_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                ),
            )
        return self.get_job(job_id) or {}

    def mark_running(self, job_id: str) -> None:
        self.init_db()
        now = _utc_now()
        if self.backend == "supabase":
            current = self.get_job(job_id) or {}
            self._client.table("a2a_jobs").update(
                {
                    "status": "running",
                    "started_at": current.get("started_at") or now,
                    "updated_at": now,
                }
            ).eq("job_id", job_id).execute()
            return

        with self._locked_connection() as conn:
            conn.execute(
                """
                UPDATE a2a_jobs
                SET status = ?, started_at = COALESCE(started_at, ?), updated_at = ?
                WHERE job_id = ?
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
        source_usage = infer_source_usage(
            action=current.get("action"),
            payload=current.get("payload"),
            result=result,
            result_summary=result_summary,
            current=current,
        )
        if self.backend == "supabase":
            self._client.table("a2a_jobs").update(
                {
                    "status": "succeeded",
                    "completed_at": now,
                    "updated_at": now,
                    "result_summary_json": result_summary,
                    "source_usage_json": source_usage,
                    "error": None,
                }
            ).eq("job_id", job_id).execute()
            return

        with self._locked_connection() as conn:
            conn.execute(
                """
                UPDATE a2a_jobs
                SET status = ?, completed_at = ?, updated_at = ?, result_summary_json = ?, source_usage_json = ?, error = NULL
                WHERE job_id = ?
                """,
                ("succeeded", now, now, _json_dumps(result_summary), _json_dumps(source_usage), job_id),
            )

    def mark_failed(self, job_id: str, error: str) -> None:
        self.init_db()
        now = _utc_now()
        if self.backend == "supabase":
            self._client.table("a2a_jobs").update(
                {
                    "status": "failed",
                    "completed_at": now,
                    "updated_at": now,
                    "error": error,
                }
            ).eq("job_id", job_id).execute()
            return

        with self._locked_connection() as conn:
            conn.execute(
                """
                UPDATE a2a_jobs
                SET status = ?, completed_at = ?, updated_at = ?, error = ?
                WHERE job_id = ?
                """,
                ("failed", now, now, error, job_id),
            )

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

    @staticmethod
    def _row_to_dict(row: Any) -> Dict[str, Any]:
        result = dict(row)
        result["server_owned"] = bool(result["server_owned"])
        payload = _json_loads(result.pop("payload_json", None)) or {}
        result_summary = _json_loads(result.pop("result_summary_json", None))
        source_usage = _json_loads(result.pop("source_usage_json", None)) or {}
        result["payload"] = payload
        result["result_summary"] = result_summary
        result["source_usage"] = infer_source_usage(
            action=result.get("action"),
            payload=payload,
            result_summary=result_summary,
            current={"source_usage": source_usage},
        )
        return result


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
