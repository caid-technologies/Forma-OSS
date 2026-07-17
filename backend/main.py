from pathlib import Path
from datetime import datetime, timedelta, timezone
import asyncio
import json
import logging
import sys
import types
import urllib.parse
from typing import Any, Dict, List, Optional
from uuid import uuid4


def _ensure_backend_package_imports() -> None:
    """Support Vercel loading backend/main.py as top-level main.py."""
    if "backend" in sys.modules:
        return

    current_dir = Path(__file__).resolve().parent
    if not (current_dir / "database.py").exists():
        return

    project_root = current_dir.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    backend_package = types.ModuleType("backend")
    backend_package.__path__ = [str(current_dir)]
    backend_package.__file__ = str(current_dir / "__init__.py")
    backend_package.__package__ = "backend"
    sys.modules["backend"] = backend_package
    sys.modules.setdefault("backend.main", sys.modules[__name__])
    setattr(backend_package, "main", sys.modules[__name__])


_ensure_backend_package_imports()

from blueprint_core.debug import (
    api_error_detail,
    debug_mode_enabled,
    exception_debug_payload,
    get_debug_mode_config,
)
from fastapi import Body, Depends, FastAPI, HTTPException, Query, WebSocket, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from blueprint_core.user_integrations import apply_user_integrations_to_environment

apply_user_integrations_to_environment()

from backend.logging_config import configure_backend_logging

configure_backend_logging()

