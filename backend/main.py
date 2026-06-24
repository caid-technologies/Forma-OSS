from pathlib import Path
from datetime import datetime
import logging
import sys
import types
from typing import Any, Dict, List
from uuid import uuid4


def _ensure_backend_package_imports() -> None:
    """Support Vercel loading backend/main.py as top-level main.py."""
    if "backend" in sys.modules:
        return

    current_dir = Path(__file__).resolve().parent
    if not (current_dir / "database.py").exists():
        return

    backend_package = types.ModuleType("backend")
    backend_package.__path__ = [str(current_dir)]
    backend_package.__file__ = str(current_dir / "__init__.py")
    backend_package.__package__ = "backend"
    sys.modules["backend"] = backend_package
    sys.modules.setdefault("backend.main", sys.modules[__name__])
    setattr(backend_package, "main", sys.modules[__name__])


_ensure_backend_package_imports()

from fastapi import Body, FastAPI, HTTPException, Query, WebSocket, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from backend.database import (
    count_component_templates,
    get_database_config,
    get_generated_project,
    init_db,
    list_component_templates,
    list_generated_projects,
    save_alpha_signup,
)
from backend.seed_db import seed_database
from backend.models import (
    AlphaSignupRequest, AlphaSignupResponse,
    GenerateProjectRequest, HardwareIR, ValidationReport, 
    ComponentInstance, ConnectionNet, ValidationIssue
)
from backend.agents.orchestrator import HardwarePipelineOrchestrator
from backend.a2a import (
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
from backend.image_providers import get_image_output_debug_config
from backend.job_store import JOB_STORE
from backend.runtime_config import (
    ALPHA_GENERATION_UNAVAILABLE_MESSAGE,
    AlphaGenerationUnavailableError,
    deployment_runtime_config,
)
from backend.storage import get_image_storage_config, hydrate_image_storage_metadata
from backend.validation import get_generation_input_issue, validate_circuit
from backend.utils import generate_mermaid_chart, generate_svg_schematic
from backend.video_providers import GMICloudProvider, get_available_video_models, get_default_video_model
from backend.video_storage import (
    ensure_video_storage_configured,
    get_video_storage_config,
    list_project_videos,
    upload_generated_videos_to_s3,
)

logger = logging.getLogger(__name__)

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


def _deployment_runtime_config(llm_config: Dict[str, Any]) -> Dict[str, Any]:
    return deployment_runtime_config(llm_config, signup_storage=get_database_config()["client"])


# Initialize and seed database on startup
@app.on_event("startup")
async def startup_event():
    print("Starting up Blueprint server...")
    try:
        init_db()
        count = count_component_templates()
        if count == 0:
            print("Database empty. Seeding templates automatically...")
            seed_database()
        else:
            print(f"Database ready with {count} component templates.")
    except Exception as e:
        print(f"Error during database startup: {e}")
        raise
    JOB_STORE.init_db()
    await start_a2a_tcp_server()


@app.on_event("shutdown")
async def shutdown_event():
    await stop_a2a_tcp_server()

@app.get("/")
def read_root():
    return {
        "status": "online",
        "service": "Blueprint Open-Source Hardware Compiler",
        "version": "1.0.0",
        "docs_url": "/api/docs"
    }

@app.get("/debug/config")
def debug_config_endpoint():
    """
    Reports LLM provider and model resolution state without exposing credentials.
    """
    try:
        orchestrator = HardwarePipelineOrchestrator()
        llm_config = orchestrator.get_debug_config()
        return {
            **llm_config,
            "deployment": _deployment_runtime_config(llm_config),
            "database": get_database_config(),
            "job_metadata": JOB_STORE.get_config(),
            "image_output": get_image_output_debug_config(),
            "image_storage": get_image_storage_config(),
            "video_generation": GMICloudProvider().get_debug_config(),
            "video_storage": get_video_storage_config(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Debug config failed: {str(e)}")

@app.post("/generate", response_model=Dict[str, Any])
def generate_project_endpoint(request: GenerateProjectRequest):
    """
    Submits a natural language hardware idea and optional multimodal reference image.
    Runs the 7-agent compilation workflow, circuit safety auditor, and returns a verified Hardware IR, SVG schematic, and Mermaid diagram.
    """
    llm_config = HardwarePipelineOrchestrator().get_debug_config()
    deployment_config = _deployment_runtime_config(llm_config)
    if deployment_config["alpha_generation_gate_active"]:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=ALPHA_GENERATION_UNAVAILABLE_MESSAGE,
        )

    input_issue = get_generation_input_issue(request.prompt, has_image=bool(request.image_data))
    if input_issue:
        raise HTTPException(status_code=400, detail=input_issue)

    job_id = f"job_frontend_{uuid4().hex}"
    message_id = f"msg_{uuid4().hex}"
    payload = {
        "prompt": request.prompt,
        "image_data": request.image_data,
        "generate_image": request.generate_image,
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
        response = build_generation_response(request.prompt, request.image_data, generate_image=request.generate_image)
        JOB_STORE.mark_succeeded(job_id, response)
        project_id = (response.get("project_ir", {}).get("assembly_metadata") or {}).get("project_id")
        return {
            **response,
            "project_id": project_id,
            "job_id": job_id,
            "job": JOB_STORE.get_job(job_id),
        }
    except ValueError as e:
        JOB_STORE.mark_failed(job_id, str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except AlphaGenerationUnavailableError as e:
        JOB_STORE.mark_failed(job_id, str(e))
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except Exception as e:
        JOB_STORE.mark_failed(job_id, str(e))
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")


class VideoImageToVideoRequest(BaseModel):
    projectId: str | None = None
    image: str | None = None
    prompt: str | None = None
    model: str | None = None
    duration: str | None = "5"
    sound: str | None = "off"


VIDEO_FAILED_STATUSES = {"failed", "failure", "error", "cancelled", "canceled"}
VIDEO_SUCCESS_STATUSES = {"success", "succeeded", "completed", "complete", "done"}


def _normalize_video_model(model: str | None) -> str:
    normalized = (model or get_default_video_model()).strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="Video model is required.")
    allowed_models = get_available_video_models()
    if normalized not in allowed_models:
        raise HTTPException(status_code=400, detail=f"Unsupported video model '{normalized}'.")
    return normalized


def _require_non_empty(value: str | None, message: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail=message)
    return normalized


def _store_video_results(result: Any, *, project_id: str, model: str) -> List[Dict[str, Any]]:
    if not result.video_urls:
        return []
    try:
        stored_videos = upload_generated_videos_to_s3(
            result.video_urls,
            project_id=project_id,
            request_id=result.request_id,
            model=model,
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


def _video_route_response(result: Any, *, project_id: str, model: str, saved_videos: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "projectId": project_id,
        "requestId": result.request_id,
        "status": result.status,
        "model": model,
        "source": "gmi-cloud",
        "videoUrls": result.video_urls,
        "savedVideos": saved_videos,
        "storedVideo": saved_videos[0] if saved_videos else None,
    }


@app.get("/video/models")
def list_video_models_endpoint():
    """Returns the backend-approved video generation models."""
    models = get_available_video_models()
    default_model = get_default_video_model()
    provider_config = GMICloudProvider().get_debug_config()
    return {
        "models": [{"id": model, "label": model} for model in models],
        "defaultModel": default_model,
        "default_model": default_model,
        "generationConfigured": provider_config["configured"],
        "generation_configured": provider_config["configured"],
        "reason": provider_config.get("reason"),
    }


@app.get("/video/projects/{project_id}")
def list_project_videos_endpoint(project_id: str):
    """Lists videos saved for one project from configured backend storage."""
    project_id = _require_non_empty(project_id, "projectId is required.")
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
def create_image_to_video_endpoint(request: VideoImageToVideoRequest):
    """Queues a backend-only GMI Cloud image-to-video generation request."""
    project_id = _require_non_empty(request.projectId, "projectId is required.")
    image = _require_non_empty(request.image, "image is required.")
    prompt = _require_non_empty(request.prompt, "prompt is required.")
    model = _normalize_video_model(request.model)
    duration = _require_non_empty(request.duration, "duration is required.")
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
            sound=sound,
        )
    except Exception as exc:
        logger.exception("GMI Cloud image-to-video create failed for project_id=%s model=%s", project_id, model)
        status_code = 500 if "API key is missing" in str(exc) else 502
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    if result.status in VIDEO_FAILED_STATUSES:
        raise HTTPException(status_code=502, detail=f"GMI Cloud video request failed with status '{result.status}'.")
    _raise_if_completed_without_video(result)

    saved_videos = _store_video_results(result, project_id=project_id, model=model)
    return _video_route_response(result, project_id=project_id, model=model, saved_videos=saved_videos)


@app.get("/video/image-to-video/status/{request_id}")
def get_image_to_video_status_endpoint(
    request_id: str,
    projectId: str | None = Query(None, description="Project id that owns this video generation request."),
    model: str | None = None,
):
    """Polls GMI Cloud for a project-scoped video request and stores completed videos in S3."""
    request_id = _require_non_empty(request_id, "requestId is required.")
    project_id = _require_non_empty(projectId, "projectId is required.")
    model = _normalize_video_model(model)

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
        saved_videos = _store_video_results(result, project_id=project_id, model=model)

    return _video_route_response(result, project_id=project_id, model=model, saved_videos=saved_videos)


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
async def send_a2a_message(message: A2AMessage):
    """Submits an A2A message and queues an async result for the sender."""
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
):
    """Lists persisted A2A job metadata."""
    return JOB_STORE.list_jobs(sender=sender, status=job_status, limit=limit)


@app.get("/a2a/jobs/{job_id}")
def get_a2a_job(job_id: str):
    """Fetches persisted metadata for one A2A job."""
    job = JOB_STORE.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="A2A job not found.")
    return job


@app.websocket("/a2a/socket/{agent_id}")
async def a2a_websocket_endpoint(websocket: WebSocket, agent_id: str):
    """WebSocket A2A transport. Send A2AMessage JSON; receive A2AEvent JSON."""
    await handle_a2a_websocket(websocket, agent_id)


@app.post("/mcp")
async def mcp_endpoint(payload: Any = Body(...)):
    """MCP-style JSON-RPC endpoint exposing Blueprint tools."""
    return await handle_mcp_json_rpc(payload)


@app.post("/a2a/mcp")
async def a2a_mcp_endpoint(payload: Any = Body(...)):
    """Alias for agents that discover MCP under the A2A route prefix."""
    return await handle_mcp_json_rpc(payload)

@app.get("/projects")
def list_projects_endpoint():
    """Lists all previously compiled hardware projects."""
    try:
        projects = list_generated_projects()
        return [
            {
                "project_id": p.project_id,
                "title": p.title,
                "prompt": p.prompt,
                "created_at": p.created_at
            }
            for p in projects
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/projects/{project_id}")
def get_project_endpoint(project_id: str):
    """Retrieves a specific hardware design and its corresponding schematics."""
    project = get_generated_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    
    try:
        ir = HardwareIR(**project.hardware_ir)
        ir.assembly_metadata = hydrate_image_storage_metadata(ir.assembly_metadata, project.project_id)
        mermaid_code = generate_mermaid_chart(ir)
        svg_schematic = generate_svg_schematic(ir)
        
        return {
            "project_id": project.project_id,
            "prompt": project.prompt,
            "created_at": project.created_at,
            "project_ir": ir.model_dump(),
            "mermaid_code": mermaid_code,
            "svg_schematic": svg_schematic
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading project IR: {str(e)}")

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
