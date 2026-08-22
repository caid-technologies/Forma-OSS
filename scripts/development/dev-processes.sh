#!/usr/bin/env bash

# Shared lifecycle helpers for the local development launchers.
# The caller must define ROOT_DIR and may override DEV_RUNTIME_DIR.

DEV_RUNTIME_DIR="${DEV_RUNTIME_DIR:-$ROOT_DIR/tmp/development}"
DEV_BACKEND_PID_FILE="${DEV_BACKEND_PID_FILE:-$DEV_RUNTIME_DIR/backend.pgid}"
DEV_FRONTEND_PID_FILE="${DEV_FRONTEND_PID_FILE:-$DEV_RUNTIME_DIR/frontend.pgid}"
DEV_PROCESS_PYTHON="${DEV_PROCESS_PYTHON:-${PYTHON_BIN:-python3}}"

dev_is_port_open() {
  local host="$1"
  local port="$2"

  "$DEV_PROCESS_PYTHON" - "$host" "$port" <<'PY'
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.settimeout(0.25)
    raise SystemExit(0 if sock.connect_ex((host, port)) == 0 else 1)
PY
}

dev_group_is_running() {
  local pgid="$1"
  if ps -p "$pgid" -o stat= 2>/dev/null | awk '$1 !~ /^Z/ { found=1 } END { exit !found }'; then
    return 0
  fi
  ps -eo pgid=,stat= | awk -v target="$pgid" \
    '$1 == target && $2 !~ /^Z/ { found=1 } END { exit !found }'
}

