# Backend

The backend is a **FastAPI** service that orchestrates agents, validates netlists, renders diagrams, and stores generated projects.

## Key modules
- `backend/main.py` – FastAPI app and API routes
- `backend/agents/orchestrator.py` – multi-agent pipeline
- `backend/a2a.py` – A2A broker, REST/WebSocket/TCP/MCP handlers
- `backend/llm_providers.py` – provider-agnostic structured LLM adapters
- `backend/image_providers.py` – optional generated product image adapters
- `backend/validation.py` – rule-based electrical checks
- `backend/models.py` – Pydantic IR schemas
- `backend/database.py` – SQLAlchemy models + DB setup
- `backend/seed_db.py` – seed component templates
- `backend/utils.py` – Mermaid and SVG schematic generation

## API endpoints
- `POST /api/generate` – run the pipeline and return IR + diagrams
- `GET /api/a2a/capabilities` – inspect agent transports and actions
- `PUT /api/a2a/agents/{agent_id}` – register an agent listener
- `POST /api/a2a/messages` – submit or broker an A2A message
- `GET /api/a2a/agents/{agent_id}/events` – long-poll queued A2A events
- `GET /api/a2a/jobs` – list persisted SQLite A2A job metadata
- `GET /api/a2a/jobs/{job_id}` – fetch one persisted A2A job metadata record
- `WebSocket /api/a2a/socket/{agent_id}` – bidirectional A2A event stream
- `POST /mcp` and `POST /api/a2a/mcp` – MCP-style JSON-RPC tool endpoint
- `POST /api/validate` – validate a user-supplied netlist
- `GET /api/components` – list component templates
- `GET /api/projects` – list generated projects
- `GET /api/projects/{project_id}` – fetch a stored project
- `POST /api/seed` – re-seed the component database
- `GET /debug/config` – inspect LLM provider and model resolution (no secrets)

## Orchestration layer
The orchestrator runs an **ADK-style 7-agent pipeline** (implemented in `backend/agents/orchestrator.py`). Live agent calls go through `backend/llm_providers.py`, which exposes a provider-agnostic structured JSON interface that maps directly to the Hardware IR. If no live provider is configured or generation fails, the job is marked failed and the stored error is available through the Jobs API and UI.

## A2A layer
The A2A layer exposes Blueprint to external agents as a tool server and lightweight broker. REST long-polling, WebSocket, and MCP-style JSON-RPC are always mounted. Job metadata is persisted to SQLite at `JOB_METADATA_DB_PATH` (default `./blueprint_jobs.db`). The TCP JSONL listener is opt-in with `A2A_SOCKET_ENABLED=true`.

LLM configuration behavior:
- Local text, vision, and image generation recipes live in [Local Models](local-models.md).
- `LOG_LEVEL`: backend log level, defaulting to `INFO`
- `BACKEND_LOG_FILE`: optional backend log file path, for example `./blueprint-backend.log`
- `LLM_PROVIDER`: `gemini`, `openai`, `openai-compatible`, or `simulation`
- `LLM_MODEL`: provider model ID
- `LLM_MODELS`: optional ordered comma-separated provider model list; supersedes `LLM_MODEL`
- `OPENAI_API_KEY`: first-party OpenAI API key when `LLM_PROVIDER=openai`
- `OPENAI_MODEL`: first-party OpenAI model alias for `LLM_MODEL`
- `OPENAI_MODELS`: optional ordered comma-separated first-party OpenAI model list; supersedes `OPENAI_MODEL`
- `OPENAI_RESPONSE_FORMAT`: OpenAI response format, defaulting to `json_schema`; `json_object` and `none` are also supported
- `OPENAI_TIMEOUT_SECONDS`: first-party OpenAI read timeout, defaulting to `300`
- `OPENAI_REASONING_EFFORT`: optional reasoning effort for GPT-5/o-series models, for example `low`
- `OPENAI_TEMPERATURE`: optional first-party OpenAI sampling temperature. Omitted by default so models that only support their default temperature can run
- `OPENAI_PROJECT_ID` / `OPENAI_ORG_ID`: optional OpenAI project and organization routing headers
- `IMAGE_OUTPUT_ENABLED=true`: make product concept image generation the default. Requests can opt in per job with `generate_image=true`
- `IMAGE_PROVIDER`: `openai`, `openai-compatible`, `local`, `stable-diffusion-webui`, or `none`
- `OPENAI_IMAGE_MODEL`: first-party OpenAI image model, for example `gpt-image-2`
- `OPENAI_IMAGE_SIZE`: image output size, for example `1024x1024`
- `IMAGE_TEXT_PROVIDER`: optional uploaded-image text extraction provider: `openai`, `openai-compatible`, `local`, `ollama`, or `none`
- `IMAGE_TEXT_BASE_URL` / `IMAGE_TEXT_MODEL`: local vision endpoint and model used before structured generation
- `IMAGE_TEXT_ALLOW_NO_API_KEY=true`: allow local OpenAI-compatible vision endpoints without auth
- `IMAGE_TEXT_FORWARD_IMAGE=false`: append extracted image text and do not forward the raw image to the structured LLM
- `IMAGE_BASE_URL` / `IMAGE_MODEL`: generic local OpenAI-compatible image endpoint and model
- `STABLE_DIFFUSION_BASE_URL`: Stable Diffusion WebUI / Automatic1111 base URL for local image generation
- `LLM_FALLBACK_MODEL`: optional fallback model
- `LLM_FALLBACK_MODELS`: optional ordered comma-separated fallback model list
- `LLM_TIMEOUT_SECONDS`: generic read timeout. OpenAI-compatible endpoints default to `90`
- `LLM_REASONING_EFFORT`: optional generic reasoning effort for compatible endpoints that support it
- `LLM_TEMPERATURE`: optional generic sampling temperature. OpenAI-compatible endpoints default to `0.2`; set `default`, `none`, or `omit` to omit it
- `STRICT_LLM=true` (default) fails fast when model availability validation is enabled and none of the primary configured models are available
- `STRICT_LLM=false` allows fallback to the configured fallback model or fallback model list
- Gemini-specific env vars remain supported as aliases for existing deployments

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

Run against first-party OpenAI:

```bash
LLM_PROVIDER=openai OPENAI_API_KEY=your_openai_api_key_here OPENAI_MODEL=gpt-4o-mini uvicorn backend.main:app --reload --port 8000
```
