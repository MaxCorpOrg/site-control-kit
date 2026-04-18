#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_ONCE_SCRIPT="${SCRIPT_DIR}/run_chat_export_once.sh"

if ! command -v zenity >/dev/null 2>&1; then
  echo "ERROR: zenity is not installed. Install package 'zenity' and rerun." >&2
  exit 1
fi

if [[ ! -x "${RUN_ONCE_SCRIPT}" ]]; then
  zenity --error \
    --title="Telegram Members Export" \
    --text="Скрипт не найден или не исполняемый:\n${RUN_ONCE_SCRIPT}"
  exit 1
fi

default_group_url="https://web.telegram.org/k/#-"
default_output="${HOME}/Загрузки/Telegram Desktop/MadCoreChat_members_non_pii.md"
default_min_records="20"

chat_steps="${CHAT_SCROLL_STEPS:-60}"
chat_deep_limit="${CHAT_DEEP_LIMIT:-3}"
timeout_sec="${CHAT_TIMEOUT_SEC:-12}"
chat_max_runtime="${CHAT_MAX_RUNTIME:-420}"
chat_deep_mode="${CHAT_DEEP_MODE:-mention}"

detect_token() {
  if [[ -n "${SITECTL_TOKEN:-}" ]]; then
    printf '%s\n' "${SITECTL_TOKEN}"
    return
  fi
  printf '%s\n' "local-bridge-quickstart-2026"
}

is_uint() {
  [[ "${1:-}" =~ ^[0-9]+$ ]]
}

terminate_export() {
  local pid="$1"
  if [[ -z "${pid}" ]]; then
    return
  fi
  kill -TERM -- "-${pid}" >/dev/null 2>&1 || kill -TERM "${pid}" >/dev/null 2>&1 || true
}

run_with_progress() {
  local token="$1"
  local output_path="$2"
  local group_url="$3"
  local min_records="$4"
  local log_file
  local pid
  local rc

  log_file="$(mktemp /tmp/telegram_members_export_gui.XXXXXX.log)"

  setsid bash "${RUN_ONCE_SCRIPT}" \
    "${token}" \
    "${output_path}" \
    "${group_url}" \
    "${chat_steps}" \
    "${chat_deep_limit}" \
    "${timeout_sec}" \
    "${chat_max_runtime}" \
    "${chat_deep_mode}" \
    "${min_records}" >"${log_file}" 2>&1 &
  pid=$!

  set +e
  {
    echo "0"
    echo "# Подготовка экспорта..."
    while kill -0 "${pid}" >/dev/null 2>&1; do
      local last_line
      last_line="$(tail -n 1 "${log_file}" 2>/dev/null | tr -d '\r')"
      if [[ -z "${last_line}" ]]; then
        last_line="Идет сбор участников..."
      fi
      echo "50"
      echo "# ${last_line}"
      sleep 1
    done
    echo "100"
    echo "# Экспорт завершен."
  } | zenity \
    --progress \
    --title="Telegram Members Export" \
    --text="Выполняется экспорт. Нажмите Stop для остановки." \
    --percentage=0 \
    --pulsate \
    --auto-close \
    --cancel-label="Stop" \
    --width=760
  local progress_rc=$?
  set -e

  if [[ "${progress_rc}" -ne 0 ]]; then
    terminate_export "${pid}"
    wait "${pid}" >/dev/null 2>&1 || true
    zenity --warning \
      --title="Telegram Members Export" \
      --text="Экспорт остановлен пользователем."
    rm -f "${log_file}"
    return 130
  fi

  set +e
  wait "${pid}"
  rc=$?
  set -e

  if [[ "${rc}" -eq 0 ]]; then
    zenity --info \
      --title="Telegram Members Export" \
      --text="Готово.\n\nФайл сохранен в:\n${output_path}"
  else
    local err_text
    err_text="$(tail -n 25 "${log_file}")"
    zenity --error \
      --title="Telegram Members Export" \
      --text="Ошибка выгрузки.\n\n${err_text}"
  fi

  rm -f "${log_file}"
  return "${rc}"
}

token="$(detect_token)"
group_url="${default_group_url}"
output_path="${default_output}"
min_records="${default_min_records}"

while true; do
  group_url="$(
    zenity \
      --entry \
      --title="Адрес чата / группы" \
      --text="Вставьте URL из Telegram Web (пример: https://web.telegram.org/k/#-1288116010)" \
      --entry-text="${group_url}"
  )" || exit 0

  if [[ "${group_url}" != *"/#"* ]]; then
    zenity --error \
      --title="Telegram Members Export" \
      --text="Некорректный URL:\n${group_url}\n\nНужен адрес с # и ID/username."
    continue
  fi

  min_records="$(
    zenity \
      --entry \
      --title="Количество записей" \
      --text="Введите минимальное количество записей для chat-режима (0 = без ограничения):" \
      --entry-text="${min_records}"
  )" || exit 0

  if ! is_uint "${min_records}"; then
    zenity --error \
      --title="Telegram Members Export" \
      --text="Количество записей должно быть целым числом >= 0."
    continue
  fi

  output_path="$(
    zenity \
      --file-selection \
      --save \
      --confirm-overwrite \
      --title="Куда сохранить .md файл" \
      --filename="${output_path}"
  )" || exit 0

  if [[ "${output_path}" != *.md ]]; then
    output_path="${output_path}.md"
  fi

  if ! zenity \
    --question \
    --title="Telegram Members Export" \
    --ok-label="Start" \
    --cancel-label="Exit" \
    --text="Запустить экспорт?\n\nURL: ${group_url}\nМин. записей: ${min_records}\nФайл: ${output_path}"; then
    exit 0
  fi

  run_with_progress "${token}" "${output_path}" "${group_url}" "${min_records}" || true

  if ! zenity \
    --question \
    --title="Telegram Members Export" \
    --ok-label="Start Again" \
    --cancel-label="Exit" \
    --text="Запустить еще один экспорт?"; then
    exit 0
  fi
done
