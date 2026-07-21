# Backend

The backend is a **FastAPI** service that orchestrates agents, validates netlists, renders diagrams, and stores generated projects.

## Key modules
- `backend/main.py` – FastAPI app and API routes
- `backend/a2a.py` – A2A broker, REST/WebSocket/TCP/MCP handlers
- `blueprint_core/generation.py` – high-level generation API
- `blueprint_core/agents/orchestrator.py` – multi-agent pipeline
- `blueprint_core/models.py` – Pydantic Hardware IR schemas
- `blueprint_core/validation.py` – rule-based electrical checks
- `blueprint_core/llm_providers.py` – provider-agnostic structured LLM adapters
- `blueprint_core/image_providers.py` – optional generated product image adapters
- `blueprint_core/runtime_config.py` – deployment and runtime gating helpers
- `blueprint_core/observability.py` – optional Langfuse tracing helpers
- `blueprint_core/database.py` – SQLAlchemy models + DB setup
- `blueprint_core/utils.py` – Mermaid and SVG schematic generation
- `backend/storage.py` – Supabase Storage image uploads, disabled in development mode
- `backend/seed_db.py` – seed component templates

## API endpoints
- `POST /api/generate` – run the pipeline and return IR + diagrams
- `POST /api/alpha-signups` – capture alpha launch interest while deployed generation is gated
- `GET /api/a2a/capabilities` – inspect agent transports and actions
- `PUT /api/a2a/agents/{agent_id}` – register an agent listener
- `POST /api/a2a/messages` – submit or broker an A2A message
- `GET /api/a2a/agents/{agent_id}/events` – long-poll queued A2A events
- `GET /api/a2a/jobs` – list persisted A2A job metadata, including generation `source_usage`
- `GET /api/a2a/jobs/{job_id}` – fetch one persisted A2A job metadata record, including generation `source_usage`
- `GET /api/logs/backend` – tail recent backend and uvicorn log lines for the frontend LOGS tab
- `WebSocket /api/a2a/socket/{agent_id}` – bidirectional A2A event stream
- `POST /api/mcp` and `POST /api/a2a/mcp` – MCP-style JSON-RPC tool endpoint
- `POST /api/validate` – validate a user-supplied netlist
- `GET /api/components` – list component templates
- `GET /api/projects` – list generated projects
- `GET /api/projects/{project_id}` – fetch a stored project
- `POST /api/seed` – re-seed the component database
- `GET /api/debug/config` – inspect LLM, database, image-provider, and image-storage resolution (no secrets)

## Orchestration layer
The orchestrator runs an **ADK-style 7-agent pipeline** (implemented in `blueprint_core/agents/orchestrator.py`). Live agent calls go through `blueprint_core.llm`, which exposes a provider-agnostic structured JSON interface that maps directly to the Hardware IR. If no live provider is configured (or generation fails), the backend falls back to deterministic example projects for a reliable local demo.

## Reusable core package
Generation behavior is packaged under `blueprint_core` so the API server, CLI, smoke tests, workers, and future services all share one implementation. Use `blueprint_core.generation` for high-level generation, `blueprint_core.models` for Hardware IR schemas, `blueprint_core.validation` for electrical checks, `blueprint_core.llm` for provider resolution and structured generation, `blueprint_core.images` for image providers and visual prompt construction, `blueprint_core.runtime` for deployment gating, and `blueprint_core.selectors` for parsing `provider/model` selectors. The legacy backend core modules are compatibility wrappers.

## A2A layer
The A2A layer exposes Blueprint to external agents as a tool server and lightweight broker. REST long-polling, WebSocket, and MCP-style JSON-RPC are always mounted. Job metadata uses `JOB_METADATA_BACKEND=auto`, storing in Supabase when the main app database is Supabase and otherwise falling back to SQLite at `JOB_METADATA_DB_PATH` (default `./blueprint_jobs.db`). `BLUEPRINT_DEV_MODE=true` always uses SQLite for job metadata. The TCP JSONL listener is opt-in with `A2A_SOCKET_ENABLED=true`.

