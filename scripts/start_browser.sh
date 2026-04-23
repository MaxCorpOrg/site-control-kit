#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXT_DIR="$ROOT_DIR/extension"
HUB_START_SCRIPT="$ROOT_DIR/scripts/start_hub.sh"

HOST="${SITECTL_HOST:-127.0.0.1}"
PORT="${SITECTL_PORT:-8765}"
SERVER_URL="${SITECTL_SERVER_URL:-http://${HOST}:${PORT}}"
TOKEN="${SITECTL_TOKEN:-local-bridge-quickstart-2026}"
PROFILE_DIR="${SITECTL_BROWSER_PROFILE:-$HOME/.site-control-kit/browser-profile}"
TARGET_URL="${SITECTL_START_URL:-https://example.com}"
AUTO_START_HUB="${SITECTL_AUTO_START_HUB:-1}"

print_usage() {
  cat <<EOF
Usage: $(basename "$0") [--url URL] [--profile DIR] [--browser CMD] [--no-start-hub]

Starts a browser client profile for site-control-kit on Linux.

Behavior:
- starts the local hub automatically unless --no-start-hub is used
- prefers Chromium-compatible browsers that allow --load-extension
- falls back to Google Chrome with a dedicated profile if the extension was already installed manually
- if only branded Google Chrome is available and the extension is not installed in the profile yet,
  opens chrome://extensions and prints the one-time setup steps
EOF
}

BROWSER_CMD=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --url)
      TARGET_URL="${2:?--url requires a value}"
      shift 2
      ;;
    --profile)
      PROFILE_DIR="${2:?--profile requires a value}"
      shift 2
      ;;
    --browser)
      BROWSER_CMD="${2:?--browser requires a value}"
      shift 2
      ;;
    --no-start-hub)
      AUTO_START_HUB="0"
      shift
      ;;
    -h|--help)
      print_usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      print_usage >&2
      exit 1
      ;;
  esac
done

hub_healthy() {
  curl -fsS --max-time 1 "$SERVER_URL/health" >/dev/null 2>&1
}

wait_for_hub() {
  for _ in {1..50}; do
    if hub_healthy; then
      return 0
    fi
    sleep 0.2
  done
  return 1
}

spawn_detached_shell() {
  local command="$1"
  local log_file="$2"
  if command -v setsid >/dev/null 2>&1; then
    setsid -f bash -lc "$command" >"$log_file" 2>&1
    return 0
  fi
  nohup bash -lc "$command" >"$log_file" 2>&1 &
}

ensure_hub() {
  if hub_healthy; then
    return 0
  fi

  if [[ "$AUTO_START_HUB" != "1" ]]; then
    echo "Hub is not healthy on $SERVER_URL and auto-start is disabled." >&2
    return 1
  fi

  echo "Starting hub on $SERVER_URL ..." >&2
  local hub_cmd=""
  printf -v hub_cmd '%q ' env SITECTL_HOST="$HOST" SITECTL_PORT="$PORT" SITECTL_TOKEN="$TOKEN" bash "$HUB_START_SCRIPT"
  spawn_detached_shell "${hub_cmd% }" /tmp/site-control-kit-hub.log

  if ! wait_for_hub; then
    echo "Failed to start hub. Check /tmp/site-control-kit-hub.log" >&2
    return 1
  fi
}

detect_browser() {
  if [[ -n "$BROWSER_CMD" ]]; then
    printf '%s\n' "$BROWSER_CMD"
    return 0
  fi

  if command -v chromium >/dev/null 2>&1; then
    printf 'chromium\n'
    return 0
  fi

  if command -v chromium-browser >/dev/null 2>&1; then
    printf 'chromium-browser\n'
    return 0
  fi

  if command -v snap >/dev/null 2>&1 && snap list chromium >/dev/null 2>&1; then
    printf 'snap:chromium\n'
    return 0
  fi

  if command -v google-chrome >/dev/null 2>&1; then
    printf 'google-chrome\n'
    return 0
  fi

  return 1
}

