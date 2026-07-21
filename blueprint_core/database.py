import logging
import os
import uuid
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from dotenv import load_dotenv
from sqlalchemy import Column, Float, Integer, JSON, String, Text, create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from blueprint_core.runtime import blueprint_dev_mode_enabled
from blueprint_core.project_objects import attach_project_object_metadata_to_dict

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_SQLITE_DATABASE_URL = "sqlite:///./blueprint.db"
SUPABASE_KEY_ENV_VARS = (
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_SECRET_KEY",
)
DATABASE_BACKEND_ENV_VARS = ("DATABASE_BACKEND", "DATABASE_PROVIDER", "DB_BACKEND", "DB_PROVIDER")


@dataclass(frozen=True)
class DatabaseConfig:
    backend: str
    source: str
    url: str


Base = declarative_base()


class DBComponentTemplate(Base):
    __tablename__ = "component_templates"

    id = Column(Integer, primary_key=True, index=True)
    part_number = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    category = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    price = Column(Float, default=0.0)
    sourcing_url = Column(String, nullable=True)
    pins = Column(JSON, nullable=False)
    use_cases = Column(JSON, nullable=False)


class DBGeneratedProject(Base):
    __tablename__ = "generated_projects"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(String, unique=True, index=True, nullable=False)
    chat_id = Column(String, index=True, nullable=True)
    owner_user_id = Column(String, index=True, nullable=True)
    visibility = Column(String, index=True, nullable=False, default="public")
    title = Column(String, nullable=False)
    prompt = Column(Text, nullable=False)
    hardware_ir = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False)


class DBProjectChat(Base):
    __tablename__ = "project_chats"

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(String, unique=True, index=True, nullable=False)
    owner_user_id = Column(String, index=True, nullable=False)
    title = Column(String, nullable=False)
    messages = Column(JSON, nullable=False, default=list)
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)


class DBAlphaSignup(Base):
    __tablename__ = "alpha_signups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, index=True, nullable=False)
    organization = Column(String, nullable=True)
    additional_info = Column(Text, nullable=True)
    source = Column(String, nullable=False, default="web")
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(String, nullable=False)


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value or default


def _backend_override() -> Optional[str]:
    aliases = {
        "sqlite": "sqlite",
        "sqlite3": "sqlite",
        "supabase": "supabase",
    }
    for name in DATABASE_BACKEND_ENV_VARS:
        value = _env(name)
        if not value:
            continue
        normalized = aliases.get(value.lower())
        if normalized:
            return normalized
        logger.warning("Ignoring unsupported %s=%r. Expected sqlite or supabase.", name, value)
    return None


def _sqlite_database_url() -> str:
    value = _env("SQLITE_DATABASE_URL") or _env("SQLITE_DB_URL") or DEFAULT_SQLITE_DATABASE_URL
    if "://" not in value:
        return f"sqlite:///{value}"
    return value


def _supabase_url() -> Optional[str]:
    return _env("SUPABASE_URL") or _env("NEXT_PUBLIC_SUPABASE_URL")


def _is_local_supabase_url(url: Optional[str]) -> bool:
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    host = (parsed.hostname or "").strip().lower()
    return host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".localhost")


def _supabase_key() -> tuple[Optional[str], Optional[str]]:
    for name in SUPABASE_KEY_ENV_VARS:
        value = _env(name)
        if value:
            return value, name
    return None, None


def _public_supabase_key_sources() -> List[str]:
    return [
        name
        for name in ("SUPABASE_KEY", "SUPABASE_ANON_KEY", "NEXT_PUBLIC_SUPABASE_ANON_KEY")
        if _env(name)
    ]


