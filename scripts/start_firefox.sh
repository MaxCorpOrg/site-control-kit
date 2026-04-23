#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXT_DIR="$ROOT_DIR/extension"
HUB_START_SCRIPT="$ROOT_DIR/scripts/start_hub.sh"

HOST="${SITECTL_HOST:-127.0.0.1}"
PORT="${SITECTL_PORT:-8765}"
SERVER_URL="${SITECTL_SERVER_URL:-http://${HOST}:${PORT}}"
TOKEN="${SITECTL_TOKEN:-local-bridge-quickstart-2026}"
PROFILE_DIR="${SITECTL_FIREFOX_PROFILE:-$HOME/.site-control-kit/firefox-profile}"
TARGET_URL="${SITECTL_START_URL:-https://web.telegram.org/a/}"
AUTO_START_HUB="${SITECTL_AUTO_START_HUB:-1}"
FIREFOX_BIN="${SITECTL_FIREFOX_BIN:-}"

print_usage() {
  cat <<EOF
Usage: $(basename "$0") [--url URL] [--profile DIR] [--firefox CMD] [--no-start-hub]

Starts Firefox for site-control-kit using the best available dev path.

Behavior:
- starts the local hub automatically unless --no-start-hub is used
- launches Firefox with a dedicated development profile
- on regular Firefox, installs extension/ temporarily via web-ext
- on snap Firefox, falls back to about:debugging manual temporary installation
- keeps the Firefox profile between runs so Telegram session/cookies persist

Notes:
- the extension itself is temporary in both modes
- the Firefox profile is for development only; web-ext changes it for debugging
EOF
}

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
    --firefox)
      FIREFOX_BIN="${2:?--firefox requires a value}"
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

detect_firefox() {
  if [[ -n "$FIREFOX_BIN" ]]; then
    printf '%s\n' "$FIREFOX_BIN"
    return 0
  fi

  if command -v firefox >/dev/null 2>&1; then
    printf 'firefox\n'
    return 0
  fi

  if command -v firefox-esr >/dev/null 2>&1; then
    printf 'firefox-esr\n'
    return 0
  fi

  return 1
}

detect_web_ext_mode() {
  if command -v web-ext >/dev/null 2>&1; then
    printf 'installed\n'
    return 0
  fi

  if command -v npx >/dev/null 2>&1; then
    printf 'npx\n'
    return 0
  fi

  return 1
}

is_snap_firefox_wrapper() {
  local firefox_path="$1"
  [[ -f "$firefox_path" ]] || return 1
  head -n 5 "$firefox_path" 2>/dev/null | grep -q '/snap/bin/firefox'
}

launch_firefox_manual() {
  local firefox="$1"
  mkdir -p "$PROFILE_DIR"

  local -a cmd=(
    "$firefox"
    --new-instance
    "--profile=$PROFILE_DIR"
    "about:debugging#/runtime/this-firefox"
    "$TARGET_URL"
  )

  local quoted=()
  local item=""
  local root_dir_quoted=""
  printf -v root_dir_quoted '%q' "$ROOT_DIR"
  for item in "${cmd[@]}"; do
    printf -v item '%q' "$item"
    quoted+=("$item")
  done
  spawn_detached_shell "cd $root_dir_quoted && exec ${quoted[*]}" /tmp/site-control-kit-firefox.log
}

launch_firefox_bridge() {
  local firefox="$1"
  local mode="$2"
  mkdir -p "$PROFILE_DIR"

  local -a cmd=()
  case "$mode" in
    installed)
      cmd=(web-ext run)
      ;;
    npx)
      cmd=(npx --yes web-ext@8 run)
      ;;
    *)
      echo "Unsupported web-ext mode: $mode" >&2
      return 1
      ;;
  esac

  cmd+=(
    "--source-dir=$EXT_DIR"
    "--target=firefox-desktop"
    "--firefox=$firefox"
    "--firefox-profile=$PROFILE_DIR"
    "--keep-profile-changes"
    "--no-reload"
    "--start-url=$TARGET_URL"
  )

  local quoted=()
  local item=""
  local root_dir_quoted=""
  printf -v root_dir_quoted '%q' "$ROOT_DIR"
  for item in "${cmd[@]}"; do
    printf -v item '%q' "$item"
    quoted+=("$item")
  done
  spawn_detached_shell "cd $root_dir_quoted && exec ${quoted[*]}" /tmp/site-control-kit-firefox.log
}

ensure_hub

firefox="$(detect_firefox || true)"
if [[ -z "$firefox" ]]; then
  echo "No Firefox binary found. Install Firefox or firefox-esr." >&2
  exit 1
fi

firefox_path="$(command -v "$firefox" || true)"
firefox_mode="web-ext"
if [[ -n "$firefox_path" ]] && is_snap_firefox_wrapper "$firefox_path"; then
  firefox_mode="manual"
fi

if [[ "$firefox_mode" == "web-ext" ]]; then
  web_ext_mode="$(detect_web_ext_mode || true)"
  if [[ -z "$web_ext_mode" ]]; then
    echo "Neither web-ext nor npx is available. Install Node.js or web-ext." >&2
    exit 1
  fi
  echo "Launching Firefox bridge via web-ext using profile: $PROFILE_DIR" >&2
  echo "Log: /tmp/site-control-kit-firefox.log" >&2
  launch_firefox_bridge "$firefox" "$web_ext_mode"
else
  echo "Detected snap Firefox wrapper; using about:debugging fallback." >&2
  echo "Log: /tmp/site-control-kit-firefox.log" >&2
  launch_firefox_manual "$firefox"
fi

if [[ "$firefox_mode" == "web-ext" ]]; then
  cat >&2 <<EOF
Firefox bridge launch requested.

Hub:
  $SERVER_URL

Profile:
  $PROFILE_DIR

If this is the first run, web-ext may need a little time to prepare the temporary add-on.
Then verify the client with:
  cd $ROOT_DIR
  ./browser.sh status
  ./browser.sh tabs
EOF
else
  cat >&2 <<EOF
Firefox dev profile launched in manual temporary-add-on mode.

Hub:
  $SERVER_URL

Profile:
  $PROFILE_DIR

Do this in Firefox:
1. Open "This Firefox" in about:debugging
2. Click "Load Temporary Add-on"
3. Select: $EXT_DIR/manifest.json
4. Keep the Telegram tab open in the same profile

Then verify the client with:
  cd $ROOT_DIR
  ./browser.sh status
  ./browser.sh tabs
EOF
fi
