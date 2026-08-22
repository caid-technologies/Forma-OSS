#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8010}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-3010}"
FRONTEND_URL="http://$FRONTEND_HOST:$FRONTEND_PORT"
BACKEND_URL="http://$BACKEND_HOST:$BACKEND_PORT/api"
DEV_PID=""

cleanup() {
  local status=$?
  if [ -n "$DEV_PID" ]; then
    kill -TERM "$DEV_PID" >/dev/null 2>&1 || true
    wait "$DEV_PID" >/dev/null 2>&1 || true
  fi
  exit "$status"
}

wait_for_url() {
  local url="$1"
  local label="$2"
  local attempt

  for attempt in $(seq 1 120); do
    if curl -fsS --max-time 2 "$url" >/dev/null 2>&1; then
      printf '[forma-e2e] %s ready at %s\n' "$label" "$url"
      return 0
    fi
    if [ -n "$DEV_PID" ] && ! kill -0 "$DEV_PID" >/dev/null 2>&1; then
      wait "$DEV_PID" || true
      printf '[forma-e2e] dev stack exited before %s became ready.\n' "$label" >&2
      return 1
    fi
    sleep 1
  done

  printf '[forma-e2e] %s did not become ready at %s\n' "$label" "$url" >&2
  return 1
}

trap cleanup EXIT INT TERM HUP

cd "$ROOT_DIR"

FORMA_AUTH_MODE="${FORMA_AUTH_MODE:-local}" \
FORMA_USER_SECRETS_KEY="${FORMA_USER_SECRETS_KEY:-playwright-local-secret-not-for-production}" \
FORMA_DEV_MODE="${FORMA_DEV_MODE:-true}" \
DATABASE_BACKEND="${DATABASE_BACKEND:-sqlite}" \
SQLITE_DATABASE_URL="${SQLITE_DATABASE_URL:-sqlite:///$ROOT_DIR/tmp/playwright/forma-e2e.db}" \
LLM_PROVIDER="${LLM_PROVIDER:-simulation}" \
IMAGE_OUTPUT_ENABLED="${IMAGE_OUTPUT_ENABLED:-false}" \
IMAGE_PROVIDER="${IMAGE_PROVIDER:-none}" \
NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:-http://$BACKEND_HOST:$BACKEND_PORT}" \
BACKEND_HOST="$BACKEND_HOST" \
BACKEND_PORT="$BACKEND_PORT" \
FRONTEND_HOST="$FRONTEND_HOST" \
FRONTEND_PORT="$FRONTEND_PORT" \
./scripts/development/dev.sh &
DEV_PID="$!"

wait_for_url "$BACKEND_URL" "Backend"
wait_for_url "$FRONTEND_URL" "Frontend"

cd "$ROOT_DIR/apps/web"
PLAYWRIGHT_REUSE_EXISTING=1 \
PLAYWRIGHT_BASE_URL="$FRONTEND_URL" \
PLAYWRIGHT_BACKEND_URL="$BACKEND_URL" \
npx playwright test "$@"