from blueprint_core.database import (
    count_component_templates,
    delete_generated_project,
    delete_project_chat,
    get_database_config,
    get_generated_project,
    get_project_chat,
    init_db,
    list_project_chats,
    list_component_templates,
    list_generated_projects,
    save_alpha_signup,
    update_generated_project_metadata,
    update_generated_project_hardware_ir,
    upsert_project_chat,
)
from backend.seed_db import seed_database
from blueprint_core.agents.workflows import get_workflow_debug_config, list_workflows
from blueprint_core.clarifying_questions import ask_clarifying_questions
from blueprint_core.models import (
    AlphaSignupRequest, AlphaSignupResponse, ClarifyingQuestionsRequest, ClarifyingQuestionsResponse,
    GenerateProjectRequest, HardwareIR, IterateProjectRequest, ValidationReport, VideoSelfCorrectRequest,
    ComponentInstance, ConnectionNet, ValidationIssue
)
from blueprint_core.agents.orchestrator import HardwarePipelineOrchestrator
from backend.a2a import (
    A2A_HUB,
    A2AAgentRegistration,
    A2AMessage,
    call_blueprint_action,
    get_a2a_capabilities,
    handle_a2a_websocket,
    handle_mcp_json_rpc,
    start_a2a_tcp_server,
    stop_a2a_tcp_server,
    submit_a2a_message,
)
from blueprint_core.images import get_image_output_debug_config
from blueprint_core.iteration import ProjectIterator
from blueprint_core.llm import LLMProviderConfigError
from blueprint_core.llm import LLMProviderOutputError
from blueprint_core.project_objects import build_project_object, list_project_namespaces
from blueprint_core.pipeline import list_agent_pipeline_steps, observe_agent_pipeline, pipeline_workflow_id
from blueprint_core.video_prompts import generate_image_to_video_prompt_from_namespaces
from blueprint_core.video_review import FireworksVideoReviewClient, FireworksVideoSelfCorrectionAgent
from backend.logs_api import router as logs_router
from backend.streams_api import router as streams_router
from backend.user_integrations_api import router as user_integrations_router
from backend.auth import clerk_user_display_name, clerk_user_id, clerk_user_image_url, clerk_user_is_admin, deployed_auth_required, optional_deployed_clerk_auth, require_deployed_admin_auth, require_deployed_clerk_auth
from backend.job_store import JOB_STORE
from blueprint_core.observability import flush_langfuse, get_langfuse_debug_config
from blueprint_core.runtime import (
    ALPHA_GENERATION_UNAVAILABLE_MESSAGE,
    AlphaGenerationUnavailableError,
    deployment_runtime_config,
    generation_unavailable_detail,
)
from backend.storage import get_image_storage_config, hydrate_image_storage_metadata
from blueprint_core.validation import validate_circuit
from blueprint_core.utils import generate_mermaid_chart, generate_svg_schematic
from backend.video_providers import (
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
from backend.video_storage import (
    ensure_video_storage_configured,
    get_video_storage_config,
    list_project_videos,
    upload_generated_videos_to_s3,
)

logger = logging.getLogger(__name__)
ROOT_DIR = Path(__file__).resolve().parents[1]
EXAMPLE_RESULTS_DIR = ROOT_DIR / "examples" / "results"


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


async def _process_frontend_generation_job(job_id: str, payload: Dict[str, Any]) -> None:
    JOB_STORE.mark_running(job_id)
    try:
        with observe_agent_pipeline(lambda event: JOB_STORE.append_progress_event(job_id, event.as_dict())):
            response = await call_blueprint_action("blueprint.generate_project", payload)
        JOB_STORE.mark_succeeded(job_id, response)
        job = JOB_STORE.get_job(job_id)
        response = _attach_generation_timing_metadata(response, job)
        metadata = (response.get("project_ir", {}).get("assembly_metadata") or {})
        project_id = metadata.get("project_id")
        if project_id and isinstance(response.get("project_ir"), dict):
            try:
                update_generated_project_hardware_ir(project_id, response["project_ir"])
            except Exception:
                logger.warning("Failed to persist generation timing metadata for project_id=%s", project_id, exc_info=debug_mode_enabled())
        if response is not None:
            JOB_STORE.mark_succeeded(job_id, response)
    except Exception as exc:
        error_debug = exception_debug_payload(exc, context=payload) if debug_mode_enabled() else None
        JOB_STORE.mark_failed(job_id, str(exc), error_debug)
        logger.exception("Background generation failed for job_id=%s provider=%s model=%s", job_id, payload.get("provider"), payload.get("model"))

app = FastAPI(
    title="Blueprint Open-Source API",
    description="AI-native prompt-to-hardware compilation, validation, and design generation platform.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    swagger_ui_oauth2_redirect_url="/docs/oauth2-redirect",
)


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

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In development, allow all. Can narrow in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(logs_router, dependencies=[Depends(require_deployed_admin_auth)])
app.include_router(streams_router, dependencies=[Depends(require_deployed_admin_auth)])
app.include_router(user_integrations_router)


@app.middleware("http")
async def apply_user_integrations_middleware(request: Any, call_next: Any) -> Any:
    apply_user_integrations_to_environment()
    return await call_next(request)


def _deployment_runtime_config(llm_config: Dict[str, Any]) -> Dict[str, Any]:
    return deployment_runtime_config(llm_config, signup_storage=get_database_config()["client"])


def _job_owner_user_id(job: Optional[Dict[str, Any]]) -> Optional[str]:
    payload = job.get("payload") if isinstance(job, dict) else None
    value = payload.get("owner_user_id") if isinstance(payload, dict) else None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _require_job_reader(job: Dict[str, Any], auth_claims: Any) -> None:
    if clerk_user_is_admin(auth_claims):
        return
    owner_user_id = _job_owner_user_id(job)
    if owner_user_id and owner_user_id == clerk_user_id(auth_claims):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only view your own jobs.")


# Initialize and seed database on startup
@app.on_event("startup")
async def startup_event():
    logger.info("Starting up Blueprint server...")
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
    JOB_STORE.init_db()
    await start_a2a_tcp_server()


@app.on_event("shutdown")
async def shutdown_event():
    await stop_a2a_tcp_server()
    flush_langfuse()

@app.get("/")
def read_root():
    return {
        "status": "online",
        "service": "Blueprint Open-Source Hardware Compiler",
        "version": "1.0.0",
        "docs_url": "/api/docs"
    }


@app.get("/admin/session")
def admin_session_endpoint(_auth_claims: Any = Depends(optional_deployed_clerk_auth)):
    """Reports whether the current signed-in user has Blueprint admin access."""
    return {
        "is_admin": clerk_user_is_admin(_auth_claims),
        "user_id": clerk_user_id(_auth_claims),
    }


@app.get("/debug/config")
def debug_config_endpoint(
    provider: Optional[str] = Query(None, description="Optional runtime LLM provider override to validate."),
    model: Optional[str] = Query(None, description="Optional runtime LLM model override to validate."),
):
    """
    Reports LLM provider and model resolution state without exposing credentials.
    """
    try:
        orchestrator = HardwarePipelineOrchestrator(provider_name=provider, model_name=model)
        llm_config = orchestrator.get_debug_config()
        return {
            **llm_config,
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

@app.post("/generate", response_model=Dict[str, Any])
async def generate_project_endpoint(request: GenerateProjectRequest, _auth_claims: Any = Depends(require_deployed_clerk_auth)):
    """
    Submits a natural language hardware idea and optional multimodal reference image.
    Runs the 7-agent compilation workflow, circuit safety auditor, and returns a verified Hardware IR, SVG schematic, and Mermaid diagram.
    """
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
    owner_user_id = _require_authenticated_user(_auth_claims)
    if request.source_project_id:
        source_project = get_generated_project(request.source_project_id)
        if not source_project:
            raise HTTPException(status_code=404, detail="Source project not found.")
        _require_project_chat_owner(source_project, _auth_claims)
    payload = {
        "prompt": request.prompt,
        "workflow": request.workflow,
        "image_data": request.image_data,
        "generate_image": request.generate_image,
        "provider": request.provider,
        "model": request.model,
        "chat_id": request.chat_id,
        "source_project_id": request.source_project_id,
        "client_job_id": job_id,
        "owner_user_id": owner_user_id,
        "external_source_provider": request.external_source_provider,
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
    if request.async_generation:
        job = JOB_STORE.get_job(job_id)
        asyncio.create_task(_process_frontend_generation_job(job_id, payload))
        return {
            "accepted": True,
            "async_generation": True,
            "job_id": job_id,
            "chat_id": request.chat_id,
            "job": job,
        }

    JOB_STORE.mark_running(job_id)

    try:
        with observe_agent_pipeline(lambda event: JOB_STORE.append_progress_event(job_id, event.as_dict())):
            response = await call_blueprint_action("blueprint.generate_project", payload)
        JOB_STORE.mark_succeeded(job_id, response)
        job = JOB_STORE.get_job(job_id)
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
            "job_id": job_id,
            "job": job,
        }
    except ValueError as e:
        error_debug = exception_debug_payload(e, context=payload) if debug_mode_enabled() else None
        JOB_STORE.mark_failed(job_id, str(e), error_debug)
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
        JOB_STORE.mark_failed(job_id, str(e), error_debug)
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
        JOB_STORE.mark_failed(job_id, str(e), error_debug)
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
        JOB_STORE.mark_failed(job_id, str(e), error_debug)
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
        JOB_STORE.mark_failed(job_id, str(e), error_debug)
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


class ProjectUpdateRequest(BaseModel):
    title: str | None = None
    prompt: str | None = None
    visibility: str | None = None


class ProjectChatUpsertRequest(BaseModel):
    chat_id: str | None = None
    title: str | None = None
    messages: List[Dict[str, Any]] | None = None


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


def _require_authenticated_user(auth_claims: Any) -> str:
    user_id = clerk_user_id(auth_claims)
    if user_id:
        return user_id
    if not deployed_auth_required():
        return "local-dev-user"
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in to manage projects and chats.")


def _project_owner_user_id(project: Any) -> Optional[str]:
    value = getattr(project, "owner_user_id", None)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def creator_display_name(owner_user_id: Optional[str]) -> str:
    if not owner_user_id:
        return "unknown"
    normalized = owner_user_id.strip()
    if normalized == "local-dev-user":
        return "local_dev"
    clerk_display = clerk_user_display_name(normalized)
    if clerk_display:
        return clerk_display
    if len(normalized) <= 12:
        return normalized
    return f"{normalized[:6]}_{normalized[-4:]}"


def _require_project_owner(project: Any, auth_claims: Any) -> str:
    user_id = _require_authenticated_user(auth_claims)
    if not deployed_auth_required():
        return user_id
    owner_user_id = _project_owner_user_id(project)
    if owner_user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only modify your own projects.")
    return user_id


def _require_project_chat_owner(project: Any, auth_claims: Any) -> str:
    user_id = _require_authenticated_user(auth_claims)
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
def list_project_videos_endpoint(project_id: str, _auth_claims: Any = Depends(require_deployed_clerk_auth)):
    """Lists videos saved for one project from configured backend storage."""
    project_id = _require_non_empty(project_id, "projectId is required.")
    project = get_generated_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    _require_project_owner(project, _auth_claims)
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
def create_image_to_video_endpoint(request: VideoImageToVideoRequest, _auth_claims: Any = Depends(require_deployed_clerk_auth)):
    """Queues a backend-only GMI Cloud image-to-video generation request."""
    project_id = _require_non_empty(request.projectId, "projectId is required.")
    project = get_generated_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    _require_project_owner(project, _auth_claims)
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
def create_video_to_video_endpoint(request: VideoToVideoRequest, _auth_claims: Any = Depends(require_deployed_clerk_auth)):
    """Queues a backend-only GMI Cloud video-to-video generation request."""
    project_id = _require_non_empty(request.projectId, "projectId is required.")
    project = get_generated_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    _require_project_owner(project, _auth_claims)
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
    _auth_claims: Any = Depends(require_deployed_clerk_auth),
):
    """Polls GMI Cloud for a project-scoped video request and stores completed videos in S3."""
    request_id = _require_non_empty(request_id, "requestId is required.")
    project_id = _require_non_empty(projectId, "projectId is required.")
    project = get_generated_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    _require_project_owner(project, _auth_claims)
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
    """Advertises Blueprint's A2A transports, actions, and MCP tools."""
    return get_a2a_capabilities()


@app.put("/a2a/agents/{agent_id}")
async def register_a2a_agent(agent_id: str, registration: A2AAgentRegistration):
    """Registers an agent so it can receive queued A2A events."""
    record = registration.model_dump()
    record["agent_id"] = registration.agent_id or agent_id
    return await A2A_HUB.register(agent_id, record)


@app.post("/a2a/messages")
async def send_a2a_message(message: A2AMessage, _auth_claims: Any = Depends(require_deployed_clerk_auth)):
    """Submits an A2A message and queues an async result for the sender."""
    owner_user_id = clerk_user_id(_auth_claims)
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
    _auth_claims: Any = Depends(require_deployed_admin_auth),
):
    """Lists persisted A2A job metadata."""
    return JOB_STORE.list_jobs(sender=sender, status=job_status, limit=limit)


