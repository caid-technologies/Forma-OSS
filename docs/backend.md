# Backend

The backend is a **FastAPI** service that orchestrates agents, validates netlists, renders diagrams, and stores generated projects.

## Key modules
- `backend/main.py` – FastAPI app and API routes
- `backend/agents/orchestrator.py` – multi-agent pipeline
- `backend/a2a.py` – A2A broker, REST/WebSocket/TCP/MCP handlers
- `backend/llm_providers.py` – provider-agnostic structured LLM adapters
- `backend/image_providers.py` – optional generated product image adapters
- `backend/storage.py` – Supabase Storage image uploads, disabled in development mode
- `backend/validation.py` – rule-based electrical checks
- `backend/models.py` – Pydantic IR schemas
- `backend/database.py` – SQLAlchemy models + DB setup
- `backend/seed_db.py` – seed component templates
- `backend/utils.py` – Mermaid and SVG schematic generation

## API endpoints
- `POST /api/generate` – run the pipeline and return IR + diagrams
- `POST /api/alpha-signups` – capture alpha launch interest while deployed generation is gated
- `GET /api/a2a/capabilities` – inspect agent transports and actions
- `PUT /api/a2a/agents/{agent_id}` – register an agent listener
- `POST /api/a2a/messages` – submit or broker an A2A message
- `GET /api/a2a/agents/{agent_id}/events` – long-poll queued A2A events
- `GET /api/a2a/jobs` – list persisted A2A job metadata
- `GET /api/a2a/jobs/{job_id}` – fetch one persisted A2A job metadata record
- `WebSocket /api/a2a/socket/{agent_id}` – bidirectional A2A event stream
- `POST /api/mcp` and `POST /api/a2a/mcp` – MCP-style JSON-RPC tool endpoint
- `POST /api/validate` – validate a user-supplied netlist
- `GET /api/components` – list component templates
- `GET /api/projects` – list generated projects
- `GET /api/projects/{project_id}` – fetch a stored project
- `POST /api/seed` – re-seed the component database
- `GET /api/debug/config` – inspect LLM, database, image-provider, and image-storage resolution (no secrets)

## Orchestration layer
The orchestrator runs an **ADK-style 7-agent pipeline** (implemented in `backend/agents/orchestrator.py`). Live agent calls go through `backend/llm_providers.py`, which exposes a provider-agnostic structured JSON interface that maps directly to the Hardware IR. If no live provider is configured (or generation fails), the backend falls back to deterministic example projects for a reliable local demo.

## A2A layer
The A2A layer exposes Blueprint to external agents as a tool server and lightweight broker. REST long-polling, WebSocket, and MCP-style JSON-RPC are always mounted. Job metadata uses `JOB_METADATA_BACKEND=auto`, storing in Supabase when the main app database is Supabase and otherwise falling back to SQLite at `JOB_METADATA_DB_PATH` (default `./blueprint_jobs.db`). `BLUEPRINT_DEV_MODE=true` always uses SQLite for job metadata. The TCP JSONL listener is opt-in with `A2A_SOCKET_ENABLED=true`.

LLM configuration behavior:
- `BLUEPRINT_DEV_MODE=true`: forces SQLite for app data and A2A job metadata even when Supabase env vars are present; Supabase Storage writes are disabled and image data stays inline in the SQLite project record
- `BLUEPRINT_DEPLOYMENT=true`: enables the deployment-only alpha gate. If live generation is unavailable, `/api/generate` is blocked and the frontend captures launch interest through `/api/alpha-signups`
- `LLM_PROVIDER`: `gemini`, `openai`, `openai-compatible`, or `simulation`
- `LLM_MODEL`: provider model ID
- `OPENAI_API_KEY`: first-party OpenAI API key when `LLM_PROVIDER=openai`
- `OPENAI_MODEL`: first-party OpenAI model alias for `LLM_MODEL`
- `OPENAI_RESPONSE_FORMAT`: OpenAI response format, defaulting to `json_schema`; `json_object` and `none` are also supported
- `OPENAI_TIMEOUT_SECONDS`: first-party OpenAI read timeout, defaulting to `300`
- `OPENAI_REASONING_EFFORT`: optional reasoning effort for GPT-5/o-series models, for example `low`
- `OPENAI_TEMPERATURE`: optional first-party OpenAI sampling temperature. Omitted by default so models that only support their default temperature can run
- `OPENAI_PROJECT_ID` / `OPENAI_ORG_ID`: optional OpenAI project and organization routing headers
- `IMAGE_OUTPUT_ENABLED=true`: make product concept image generation the default. Requests can opt in per job with `generate_image=true`
- `IMAGE_PROVIDER`: `openai`, `openai-compatible`, or `none`
- `OPENAI_IMAGE_MODEL`: first-party OpenAI image model, for example `gpt-image-2`
- `OPENAI_IMAGE_SIZE`: image output size, for example `1024x1024`
- `SUPABASE_S3_ENDPOINT`: Supabase Storage S3 endpoint associated with image uploads, defaulting from `SUPABASE_URL` when possible
- `SUPABASE_S3_BUCKET`: Supabase Storage bucket for reference and generated product images, defaulting to `contents`
- `SUPABASE_S3_ACCESS_KEY_ID` / `SUPABASE_S3_SECRET_ACCESS_KEY`: optional S3-compatible fallback credentials. The normal backend path writes through the Supabase client using `SUPABASE_URL` plus the service-role/secret key; `BLUEPRINT_DEV_MODE=true` disables these image uploads
- `SUPABASE_IMAGE_SIGNED_URL_SECONDS`: lifetime for refreshed Supabase Storage read URLs when projects are loaded, defaulting to `86400`
- `SUPABASE_STORAGE_PUBLIC_BASE_URL`: optional public object URL base; defaults from `SUPABASE_URL` or the S3 endpoint
- `LLM_FALLBACK_MODEL`: optional fallback model
- `LLM_TIMEOUT_SECONDS`: generic read timeout. OpenAI-compatible endpoints default to `90`
- `LLM_REASONING_EFFORT`: optional generic reasoning effort for compatible endpoints that support it
- `LLM_TEMPERATURE`: optional generic sampling temperature. OpenAI-compatible endpoints default to `0.2`; set `default`, `none`, or `omit` to omit it
- `STRICT_LLM=true` (default) fails fast when model availability validation is enabled and the requested model is unavailable
- `STRICT_LLM=false` allows fallback to the configured fallback model
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
