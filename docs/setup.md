# Local Setup

Blueprint OSS runs a FastAPI backend and a Next.js frontend. Supabase is supported for deployment through the Supabase client; the backend falls back to SQLite for local use.

## Prerequisites
- **Python 3.11+**
- **Node.js 18+**
- **Supabase project** (optional, recommended for deployed persistent storage)
- **Docker** (optional, for containerized frontend/backend images)

## Docker setup
From the repo root:

```bash
docker compose up --build
```

This builds `blueprint-backend:local` and `blueprint-frontend:local`, starts the API on port `8000`, starts the UI on port `3000`, and keeps SQLite data in the `blueprint-data` Docker volume.

The Compose backend defaults to:

```env
BLUEPRINT_DEV_MODE=false
SQLITE_DATABASE_URL=sqlite:////data/blueprint.db
JOB_METADATA_BACKEND=auto
JOB_METADATA_DB_PATH=/data/blueprint_jobs.db
LLM_PROVIDER=simulation
```

Set the same database and live-provider variables listed below in your shell or repo-root `.env` before running Compose if you want Supabase or model-backed generation.

If you publish the backend on a different host or port, rebuild the frontend with a matching browser-visible API URL:

```bash
BACKEND_PORT=8010 NEXT_PUBLIC_API_URL=http://localhost:8010 docker compose up --build
```

## Backend setup (FastAPI)
From the repo root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

### Environment variables
Recommended: create a repo-root `.env` (see `.env.example`).

```env
# Supabase persistence through the Supabase Python client.
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key_here
# Or, for newer Supabase projects:
# SUPABASE_SECRET_KEY=your_secret_key_here

# Local fallback / explicit SQLite
# BLUEPRINT_DEV_MODE=true
# DATABASE_BACKEND=sqlite
SQLITE_DATABASE_URL=sqlite:///./blueprint.db

# Deployment-only alpha gate
# BLUEPRINT_DEPLOYMENT=true

# Live LLM generation
LLM_PROVIDER=openai
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o-mini
STRICT_LLM=true

# Optional first-party OpenAI settings
# OPENAI_RESPONSE_FORMAT=json_schema
# OPENAI_VALIDATE_MODELS=false
# OPENAI_TIMEOUT_SECONDS=300
# OPENAI_REASONING_EFFORT=low
# OPENAI_TEMPERATURE=1
# OPENAI_PROJECT_ID=your_openai_project_id_here
# OPENAI_ORG_ID=your_openai_org_id_here

# Optional Langfuse observability
# LANGFUSE_PUBLIC_KEY=pk-lf-your_public_key_here
# LANGFUSE_SECRET_KEY=sk-lf-your_secret_key_here
# LANGFUSE_BASE_URL=https://cloud.langfuse.com
# LANGFUSE_TRACING_ENVIRONMENT=local
# LANGFUSE_TRACING_RELEASE=dev
# LANGFUSE_MAX_FIELD_CHARS=20000
# LANGFUSE_ENABLED=false

# Optional generated product image output
IMAGE_OUTPUT_ENABLED=false
IMAGE_PROVIDER=openai
OPENAI_IMAGE_MODEL=gpt-image-2
OPENAI_IMAGE_SIZE=1024x1024
# OPENAI_IMAGE_QUALITY=medium
# OPENAI_IMAGE_OUTPUT_FORMAT=png

# Optional Supabase Storage upload for reference/product images.
# Uses the Supabase client with SUPABASE_URL plus the service-role/secret key.
SUPABASE_S3_ENDPOINT=https://knmuwxhfrgkykyvblzwi.storage.supabase.co/storage/v1/s3
SUPABASE_S3_BUCKET=contents
# SUPABASE_S3_REGION=us-east-1
# Optional fallback for S3-compatible uploads when Supabase client env is absent.
# SUPABASE_S3_ACCESS_KEY_ID=your_supabase_s3_access_key_id
# SUPABASE_S3_SECRET_ACCESS_KEY=your_supabase_s3_secret_access_key
# SUPABASE_IMAGE_SIGNED_URL_SECONDS=86400
# SUPABASE_STORAGE_PUBLIC_BASE_URL=https://knmuwxhfrgkykyvblzwi.supabase.co

# Generic provider aliases
# LLM_API_KEY=your_provider_api_key_here
# LLM_MODEL=gpt-4o-mini
# LLM_FALLBACK_MODEL=your_fallback_model_here

# Optional for OpenAI-compatible providers
# LLM_PROVIDER=openai-compatible
# LLM_BASE_URL=http://localhost:11434/v1
# LLM_ALLOW_NO_API_KEY=true
# LLM_TIMEOUT_SECONDS=90
# LLM_REASONING_EFFORT=low
# LLM_TEMPERATURE=0.2

# Optional TCP JSONL A2A socket
JOB_METADATA_BACKEND=auto
JOB_METADATA_DB_PATH=./blueprint_jobs.db
A2A_SOCKET_ENABLED=false
A2A_SOCKET_HOST=127.0.0.1
A2A_SOCKET_PORT=8766
```

