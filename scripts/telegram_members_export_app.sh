#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPORT_SCRIPT="${SCRIPT_DIR}/export_telegram_members_non_pii.py"
START_HUB_SCRIPT="${SCRIPT_DIR}/start_hub.sh"

if ! command -v zenity >/dev/null 2>&1; then
  echo "ERROR: zenity is not installed. Install package 'zenity' and rerun." >&2
  exit 1
fi

if [[ ! -f "${EXPORT_SCRIPT}" ]]; then
  zenity --error --title="Telegram Members Export" --text="Скрипт экспорта не найден:\n${EXPORT_SCRIPT}"
  exit 1
fi

default_server="http://127.0.0.1:8765"
default_group_url="https://web.telegram.org/k/#-"
default_timeout="12"
default_chat_scroll_steps="20"
default_info_scroll_steps="0"
default_chat_deep_limit="10"
default_chat_max_runtime="180"
default_chat_deep_mode="url"
default_output="${HOME}/Загрузки/Telegram Desktop/MadCoreChat_members_non_pii.md"
default_token="local-bridge-quickstart-2026"

detect_token() {
  if [[ -n "${SITECTL_TOKEN:-}" ]]; then
    printf '%s\n' "${SITECTL_TOKEN}"
    return
  fi

  local token_from_process
  token_from_process="$(
    ps -eo args | awk '
      /webcontrol(\.cli)? serve/ {
        for (i = 1; i <= NF; i++) {
          if ($i == "--token" && i < NF) {
            print $(i + 1);
            exit;
          }
        }
      }
    '
  )"
  if [[ -n "${token_from_process}" ]]; then
    printf '%s\n' "${token_from_process}"
    return
  fi

  printf '%s\n' "${default_token}"
}

hub_is_alive() {
  local url="$1"
  curl -fsS "${url}/health" >/dev/null 2>&1
}

list_open_telegram_dialogs() {
  local server_url="$1"
  local access_token="$2"
  python3 - "$server_url" "$access_token" <<'PY'
import json
import sys
from urllib.request import Request, urlopen

server = sys.argv[1].rstrip("/")
token = sys.argv[2]
req = Request(
    f"{server}/api/clients",
    headers={"Accept": "application/json", "X-Access-Token": token},
)
try:
    with urlopen(req, timeout=5) as response:
        data = json.loads(response.read().decode("utf-8"))
except Exception:
    sys.exit(0)

seen_urls = set()
for client in data.get("clients") or []:
    for tab in client.get("tabs") or []:
        url = str(tab.get("url") or "").strip()
        if "web.telegram.org" not in url:
            continue
        if "/#" not in url:
            continue
        if url.endswith("/k/") or url.endswith("/a/"):
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        title = str(tab.get("title") or "").strip() or "(без названия)"
        print(f"{title}\t{url}")
PY
}

server="${default_server}"
token="$(detect_token)"

if ! hub_is_alive "${server}" && [[ -x "${START_HUB_SCRIPT}" ]]; then
  nohup env SITECTL_TOKEN="${token}" bash "${START_HUB_SCRIPT}" >/tmp/telegram_members_export_hub.log 2>&1 &
  sleep 1
fi

if ! hub_is_alive "${server}"; then
  zenity --error --title="Telegram Members Export" --text="Не удалось подключиться к локальному хабу ${server}.\n\nЗапустите хаб и Telegram Web с расширением, затем повторите."
  exit 1
fi

output_path="$(
  zenity \
    --file-selection \
    --save \
    --confirm-overwrite \
    --title="Куда сохранить .md файл" \
    --filename="${default_output}"
)"

if [[ -z "${output_path:-}" ]]; then
  exit 0
fi

mode_choice="$(
  zenity \
    --list \
    --radiolist \
    --title="Режим сбора" \
    --text="Выберите источник участников:" \
    --column="" \
    --column="Режим" \
    TRUE "Взять из инфо группы" \
    FALSE "Взять из чата группы" \
    FALSE "Объединить: чат + инфо" \
    --height=260 \
    --width=420
)"

if [[ -z "${mode_choice:-}" ]]; then
  exit 0
fi

source_mode="info"
if [[ "${mode_choice}" == "Взять из чата группы" ]]; then
  source_mode="chat"
elif [[ "${mode_choice}" == "Объединить: чат + инфо" ]]; then
  source_mode="both"
fi

group_url=""
mapfile -t dialog_rows < <(list_open_telegram_dialogs "${server}" "${token}")
if [[ "${#dialog_rows[@]}" -gt 0 ]]; then
  dialog_args=()
  for row in "${dialog_rows[@]}"; do
    title="${row%%$'\t'*}"
    url="${row#*$'\t'}"
    dialog_args+=("$title" "$url")
  done
  dialog_args+=("Ввести URL вручную" "__manual__")

  selected_url="$(
    zenity \
      --list \
      --title="Выбор чата/группы" \
      --text="Выберите любой открытый чат/группу Telegram:" \
      --column="Чат" \
      --column="URL" \
      --print-column=2 \
      --height=420 \
      --width=980 \
      "${dialog_args[@]}"
  )"
  if [[ -z "${selected_url:-}" ]]; then
    exit 0
  fi
  if [[ "${selected_url}" != "__manual__" ]]; then
    group_url="${selected_url}"
  fi
