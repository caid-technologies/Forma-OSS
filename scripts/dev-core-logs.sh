#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"
BACKEND_LOG_FILE="${BACKEND_LOG_FILE:-$ROOT_DIR/.logs/blueprint-core-dev.log}"
BACKEND_LOG_NAMESPACES="${BACKEND_LOG_NAMESPACES:-blueprint_core,backend.main,backend.user_integrations_api,backend.logging_config}"
FRONTEND_LOG_FILE="${FRONTEND_LOG_FILE:-$ROOT_DIR/.logs/frontend-dev.log}"
UVICORN_LOG_LEVEL="${UVICORN_LOG_LEVEL:-warning}"
UVICORN_ACCESS_LOG="${UVICORN_ACCESS_LOG:-false}"

backend_pid=""
frontend_pid=""
cleaned_up="false"

log() {
  printf '[blueprint-core-dev] %s\n' "$*"
}

is_truthy() {
  [[ "${1:-}" =~ ^(1|true|yes|on)$ ]]
}

is_port_open() {
  local port="$1"
  ss -ltn 2>/dev/null | awk '{print $4}' | grep -Eq "[:.]${port}$"
}

wait_for_url() {
  local url="$1"
  local label="$2"
  local attempts="${3:-60}"
  local process_pid="${4:-}"
  local failure_log="${5:-}"

  for _ in $(seq 1 "$attempts"); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      log "$label is ready at $url"
      return 0
    fi
    if [ -n "$process_pid" ] && ! kill -0 "$process_pid" >/dev/null 2>&1; then
      log "$label process exited before becoming ready at $url"
      return 1
    fi
    sleep 1
  done

  log "$label did not become ready at $url"
  if [ -n "$failure_log" ] && [ -s "$failure_log" ]; then
    log "Recent $label log output:"
    tail -n 80 "$failure_log"
  fi
  return 1
}

first_free_port() {
  local start_port="$1"
  local port="$start_port"

  while is_port_open "$port"; do
    port=$((port + 1))
    if [ "$port" -gt $((start_port + 20)) ]; then
      log "No free frontend port found from $start_port to $((start_port + 20))."
      exit 1
    fi
  done

  printf '%s' "$port"
}

cleanup() {
  if [ "$cleaned_up" = "true" ]; then
    return
  fi
  cleaned_up="true"

  log "Stopping services..."
  if [ -n "$frontend_pid" ] && kill -0 "$frontend_pid" >/dev/null 2>&1; then
    kill "$frontend_pid" >/dev/null 2>&1 || true
  fi
  if [ -n "$backend_pid" ] && kill -0 "$backend_pid" >/dev/null 2>&1; then
    kill "$backend_pid" >/dev/null 2>&1 || true
  fi
  if [ -n "$frontend_pid" ] || [ -n "$backend_pid" ]; then
    wait ${frontend_pid:+"$frontend_pid"} ${backend_pid:+"$backend_pid"} >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT INT TERM

cd "$ROOT_DIR"

if [ ! -x "$VENV_DIR/bin/python" ]; then
  log "Creating Python virtualenv at $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

if ! "$VENV_DIR/bin/python" -m uvicorn --version >/dev/null 2>&1; then
  log "Installing backend dependencies"
  "$VENV_DIR/bin/pip" install -r "$ROOT_DIR/backend/requirements.txt"
fi

if [ ! -d "$ROOT_DIR/frontend/node_modules" ]; then
  log "Installing frontend dependencies"
  (cd "$ROOT_DIR/frontend" && npm install)
fi

if is_port_open "$BACKEND_PORT"; then
  if curl -fsS "http://$BACKEND_HOST:$BACKEND_PORT/api" >/dev/null 2>&1; then
    log "Backend already appears to be running at http://$BACKEND_HOST:$BACKEND_PORT"
    log "Core-only logs require the backend to be started by this script."
  else
    log "Port $BACKEND_PORT is already in use, but Forma did not respond there."
    exit 1
  fi
else
  mkdir -p "$(dirname "$BACKEND_LOG_FILE")"
  export BACKEND_LOG_FILE BACKEND_LOG_NAMESPACES
  log "Starting backend at http://$BACKEND_HOST:$BACKEND_PORT"
  log "Backend log file: $BACKEND_LOG_FILE"
  log "Backend log namespaces: $BACKEND_LOG_NAMESPACES"
  uvicorn_args=(
    backend.main:app
    --host "$BACKEND_HOST"
    --port "$BACKEND_PORT"
    --log-level "$UVICORN_LOG_LEVEL"
  )
  if ! is_truthy "$UVICORN_ACCESS_LOG"; then
    uvicorn_args+=(--no-access-log)
  fi
  "$VENV_DIR/bin/python" -m uvicorn "${uvicorn_args[@]}" &
  backend_pid="$!"
  wait_for_url "http://$BACKEND_HOST:$BACKEND_PORT/api" "Backend" 60 "$backend_pid" "$BACKEND_LOG_FILE"
fi

FRONTEND_PORT="$(first_free_port "$FRONTEND_PORT")"
mkdir -p "$(dirname "$FRONTEND_LOG_FILE")"
log "Starting frontend at http://$FRONTEND_HOST:$FRONTEND_PORT"
log "Frontend log file: $FRONTEND_LOG_FILE"
(cd "$ROOT_DIR/frontend" && npm run dev -- --hostname "$FRONTEND_HOST" --port "$FRONTEND_PORT" >"$FRONTEND_LOG_FILE" 2>&1) &
frontend_pid="$!"

wait_for_url "http://$FRONTEND_HOST:$FRONTEND_PORT/" "Frontend"

cat <<EOF

Forma is running:
  Backend:       http://$BACKEND_HOST:$BACKEND_PORT
  Frontend:      http://$FRONTEND_HOST:$FRONTEND_PORT
  Core logs:     $BACKEND_LOG_FILE
  Frontend logs: $FRONTEND_LOG_FILE

Press Ctrl+C to stop both services.
EOF

wait
