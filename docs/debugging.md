# Debugging

Blueprint includes a local VS Code full-stack debug setup under `.vscode/`. That folder is ignored by git because debug config is machine-specific, but the workspace files are created for local development.

## VS Code Full Stack

Open the Run and Debug panel and choose:

```text
Full Stack: Backend + Frontend + Browser
```

This starts:

- FastAPI backend on `http://127.0.0.1:8000`
- Next.js frontend on `http://localhost:3000`
- Chrome attached to the frontend
- Python debugging for backend breakpoints
- Node/Chrome debugging for frontend breakpoints

Use this for most debugging. The backend runs without `--reload` so breakpoints are stable and there is only one Python process.

## Reload Variant

Use this only when you specifically want backend auto-reload:

```text
Full Stack: Backend reload + Frontend + Browser
```

Reload mode can spawn child processes, so breakpoint behavior can be noisier.

## Useful Single Targets

- `Backend: FastAPI (uvicorn)` starts only the Python API debugger.
- `Frontend: Next.js dev + browser` starts only the frontend and opens Chrome.
- `Browser: Frontend only` attaches a browser when the frontend is already running.
- `Attach: Backend debugpy on 5678` is for manually started debugpy sessions.

## Tasks

Open the Command Palette and run `Tasks: Run Task`:

- `Backend: tail log file` follows `blueprint-backend.log`.
- `Backend: debug config` prints `/debug/config`.
- `Ports: inspect Blueprint stack` shows local listeners for common Blueprint/model ports.
- `Backend: ensure deps` creates `.venv` if needed and installs backend dependencies.
- `Frontend: ensure deps` installs frontend dependencies if `node_modules` is missing.

## Logs

The backend reads these from `.env`:

```env
LOG_LEVEL=INFO
BACKEND_LOG_FILE=./blueprint-backend.log
```

For noisier debugging, set:

```env
LOG_LEVEL=DEBUG
```

The VS Code backend launch config overrides `LOG_LEVEL=DEBUG` and writes to `blueprint-backend.log` automatically.

## Before Starting A Compound

If ports are already in use, stop existing servers first:

```bash
ss -ltnp | rg ':3000|:8000'
```

The compound launch expects to own ports `3000` and `8000`.

## Local Model Debugging

If the backend falls back to simulation, check the backend terminal or `blueprint-backend.log`. The fallback logs include provider, model, schema, image attachment status, and a traceback.

Then check:

```bash
curl -s http://localhost:8000/debug/config | python -m json.tool
```

For Ollama, also check:

```bash
curl -s http://localhost:11434/v1/models | python -m json.tool
```