LLM configuration behavior:
- `LOG_LEVEL`: backend logging level, for example `INFO` or `DEBUG`
- `BACKEND_LOG_FILE`: optional rotating log file for backend and uvicorn logs, for example `./blueprint-backend.log`. `./scripts/dev.sh` defaults this to `.logs/backend-dev.log` so the frontend LOGS tab can tail local backend output.
- `BLUEPRINT_DEBUG=true`: include redacted traceback/context debug payloads in API errors and failed job metadata; this also defaults backend logging to `DEBUG` when `LOG_LEVEL` is unset
- `BLUEPRINT_DEV_MODE=true`: forces SQLite for app data and A2A job metadata even when Supabase env vars are present; Supabase Storage writes are disabled and image data stays inline in the SQLite project record
- `BLUEPRINT_DEPLOYMENT=true`: enables the deployment-only alpha gate. If live generation is unavailable, `/api/generate` is blocked and the frontend captures launch interest through `/api/alpha-signups`
- `LLM_PROVIDER`: `anthropic`, `baseten`, `gemini`, `huggingface`, `nvidia`, `openai`, `openai-compatible`, `runpod`, `runpod-serverless`, or `simulation`. Use `runpod` for Runpod OpenAI-compatible/vLLM endpoints and `runpod-serverless` for queue-style `/runsync` workers.
- `LLM_MODEL`: provider model ID
- `/api/generate` accepts optional `provider` and `model` fields for runtime switching. The backend validates them before generation and records requested/actual provider/model metadata on the project.
- `LLM_ALLOWED_PROVIDERS`: optional comma-separated allowlist for runtime provider overrides. If unset, configured providers detected from env plus `simulation` are allowed.
- `OPENAI_ALLOWED_MODELS` / `BASETEN_ALLOWED_MODELS` / `HUGGINGFACE_ALLOWED_MODELS` / `NVIDIA_ALLOWED_MODELS` / `OPENAI_COMPATIBLE_ALLOWED_MODELS` / `GEMINI_ALLOWED_MODELS` / `RUNPOD_ALLOWED_MODELS`: optional comma-separated allowlists for runtime model overrides. If unset, runtime model overrides are limited to configured default/fallback models for the selected provider.
- `OPENAI_API_KEY`: first-party OpenAI API key when `LLM_PROVIDER=openai`
- `OPENAI_MODEL`: first-party OpenAI model alias for `LLM_MODEL`
- `OPENAI_RESPONSE_FORMAT`: OpenAI response format, defaulting to `json_schema`; `json_object` and `none` are also supported
- `OPENAI_TIMEOUT_SECONDS`: first-party OpenAI read timeout, defaulting to `300`
- `OPENAI_REASONING_EFFORT`: optional reasoning effort for GPT-5/o-series models, for example `low`
- `OPENAI_TEMPERATURE`: optional first-party OpenAI sampling temperature. Omitted by default so models that only support their default temperature can run
- `OPENAI_PROJECT_ID` / `OPENAI_ORG_ID`: optional OpenAI project and organization routing headers
- `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`: optional Langfuse project keys. When both are set, Blueprint traces each generation request and structured LLM step.
- `LANGFUSE_BASE_URL`: optional Langfuse host, defaulting to `https://cloud.langfuse.com`.
- `LANGFUSE_TRACING_ENVIRONMENT` / `LANGFUSE_TRACING_RELEASE`: optional trace attributes for environment and release filtering.
- `LANGFUSE_MAX_FIELD_CHARS`: optional per-field payload cap for traced prompt/output previews, defaulting to `20000`.
- `LANGFUSE_ENABLED=false`: explicit opt-out when project keys are present in the runtime environment.
- `IMAGE_OUTPUT_ENABLED=true`: make product concept image generation the default. Requests can opt in per job with `generate_image=true`
- `IMAGE_PROVIDER`: `openai`, `openai-compatible`, `huggingface`, or `none`
- `OPENAI_IMAGE_MODEL`: first-party OpenAI image model, for example `gpt-image-2`
- `OPENAI_IMAGE_SIZE`: image output size, for example `1024x1024`
- `HUGGINGFACE_IMAGE_MODEL` / `HUGGINGFACE_IMAGE_INFERENCE_PROVIDER`: Hugging Face text-to-image model and underlying inference provider when `IMAGE_PROVIDER=huggingface`
- `HUGGINGFACE_IMAGE_MODEL_REVISION` / `HUGGINGFACE_IMAGE_MODEL_LICENSE`: optional policy metadata recorded with stored Hugging Face image outputs
- `SUPABASE_S3_ENDPOINT`: Supabase Storage S3 endpoint associated with image uploads, defaulting from `SUPABASE_URL` when possible
- `SUPABASE_S3_BUCKET`: Supabase Storage bucket for reference and generated product images, defaulting to `contents`
- `SUPABASE_S3_ACCESS_KEY_ID` / `SUPABASE_S3_SECRET_ACCESS_KEY`: optional S3-compatible fallback credentials. The normal backend path writes through the Supabase client using `SUPABASE_URL` plus the service-role/secret key; `BLUEPRINT_DEV_MODE=true` disables these image uploads
- `SUPABASE_IMAGE_SIGNED_URL_SECONDS`: lifetime for refreshed Supabase Storage read URLs when projects are loaded, defaulting to `86400`
- `SUPABASE_STORAGE_PUBLIC_BASE_URL`: optional public object URL base; defaults from `SUPABASE_URL` or the S3 endpoint
- `LLM_FALLBACK_MODEL`: optional fallback model
- `LLM_TIMEOUT_SECONDS`: generic read timeout. OpenAI-compatible endpoints default to `90`
- `LLM_REASONING_EFFORT`: optional generic reasoning effort for compatible endpoints that support it
- `LLM_TEMPERATURE`: optional generic sampling temperature. OpenAI-compatible endpoints default to `0.2`; set `default`, `none`, or `omit` to omit it
- `RUNPOD_MAX_TOKENS` / `LLM_MAX_TOKENS`: output token budget for structured generation. A budget is now always sent. When no `*_MAX_TOKENS` is set it defaults to `8192`, and large schemas (for example `MechanicalNotes`, whose JSON schema is ~6,656 chars) are raised to a `6000` floor so big records are not truncated mid-string. Small schemas keep the configured value. Set `RUNPOD_MAX_TOKENS=8192` on parti-base backends.
- Structured calls do one bounded retry: on a validation failure the request is re-sent once with a larger budget (doubled, floored at `6000`, capped at `16384`). Truncated-but-recoverable JSON is salvaged with `json-repair` (structure closed, half-written trailing item pruned, then full pydantic validation), so a completion cut off at the token cap still yields a valid record. If both attempts fail the backend returns `502 llm_output_invalid` instead of the generic `500 generation_failed`.
- `RUNPOD_RESPONSE_FORMAT` / `LLM_RESPONSE_FORMAT`: response format for the endpoint, defaulting to `json_object`. Set `json_schema` for vLLM grammar-constrained JSON (requires vLLM >= 0.6.3 on the Runpod worker; the first request for a large schema pays a grammar-compile latency). `json_schema` does not prevent truncation, so the token budget, salvage, and retry above still apply.
- `BASETEN_API_KEY` / `BASETEN_BASE_URL`: Baseten Model APIs configuration when `LLM_PROVIDER=baseten` or a request uses `provider=baseten`. `BASETEN_BASE_URL` defaults to `https://inference.baseten.co/v1`.
- `BASETEN_MODEL`: Baseten model slug, for example `deepseek-ai/DeepSeek-V4-Pro`
- `HF_TOKEN` / `HUGGINGFACE_API_KEY` / `HUGGINGFACE_HUB_TOKEN`: Hugging Face Inference Providers token when `LLM_PROVIDER=huggingface` or a request uses `provider=huggingface`
- `HUGGINGFACE_BASE_URL`: Hugging Face OpenAI-compatible router URL. Defaults to `https://router.huggingface.co/v1`
- `ANTHROPIC_API_KEY` / `CLAUDE_API_KEY`: Anthropic Claude key when `LLM_PROVIDER=anthropic` or a request uses `provider=anthropic`
- `ANTHROPIC_BASE_URL`: Claude API base URL. Defaults to `https://api.anthropic.com/v1`
- `HUGGINGFACE_MODEL`: Hugging Face model ID, for example `Qwen/Qwen2.5-Coder-3B-Instruct:nscale`
- `NVIDIA_API_KEY` / `NVIDIA_BASE_URL`: NVIDIA Build/NIM configuration when `LLM_PROVIDER=nvidia` or a request uses `provider=nvidia`. `NVIDIA_BASE_URL` defaults to `https://integrate.api.nvidia.com/v1`.
- `NVIDIA_MODEL`: NVIDIA model slug, for example `nvidia/z-ai/glm-5.2`
- `RUNPOD_API_KEY` / `RUNPOD_OPENAI_BASE_URL`: Runpod OpenAI-compatible/vLLM configuration when `LLM_PROVIDER=runpod` or a request uses `provider=runpod`
- `RUNPOD_ENDPOINT_ID` / `RUNPOD_ENDPOINT_URL`: Runpod Serverless queue configuration when `LLM_PROVIDER=runpod-serverless` or a request uses `provider=runpod-serverless`
- `RUNPOD_MODEL_ENDPOINTS`: optional JSON object mapping model IDs to Runpod endpoint IDs or endpoint URLs when each model is hosted on a separate Serverless endpoint
- `RUNPOD_INPUT_TEMPLATE`: optional JSON payload template for Runpod workers. Use `{prompt}` and, for single-endpoint multi-model workers, `{model}` placeholders.
- `RUNPOD_TIMEOUT_SECONDS`: Runpod HTTP read timeout. Defaults to `1200` for 10-15 minute cold starts or long generations.
- `RUNPOD_POLL_TIMEOUT_SECONDS`: Runpod Serverless `/status` polling timeout. Defaults to `1200`.
- `RUNPOD_EXECUTION_TIMEOUT_MS` / `RUNPOD_TTL_MS`: Runpod Serverless job policy values. Use `1200000` for 20-minute generation windows.
- `RUNPOD_PARTI_SEED_TIMEOUT_SECONDS`: optional timeout for the `caid-technologies/parti-base` seed call. Defaults to `RUNPOD_TIMEOUT_SECONDS`; set lower to fall back to catalog repair faster.
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

