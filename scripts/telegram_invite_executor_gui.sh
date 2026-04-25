#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMON_GUI="${SCRIPT_DIR}/telegram_invite_gui_common.sh"
EXECUTOR_SCRIPT="${SCRIPT_DIR}/telegram_invite_executor.py"
DEFAULT_JOB_ROOT="${HOME}/telegram_invite_jobs"
TITLE="Telegram Invite Executor"

if [[ ! -f "${COMMON_GUI}" ]]; then
  echo "ERROR: helper script not found: ${COMMON_GUI}" >&2
  exit 1
fi

# shellcheck source=/home/max/site-control-kit/scripts/telegram_invite_gui_common.sh
source "${COMMON_GUI}"

invite_gui_require_zenity
invite_gui_require_script "${TITLE}" "${EXECUTOR_SCRIPT}"

while true; do
  action="$(
    zenity \
      --list \
      --radiolist \
      --title="${TITLE}" \
      --text="Выберите действие:" \
      --column="" \
      --column="Действие" \
      TRUE "configure" \
      FALSE "plan" \
      FALSE "inspect-chat" \
      FALSE "open-chat dry" \
      FALSE "open-chat" \
      FALSE "add-contact dry" \
      FALSE "add-contact prepare" \
      FALSE "add-contact live" \
      FALSE "record" \
      FALSE "report" \
      --height=460 \
      --width=460
  )" || exit 0

  job_dir="$(invite_gui_choose_job_dir "Выберите job directory" "${DEFAULT_JOB_ROOT}")" || continue

  case "${action}" in
    configure)
      invite_link="$(zenity --entry --title="Invite link" --text="Введите invite link или ссылку на чат:" --entry-text="https://t.me/+...")" || continue
      message_template="$(zenity --entry --title="Message template" --text="Шаблон сообщения:" --entry-text="Привет! Вот ссылка для вступления в чат: {invite_link}")" || continue
      note="$(zenity --entry --title="Note" --text="Заметка для execution config:" --entry-text="operator-assisted flow")" || continue
      client_id="$(zenity --entry --title="Client ID" --text="Client ID bridge (можно оставить пустым):" --entry-text="")" || continue
      tab_id="$(zenity --entry --title="Tab ID" --text="Tab ID (можно оставить пустым):" --entry-text="")" || continue
      url_pattern="$(zenity --entry --title="URL pattern" --text="URL pattern для поиска Telegram tab (можно оставить пустым):" --entry-text="web.telegram.org/k/#")" || continue
      requires_approval="$(invite_gui_choose_yes_no "Approval mode" "Этот invite-flow подразумевает join request?" "yes" "no" "yes")" || continue
      active_mode="$(invite_gui_choose_yes_no "Active tab" "Предпочитать активную вкладку при неявном таргетинге?" "yes" "no" "yes")" || continue
      cmd=( "${EXECUTOR_SCRIPT}" configure --job-dir "${job_dir}" --invite-link "${invite_link}" --message-template "${message_template}" --note "${note}" )
      if [[ -n "${client_id}" ]]; then
        cmd+=( --client-id "${client_id}" )
      fi
      if [[ -n "${tab_id}" ]]; then
        cmd+=( --tab-id "${tab_id}" )
      fi
      if [[ -n "${url_pattern}" ]]; then
        cmd+=( --url-pattern "${url_pattern}" )
      fi
      if [[ "${requires_approval}" == "yes" ]]; then
        cmd+=( --requires-approval )
      else
        cmd+=( --no-requires-approval )
      fi
      if [[ "${active_mode}" == "yes" ]]; then
        cmd+=( --active )
      else
        cmd+=( --no-active )
      fi
      ;;
    plan)
      limit="$(zenity --entry --title="Batch size" --text="Сколько пользователей включить в execution-plan?" --entry-text="3")" || continue
      reserve="$(invite_gui_choose_yes_no "Reserve users" "Резервировать пользователей в invite_link_created?" "yes" "no" "no")" || continue
      cmd=( "${EXECUTOR_SCRIPT}" plan --job-dir "${job_dir}" --limit "${limit}" )
      if [[ "${reserve}" == "yes" ]]; then
        cmd+=( --reserve )
      fi
      ;;
    inspect-chat)
      tab_id="$(zenity --entry --title="Tab ID" --text="Tab ID Telegram (можно оставить пустым и использовать config):" --entry-text="")" || continue
      url_pattern="$(zenity --entry --title="URL pattern" --text="URL pattern (можно оставить пустым):" --entry-text="")" || continue
      skip_open="$(invite_gui_choose_yes_no "Skip open" "Чат уже открыт в нужной вкладке?" "yes" "no" "yes")" || continue
      cmd=( "${EXECUTOR_SCRIPT}" inspect-chat --job-dir "${job_dir}" )
      if [[ -n "${tab_id}" ]]; then
        cmd+=( --tab-id "${tab_id}" )
      fi
      if [[ -n "${url_pattern}" ]]; then
        cmd+=( --url-pattern "${url_pattern}" )
      fi
      if [[ "${skip_open}" == "yes" ]]; then
        cmd+=( --skip-open )
      fi
      ;;
    "open-chat dry")
      tab_id="$(zenity --entry --title="Tab ID" --text="Tab ID (можно оставить пустым):" --entry-text="")" || continue
      url_pattern="$(zenity --entry --title="URL pattern" --text="URL pattern (можно оставить пустым):" --entry-text="")" || continue
      cmd=( "${EXECUTOR_SCRIPT}" open-chat --job-dir "${job_dir}" --dry-run )
      if [[ -n "${tab_id}" ]]; then
        cmd+=( --tab-id "${tab_id}" )
      fi
      if [[ -n "${url_pattern}" ]]; then
        cmd+=( --url-pattern "${url_pattern}" )
      fi
      ;;
    "open-chat")
      tab_id="$(zenity --entry --title="Tab ID" --text="Tab ID (можно оставить пустым):" --entry-text="")" || continue
      url_pattern="$(zenity --entry --title="URL pattern" --text="URL pattern (можно оставить пустым):" --entry-text="")" || continue
      cmd=( "${EXECUTOR_SCRIPT}" open-chat --job-dir "${job_dir}" )
      if [[ -n "${tab_id}" ]]; then
        cmd+=( --tab-id "${tab_id}" )
      fi
      if [[ -n "${url_pattern}" ]]; then
        cmd+=( --url-pattern "${url_pattern}" )
      fi
      ;;
    "add-contact dry"|"add-contact prepare"|"add-contact live")
      username="$(zenity --entry --title="Username" --text="Введите username из invite_state.json:" --entry-text="@username")" || continue
      search_query="$(zenity --entry --title="Search query" --text="Поисковая строка Telegram (можно оставить пустой):" --entry-text="")" || continue
      tab_id="$(zenity --entry --title="Tab ID" --text="Tab ID Telegram (можно оставить пустым):" --entry-text="")" || continue
      url_pattern="$(zenity --entry --title="URL pattern" --text="URL pattern (можно оставить пустым):" --entry-text="")" || continue
      skip_open="$(invite_gui_choose_yes_no "Skip open" "Чат уже открыт в нужной вкладке?" "yes" "no" "yes")" || continue
      cmd=( "${EXECUTOR_SCRIPT}" add-contact --job-dir "${job_dir}" --username "${username}" )
      if [[ -n "${search_query}" ]]; then
        cmd+=( --search-query "${search_query}" )
      fi
      if [[ -n "${tab_id}" ]]; then
        cmd+=( --tab-id "${tab_id}" )
      fi
      if [[ -n "${url_pattern}" ]]; then
        cmd+=( --url-pattern "${url_pattern}" )
      fi
      if [[ "${skip_open}" == "yes" ]]; then
        cmd+=( --skip-open )
      fi
      case "${action}" in
        "add-contact dry")
          cmd+=( --dry-run )
          ;;
        "add-contact prepare")
          ;;
        "add-contact live")
          allow_first_result="$(invite_gui_choose_yes_no "Multiple results" "Если Telegram покажет несколько кандидатов, брать первый результат?" "yes" "no" "no")" || continue
          verify_membership="$(invite_gui_choose_yes_no "Verify joined" "Автоматически снять inspect-chat до/после и подтверждать joined только по сильному сигналу?" "yes" "no" "yes")" || continue
          verify_wait=""
          if [[ "${verify_membership}" == "yes" ]]; then
            verify_wait="$(zenity --entry --title="Verify wait" --text="Сколько секунд ждать перед повторной after-проверкой member count?" --entry-text="10")" || continue
          fi
          record_result="$(invite_gui_choose_yes_no "Record result" "После клика Add записать итог в state: joined только при подтверждении, иначе requested?" "yes" "no" "yes")" || continue
          cmd+=( --confirm-add )
          if [[ "${allow_first_result}" == "yes" ]]; then
            cmd+=( --allow-first-result )
          fi
          if [[ "${verify_membership}" == "yes" ]]; then
            cmd+=( --verify-membership )
            if [[ -n "${verify_wait}" ]]; then
              cmd+=( --verify-wait "${verify_wait}" )
            fi
          else
            cmd+=( --no-verify-membership )
          fi
          if [[ "${record_result}" == "yes" ]]; then
            cmd+=( --record-result )
          fi
          ;;
      esac
      ;;
    record)
      username="$(zenity --entry --title="Username" --text="Введите username:" --entry-text="@username")" || continue
      target_status="$(zenity --entry --title="Target status" --text="Целевой статус:" --entry-text="sent")" || continue
      reason="$(zenity --entry --title="Reason" --text="Причина изменения статуса:" --entry-text="execution_record")" || continue
      execution_id="$(zenity --entry --title="Execution ID" --text="Execution ID (можно оставить пустым):" --entry-text="")" || continue
      cmd=( "${EXECUTOR_SCRIPT}" record --job-dir "${job_dir}" --username "${username}" --status "${target_status}" --reason "${reason}" )
      if [[ -n "${execution_id}" ]]; then
        cmd+=( --execution-id "${execution_id}" )
      fi
      ;;
    report)
      limit="$(zenity --entry --title="Preview limit" --text="Сколько пользователей показать в next_execution_batch?" --entry-text="5")" || continue
      cmd=( "${EXECUTOR_SCRIPT}" report --job-dir "${job_dir}" --limit "${limit}" )
      ;;
    *)
      continue
      ;;
  esac

  if ! output="$(invite_gui_run_json "${TITLE}" "${cmd[@]}")"; then
    continue
  fi
  invite_gui_show_output "${TITLE}" "telegram_invite_executor_gui" "${output}"
done
