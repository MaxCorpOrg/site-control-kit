#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMON_GUI="${SCRIPT_DIR}/telegram_invite_gui_common.sh"
MANAGER_SCRIPT="${SCRIPT_DIR}/telegram_invite_manager.py"
DEFAULT_JOB_ROOT="${HOME}/telegram_invite_jobs"
TITLE="Telegram Invite Manager"

if [[ ! -f "${COMMON_GUI}" ]]; then
  echo "ERROR: helper script not found: ${COMMON_GUI}" >&2
  exit 1
fi

# shellcheck source=/home/max/site-control-kit/scripts/telegram_invite_gui_common.sh
source "${COMMON_GUI}"

invite_gui_require_zenity
invite_gui_require_script "${TITLE}" "${MANAGER_SCRIPT}"

while true; do
  action="$(
    zenity \
      --list \
      --radiolist \
      --title="${TITLE}" \
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
      --height=380 \
      --width=440
  )" || exit 0

  if [[ "${action}" == "init" ]]; then
    chat_url="$(zenity --entry --title="Chat URL" --text="Введите URL чата Telegram:" --entry-text="https://web.telegram.org/k/#-")" || continue
    input_path="$(zenity --file-selection --title="Выберите CSV или JSON файл")" || continue
    job_dir="$(invite_gui_choose_job_dir "Выберите или создайте каталог job" "${DEFAULT_JOB_ROOT}")" || continue
    cmd=( "${MANAGER_SCRIPT}" init --chat-url "${chat_url}" --input "${input_path}" --job-dir "${job_dir}" )
    if ! output="$(invite_gui_run_json "${TITLE}" "${cmd[@]}")"; then
      continue
    fi
    invite_gui_show_output "${TITLE}" "telegram_invite_manager_gui" "${output}"
    continue
  fi

  job_dir="$(invite_gui_choose_job_dir "Выберите job directory" "${DEFAULT_JOB_ROOT}")" || continue

  case "${action}" in
    status)
      cmd=( "${MANAGER_SCRIPT}" status --job-dir "${job_dir}" )
      ;;
    next)
      limit="$(zenity --entry --title="Batch size" --text="Сколько пользователей показать?" --entry-text="3")" || continue
      cmd=( "${MANAGER_SCRIPT}" next --job-dir "${job_dir}" --limit "${limit}" )
      ;;
    "add user")
      chat_url="$(zenity --entry --title="Chat URL" --text="Если job новый, укажите URL чата:" --entry-text="https://web.telegram.org/k/#-2465948544")" || continue
      username="$(zenity --entry --title="Username" --text="Введите username пользователя с подтверждённым согласием:" --entry-text="@username")" || continue
      display_name="$(zenity --entry --title="Display name" --text="Имя для заметки:" --entry-text="")" || continue
      note="$(zenity --entry --title="Note" --text="Заметка:" --entry-text="one user invite")" || continue
      source_name="$(zenity --entry --title="Source" --text="Источник:" --entry-text="manual")" || continue
      cmd=(
        "${MANAGER_SCRIPT}" add-user
        --job-dir "${job_dir}"
        --chat-url "${chat_url}"
        --username "${username}"
        --display-name "${display_name}"
        --note "${note}"
        --source "${source_name}"
        --consent yes
      )
      ;;
    "run dry")
      limit="$(zenity --entry --title="Batch size" --text="Сколько пользователей взять в dry-run?" --entry-text="3")" || continue
      target_status="$(zenity --entry --title="Target status" --text="Во что dry-run должен переводить пользователей?" --entry-text="checked")" || continue
      cmd=( "${MANAGER_SCRIPT}" run --job-dir "${job_dir}" --limit "${limit}" --to-status "${target_status}" --dry-run )
      ;;
    run)
      limit="$(zenity --entry --title="Batch size" --text="Сколько пользователей обработать?" --entry-text="3")" || continue
      target_status="$(zenity --entry --title="Target status" --text="Целевой статус:" --entry-text="checked")" || continue
      cmd=( "${MANAGER_SCRIPT}" run --job-dir "${job_dir}" --limit "${limit}" --to-status "${target_status}" )
      ;;
    mark)
      username="$(zenity --entry --title="Username" --text="Введите username:" --entry-text="@username")" || continue
      target_status="$(zenity --entry --title="Target status" --text="Целевой статус:" --entry-text="sent")" || continue
      reason="$(zenity --entry --title="Reason" --text="Причина изменения статуса:" --entry-text="manual_mark")" || continue
      cmd=( "${MANAGER_SCRIPT}" mark --job-dir "${job_dir}" --username "${username}" --status "${target_status}" --reason "${reason}" )
      ;;
    report)
      cmd=( "${MANAGER_SCRIPT}" report --job-dir "${job_dir}" )
      ;;
    *)
      continue
      ;;
  esac

  if ! output="$(invite_gui_run_json "${TITLE}" "${cmd[@]}")"; then
    continue
  fi
  invite_gui_show_output "${TITLE}" "telegram_invite_manager_gui" "${output}"
done
