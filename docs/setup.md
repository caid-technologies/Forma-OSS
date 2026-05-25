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
GEMINI_API_KEY=your_gemini_api_key_here

# Optional model controls
GEMINI_MODEL=gemini-3.5-flash
STRICT_GEMINI=true
GEMINI_FALLBACK_MODEL=gemini-2.5-flash
```

Notes:
- If `DATABASE_URL` is missing or the connection fails, the backend falls back to `sqlite:///./blueprint.db`.
- `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) enables live structured generation. Without it, the backend uses deterministic simulated example outputs.
- With `STRICT_GEMINI=true`, generation fails fast if `GEMINI_MODEL` isn’t available to your API key/provider.
- With `STRICT_GEMINI=false`, the backend may fall back to `GEMINI_FALLBACK_MODEL`.

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
