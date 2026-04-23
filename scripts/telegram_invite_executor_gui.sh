#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXECUTOR_SCRIPT="${SCRIPT_DIR}/telegram_invite_executor.py"
DEFAULT_JOB_ROOT="${HOME}/telegram_invite_jobs"

if ! command -v zenity >/dev/null 2>&1; then
  echo "ERROR: zenity is not installed. Install package 'zenity' and rerun." >&2
  exit 1
fi

if [[ ! -f "${EXECUTOR_SCRIPT}" ]]; then
  zenity --error --title="Telegram Invite Executor" --text="Скрипт не найден:\n${EXECUTOR_SCRIPT}"
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
      --title="Telegram Invite Executor" \
      --text="Выберите действие:" \
      --column="" \
      --column="Действие" \
      TRUE "configure" \
      FALSE "plan" \
      FALSE "open-chat dry" \
      FALSE "record" \
      FALSE "report" \
      --height=320 \
      --width=420
  )" || exit 0

  job_dir="$(zenity --file-selection --directory --title="Выберите job directory" --filename="${DEFAULT_JOB_ROOT}/")" || continue

  case "${action}" in
    configure)
      invite_link="$(zenity --entry --title="Invite link" --text="Введите invite link (можно оставить пустым):" --entry-text="https://t.me/+...")" || continue
      message_template="$(zenity --entry --title="Message template" --text="Шаблон сообщения:" --entry-text="Привет! Вот ссылка для вступления в чат: {invite_link}")" || continue
      url_pattern="$(zenity --entry --title="URL pattern" --text="URL pattern для поиска Telegram tab (можно оставить пустым):" --entry-text="web.telegram.org/k/#")" || continue
      output="$(run_json "${EXECUTOR_SCRIPT}" configure --job-dir "${job_dir}" --invite-link "${invite_link}" --message-template "${message_template}" --url-pattern "${url_pattern}" --requires-approval)"
      ;;
    plan)
      limit="$(zenity --entry --title="Batch size" --text="Сколько пользователей включить в execution-plan?" --entry-text="3")" || continue
      reserve="$(
        zenity \
          --list \
          --radiolist \
          --title="Reserve users" \
          --text="Резервировать пользователей в статус invite_link_created?" \
          --column="" \
          --column="Режим" \
          TRUE "no" \
          FALSE "yes" \
          --height=220 \
          --width=360
      )" || continue
      if [[ "${reserve}" == "yes" ]]; then
        output="$(run_json "${EXECUTOR_SCRIPT}" plan --job-dir "${job_dir}" --limit "${limit}" --reserve)"
      else
        output="$(run_json "${EXECUTOR_SCRIPT}" plan --job-dir "${job_dir}" --limit "${limit}")"
      fi
      ;;
    "open-chat dry")
      output="$(run_json "${EXECUTOR_SCRIPT}" open-chat --job-dir "${job_dir}" --dry-run)"
      ;;
    record)
      username="$(zenity --entry --title="Username" --text="Введите username:" --entry-text="@username")" || continue
      target_status="$(zenity --entry --title="Target status" --text="Целевой статус:" --entry-text="sent")" || continue
      reason="$(zenity --entry --title="Reason" --text="Причина изменения статуса:" --entry-text="execution_record")" || continue
      execution_id="$(zenity --entry --title="Execution ID" --text="Execution ID (можно оставить пустым):" --entry-text="")" || continue
      if [[ -n "${execution_id}" ]]; then
        output="$(run_json "${EXECUTOR_SCRIPT}" record --job-dir "${job_dir}" --username "${username}" --status "${target_status}" --reason "${reason}" --execution-id "${execution_id}")"
      else
        output="$(run_json "${EXECUTOR_SCRIPT}" record --job-dir "${job_dir}" --username "${username}" --status "${target_status}" --reason "${reason}")"
      fi
      ;;
    report)
      output="$(run_json "${EXECUTOR_SCRIPT}" report --job-dir "${job_dir}")"
      ;;
    *)
      continue
      ;;
  esac

  temp_output="$(mktemp /tmp/telegram_invite_executor_gui.XXXXXX.txt)"
  printf '%s\n' "${output}" >"${temp_output}"
  if ! zenity --text-info --title="Telegram Invite Executor" --width=900 --height=700 --filename="${temp_output}"; then
    zenity --info --title="Telegram Invite Executor" --text="$(printf '%s' "${output}" | sed 's/"/\"/g')"
  fi
  rm -f "${temp_output}"
done
