#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="${SCRIPT_DIR}/telegram_portable.py"
TITLE="Telegram Portable Import"

require_zenity() {
  if command -v zenity >/dev/null 2>&1; then
    return 0
  fi
  echo "ERROR: zenity is not installed. Install package 'zenity' and rerun." >&2
  exit 1
}

show_output() {
  local title="$1"
  local prefix="$2"
  local output="$3"
  local temp_output
  temp_output="$(mktemp "/tmp/${prefix}.XXXXXX.txt")"
  printf '%s\n' "${output}" >"${temp_output}"
  zenity --text-info --title="${title}" --width=960 --height=720 --filename="${temp_output}" || true
  rm -f "${temp_output}"
}

show_error() {
  local title="$1"
  local message="$2"
  zenity --error --title="${title}" --text="${message}" || true
}

require_zenity

if [[ ! -f "${PYTHON_SCRIPT}" ]]; then
  show_error "${TITLE}" "Скрипт не найден:\n${PYTHON_SCRIPT}"
  exit 1
fi

zip_path="$(zenity --file-selection --title="${TITLE}: выберите zip с tdata")" || exit 0
default_name="$(basename "${zip_path}")"
default_name="${default_name%.zip}"

profile_name="$(
  zenity \
    --entry \
    --title="${TITLE}" \
    --text="Имя профиля. Папка будет создана как ~/TelegramPortable-<имя>." \
    --entry-text="${default_name}"
)" || exit 0

launch_args=()
if zenity --question --title="${TITLE}" --text="Сразу запустить Telegram после импорта?" --ok-label="Запустить" --cancel-label="Только импорт"; then
  launch_args+=(--launch)
fi

if output="$(python3 "${PYTHON_SCRIPT}" import-zip --zip "${zip_path}" --profile-name "${profile_name}" "${launch_args[@]}" 2>&1)"; then
  show_output "${TITLE}" "telegram_portable_gui" "${output}"
  exit 0
fi

rc=$?
show_error "${TITLE}" "Импорт завершился с кодом ${rc}."
show_output "${TITLE} error" "telegram_portable_gui_error" "${output}"
exit "${rc}"
