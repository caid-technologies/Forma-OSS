#!/usr/bin/env bash

# Shared lifecycle helpers for the local development launchers.
# The caller must define ROOT_DIR and may override DEV_RUNTIME_DIR.

DEV_RUNTIME_DIR="${DEV_RUNTIME_DIR:-$ROOT_DIR/.tmp/development}"
DEV_BACKEND_PID_FILE="${DEV_BACKEND_PID_FILE:-$DEV_RUNTIME_DIR/backend.pgid}"
DEV_FRONTEND_PID_FILE="${DEV_FRONTEND_PID_FILE:-$DEV_RUNTIME_DIR/frontend.pgid}"

dev_group_is_running() {
  local pgid="$1"
  ps -eo pgid=,stat= | awk -v target="$pgid" \
    '$1 == target && $2 !~ /^Z/ { found=1 } END { exit !found }'
}

dev_group_belongs_to_repo() {
  local pgid="$1"
  local pid cwd

  while read -r pid; do
    [ -n "$pid" ] || continue
    cwd="$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)"
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

  if [ -f "$pid_file" ]; then
    read -r recorded_pgid <"$pid_file" || true
    if [ "$recorded_pgid" = "$expected_pgid" ]; then
      rm -f -- "$pid_file"
    fi
  fi
}

dev_stop_process_group() {
  local pgid="$1"
  local label="$2"
  local pid_file="${3:-}"
  local attempt

  if ! [[ "$pgid" =~ ^[0-9]+$ ]] || [ "$pgid" -le 1 ]; then
    return 0
  fi
  if ! dev_group_is_running "$pgid"; then
    [ -n "$pid_file" ] && dev_remove_pid_file "$pid_file" "$pgid"
    return 0
  fi
  if ! dev_group_belongs_to_repo "$pgid"; then
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

  [ -f "$pid_file" ] || return 0
  read -r pgid <"$pid_file" || true
  dev_stop_process_group "$pgid" "$label" "$pid_file"
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
  if [ -n "$log_file" ]; then
    setsid "$@" >"$log_file" 2>&1 &
  else
    setsid "$@" &
  fi
  child_pid="$!"
  printf '%s\n' "$child_pid" >"$pid_file"
  printf -v "$output_variable" '%s' "$child_pid"
}
