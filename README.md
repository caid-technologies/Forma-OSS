# Forma

Forma is AI-native full-stack hardware. It turns a prompt (and optionally an image) into a structured, validated **Hardware IR** package plus generated product imagery, wiring diagrams, BOM, and build steps.

This repository is an **MVP and research prototype** focused on **low-voltage maker electronics** (3.3V–5V) and safe, educational projects.

![Blueprint project workspace showing a generated 3D printer concept and validated parts list](docs/assets/blueprint-project-3d-printer.png)

## What you can do
- Compile a hardware idea into typed **Hardware IR** (Pydantic)
- Run **rule-based electrical validation** (shorts, voltage mismatch, unpowered ICs, pin conflicts, overcurrent risk)
- Visualize wiring with:
  - Interactive **React Flow** schematic
  - Generated **SVG** schematic
- View a lightweight **3D mechanical layout** (Three.js / React Three Fiber)
- Generate an optional **product concept image** with an image model
- Persist generated projects to **Supabase** through the Supabase client when configured, with an automatic **SQLite fallback** and `BLUEPRINT_DEV_MODE` for SQLite-only local work
- Trace generation runs and structured LLM calls with **Langfuse** when project keys are configured
- Let external agents integrate over **REST long-polling, WebSocket, optional TCP JSONL sockets, or MCP-style JSON-RPC tools**

## How it works

Blueprint follows a sequential processing pipeline:

1. **Input**: User provides a prompt and optional image
2. **Agent Processing**: ADK-style sequential agents process the input using the configured structured LLM provider
3. **Hardware IR Generation**: Agents produce typed Hardware IR (Pydantic models)
4. **Validation & Repair**: Rule-based validation checks the design and repairs issues automatically
5. **UI Outputs**: Generate interactive visualizations (product image, React Flow schematic, SVG diagrams, 3D mechanical layout) and save to database
6. **Persistence**: Project data is stored in Supabase or SQLite

## MVP scope & safety boundaries
Blueprint intentionally limits scope to low-voltage maker electronics:
- 3.3V–5V DC systems
- Breadboard-friendly microcontrollers, sensors, displays, and actuators
- Educational and hobbyist prototypes

It blocks or warns on high-risk domains (mains AC, medical, automotive control, weapons, high-power battery packs). See [docs/validation.md](docs/validation.md).

## Local setup (quick)
Detailed instructions live in [docs/setup.md](docs/setup.md). The short version:

### Run Everything
From the repo root:

```bash
./scripts/dev.sh
```

This starts the FastAPI backend and Next.js frontend together. Use `BACKEND_PORT`, `FRONTEND_PORT`, `BACKEND_HOST`, or `FRONTEND_HOST` to override defaults.