def _warn_ignored_database_urls() -> None:
    ignored = [
        name
        for name in (
            "SUPABASE_DATABASE_URL",
            "SUPABASE_DB_URL",
            "SUPABASE_POSTGRES_URL",
            "SUPABASE_POOLER_URL",
            "DATABASE_URL",
            "POSTGRES_URL",
            "POSTGRES_URL_NON_POOLING",
        )
        if _env(name)
    ]
    if ignored:
        logger.warning(
            "Ignoring raw database URL env vars (%s). Supabase mode uses SUPABASE_URL plus "
            "SUPABASE_SERVICE_ROLE_KEY/SUPABASE_SECRET_KEY through the Supabase client.",
            ", ".join(ignored),
        )


def _build_supabase_client(url: str, key: str):
    try:
        from supabase import create_client
    except ImportError as exc:
        raise RuntimeError("Supabase client is not installed. Run pip install -r backend/requirements.txt.") from exc
    return create_client(url, key)


def _select_database_config() -> tuple[DatabaseConfig, Any, Any]:
    override = _backend_override()
    sqlite_url = _sqlite_database_url()
    url = _supabase_url()

    if blueprint_dev_mode_enabled():
        if override == "supabase" and _is_local_supabase_url(url):
            logger.info("BLUEPRINT_DEV_MODE=true with local DATABASE_BACKEND=supabase; using local Supabase.")
        else:
            if override == "supabase":
                logger.warning("BLUEPRINT_DEV_MODE=true overrides remote DATABASE_BACKEND=supabase; using SQLite.")
            engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})
            return DatabaseConfig(backend="sqlite", source="BLUEPRINT_DEV_MODE", url=sqlite_url), engine, None

    if override == "sqlite":
        engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})
        return DatabaseConfig(backend="sqlite", source="SQLITE_DATABASE_URL", url=sqlite_url), engine, None

    key, key_source = _supabase_key()
    public_key_sources = _public_supabase_key_sources()
    if override == "supabase" and (not url or not key):
        public_key_hint = (
            f" Found public/anon key env vars instead: {', '.join(public_key_sources)}."
            if public_key_sources
            else ""
        )
        raise RuntimeError(
            "DATABASE_BACKEND=supabase requires SUPABASE_URL plus SUPABASE_SERVICE_ROLE_KEY "
            "or SUPABASE_SECRET_KEY. The backend writes seed/project data and cannot use anon/publishable keys."
            f"{public_key_hint}"
        )

    if url and key:
        _warn_ignored_database_urls()
        client = _build_supabase_client(url, key)
        return DatabaseConfig(backend="supabase", source=f"SUPABASE_URL+{key_source}", url=url), None, client

    if url or key:
        logger.warning(
            "Supabase client is partially configured. Provide both SUPABASE_URL and "
            "SUPABASE_SERVICE_ROLE_KEY/SUPABASE_SECRET_KEY. Falling back to SQLite."
        )
    else:
        _warn_ignored_database_urls()

    engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})
    return DatabaseConfig(backend="sqlite", source="SQLITE_DATABASE_URL", url=sqlite_url), engine, None


_ACTIVE_DATABASE_CONFIG, engine, _SUPABASE_CLIENT = _select_database_config()
DATABASE_BACKEND = _ACTIVE_DATABASE_CONFIG.backend
DATABASE_SOURCE = _ACTIVE_DATABASE_CONFIG.source
DATABASE_URL = _ACTIVE_DATABASE_CONFIG.url
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine) if engine is not None else None


def _as_record(row: Dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(**row)


def _canonical_project_id(value: str) -> str:
    try:
        return str(uuid.UUID(str(value).strip()))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"generated_projects.project_id must be a UUID, got {value!r}.") from exc


