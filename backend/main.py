from pathlib import Path
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
from dotenv import load_dotenv

load_dotenv()

from backend.database import (
    count_component_templates,
    get_database_config,
    get_generated_project,
    init_db,
    list_component_templates,
    list_generated_projects,
)
from backend.seed_db import seed_database
from backend.models import (
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
from backend.storage import get_image_storage_config, hydrate_image_storage_metadata
from backend.validation import validate_circuit
from backend.utils import generate_mermaid_chart, generate_svg_schematic

app = FastAPI(
    title="Blueprint Open-Source API",
    description="AI-native prompt-to-hardware compilation, validation, and design generation platform.",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    swagger_ui_oauth2_redirect_url="/api/docs/oauth2-redirect",
)

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In development, allow all. Can narrow in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

@app.get("/api")
@app.get("/api/")
def read_root():
    return {
        "status": "online",
        "service": "Blueprint Open-Source Hardware Compiler",
        "version": "1.0.0",
        "docs_url": "/api/docs"
    }

@app.get("/api/debug/config")
def debug_config_endpoint():
    """
    Reports LLM provider and model resolution state without exposing credentials.
    """
    try:
        orchestrator = HardwarePipelineOrchestrator()
        return {
            **orchestrator.get_debug_config(),
            "database": get_database_config(),
            "job_metadata": JOB_STORE.get_config(),
            "image_output": get_image_output_debug_config(),
            "image_storage": get_image_storage_config(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Debug config failed: {str(e)}")

@app.post("/api/generate", response_model=Dict[str, Any])
def generate_project_endpoint(request: GenerateProjectRequest):
    """
    Submits a natural language hardware idea and optional multimodal reference image.
    Runs the 7-agent compilation workflow, circuit safety auditor, and returns a verified Hardware IR, SVG schematic, and Mermaid diagram.
    """
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
    except Exception as e:
        JOB_STORE.mark_failed(job_id, str(e))
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")


@app.get("/api/a2a/capabilities")
def a2a_capabilities_endpoint():
    """Advertises Blueprint's A2A transports, actions, and MCP tools."""
    return get_a2a_capabilities()


@app.put("/api/a2a/agents/{agent_id}")
async def register_a2a_agent(agent_id: str, registration: A2AAgentRegistration):
    """Registers an agent so it can receive queued A2A events."""
    record = registration.model_dump()
    record["agent_id"] = registration.agent_id or agent_id
    return await A2A_HUB.register(agent_id, record)


@app.post("/api/a2a/messages")
async def send_a2a_message(message: A2AMessage):
    """Submits an A2A message and queues an async result for the sender."""
    ack = await submit_a2a_message(message)
    return ack.model_dump()


@app.get("/api/a2a/agents/{agent_id}/events")
async def poll_a2a_events(
    agent_id: str,
    timeout: float = Query(25.0, ge=0.0, le=60.0),
    limit: int = Query(10, ge=1, le=100),
):
    """Long-polls queued A2A events for an agent."""
    events = await A2A_HUB.poll(agent_id, timeout=timeout, limit=limit)
    return [event.model_dump() for event in events]


@app.get("/api/a2a/jobs")
def list_a2a_jobs(
    sender: str | None = None,
    job_status: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
):
    """Lists persisted A2A job metadata."""
    return JOB_STORE.list_jobs(sender=sender, status=job_status, limit=limit)


@app.get("/api/a2a/jobs/{job_id}")
def get_a2a_job(job_id: str):
    """Fetches persisted metadata for one A2A job."""
    job = JOB_STORE.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="A2A job not found.")
    return job


@app.websocket("/api/a2a/socket/{agent_id}")
async def a2a_websocket_endpoint(websocket: WebSocket, agent_id: str):
    """WebSocket A2A transport. Send A2AMessage JSON; receive A2AEvent JSON."""
    await handle_a2a_websocket(websocket, agent_id)


@app.post("/api/mcp")
async def mcp_endpoint(payload: Any = Body(...)):
    """MCP-style JSON-RPC endpoint exposing Blueprint tools."""
    return await handle_mcp_json_rpc(payload)


@app.post("/api/a2a/mcp")
async def a2a_mcp_endpoint(payload: Any = Body(...)):
    """Alias for agents that discover MCP under the A2A route prefix."""
    return await handle_mcp_json_rpc(payload)

@app.get("/api/projects")
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

@app.get("/api/projects/{project_id}")
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

@app.get("/api/components")
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

@app.post("/api/seed", status_code=status.HTTP_201_CREATED)
def trigger_db_seeding():
    """Manual trigger to re-seed the parts library database."""
    try:
        seed_database()
        return {"message": "Database templates successfully seeded."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Dedicated schemas for validate endpoint
from pydantic import BaseModel

class ValidateCircuitRequest(BaseModel):
    components: List[ComponentInstance]
    nets: List[ConnectionNet]

@app.post("/api/validate", response_model=ValidationReport)
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