### Python Package (PyPI)
The reusable core is published on PyPI as [`caid-blueprint-core`](https://pypi.org/project/caid-blueprint-core/). The distribution name is `caid-blueprint-core`; the Python import package is `blueprint_core`.

```bash
pip install caid-blueprint-core
```

```python
import blueprint_core
from blueprint_core.generation import HardwarePipelineOrchestrator, list_workflows
from blueprint_core.models import HardwareIR
```

### Docker
Build and run both images from the repo root:

```bash
docker compose up --build
```

The Docker setup runs the backend on port `8000`, the frontend on port `3000`, and stores SQLite data in a named Docker volume. Set `LLM_PROVIDER`, `OPENAI_API_KEY`, `LLM_API_KEY`, or the other variables from `.env.example` before running Compose to use a live model provider; otherwise the backend defaults to simulation mode.

If you change the published backend URL, rebuild the frontend with a matching public API URL:

```bash
BACKEND_PORT=8010 NEXT_PUBLIC_API_URL=http://localhost:8010 docker compose up --build
```

### Backend (FastAPI)
From the repo root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

**Optional: seed the component library**
The server auto-seeds the component library on startup if empty. To seed manually:

```bash
python3 backend/seed_db.py
```

**Run the backend:**
```bash
uvicorn backend.main:app --reload --port 8000
```

**Backend CLI:**
```bash
./scripts/blueprint-backend serve --reload
./scripts/blueprint-backend health
./scripts/blueprint-backend jobs --status running
./scripts/blueprint-backend jobs --local --limit 10
./scripts/test.sh
./sample.py "Describe a low-voltage plant watering monitor with OLED status"
./sample_async.py --llm openai/gpt-5.5 --llm runpod/caid-technologies/parti-base "Describe a low-voltage plant watering monitor with OLED status"
./scripts/blueprint-backend generate "plant watering monitor" --llm openai/gpt-5.5
./scripts/blueprint-backend generate "plant watering monitor" --llm runpod/caid-technologies/parti-base
curl -X POST http://127.0.0.1:8000/projects/<project-id>/iterate -H 'Content-Type: application/json' -d '{"instruction":"Add battery charging and make the enclosure splash resistant","namespace":"product.mech","provider":"openai","model":"gpt-5.5"}'
./scripts/verify-llm-providers.py --list
./scripts/verify-llm-providers.py
./scripts/verify-llm-providers.py --save
./scripts/run-llm-smoke-tests.py
./scripts/verify-llm-providers.py --llm openai/gpt-5.5
./scripts/verify-llm-providers.py --llm runpod/caid-technologies/parti-base --timeout-seconds 1200
./scripts/verify-llm-providers.py --llm baseten/deepseek-ai/DeepSeek-V4-Pro
./scripts/verify-llm-providers.py --llm huggingface/Qwen/Qwen2.5-Coder-3B-Instruct:nscale
./scripts/verify-llm-providers.py --llm nvidia/meta/llama-3.1-8b-instruct
./scripts/blueprint-backend seed
```

`scripts/test.sh` runs the offline unit suite with `unittest` after a Python compile check. `sample.py` sends the same prompt to each configured/allowed provider-model pair and saves a comparison report under `.logs/model-samples/`. `sample_async.py` does the same work concurrently, running one nonblocking task per selected model up to `--concurrency`. `verify-llm-providers.py` discovers the configured runtime provider/model pairs from `.env`, sends a tiny structured JSON prompt, and exits non-zero if any live provider returns invalid output. Use `--config-only` to validate selectors without spending tokens or waiting on long Runpod jobs. Use `--save` or `run-llm-smoke-tests.py` to write timestamped reports under `.logs/llm-smoke/`, plus `.logs/llm-smoke/latest.json`. The automated runner also accepts `LLM_SMOKE_LLM`, `LLM_SMOKE_CONFIG_ONLY`, `LLM_SMOKE_TIMEOUT_SECONDS`, and `LLM_SMOKE_OUTPUT_DIR` for CI or cron-style runs.

Generation and project iteration logic lives in the reusable `blueprint_core` package, published as the `caid-blueprint-core` PyPI distribution. New code should import from `blueprint_core.generation`, `blueprint_core.iteration`, `blueprint_core.project_objects`, `blueprint_core.models`, `blueprint_core.validation`, `blueprint_core.llm`, `blueprint_core.images`, `blueprint_core.runtime`, and `blueprint_core.selectors`; the old backend modules are compatibility wrappers. Projects are represented as `BlueprintProjectObject` values with an object version plus versioned namespaces such as `product.mech`, `product.electrical`, `product.validation`, `product.assembly`, `project.docs`, and `project.history`. `ProjectIterator.iterate_project(...)` takes an existing `HardwareIR` plus a natural-language instruction, can target a namespace, returns a full revised `HardwareIR`, normalizes revision/history/object metadata, redacts bulky data URLs from LLM context, and reruns circuit validation before returning. `ProjectSelfCorrectionAgent` builds validation-driven repair instructions and applies them through the same namespace-aware iterator.

Benchmarks live under `benchmarks/` and save JSON reports under `.logs/benchmarks/`:
```bash
./scripts/benchmark.sh
./benchmarks/benchmark_models.py --iterations 1
./benchmarks/benchmark_models.py --live --llm openai/gpt-5.5 --iterations 3 --concurrency 2
```

`benchmark_models.py` defaults to config-only mode so it can run safely without spending provider calls. Add `--live` when you want real LLM latency measurements. Each completed provider/model attempt is also flushed immediately to per-run JSONL and CSV files named `model-job-results-*.jsonl` and `model-job-results-*.csv`, including status, round, completion time, and duration fields.

Benchmark, output, and eval artifacts can be uploaded to a Hugging Face dataset repo:

```bash
export HF_TOKEN=...
export HF_ARTIFACT_REPO_ID=username/blueprint-metrics

./benchmarks/benchmark_models.py --live --iterations 3 --upload-huggingface
./benchmarks/benchmark_offline.py --upload-huggingface
./scripts/upload-artifacts-to-huggingface.py --artifact-type outputs examples/results
./scripts/upload-artifacts-to-huggingface.py --artifact-type evals .logs/evals
```

The CLI uses `.venv/bin/python` when present and falls back to `python3`. `health`
checks the root, component, and A2A jobs endpoints; `jobs --local` reads the
SQLite job metadata store directly when the API server is not running. Job
tables include the generation source when known: `Catalog`, `Web Research`, or
both.

To run with OpenAI:
```bash
LLM_PROVIDER=openai OPENAI_API_KEY=your_openai_api_key_here OPENAI_MODEL=gpt-4o-mini uvicorn backend.main:app --reload --port 8000
```

Environment variables (recommended via a repo-root `.env`; see `.env.example`):
- `LOG_LEVEL`: Backend logging level, for example `INFO` or `DEBUG`.
- `BACKEND_LOG_FILE`: Optional rotating log file for backend and uvicorn logs, for example `./blueprint-backend.log`.
- `BLUEPRINT_DEBUG`: When `true`, API errors and failed job metadata include redacted traceback/context debug payloads. Intended for trusted local/dev environments.
- `SUPABASE_URL`: Supabase project API URL, for example `https://your-project-ref.supabase.co`.
- `SUPABASE_SERVICE_ROLE_KEY` / `SUPABASE_SECRET_KEY`: Backend-only Supabase key for writes. Do not use anon/publishable keys.
- `BLUEPRINT_DEV_MODE`: When `true`, forces SQLite for app data and A2A job metadata, disables Supabase Storage writes, and keeps reference/product image data inline in the SQLite project record.
- `NEXT_PUBLIC_BLUEPRINT_DEBUG` / `NEXT_PUBLIC_BLUEPRINT_DEV_MODE`: Frontend-visible local/dev flags. The `Keys` integrations UI, `Listening Jobs`, and `Backend Logs` are shown only in Next development mode or when a debug/dev-mode flag is truthy. Keep these unset or `false` in public production builds.
- `DATABASE_BACKEND`: Optional override: `supabase` or `sqlite`.
- `SQLITE_DATABASE_URL`: SQLite fallback URL (default: `sqlite:///./blueprint.db`).
- `BLUEPRINT_DEPLOYMENT`: When `true`, deployed builds without a live LLM show generated examples plus an alpha signup form instead of running generation.
- `LLM_PROVIDER`: Live generation provider: `baseten`, `gemini`, `huggingface`, `nvidia`, `openai`, `openai-compatible`, `runpod`, `runpod-serverless`, or `simulation`. Use `runpod` for Runpod OpenAI-compatible/vLLM endpoints and `runpod-serverless` for queue-style `/runsync` workers.
- `LLM_ALLOWED_PROVIDERS`: Optional comma-separated allowlist for per-request provider overrides.
- `OPENAI_ALLOWED_MODELS` / `BASETEN_ALLOWED_MODELS` / `HUGGINGFACE_ALLOWED_MODELS` / `NVIDIA_ALLOWED_MODELS` / `OPENAI_COMPATIBLE_ALLOWED_MODELS` / `GEMINI_ALLOWED_MODELS` / `RUNPOD_ALLOWED_MODELS`: Optional comma-separated allowlists for per-request model overrides. Without an explicit allowlist, runtime overrides are limited to the configured default/fallback model for that provider.
- `/api/generate` also accepts optional `provider` and `model` fields for runtime switching. Each generated project records the requested provider/model and actual provider/model in `assembly_metadata`.
- `OPENAI_API_KEY`: API key for first-party OpenAI when `LLM_PROVIDER=openai`.
- `OPENAI_MODEL`: OpenAI model ID. The example default is `gpt-4o-mini`.
- `OPENAI_RESPONSE_FORMAT`: OpenAI response format. Defaults to `json_schema`; `json_object` and `none` are also supported.
- `OPENAI_TIMEOUT_SECONDS`: First-party OpenAI read timeout. Defaults to `300`.
- `OPENAI_REASONING_EFFORT`: Optional reasoning effort for GPT-5/o-series models, for example `low`.
- `OPENAI_TEMPERATURE`: Optional first-party OpenAI sampling temperature. Omitted by default so models that only support their default temperature can run.
- `OPENAI_PROJECT_ID` / `OPENAI_ORG_ID`: Optional OpenAI project and organization routing headers.
- `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`: Optional Langfuse project keys. When both are set, the backend traces each generation request and structured LLM call.
- `LANGFUSE_BASE_URL`: Optional Langfuse host (default `https://cloud.langfuse.com`).
- `LANGFUSE_TRACING_ENVIRONMENT` / `LANGFUSE_TRACING_RELEASE`: Optional Langfuse trace attributes.
- `LANGFUSE_MAX_FIELD_CHARS`: Optional traced payload preview cap (default `20000`).
- `LANGFUSE_ENABLED`: Optional explicit on/off switch. Set to `false` to disable tracing even when keys are present.
- `IMAGE_OUTPUT_ENABLED`: Optional global default for generated product images. The UI and API can opt in per job with `generate_image=true`.
- `IMAGE_PROVIDER`: Image provider. Supports `openai`, `openai-compatible`, or `none`.
- `OPENAI_IMAGE_MODEL`: OpenAI image model ID. The example default is `gpt-image-2`.
- `OPENAI_IMAGE_SIZE`: Generated image size, for example `1024x1024`.
- `OPENAI_IMAGE_API_KEY` / `OPENAI_API_KEY`: First-party OpenAI image credentials. `IMAGE_PROVIDER=openai` does not inherit `LLM_API_KEY` or `LLM_BASE_URL`; use `IMAGE_PROVIDER=openai-compatible` plus `IMAGE_BASE_URL`/`IMAGE_API_KEY` or `LLM_BASE_URL`/`LLM_API_KEY` for compatible image endpoints.
- `FIREWORKS_API_KEY`: Enables Video tab self-correction. Auto mode samples the saved video with `ffmpeg`, reviews frames with the Fireworks `kimi-k2p6` image-input model, then applies the review through `ProjectIterator`.
- `FIREWORKS_VIDEO_REVIEW_INPUT_MODE`: `auto` by default. Auto uses the working `kimi-k2p6` frame-review fallback unless native video deployment routing is configured.
- `FIREWORKS_ACCOUNT_ID` / `FIREWORKS_VIDEO_REVIEW_DEPLOYMENT_ID`: Optional Fireworks dedicated deployment routing for native video/audio models. With these set and no explicit frame model override, auto mode uses `qwen3-omni-30b-a3b-instruct`.
- `FIREWORKS_VIDEO_REVIEW_MODEL`: Fireworks review model slug or full deployment path. Defaults to `kimi-k2p6` for frame review. For native video, use `qwen3-omni-30b-a3b-instruct`, `molmo2-4b`, `molmo2-8b`, or a full `accounts/<account>/models/<model>#accounts/<account>/deployments/<deployment>` path.
- `FIREWORKS_BASE_URL` / `FIREWORKS_VIDEO_REVIEW_MAX_FRAMES` / `FIREWORKS_VIDEO_REVIEW_MAX_SECONDS` / `FIREWORKS_VIDEO_REVIEW_NATIVE_FPS` / `FIREWORKS_VIDEO_REVIEW_NATIVE_HEIGHT` / `FIREWORKS_VIDEO_REVIEW_MAX_MEDIA_BYTES` / `FIREWORKS_TIMEOUT_SECONDS`: Optional Fireworks video-review endpoint, preprocessing, and timeout overrides.
- `SUPABASE_S3_ENDPOINT`: Supabase Storage S3 endpoint associated with image uploads. Defaults from `SUPABASE_URL`; this project uses `https://knmuwxhfrgkykyvblzwi.storage.supabase.co/storage/v1/s3`.
- `SUPABASE_S3_BUCKET`: Supabase Storage bucket for image uploads (default: `contents`).
- `SUPABASE_S3_ACCESS_KEY_ID` / `SUPABASE_S3_SECRET_ACCESS_KEY`: Optional S3-compatible fallback credentials. The normal backend path uploads through the Supabase client with `SUPABASE_URL` plus the service-role/secret key.
- `SUPABASE_IMAGE_SIGNED_URL_SECONDS`: Lifetime for refreshed Supabase Storage read URLs when projects are loaded (default: `86400`).
- `LLM_API_KEY`: Generic provider API key alias. For Gemini, `GEMINI_API_KEY` or `GOOGLE_API_KEY` still work.
- `LLM_MODEL`: Model to use, for example `gemini-3.5-flash` or an OpenAI/OpenAI-compatible model ID.
- `LLM_TIMEOUT_SECONDS`: Generic read timeout. OpenAI-compatible endpoints default to `90`.
- `LLM_REASONING_EFFORT`: Optional generic reasoning effort for compatible endpoints that support it.
- `LLM_TEMPERATURE`: Optional generic sampling temperature. OpenAI-compatible endpoints default to `0.2`; set `default`, `none`, or `omit` to omit it.
- `BASETEN_API_KEY` / `BASETEN_BASE_URL`: Baseten Model APIs configuration when `LLM_PROVIDER=baseten` or a request uses `provider=baseten`. `BASETEN_BASE_URL` defaults to `https://inference.baseten.co/v1`.
- `BASETEN_MODEL`: Baseten model slug, for example `deepseek-ai/DeepSeek-V4-Pro`.
- `HF_TOKEN` / `HUGGINGFACE_API_KEY` / `HUGGINGFACE_HUB_TOKEN`: Hugging Face Inference Providers token when `LLM_PROVIDER=huggingface` or a request uses `provider=huggingface`.
- `HUGGINGFACE_BASE_URL`: Hugging Face OpenAI-compatible router URL. Defaults to `https://router.huggingface.co/v1`.
- `HUGGINGFACE_MODEL`: Hugging Face model ID, for example `Qwen/Qwen2.5-Coder-3B-Instruct:nscale`.
- `HF_ARTIFACT_REPO_ID` / `HUGGINGFACE_ARTIFACT_REPO_ID` / `HF_DATASET_REPO_ID`: Optional Hugging Face dataset repo for uploaded benchmark, output, and eval artifacts.
- `HF_ARTIFACT_PATH_PREFIX`: Optional path prefix inside the artifact repo. Defaults to `blueprint`.
- `EXTERNAL_SOURCE_PROVIDER`: External web/source provider for `workflow=web_research`. Firecrawl is the only active provider for now; legacy `auto` or `tavily` values are normalized to `firecrawl`.
- `FIRECRAWL_API_KEY` / `FIRECRAWL_MCP_COMMAND`: Enable Firecrawl MCP search and page extraction for the web research workflow.
- `FIRECRAWL_SEARCH_LIMIT` / `FIRECRAWL_MCP_TIMEOUT_SECONDS`: Firecrawl search controls for the web research workflow.
- `NVIDIA_API_KEY` / `NVIDIA_BASE_URL`: NVIDIA Build/NIM configuration when `LLM_PROVIDER=nvidia` or a request uses `provider=nvidia`. `NVIDIA_BASE_URL` defaults to `https://integrate.api.nvidia.com/v1`.
- `NVIDIA_MODEL`: NVIDIA model slug, for example `meta/llama-3.1-8b-instruct`.
- `RUNPOD_API_KEY` / `RUNPOD_OPENAI_BASE_URL`: Runpod OpenAI-compatible/vLLM configuration when `LLM_PROVIDER=runpod` or a request uses `provider=runpod`.
- `RUNPOD_ENDPOINT_ID` / `RUNPOD_ENDPOINT_URL`: Runpod Serverless queue configuration when `LLM_PROVIDER=runpod-serverless` or a request uses `provider=runpod-serverless`.
- `RUNPOD_MODEL_ENDPOINTS`: Optional JSON mapping of Runpod model IDs to endpoint IDs or endpoint URLs when each model uses a different Serverless endpoint.
- A plain Runpod queue URL such as `https://api.runpod.ai/v2/<endpoint-id>` belongs in `RUNPOD_ENDPOINT_URL` with `LLM_PROVIDER=runpod-serverless`; `LLM_PROVIDER=runpod` requires the OpenAI-compatible base URL ending in `/openai/v1`.
- `RUNPOD_TIMEOUT_SECONDS`: Runpod HTTP read timeout. Defaults to `1200` so 10-15 minute cold starts or long generations can finish.
- `RUNPOD_POLL_TIMEOUT_SECONDS`: Runpod Serverless `/status` polling timeout. Defaults to `1200`.
- `RUNPOD_EXECUTION_TIMEOUT_MS` / `RUNPOD_TTL_MS`: Runpod Serverless job policy values. Use `1200000` for 20-minute generation windows.
- `RUNPOD_PARTI_SEED_TIMEOUT_SECONDS`: Optional timeout just for the `caid-technologies/parti-base` seed call. Defaults to `RUNPOD_TIMEOUT_SECONDS`; set lower if you prefer fast catalog repair when Parti is slow.
- `RUNPOD_INPUT_TEMPLATE`: Optional JSON payload template for Runpod workers. Use `{prompt}` and, for single-endpoint multi-model workers, `{model}` placeholders.
- `STRICT_LLM`: Set to `true` (default) to fail fast when model validation is enabled and the model is unavailable. Set to `false` to attempt fallback.
- `LLM_FALLBACK_MODEL`: Optional fallback model when `STRICT_LLM=false`.
- `LLM_BASE_URL`: Optional base URL for OpenAI-compatible providers.
- `JOB_METADATA_BACKEND`: Durable A2A job metadata backend. `auto` uses Supabase when the main app DB is Supabase, otherwise SQLite.
- `JOB_METADATA_DB_PATH`: SQLite file used when A2A job metadata is on SQLite (default: `./blueprint_jobs.db`).
- `A2A_SOCKET_ENABLED`: Set to `true` to start the optional TCP JSONL A2A socket.
- `A2A_SOCKET_HOST` / `A2A_SOCKET_PORT`: Host and port for the optional TCP JSONL listener.

If no live LLM provider is configured or generation fails, the backend returns deterministic simulation outputs based on built-in example projects.

### Frontend (Next.js)
```bash
cd frontend
npm install
npm run dev
```

Open:
- http://localhost:3000 (UI)
- http://localhost:8000/api/docs (API docs)

Tip: load an example directly with http://localhost:3000/?example=pocket_mp3_player (or any JSON under `frontend/public/examples/`).

## Documentation
- [Architecture](docs/architecture.md)
- [Agents](docs/agents.md)
- [Hardware IR](docs/hardware-ir.md)
- [Validation](docs/validation.md)
- [Database](docs/database.md)
- [A2A](docs/a2a.md)
- [Backend](docs/backend.md)
- [Frontend](docs/frontend.md)
- [Setup](docs/setup.md)
- [Development](docs/development.md)
- [Examples](docs/examples.md)
- [Roadmap](docs/roadmap.md)
- [Legal and policy drafts](docs/legal/README.md)
