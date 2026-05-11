#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

is_windows_bash() {
  [[ "${OSTYPE:-}" == msys* || "${OSTYPE:-}" == cygwin* || "${OS:-}" == Windows_NT ]]
}

default_python_bin() {
  if is_windows_bash; then
    if command -v python.exe >/dev/null 2>&1; then
      printf 'python.exe\n'
      return 0
    fi
    if command -v py >/dev/null 2>&1; then
      printf 'py -3\n'
      return 0
    fi
  fi
  if command -v python3 >/dev/null 2>&1; then
    printf 'python3\n'
    return 0
  fi
  printf 'python\n'
}

PYTHON_BIN="${PYTHON_BIN:-$(default_python_bin)}"

venv_python_path() {
  local venv_dir="$1"
  if is_windows_bash; then
    printf '%s\n' "$venv_dir/Scripts/python.exe"
    return 0
  fi
  printf '%s\n' "$venv_dir/bin/python"
}

helper_python_path() {
  local helper_root="$1"
  if is_windows_bash; then
    printf '%s\n' "$helper_root/.venv/Scripts/python.exe"
    return 0
  fi
  printf '%s\n' "$helper_root/.venv/bin/python"
}

eval "$("$PYTHON_BIN" -m webcontrol runtime-env --format shell)"

WORKSPACE_ROOT="${TELEGRAM_WORKSPACE_ROOT:-$ROOT_DIR/var/site-control-kit/telegram_workspace}"
MANAGED_HELPER_ROOT="${TELEGRAM_MANAGED_HELPER_ROOT:-$WORKSPACE_ROOT/managed_helper}"
VENV_DIR="$MANAGED_HELPER_ROOT/.venv"
VENV_PYTHON="$(venv_python_path "$VENV_DIR")"
REQ_FILE="$ROOT_DIR/scripts/telegram_helper_requirements.txt"
SYSTEM_PYTHON="$PYTHON_BIN"
LEGACY_COLLECTOR_ROOT="${TELEGRAM_API_COLLECTOR_ROOT:-}"
LEGACY_HELPER_PYTHON=""
if [[ -n "$LEGACY_COLLECTOR_ROOT" ]]; then
  LEGACY_HELPER_PYTHON="$(helper_python_path "$LEGACY_COLLECTOR_ROOT")"
fi

usage() {
  cat <<'EOF'
Usage: scripts/bootstrap_telegram_workstation.sh [--doctor]

--doctor   Print Linux Telegram workstation/bootstrap diagnostics without mutating anything.

Default mode:
- creates managed helper venv inside TELEGRAM_WORKSPACE_ROOT/managed_helper
- installs pinned Telegram helper requirements from scripts/telegram_helper_requirements.txt
- keeps GUI runtime on system Python/GTK
EOF
}

gtk_runtime_state() {
  "$SYSTEM_PYTHON" - <<'PY'
import importlib.util
import sys

if importlib.util.find_spec("gi") is None:
    print("missing")
    raise SystemExit(0)

try:
    import gi
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk  # noqa: F401
except Exception:
    print("broken")
else:
    print("ok")
PY
}

selected_helper() {
  local explicit="${TELEGRAM_API_COLLECTOR_PYTHON:-}"
  if [[ -n "$explicit" && -x "$explicit" ]]; then
    printf 'explicit\t%s\n' "$explicit"
    return 0
  fi
  if [[ -x "$VENV_PYTHON" ]]; then
    printf 'managed\t%s\n' "$VENV_PYTHON"
    return 0
  fi
  if [[ -x "$LEGACY_HELPER_PYTHON" ]]; then
    printf 'legacy\t%s\n' "$LEGACY_HELPER_PYTHON"
    return 0
  fi
  printf 'missing\t-\n'
}

print_doctor() {
  local gtk_state helper_row helper_source helper_python
  gtk_state="$(gtk_runtime_state)"
  helper_row="$(selected_helper)"
  helper_source="${helper_row%%$'\t'*}"
  helper_python="${helper_row#*$'\t'}"
  printf 'runtime_root=%s\n' "${SITECTL_RUNTIME_ROOT:-$ROOT_DIR/var/site-control-kit}"
  printf 'logs_root=%s\n' "${SITECTL_LOG_DIR:-$ROOT_DIR/var/site-control-kit/logs}"
  printf 'reports_root=%s\n' "${SITECTL_REPORTS_ROOT:-$ROOT_DIR/var/site-control-kit/reports}"
  printf 'hub_state_file=%s\n' "${SITECTL_STATE_FILE:-$ROOT_DIR/var/site-control-kit/state/state.json}"
  printf 'runtime_events_log=%s\n' "${SITECTL_RUNTIME_EVENTS_LOG:-$ROOT_DIR/var/site-control-kit/logs/runtime_events.jsonl}"
  printf 'runtime_errors_log=%s\n' "${SITECTL_RUNTIME_ERRORS_LOG:-$ROOT_DIR/var/site-control-kit/logs/runtime_errors.jsonl}"
  printf 'local_config_path=%s\n' "$ROOT_DIR/.site-control-kit/local.yaml"
  printf 'generated_token_file=%s\n' "$ROOT_DIR/.site-control-kit/generated_token.txt"
  printf 'workspace_root=%s\n' "$WORKSPACE_ROOT"
  printf 'managed_helper_root=%s\n' "$MANAGED_HELPER_ROOT"
  printf 'managed_helper_python=%s\n' "$VENV_PYTHON"
  printf 'managed_helper_ready=%s\n' "$([[ -x "$VENV_PYTHON" ]] && echo 1 || echo 0)"
  printf 'requirements_file=%s\n' "$REQ_FILE"
  printf 'requirements_ready=%s\n' "$([[ -f "$REQ_FILE" ]] && echo 1 || echo 0)"
  printf 'system_python=%s\n' "$SYSTEM_PYTHON"
  printf 'gtk_runtime=%s\n' "$gtk_state"
  printf 'selected_helper_source=%s\n' "$helper_source"
  printf 'selected_helper_python=%s\n' "$helper_python"
  printf 'legacy_helper_python=%s\n' "$LEGACY_HELPER_PYTHON"
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ "${1:-}" == "--doctor" ]]; then
  print_doctor
  exit 0
fi

if [[ $# -gt 0 ]]; then
  echo "Unknown argument: $1" >&2
  usage >&2
  exit 1
fi

if ! command -v "$SYSTEM_PYTHON" >/dev/null 2>&1; then
  echo "ERROR: system python not found: $SYSTEM_PYTHON" >&2
  exit 1
fi

if [[ ! -f "$REQ_FILE" ]]; then
  echo "ERROR: helper requirements file not found: $REQ_FILE" >&2
  exit 1
fi

mkdir -p "$MANAGED_HELPER_ROOT"

if [[ ! -x "$VENV_PYTHON" ]]; then
  "$SYSTEM_PYTHON" -m venv "$VENV_DIR"
fi

"$VENV_PYTHON" -m pip install --upgrade pip setuptools wheel
"$VENV_PYTHON" -m pip install -r "$REQ_FILE"

print_doctor
