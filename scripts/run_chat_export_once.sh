#!/usr/bin/env bash
set -euo pipefail

TOKEN="${1:-${SITECTL_TOKEN:-}}"
if [[ -z "$TOKEN" ]]; then
  echo "ERROR: pass token as first arg or set SITECTL_TOKEN" >&2
  exit 1
fi

OUTPUT="${2:-/home/max/Загрузки/Telegram Desktop/3.md}"
GROUP_URL="${3:-https://web.telegram.org/k/#-2181640359}"
CHAT_STEPS="${4:-20}"
CHAT_DEEP_LIMIT="${5:-10}"
TIMEOUT_SEC="${6:-8}"
CHAT_MAX_RUNTIME="${7:-180}"
CHAT_DEEP_MODE="${8:-mention}"
CHAT_MIN_MEMBERS="${9:-0}"

ROOT="/home/max/site-control-kit"
HUB_URL="http://127.0.0.1:8765"
STARTED_HUB=0

cd "$ROOT"
cleanup() {
  if [[ "${STARTED_HUB}" -eq 1 ]]; then
    kill "${HUB_PID:-}" >/dev/null 2>&1 || true
    wait "${HUB_PID:-}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

if ! curl -fsS --max-time 1 "$HUB_URL/health" >/dev/null 2>&1; then
  echo "INFO: hub not healthy on ${HUB_URL}, starting/recovering..."
  stale_pids="$(ss -ltnp 'sport = :8765' 2>/dev/null | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' | sort -u)"
  if [[ -n "${stale_pids}" ]]; then
    # Port is occupied but health endpoint is dead; terminate stale listeners.
    kill -9 ${stale_pids} >/dev/null 2>&1 || true
    sleep 0.4
  fi

  python3 -m webcontrol serve \
    --host 127.0.0.1 \
    --port 8765 \
    --token "$TOKEN" \
    --state-file "$HOME/.site-control-kit/state.json" \
    >/tmp/sitectl_hub_once.log 2>&1 &
  HUB_PID=$!
  STARTED_HUB=1

  for _ in {1..30}; do
    if curl -fsS --max-time 1 "$HUB_URL/health" >/dev/null 2>&1; then
      break
    fi
    sleep 0.2
  done

  if ! curl -fsS --max-time 2 "$HUB_URL/health" >/dev/null 2>&1; then
    echo "ERROR: hub failed to start. Log: /tmp/sitectl_hub_once.log" >&2
    exit 1
  fi
fi

clients_payload=""
for _ in {1..40}; do
  clients_payload="$(curl -sS --max-time 2 -H "X-Access-Token: ${TOKEN}" "${HUB_URL}/api/clients" || true)"
  if printf '%s' "$clients_payload" | grep -q '"client_id"'; then
    break
  fi
  sleep 0.25
done

clients_payload="$(curl -sS --max-time 2 -H "X-Access-Token: ${TOKEN}" "${HUB_URL}/api/clients" || true)"
if ! printf '%s' "$clients_payload" | grep -q '"client_id"'; then
  if printf '%s' "$clients_payload" | grep -q 'unauthorized'; then
    echo "ERROR: unauthorized on /api/clients (token mismatch). Align SITECTL_TOKEN in hub and extension." >&2
  else
    echo "ERROR: no connected bridge clients. Open Telegram Web tab and wait 2-3s." >&2
  fi
  exit 1
fi

echo "INFO: export start: source=chat steps=${CHAT_STEPS} deep_limit=${CHAT_DEEP_LIMIT} timeout=${TIMEOUT_SEC}s"
python3 -u "$ROOT/scripts/export_telegram_members_non_pii.py" \
  --token "$TOKEN" \
  --group-url "$GROUP_URL" \
  --source chat \
  --force-navigate \
  --timeout "$TIMEOUT_SEC" \
  --chat-max-runtime "$CHAT_MAX_RUNTIME" \
  --chat-deep-mode "$CHAT_DEEP_MODE" \
  --chat-min-members "$CHAT_MIN_MEMBERS" \
  --chat-scroll-steps "$CHAT_STEPS" \
  --deep-usernames \
  --chat-deep-limit "$CHAT_DEEP_LIMIT" \
  --output "$OUTPUT"
