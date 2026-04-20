#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER_URL="${SITECTL_SERVER:-http://127.0.0.1:8765}"
ACCESS_TOKEN="${SITECTL_TOKEN:-local-bridge-quickstart-2026}"
EXTENSION_ID="${SCB_EXTENSION_ID:-bfmgnjibjekkbhhchjfmjfbfbfemdnbf}"
RELOAD_X_RATIO="${SCB_RELOAD_X_RATIO:-0.93}"
RELOAD_Y_RATIO="${SCB_RELOAD_Y_RATIO:-0.17}"
BUTTON_NUMBER="${SCB_RELOAD_BUTTON:-1}"
OPEN_WAIT_SEC="${SCB_RELOAD_OPEN_WAIT_SEC:-1.5}"
POST_CLICK_WAIT_SEC="${SCB_RELOAD_POST_CLICK_WAIT_SEC:-3}"
VERIFY_WAIT_SEC="${SCB_RELOAD_VERIFY_WAIT_SEC:-12}"
RESTORE_ORIGINAL_URL="${SCB_RESTORE_ORIGINAL_URL:-1}"
REQUESTED_CLIENT_ID="${SCB_CLIENT_ID:-}"
REQUESTED_TAB_ID="${SCB_RELOAD_TAB_ID:-}"

PYTHONPATH="${ROOT_DIR}:${PYTHONPATH:-}"
export PYTHONPATH
export SERVER_URL ACCESS_TOKEN REQUESTED_CLIENT_ID REQUESTED_TAB_ID VERIFY_WAIT_SEC CLIENT_ID

TARGET_URL="chrome://extensions/?id=${EXTENSION_ID}"
SELF_RELOAD_URL="chrome-extension://${EXTENSION_ID}/options.html?action=reload-self"

selection_json="$(
python3 - <<'PY'
import json
import os
import sys
import urllib.request

server = os.environ["SERVER_URL"]
token = os.environ["ACCESS_TOKEN"]
requested_client_id = os.environ.get("REQUESTED_CLIENT_ID", "").strip()
requested_tab_id = os.environ.get("REQUESTED_TAB_ID", "").strip()

req = urllib.request.Request(
    server.rstrip("/") + "/api/clients",
    headers={"Authorization": f"Bearer {token}"},
)
with urllib.request.urlopen(req, timeout=10) as response:
    payload = json.load(response)

clients = payload.get("clients") or []
if not clients:
    raise SystemExit("No connected browser clients.")

selected_client = None
if requested_client_id:
    for candidate in clients:
        if str(candidate.get("client_id") or "").strip() == requested_client_id:
            selected_client = candidate
            break
    if selected_client is None:
        raise SystemExit(f"Browser client not found: {requested_client_id}")
else:
    selected_client = sorted(clients, key=lambda item: str(item.get("last_seen", "")), reverse=True)[0]

tabs = selected_client.get("tabs") or []
selected_tab = None
if requested_tab_id:
    for candidate in tabs:
        if str(candidate.get("id", "")).strip() == requested_tab_id:
            selected_tab = candidate
            break
    if selected_tab is None:
        raise SystemExit(f"Browser tab not found: {requested_tab_id}")
else:
    for candidate in tabs:
        url = str(candidate.get("url") or "")
        if url.startswith("chrome://extensions/?id="):
            selected_tab = candidate
            break
    if selected_tab is None:
        for candidate in tabs:
            url = str(candidate.get("url") or "")
            if url == "chrome://newtab/":
                selected_tab = candidate
                break
    if selected_tab is None and tabs:
        selected_tab = tabs[0]

if selected_tab is None:
    raise SystemExit("No browser tab available for extension reload helper.")

result = {
    "client_id": str(selected_client.get("client_id") or "").strip(),
    "tab_id": int(selected_tab.get("id")),
    "original_url": str(selected_tab.get("url") or ""),
    "original_title": str(selected_tab.get("title") or ""),
}
print(json.dumps(result, ensure_ascii=False))
PY
)"

CLIENT_ID="$(python3 - <<'PY' "$selection_json"
import json
import sys
print(json.loads(sys.argv[1])["client_id"])
PY
)"
TAB_ID="$(python3 - <<'PY' "$selection_json"
import json
import sys
print(json.loads(sys.argv[1])["tab_id"])
PY
)"
ORIGINAL_URL="$(python3 - <<'PY' "$selection_json"
import json
import sys
print(json.loads(sys.argv[1])["original_url"])
PY
)"
ORIGINAL_TITLE="$(python3 - <<'PY' "$selection_json"
import json
import sys
print(json.loads(sys.argv[1])["original_title"])
PY
)"