To make backend logs visible in the local frontend LOGS tab when running uvicorn directly, set `BACKEND_LOG_FILE`:

```bash
BACKEND_LOG_FILE=.logs/backend-dev.log uvicorn backend.main:app --reload --port 8000
```

Switch the generation LLM from the CLI with `--llm provider/model`:

```bash
./scripts/blueprint-backend generate "plant watering monitor" --llm openai/gpt-5.5
./scripts/blueprint-backend generate "plant watering monitor" --llm runpod/caid-technologies/parti-base
```

Smoke-test configured LLM providers with a tiny structured prompt:

```bash
./scripts/verify-llm-providers.py --list
./scripts/verify-llm-providers.py --config-only
./scripts/verify-llm-providers.py --save
./scripts/run-llm-smoke-tests.py
./scripts/verify-llm-providers.py --llm openai/gpt-5.5
./scripts/verify-llm-providers.py --llm runpod/caid-technologies/parti-base --timeout-seconds 1200
./scripts/verify-llm-providers.py --llm baseten/deepseek-ai/DeepSeek-V4-Pro
./scripts/verify-llm-providers.py --llm huggingface/Qwen/Qwen2.5-Coder-3B-Instruct:nscale
./scripts/verify-llm-providers.py --llm nvidia/nvidia/z-ai/glm-5.2
./sample.py "Describe a low-voltage plant watering monitor with OLED status"
./sample_async.py --concurrency 4 "Describe a low-voltage plant watering monitor with OLED status"
```

Saved smoke-test reports are written to `.logs/llm-smoke/` by default, with `.logs/llm-smoke/latest.json` overwritten on each saved run. `sample.py` writes model comparison reports to `.logs/model-samples/` and `.logs/model-samples/latest.json`. `sample_async.py` writes the same report format while running selected models concurrently with `--concurrency`. The automated runner accepts `LLM_SMOKE_LLM`, `LLM_SMOKE_CONFIG_ONLY`, `LLM_SMOKE_TIMEOUT_SECONDS`, and `LLM_SMOKE_OUTPUT_DIR`.

Run against first-party OpenAI:

```bash
LLM_PROVIDER=openai OPENAI_API_KEY=your_openai_api_key_here OPENAI_MODEL=gpt-4o-mini uvicorn backend.main:app --reload --port 8000
```
