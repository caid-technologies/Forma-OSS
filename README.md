# Blueprint

Blueprint is AI-native full-stack hardware. It turns a prompt (and optionally an image) into a structured, validated **Hardware IR** package plus generated product imagery, wiring diagrams, BOM, and build steps.

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
- Persist generated projects to **Supabase** through the Supabase client when configured, with an automatic **SQLite fallback**
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
./scripts/blueprint-backend seed
```

The CLI uses `.venv/bin/python` when present and falls back to `python3`. `health`
checks the root, component, and A2A jobs endpoints; `jobs --local` reads the
SQLite job metadata store directly when the API server is not running.

To run with OpenAI:
```bash
LLM_PROVIDER=openai OPENAI_API_KEY=your_openai_api_key_here OPENAI_MODEL=gpt-4o-mini uvicorn backend.main:app --reload --port 8000
```

Environment variables (recommended via a repo-root `.env`; see `.env.example`):
- `SUPABASE_URL`: Supabase project API URL, for example `https://your-project-ref.supabase.co`.
- `SUPABASE_SERVICE_ROLE_KEY` / `SUPABASE_SECRET_KEY`: Backend-only Supabase key for writes. Do not use anon/publishable keys.
- `DATABASE_BACKEND`: Optional override: `supabase` or `sqlite`.
- `SQLITE_DATABASE_URL`: SQLite fallback URL (default: `sqlite:///./blueprint.db`).
- `LLM_PROVIDER`: Live generation provider: `gemini`, `openai`, `openai-compatible`, or `simulation`.
- `OPENAI_API_KEY`: API key for first-party OpenAI when `LLM_PROVIDER=openai`.
- `OPENAI_MODEL`: OpenAI model ID. The example default is `gpt-4o-mini`.
- `OPENAI_RESPONSE_FORMAT`: OpenAI response format. Defaults to `json_schema`; `json_object` and `none` are also supported.
- `OPENAI_TIMEOUT_SECONDS`: First-party OpenAI read timeout. Defaults to `300`.
- `OPENAI_REASONING_EFFORT`: Optional reasoning effort for GPT-5/o-series models, for example `low`.
- `OPENAI_TEMPERATURE`: Optional first-party OpenAI sampling temperature. Omitted by default so models that only support their default temperature can run.
- `OPENAI_PROJECT_ID` / `OPENAI_ORG_ID`: Optional OpenAI project and organization routing headers.
- `IMAGE_OUTPUT_ENABLED`: Optional global default for generated product images. The UI and API can opt in per job with `generate_image=true`.
- `IMAGE_PROVIDER`: Image provider. Supports `openai`, `openai-compatible`, or `none`.
- `OPENAI_IMAGE_MODEL`: OpenAI image model ID. The example default is `gpt-image-2`.
- `OPENAI_IMAGE_SIZE`: Generated image size, for example `1024x1024`.
- `SUPABASE_S3_ENDPOINT`: Supabase Storage S3 endpoint associated with image uploads. Defaults from `SUPABASE_URL`; this project uses `https://knmuwxhfrgkykyvblzwi.storage.supabase.co/storage/v1/s3`.
- `SUPABASE_S3_BUCKET`: Supabase Storage bucket for image uploads (default: `contents`).
- `SUPABASE_S3_ACCESS_KEY_ID` / `SUPABASE_S3_SECRET_ACCESS_KEY`: Optional S3-compatible fallback credentials. The normal backend path uploads through the Supabase client with `SUPABASE_URL` plus the service-role/secret key.
- `SUPABASE_IMAGE_SIGNED_URL_SECONDS`: Lifetime for refreshed Supabase Storage read URLs when projects are loaded (default: `86400`).
- `LLM_API_KEY`: Generic provider API key alias. For Gemini, `GEMINI_API_KEY` or `GOOGLE_API_KEY` still work.
- `LLM_MODEL`: Model to use, for example `gemini-3.5-flash` or an OpenAI/OpenAI-compatible model ID.
- `LLM_TIMEOUT_SECONDS`: Generic read timeout. OpenAI-compatible endpoints default to `90`.
- `LLM_REASONING_EFFORT`: Optional generic reasoning effort for compatible endpoints that support it.
- `LLM_TEMPERATURE`: Optional generic sampling temperature. OpenAI-compatible endpoints default to `0.2`; set `default`, `none`, or `omit` to omit it.
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