Notes:
- Supabase mode uses `SUPABASE_URL` plus `SUPABASE_SERVICE_ROLE_KEY` or `SUPABASE_SECRET_KEY`; it does not use a Postgres connection string.
- Do not use anon, publishable, or `NEXT_PUBLIC_` Supabase keys for the backend. They obey RLS and cannot seed these tables by default.
- `BLUEPRINT_DEV_MODE=true` forces SQLite for app data and A2A job metadata even if Supabase env vars are present. It also disables Supabase Storage writes, so reference and product image data is stored inline in the SQLite project record.
- If Supabase client variables are missing, the backend falls back to `SQLITE_DATABASE_URL` or `sqlite:///./blueprint.db`.
- `DATABASE_BACKEND` can be `supabase` or `sqlite`.
- `BLUEPRINT_DEPLOYMENT=true` enables the deployment-only alpha gate. When live LLM generation is unavailable, the frontend offers generated example projects plus a contact form that stores leads in `alpha_signups`.
- `LLM_PROVIDER` can be `gemini`, `openai`, `openai-compatible`, or `simulation`.
- `OPENAI_API_KEY` enables first-party OpenAI live structured generation when `LLM_PROVIDER=openai`.
- `OPENAI_RESPONSE_FORMAT` defaults to `json_schema` for OpenAI. You can set it to `json_object` for older JSON mode or `none` to omit `response_format`.
- `OPENAI_TIMEOUT_SECONDS` controls the per-request OpenAI read timeout and defaults to `300`.
- `OPENAI_REASONING_EFFORT` can lower latency for GPT-5/o-series reasoning models, for example `low`.
- `OPENAI_TEMPERATURE` is optional and omitted by default for first-party OpenAI so models that only support their default temperature can run.
- `OPENAI_PROJECT_ID` and `OPENAI_ORG_ID` are optional routing headers for accounts that need explicit project or organization selection.
- Set `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` to enable Langfuse tracing for full generation requests and every structured LLM step. `GET /api/debug/config` reports whether tracing is active without exposing secrets. Set `LANGFUSE_ENABLED=false` to disable tracing even when keys are present.
- `IMAGE_OUTPUT_ENABLED=true` makes generated product concept images the default. Leave it `false` and use the UI checkbox or `generate_image=true` API flag to opt in per job.
- `IMAGE_PROVIDER` can be `openai`, `openai-compatible`, or `none`.
- `OPENAI_IMAGE_MODEL` selects the image model. The example default is `gpt-image-2`.
- `OPENAI_IMAGE_SIZE`, `OPENAI_IMAGE_QUALITY`, and `OPENAI_IMAGE_OUTPUT_FORMAT` tune generated image output.
- When `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`/`SUPABASE_SECRET_KEY` are set, uploaded reference images and generated product images are stored in the Supabase Storage bucket from `SUPABASE_S3_BUCKET` (default `contents`) through the Supabase client. S3-compatible credentials are only a fallback. `BLUEPRINT_DEV_MODE=true` disables this storage path.
- `SUPABASE_IMAGE_SIGNED_URL_SECONDS` controls how long refreshed Supabase Storage read URLs live when projects are loaded. It defaults to `86400`.
- `LLM_API_KEY` is a generic provider key alias. Gemini aliases (`GEMINI_API_KEY` or `GOOGLE_API_KEY`) are still supported.
- `LLM_TIMEOUT_SECONDS` controls the generic provider read timeout. OpenAI-compatible endpoints default to `90`.
- `LLM_REASONING_EFFORT` passes reasoning effort to compatible endpoints that support it.
- `LLM_TEMPERATURE` controls generic provider sampling. OpenAI-compatible endpoints default to `0.2`; set `default`, `none`, or `omit` to omit it.
- With `STRICT_LLM=true`, generation fails fast when model availability validation is enabled and `LLM_MODEL` is unavailable.
- With `STRICT_LLM=false`, the backend may fall back to `LLM_FALLBACK_MODEL`.
- OpenAI-compatible endpoints can use `LLM_BASE_URL`; local endpoints that do not require auth can set `LLM_ALLOW_NO_API_KEY=true`.
- `JOB_METADATA_BACKEND=auto` stores A2A job metadata in Supabase when the main app database is Supabase, otherwise in SQLite. `BLUEPRINT_DEV_MODE=true` always uses SQLite.
- `JOB_METADATA_DB_PATH` controls the SQLite A2A job metadata file.
- A2A REST, WebSocket, and MCP routes are always mounted. The TCP JSONL socket starts only when `A2A_SOCKET_ENABLED=true`.

### Seed the component database
The server auto-seeds templates on startup if the `component_templates` table is empty.

Optional manual seed:
```bash
python3 backend/seed_db.py
```

### Run the backend
Run from the repo root so `backend.*` imports resolve correctly:

```bash
uvicorn backend.main:app --reload --port 8000
```

OpenAI one-liner:
```bash
LLM_PROVIDER=openai OPENAI_API_KEY=your_openai_api_key_here OPENAI_MODEL=gpt-4o-mini uvicorn backend.main:app --reload --port 8000
```

API docs: http://localhost:8000/api/docs

## Frontend setup (Next.js)
```bash
cd frontend
npm install
npm run dev
```

UI: http://localhost:3000

## Optional: validate a netlist
You can submit a netlist to `POST /api/validate` to test validation rules without running the full pipeline.