echo "INFO: reload helper client=${CLIENT_ID} tab=${TAB_ID} title=${ORIGINAL_TITLE:-unknown}"
echo "INFO: try self-reload via ${SELF_RELOAD_URL}"
python3 -m webcontrol browser \
  --server "${SERVER_URL}" \
  --token "${ACCESS_TOKEN}" \
  --client-id "${CLIENT_ID}" \
  --tab-id "${TAB_ID}" \
  open "${SELF_RELOAD_URL}" >/dev/null || true

sleep "${POST_CLICK_WAIT_SEC}"

verify_json="$(
python3 - <<'PY'
import json
import os
import time
import urllib.request

server = os.environ["SERVER_URL"]
token = os.environ["ACCESS_TOKEN"]
client_id = os.environ["CLIENT_ID"]
deadline = time.time() + float(os.environ["VERIFY_WAIT_SEC"])
last_seen = ""
content_caps = None

while time.time() < deadline:
    req = urllib.request.Request(
        server.rstrip("/") + "/api/clients",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        payload = json.load(response)
    clients = payload.get("clients") or []
    for client in clients:
        if str(client.get("client_id") or "").strip() != client_id:
            continue
        last_seen = str(client.get("last_seen") or "")
        meta = client.get("meta") or {}
        capabilities = meta.get("capabilities") if isinstance(meta, dict) else None
        if isinstance(capabilities, dict):
            content_caps = capabilities.get("content_commands")
        if isinstance(content_caps, list) and content_caps:
            print(json.dumps({"ok": True, "last_seen": last_seen, "content_commands": content_caps}, ensure_ascii=False))
            raise SystemExit(0)
    time.sleep(0.8)

print(json.dumps({"ok": False, "last_seen": last_seen, "content_commands": content_caps}, ensure_ascii=False))
PY
)"

echo "INFO: verify ${verify_json}"

if [[ "${verify_json}" == *'"ok": false'* ]]; then
  echo "INFO: self-reload did not expose content_commands, falling back to chrome://extensions"
  python3 -m webcontrol browser \
    --server "${SERVER_URL}" \
    --token "${ACCESS_TOKEN}" \
    --client-id "${CLIENT_ID}" \
    --tab-id "${TAB_ID}" \
    open "${TARGET_URL}" >/dev/null

  sleep "${OPEN_WAIT_SEC}"

  echo "INFO: x11 click ratio=(${RELOAD_X_RATIO}, ${RELOAD_Y_RATIO}) button=${BUTTON_NUMBER}"
  python3 -m webcontrol browser \
    --server "${SERVER_URL}" \
    --token "${ACCESS_TOKEN}" \
    --client-id "${CLIENT_ID}" \
    --tab-id "${TAB_ID}" \
    x11-click \
    --x-ratio "${RELOAD_X_RATIO}" \
    --y-ratio "${RELOAD_Y_RATIO}" \
    --button "${BUTTON_NUMBER}"

  sleep "${POST_CLICK_WAIT_SEC}"

  verify_json="$(
  python3 - <<'PY'
import json
import os
import time
import urllib.request

server = os.environ["SERVER_URL"]
token = os.environ["ACCESS_TOKEN"]
client_id = os.environ["CLIENT_ID"]
deadline = time.time() + float(os.environ["VERIFY_WAIT_SEC"])
last_seen = ""
content_caps = None

while time.time() < deadline:
    req = urllib.request.Request(
        server.rstrip("/") + "/api/clients",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        payload = json.load(response)
    clients = payload.get("clients") or []
    for client in clients:
        if str(client.get("client_id") or "").strip() != client_id:
            continue
        last_seen = str(client.get("last_seen") or "")
        meta = client.get("meta") or {}
        capabilities = meta.get("capabilities") if isinstance(meta, dict) else None
        if isinstance(capabilities, dict):
            content_caps = capabilities.get("content_commands")
        if isinstance(content_caps, list) and content_caps:
            print(json.dumps({"ok": True, "last_seen": last_seen, "content_commands": content_caps}, ensure_ascii=False))
            raise SystemExit(0)
    time.sleep(0.8)

print(json.dumps({"ok": False, "last_seen": last_seen, "content_commands": content_caps}, ensure_ascii=False))
PY
  )"
  echo "INFO: verify after fallback ${verify_json}"
fi

if [[ "${RESTORE_ORIGINAL_URL}" == "1" ]] && [[ -n "${ORIGINAL_URL}" ]] && [[ "${ORIGINAL_URL}" != "${TARGET_URL}" ]]; then
  echo "INFO: restore ${ORIGINAL_URL}"
  python3 -m webcontrol browser \
    --server "${SERVER_URL}" \
    --token "${ACCESS_TOKEN}" \
    --client-id "${CLIENT_ID}" \
    --tab-id "${TAB_ID}" \
    open "${ORIGINAL_URL}" >/dev/null || true
fi