dev_group_belongs_to_repo() {
  local pgid="$1"
  local recorded_root="${2:-}"
  local pid cwd

  if [ -n "$recorded_root" ] && [ "$recorded_root" = "$ROOT_DIR" ]; then
    return 0
  fi

  while read -r pid; do
    [ -n "$pid" ] || continue
    cwd="$(
      "$DEV_PROCESS_PYTHON" - "$pid" 2>/dev/null <<'PY' || true
import os
import subprocess
import sys

pid = sys.argv[1]
proc_cwd = f"/proc/{pid}/cwd"
if os.path.exists(proc_cwd):
    print(os.path.realpath(proc_cwd))
    raise SystemExit(0)

try:
    output = subprocess.check_output(
        ["lsof", "-a", "-p", pid, "-d", "cwd", "-Fn"],
        stderr=subprocess.DEVNULL,
        text=True,
    )
except Exception:
    raise SystemExit(0)

for line in output.splitlines():
    if line.startswith("n"):
        print(os.path.realpath(line[1:]))
        break
PY
    )"
    case "$cwd" in
      "$ROOT_DIR"|"$ROOT_DIR"/*) return 0 ;;
    esac
  done < <(ps -eo pid=,pgid= | awk -v target="$pgid" '$2 == target { print $1 }')

  return 1
}

dev_remove_pid_file() {
  local pid_file="$1"
  local expected_pgid="$2"
  local recorded_pgid=""
  local recorded_root=""

  if [ -f "$pid_file" ]; then
    read -r recorded_pgid recorded_root <"$pid_file" || true
    if [ "$recorded_pgid" = "$expected_pgid" ]; then
      rm -f -- "$pid_file"
    fi
  fi
}

dev_stop_process_group() {
  local pgid="$1"
  local label="$2"
  local pid_file="${3:-}"
  local recorded_root="${4:-}"
  local attempt

  if ! [[ "$pgid" =~ ^[0-9]+$ ]] || [ "$pgid" -le 1 ]; then
    return 0
  fi
  if ! dev_group_is_running "$pgid"; then
    [ -n "$pid_file" ] && dev_remove_pid_file "$pid_file" "$pgid"
    return 0
  fi
  if ! dev_group_belongs_to_repo "$pgid" "$recorded_root"; then
    printf '[forma-dev] Refusing to stop %s process group %s; it is not owned by %s.\n' \
      "$label" "$pgid" "$ROOT_DIR" >&2
    [ -n "$pid_file" ] && dev_remove_pid_file "$pid_file" "$pgid"
    return 1
  fi

  printf '[forma-dev] Stopping prior %s process group %s...\n' "$label" "$pgid"
  kill -TERM -- "-$pgid" >/dev/null 2>&1 || true
  for attempt in $(seq 1 20); do
    if ! dev_group_is_running "$pgid"; then
      break
    fi
    sleep 0.1
  done
  if dev_group_is_running "$pgid"; then
    printf '[forma-dev] Force-stopping %s process group %s...\n' "$label" "$pgid"
    kill -KILL -- "-$pgid" >/dev/null 2>&1 || true
  fi
  [ -n "$pid_file" ] && dev_remove_pid_file "$pid_file" "$pgid"
}

dev_stop_recorded_process() {
  local pid_file="$1"
  local label="$2"
  local pgid=""
  local recorded_root=""

  [ -f "$pid_file" ] || return 0
  read -r pgid recorded_root <"$pid_file" || true
  dev_stop_process_group "$pgid" "$label" "$pid_file" "$recorded_root"
}

dev_cleanup_previous_session() {
  mkdir -p "$DEV_RUNTIME_DIR"
  dev_stop_recorded_process "$DEV_FRONTEND_PID_FILE" "frontend"
  dev_stop_recorded_process "$DEV_BACKEND_PID_FILE" "backend"
}

dev_start_process_group() {
  local output_variable="$1"
  local pid_file="$2"
  local log_file="$3"
  shift 3
  local child_pid

  mkdir -p "$DEV_RUNTIME_DIR"
  "$DEV_PROCESS_PYTHON" - "$log_file" "$@" <<'PY' &
import os
import subprocess
import sys

log_file = sys.argv[1]
command = sys.argv[2:]

os.setsid()
stdout = stderr = None
log_handle = None
if log_file:
    log_handle = open(log_file, "ab", buffering=0)
    stdout = stderr = log_handle

try:
    process = subprocess.Popen(command, stdout=stdout, stderr=stderr)
    raise SystemExit(process.wait())
finally:
    if log_handle is not None:
        log_handle.close()
PY
  child_pid="$!"
  printf '%s %s\n' "$child_pid" "$ROOT_DIR" >"$pid_file"
  printf -v "$output_variable" '%s' "$child_pid"
}

dev_ensure_local_simulation_env() {
  if [ -f "$ROOT_DIR/.env" ] || [ -n "${FORMA_USER_SECRETS_KEY:-}" ]; then
    dev_ensure_sqlite_parent
    return
  fi

  local secret_file="$DEV_RUNTIME_DIR/forma-user-secrets.key"
  mkdir -p "$DEV_RUNTIME_DIR"
  if [ ! -s "$secret_file" ]; then
    "$DEV_PROCESS_PYTHON" - "$secret_file" <<'PY'
import base64
import os
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
path.write_text(base64.b64encode(os.urandom(48)).decode("ascii"), encoding="utf-8")
path.chmod(0o600)
PY
  fi

  export FORMA_AUTH_MODE="${FORMA_AUTH_MODE:-local}"
  export FORMA_USER_SECRETS_KEY
  FORMA_USER_SECRETS_KEY="$(tr -d '\n\r' <"$secret_file")"
  export FORMA_DEV_MODE="${FORMA_DEV_MODE:-true}"
  export DATABASE_BACKEND="${DATABASE_BACKEND:-sqlite}"
  export SQLITE_DATABASE_URL="${SQLITE_DATABASE_URL:-sqlite:///$DEV_RUNTIME_DIR/forma-dev.db}"
  export LLM_PROVIDER="${LLM_PROVIDER:-simulation}"
  export IMAGE_OUTPUT_ENABLED="${IMAGE_OUTPUT_ENABLED:-false}"
  export IMAGE_PROVIDER="${IMAGE_PROVIDER:-none}"
  export NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:-http://$BACKEND_HOST:$BACKEND_PORT}"
  export NEXT_PUBLIC_FORMA_DEV_MODE="${NEXT_PUBLIC_FORMA_DEV_MODE:-true}"
  dev_ensure_sqlite_parent
}

dev_ensure_sqlite_parent() {
  "$DEV_PROCESS_PYTHON" - "${SQLITE_DATABASE_URL:-}" <<'PY'
import pathlib
import sys
from urllib.parse import unquote, urlparse

url = sys.argv[1].strip()
if not url.startswith("sqlite:///") or url in {"sqlite://", "sqlite:///:memory:", "sqlite://"}:
    raise SystemExit(0)

parsed = urlparse(url)
path = unquote(parsed.path)
if not path:
    raise SystemExit(0)
pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
PY
}
