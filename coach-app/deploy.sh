#!/usr/bin/env bash

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHARED_INFRA_DIR="${SHARED_INFRA_DIR:-$HOME/shared-infra}"
ROOT_ENV_FILE="$APP_DIR/.env"
BACKEND_ENV_FILE="$APP_DIR/backend/.env"
LLMS_CONFIG_FILE="$APP_DIR/backend/config/llms.local.json"

REBUILD_INDEX=0
SKIP_SHARED_INFRA=0
SKIP_HEALTHCHECK=0
SERVICES=()
VALID_SERVICES=(backend frontend)

log() {
  printf '[deploy] %s\n' "$*"
}

warn() {
  printf '[deploy] WARN: %s\n' "$*" >&2
}

fail() {
  printf '[deploy] ERROR: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage: ./deploy.sh [options]
Usage: ./deploy.sh [options] [service...]

Options:
  --reindex              Trigger /api/v1/index/rebuild after health check
  --skip-shared-infra    Do not start ~/shared-infra automatically
  --skip-healthcheck     Skip HTTP health check after docker compose up
  -h, --help             Show this help message

Environment overrides:
  SHARED_INFRA_DIR       Path to shared infra compose directory

Examples:
  ./deploy.sh
  ./deploy.sh backend frontend
  ./deploy.sh frontend --skip-healthcheck
EOF
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"
}

copy_if_missing() {
  local source_file="$1"
  local target_file="$2"
  local display_path="$target_file"
  if [[ -f "$target_file" ]]; then
    return
  fi
  cp "$source_file" "$target_file"
  if [[ "$target_file" == "$APP_DIR/"* ]]; then
    display_path="${target_file#"$APP_DIR"/}"
  fi
  log "created $display_path from example"
}

env_value() {
  local file="$1"
  local key="$2"
  awk -F '=' -v search_key="$key" '
    $0 ~ "^[[:space:]]*" search_key "=" {
      value = substr($0, index($0, "=") + 1)
      gsub(/\r$/, "", value)
      print value
    }
  ' "$file" | tail -n 1
}

wait_for_health() {
  local url="$1"
  local attempts=20
  local i
  for ((i = 1; i <= attempts; i += 1)); do
    if response="$(curl --silent --show-error --max-time 5 "$url" 2>/dev/null)"; then
      log "health check passed: $response"
      return 0
    fi
    sleep 2
  done
  return 1
}

is_valid_service() {
  local candidate="$1"
  local service
  for service in "${VALID_SERVICES[@]}"; do
    if [[ "$service" == "$candidate" ]]; then
      return 0
    fi
  done
  return 1
}

for arg in "$@"; do
  case "$arg" in
    --reindex)
      REBUILD_INDEX=1
      ;;
    --skip-shared-infra)
      SKIP_SHARED_INFRA=1
      ;;
    --skip-healthcheck)
      SKIP_HEALTHCHECK=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      if is_valid_service "$arg"; then
        SERVICES+=("$arg")
      else
        fail "unknown argument or unsupported service: $arg"
      fi
      ;;
  esac
done

require_command docker
require_command curl
require_command awk

copy_if_missing "$APP_DIR/.env.example" "$ROOT_ENV_FILE"
copy_if_missing "$APP_DIR/backend/.env.example" "$BACKEND_ENV_FILE"
copy_if_missing "$APP_DIR/backend/config/llms.local.example.json" "$LLMS_CONFIG_FILE"

openrouter_api_key="$(env_value "$BACKEND_ENV_FILE" "OPENROUTER_API_KEY")"
if [[ -z "${openrouter_api_key// }" ]]; then
  fail "OPENROUTER_API_KEY is empty in backend/.env; edit it and rerun"
fi

backend_port="$(env_value "$ROOT_ENV_FILE" "BACKEND_PORT")"
backend_port="${backend_port:-8000}"
health_url="http://127.0.0.1:${backend_port}/health"

if [[ "$SKIP_SHARED_INFRA" -eq 0 ]]; then
  if [[ -f "$SHARED_INFRA_DIR/docker-compose.yml" || -f "$SHARED_INFRA_DIR/compose.yml" ]]; then
    log "starting shared infra in $SHARED_INFRA_DIR"
    (
      cd "$SHARED_INFRA_DIR"
      docker compose up -d
    )
  else
    warn "shared infra directory not found at $SHARED_INFRA_DIR; expecting external network to already exist"
  fi
fi

if [[ "${#SERVICES[@]}" -eq 0 ]]; then
  SERVICES=("${VALID_SERVICES[@]}")
fi

log "deploying coach-app from $APP_DIR"
log "target services: ${SERVICES[*]}"
(
  cd "$APP_DIR"
  docker compose up -d --build "${SERVICES[@]}"
)

if [[ "$SKIP_HEALTHCHECK" -eq 0 ]]; then
  log "waiting for backend health: $health_url"
  wait_for_health "$health_url" || fail "backend health check failed: $health_url"
fi

if [[ "$REBUILD_INDEX" -eq 1 ]]; then
  log "triggering index rebuild"
  curl --silent --show-error -X POST "${health_url%/health}/api/v1/index/rebuild"
  printf '\n'
fi

log "deployment finished"
