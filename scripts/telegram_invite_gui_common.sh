#!/usr/bin/env bash
set -euo pipefail

invite_gui_require_zenity() {
  if ! command -v zenity >/dev/null 2>&1; then
    echo "ERROR: zenity is not installed. Install package 'zenity' and rerun." >&2
    exit 1
  fi
}

invite_gui_require_script() {
  local title="$1"
  local script_path="$2"
  if [[ -f "${script_path}" ]]; then
    return 0
  fi
  zenity --error --title="${title}" --text="Скрипт не найден:\n${script_path}"
  exit 1
}

invite_gui_show_output() {
  local title="$1"
  local prefix="$2"
  local output="$3"
  local temp_output
  temp_output="$(mktemp "/tmp/${prefix}.XXXXXX.txt")"
  printf '%s\n' "${output}" >"${temp_output}"
  zenity --text-info --title="${title}" --width=960 --height=720 --filename="${temp_output}" || true
  rm -f "${temp_output}"
}

invite_gui_show_error() {
  local title="$1"
  local message="$2"
  zenity --error --title="${title}" --text="${message}" || true
}

invite_gui_run_json() {
  local title="$1"
  shift
  local output
  local rc
  if output="$(python3 "$@" 2>&1)"; then
    printf '%s\n' "${output}"
    return 0
  fi
  rc=$?
  invite_gui_show_error "${title}" "Команда завершилась с кодом ${rc}."
  invite_gui_show_output "${title} error" "invite_gui_error" "${output}"
  return "${rc}"
}

invite_gui_choose_job_dir() {
  local title="$1"
  local default_root="$2"
  zenity --file-selection --directory --title="${title}" --filename="${default_root}/"
}

invite_gui_choose_yes_no() {
  local title="$1"
  local text="$2"
  local true_label="$3"
  local false_label="$4"
  local default_value="$5"
  local first_checked="FALSE"
  local second_checked="FALSE"
  if [[ "${default_value}" == "yes" ]]; then
    first_checked="TRUE"
  else
    second_checked="TRUE"
  fi
  zenity \
    --list \
    --radiolist \
    --title="${title}" \
    --text="${text}" \
    --column="" \
    --column="Режим" \
    "${first_checked}" "${true_label}" \
    "${second_checked}" "${false_label}" \
    --height=240 \
    --width=420
}

