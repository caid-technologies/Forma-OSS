# Blueprint OSS

Blueprint OSS is an open-source, AI-native hardware design generator. It turns a prompt (and optionally an image) into a structured, validated **Hardware IR** package plus wiring diagrams, BOM, and build steps.

This repository is an **MVP and research prototype** focused on **low-voltage maker electronics** (3.3V–5V) and safe, educational projects.

## What you can do
- Compile a hardware idea into typed **Hardware IR** (Pydantic)
- Run **rule-based electrical validation** (shorts, voltage mismatch, unpowered ICs, pin conflicts, overcurrent risk)
- Visualize wiring in:
  - Interactive **React Flow** schematic
  - Generated **SVG** schematic
  - Generated **Mermaid** topology diagram
- View a lightweight **3D mechanical layout** (Three.js / React Three Fiber)
- Persist generated projects to **Postgres** (default) with an automatic **SQLite fallback**

## How it works
Prompt (+ optional image) → sequential agents → Hardware IR → validation/repair → UI outputs.

```mermaid
flowchart LR
  A[Prompt + optional image] --> B[ADK-style sequential agents\n(Gemini structured JSON)]
  B --> C[Typed Hardware IR (Pydantic)]
  C --> D[Rule-based validation + repair loop]
  D --> E[UI: React Flow + SVG + Mermaid + 3D mech]
  C --> F[(Project database)]
```

## MVP scope & safety boundaries
Blueprint intentionally limits scope to low-voltage maker electronics:
- 3.3V–5V DC systems
- Breadboard-friendly microcontrollers, sensors, displays, and actuators
- Educational and hobbyist prototypes

It blocks or warns on high-risk domains (mains AC, medical, automotive control, weapons, high-power battery packs). See [docs/validation.md](docs/validation.md).

## Local setup (quick)
Detailed instructions live in [docs/setup.md](docs/setup.md). The short version:

### Backend (FastAPI)
From the repo root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

# optional: seed parts library (the server also auto-seeds if empty)
python3 backend/seed_db.py

uvicorn backend.main:app --reload --port 8000
```

Environment variables (recommended via a repo-root `.env`; see `.env.example`):
- `DATABASE_URL` (defaults to `postgresql://postgres:postgres@localhost:5432/blueprint`, falls back to `sqlite:///./blueprint.db` if Postgres isn’t reachable)
- `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) to enable live generation
- `GEMINI_MODEL` (default `gemini-3.5-flash`)
- `STRICT_GEMINI` (default `true`; fail fast if `GEMINI_MODEL` is unavailable)
- `GEMINI_FALLBACK_MODEL` (default `gemini-2.5-flash`; used when `STRICT_GEMINI=false`)

If no Gemini key is configured (or generation fails), the backend returns a deterministic **simulation** based on the built-in example projects.

### Frontend (Next.js)
```bash
cd frontend
npm install
npm run dev
```

Open:
- http://localhost:3000 (UI)
- http://localhost:8000/docs (API docs)

Tip: load an example directly with http://localhost:3000/?example=pocket_mp3_player (or any JSON under `frontend/public/examples/`).

## Documentation
- [Architecture](docs/architecture.md)
- [Agents](docs/agents.md)
- [Hardware IR](docs/hardware-ir.md)
- [Validation](docs/validation.md)
- [Database](docs/database.md)
- [Backend](docs/backend.md)
- [Frontend](docs/frontend.md)
- [Setup](docs/setup.md)
- [Development](docs/development.md)
- [Examples](docs/examples.md)
- [Roadmap](docs/roadmap.md)

## Screenshots (placeholder)
![Blueprint UI placeholder](docs/assets/ui-placeholder.svg)
