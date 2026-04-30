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
CHAT_DEEP_MODE="${8:-url}"
FORCED_CLIENT_ID="${10:-${CHAT_CLIENT_ID:-}}"
FORCED_TAB_ID="${11:-${CHAT_TAB_ID:-}}"

ROOT="/home/max/site-control-kit"
HUB_URL="http://127.0.0.1:8765"
STARTED_HUB=0
START_TELEGRAM_SCRIPT="$ROOT/scripts/start_telegram.sh"

cd "$ROOT"
cleanup() {
  if [[ "${STARTED_HUB}" -eq 1 ]]; then
    kill "${HUB_PID:-}" >/dev/null 2>&1 || true
    wait "${HUB_PID:-}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

has_bridge_client() {
  local target_client_id="${1:-}"
  python3 - "$HUB_URL" "$TOKEN" "$target_client_id" <<'PY'
import json
import sys
from urllib.request import Request, urlopen

hub_url, token, forced_client_id = sys.argv[1], sys.argv[2], str(sys.argv[3] or "").strip()
req = Request(
    f"{hub_url}/api/clients",
    headers={"Accept": "application/json", "X-Access-Token": token},
)
try:
    with urlopen(req, timeout=3) as response:
        payload = json.loads(response.read().decode("utf-8"))
except Exception:
    raise SystemExit(1)

clients = payload.get("clients") or []
if forced_client_id:
    for client in clients:
        if str(client.get("client_id") or "").strip() == forced_client_id:
            raise SystemExit(0)
    raise SystemExit(1)

for client in clients:
    if str(client.get("client_id") or "").strip():
        raise SystemExit(0)
raise SystemExit(1)
PY
}

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

for _ in {1..40}; do
  if has_bridge_client "${FORCED_CLIENT_ID}"; then
    break
  fi
  sleep 0.25
done

if ! has_bridge_client "${FORCED_CLIENT_ID}"; then
  if [[ -x "${START_TELEGRAM_SCRIPT}" ]]; then
    echo "INFO: no connected bridge clients, opening Telegram Web profile..." >&2
    nohup env SITECTL_TOKEN="${TOKEN}" bash "${START_TELEGRAM_SCRIPT}" >/tmp/sitectl_telegram_browser.log 2>&1 &
    for _ in {1..30}; do
      if has_bridge_client "${FORCED_CLIENT_ID}"; then
        break
      fi
      sleep 0.5
    done
  fi
fi

if ! has_bridge_client "${FORCED_CLIENT_ID}"; then
  if [[ -n "${FORCED_CLIENT_ID}" ]]; then
    echo "ERROR: target client is not connected: ${FORCED_CLIENT_ID}" >&2
  else
    echo "ERROR: no connected bridge clients. The Telegram browser profile was opened; finish the one-time extension setup there if needed, then rerun." >&2
  fi
  exit 1
fi

echo "INFO: export start: source=chat steps=${CHAT_STEPS} deep_limit=${CHAT_DEEP_LIMIT} timeout=${TIMEOUT_SEC}s"
if [[ -n "${FORCED_CLIENT_ID}" || -n "${FORCED_TAB_ID}" ]]; then
  echo "INFO: target override: client_id=${FORCED_CLIENT_ID:-auto} tab_id=${FORCED_TAB_ID:-auto}"
fi

extra_target_args=()
if [[ -n "${FORCED_CLIENT_ID}" ]]; then
  extra_target_args+=(--client-id "${FORCED_CLIENT_ID}")
fi
if [[ -n "${FORCED_TAB_ID}" ]]; then
  extra_target_args+=(--tab-id "${FORCED_TAB_ID}")
fi

python3 -u "$ROOT/scripts/export_telegram_members_non_pii.py" \
  --token "$TOKEN" \
  --group-url "$GROUP_URL" \
  --source chat \
  --force-navigate \
  --timeout "$TIMEOUT_SEC" \
  --chat-max-runtime "$CHAT_MAX_RUNTIME" \
  --chat-deep-mode "$CHAT_DEEP_MODE" \
  --chat-scroll-steps "$CHAT_STEPS" \
  --deep-usernames \
  --chat-deep-limit "$CHAT_DEEP_LIMIT" \
  "${extra_target_args[@]}" \
  --output "$OUTPUT"