@app.get("/a2a/jobs/{job_id}")
def get_a2a_job(job_id: str, _auth_claims: Any = Depends(require_deployed_clerk_auth)):
    """Fetches persisted metadata for one A2A job."""
    job = JOB_STORE.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="A2A job not found.")
    _require_job_reader(job, _auth_claims)
    return job


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
    _auth_claims: Any = Depends(require_deployed_admin_auth),
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
async def mcp_endpoint(payload: Any = Body(...), _auth_claims: Any = Depends(require_deployed_admin_auth)):
    """MCP-style JSON-RPC endpoint exposing Blueprint tools."""
    return await handle_mcp_json_rpc(payload)


@app.post("/a2a/mcp")
async def a2a_mcp_endpoint(payload: Any = Body(...), _auth_claims: Any = Depends(require_deployed_admin_auth)):
    """Alias for agents that discover MCP under the A2A route prefix."""
    return await handle_mcp_json_rpc(payload)


def _project_summary_response(project: Any, current_user_id: Optional[str] = None) -> Dict[str, Any]:
    owner_user_id = _project_owner_user_id(project)
    hardware_ir = getattr(project, "hardware_ir", None) if isinstance(getattr(project, "hardware_ir", None), dict) else {}
    components = hardware_ir.get("components") if isinstance(hardware_ir, dict) else []
    metadata = hardware_ir.get("assembly_metadata") if isinstance(hardware_ir, dict) and isinstance(hardware_ir.get("assembly_metadata"), dict) else {}
    star_count = metadata.get("star_count", metadata.get("stars", 0))
    creator_display = creator_display_name(owner_user_id)
    creator_image_url = clerk_user_image_url(owner_user_id) if owner_user_id else None
    return {
        "project_id": project.project_id,
        "chat_id": getattr(project, "chat_id", None),
        "title": project.title,
        "prompt": project.prompt,
        "created_at": project.created_at,
        "can_chat": bool(current_user_id and owner_user_id == current_user_id),
        "creator_display": creator_display,
        "creator_username": creator_display,
        "creator_image_url": creator_image_url,
        "parts_count": len(components) if isinstance(components, list) else 0,
        "star_count": max(0, int(star_count) if isinstance(star_count, (int, float, str)) and str(star_count).isdigit() else 0),
    }


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
            for key in ("url", "href", "download_url", "downloadUrl", "file_url", "fileUrl", "source_url", "sourceUrl"):
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
        metadata["downloadable_assets_owner_only"] = True
    return sanitized


