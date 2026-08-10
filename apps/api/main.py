from pathlib import Path
from datetime import datetime, timedelta, timezone
import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import logging
import sys
import types
import urllib.parse
from typing import Any, Dict, List, Optional
from uuid import uuid4


def _ensure_api_package_imports() -> None:
    """Support Vercel loading apps/api/main.py as top-level main.py."""
    if "apps.api" in sys.modules:
        return

    current_dir = Path(__file__).resolve().parent
    if not (current_dir / "database.py").exists():
        return

    project_root = current_dir.parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    apps_package = types.ModuleType("apps")
    apps_package.__path__ = [str(current_dir.parent)]
    apps_package.__file__ = str(current_dir.parent / "__init__.py")
    apps_package.__package__ = "apps"
    sys.modules["apps"] = apps_package

    api_package = types.ModuleType("apps.api")
    api_package.__path__ = [str(current_dir)]
    api_package.__file__ = str(current_dir / "__init__.py")
    api_package.__package__ = "apps.api"
    sys.modules["apps.api"] = api_package
    sys.modules.setdefault("apps.api.main", sys.modules[__name__])
    setattr(apps_package, "api", api_package)
    setattr(api_package, "main", sys.modules[__name__])


_ensure_api_package_imports()

from blueprint_core.debug import (
    api_error_detail,
    debug_mode_enabled,
    exception_debug_payload,
    get_debug_mode_config,
    runtime_safe_error_message,
)
from fastapi import Body, Depends, FastAPI, HTTPException, Query, WebSocket, status
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")
load_dotenv(Path(__file__).resolve().parent / ".env", override=False)

from blueprint_core.user_integrations import UserIntegrationStore, apply_user_integrations_to_environment, require_user_secrets_key
from blueprint_core.vertex_auth import VercelOidcContextMiddleware

apply_user_integrations_to_environment()

from apps.api.logging_config import configure_backend_logging

configure_backend_logging()

from blueprint_core.database import (
    append_project_revision,
    DesignBriefNotFoundError,
    count_component_templates,
    delete_generated_project,
    delete_project_chat,
    ensure_project_action_allowed,
    get_database_config,
    get_generated_project,
    get_latest_design_brief,
    get_latest_project_revision,
    get_latest_project_deletion_audit,
    get_project_contribution_consent,
    get_project_chat,
    init_db,
    list_project_chats,
    list_component_templates,
    list_generated_projects,
    list_latest_project_revisions,
    list_project_deletion_audits,
    save_alpha_signup,
    update_generated_project_metadata,
    update_generated_project_hardware_ir,
    upsert_project_chat,
)
from blueprint_core.project_list_cache import (
    cache_project_list,
    get_cached_project_list,
    require_project_list_cache_config,
)
from apps.api.seed_db import seed_database
from blueprint_core.agents.workflows import get_workflow_debug_config, list_workflows
from blueprint_core.agents.clarification import ask_clarifying_questions
from blueprint_core.workspaces.chats.models import Chat, ChatUpsertRequest, ProjectChatUpsertRequest
from blueprint_core.workspaces.projects.models import (
    ClarifyingQuestionsRequest, ClarifyingQuestionsResponse, ComponentInstance,
    ConnectionNet, GenerateProjectRequest, HardwareIR, IterateProjectRequest,
    ProjectContributionConsentRequest, ProjectUpdateRequest, ValidationIssue, ValidationReport, VideoSelfCorrectRequest,
)
from blueprint_core.workspaces.projects import ProjectStateError
from blueprint_core.workspaces.workflow import WorkflowStateError
from blueprint_core.signups.models import AlphaSignupRequest, AlphaSignupResponse
from blueprint_core.agents.orchestrator import HardwarePipelineOrchestrator
from apps.api.a2a import (
    A2A_HUB,
    A2AAgentRegistration,
    A2AMessage,
    build_generation_response,
    get_a2a_capabilities,
    handle_a2a_websocket,
    handle_mcp_json_rpc,
    start_a2a_tcp_server,
    stop_a2a_tcp_server,
    submit_a2a_message,
)
from blueprint_core.images import get_image_output_debug_config
from blueprint_core.config.contract import resolve_runtime_contract
from blueprint_core.workspaces.projects.iteration import ProjectIterator
from blueprint_core.llm import LLMProviderConfigError
from blueprint_core.llm import LLMProviderOutputError
from blueprint_core.workspaces.projects.objects import build_project_object, list_project_namespaces
from blueprint_core.agents.pipeline import PipelineCancelledError, list_agent_pipeline_steps, observe_agent_pipeline, pipeline_workflow_id
from blueprint_core.video_prompts import generate_image_to_video_prompt_from_namespaces
from blueprint_core.agents.video_correction import FireworksVideoSelfCorrectionAgent
from blueprint_core.video_review import FireworksVideoReviewClient
from apps.api.logs_api import router as logs_router
from apps.api.streams_api import router as streams_router
from apps.api.design_briefs_api import router as design_briefs_router
from apps.api.context_gathering_api import router as context_gathering_router
from apps.api.project_workflow_api import router as project_workflow_router
from apps.api.readiness_api import router as readiness_router
from apps.api.worker_plans_api import router as worker_plans_router
from apps.api.user_integrations_api import router as user_integrations_router
from apps.api.user_settings_api import router as user_settings_router
from apps.api.auth import (
    UserContext,
    clerk_user_profile,
    deployed_auth_required,
    optional_user_context,
    require_admin_user_context,
    require_destructive_user_context,
    require_user_context,
)
from apps.api.project_deletion import (
    DELETION_POLICY_VERSION,
    PERMITTED_CONTRIBUTION_PURPOSES,
    deletion_metrics,
    grant_contribution_consent,
    purge_worker,
    request_project_deletion,
    restore_project,
    withdraw_contribution,
)
from blueprint_core.jobs.store import JOB_STORE, JobCancelledError
from blueprint_core.jobs.context import PAST_JOBS_DATA_SOURCE, PastJobContextSource, list_generation_data_sources
from blueprint_core.observability import flush_langfuse, get_langfuse_debug_config
from blueprint_core.runtime import (
    ALPHA_GENERATION_UNAVAILABLE_MESSAGE,
    AlphaGenerationUnavailableError,
    deployment_runtime_config,
    generation_unavailable_detail,
)
from blueprint_core.config.runtime import blueprint_dev_mode_enabled
from apps.api.storage import get_image_storage_config, hydrate_image_storage_metadata
from blueprint_core.validation import validate_circuit
from blueprint_core.utils import generate_mermaid_chart, generate_svg_schematic
from apps.api.video_providers import (
    GMICloudProvider,
    VIDEO_MODE_IMAGE_TO_VIDEO,
    VIDEO_MODE_VIDEO_TO_VIDEO,
    get_available_video_aspect_ratios,
    get_available_video_model_options,
    get_available_video_models,
    get_default_video_model,
    normalize_video_aspect_ratio,
    normalize_video_mode,
)
from apps.api.video_storage import (
    ensure_video_storage_configured,
    get_video_storage_config,
    list_project_videos,
    upload_generated_videos_to_s3,
)

logger = logging.getLogger(__name__)
ROOT_DIR = REPO_ROOT
EXAMPLE_RESULTS_DIR = ROOT_DIR / "examples" / "results"
_CACHE_OWNER_DIGEST_FIELD = "_blueprint_cache_owner_digest"
_CACHE_OWNER_CHAT_FIELD = "_blueprint_cache_owner_chat_id"


