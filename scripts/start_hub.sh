#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOKEN="${SITECTL_TOKEN:-}"
HOST="${SITECTL_HOST:-127.0.0.1}"
PORT="${SITECTL_PORT:-8765}"
STATE_FILE="${SITECTL_STATE_FILE:-$HOME/.site-control-kit/state.json}"
QUICK_TOKEN="local-bridge-quickstart-2026"

if [[ -z "$TOKEN" ]]; then
  TOKEN="$QUICK_TOKEN"
  echo "SITECTL_TOKEN не задан. Запуск в быстром локальном режиме." >&2
  echo "Используется токен по умолчанию: $QUICK_TOKEN" >&2
  echo "Для безопасного режима задайте свой токен:" >&2
  echo "export SITECTL_TOKEN='your-strong-token'" >&2
fi

cd "$ROOT_DIR"
exec python3 -m webcontrol serve --host "$HOST" --port "$PORT" --token "$TOKEN" --state-file "$STATE_FILE"
