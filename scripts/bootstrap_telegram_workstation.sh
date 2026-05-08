#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKSPACE_ROOT="${TELEGRAM_WORKSPACE_ROOT:-$HOME/.site-control-kit/telegram_workspace}"
MANAGED_HELPER_ROOT="${TELEGRAM_MANAGED_HELPER_ROOT:-$WORKSPACE_ROOT/managed_helper}"
VENV_DIR="$MANAGED_HELPER_ROOT/.venv"
REQ_FILE="$ROOT_DIR/scripts/telegram_helper_requirements.txt"
SYSTEM_PYTHON="${PYTHON_BIN:-python3}"
LEGACY_COLLECTOR_ROOT="${TELEGRAM_API_COLLECTOR_ROOT:-$HOME/telegram-api-collector}"
LEGACY_HELPER_PYTHON="$LEGACY_COLLECTOR_ROOT/.venv/bin/python"

usage() {
  cat <<'EOF'
Usage: scripts/bootstrap_telegram_workstation.sh [--doctor]

--doctor   Print Linux Telegram workstation/bootstrap diagnostics without mutating anything.

Default mode:
- creates managed helper venv inside ~/.site-control-kit/telegram_workspace/managed_helper
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
  if [[ -x "$VENV_DIR/bin/python" ]]; then
    printf 'managed\t%s\n' "$VENV_DIR/bin/python"
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
  printf 'workspace_root=%s\n' "$WORKSPACE_ROOT"
  printf 'managed_helper_root=%s\n' "$MANAGED_HELPER_ROOT"
  printf 'managed_helper_python=%s\n' "$VENV_DIR/bin/python"
  printf 'managed_helper_ready=%s\n' "$([[ -x "$VENV_DIR/bin/python" ]] && echo 1 || echo 0)"
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

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  "$SYSTEM_PYTHON" -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel
"$VENV_DIR/bin/python" -m pip install -r "$REQ_FILE"

print_doctor
