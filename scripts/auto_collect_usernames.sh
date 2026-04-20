#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/home/max/site-control-kit"
EXPORT_SCRIPT="${ROOT_DIR}/scripts/export_telegram_members_non_pii.py"
PROFILE_HELPER="${ROOT_DIR}/scripts/telegram_profiles.py"
HUB_URL="http://127.0.0.1:8765"
TOKEN="${SITECTL_TOKEN:-local-bridge-quickstart-2026}"

GROUP_URL="${1:-https://web.telegram.org/k/#-1288116010}"
OUT_MD="${2:-${HOME}/Загрузки/Telegram Desktop/telegram_usernames_auto.md}"

CHAT_PROFILE="${CHAT_PROFILE:-balanced}"

if [[ ! -f "${PROFILE_HELPER}" ]]; then
  echo "ERROR: profile helper not found: ${PROFILE_HELPER}" >&2
  exit 1
fi

apply_profile_defaults() {
  local profile_name="$1"
  while IFS=$'\t' read -r name value; do
    [[ -n "${name:-}" ]] || continue
    if [[ -z "${!name:-}" ]]; then
      export "${name}=${value}"
    fi
  done < <(python3 "${PROFILE_HELPER}" env "${profile_name}")
}

apply_profile_defaults "${CHAT_PROFILE}"

CHAT_STEPS="${CHAT_SCROLL_STEPS:-120}"
CHAT_DEEP_LIMIT="${CHAT_DEEP_LIMIT:-120}"
CHAT_TIMEOUT_SEC="${CHAT_TIMEOUT_SEC:-12}"
CHAT_MAX_RUNTIME="${CHAT_MAX_RUNTIME:-900}"
CHAT_DEEP_MODE="${CHAT_DEEP_MODE:-full}"
CHAT_MIN_MEMBERS="${CHAT_MIN_MEMBERS:-0}"
CHAT_MAX_MEMBERS="${CHAT_MAX_MEMBERS:-0}"
WAIT_CLIENT_SEC="${WAIT_CLIENT_SEC:-120}"
CHAT_CLIENT_ID="${CHAT_CLIENT_ID:-}"
CHAT_TAB_ID="${CHAT_TAB_ID:-}"
CHAT_IDENTITY_HISTORY="${CHAT_IDENTITY_HISTORY:-}"
CHAT_DISCOVERY_STATE="${CHAT_DISCOVERY_STATE:-}"
CHAT_STATS_OUTPUT="${CHAT_STATS_OUTPUT:-}"

if [[ ! -f "${EXPORT_SCRIPT}" ]]; then
  echo "ERROR: export script not found: ${EXPORT_SCRIPT}" >&2
  exit 1
fi

start_hub_if_needed() {
  if curl -fsS --max-time 2 "${HUB_URL}/health" >/dev/null 2>&1; then
    return
  fi

  echo "INFO: starting hub on ${HUB_URL}"
  nohup python3 -m webcontrol serve \
    --host 127.0.0.1 \
    --port 8765 \
    --token "${TOKEN}" \
    --state-file "${HOME}/.site-control-kit/state.json" \
    >/tmp/telegram_auto_hub.log 2>&1 &

  for _ in {1..80}; do
    if curl -fsS --max-time 2 "${HUB_URL}/health" >/dev/null 2>&1; then
      return
    fi
    sleep 0.25
  done

  echo "ERROR: hub failed to start. Log: /tmp/telegram_auto_hub.log" >&2
  exit 1
}

open_telegram_tab() {
  if ! command -v xdg-open >/dev/null 2>&1; then
    return
  fi

  if python3 - "$HUB_URL" "$TOKEN" "$GROUP_URL" <<'PY'
import json
import sys
from urllib.request import Request, urlopen

hub_url, token, group_url = sys.argv[1], sys.argv[2], sys.argv[3]
target_fragment = group_url.split("#", 1)[1] if "#" in group_url else ""
req = Request(
    f"{hub_url}/api/clients",
    headers={"Accept": "application/json", "X-Access-Token": token},
)
try:
    with urlopen(req, timeout=3) as r:
        payload = json.loads(r.read().decode("utf-8"))
except Exception:
    raise SystemExit(1)

for client in payload.get("clients") or []:
    for tab in client.get("tabs") or []:
        url = str(tab.get("url") or "")
        if "web.telegram.org" not in url:
            continue
        fragment = url.split("#", 1)[1] if "#" in url else ""
        if target_fragment and fragment == target_fragment:
            raise SystemExit(0)

raise SystemExit(1)
PY
  then
    echo "INFO: target Telegram tab already visible in hub state"
    return
  fi

  xdg-open "${GROUP_URL}" >/dev/null 2>&1 || true
}