def _normalize_chat_id(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_user_id(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_visibility(value: Optional[str]) -> str:
    normalized = (value or "public").strip().lower()
    return normalized if normalized in {"public", "private"} else "public"


def _error_mentions_missing_chat_id_column(exc: Exception) -> bool:
    return _error_mentions_missing_column(exc, "chat_id")


def _error_mentions_missing_column(exc: Exception, column: str) -> bool:
    text = str(exc).lower()
    return column.lower() in text and (
        "does not exist" in text
        or "42703" in text
        or "missing" in text
        or "could not find" in text
        or "pgrst204" in text
        or "schema cache" in text
    )


def _chat_id_from_hardware_ir(hardware_ir: Any) -> Optional[str]:
    if not isinstance(hardware_ir, dict):
        return None
    metadata = hardware_ir.get("assembly_metadata")
    if not isinstance(metadata, dict):
        return None
    return _normalize_chat_id(metadata.get("chat_id"))


def _hardware_ir_with_project_id(
    project_id: str,
    hardware_ir: Dict[str, Any],
    chat_id: Optional[str] = None,
) -> Dict[str, Any]:
    hardware_ir = dict(hardware_ir or {})
    metadata = dict(hardware_ir.get("assembly_metadata") or {})
    metadata_project_id = metadata.get("project_id")
    if metadata_project_id and _canonical_project_id(metadata_project_id) != project_id:
        raise ValueError(
            "hardware_ir.assembly_metadata.project_id must match generated_projects.project_id."
        )
    metadata["project_id"] = project_id
    normalized_chat_id = _normalize_chat_id(chat_id) or _normalize_chat_id(metadata.get("chat_id"))
    if normalized_chat_id:
        metadata["chat_id"] = normalized_chat_id
    hardware_ir["assembly_metadata"] = metadata
    object_metadata = metadata.get("project_object") if isinstance(metadata.get("project_object"), dict) else {}
    target_namespace = metadata.get("iteration_target_namespace") or object_metadata.get("target_namespace")
    return attach_project_object_metadata_to_dict(hardware_ir, target_namespace=target_namespace)


def _sqlite_session():
    if SessionLocal is None:
        raise RuntimeError("SQLite session requested while Supabase backend is active.")
    return SessionLocal()


def get_supabase_client():
    if DATABASE_BACKEND != "supabase" or _SUPABASE_CLIENT is None:
        raise RuntimeError("Supabase client requested while SQLite backend is active.")
    return _SUPABASE_CLIENT


def _verify_supabase_tables() -> None:
    client = get_supabase_client()
    client.table("component_templates").select("id").limit(1).execute()
    client.table("generated_projects").select("id").limit(1).execute()
    client.table("project_chats").select("id").limit(1).execute()
    client.table("a2a_jobs").select("job_id").limit(1).execute()
    client.table("alpha_signups").select("id").limit(1).execute()
    client.table("user_integration_configs").select("owner_user_id").limit(1).execute()
    client.table("workspace_integration_configs").select("config_key").limit(1).execute()


def init_db() -> None:
    if DATABASE_BACKEND == "supabase":
        _verify_supabase_tables()
        return
    Base.metadata.create_all(bind=engine)
    _migrate_sqlite_schema()


def _migrate_sqlite_schema() -> None:
    if engine is None:
        return
    with engine.begin() as connection:
        columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(generated_projects)").fetchall()}
        if "chat_id" not in columns:
            connection.execute(text("ALTER TABLE generated_projects ADD COLUMN chat_id VARCHAR"))
        if "owner_user_id" not in columns:
            connection.execute(text("ALTER TABLE generated_projects ADD COLUMN owner_user_id VARCHAR"))
        if "visibility" not in columns:
            connection.execute(text("ALTER TABLE generated_projects ADD COLUMN visibility VARCHAR NOT NULL DEFAULT 'public'"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_generated_projects_chat_id ON generated_projects (chat_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_generated_projects_owner_user_id ON generated_projects (owner_user_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_generated_projects_visibility ON generated_projects (visibility)"))


def get_db():
    db = _sqlite_session()
    try:
        yield db
    finally:
        db.close()


def count_component_templates() -> int:
    if DATABASE_BACKEND == "supabase":
        rows = get_supabase_client().table("component_templates").select("id").execute().data or []
        return len(rows)
    db = _sqlite_session()
    try:
        return db.query(DBComponentTemplate).count()
    finally:
        db.close()


def list_component_templates() -> List[Any]:
    if DATABASE_BACKEND == "supabase":
        rows = get_supabase_client().table("component_templates").select("*").order("id").execute().data or []
        return [_as_record(row) for row in rows]
    db = _sqlite_session()
    try:
        return db.query(DBComponentTemplate).all()
    finally:
        db.close()


def get_component_template_by_part_number(part_number: str) -> Optional[Any]:
    if DATABASE_BACKEND == "supabase":
        rows = (
            get_supabase_client()
            .table("component_templates")
            .select("*")
            .eq("part_number", part_number)
            .limit(1)
            .execute()
            .data
            or []
        )
        return _as_record(rows[0]) if rows else None
    db = _sqlite_session()
    try:
        return db.query(DBComponentTemplate).filter(DBComponentTemplate.part_number == part_number).first()
    finally:
        db.close()


def insert_component_template_if_missing(component: Dict[str, Any]) -> bool:
    if get_component_template_by_part_number(component["part_number"]):
        return False

    record = {
        "part_number": component["part_number"],
        "name": component["name"],
        "category": component["category"],
        "description": component["description"],
        "price": component["price"],
        "sourcing_url": component["sourcing_url"],
        "pins": component["pins"],
        "use_cases": component["use_cases"],
    }
    if DATABASE_BACKEND == "supabase":
        get_supabase_client().table("component_templates").insert(record).execute()
        return True

    db = _sqlite_session()
    try:
        db.add(DBComponentTemplate(**record))
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def save_generated_project(
    project_id: str,
    title: str,
    prompt: str,
    hardware_ir: Dict[str, Any],
    created_at: str,
    chat_id: Optional[str] = None,
    owner_user_id: Optional[str] = None,
    visibility: Optional[str] = "public",
) -> None:
    project_id = _canonical_project_id(project_id)
    hardware_ir = _hardware_ir_with_project_id(project_id, hardware_ir, chat_id=chat_id)
    metadata = hardware_ir.get("assembly_metadata") if isinstance(hardware_ir.get("assembly_metadata"), dict) else {}
    normalized_chat_id = _normalize_chat_id(chat_id) or _normalize_chat_id(metadata.get("chat_id"))
    normalized_owner_user_id = _normalize_user_id(owner_user_id)
    normalized_visibility = _normalize_visibility(visibility)
    record = {
        "project_id": project_id,
        "chat_id": normalized_chat_id,
        "owner_user_id": normalized_owner_user_id,
        "visibility": normalized_visibility,
        "title": title,
        "prompt": prompt,
        "hardware_ir": hardware_ir,
        "created_at": created_at,
    }
    if DATABASE_BACKEND == "supabase":
        try:
            get_supabase_client().table("generated_projects").insert(record).execute()
        except Exception as exc:
            if not _error_mentions_missing_chat_id_column(exc) or normalized_owner_user_id:
                raise
            fallback_record = dict(record)
            fallback_record.pop("chat_id", None)
            fallback_record.pop("owner_user_id", None)
            fallback_record.pop("visibility", None)
            get_supabase_client().table("generated_projects").insert(fallback_record).execute()
        if normalized_chat_id and normalized_owner_user_id:
            upsert_project_chat(
                chat_id=normalized_chat_id,
                owner_user_id=normalized_owner_user_id,
                title=title or prompt[:80] or "Untitled chat",
                messages=[],
                created_at=created_at,
                updated_at=created_at,
            )
        return

    db = _sqlite_session()
    try:
        db.add(DBGeneratedProject(**record))
        if normalized_chat_id and normalized_owner_user_id:
            chat = db.query(DBProjectChat).filter(DBProjectChat.chat_id == normalized_chat_id).first()
            if chat:
                if chat.owner_user_id == normalized_owner_user_id:
                    chat.title = chat.title or title or "Untitled chat"
                    chat.updated_at = created_at
            else:
                db.add(
                    DBProjectChat(
                        chat_id=normalized_chat_id,
                        owner_user_id=normalized_owner_user_id,
                        title=title or prompt[:80] or "Untitled chat",
                        messages=[],
                        created_at=created_at,
                        updated_at=created_at,
                    )
                )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def list_generated_projects(owner_user_id: Optional[str] = None) -> List[Any]:
    normalized_owner_user_id = _normalize_user_id(owner_user_id)
    if DATABASE_BACKEND == "supabase":
        client = get_supabase_client()
        try:
            query = (
                client
                .table("generated_projects")
                .select("id,project_id,chat_id,title,prompt,created_at,owner_user_id,visibility,hardware_ir")
            )
            if normalized_owner_user_id:
                query = query.eq("owner_user_id", normalized_owner_user_id)
            rows = query.order("id", desc=True).execute().data or []
        except Exception as exc:
            if not _error_mentions_missing_chat_id_column(exc):
                raise
            query = (
                client
                .table("generated_projects")
                .select("id,project_id,title,prompt,created_at,hardware_ir")
            )
            if normalized_owner_user_id:
                query = query.eq("owner_user_id", normalized_owner_user_id)
            rows = query.order("id", desc=True).execute().data or []
            for row in rows:
                row["chat_id"] = _chat_id_from_hardware_ir(row.get("hardware_ir"))
        return [_as_record(row) for row in rows]
    db = _sqlite_session()
    try:
        query = db.query(DBGeneratedProject)
        if normalized_owner_user_id:
            query = query.filter(DBGeneratedProject.owner_user_id == normalized_owner_user_id)
        return query.order_by(DBGeneratedProject.id.desc()).all()
    finally:
        db.close()


def get_generated_project(project_id: str) -> Optional[Any]:
    if DATABASE_BACKEND == "supabase":
        rows = (
            get_supabase_client()
            .table("generated_projects")
            .select("*")
            .eq("project_id", project_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        return _as_record(rows[0]) if rows else None
    db = _sqlite_session()
    try:
        return db.query(DBGeneratedProject).filter(DBGeneratedProject.project_id == project_id).first()
    finally:
        db.close()


def update_generated_project_hardware_ir(
    project_id: str,
    hardware_ir: Dict[str, Any],
    owner_user_id: Optional[str] = None,
) -> bool:
    project_id = _canonical_project_id(project_id)
    hardware_ir = _hardware_ir_with_project_id(project_id, hardware_ir)
    metadata = hardware_ir.get("assembly_metadata") if isinstance(hardware_ir.get("assembly_metadata"), dict) else {}
    chat_id = _normalize_chat_id(metadata.get("chat_id"))
    normalized_owner_user_id = _normalize_user_id(owner_user_id)
    if DATABASE_BACKEND == "supabase":
        client = get_supabase_client()
        try:
            query = client.table("generated_projects").update({"hardware_ir": hardware_ir, "chat_id": chat_id}).eq("project_id", project_id)
            if normalized_owner_user_id:
                query = query.eq("owner_user_id", normalized_owner_user_id)
            response = query.execute()
        except Exception as exc:
            if not _error_mentions_missing_chat_id_column(exc):
                raise
            query = client.table("generated_projects").update({"hardware_ir": hardware_ir}).eq("project_id", project_id)
            if normalized_owner_user_id:
                query = query.eq("owner_user_id", normalized_owner_user_id)
            response = query.execute()
        return bool(response.data)

    db = _sqlite_session()
    try:
        query = db.query(DBGeneratedProject).filter(DBGeneratedProject.project_id == project_id)
        if normalized_owner_user_id:
            query = query.filter(DBGeneratedProject.owner_user_id == normalized_owner_user_id)
        project = query.first()
        if not project:
            return False
        project.hardware_ir = hardware_ir
        project.chat_id = chat_id
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def update_generated_project_metadata(
    project_id: str,
    *,
    owner_user_id: str,
    title: Optional[str] = None,
    prompt: Optional[str] = None,
    visibility: Optional[str] = None,
) -> bool:
    project_id = _canonical_project_id(project_id)
    normalized_owner_user_id = _normalize_user_id(owner_user_id)
    if not normalized_owner_user_id:
        return False
    updates: Dict[str, Any] = {}
    if title is not None:
        updates["title"] = title.strip() or "Untitled Blueprint Project"
    if prompt is not None:
        updates["prompt"] = prompt.strip()
    if visibility is not None:
        updates["visibility"] = _normalize_visibility(visibility)
    if not updates:
        return True

    if DATABASE_BACKEND == "supabase":
        response = (
            get_supabase_client()
            .table("generated_projects")
            .update(updates)
            .eq("project_id", project_id)
            .eq("owner_user_id", normalized_owner_user_id)
            .execute()
        )
        return bool(response.data)

    db = _sqlite_session()
    try:
        project = (
            db.query(DBGeneratedProject)
            .filter(DBGeneratedProject.project_id == project_id)
            .filter(DBGeneratedProject.owner_user_id == normalized_owner_user_id)
            .first()
        )
        if not project:
            return False
        for key, value in updates.items():
            setattr(project, key, value)
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def delete_generated_project(project_id: str, owner_user_id: str) -> bool:
    project_id = _canonical_project_id(project_id)
    normalized_owner_user_id = _normalize_user_id(owner_user_id)
    if not normalized_owner_user_id:
        return False
    if DATABASE_BACKEND == "supabase":
        response = (
            get_supabase_client()
            .table("generated_projects")
            .delete()
            .eq("project_id", project_id)
            .eq("owner_user_id", normalized_owner_user_id)
            .execute()
        )
        return bool(response.data)

    db = _sqlite_session()
    try:
        project = (
            db.query(DBGeneratedProject)
            .filter(DBGeneratedProject.project_id == project_id)
            .filter(DBGeneratedProject.owner_user_id == normalized_owner_user_id)
            .first()
        )
        if not project:
            return False
        db.delete(project)
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def upsert_project_chat(
    *,
    chat_id: str,
    owner_user_id: str,
    title: str,
    messages: Optional[List[Dict[str, Any]]] = None,
    created_at: str,
    updated_at: str,
) -> Any:
    normalized_chat_id = _normalize_chat_id(chat_id)
    normalized_owner_user_id = _normalize_user_id(owner_user_id)
    if not normalized_chat_id or not normalized_owner_user_id:
        raise ValueError("chat_id and owner_user_id are required.")
    record = {
        "chat_id": normalized_chat_id,
        "owner_user_id": normalized_owner_user_id,
        "title": title.strip() or "Untitled chat",
        "messages": messages or [],
        "created_at": created_at,
        "updated_at": updated_at,
    }
    if DATABASE_BACKEND == "supabase":
        rows = (
            get_supabase_client()
            .table("project_chats")
            .select("*")
            .eq("chat_id", normalized_chat_id)
            .eq("owner_user_id", normalized_owner_user_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        if rows:
            response = (
                get_supabase_client()
                .table("project_chats")
                .update({"title": record["title"], "messages": record["messages"], "updated_at": updated_at})
                .eq("chat_id", normalized_chat_id)
                .eq("owner_user_id", normalized_owner_user_id)
                .execute()
            )
        else:
            response = get_supabase_client().table("project_chats").insert(record).execute()
        rows = response.data or []
        return _as_record(rows[0]) if rows else _as_record(record)

    db = _sqlite_session()
    try:
        chat = (
            db.query(DBProjectChat)
            .filter(DBProjectChat.chat_id == normalized_chat_id)
            .filter(DBProjectChat.owner_user_id == normalized_owner_user_id)
            .first()
        )
        if chat:
            chat.title = record["title"]
            chat.messages = record["messages"]
            chat.updated_at = updated_at
        else:
            chat = DBProjectChat(**record)
            db.add(chat)
        db.commit()
        db.refresh(chat)
        return chat
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def list_project_chats(owner_user_id: str) -> List[Any]:
    normalized_owner_user_id = _normalize_user_id(owner_user_id)
    if not normalized_owner_user_id:
        return []
    if DATABASE_BACKEND == "supabase":
        rows = (
            get_supabase_client()
            .table("project_chats")
            .select("*")
            .eq("owner_user_id", normalized_owner_user_id)
            .order("updated_at", desc=True)
            .execute()
            .data
            or []
        )
        return [_as_record(row) for row in rows]
    db = _sqlite_session()
    try:
        return (
            db.query(DBProjectChat)
            .filter(DBProjectChat.owner_user_id == normalized_owner_user_id)
            .order_by(DBProjectChat.updated_at.desc())
            .all()
        )
    finally:
        db.close()


def get_project_chat(chat_id: str, owner_user_id: str) -> Optional[Any]:
    normalized_chat_id = _normalize_chat_id(chat_id)
    normalized_owner_user_id = _normalize_user_id(owner_user_id)
    if not normalized_chat_id or not normalized_owner_user_id:
        return None
    if DATABASE_BACKEND == "supabase":
        rows = (
            get_supabase_client()
            .table("project_chats")
            .select("*")
            .eq("chat_id", normalized_chat_id)
            .eq("owner_user_id", normalized_owner_user_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        return _as_record(rows[0]) if rows else None
    db = _sqlite_session()
    try:
        return (
            db.query(DBProjectChat)
            .filter(DBProjectChat.chat_id == normalized_chat_id)
            .filter(DBProjectChat.owner_user_id == normalized_owner_user_id)
            .first()
        )
    finally:
        db.close()


def delete_project_chat(chat_id: str, owner_user_id: str) -> bool:
    normalized_chat_id = _normalize_chat_id(chat_id)
    normalized_owner_user_id = _normalize_user_id(owner_user_id)
    if not normalized_chat_id or not normalized_owner_user_id:
        return False
    if DATABASE_BACKEND == "supabase":
        response = (
            get_supabase_client()
            .table("project_chats")
            .delete()
            .eq("chat_id", normalized_chat_id)
            .eq("owner_user_id", normalized_owner_user_id)
            .execute()
        )
        if response.data:
            get_supabase_client().table("generated_projects").update({"chat_id": None}).eq("chat_id", normalized_chat_id).eq("owner_user_id", normalized_owner_user_id).execute()
        return bool(response.data)
    db = _sqlite_session()
    try:
        chat = (
            db.query(DBProjectChat)
            .filter(DBProjectChat.chat_id == normalized_chat_id)
            .filter(DBProjectChat.owner_user_id == normalized_owner_user_id)
            .first()
        )
        if not chat:
            return False
        db.delete(chat)
        db.query(DBGeneratedProject).filter(DBGeneratedProject.chat_id == normalized_chat_id).filter(DBGeneratedProject.owner_user_id == normalized_owner_user_id).update({"chat_id": None})
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def save_alpha_signup(
    *,
    name: str,
    email: str,
    organization: Optional[str],
    additional_info: Optional[str],
    source: str,
    metadata: Optional[Dict[str, Any]],
    created_at: str,
) -> Any:
    record = {
        "name": name,
        "email": email.lower(),
        "organization": organization,
        "additional_info": additional_info,
        "source": source,
        "metadata_json": metadata or {},
        "created_at": created_at,
    }
    if DATABASE_BACKEND == "supabase":
        response = get_supabase_client().table("alpha_signups").insert(record).execute()
        rows = response.data or []
        return _as_record(rows[0]) if rows else _as_record(record)

    db = _sqlite_session()
    try:
        signup = DBAlphaSignup(**record)
        db.add(signup)
        db.commit()
        db.refresh(signup)
        return signup
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_database_config() -> Dict[str, Any]:
    return {
        "backend": DATABASE_BACKEND,
        "source": DATABASE_SOURCE,
        "url": DATABASE_URL,
        "client": "supabase-py" if DATABASE_BACKEND == "supabase" else "sqlite/sqlalchemy",
        "dev_mode": blueprint_dev_mode_enabled(),
    }
