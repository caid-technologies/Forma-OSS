# Local Setup

Blueprint OSS runs a FastAPI backend and a Next.js frontend. PostgreSQL is supported but optional; the backend will fall back to SQLite for local use.

## Prerequisites
- **Python 3.11+**
- **Node.js 18+**
- **PostgreSQL** (optional, recommended for persistent storage)

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
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/blueprint
LOG_LEVEL=INFO
# BACKEND_LOG_FILE=./blueprint-backend.log

# Live LLM generation
LLM_PROVIDER=openai
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o-mini
# OPENAI_MODELS=primary-model,backup-model
STRICT_LLM=true

# Optional first-party OpenAI settings
# OPENAI_RESPONSE_FORMAT=json_schema
# OPENAI_VALIDATE_MODELS=false
# OPENAI_TIMEOUT_SECONDS=300
# OPENAI_REASONING_EFFORT=low
# OPENAI_TEMPERATURE=1
# OPENAI_PROJECT_ID=your_openai_project_id_here
# OPENAI_ORG_ID=your_openai_org_id_here

# Optional generated product image output
IMAGE_OUTPUT_ENABLED=false
IMAGE_PROVIDER=openai
OPENAI_IMAGE_MODEL=gpt-image-2
OPENAI_IMAGE_SIZE=1024x1024
# OPENAI_IMAGE_QUALITY=medium
# OPENAI_IMAGE_OUTPUT_FORMAT=png

# Optional local image-to-text extraction for uploaded reference images
# IMAGE_TEXT_PROVIDER=ollama
# IMAGE_TEXT_BASE_URL=http://localhost:11434
# IMAGE_TEXT_MODEL=llava:latest
# IMAGE_TEXT_FORWARD_IMAGE=false
# IMAGE_TEXT_PROVIDER=local
# IMAGE_TEXT_BASE_URL=http://localhost:1234/v1
# IMAGE_TEXT_MODEL=your-local-vision-model
# IMAGE_TEXT_ALLOW_NO_API_KEY=true

# Optional local image generation
# IMAGE_PROVIDER=local
# IMAGE_BASE_URL=http://localhost:8000/v1
# IMAGE_MODEL=your-local-image-model
# IMAGE_ALLOW_NO_API_KEY=true
# IMAGE_PROVIDER=stable-diffusion-webui
# STABLE_DIFFUSION_BASE_URL=http://127.0.0.1:7860
# IMAGE_SIZE=1024x1024
# STABLE_DIFFUSION_STEPS=24

# Generic provider aliases
# LLM_API_KEY=your_provider_api_key_here
# LLM_MODEL=gpt-4o-mini
# LLM_MODELS=primary-model,backup-model
# LLM_FALLBACK_MODEL=your_fallback_model_here
# LLM_FALLBACK_MODELS=first_fallback,second_fallback

# Optional for OpenAI-compatible providers
# LLM_PROVIDER=openai-compatible
# LLM_BASE_URL=http://localhost:11434/v1
# LLM_ALLOW_NO_API_KEY=true
# LLM_TIMEOUT_SECONDS=90
# LLM_REASONING_EFFORT=low
# LLM_TEMPERATURE=0.2