wait_for_telegram_client() {
  local deadline
  deadline=$((SECONDS + WAIT_CLIENT_SEC))

  while (( SECONDS < deadline )); do
    if python3 - "$HUB_URL" "$TOKEN" <<'PY'
import json
import sys
from datetime import datetime, timezone
from urllib.request import Request, urlopen

hub_url, token = sys.argv[1], sys.argv[2]
req = Request(
    f"{hub_url}/api/clients",
    headers={"Accept": "application/json", "X-Access-Token": token},
)
try:
    with urlopen(req, timeout=3) as r:
        payload = json.loads(r.read().decode("utf-8"))
except Exception:
    raise SystemExit(1)

now = datetime.now(timezone.utc)
clients = payload.get("clients") or []
for client in clients:
    seen = str(client.get("last_seen") or "").strip()
    tabs = client.get("tabs") or []
    if not tabs:
        continue
    has_telegram = any("web.telegram.org" in str(tab.get("url") or "") for tab in tabs)
    if not has_telegram:
        continue
    if seen:
        try:
            dt = datetime.fromisoformat(seen)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if (now - dt).total_seconds() > 120:
                continue
        except Exception:
            pass
    raise SystemExit(0)

raise SystemExit(1)
PY
    then
      return
    fi
    sleep 1
  done

  echo "ERROR: telegram bridge client not detected in ${WAIT_CLIENT_SEC}s." >&2
  echo "Open Telegram Web with extension enabled and logged in." >&2
  exit 1
}

resolve_target_tab() {
  python3 - "$HUB_URL" "$TOKEN" "$GROUP_URL" "$CHAT_CLIENT_ID" "$CHAT_TAB_ID" <<'PY'
import json
import sys
from urllib.request import Request, urlopen

hub_url, token, group_url, forced_client_id, forced_tab_id = sys.argv[1:6]
target_fragment = group_url.split("#", 1)[1] if "#" in group_url else ""

req = Request(
    f"{hub_url}/api/clients",
    headers={"Accept": "application/json", "X-Access-Token": token},
)
try:
    with urlopen(req, timeout=3) as r:
        payload = json.loads(r.read().decode("utf-8"))
except Exception:
    raise SystemExit(0)

clients = payload.get("clients") or []

forced_client_id = forced_client_id.strip()
forced_tab_id = forced_tab_id.strip()

if forced_tab_id:
    for client in clients:
        client_id = str(client.get("client_id") or "").strip()
        if forced_client_id and client_id != forced_client_id:
            continue
        for tab in client.get("tabs") or []:
            tab_id = tab.get("id")
            if str(tab_id) == forced_tab_id:
                print(f"{client_id}\t{forced_tab_id}")
                raise SystemExit(0)
    if forced_client_id:
        print(f"{forced_client_id}\t{forced_tab_id}")
        raise SystemExit(0)
    print(f"\t{forced_tab_id}")
    raise SystemExit(0)

exact_matches = []
for client in clients:
    client_id = str(client.get("client_id") or "").strip()
    if forced_client_id and client_id != forced_client_id:
        continue
    for tab in client.get("tabs") or []:
        tab_id = tab.get("id")
        url = str(tab.get("url") or "")
        fragment = url.split("#", 1)[1] if "#" in url else ""
        if target_fragment and fragment == target_fragment and isinstance(tab_id, int):
            exact_matches.append((bool(tab.get("active")), client_id, tab_id))

if exact_matches:
    exact_matches.sort(key=lambda item: (not item[0], item[1], item[2]))
    _, client_id, tab_id = exact_matches[0]
    print(f"{client_id}\t{tab_id}")
    raise SystemExit(0)

for client in clients:
    client_id = str(client.get("client_id") or "").strip()
    if forced_client_id and client_id != forced_client_id:
        continue
    for tab in client.get("tabs") or []:
        tab_id = tab.get("id")
        url = str(tab.get("url") or "")
        if "web.telegram.org" in url and isinstance(tab_id, int):
            print(f"{client_id}\t{tab_id}")
            raise SystemExit(0)

raise SystemExit(0)
PY
}

