#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

is_windows_bash() {
  [[ "${OSTYPE:-}" == msys* || "${OSTYPE:-}" == cygwin* || "${OS:-}" == Windows_NT ]]
}

has_real_windows_python3() {
  local python3_path
  python3_path="$(command -v python3 2>/dev/null || true)"
  [[ -n "${python3_path}" ]] || return 1
  case "${python3_path}" in
    */WindowsApps/python3|*/WindowsApps/python3.exe) return 1 ;;
  esac
  return 0
}

if is_windows_bash; then
  if command -v python >/dev/null 2>&1; then
    exec python "${SCRIPT_DIR}/telegram_members_export_gui.py" "$@"
  fi
  if command -v py >/dev/null 2>&1; then
    exec py -3 "${SCRIPT_DIR}/telegram_members_export_gui.py" "$@"
  fi
  if has_real_windows_python3; then
    exec python3 "${SCRIPT_DIR}/telegram_members_export_gui.py" "$@"
  fi
  echo "ERROR: no supported Python launcher found for telegram_members_export_gui on Windows." >&2
  exit 2
fi

exec python3 "${SCRIPT_DIR}/telegram_members_export_gui.py" "$@"
