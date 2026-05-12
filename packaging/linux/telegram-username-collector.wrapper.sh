#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="/opt/telegram-username-collector/app"
VENV_ROOT="/opt/telegram-username-collector/venv"
PYTHON_BIN="$VENV_ROOT/bin/python"
CONFIG_ROOT="${XDG_CONFIG_HOME:-$HOME/.config}/site-control-kit"
DATA_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/site-control-kit"
STATE_ROOT="${XDG_STATE_HOME:-$HOME/.local/state}/site-control-kit"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "ERROR: bundled Python is missing: $PYTHON_BIN" >&2
  exit 1
fi

mkdir -p "$CONFIG_ROOT" "$DATA_ROOT" "$STATE_ROOT/logs"

export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"
export SITECTL_PRODUCT_MODE="installed"
export SITECTL_PRODUCT_APP_ROOT="$APP_ROOT"
export SITECTL_PRODUCT_VENV="$VENV_ROOT"
export SITECTL_PRODUCT_EXECUTABLE="telegram-username-collector"
export SITECTL_PRODUCT_DESKTOP_FILE="/usr/share/applications/telegram-username-collector.desktop"
export SITECTL_PRODUCT_ICON="/usr/share/icons/hicolor/256x256/apps/telegram-username-collector.png"
export SITECTL_PRODUCT_EXTENSION_DIR="$APP_ROOT/extension"
export SITECTL_PRODUCT_EXTENSION_ZIP="$APP_ROOT/resources/site-control-bridge-extension.zip"
export SITECTL_RUNTIME_ROOT="$DATA_ROOT"
export SITECTL_STATE_FILE="$DATA_ROOT/state/state.json"
export SITECTL_REPORTS_ROOT="$DATA_ROOT/reports"
export SITECTL_LOG_DIR="$STATE_ROOT/logs"
export SITECTL_RUNTIME_EVENTS_LOG="$STATE_ROOT/logs/runtime_events.jsonl"
export SITECTL_RUNTIME_ERRORS_LOG="$STATE_ROOT/logs/runtime_errors.jsonl"
export SITECTL_BROWSER_PROFILE="$DATA_ROOT/browser-profile"
export SITECTL_FIREFOX_PROFILE="$DATA_ROOT/firefox-profile"
export SITECTL_TOKEN_FILE="$CONFIG_ROOT/generated_token.txt"
export SITECTL_LOCAL_CONFIG_PATH="$CONFIG_ROOT/local.yaml"
export TELEGRAM_WORKSPACE_ROOT="$DATA_ROOT/telegram_workspace"
export TELEGRAM_USERS_REGISTRY_FILE="$DATA_ROOT/telegram_workspace/registry/users.json"
export TELEGRAM_API_ACCOUNTS_FILE="$DATA_ROOT/telegram_workspace/registry/api_accounts.json"
export TELEGRAM_MANAGED_HELPER_ROOT="$DATA_ROOT/telegram_workspace/managed_helper"
export TELEGRAM_DEFAULT_OUTPUT_DIR="$DATA_ROOT/reports/telegram_exports"
export TELEGRAM_API_COLLECTOR_PYTHON="$PYTHON_BIN"

exec "$PYTHON_BIN" -m scripts.telegram_username_collector_launcher "$@"