extract_usernames_txt() {
  local md_file="$1"
  local txt_file="$2"
  python3 - "$md_file" "$txt_file" <<'PY'
import re
import sys
from pathlib import Path

md = Path(sys.argv[1])
out = Path(sys.argv[2])
text = md.read_text(encoding="utf-8", errors="ignore")
seen = set()
rows = []
for line in text.splitlines():
    m = re.search(r"\|\s*\d+\s*\|.*\|\s*(@[A-Za-z0-9_]{5,32})\s*\|", line)
    if not m:
        continue
    u = m.group(1)
    k = u.lower()
    if k in seen:
        continue
    seen.add(k)
    rows.append(u)
out.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")
print(f"OK: saved {len(rows)} usernames to {out}")
PY
}

cd "${ROOT_DIR}"
start_hub_if_needed
open_telegram_tab
wait_for_telegram_client

resolved_client_id=""
resolved_tab_id=""
resolved_target="$(resolve_target_tab || true)"
if [[ -n "${resolved_target}" ]]; then
  IFS=$'\t' read -r resolved_client_id resolved_tab_id <<<"${resolved_target}"
fi

mkdir -p "$(dirname "${OUT_MD}")"
echo "INFO: collecting usernames from ${GROUP_URL}"
extra_args=()
identity_args=()
discovery_args=()
stats_args=()
if [[ -n "${resolved_client_id}" ]]; then
  extra_args+=(--client-id "${resolved_client_id}")
fi
if [[ -n "${resolved_tab_id}" ]]; then
  extra_args+=(--tab-id "${resolved_tab_id}")
fi
if [[ -n "${CHAT_IDENTITY_HISTORY}" ]]; then
  identity_args+=(--identity-history "${CHAT_IDENTITY_HISTORY}")
fi
if [[ -n "${CHAT_DISCOVERY_STATE}" ]]; then
  discovery_args+=(--discovery-state "${CHAT_DISCOVERY_STATE}")
fi
if [[ -n "${CHAT_STATS_OUTPUT}" ]]; then
  stats_args+=(--stats-output "${CHAT_STATS_OUTPUT}")
fi
if [[ -n "${resolved_client_id}" || -n "${resolved_tab_id}" ]]; then
  echo "INFO: using Telegram target client=${resolved_client_id:-auto} tab=${resolved_tab_id:-auto}"
fi

python3 -u "${EXPORT_SCRIPT}" \
  --token "${TOKEN}" \
  --group-url "${GROUP_URL}" \
  --source chat \
  --force-navigate \
  --timeout "${CHAT_TIMEOUT_SEC}" \
  --chat-max-runtime "${CHAT_MAX_RUNTIME}" \
  --chat-deep-mode "${CHAT_DEEP_MODE}" \
  --chat-min-members "${CHAT_MIN_MEMBERS}" \
  --max-members "${CHAT_MAX_MEMBERS}" \
  --chat-scroll-steps "${CHAT_STEPS}" \
  --deep-usernames \
  --chat-deep-limit "${CHAT_DEEP_LIMIT}" \
  "${identity_args[@]}" \
  "${discovery_args[@]}" \
  "${stats_args[@]}" \
  "${extra_args[@]}" \
  --output "${OUT_MD}"

OUT_TXT="${OUT_MD%.md}_usernames.txt"
extract_usernames_txt "${OUT_MD}" "${OUT_TXT}"
echo "DONE:"
echo "  MD:  ${OUT_MD}"
echo "  TXT: ${OUT_TXT}"
