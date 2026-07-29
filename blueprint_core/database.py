import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from dotenv import load_dotenv
from blueprint_core.runtime import blueprint_dev_mode_enabled
from blueprint_core.workspaces.projects.objects import attach_project_object_metadata_to_dict
from blueprint_core.persistence.base import DatabaseProvider
from blueprint_core.persistence.models import (
    Base,
    DBAlphaSignup,
    DBComponentTemplate,
    DBGeneratedProject,
    DBProjectChat,
    DBUserIntegrationConfig,
    DBUserSettings,
    DBWorkspaceIntegrationConfig,
)
from blueprint_core.persistence.providers import SQLiteProvider, SupabaseProvider, create_sqlite_provider
from blueprint_core.persistence.repositories import (
    ApplicationRepository,
    SqlAlchemyRepository,
    SupabaseRepository,
)

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
            provider = create_sqlite_provider(source="BLUEPRINT_DEV_MODE", url=sqlite_url)
            return DatabaseConfig(backend="sqlite", source="BLUEPRINT_DEV_MODE", url=sqlite_url), provider.engine, None

    if override == "sqlite":
        provider = create_sqlite_provider(source="SQLITE_DATABASE_URL", url=sqlite_url)
        return DatabaseConfig(backend="sqlite", source="SQLITE_DATABASE_URL", url=sqlite_url), provider.engine, None

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

    provider = create_sqlite_provider(source="SQLITE_DATABASE_URL", url=sqlite_url)
    return DatabaseConfig(backend="sqlite", source="SQLITE_DATABASE_URL", url=sqlite_url), provider.engine, None


_ACTIVE_DATABASE_CONFIG, engine, _SUPABASE_CLIENT = _select_database_config()
DATABASE_BACKEND = _ACTIVE_DATABASE_CONFIG.backend
DATABASE_SOURCE = _ACTIVE_DATABASE_CONFIG.source
DATABASE_URL = _ACTIVE_DATABASE_CONFIG.url
_DATABASE_PROVIDER: DatabaseProvider
if DATABASE_BACKEND == "supabase":
    _DATABASE_PROVIDER = SupabaseProvider(
        source=DATABASE_SOURCE,
        url=DATABASE_URL,
        client=_SUPABASE_CLIENT,
    )
else:
    assert engine is not None
    _DATABASE_PROVIDER = SQLiteProvider(
        source=DATABASE_SOURCE,
        url=DATABASE_URL,
        engine=engine,
    )
_DATABASE_REPOSITORY: ApplicationRepository
if DATABASE_BACKEND == "supabase":
    SessionLocal = None
    _DATABASE_REPOSITORY = SupabaseRepository(_SUPABASE_CLIENT)
else:
    assert isinstance(_DATABASE_PROVIDER, SQLiteProvider)
    SessionLocal = _DATABASE_PROVIDER.session_factory
    assert SessionLocal is not None
    _DATABASE_REPOSITORY = SqlAlchemyRepository(SessionLocal)


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


def get_database_provider() -> DatabaseProvider:
    """Return the provider selected once at application composition time."""

    return _DATABASE_PROVIDER


def init_db() -> None:
    _DATABASE_PROVIDER.initialize()


def get_db():
    db = _sqlite_session()
    try:
        yield db
    finally:
        db.close()


def count_component_templates() -> int:
    return _DATABASE_REPOSITORY.count_component_templates()


def list_component_templates() -> List[Any]:
    return _DATABASE_REPOSITORY.list_component_templates()


def get_component_template_by_part_number(part_number: str) -> Optional[Any]:
    return _DATABASE_REPOSITORY.get_component_template_by_part_number(part_number)


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
    _DATABASE_REPOSITORY.insert_component_template(record)
    return True


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
    chat_record = None
    if normalized_chat_id and normalized_owner_user_id:
        chat_record = {
            "chat_id": normalized_chat_id,
            "owner_user_id": normalized_owner_user_id,
            "title": title or prompt[:80] or "Untitled chat",
            "messages": [],
            "created_at": created_at,
            "updated_at": created_at,
        }
    _DATABASE_REPOSITORY.save_generated_project(record, chat_record)


