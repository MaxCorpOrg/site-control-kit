#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANAGER_SCRIPT="${SCRIPT_DIR}/telegram_invite_manager.py"
DEFAULT_JOB_ROOT="${HOME}/telegram_invite_jobs"

if ! command -v zenity >/dev/null 2>&1; then
  echo "ERROR: zenity is not installed. Install package 'zenity' and rerun." >&2
  exit 1
fi

if [[ ! -f "${MANAGER_SCRIPT}" ]]; then
  zenity --error --title="Telegram Invite Manager" --text="Скрипт не найден:\n${MANAGER_SCRIPT}"
  exit 1
fi

run_json() {
  python3 "$@"
}

while true; do
  action="$(
    zenity \
      --list \
      --radiolist \
      --title="Telegram Invite Manager" \
      --text="Выберите действие:" \
      --column="" \
      --column="Действие" \
      TRUE "init" \
      FALSE "status" \
      FALSE "next" \
      FALSE "add user" \
      FALSE "run dry" \
      FALSE "run" \
      FALSE "mark" \
      FALSE "report" \
      --height=360 \
      --width=420
  )" || exit 0

  if [[ "${action}" == "init" ]]; then
    chat_url="$(zenity --entry --title="Chat URL" --text="Введите URL чата Telegram:" --entry-text="https://web.telegram.org/k/#-")" || continue
    input_path="$(zenity --file-selection --title="Выберите CSV/JSON файл")" || continue
    job_dir="$(zenity --file-selection --directory --title="Выберите или создайте каталог job" --filename="${DEFAULT_JOB_ROOT}/")" || continue
    output="$(run_json "${MANAGER_SCRIPT}" init --chat-url "${chat_url}" --input "${input_path}" --job-dir "${job_dir}")"
    zenity --info --title="Telegram Invite Manager" --text="$(printf '%s' "${output}" | sed 's/"/\"/g')"
    continue
  fi

  job_dir="$(zenity --file-selection --directory --title="Выберите job directory" --filename="${DEFAULT_JOB_ROOT}/")" || continue

  case "${action}" in
    status)
      output="$(run_json "${MANAGER_SCRIPT}" status --job-dir "${job_dir}")"
      ;;
    next)
      limit="$(zenity --entry --title="Batch size" --text="Сколько пользователей показать?" --entry-text="3")" || continue
      output="$(run_json "${MANAGER_SCRIPT}" next --job-dir "${job_dir}" --limit "${limit}")"
      ;;
    "add user")
      chat_url="$(zenity --entry --title="Chat URL" --text="Если job новый, укажите URL чата:" --entry-text="https://web.telegram.org/k/#-2465948544")" || continue
      username="$(zenity --entry --title="Username" --text="Введите username пользователя с подтверждённым согласием:" --entry-text="@username")" || continue
      display_name="$(zenity --entry --title="Display name" --text="Имя для заметки:" --entry-text="")" || continue
      note="$(zenity --entry --title="Note" --text="Заметка:" --entry-text="one user invite")" || continue
      source="$(zenity --entry --title="Source" --text="Источник:" --entry-text="manual")" || continue
      output="$(run_json "${MANAGER_SCRIPT}" add-user --job-dir "${job_dir}" --chat-url "${chat_url}" --username "${username}" --display-name "${display_name}" --note "${note}" --source "${source}" --consent yes)"
      ;;
    "run dry")
      limit="$(zenity --entry --title="Batch size" --text="Сколько пользователей взять в dry-run?" --entry-text="3")" || continue
      output="$(run_json "${MANAGER_SCRIPT}" run --job-dir "${job_dir}" --limit "${limit}" --dry-run)"
      ;;
    run)
      limit="$(zenity --entry --title="Batch size" --text="Сколько пользователей обработать?" --entry-text="3")" || continue
      target_status="$(zenity --entry --title="Target status" --text="Целевой статус:" --entry-text="checked")" || continue
      output="$(run_json "${MANAGER_SCRIPT}" run --job-dir "${job_dir}" --limit "${limit}" --to-status "${target_status}")"
      ;;
    mark)
      username="$(zenity --entry --title="Username" --text="Введите username:" --entry-text="@username")" || continue
      target_status="$(zenity --entry --title="Target status" --text="Целевой статус:" --entry-text="sent")" || continue
      reason="$(zenity --entry --title="Reason" --text="Причина изменения статуса:" --entry-text="manual_mark")" || continue
      output="$(run_json "${MANAGER_SCRIPT}" mark --job-dir "${job_dir}" --username "${username}" --status "${target_status}" --reason "${reason}")"
      ;;
    report)
      output="$(run_json "${MANAGER_SCRIPT}" report --job-dir "${job_dir}")"
      ;;
    *)
      continue
      ;;
  esac

  temp_output="$(mktemp /tmp/telegram_invite_manager_gui.XXXXXX.txt)"
  printf '%s\n' "${output}" >"${temp_output}"
  if ! zenity --text-info --title="Telegram Invite Manager" --width=900 --height=700 --filename="${temp_output}"; then
    zenity --info --title="Telegram Invite Manager" --text="$(printf '%s' "${output}" | sed 's/"/\"/g')"
  fi
  rm -f "${temp_output}"
done