profile_has_site_control_extension() {
  local pref_file="$PROFILE_DIR/Default/Preferences"
  if [[ ! -f "$pref_file" ]]; then
    return 1
  fi

  python3 - "$pref_file" "$EXT_DIR" <<'PY'
import json
import sys
from pathlib import Path

pref_file = Path(sys.argv[1])
ext_dir = Path(sys.argv[2]).resolve()

try:
    data = json.loads(pref_file.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(1)

settings = ((data.get("extensions") or {}).get("settings") or {})
for cfg in settings.values():
    manifest = cfg.get("manifest") or {}
    path = str(cfg.get("path") or "").strip()
    if manifest.get("name") == "Site Control Bridge":
        raise SystemExit(0)
    if path:
        resolved = (pref_file.parent / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
        if resolved == ext_dir:
            raise SystemExit(0)

raise SystemExit(1)
PY
}

launch_detached() {
  local -a cmd=("$@")
  local quoted=()
  local item=""
  for item in "${cmd[@]}"; do
    printf -v item '%q' "$item"
    quoted+=("$item")
  done
  spawn_detached_shell "exec ${quoted[*]}" /tmp/site-control-kit-browser.log
}

launch_with_extension_flags() {
  local browser="$1"
  mkdir -p "$PROFILE_DIR"
  if [[ "$browser" == "snap:chromium" ]]; then
    launch_detached snap run chromium \
      --user-data-dir="$PROFILE_DIR" \
      --disable-extensions-except="$EXT_DIR" \
      --load-extension="$EXT_DIR" \
      --no-first-run \
      --no-default-browser-check \
      --new-window \
      "$TARGET_URL"
    return 0
  fi

  launch_detached "$browser" \
    --user-data-dir="$PROFILE_DIR" \
    --disable-extensions-except="$EXT_DIR" \
    --load-extension="$EXT_DIR" \
    --no-first-run \
    --no-default-browser-check \
    --new-window \
    "$TARGET_URL"
}

launch_google_chrome_profile() {
  mkdir -p "$PROFILE_DIR"
  launch_detached "google-chrome" \
    --user-data-dir="$PROFILE_DIR" \
    --no-first-run \
    --no-default-browser-check \
    --new-window \
    "$1"
}

ensure_hub

browser="$(detect_browser || true)"
if [[ -z "$browser" ]]; then
  echo "No supported browser command found. Install Chromium or Google Chrome." >&2
  exit 1
fi

case "$browser" in
  chromium|chromium-browser|"snap run chromium")
    echo "Launching compatible browser: $browser" >&2
    launch_with_extension_flags "$browser"
    ;;
  snap:chromium)
    echo "Launching compatible browser: snap run chromium" >&2
    launch_with_extension_flags "$browser"
    ;;
  google-chrome)
    if profile_has_site_control_extension; then
      echo "Launching Google Chrome with the prepared site-control profile." >&2
      launch_google_chrome_profile "$TARGET_URL"
    else
      cat >&2 <<EOF
Google Chrome on this machine blocks command-line flags:
  --disable-extensions-except
  --load-extension

Automatic unpacked extension loading is not possible in branded Chrome here.

One-time setup:
1. A dedicated profile will open on chrome://extensions
2. Enable Developer mode
3. Click "Load unpacked"
4. Select: $EXT_DIR
5. Open extension Options and keep:
   Server URL: $SERVER_URL
   Access Token: $TOKEN

After this one-time setup, rerun:
  $ROOT_DIR/start-browser.sh

Hub is already available on:
  $SERVER_URL
EOF
      launch_google_chrome_profile "chrome://extensions"
    fi
    ;;
  *)
    echo "Unsupported browser command: $browser" >&2
    exit 1
    ;;
esac

echo "Browser launch requested. Hub: $SERVER_URL" >&2