fi

if [[ -z "${group_url}" ]]; then
  group_url="$(
    zenity \
      --entry \
      --title="URL группы Telegram" \
      --text="Вставьте URL группы/чата из адресной строки Telegram Web (пример: https://web.telegram.org/a/#-2181640359)" \
      --entry-text="${default_group_url}"
  )"
fi

if [[ -z "${group_url:-}" ]]; then
  exit 0
fi

if [[ "${group_url}" != *"/#"* ]]; then
  zenity --error --title="Telegram Members Export" --text="Некорректный URL группы:\n${group_url}\n\nНужен адрес с # и ID/username диалога."
  exit 1
fi

timeout_value="${default_timeout}"
chat_scroll_steps="${default_chat_scroll_steps}"
chat_deep_limit="${default_chat_deep_limit}"
chat_max_runtime="${default_chat_max_runtime}"
chat_deep_mode="${default_chat_deep_mode}"
if [[ "${source_mode}" == "chat" || "${source_mode}" == "both" ]]; then
  run_params="$(
    zenity \
      --entry \
      --title="Параметры сбора" \
      --text="Введите: шаги_скролла|deep_лимит|таймаут_сек|макс_время_чата\nПример: 20|3|12|40" \
      --entry-text "${chat_scroll_steps}|${chat_deep_limit}|${timeout_value}|${chat_max_runtime}"
  )"
  if [[ -z "${run_params:-}" ]]; then
    exit 0
  fi
  IFS='|' read -r chat_scroll_steps chat_deep_limit timeout_value chat_max_runtime <<<"${run_params}"
  [[ "${chat_scroll_steps}" =~ ^[0-9]+$ ]] || chat_scroll_steps="${default_chat_scroll_steps}"
  [[ "${chat_deep_limit}" =~ ^[0-9]+$ ]] || chat_deep_limit="${default_chat_deep_limit}"
  [[ "${timeout_value}" =~ ^[0-9]+$ ]] || timeout_value="${default_timeout}"
  [[ "${chat_max_runtime}" =~ ^[0-9]+$ ]] || chat_max_runtime="${default_chat_max_runtime}"

  deep_mode_choice="$(
    zenity \
      --list \
      --radiolist \
      --title="Режим извлечения @username" \
      --text="Как собирать @username из чата:" \
      --column="" \
      --column="Режим" \
      TRUE "URL (рекомендуется)" \
      FALSE "Полный (URL + профиль)" \
      FALSE "Mention (ПКМ -> Mention)" \
      --height=260 \
      --width=460
  )"
  if [[ -z "${deep_mode_choice:-}" ]]; then
    exit 0
  fi
  if [[ "${deep_mode_choice}" == "Полный (URL + профиль)" ]]; then
    chat_deep_mode="full"
  elif [[ "${deep_mode_choice}" == "Mention (ПКМ -> Mention)" ]]; then
    chat_deep_mode="mention"
  else
    chat_deep_mode="url"
  fi
fi

cmd=(
  python3
  "${EXPORT_SCRIPT}"
  --server "${server}"
  --token "${token}"
  --group-url "${group_url}"
  --timeout "${timeout_value}"
  --output "${output_path}"
  --source "${source_mode}"
)

if [[ "${source_mode}" == "chat" ]]; then
  cmd+=(--chat-scroll-steps "${chat_scroll_steps}")
  cmd+=(--chat-deep-limit "${chat_deep_limit}")
  cmd+=(--chat-max-runtime "${chat_max_runtime}")
  cmd+=(--chat-deep-mode "${chat_deep_mode}")
  cmd+=(--info-scroll-steps "${default_info_scroll_steps}")
  cmd+=(--deep-usernames)
elif [[ "${source_mode}" == "both" ]]; then
  cmd+=(--chat-scroll-steps "${chat_scroll_steps}")
  cmd+=(--chat-deep-limit "${chat_deep_limit}")
  cmd+=(--chat-max-runtime "${chat_max_runtime}")
  cmd+=(--chat-deep-mode "${chat_deep_mode}")
  cmd+=(--info-scroll-steps "${default_info_scroll_steps}")
  cmd+=(--deep-usernames)
else
  cmd+=(--info-scroll-steps "${default_info_scroll_steps}")
  cmd+=(--deep-usernames)
fi

log_file="$(mktemp /tmp/telegram_members_export.XXXXXX.log)"

set +e
"${cmd[@]}" >"${log_file}" 2>&1
exit_code=$?
set -e

if [[ ${exit_code} -eq 0 ]]; then
  zenity --info --title="Telegram Members Export" --text="Готово.\n\nФайл сохранен в:\n${output_path}"
else
  error_text="$(tail -n 25 "${log_file}")"
  zenity --error --title="Telegram Members Export" --text="Ошибка выгрузки.\n\n${error_text}"
fi

rm -f "${log_file}"
exit "${exit_code}"