@app.get("/projects")
def list_projects_endpoint(_auth_claims: Any = Depends(optional_deployed_clerk_auth)):
    """Lists all previously compiled hardware projects."""
    current_user_id = clerk_user_id(_auth_claims)
    try:
        projects = list_generated_projects()
        return [_project_summary_response(p, current_user_id=current_user_id) for p in projects]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/my/projects")
def list_my_projects_endpoint(_auth_claims: Any = Depends(require_deployed_clerk_auth)):
    """Lists projects owned by the signed-in user."""
    owner_user_id = _require_authenticated_user(_auth_claims)
    try:
        projects = list_generated_projects(owner_user_id=owner_user_id)
        return [_project_summary_response(p, current_user_id=owner_user_id) for p in projects]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/projects/{project_id}")
def get_project_endpoint(project_id: str, _auth_claims: Any = Depends(optional_deployed_clerk_auth)):
    """Retrieves a specific hardware design and its corresponding schematics."""
    project = get_generated_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    
    try:
        current_user_id = clerk_user_id(_auth_claims)
        can_chat = bool(current_user_id and _project_owner_user_id(project) == current_user_id)
        ir = HardwareIR(**project.hardware_ir)
        ir.assembly_metadata = hydrate_image_storage_metadata(ir.assembly_metadata, project.project_id)
        response_ir = ir if can_chat else HardwareIR(**_without_downloadable_project_assets(ir.model_dump()))
        mermaid_code = generate_mermaid_chart(ir)
        svg_schematic = generate_svg_schematic(ir)
        
        return {
            "project_id": project.project_id,
            "chat_id": getattr(project, "chat_id", None) or (ir.assembly_metadata or {}).get("chat_id"),
            "prompt": project.prompt,
            "created_at": project.created_at,
            "can_chat": can_chat,
            "project_ir": response_ir.model_dump(),
            "project_object": build_project_object(response_ir).model_dump(mode="json"),
            "mermaid_code": mermaid_code,
            "svg_schematic": svg_schematic
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading project IR: {str(e)}")


@app.patch("/projects/{project_id}")
def update_project_endpoint(
    project_id: str,
    request: ProjectUpdateRequest,
    _auth_claims: Any = Depends(require_deployed_clerk_auth),
):
    """Updates owner-managed project metadata. Project records remain publicly readable."""
    project = get_generated_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    owner_user_id = _require_project_owner(project, _auth_claims)
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


@app.delete("/projects/{project_id}")
def delete_project_endpoint(project_id: str, _auth_claims: Any = Depends(require_deployed_clerk_auth)):
    """Deletes a project owned by the signed-in user."""
    project = get_generated_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    owner_user_id = _require_project_owner(project, _auth_claims)
    deleted = delete_generated_project(project.project_id, owner_user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found.")
    return {"ok": True, "project_id": project.project_id}


def _chat_response(chat: Any) -> Dict[str, Any]:
    return {
        "chat_id": chat.chat_id,
        "title": chat.title,
        "messages": getattr(chat, "messages", []) or [],
        "created_at": chat.created_at,
        "updated_at": chat.updated_at,
    }


@app.get("/chats")
def list_chats_endpoint(_auth_claims: Any = Depends(require_deployed_clerk_auth)):
    """Lists private chats for the signed-in user."""
    owner_user_id = _require_authenticated_user(_auth_claims)
    return [_chat_response(chat) for chat in list_project_chats(owner_user_id)]


@app.get("/chats/{chat_id}")
def get_chat_endpoint(chat_id: str, _auth_claims: Any = Depends(require_deployed_clerk_auth)):
    """Retrieves one private chat owned by the signed-in user."""
    owner_user_id = _require_authenticated_user(_auth_claims)
    chat = get_project_chat(chat_id, owner_user_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")
    return _chat_response(chat)


@app.put("/chats/{chat_id}")
def upsert_chat_endpoint(
    chat_id: str,
    request: ProjectChatUpsertRequest,
    _auth_claims: Any = Depends(require_deployed_clerk_auth),
):
    """Creates or updates a private chat owned by the signed-in user."""
    owner_user_id = _require_authenticated_user(_auth_claims)
    now = datetime.utcnow().isoformat() + "Z"
    chat = upsert_project_chat(
        chat_id=chat_id,
        owner_user_id=owner_user_id,
        title=request.title or "Untitled chat",
        messages=request.messages or [],
        created_at=now,
        updated_at=now,
    )
    return _chat_response(chat)


@app.delete("/chats/{chat_id}")
def delete_chat_endpoint(chat_id: str, _auth_claims: Any = Depends(require_deployed_clerk_auth)):
    """Deletes a private chat owned by the signed-in user."""
    owner_user_id = _require_authenticated_user(_auth_claims)
    deleted = delete_project_chat(chat_id, owner_user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Chat not found.")
    return {"ok": True, "chat_id": chat_id}


@app.get("/projects/{project_id}/video-prompt")
def generate_project_video_prompt_endpoint(project_id: str):
    """Builds an image-to-video prompt from Blueprint project namespaces."""
    project = get_generated_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

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
    _auth_claims: Any = Depends(require_deployed_clerk_auth),
):
    """Applies an iteration instruction to an existing project through blueprint_core."""
    project = get_generated_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    try:
        current_ir = HardwareIR(**project.hardware_ir)
        iterator = ProjectIterator(provider_name=request.provider, model_name=request.model)
        revised_ir = iterator.iterate_project(
            current_ir,
            request.instruction,
            original_prompt=project.prompt,
            project_id=project.project_id,
            target_namespace=request.namespace,
        )
        revised_ir.assembly_metadata = hydrate_image_storage_metadata(revised_ir.assembly_metadata, project.project_id)
        if request.save:
            owner_user_id = _require_project_owner(project, _auth_claims)
            saved = update_generated_project_hardware_ir(project.project_id, revised_ir.model_dump(mode="json"), owner_user_id=owner_user_id)
            if not saved:
                raise HTTPException(status_code=404, detail="Project not found.")

        return {
            "project_id": project.project_id,
            "prompt": project.prompt,
            "created_at": project.created_at,
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
        raise HTTPException(status_code=400, detail=str(e)) from e
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
        raise HTTPException(status_code=500, detail=f"Project iteration failed: {str(e)}") from e


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
    _auth_claims: Any = Depends(require_deployed_clerk_auth),
):
    """Reviews a generated project video with a Fireworks native video model and applies a corrective iteration."""
    project = get_generated_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

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
            owner_user_id = _require_project_owner(project, _auth_claims)
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
