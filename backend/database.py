import logging
import os
import uuid
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from sqlalchemy import Column, Float, Integer, JSON, String, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from backend.runtime_config import blueprint_dev_mode_enabled

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
    title = Column(String, nullable=False)
    prompt = Column(Text, nullable=False)
    hardware_ir = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False)


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

    if blueprint_dev_mode_enabled():
        if override == "supabase":
            logger.warning("BLUEPRINT_DEV_MODE=true overrides DATABASE_BACKEND=supabase; using SQLite.")
        engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})
        return DatabaseConfig(backend="sqlite", source="BLUEPRINT_DEV_MODE", url=sqlite_url), engine, None

    if override == "sqlite":
        engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})
        return DatabaseConfig(backend="sqlite", source="SQLITE_DATABASE_URL", url=sqlite_url), engine, None

    url = _supabase_url()
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


def _hardware_ir_with_project_id(project_id: str, hardware_ir: Dict[str, Any]) -> Dict[str, Any]:
    hardware_ir = dict(hardware_ir or {})
    metadata = dict(hardware_ir.get("assembly_metadata") or {})
    metadata_project_id = metadata.get("project_id")
    if metadata_project_id and _canonical_project_id(metadata_project_id) != project_id:
        raise ValueError(
            "hardware_ir.assembly_metadata.project_id must match generated_projects.project_id."
        )
    metadata["project_id"] = project_id
    hardware_ir["assembly_metadata"] = metadata
    return hardware_ir


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
    client.table("a2a_jobs").select("job_id").limit(1).execute()
    client.table("alpha_signups").select("id").limit(1).execute()


def init_db() -> None:
    if DATABASE_BACKEND == "supabase":
        _verify_supabase_tables()
        return
    Base.metadata.create_all(bind=engine)


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


def save_generated_project(project_id: str, title: str, prompt: str, hardware_ir: Dict[str, Any], created_at: str) -> None:
    project_id = _canonical_project_id(project_id)
    hardware_ir = _hardware_ir_with_project_id(project_id, hardware_ir)
    record = {
        "project_id": project_id,
        "title": title,
        "prompt": prompt,
        "hardware_ir": hardware_ir,
        "created_at": created_at,
    }
    if DATABASE_BACKEND == "supabase":
        get_supabase_client().table("generated_projects").insert(record).execute()
        return

    db = _sqlite_session()
    try:
        db.add(DBGeneratedProject(**record))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def list_generated_projects() -> List[Any]:
    if DATABASE_BACKEND == "supabase":
        rows = (
            get_supabase_client()
            .table("generated_projects")
            .select("id,project_id,title,prompt,created_at")
            .order("id", desc=True)
            .execute()
            .data
            or []
        )
        return [_as_record(row) for row in rows]
    db = _sqlite_session()
    try:
        return db.query(DBGeneratedProject).order_by(DBGeneratedProject.id.desc()).all()
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


def update_generated_project_hardware_ir(project_id: str, hardware_ir: Dict[str, Any]) -> bool:
    project_id = _canonical_project_id(project_id)
    hardware_ir = _hardware_ir_with_project_id(project_id, hardware_ir)
    if DATABASE_BACKEND == "supabase":
        response = (
            get_supabase_client()
            .table("generated_projects")
            .update({"hardware_ir": hardware_ir})
            .eq("project_id", project_id)
            .execute()
        )
        return bool(response.data)

    db = _sqlite_session()
    try:
        project = db.query(DBGeneratedProject).filter(DBGeneratedProject.project_id == project_id).first()
        if not project:
            return False
        project.hardware_ir = hardware_ir
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
