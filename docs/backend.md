# Backend

The backend is a **FastAPI** service that orchestrates agents, validates netlists, renders diagrams, and stores generated projects.

## Key modules
- `backend/main.py` – FastAPI app and API routes
- `backend/agents/orchestrator.py` – multi-agent pipeline
- `backend/validation.py` – rule-based electrical checks
- `backend/models.py` – Pydantic IR schemas
- `backend/database.py` – SQLAlchemy models + DB setup
- `backend/seed_db.py` – seed component templates
- `backend/utils.py` – Mermaid and SVG schematic generation

## API endpoints
- `POST /api/generate` – run the pipeline and return IR + diagrams
- `POST /api/validate` – validate a user-supplied netlist
- `GET /api/components` – list component templates
- `GET /api/projects` – list generated projects
- `GET /api/projects/{project_id}` – fetch a stored project
- `POST /api/seed` – re-seed the component database
- `GET /debug/config` – inspect Gemini model resolution (no secrets)

## Orchestration layer
The orchestrator runs an **ADK-style 7-agent pipeline** (implemented in `backend/agents/orchestrator.py`). When a Gemini API key is configured, agents generate structured JSON that maps directly to the Hardware IR. If no key is set (or generation fails), the backend falls back to deterministic example projects for a reliable local demo.

Gemini configuration behavior:
- Default model: `gemini-3.5-flash`
- Fallback model: `gemini-2.5-flash`
- `STRICT_GEMINI=true` (default) fails fast when the requested model is unavailable
- `STRICT_GEMINI=false` allows fallback to the configured fallback model

## Validation
Validation is run after the netlist step. Critical issues trigger a repair loop that re-invokes the wiring agent before finalizing the IR.

## Startup behavior
On startup the server:
- Initializes the DB schema
- Auto-seeds component templates if the catalog is empty

## Running locally
Run the server from the repo root:

```bash
uvicorn backend.main:app --reload --port 8000
```