# Optional TCP JSONL A2A socket
JOB_METADATA_DB_PATH=./blueprint_jobs.db
A2A_SOCKET_ENABLED=false
A2A_SOCKET_HOST=127.0.0.1
A2A_SOCKET_PORT=8766
```

Notes:
- If `DATABASE_URL` is missing or the connection fails, the backend falls back to `sqlite:///./blueprint.db`.
- Local text, vision, and image generation recipes live in [Local Models](local-models.md).
- `LOG_LEVEL` controls backend logs and defaults to `INFO`. Set `BACKEND_LOG_FILE=./blueprint-backend.log` to also write logs to a file.
- `LLM_PROVIDER` can be `gemini`, `openai`, `openai-compatible`, or `simulation`.
- `OPENAI_API_KEY` enables first-party OpenAI live structured generation when `LLM_PROVIDER=openai`.
- `OPENAI_MODELS` is an optional ordered comma-separated model list. When set, it supersedes `OPENAI_MODEL`; the backend tries each model before the job fails.
- `OPENAI_RESPONSE_FORMAT` defaults to `json_schema` for OpenAI. You can set it to `json_object` for older JSON mode or `none` to omit `response_format`.
- `OPENAI_TIMEOUT_SECONDS` controls the per-request OpenAI read timeout and defaults to `300`.
- `OPENAI_REASONING_EFFORT` can lower latency for GPT-5/o-series reasoning models, for example `low`.
- `OPENAI_TEMPERATURE` is optional and omitted by default for first-party OpenAI so models that only support their default temperature can run.
- `OPENAI_PROJECT_ID` and `OPENAI_ORG_ID` are optional routing headers for accounts that need explicit project or organization selection.
- `IMAGE_OUTPUT_ENABLED=true` makes generated product concept images the default. Leave it `false` and use the UI checkbox or `generate_image=true` API flag to opt in per job.
- `IMAGE_PROVIDER` can be `openai`, `openai-compatible`, `local`, `stable-diffusion-webui`, or `none`.
- `OPENAI_IMAGE_MODEL` selects the image model. The example default is `gpt-image-2`.
- `OPENAI_IMAGE_SIZE`, `OPENAI_IMAGE_QUALITY`, and `OPENAI_IMAGE_OUTPUT_FORMAT` tune generated image output.
- `IMAGE_TEXT_PROVIDER` enables uploaded-image text extraction before the hardware pipeline. Use `ollama` for local Ollama vision models or `openai-compatible`/`local` for local OpenAI-compatible vision endpoints.
- `IMAGE_TEXT_ALLOW_NO_API_KEY=true` lets local OpenAI-compatible vision endpoints run without auth.
- `IMAGE_TEXT_FORWARD_IMAGE=false` means the extracted image text is appended to the prompt and the raw image is not sent to the structured LLM. Set it to `true` when the structured LLM is also multimodal.
- `IMAGE_BASE_URL`, `IMAGE_MODEL`, and `IMAGE_ALLOW_NO_API_KEY=true` configure OpenAI-compatible local image generation.
- `STABLE_DIFFUSION_BASE_URL`, `STABLE_DIFFUSION_STEPS`, and `IMAGE_SIZE` configure Stable Diffusion WebUI / Automatic1111 local image generation.
- `LLM_API_KEY` is a generic provider key alias. Gemini aliases (`GEMINI_API_KEY` or `GOOGLE_API_KEY`) are still supported.
- `LLM_MODELS` is an optional ordered comma-separated model list for Gemini or OpenAI-compatible providers. When set, it supersedes `LLM_MODEL`.
- `LLM_TIMEOUT_SECONDS` controls the generic provider read timeout. OpenAI-compatible endpoints default to `90`.
- `LLM_REASONING_EFFORT` passes reasoning effort to compatible endpoints that support it.
- `LLM_TEMPERATURE` controls generic provider sampling. OpenAI-compatible endpoints default to `0.2`; set `default`, `none`, or `omit` to omit it.
- With `STRICT_LLM=true`, generation fails fast only when model availability validation is enabled and none of the primary configured models are available.
- With `STRICT_LLM=false`, the backend may fall back to `LLM_FALLBACK_MODEL` or `LLM_FALLBACK_MODELS`.
- OpenAI-compatible endpoints can use `LLM_BASE_URL`; local endpoints that do not require auth can set `LLM_ALLOW_NO_API_KEY=true`.
- A2A job metadata is persisted to SQLite at `JOB_METADATA_DB_PATH`.
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

API docs: http://localhost:8000/docs

## Frontend setup (Next.js)
```bash
cd frontend
npm install
npm run dev
```

UI: http://localhost:3000

## Optional: validate a netlist
You can submit a netlist to `POST /api/validate` to test validation rules without running the full pipeline.