def _parse_job_timestamp(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _generation_duration_seconds(job: Optional[Dict[str, Any]]) -> Optional[int]:
    if not job:
        return None
    started_at = _parse_job_timestamp(job.get("started_at"))
    completed_at = _parse_job_timestamp(job.get("completed_at"))
    if not started_at or not completed_at or completed_at < started_at:
        return None
    return max(1, round((completed_at - started_at).total_seconds()))


def _attach_generation_timing_metadata(response: Dict[str, Any], job: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    duration_seconds = _generation_duration_seconds(job)
    if duration_seconds is None:
        return response

    project_ir = response.get("project_ir")
    if not isinstance(project_ir, dict):
        return response

    metadata = project_ir.get("assembly_metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    project_ir["assembly_metadata"] = {
        **metadata,
        "total_generation_time_seconds": duration_seconds,
        "total_generation_started_at": job.get("started_at") if job else None,
        "total_generation_completed_at": job.get("completed_at") if job else None,
    }
    return response

app = FastAPI(
    title="Forma Open-Source API",
    description="AI-native prompt-to-hardware compilation, validation, and design generation platform.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    swagger_ui_oauth2_redirect_url="/docs/oauth2-redirect",
)

_project_purge_stop_event: Optional[asyncio.Event] = None
_project_purge_task: Optional[asyncio.Task[Any]] = None


class ApiPrefixCompatibilityMiddleware:
    """Accept /api-prefixed requests when the service receives the full public path."""

    def __init__(self, app: Any, prefix: str = "/api") -> None:
        self.app = app
        self.prefix = prefix

    async def __call__(self, scope: Dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") in {"http", "websocket"}:
            path = scope.get("path", "")
            if path == self.prefix:
                scope = dict(scope)
                scope["path"] = "/"
                scope["root_path"] = f"{scope.get('root_path', '').rstrip('/')}{self.prefix}"
            elif path.startswith(f"{self.prefix}/"):
                scope = dict(scope)
                scope["path"] = path[len(self.prefix):] or "/"
                scope["root_path"] = f"{scope.get('root_path', '').rstrip('/')}{self.prefix}"

        await self.app(scope, receive, send)


app.add_middleware(ApiPrefixCompatibilityMiddleware)
app.add_middleware(VercelOidcContextMiddleware)

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In development, allow all. Can narrow in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(logs_router, dependencies=[Depends(require_admin_user_context)])
app.include_router(streams_router, dependencies=[Depends(require_admin_user_context)])
app.include_router(design_briefs_router)
app.include_router(context_gathering_router)
app.include_router(project_workflow_router)
app.include_router(readiness_router)
app.include_router(worker_plans_router)
app.include_router(user_integrations_router)
app.include_router(user_settings_router)


def _deployment_runtime_config(llm_config: Dict[str, Any]) -> Dict[str, Any]:
    return deployment_runtime_config(llm_config, signup_storage=get_database_config()["client"])


def _resolved_client_runtime_config() -> tuple[Dict[str, Any], Dict[str, Any]]:
    llm_config = HardwarePipelineOrchestrator().get_debug_config()
    image_config = get_image_output_debug_config()
    contract = resolve_runtime_contract(
        llm_config=llm_config,
        image_config=image_config,
        workflows=list_workflows(),
        signup_storage=get_database_config()["client"],
    )
    contract["video"] = {
        "generation": GMICloudProvider().get_debug_config(),
        "self_correction": FireworksVideoReviewClient().get_debug_config(),
    }
    return llm_config, contract


def _apply_user_integrations(user: UserContext) -> None:
    """Load provider settings only for operations that consume them."""
    if user.provider == "local":
        apply_user_integrations_to_environment()
    elif user.owner_user_id:
        apply_user_integrations_to_environment(UserIntegrationStore.for_user(user.owner_user_id))


def _job_owner_user_id(job: Optional[Dict[str, Any]]) -> Optional[str]:
    payload = job.get("payload") if isinstance(job, dict) else None
    value = payload.get("owner_user_id") if isinstance(payload, dict) else None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _admin_job_records(jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Add admin-only owner labels without changing the persisted job shape."""
    records = [dict(job) for job in jobs]
    owner_user_ids: List[str] = []

    for record in records:
        owner_user_id = _job_owner_user_id(record)
        record["owner_user_id"] = owner_user_id
        if owner_user_id and owner_user_id not in owner_user_ids:
            owner_user_ids.append(owner_user_id)

    # Clerk lookups are optional display enrichment. Cap and parallelize cold
    # lookups so a large job list cannot hold the admin request open.
    profile_user_ids = owner_user_ids[:16]
    if profile_user_ids:
        with ThreadPoolExecutor(max_workers=min(8, len(profile_user_ids))) as executor:
            resolved_profiles = executor.map(clerk_user_profile, profile_user_ids)
            profiles = dict(zip(profile_user_ids, resolved_profiles))
    else:
        profiles = {}

    for record in records:
        owner_user_id = record.get("owner_user_id")
        profile = profiles.get(owner_user_id) if isinstance(owner_user_id, str) else None
        display_name = profile.get("display_name") if profile else None
        email = profile.get("email") if profile else None
        github_username = profile.get("github_username") if profile else None
        record["owner_display_name"] = display_name
        record["owner_email"] = email
        record["owner_github_username"] = github_username
        record["owner_username"] = github_username or email or display_name or owner_user_id

    return records


def _require_job_reader(job: Dict[str, Any], user: UserContext) -> None:
    if user.is_admin:
        return
    owner_user_id = _job_owner_user_id(job)
    if owner_user_id and owner_user_id == user.owner_user_id:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only view your own jobs.")


def _delete_cancelled_generation_projects(job_id: str, job: Optional[Dict[str, Any]] = None) -> None:
    """Remove project artifacts persisted by a worker after its job was cancelled."""
    current_job = job or JOB_STORE.get_job(job_id) or {}
    owner_user_id = _job_owner_user_id(current_job)
    if not owner_user_id:
        return
    deleted_chats: List[tuple[str, str]] = []
    for project in list_generated_projects(owner_user_id=owner_user_id):
        hardware_ir = getattr(project, "hardware_ir", None)
        project_id = getattr(project, "project_id", None)
        if not isinstance(hardware_ir, dict) or not isinstance(project_id, str):
            continue
        metadata = hardware_ir.get("assembly_metadata")
        if not isinstance(metadata, dict) or metadata.get("frontend_job_id") != job_id:
            continue
        if delete_generated_project(project_id, owner_user_id):
            chat_id = getattr(project, "chat_id", None)
            title = getattr(project, "title", None)
            if isinstance(chat_id, str) and isinstance(title, str):
                deleted_chats.append((chat_id, title))
            logger.info("Removed project %s created after cancelled job %s.", project_id, job_id)

    payload = current_job.get("payload") if isinstance(current_job.get("payload"), dict) else {}
    prompt_title = str(payload.get("prompt") or "").splitlines()[0].strip()[:80] or "Cancelled project"
    for chat_id, deleted_title in deleted_chats:
        chat = get_project_chat(chat_id, owner_user_id)
        if not chat or getattr(chat, "title", None) != deleted_title:
            continue
        upsert_project_chat(
            chat_id=chat_id,
            owner_user_id=owner_user_id,
            title=prompt_title,
            messages=getattr(chat, "messages", None) or [],
            created_at=getattr(chat, "created_at", None) or datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )


# Initialize and seed database on startup
@app.on_event("startup")
async def startup_event():
    global _project_purge_stop_event, _project_purge_task
    logger.info("Starting up Forma server...")
    require_user_secrets_key()
    require_project_list_cache_config()
    logger.info("Authentication mode: %s", "clerk" if deployed_auth_required() else "local")
    try:
        init_db()
        count = count_component_templates()
        if count == 0:
            logger.info("Database empty. Seeding templates automatically...")
            seed_database()
        else:
            logger.info("Database ready with %s component templates.", count)
    except Exception as e:
        logger.exception("Error during database startup: %s", e)
        raise
    await start_a2a_tcp_server()
    _project_purge_stop_event = asyncio.Event()
    _project_purge_task = asyncio.create_task(
        purge_worker(_project_purge_stop_event),
        name="project-retention-purge-worker",
    )


@app.on_event("shutdown")
async def shutdown_event():
    global _project_purge_stop_event, _project_purge_task
    if _project_purge_stop_event is not None:
        _project_purge_stop_event.set()
    if _project_purge_task is not None:
        await _project_purge_task
    _project_purge_stop_event = None
    _project_purge_task = None
    await stop_a2a_tcp_server()
    flush_langfuse()

@app.get("/")
def read_root():
    return {
        "status": "online",
        "service": "Forma Open-Source Hardware Compiler",
        "version": "1.0.0",
        "docs_url": "/api/docs"
    }


@app.get("/admin/session")
def admin_session_endpoint(user: UserContext = Depends(optional_user_context)):
    """Reports whether the current signed-in user has Forma admin access."""
    return {
        "is_admin": user.is_admin,
        "user_id": user.owner_user_id,
        "provider": user.provider,
    }


@app.get("/debug/config")
def debug_config_endpoint(
    provider: Optional[str] = Query(None, description="Optional runtime LLM provider override to validate."),
    model: Optional[str] = Query(None, description="Optional runtime LLM model override to validate."),
    user: UserContext = Depends(optional_user_context),
):
    """
    Reports LLM provider and model resolution state without exposing credentials.
    """
    _apply_user_integrations(user)
    try:
        orchestrator = HardwarePipelineOrchestrator(provider_name=provider, model_name=model)
        llm_config = orchestrator.get_debug_config()
        return {
            **llm_config,
            "blueprint_dev_mode": blueprint_dev_mode_enabled(),
            "deployment": _deployment_runtime_config(llm_config),
            "database": get_database_config(),
            "job_metadata": JOB_STORE.get_config(),
            "image_output": get_image_output_debug_config(),
            "image_storage": get_image_storage_config(),
            "observability": get_langfuse_debug_config(),
            "debug": get_debug_mode_config(),
            "video_generation": GMICloudProvider().get_debug_config(),
            "video_self_correction": FireworksVideoReviewClient().get_debug_config(),
            "video_storage": get_video_storage_config(),
            "workflows": list_workflows(),
            "data_sources": list_generation_data_sources(),
            "project_namespaces": [namespace.model_dump(mode="json") for namespace in list_project_namespaces()],
        }
    except LLMProviderConfigError as e:
        raise HTTPException(
            status_code=400,
            detail=api_error_detail(code="llm_config_invalid", message=str(e), exc=e, provider=provider, model=model),
        ) from e
    except Exception as e:
        logger.exception("Debug config failed.")
        raise HTTPException(
            status_code=500,
            detail=api_error_detail(code="debug_config_failed", message=f"Debug config failed: {str(e)}", exc=e),
        ) from e


@app.get("/runtime/config")
def runtime_config_endpoint(user: UserContext = Depends(optional_user_context)):
    """Return the canonical, credential-safe runtime contract for this user."""
    _apply_user_integrations(user)
    try:
        _, contract = _resolved_client_runtime_config()
        return contract
    except LLMProviderConfigError as e:
        raise HTTPException(
            status_code=400,
            detail=api_error_detail(code="llm_config_invalid", message=str(e), exc=e),
        ) from e
    except Exception as e:
        logger.exception("Runtime config resolution failed.")
        raise HTTPException(
            status_code=500,
            detail=api_error_detail(code="runtime_config_failed", message=f"Runtime config failed: {str(e)}", exc=e),
        ) from e

@app.post("/generate", response_model=Dict[str, Any])
async def generate_project_endpoint(request: GenerateProjectRequest, user: UserContext = Depends(require_user_context)):
    """
    Submits a natural language hardware idea and optional multimodal reference image.
    Runs the 7-agent compilation workflow, circuit safety auditor, and returns a verified Hardware IR, SVG schematic, and Mermaid diagram.
    """
    owner_user_id = _require_authenticated_user(user)
    if request.project_id:
        try:
            ensure_project_action_allowed(
                request.project_id,
                owner_user_id,
                "blueprint.generate_project",
                require_workflow=True,
            )
        except WorkflowStateError as exc:
            status_code = status.HTTP_404_NOT_FOUND if exc.code == "workflow_not_found" else status.HTTP_409_CONFLICT
            raise HTTPException(status_code=status_code, detail=exc.as_dict()) from exc
    _apply_user_integrations(user)
    try:
        llm_config = get_workflow_debug_config(
            request.workflow,
            provider_name=request.provider,
            model_name=request.model,
            external_source_provider=request.external_source_provider,
        )
    except LLMProviderConfigError as e:
        raise HTTPException(
            status_code=400,
            detail=api_error_detail(
                code="llm_config_invalid",
                message=str(e),
                exc=e,
                provider=request.provider,
                model=request.model,
                context={
                    "workflow": request.workflow,
                    "generate_image": request.generate_image,
                    "external_source_provider": request.external_source_provider,
                },
            ),
        ) from e
    deployment_config = _deployment_runtime_config(llm_config)
    if deployment_config["alpha_generation_gate_active"]:
        detail = generation_unavailable_detail(llm_config)
        logger.warning(
            "Generation unavailable for provider=%s model=%s: %s",
            detail.get("provider"),
            detail.get("model"),
            detail.get("reason") or detail.get("message"),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
        )

    if not (request.prompt or "").strip() and not request.image_data:
        message = "Provide a prompt or reference image."
        detail = (
            api_error_detail(
                code="generation_input_invalid",
                message=message,
                provider=request.provider,
                model=request.model,
                context={
                    "workflow": request.workflow,
                    "has_image": bool(request.image_data),
                    "external_source_provider": request.external_source_provider,
                },
            )
            if debug_mode_enabled()
            else message
        )
        raise HTTPException(status_code=400, detail=detail)

    job_id = request.client_job_id or f"job_frontend_{uuid4().hex}"
    message_id = f"msg_{uuid4().hex}"
    if request.source_project_id:
        source_project = get_generated_project(request.source_project_id)
        if not source_project:
            raise HTTPException(status_code=404, detail="Source project not found.")
        _require_project_chat_owner(source_project, user)
    payload = {
        "prompt": request.prompt,
        "project_id": request.project_id,
        "workflow": request.workflow,
        "image_data": request.image_data,
        "generate_image": request.generate_image,
        "provider": request.provider,
        "model": request.model,
        "chat_id": request.chat_id,
        "source_project_id": request.source_project_id,
        "client_job_id": request.client_job_id,
        "owner_user_id": owner_user_id,
        "external_source_provider": request.external_source_provider,
        "data_sources": request.data_sources,
        "past_jobs_limit": request.past_jobs_limit,
    }
    JOB_STORE.create_job(
        job_id=job_id,
        message_id=message_id,
        correlation_id=None,
        action="blueprint.generate_project",
        sender="frontend",
        recipient="blueprint",
        payload=payload,
        server_owned=True,
        status="queued",
    )
    JOB_STORE.mark_running(job_id)

    try:
        past_job_context = None
        if PAST_JOBS_DATA_SOURCE in request.data_sources:
            past_job_context = await PastJobContextSource(JOB_STORE, get_generated_project).retrieve(
                request.prompt,
                owner_user_id=owner_user_id,
                limit=request.past_jobs_limit,
                exclude_job_id=job_id,
            )
        with observe_agent_pipeline(
            lambda event: JOB_STORE.append_progress_event(job_id, event.as_dict()),
            cancellation_check=lambda: JOB_STORE.is_cancelled(job_id),
        ):
            response = await asyncio.to_thread(
                build_generation_response,
                request.prompt,
                request.image_data,
                generate_image=request.generate_image,
                workflow=request.workflow,
                provider=request.provider,
                model=request.model,
                external_source_provider=request.external_source_provider,
                chat_id=request.chat_id,
                source_project_id=request.source_project_id,
                frontend_job_id=job_id,
                owner_user_id=owner_user_id,
                data_sources=request.data_sources,
                past_job_context=past_job_context,
                project_id=request.project_id,
            )
        if JOB_STORE.is_cancelled(job_id):
            raise JobCancelledError(f"Job {job_id} was cancelled.")
        JOB_STORE.mark_succeeded(job_id, response)
        job = JOB_STORE.get_job(job_id)
        if str((job or {}).get("status") or "").lower() in {"cancelled", "canceled"}:
            raise JobCancelledError(f"Job {job_id} was cancelled.")
        response = _attach_generation_timing_metadata(response, job)
        metadata = (response.get("project_ir", {}).get("assembly_metadata") or {})
        project_id = metadata.get("project_id")
        if project_id and isinstance(response.get("project_ir"), dict):
            try:
                update_generated_project_hardware_ir(project_id, response["project_ir"])
            except Exception:
                logger.warning("Failed to persist generation timing metadata for project_id=%s", project_id, exc_info=debug_mode_enabled())
        return {
            **response,
            "project_id": project_id,
            "chat_id": metadata.get("chat_id"),
            "can_chat": True,
            "job_id": job_id,
            "job": job,
        }
    except PipelineCancelledError as e:
        JOB_STORE.mark_cancelled(job_id)
        _delete_cancelled_generation_projects(job_id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=api_error_detail(
                code="generation_cancelled",
                message="Generation was stopped by the user.",
                exc=e,
                job_id=job_id,
                provider=request.provider,
                model=request.model,
            ),
        ) from e
    except ValueError as e:
        error_debug = exception_debug_payload(e, context=payload) if debug_mode_enabled() else None
        JOB_STORE.mark_failed(job_id, runtime_safe_error_message(str(e), provider=request.provider, model=request.model), error_debug)
        logger.warning("Generation request rejected for job_id=%s: %s", job_id, e, exc_info=debug_mode_enabled())
        raise HTTPException(
            status_code=400,
            detail=api_error_detail(
                code="generation_request_invalid",
                message=str(e),
                exc=e,
                job_id=job_id,
                provider=request.provider,
                model=request.model,
                context=payload,
            ),
        ) from e
    except LLMProviderConfigError as e:
        error_debug = exception_debug_payload(e, context=payload) if debug_mode_enabled() else None
        JOB_STORE.mark_failed(job_id, runtime_safe_error_message(str(e), provider=request.provider, model=request.model), error_debug)
        logger.warning("Generation LLM config failed for job_id=%s: %s", job_id, e, exc_info=debug_mode_enabled())
        raise HTTPException(
            status_code=400,
            detail=api_error_detail(
                code="llm_config_invalid",
                message=str(e),
                exc=e,
                job_id=job_id,
                provider=request.provider,
                model=request.model,
                context=payload,
            ),
        ) from e
    except LLMProviderOutputError as e:
        error_debug = exception_debug_payload(e, context=payload) if debug_mode_enabled() else None
        JOB_STORE.mark_failed(job_id, runtime_safe_error_message(str(e), provider=request.provider, model=request.model), error_debug)
        logger.warning(
            "LLM output rejected for job_id=%s provider=%s model=%s: %s",
            job_id,
            request.provider,
            request.model,
            e,
            exc_info=debug_mode_enabled(),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=api_error_detail(
                code="llm_output_invalid",
                message=str(e),
                exc=e,
                job_id=job_id,
                provider=request.provider,
                model=request.model,
                context=payload,
            ),
        ) from e
    except AlphaGenerationUnavailableError as e:
        error_debug = exception_debug_payload(e, context=payload) if debug_mode_enabled() else None
        JOB_STORE.mark_failed(job_id, runtime_safe_error_message(str(e), provider=request.provider, model=request.model), error_debug)
        code = "alpha_generation_unavailable" if str(e) == ALPHA_GENERATION_UNAVAILABLE_MESSAGE else "llm_generation_unavailable"
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=api_error_detail(
                code=code,
                message=str(e),
                exc=e,
                job_id=job_id,
                provider=request.provider,
                model=request.model,
                context=payload,
            ),
        ) from e
    except Exception as e:
        error_debug = exception_debug_payload(e, context=payload) if debug_mode_enabled() else None
        JOB_STORE.mark_failed(job_id, runtime_safe_error_message(str(e), provider=request.provider, model=request.model), error_debug)
        logger.exception("Generation failed for job_id=%s provider=%s model=%s", job_id, request.provider, request.model)
        raise HTTPException(
            status_code=500,
            detail=api_error_detail(
                code="generation_failed",
                message=f"Generation failed: {str(e)}",
                exc=e,
                job_id=job_id,
                provider=request.provider,
                model=request.model,
                context=payload,
            ),
        ) from e


@app.get("/workflows")
def list_generation_workflows_endpoint():
    """List generation workflows available to frontend and CLI clients."""
    return list_workflows()


@app.get("/data-sources")
def list_generation_data_sources_endpoint():
    """List optional lightweight context sources available during generation."""
    return list_generation_data_sources()


@app.get("/pipeline/steps")
def list_agent_pipeline_steps_endpoint(
    workflow: Optional[str] = Query(None, description="Generation workflow id, for example default or web_research."),
    include_image: bool = Query(False, description="Include optional product image generation stage."),
):
    """List public, user-safe agent pipeline stages for the selected workflow."""
    return {
        "workflow": pipeline_workflow_id(workflow),
        "include_image": include_image,
        "steps": list_agent_pipeline_steps(workflow, include_image=include_image),
    }


@app.post("/clarifying-questions", response_model=ClarifyingQuestionsResponse)
def clarifying_questions_endpoint(request: ClarifyingQuestionsRequest):
    """Run the core Context Clarifier Agent before starting a generation job."""
    return ask_clarifying_questions(request)


class VideoImageToVideoRequest(BaseModel):
    projectId: str | None = None
    image: str | None = None
    prompt: str | None = None
    model: str | None = None
    duration: str | None = "5"
    aspectRatio: str | None = None
    aspect_ratio: str | None = None
    sound: str | None = "off"


class VideoToVideoRequest(BaseModel):
    projectId: str | None = None
    video: str | None = None
    prompt: str | None = None
    model: str | None = None
    duration: str | None = "5"
    aspectRatio: str | None = None
    aspect_ratio: str | None = None
    sound: str | None = "off"


VIDEO_FAILED_STATUSES = {"failed", "failure", "error", "cancelled", "canceled"}
VIDEO_SUCCESS_STATUSES = {"success", "succeeded", "completed", "complete", "done"}


def _normalize_video_model(model: str | None, mode: str = VIDEO_MODE_IMAGE_TO_VIDEO) -> str:
    normalized_mode = normalize_video_mode(mode)
    normalized = (model or get_default_video_model(normalized_mode)).strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="Video model is required.")
    allowed_models = get_available_video_models(normalized_mode)
    if normalized not in allowed_models:
        raise HTTPException(status_code=400, detail=f"Unsupported {normalized_mode} model '{normalized}'.")
    return normalized


def _normalize_video_request_aspect_ratio(aspect_ratio: str | None) -> str:
    try:
        return normalize_video_aspect_ratio(aspect_ratio)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _require_non_empty(value: str | None, message: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail=message)
    return normalized


def _require_authenticated_user(user: UserContext) -> str:
    if user.is_authenticated and user.owner_user_id:
        return user.owner_user_id
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in to manage projects and chats.")


def _project_owner_user_id(project: Any) -> Optional[str]:
    value = getattr(project, "owner_user_id", None)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _project_visibility(project: Any) -> str:
    value = getattr(project, "visibility", "public")
    normalized = str(value or "public").strip().lower()
    return normalized if normalized in {"public", "private"} else "public"


def _user_owns_project(project: Any, user: UserContext) -> bool:
    return bool(user.owner_user_id and _project_owner_user_id(project) == user.owner_user_id)


def _require_project_reader(project: Any, user: UserContext) -> None:
    if _project_visibility(project) == "public" or _user_owns_project(project, user):
        return
    # Do not reveal that another user's private project exists.
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")


def creator_display_name(owner_user_id: Optional[str]) -> str:
    if not owner_user_id:
        return "unknown"
    normalized = owner_user_id.strip()
    if normalized == "local-dev-user":
        return "local_dev"
    if len(normalized) <= 12:
        return normalized
    return f"{normalized[:6]}_{normalized[-4:]}"


def _require_project_owner(project: Any, user: UserContext) -> str:
    user_id = _require_authenticated_user(user)
    owner_user_id = _project_owner_user_id(project)
    if owner_user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only modify your own projects.")
    return user_id


def _require_project_chat_owner(project: Any, user: UserContext) -> str:
    user_id = _require_authenticated_user(user)
    owner_user_id = _project_owner_user_id(project)
    if owner_user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only chat with your own projects.")
    return user_id


def _store_video_results(
    result: Any,
    *,
    project_id: str,
    model: str,
    prompt: str | None = None,
    mode: str | None = None,
    aspect_ratio: str | None = None,
    source_url: str | None = None,
) -> List[Dict[str, Any]]:
    if not result.video_urls:
        return []
    try:
        stored_videos = upload_generated_videos_to_s3(
            result.video_urls,
            project_id=project_id,
            request_id=result.request_id,
            model=model,
            prompt=prompt,
            mode=mode,
            aspect_ratio=aspect_ratio,
            source_url=source_url,
        )
        return [stored_video.response_metadata() for stored_video in stored_videos]
    except Exception as exc:
        logger.exception(
            "Generated video S3 upload failed for project_id=%s request_id=%s source_urls=%s",
            project_id,
            result.request_id,
            result.video_urls,
        )
        raise HTTPException(
            status_code=502,
            detail=f"S3 upload failed for video request {result.request_id}: {str(exc)}",
        ) from exc


def _raise_if_completed_without_video(result: Any) -> None:
    if result.status in VIDEO_SUCCESS_STATUSES and not result.video_urls:
        raise HTTPException(
            status_code=502,
            detail=f"GMI Cloud video request {result.request_id} completed without a video URL.",
        )


def _video_route_response(
    result: Any,
    *,
    project_id: str,
    model: str,
    saved_videos: List[Dict[str, Any]],
    aspect_ratio: str | None = None,
    prompt: str | None = None,
    mode: str | None = None,
) -> Dict[str, Any]:
    return {
        "projectId": project_id,
        "requestId": result.request_id,
        "status": result.status,
        "model": model,
        "mode": mode,
        "prompt": prompt,
        "aspectRatio": aspect_ratio,
        "aspect_ratio": aspect_ratio,
        "source": "gmi-cloud",
        "videoUrls": result.video_urls,
        "savedVideos": saved_videos,
        "storedVideo": saved_videos[0] if saved_videos else None,
    }


@app.get("/video/models")
def list_video_models_endpoint():
    """Returns the backend-approved video generation models."""
    models = get_available_video_model_options()
    default_model = get_default_video_model(VIDEO_MODE_IMAGE_TO_VIDEO)
    default_video_to_video_model = get_default_video_model(VIDEO_MODE_VIDEO_TO_VIDEO)
    provider_config = GMICloudProvider().get_debug_config()
    return {
        "models": [model.response_metadata() for model in models],
        "defaultModel": default_model,
        "default_model": default_model,
        "defaultVideoToVideoModel": default_video_to_video_model,
        "default_video_to_video_model": default_video_to_video_model,
        "aspectRatioOptions": get_available_video_aspect_ratios(),
        "aspect_ratio_options": get_available_video_aspect_ratios(),
        "generationConfigured": provider_config["configured"],
        "generation_configured": provider_config["configured"],
        "reason": provider_config.get("reason"),
    }


@app.get("/video/projects/{project_id}")
def list_project_videos_endpoint(project_id: str, user: UserContext = Depends(require_user_context)):
    """Lists videos saved for one project from configured backend storage."""
    project_id = _require_non_empty(project_id, "projectId is required.")
    project = get_generated_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    _require_project_owner(project, user)
    try:
        videos = list_project_videos(project_id)
        return {
            "projectId": project_id,
            "videos": [video.response_metadata() for video in videos],
        }
    except Exception as exc:
        logger.exception("Video gallery list failed for project_id=%s", project_id)
        raise HTTPException(status_code=500, detail=f"Video gallery failed: {str(exc)}") from exc


@app.post("/video/image-to-video")
def create_image_to_video_endpoint(request: VideoImageToVideoRequest, user: UserContext = Depends(require_user_context)):
    """Queues a backend-only GMI Cloud image-to-video generation request."""
    project_id = _require_non_empty(request.projectId, "projectId is required.")
    project = get_generated_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    _require_project_owner(project, user)
    image = _require_non_empty(request.image, "image is required.")
    prompt = _require_non_empty(request.prompt, "prompt is required.")
    model = _normalize_video_model(request.model, VIDEO_MODE_IMAGE_TO_VIDEO)
    duration = _require_non_empty(request.duration, "duration is required.")
    aspect_ratio = _normalize_video_request_aspect_ratio(request.aspectRatio or request.aspect_ratio)
    sound = "on" if (request.sound or "").strip().lower() == "on" else "off"

    try:
        ensure_video_storage_configured()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    provider = GMICloudProvider()
    try:
        result = provider.create_image_to_video(
            image=image,
            prompt=prompt,
            model=model,
            duration=duration,
            aspect_ratio=aspect_ratio,
            sound=sound,
        )
    except Exception as exc:
        logger.exception("GMI Cloud image-to-video create failed for project_id=%s model=%s", project_id, model)
        status_code = 500 if "API key is missing" in str(exc) else 502
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    if result.status in VIDEO_FAILED_STATUSES:
        raise HTTPException(status_code=502, detail=f"GMI Cloud video request failed with status '{result.status}'.")
    _raise_if_completed_without_video(result)

    saved_videos = _store_video_results(
        result,
        project_id=project_id,
        model=model,
        prompt=prompt,
        mode=VIDEO_MODE_IMAGE_TO_VIDEO,
        aspect_ratio=aspect_ratio,
        source_url=image,
    )
    return _video_route_response(
        result,
        project_id=project_id,
        model=model,
        saved_videos=saved_videos,
        aspect_ratio=aspect_ratio,
        prompt=prompt,
        mode=VIDEO_MODE_IMAGE_TO_VIDEO,
    )


@app.post("/video/video-to-video")
def create_video_to_video_endpoint(request: VideoToVideoRequest, user: UserContext = Depends(require_user_context)):
    """Queues a backend-only GMI Cloud video-to-video generation request."""
    project_id = _require_non_empty(request.projectId, "projectId is required.")
    project = get_generated_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    _require_project_owner(project, user)
    video = _require_non_empty(request.video, "video is required.")
    prompt = _require_non_empty(request.prompt, "prompt is required.")
    model = _normalize_video_model(request.model, VIDEO_MODE_VIDEO_TO_VIDEO)
    duration = _require_non_empty(request.duration, "duration is required.")
    aspect_ratio = _normalize_video_request_aspect_ratio(request.aspectRatio or request.aspect_ratio)
    sound = "on" if (request.sound or "").strip().lower() == "on" else "off"

    try:
        ensure_video_storage_configured()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    provider = GMICloudProvider()
    try:
        result = provider.create_video_to_video(
            video=video,
            prompt=prompt,
            model=model,
            duration=duration,
            aspect_ratio=aspect_ratio,
            sound=sound,
        )
    except Exception as exc:
        logger.exception("GMI Cloud video-to-video create failed for project_id=%s model=%s", project_id, model)
        status_code = 500 if "API key is missing" in str(exc) else 502
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    if result.status in VIDEO_FAILED_STATUSES:
        raise HTTPException(status_code=502, detail=f"GMI Cloud video request failed with status '{result.status}'.")
    _raise_if_completed_without_video(result)

    saved_videos = _store_video_results(
        result,
        project_id=project_id,
        model=model,
        prompt=prompt,
        mode=VIDEO_MODE_VIDEO_TO_VIDEO,
        aspect_ratio=aspect_ratio,
        source_url=video,
    )
    return _video_route_response(
        result,
        project_id=project_id,
        model=model,
        saved_videos=saved_videos,
        aspect_ratio=aspect_ratio,
        prompt=prompt,
        mode=VIDEO_MODE_VIDEO_TO_VIDEO,
    )


@app.get("/video/image-to-video/status/{request_id}")
def get_image_to_video_status_endpoint(
    request_id: str,
    projectId: str | None = Query(None, description="Project id that owns this video generation request."),
    model: str | None = None,
    mode: str | None = Query(VIDEO_MODE_IMAGE_TO_VIDEO, description="Video generation mode."),
    prompt: str | None = Query(None, description="Prompt used for the original video request."),
    aspectRatio: str | None = Query(None, description="Aspect ratio used for the original video request."),
    sourceUrl: str | None = Query(None, description="Source image or video URL used for the original video request."),
    user: UserContext = Depends(require_user_context),
):
    """Polls GMI Cloud for a project-scoped video request and stores completed videos in S3."""
    request_id = _require_non_empty(request_id, "requestId is required.")
    project_id = _require_non_empty(projectId, "projectId is required.")
    project = get_generated_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    _require_project_owner(project, user)
    normalized_mode = normalize_video_mode(mode)
    model = _normalize_video_model(model, normalized_mode)
    aspect_ratio = _normalize_video_request_aspect_ratio(aspectRatio) if aspectRatio else None

    provider = GMICloudProvider()
    try:
        result = provider.get_request_status(request_id)
    except Exception as exc:
        logger.exception("GMI Cloud image-to-video status failed for project_id=%s request_id=%s model=%s", project_id, request_id, model)
        status_code = 500 if "API key is missing" in str(exc) else 502
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    if result.status in VIDEO_FAILED_STATUSES:
        raise HTTPException(status_code=502, detail=f"GMI Cloud video request failed with status '{result.status}'.")
    _raise_if_completed_without_video(result)

    saved_videos: List[Dict[str, Any]] = []
    if result.video_urls or result.status in VIDEO_SUCCESS_STATUSES:
        try:
            ensure_video_storage_configured()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        saved_videos = _store_video_results(
            result,
            project_id=project_id,
            model=model,
            prompt=prompt,
            mode=normalized_mode,
            aspect_ratio=aspect_ratio,
            source_url=sourceUrl,
        )

    return _video_route_response(
        result,
        project_id=project_id,
        model=model,
        saved_videos=saved_videos,
        aspect_ratio=aspect_ratio,
        prompt=prompt,
        mode=normalized_mode,
    )


@app.post("/alpha-signups", response_model=AlphaSignupResponse)
def alpha_signup_endpoint(request: AlphaSignupRequest):
    """
    Captures alpha access interest while deployed generation is unavailable.
    """
    try:
        llm_config = HardwarePipelineOrchestrator().get_debug_config()
        deployment_config = _deployment_runtime_config(llm_config)
        save_alpha_signup(
            name=request.name,
            email=request.email,
            organization=request.organization,
            additional_info=request.additional_info,
            source="web-alpha-gate",
            metadata={
                "deployment": deployment_config,
                "provider": llm_config.get("provider"),
                "requested_model": llm_config.get("requested_model"),
            },
            created_at=datetime.utcnow().isoformat() + "Z",
        )
        return AlphaSignupResponse(ok=True, message="Thanks. We will follow up when generation opens.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Signup failed: {str(e)}")


@app.get("/a2a/capabilities")
def a2a_capabilities_endpoint():
    """Advertises Forma's A2A transports, actions, and MCP tools."""
    return get_a2a_capabilities()


@app.put("/a2a/agents/{agent_id}")
async def register_a2a_agent(agent_id: str, registration: A2AAgentRegistration):
    """Registers an agent so it can receive queued A2A events."""
    record = registration.model_dump()
    record["agent_id"] = registration.agent_id or agent_id
    return await A2A_HUB.register(agent_id, record)


@app.post("/a2a/messages")
async def send_a2a_message(message: A2AMessage, user: UserContext = Depends(require_user_context)):
    """Submits an A2A message and queues an async result for the sender."""
    owner_user_id = user.owner_user_id
    if owner_user_id and message.action.startswith("blueprint."):
        message.payload = {**message.payload, "owner_user_id": owner_user_id}
    ack = await submit_a2a_message(message)
    return ack.model_dump()


@app.get("/a2a/agents/{agent_id}/events")
async def poll_a2a_events(
    agent_id: str,
    timeout: float = Query(25.0, ge=0.0, le=60.0),
    limit: int = Query(10, ge=1, le=100),
):
    """Long-polls queued A2A events for an agent."""
    events = await A2A_HUB.poll(agent_id, timeout=timeout, limit=limit)
    return [event.model_dump() for event in events]


@app.get("/a2a/jobs")
def list_a2a_jobs(
    sender: str | None = None,
    job_status: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    _user: UserContext = Depends(require_admin_user_context),
):
    """Lists persisted A2A job metadata."""
    return _admin_job_records(JOB_STORE.list_jobs(sender=sender, status=job_status, limit=limit))


@app.get("/a2a/jobs/{job_id}")
def get_a2a_job(job_id: str, user: UserContext = Depends(require_user_context)):
    """Fetches persisted metadata for one A2A job."""
    job = JOB_STORE.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="A2A job not found.")
    _require_job_reader(job, user)
    return job


@app.post("/a2a/jobs/{job_id}/cancel")
def cancel_a2a_job(job_id: str, user: UserContext = Depends(require_user_context)):
    """Stops a queued or running job owned by the current user."""
    job = JOB_STORE.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="A2A job not found.")
    _require_job_reader(job, user)
    cancelled_job = JOB_STORE.mark_cancelled(job_id) or job
    if str(cancelled_job.get("status") or "").lower() in {"cancelled", "canceled"}:
        _delete_cancelled_generation_projects(job_id, cancelled_job)
    return cancelled_job


def _parse_example_job_time(value: Any) -> datetime:
    if isinstance(value, str) and value.strip():
        normalized = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.fromtimestamp(0, tz=timezone.utc)


def _format_example_job_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _example_job_status(status_value: Any) -> str:
    normalized = str(status_value or "").strip().lower()
    if normalized in {"pass", "passed", "success", "succeeded", "completed"}:
        return "succeeded"
    if normalized in {"fail", "failed", "error"}:
        return "failed"
    if normalized in {"running", "queued"}:
        return normalized
    return "failed"


def _example_job_id(summary_path: Path, index: int, result: Dict[str, Any]) -> str:
    provider = str(result.get("provider") or "provider")
    model = str(result.get("model") or "model")
    raw = f"example_{summary_path.stem}_{index}_{provider}_{model}"
    return "".join(char if char.isalnum() else "_" for char in raw).strip("_")


def _example_operation_summary(operations: List[Dict[str, Any]]) -> Dict[str, Any]:
    counts = {"succeeded": 0, "failed": 0, "pending": 0, "not_requested": 0}
    for operation in operations:
        operation_status = str(operation.get("status") or "unknown")
        counts[operation_status] = counts.get(operation_status, 0) + 1
    return {
        "total": len(operations),
        "failed": counts.get("failed", 0),
        "succeeded": counts.get("succeeded", 0),
        "pending": counts.get("pending", 0),
        "not_requested": counts.get("not_requested", 0),
        "ok": counts.get("failed", 0) == 0,
    }


def _example_project_object_jobs(limit: int, status: Optional[str]) -> List[Dict[str, Any]]:
    if not EXAMPLE_RESULTS_DIR.exists():
        return []

    jobs: List[Dict[str, Any]] = []
    normalized_filter = None if not status or status == "all" else status
    summary_paths = sorted(
        (path for path in EXAMPLE_RESULTS_DIR.glob("*-summary.json") if not path.name.startswith("latest-")),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    for summary_path in summary_paths:
        try:
            summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("Skipping unreadable example project summary: %s", summary_path)
            continue

        run_id = str(summary_payload.get("run_id") or summary_path.stem.removesuffix("-summary"))
        completed_at = _parse_example_job_time(summary_payload.get("created_at"))
        results = summary_payload.get("results") if isinstance(summary_payload.get("results"), list) else []
        for index, result in enumerate(results):
            if not isinstance(result, dict):
                continue
            job_status = _example_job_status(result.get("status"))
            if normalized_filter and normalized_filter != job_status:
                continue

            duration_seconds = float(result.get("duration_seconds") or 0.0)
            started_at = completed_at - timedelta(seconds=max(0.0, duration_seconds))
            provider = result.get("runtime_provider") or result.get("provider")
            model = result.get("runtime_model") or result.get("model")
            project_operation = {
                "id": "example_project_object_generation",
                "label": "Project object generation",
                "status": "succeeded" if job_status == "succeeded" else "failed",
                "provider": provider,
                "model": model,
                "error": result.get("error"),
                "details": {
                    "version": result.get("version"),
                    "namespace_count": len(result.get("namespaces") or []),
                    "pipeline": result.get("pipeline"),
                },
            }
            operation_statuses = [project_operation]
            seen_operation_ids = {project_operation["id"]}
            saved_operations = result.get("operation_statuses")
            if isinstance(saved_operations, list):
                for saved_operation in saved_operations:
                    if not isinstance(saved_operation, dict):
                        continue
                    operation_id = str(saved_operation.get("id") or "")
                    if operation_id and operation_id in seen_operation_ids:
                        continue
                    if operation_id:
                        seen_operation_ids.add(operation_id)
                    operation_statuses.append(saved_operation)
            operation_summary = _example_operation_summary(operation_statuses)
            jobs.append(
                {
                    "job_id": _example_job_id(summary_path, index, result),
                    "message_id": f"example_{run_id}",
                    "correlation_id": run_id,
                    "action": "examples.project_object_generation",
                    "sender": "examples",
                    "recipient": "blueprint",
                    "status": job_status,
                    "server_owned": False,
                    "created_at": _format_example_job_time(started_at),
                    "updated_at": _format_example_job_time(completed_at),
                    "started_at": _format_example_job_time(started_at),
                    "completed_at": _format_example_job_time(completed_at),
                    "payload": {
                        "provider": result.get("provider"),
                        "model": result.get("model"),
                        "runtime_provider": result.get("runtime_provider"),
                        "runtime_model": result.get("runtime_model"),
                        "summary_path": str(summary_path.relative_to(ROOT_DIR)),
                    },
                    "result_summary": {
                        "project_id": result.get("object_id"),
                        "title": result.get("title") or f"{result.get('provider')}/{result.get('model')}",
                        "is_valid": result.get("is_valid"),
                        "llm_provider": provider,
                        "model_name": model,
                        "pipeline": result.get("pipeline"),
                        "workflow": "examples",
                        "has_product_image": result.get("has_product_image"),
                        "image_output_requested": result.get("image_output_requested"),
                        "image_output_enabled": result.get("image_output_enabled"),
                        "image_output_configured": result.get("image_output_configured"),
                        "image_output_status": result.get("image_output_status"),
                        "image_output_failed": result.get("image_output_status") == "failed",
                        "image_output_error": result.get("image_output_error"),
                        "image_output_error_type": result.get("image_output_error_type"),
                        "image_output_generated_count": result.get("image_output_generated_count"),
                        "product_image_provider": result.get("image_output_provider"),
                        "product_image_model": result.get("image_output_model"),
                        "product_image_error": result.get("image_output_error"),
                        "source_usage": {
                            "workflow": "examples",
                            "source_labels": ["Examples"],
                        },
                        "operation_statuses": operation_statuses,
                        "operation_summary": operation_summary,
                        "namespace_count": len(result.get("namespaces") or []),
                        "duration_seconds": duration_seconds,
                    },
                    "source_usage": {
                        "workflow": "examples",
                        "source_labels": ["Examples"],
                    },
                    "error": result.get("error"),
                    "error_debug": (
                        {
                            "error_type": result.get("error_type"),
                            "error": result.get("error"),
                            "traceback": result.get("traceback"),
                        }
                        if result.get("error") or result.get("traceback")
                        else None
                    ),
                }
            )

            if len(jobs) >= limit:
                return jobs

    return jobs


@app.get("/example-project-object-jobs")
def list_example_project_object_jobs(
    job_status: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    _user: UserContext = Depends(require_admin_user_context),
):
    """Lists project-object jobs created by scripts under examples/results."""
    try:
        return _example_project_object_jobs(limit=limit, status=job_status)
    except Exception as exc:
        logger.exception("Example project object job listing failed.")
        raise HTTPException(status_code=500, detail=f"Example project jobs unavailable: {str(exc)}") from exc


@app.websocket("/a2a/socket/{agent_id}")
async def a2a_websocket_endpoint(websocket: WebSocket, agent_id: str):
    """WebSocket A2A transport. Send A2AMessage JSON; receive A2AEvent JSON."""
    await handle_a2a_websocket(websocket, agent_id)


@app.post("/mcp")
async def mcp_endpoint(payload: Any = Body(...), _user: UserContext = Depends(require_admin_user_context)):
    """MCP-style JSON-RPC endpoint exposing Forma tools."""
    return await handle_mcp_json_rpc(payload)


@app.post("/a2a/mcp")
async def a2a_mcp_endpoint(payload: Any = Body(...), _user: UserContext = Depends(require_admin_user_context)):
    """Alias for agents that discover MCP under the A2A route prefix."""
    return await handle_mcp_json_rpc(payload)


def _project_summary_response(project: Any, current_user_id: Optional[str] = None) -> Dict[str, Any]:
    owner_user_id = _project_owner_user_id(project)
    can_chat = bool(current_user_id and owner_user_id == current_user_id)
    hardware_ir = getattr(project, "hardware_ir", None) if isinstance(getattr(project, "hardware_ir", None), dict) else {}
    components = hardware_ir.get("components") if isinstance(hardware_ir, dict) else []
    metadata = hardware_ir.get("assembly_metadata") if isinstance(hardware_ir, dict) and isinstance(hardware_ir.get("assembly_metadata"), dict) else {}
    hydrated_metadata = hydrate_image_storage_metadata(metadata, project.project_id) if metadata else {}
    sequence = hydrated_metadata.get("product_visual_sequence")
    first_sequence_image = None
    if isinstance(sequence, list):
        first_sequence_image = next((item for item in sequence if isinstance(item, dict) and item.get("url")), None)
    product_image_url = (
        (first_sequence_image.get("url") if isinstance(first_sequence_image, dict) else None)
        or hydrated_metadata.get("product_case_image_url")
        or hydrated_metadata.get("product_image_url")
    )
    product_image_content_type = (
        (first_sequence_image.get("content_type") if isinstance(first_sequence_image, dict) else None)
        or hydrated_metadata.get("product_case_image_content_type")
        or hydrated_metadata.get("product_image_content_type")
    )
    star_count = metadata.get("star_count", metadata.get("stars", 0))
    stored_creator_display = metadata.get("creator_display") or metadata.get("creator_username")
    creator_display = (
        stored_creator_display.strip()
        if isinstance(stored_creator_display, str) and stored_creator_display.strip()
        else creator_display_name(owner_user_id)
    )
    stored_creator_image_url = metadata.get("creator_image_url")
    creator_image_url = (
        stored_creator_image_url.strip()
        if isinstance(stored_creator_image_url, str)
        and stored_creator_image_url.strip().startswith(("http://", "https://"))
        else None
    )
    return {
        "project_id": project.project_id,
        "chat_id": getattr(project, "chat_id", None) if can_chat else None,
        "title": project.title,
        "prompt": project.prompt,
        "created_at": project.created_at,
        "visibility": _project_visibility(project),
        "can_chat": can_chat,
        "creator_display": creator_display,
        "creator_username": creator_display,
        "creator_image_url": creator_image_url,
        "parts_count": len(components) if isinstance(components, list) else 0,
        "star_count": max(0, int(star_count) if isinstance(star_count, (int, float, str)) and str(star_count).isdigit() else 0),
        "has_product_image": bool(product_image_url or hydrated_metadata.get("product_image_data")),
        "product_image_url": product_image_url,
        "product_image_content_type": product_image_content_type,
        "product_image_model": hydrated_metadata.get("product_image_model") or hydrated_metadata.get("image_output_model"),
        "product_visual_sequence": sequence if isinstance(sequence, list) else [],
        "image_output_status": hydrated_metadata.get("image_output_status"),
    }


def _canonical_project_summary_response(
    revision: Any,
    brief: Any,
    *,
    owner_user_id: str,
) -> Dict[str, Any]:
    """Adapt canonical project state to the established gallery response."""

    state = revision.state
    overview = getattr(state, "overview", None)
    title = str(getattr(overview, "title", "") or getattr(brief, "summary", "") or "Untitled project")
    project = types.SimpleNamespace(
        project_id=str(revision.project_id),
        chat_id=brief.conversation_id,
        owner_user_id=owner_user_id,
        visibility="private",
        title=title,
        prompt=brief.summary,
        created_at=revision.created_at,
        hardware_ir=state.model_dump(mode="json"),
    )
    return _project_summary_response(project, current_user_id=owner_user_id)


def _project_owner_digest(owner_user_id: Optional[str]) -> Optional[str]:
    if not isinstance(owner_user_id, str) or not owner_user_id.strip():
        return None
    return hashlib.sha256(owner_user_id.strip().encode("utf-8")).hexdigest()


def _public_project_cache_record(project: Any) -> Dict[str, Any]:
    """Build one shared gallery record with non-response ownership hints."""
    summary = _project_summary_response(project, current_user_id=None)
    summary[_CACHE_OWNER_DIGEST_FIELD] = _project_owner_digest(_project_owner_user_id(project))
    summary[_CACHE_OWNER_CHAT_FIELD] = getattr(project, "chat_id", None)
    return summary


def _personalize_public_project_records(
    records: List[Dict[str, Any]],
    current_user_id: Optional[str],
) -> List[Dict[str, Any]]:
    """Strip cache-only fields and restore owner-only gallery capabilities."""
    current_owner_digest = _project_owner_digest(current_user_id)
    response: List[Dict[str, Any]] = []
    for record in records:
        item = {
            key: value
            for key, value in record.items()
            if key not in {_CACHE_OWNER_DIGEST_FIELD, _CACHE_OWNER_CHAT_FIELD}
        }
        can_chat = bool(
            current_owner_digest
            and record.get(_CACHE_OWNER_DIGEST_FIELD) == current_owner_digest
        )
        item["can_chat"] = can_chat
        item["chat_id"] = record.get(_CACHE_OWNER_CHAT_FIELD) if can_chat else None
        response.append(item)
    return response


def _without_downloadable_project_assets(hardware_ir: Dict[str, Any]) -> Dict[str, Any]:
    """Keep public project reads inspectable while withholding owner-only files."""
    sanitized = json.loads(json.dumps(hardware_ir))
    mechanical = sanitized.get("mechanical")
    if isinstance(mechanical, dict) and isinstance(mechanical.get("cad_sources"), list):
        sanitized_sources = []
        for source in mechanical["cad_sources"]:
            if not isinstance(source, dict):
                sanitized_sources.append(source)
                continue
            sanitized_source = dict(source)
            # MechanicalSource.url is required by HardwareIR. Keep the public
            # shape valid while removing the downloadable target itself.
            sanitized_source["url"] = ""
            for key in ("href", "download_url", "downloadUrl", "file_url", "fileUrl", "source_url", "sourceUrl"):
                sanitized_source.pop(key, None)
            sanitized_sources.append(sanitized_source)
        mechanical["cad_sources"] = sanitized_sources

    components = sanitized.get("components")
    if isinstance(components, list):
        for component in components:
            if not isinstance(component, dict):
                continue
            category = str(component.get("category") or "").strip().lower()
            if category not in {"mechanical", "3d print"}:
                continue
            for key in ("url", "href", "download_url", "downloadUrl", "file_url", "fileUrl", "source_url", "sourceUrl", "sourcing_url"):
                component.pop(key, None)

    metadata = sanitized.get("assembly_metadata")
    if isinstance(metadata, dict):
        metadata.pop("chat_id", None)
        metadata["can_chat"] = False
        metadata["downloadable_assets_owner_only"] = True
    return sanitized


@app.get("/projects")
def list_projects_endpoint(user: UserContext = Depends(optional_user_context)):
    """Lists public compiled hardware projects."""
    try:
        cached, generation = get_cached_project_list("public", None)
        if cached is not None:
            return _personalize_public_project_records(cached, user.owner_user_id)
        projects = [project for project in list_generated_projects() if _project_visibility(project) == "public"]
        cache_records = jsonable_encoder(
            [_public_project_cache_record(project) for project in projects]
        )
        cache_project_list("public", None, cache_records, generation)
        return _personalize_public_project_records(cache_records, user.owner_user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/my/projects")
def list_my_projects_endpoint(user: UserContext = Depends(require_user_context)):
    """Lists projects owned by the signed-in user."""
    owner_user_id = _require_authenticated_user(user)
    try:
        cached, generation = get_cached_project_list("mine", owner_user_id)
        if cached is not None:
            return cached
        projects = list_generated_projects(owner_user_id=owner_user_id)
        response = [
            _project_summary_response(project, current_user_id=owner_user_id)
            for project in projects
        ]
        legacy_project_ids = {str(project.project_id) for project in projects}
        for revision in list_latest_project_revisions(owner_user_id):
            project_id = str(revision.project_id)
            if project_id in legacy_project_ids:
                continue
            legacy_record = get_generated_project(project_id, include_deleted=True)
            if legacy_record is not None:
                # A soft-deleted legacy projection must not be resurrected by
                # its retained canonical revisions during the recovery window.
                continue
            try:
                brief = get_latest_design_brief(project_id, owner_user_id)
            except DesignBriefNotFoundError:
                logger.warning(
                    "Skipping canonical project without a design brief in owner listing: project_id=%s",
                    project_id,
                )
                continue
            response.append(
                _canonical_project_summary_response(
                    revision,
                    brief,
                    owner_user_id=owner_user_id,
                )
            )
        response.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        response = jsonable_encoder(response)
        cache_project_list("mine", owner_user_id, response, generation)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/projects/{project_id}/image-summary")
def get_project_image_summary_endpoint(project_id: str, user: UserContext = Depends(optional_user_context)):
    """Returns gallery-safe project metadata without validating or expanding the full hardware IR."""
    project = get_generated_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    _require_project_reader(project, user)

    try:
        return _project_summary_response(project, current_user_id=user.owner_user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading project image summary: {str(e)}")


@app.get("/projects/{project_id}")
def get_project_endpoint(project_id: str, user: UserContext = Depends(optional_user_context)):
    """Retrieves a specific hardware design and its corresponding schematics."""
    project = get_generated_project(project_id)
    if not project:
        owner_user_id = str(user.owner_user_id or "").strip()
        if not owner_user_id:
            raise HTTPException(status_code=404, detail="Project not found.")
        try:
            revision = get_latest_project_revision(project_id, owner_user_id)
            brief = get_latest_design_brief(project_id, owner_user_id)
        except (ProjectStateError, DesignBriefNotFoundError) as exc:
            raise HTTPException(status_code=404, detail="Project not found.") from exc
        ir = revision.state.model_copy(deep=True)
        ir.assembly_metadata = {
            **(ir.assembly_metadata or {}),
            "project_id": str(revision.project_id),
            "chat_id": brief.conversation_id,
            "can_chat": True,
            "project_revision": revision.revision,
            "design_brief_version": revision.design_brief_version,
        }
        return {
            "project_id": str(revision.project_id),
            "chat_id": brief.conversation_id,
            "prompt": brief.summary,
            "created_at": revision.created_at,
            "can_chat": True,
            "project_ir": ir.model_dump(mode="json"),
            "project_object": build_project_object(ir).model_dump(mode="json"),
            "mermaid_code": generate_mermaid_chart(ir),
            "svg_schematic": generate_svg_schematic(ir),
        }
    _require_project_reader(project, user)

    can_chat = _user_owns_project(project, user)
    stored_hardware_ir = json.loads(json.dumps(project.hardware_ir or {}))
    try:
        ir = HardwareIR(**stored_hardware_ir)
    except ValidationError as exc:
        # Saved projects can outlive the current HardwareIR schema. They should
        # remain inspectable, but public readers still receive a redacted copy.
        logger.warning(
            "Returning legacy project IR without derived artifacts: project_id=%s validation_errors=%s",
            project.project_id,
            len(exc.errors()),
        )
        metadata = stored_hardware_ir.get("assembly_metadata")
        if isinstance(metadata, dict):
            stored_hardware_ir["assembly_metadata"] = hydrate_image_storage_metadata(metadata, project.project_id)
        response_payload = stored_hardware_ir if can_chat else _without_downloadable_project_assets(stored_hardware_ir)
        response_metadata = response_payload.get("assembly_metadata")
        return {
            "project_id": project.project_id,
            "chat_id": (
                getattr(project, "chat_id", None)
                or (response_metadata.get("chat_id") if isinstance(response_metadata, dict) else None)
            ) if can_chat else None,
            "prompt": project.prompt,
            "created_at": project.created_at,
            "can_chat": can_chat,
            "project_ir": response_payload,
            "project_object": None,
            "mermaid_code": None,
            "svg_schematic": None,
        }

    try:
        ir.assembly_metadata = hydrate_image_storage_metadata(ir.assembly_metadata, project.project_id)
        if can_chat:
            response_ir = ir
        else:
            sanitized_payload = _without_downloadable_project_assets(ir.model_dump())
            try:
                response_ir = HardwareIR(**sanitized_payload)
            except ValidationError:
                return {
                    "project_id": project.project_id,
                    "chat_id": None,
                    "prompt": project.prompt,
                    "created_at": project.created_at,
                    "can_chat": False,
                    "project_ir": sanitized_payload,
                    "project_object": None,
                    "mermaid_code": None,
                    "svg_schematic": None,
                }
        mermaid_code = generate_mermaid_chart(ir)
        svg_schematic = generate_svg_schematic(ir)
        
        return {
            "project_id": project.project_id,
            "chat_id": (
                getattr(project, "chat_id", None) or (ir.assembly_metadata or {}).get("chat_id")
            ) if can_chat else None,
            "prompt": project.prompt,
            "created_at": project.created_at,
            "can_chat": can_chat,
            "project_ir": response_ir.model_dump(),
            "project_object": build_project_object(response_ir).model_dump(mode="json"),
            "mermaid_code": mermaid_code,
            "svg_schematic": svg_schematic
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading project IR: {str(e)}")


@app.patch("/projects/{project_id}")
def update_project_endpoint(
    project_id: str,
    request: ProjectUpdateRequest,
    user: UserContext = Depends(require_user_context),
):
    """Updates owner-managed project metadata, including public/private visibility."""
    project = get_generated_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    owner_user_id = _require_project_owner(project, user)
    saved = update_generated_project_metadata(
        project.project_id,
        owner_user_id=owner_user_id,
        title=request.title,
        prompt=request.prompt,
        visibility=request.visibility,
    )
    if not saved:
        raise HTTPException(status_code=404, detail="Project not found.")
    return {"ok": True, "project_id": project.project_id}


@app.delete("/projects/{project_id}", status_code=status.HTTP_202_ACCEPTED)
def delete_project_endpoint(
    project_id: str,
    user: UserContext = Depends(require_destructive_user_context),
):
    """Immediately hide a project and schedule its permanent purge."""
    owner_user_id = _require_authenticated_user(user)
    try:
        project = get_generated_project(project_id, include_deleted=True)
        if not project:
            audit = get_latest_project_deletion_audit(project_id)
            if (
                audit
                and getattr(audit, "acting_user_id", None) == owner_user_id
                and getattr(audit, "action", None) == "purge_completed"
                and getattr(audit, "status", None) == "succeeded"
            ):
                return {
                    "ok": True,
                    "project_id": project_id,
                    "status": "purged",
                    "policy_version": DELETION_POLICY_VERSION,
                }
            raise HTTPException(status_code=404, detail="Project not found.")
        _require_project_owner(project, user)
        deleted = request_project_deletion(project_id, owner_user_id)
        return {
            "ok": True,
            "project_id": project_id,
            "status": getattr(deleted, "status", "deletion_pending"),
            "deleted_at": getattr(deleted, "deleted_at", None),
            "purge_after": getattr(deleted, "purge_after", None),
            "policy_version": DELETION_POLICY_VERSION,
        }
    except HTTPException:
        raise
    except (LookupError, ValueError):
        raise HTTPException(status_code=404, detail="Project not found.")


@app.post("/projects/{project_id}/restore")
def restore_project_endpoint(
    project_id: str,
    user: UserContext = Depends(require_destructive_user_context),
):
    """Restore a project while it is still inside the retention window."""
    owner_user_id = _require_authenticated_user(user)
    try:
        project = restore_project(project_id, owner_user_id)
    except (LookupError, ValueError):
        raise HTTPException(status_code=404, detail="Project not found.")
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"ok": True, "project_id": project_id, "status": getattr(project, "status", "active")}


@app.get("/projects/{project_id}/data-contribution-consent")
def get_project_contribution_consent_endpoint(
    project_id: str,
    user: UserContext = Depends(require_user_context),
):
    owner_user_id = _require_authenticated_user(user)
    try:
        project = get_generated_project(project_id, include_deleted=True)
    except ValueError:
        project = None
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    _require_project_owner(project, user)
    consent = get_project_contribution_consent(project_id, owner_user_id)
    return {
        "project_id": project_id,
        "granted": bool(consent and not getattr(consent, "withdrawn_at", None)),
        "consent_version": getattr(consent, "consent_version", None),
        "permitted_purposes": getattr(consent, "permitted_purposes", []) if consent else [],
        "granted_at": getattr(consent, "granted_at", None),
        "withdrawn_at": getattr(consent, "withdrawn_at", None),
        "anonymized_at": getattr(consent, "anonymized_at", None),
        "available_purposes": sorted(PERMITTED_CONTRIBUTION_PURPOSES),
    }


@app.put("/projects/{project_id}/data-contribution-consent")
def grant_project_contribution_consent_endpoint(
    project_id: str,
    request: ProjectContributionConsentRequest,
    user: UserContext = Depends(require_destructive_user_context),
):
    owner_user_id = _require_authenticated_user(user)
    try:
        consent = grant_contribution_consent(
            project_id,
            owner_user_id,
            consent_version=request.consent_version,
            permitted_purposes=request.permitted_purposes,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Project not found.")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {
        "ok": True,
        "project_id": project_id,
        "granted": True,
        "consent_version": getattr(consent, "consent_version", request.consent_version),
        "permitted_purposes": getattr(consent, "permitted_purposes", request.permitted_purposes),
        "granted_at": getattr(consent, "granted_at", None),
    }


@app.delete("/projects/{project_id}/data-contribution-consent")
def withdraw_project_contribution_consent_endpoint(
    project_id: str,
    user: UserContext = Depends(require_destructive_user_context),
):
    owner_user_id = _require_authenticated_user(user)
    try:
        project = get_generated_project(project_id, include_deleted=True)
    except ValueError:
        project = None
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    _require_project_owner(project, user)
    withdrawn = withdraw_contribution(project_id, owner_user_id)
    return {"ok": True, "project_id": project_id, "granted": False, "withdrawn": bool(withdrawn)}


@app.get("/admin/project-deletions")
def list_project_deletions_endpoint(
    limit: int = Query(100, ge=1, le=500),
    _user: UserContext = Depends(require_admin_user_context),
):
    """Return content-free deletion lifecycle events for operational audits."""
    return [
        {
            "id": getattr(event, "id", None),
            "project_id": getattr(event, "project_id", None),
            "acting_user_id": getattr(event, "acting_user_id", None),
            "action": getattr(event, "action", None),
            "status": getattr(event, "status", None),
            "policy_version": getattr(event, "policy_version", None),
            "details": getattr(event, "details_json", {}) or {},
            "created_at": getattr(event, "created_at", None),
        }
        for event in list_project_deletion_audits(limit)
    ]


@app.get("/admin/project-deletion-metrics")
def project_deletion_metrics_endpoint(
    _user: UserContext = Depends(require_admin_user_context),
):
    return deletion_metrics()


def _chat_response(chat: Any) -> Dict[str, Any]:
    return Chat(
        chat_id=chat.chat_id,
        title=chat.title,
        messages=getattr(chat, "messages", []) or [],
        created_at=chat.created_at,
        updated_at=chat.updated_at,
    ).model_dump(mode="json", exclude_unset=True)


@app.get("/chats")
def list_chats_endpoint(user: UserContext = Depends(require_user_context)):
    """Lists private chats for the signed-in user."""
    owner_user_id = _require_authenticated_user(user)
    return [_chat_response(chat) for chat in list_project_chats(owner_user_id)]


@app.get("/chats/{chat_id}")
def get_chat_endpoint(chat_id: str, user: UserContext = Depends(require_user_context)):
    """Retrieves one private chat owned by the signed-in user."""
    owner_user_id = _require_authenticated_user(user)
    chat = get_project_chat(chat_id, owner_user_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")
    return _chat_response(chat)


@app.put("/chats/{chat_id}")
def upsert_chat_endpoint(
    chat_id: str,
    request: ChatUpsertRequest,
    user: UserContext = Depends(require_user_context),
):
    """Creates or updates a private chat owned by the signed-in user."""
    owner_user_id = _require_authenticated_user(user)
    now = datetime.utcnow().isoformat() + "Z"
    chat = upsert_project_chat(
        chat_id=chat_id,
        owner_user_id=owner_user_id,
        title=request.title or "Untitled chat",
        messages=[message.model_dump(mode="json", exclude_unset=True) for message in request.messages or []],
        created_at=now,
        updated_at=now,
    )
    return _chat_response(chat)


@app.delete("/chats/{chat_id}")
def delete_chat_endpoint(chat_id: str, user: UserContext = Depends(require_user_context)):
    """Deletes a private chat owned by the signed-in user."""
    owner_user_id = _require_authenticated_user(user)
    deleted = delete_project_chat(chat_id, owner_user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Chat not found.")
    return {"ok": True, "chat_id": chat_id}


@app.get("/projects/{project_id}/video-prompt")
def generate_project_video_prompt_endpoint(project_id: str, user: UserContext = Depends(optional_user_context)):
    """Builds an image-to-video prompt from Forma project namespaces."""
    project = get_generated_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    _require_project_reader(project, user)

    try:
        ir = HardwareIR(**project.hardware_ir)
        ir.assembly_metadata = hydrate_image_storage_metadata(ir.assembly_metadata, project.project_id)
        prompt_payload = generate_image_to_video_prompt_from_namespaces(ir)
        return {
            "project_id": project.project_id,
            **prompt_payload,
        }
    except Exception as e:
        logger.exception("Project video prompt generation failed for project_id=%s", project_id)
        raise HTTPException(status_code=500, detail=f"Video prompt generation failed: {str(e)}") from e


@app.post("/projects/{project_id}/iterate")
def iterate_project_endpoint(
    project_id: str,
    request: IterateProjectRequest,
    user: UserContext = Depends(require_user_context),
):
    """Applies an iteration instruction to an existing project through blueprint_core."""
    _apply_user_integrations(user)
    project = get_generated_project(project_id)
    canonical_revision = None
    canonical_brief = None
    if project is not None:
        _require_project_reader(project, user)
        save_owner_user_id = _require_project_owner(project, user) if request.save else None
        current_ir = HardwareIR(**project.hardware_ir)
        project_prompt = project.prompt
        project_chat_id = getattr(project, "chat_id", None)
        project_created_at = project.created_at
        can_chat = _user_owns_project(project, user)
    else:
        save_owner_user_id = _require_authenticated_user(user)
        try:
            canonical_revision = get_latest_project_revision(project_id, save_owner_user_id)
            canonical_brief = get_latest_design_brief(project_id, save_owner_user_id)
        except (ProjectStateError, DesignBriefNotFoundError) as exc:
            raise HTTPException(status_code=404, detail="Project not found.") from exc
        current_ir = canonical_revision.state
        project_prompt = canonical_brief.summary
        project_chat_id = canonical_brief.conversation_id
        project_created_at = canonical_revision.created_at
        can_chat = True

    if save_owner_user_id:
        try:
            ensure_project_action_allowed(project_id, save_owner_user_id, "blueprint.iterate_project")
        except WorkflowStateError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.as_dict()) from exc

    try:
        iterator = ProjectIterator(provider_name=request.provider, model_name=request.model)
        revised_ir = iterator.iterate_project(
            current_ir,
            request.instruction,
            original_prompt=project_prompt,
            project_id=project_id,
            target_namespace=request.namespace,
        )
        revised_ir.assembly_metadata = hydrate_image_storage_metadata(revised_ir.assembly_metadata, project_id)
        if request.save:
            if canonical_revision is not None:
                persisted_revision = append_project_revision(
                    project_id,
                    save_owner_user_id,
                    revised_ir,
                    source_job_id=f"iteration-{uuid4().hex}",
                )
                revised_ir = persisted_revision.state
            else:
                saved = update_generated_project_hardware_ir(
                    project_id,
                    revised_ir.model_dump(mode="json"),
                    owner_user_id=save_owner_user_id,
                )
                if not saved:
                    raise HTTPException(status_code=404, detail="Project not found.")

        return {
            "project_id": project_id,
            "chat_id": project_chat_id or (revised_ir.assembly_metadata or {}).get("chat_id"),
            "prompt": project_prompt,
            "created_at": project_created_at,
            "can_chat": can_chat,
            "saved": request.save,
            "iteration": (revised_ir.assembly_metadata or {}).get("last_iteration"),
            "project_ir": revised_ir.model_dump(mode="json"),
            "project_object": build_project_object(revised_ir, target_namespace=request.namespace).model_dump(mode="json"),
            "mermaid_code": generate_mermaid_chart(revised_ir),
            "svg_schematic": generate_svg_schematic(revised_ir),
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=runtime_safe_error_message(str(e), provider=request.provider, model=request.model),
        ) from e
    except LLMProviderConfigError as e:
        raise HTTPException(
            status_code=400,
            detail=api_error_detail(
                code="llm_config_invalid",
                message=str(e),
                exc=e,
                provider=request.provider,
                model=request.model,
                context={"project_id": project_id, "instruction": request.instruction},
            ),
        ) from e
    except LLMProviderOutputError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=api_error_detail(
                code="llm_output_invalid",
                message=str(e),
                exc=e,
                provider=request.provider,
                model=request.model,
                context={"project_id": project_id, "instruction": request.instruction},
            ),
        ) from e
    except Exception as e:
        logger.exception("Project iteration failed for project_id=%s provider=%s model=%s", project_id, request.provider, request.model)
        raise HTTPException(
            status_code=500,
            detail=runtime_safe_error_message(
                f"Project iteration failed: {str(e)}",
                provider=request.provider,
                model=request.model,
            ),
        ) from e


def _stored_video_metadata_value(video: Any, keys: List[str]) -> str:
    metadata = getattr(video, "metadata", None)
    if not isinstance(metadata, dict):
        return ""
    lowered = {str(key).lower(): value for key, value in metadata.items()}
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        lowered_value = lowered.get(key.lower())
        if isinstance(lowered_value, str) and lowered_value.strip():
            return lowered_value.strip()
    return ""


def _normalized_url_path(value: str) -> str:
    if not value:
        return ""
    try:
        return urllib.parse.unquote(urllib.parse.urlparse(value).path).strip("/")
    except Exception:
        return ""


def _stored_video_matches_review_request(video: Any, *, video_url: str, video_key: Optional[str]) -> bool:
    requested_key = str(video_key or "").strip()
    stored_key = str(getattr(video, "key", "") or "").strip()
    stored_s3_uri = str(getattr(video, "s3_uri", "") or "").strip()
    if requested_key and requested_key in {stored_key, stored_s3_uri}:
        return True

    requested_url = str(video_url or "").strip()
    candidates = {
        str(getattr(video, "public_url", "") or "").strip(),
        str(getattr(video, "signed_url", "") or "").strip(),
        stored_s3_uri,
    }
    if requested_url and requested_url in candidates:
        return True

    requested_path = _normalized_url_path(requested_url)
    return bool(stored_key and requested_path and requested_path.endswith(stored_key))


def _resolve_stored_video_review_target(project_id: str, request: VideoSelfCorrectRequest) -> str:
    try:
        videos = list_project_videos(project_id)
    except Exception as exc:
        logger.exception("Video review target lookup failed for project_id=%s", project_id)
        raise HTTPException(
            status_code=400,
            detail="Video review requires a saved project video.",
        ) from exc

    matched_video = next(
        (
            video
            for video in videos
            if _stored_video_matches_review_request(video, video_url=request.video_url, video_key=request.video_key)
        ),
        None,
    )
    if matched_video is None:
        raise HTTPException(
            status_code=400,
            detail="Video review only supports saved videos for this project.",
        )

    review_url = (
        str(getattr(matched_video, "public_url", "") or "").strip()
        or str(getattr(matched_video, "signed_url", "") or "").strip()
        or request.video_url
    )
    if not review_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="The saved video needs an HTTP(S) URL before it can be reviewed.")
    return review_url


@app.post("/projects/{project_id}/video-self-correct")
def video_self_correct_project_endpoint(
    project_id: str,
    request: VideoSelfCorrectRequest,
    user: UserContext = Depends(require_user_context),
):
    """Reviews a generated project video with a Fireworks native video model and applies a corrective iteration."""
    _apply_user_integrations(user)
    project = get_generated_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    owner_user_id = _require_project_owner(project, user)

    try:
        current_ir = HardwareIR(**project.hardware_ir)
        review_video_url = _resolve_stored_video_review_target(project.project_id, request)
        agent = FireworksVideoSelfCorrectionAgent(
            review_client=FireworksVideoReviewClient(model=request.review_model),
            iterator=ProjectIterator(provider_name=request.provider, model_name=request.model),
        )
        revised_ir, review = agent.correct_project_from_video(
            current_ir,
            video_url=review_video_url,
            original_prompt=project.prompt,
            project_id=project.project_id,
            target_namespace=request.namespace,
        )
        revised_ir.assembly_metadata = hydrate_image_storage_metadata(revised_ir.assembly_metadata, project.project_id)
        if request.save:
            saved = update_generated_project_hardware_ir(project.project_id, revised_ir.model_dump(mode="json"), owner_user_id=owner_user_id)
            if not saved:
                raise HTTPException(status_code=404, detail="Project not found.")

        target_namespace = (revised_ir.assembly_metadata or {}).get("iteration_target_namespace") or request.namespace
        return {
            "project_id": project.project_id,
            "prompt": project.prompt,
            "created_at": project.created_at,
            "saved": request.save,
            "video_review": review.model_dump(mode="json"),
            "iteration": (revised_ir.assembly_metadata or {}).get("last_iteration"),
            "project_ir": revised_ir.model_dump(mode="json"),
            "project_object": build_project_object(revised_ir, target_namespace=target_namespace).model_dump(mode="json"),
            "mermaid_code": generate_mermaid_chart(revised_ir),
            "svg_schematic": generate_svg_schematic(revised_ir),
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except LLMProviderConfigError as e:
        raise HTTPException(
            status_code=400,
            detail=api_error_detail(
                code="video_review_config_invalid",
                message=str(e),
                exc=e,
                provider="fireworks",
                model=request.review_model,
                context={"project_id": project_id, "video_url": request.video_url, "video_key": request.video_key},
            ),
        ) from e
    except LLMProviderOutputError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=api_error_detail(
                code="video_review_output_invalid",
                message=str(e),
                exc=e,
                provider="fireworks",
                model=request.review_model,
                context={"project_id": project_id, "video_url": request.video_url, "video_key": request.video_key},
            ),
        ) from e
    except Exception as e:
        logger.exception("Video self-correction failed for project_id=%s", project_id)
        raise HTTPException(status_code=500, detail=f"Video self-correction failed: {str(e)}") from e

@app.get("/components")
def get_components_endpoint():
    """Returns the template library of seed electrical parts."""
    try:
        components = list_component_templates()
        return [
            {
                "id": c.id,
                "part_number": c.part_number,
                "name": c.name,
                "category": c.category,
                "description": c.description,
                "price": c.price,
                "sourcing_url": c.sourcing_url,
                "pins": c.pins,
                "use_cases": c.use_cases
            }
            for c in components
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/seed", status_code=status.HTTP_201_CREATED)
def trigger_db_seeding():
    """Manual trigger to re-seed the parts library database."""
    try:
        seed_database()
        return {"message": "Database templates successfully seeded."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class ValidateCircuitRequest(BaseModel):
    components: List[ComponentInstance]
    nets: List[ConnectionNet]

@app.post("/validate", response_model=ValidationReport)
def validate_circuit_endpoint(request: ValidateCircuitRequest):
    """
    Accepts arbitrary list of parts and electrical connection nets.
    Runs rule checks and returns validation errors or warnings.
    """
    try:
        issues = validate_circuit(request.components, request.nets)
        is_valid = not any(issue.severity.upper() == "CRITICAL" for issue in issues)
        return ValidationReport(is_valid=is_valid, issues=issues)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