def list_generated_projects(owner_user_id: Optional[str] = None) -> List[Any]:
    normalized_owner_user_id = _normalize_user_id(owner_user_id)
    return _DATABASE_REPOSITORY.list_generated_projects(normalized_owner_user_id)


def get_generated_project(project_id: str) -> Optional[Any]:
    return _DATABASE_REPOSITORY.get_generated_project(project_id)


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
    return _DATABASE_REPOSITORY.update_generated_project_hardware_ir(
        project_id,
        hardware_ir,
        chat_id,
        normalized_owner_user_id,
    )


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
        updates["title"] = title.strip() or "Untitled Forma Project"
    if prompt is not None:
        updates["prompt"] = prompt.strip()
    if visibility is not None:
        updates["visibility"] = _normalize_visibility(visibility)
    if not updates:
        return True
    return _DATABASE_REPOSITORY.update_generated_project_metadata(
        project_id,
        normalized_owner_user_id,
        updates,
    )


def delete_generated_project(project_id: str, owner_user_id: str) -> bool:
    project_id = _canonical_project_id(project_id)
    normalized_owner_user_id = _normalize_user_id(owner_user_id)
    if not normalized_owner_user_id:
        return False
    return _DATABASE_REPOSITORY.delete_generated_project(project_id, normalized_owner_user_id)


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
    return _DATABASE_REPOSITORY.upsert_project_chat(record)


def list_project_chats(owner_user_id: str) -> List[Any]:
    normalized_owner_user_id = _normalize_user_id(owner_user_id)
    if not normalized_owner_user_id:
        return []
    return _DATABASE_REPOSITORY.list_project_chats(normalized_owner_user_id)


def get_project_chat(chat_id: str, owner_user_id: str) -> Optional[Any]:
    normalized_chat_id = _normalize_chat_id(chat_id)
    normalized_owner_user_id = _normalize_user_id(owner_user_id)
    if not normalized_chat_id or not normalized_owner_user_id:
        return None
    return _DATABASE_REPOSITORY.get_project_chat(normalized_chat_id, normalized_owner_user_id)


def delete_project_chat(chat_id: str, owner_user_id: str) -> bool:
    normalized_chat_id = _normalize_chat_id(chat_id)
    normalized_owner_user_id = _normalize_user_id(owner_user_id)
    if not normalized_chat_id or not normalized_owner_user_id:
        return False
    return _DATABASE_REPOSITORY.delete_project_chat(normalized_chat_id, normalized_owner_user_id)


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
    return _DATABASE_REPOSITORY.save_alpha_signup(record)


def get_user_settings(owner_user_id: str) -> Optional[Any]:
    normalized_owner_user_id = _normalize_user_id(owner_user_id)
    if not normalized_owner_user_id:
        return None
    return _DATABASE_REPOSITORY.get_user_settings(normalized_owner_user_id)


def set_user_model_training_preference(
    owner_user_id: str,
    *,
    allow_model_training: bool,
    updated_at: str,
) -> Any:
    normalized_owner_user_id = _normalize_user_id(owner_user_id)
    if not normalized_owner_user_id:
        raise ValueError("owner_user_id is required.")
    existing = _DATABASE_REPOSITORY.get_user_settings(normalized_owner_user_id)
    record = {
        "owner_user_id": normalized_owner_user_id,
        "model_training_opt_out": not allow_model_training,
        "created_at": getattr(existing, "created_at", None) or updated_at,
        "updated_at": updated_at,
    }
    return _DATABASE_REPOSITORY.upsert_user_settings(record)


def list_model_training_opt_out_user_ids() -> List[str]:
    """Return owner ids that dataset exports must exclude from model training."""

    return _DATABASE_REPOSITORY.list_model_training_opt_out_user_ids()


def get_database_config() -> Dict[str, Any]:
    config = _DATABASE_PROVIDER.describe()
    config["dev_mode"] = blueprint_dev_mode_enabled()
    return config
