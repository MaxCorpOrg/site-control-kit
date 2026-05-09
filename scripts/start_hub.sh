#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

eval "$("$PYTHON_BIN" -m webcontrol runtime-env --format shell)"

TOKEN="${SITECTL_TOKEN:-}"
HOST="${SITECTL_HOST:-127.0.0.1}"
PORT="${SITECTL_PORT:-8765}"
STATE_FILE="${SITECTL_STATE_FILE:-$ROOT_DIR/var/site-control-kit/state/state.json}"

if [[ -z "$TOKEN" ]]; then
  echo "ERROR: SITECTL_TOKEN is not configured. Create .env from .env.example or use the generated local runtime config." >&2
  exit 1
fi

cd "$ROOT_DIR"
exec "$PYTHON_BIN" -m webcontrol serve --host "$HOST" --port "$PORT" --token "$TOKEN" --state-file "$STATE_FILE"
