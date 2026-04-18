#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPORT_SCRIPT="${SCRIPT_DIR}/export_telegram_members_non_pii.py"
START_HUB_SCRIPT="${SCRIPT_DIR}/start_hub.sh"

if ! command -v zenity >/dev/null 2>&1; then
  echo "ERROR: zenity is not installed. Install package 'zenity' and rerun." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 is not installed." >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "ERROR: curl is not installed." >&2
  exit 1
fi

if [[ ! -f "${EXPORT_SCRIPT}" ]]; then
  zenity --error --title="Telegram Members Export" --text="Скрипт экспорта не найден:\n${EXPORT_SCRIPT}"
  exit 1
fi

default_server="http://127.0.0.1:8765"
default_group_url="https://web.telegram.org/k/#-"
default_timeout="12"
default_chat_scroll_steps="120"
default_chat_deep_limit="60"
default_chat_max_runtime="900"
default_chat_deep_mode="full"
default_target_users="0"
default_output="${HOME}/Загрузки/Telegram Desktop/telegram_usernames.txt"
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

is_uint() {
  [[ "${1:-}" =~ ^[0-9]+$ ]]
}

extract_usernames_from_markdown() {
  local input_md="$1"
  local output_txt="$2"
  python3 - "$input_md" "$output_txt" <<'PY'
import re
import sys
from pathlib import Path

src = Path(sys.argv[1])
dst = Path(sys.argv[2])
text = src.read_text(encoding="utf-8", errors="ignore")
seen = set()
rows = []
for line in text.splitlines():
    match = re.search(r"\|\s*\d+\s*\|.*\|\s*(@[A-Za-z0-9_]{5,32})\s*\|", line)
    if not match:
        continue
    username = match.group(1)
    key = username.lower()
    if key in seen:
        continue
    seen.add(key)
    rows.append(username)
dst.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")
print(len(rows))
PY
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
    --title="Куда сохранить результат (.txt или .md)" \
    --filename="${default_output}"
)"

if [[ -z "${output_path:-}" ]]; then
  exit 0
fi

source_mode="chat"
output_mode="md"
output_path_lower="$(printf '%s' "${output_path}" | tr '[:upper:]' '[:lower:]')"
if [[ "${output_path_lower}" == *.txt ]]; then
  output_mode="txt"
elif [[ "${output_path_lower}" != *.md ]]; then
  output_mode="txt"
  output_path="${output_path}.txt"
fi
mkdir -p "$(dirname "${output_path}")"

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
target_users="${default_target_users}"
run_params="$(
  zenity \
    --entry \
    --title="Параметры сбора чата" \
    --text="Введите: шаги_скролла|deep_лимит|таймаут_сек|макс_время_чата|лимит_пользователей\nПример: 120|60|12|900|0 (0 = без лимита)" \
    --entry-text "${chat_scroll_steps}|${chat_deep_limit}|${timeout_value}|${chat_max_runtime}|${target_users}"
)"
if [[ -z "${run_params:-}" ]]; then
  exit 0
fi
IFS='|' read -r chat_scroll_steps chat_deep_limit timeout_value chat_max_runtime target_users <<<"${run_params}"
is_uint "${chat_scroll_steps}" || chat_scroll_steps="${default_chat_scroll_steps}"
is_uint "${chat_deep_limit}" || chat_deep_limit="${default_chat_deep_limit}"
is_uint "${timeout_value}" || timeout_value="${default_timeout}"
is_uint "${chat_max_runtime}" || chat_max_runtime="${default_chat_max_runtime}"
is_uint "${target_users}" || target_users="${default_target_users}"

deep_mode_choice="$(
  zenity \
    --list \
    --radiolist \
    --title="Режим извлечения @username" \
    --text="Как собирать @username из чата:" \
    --column="" \
    --column="Режим" \
    TRUE "Полный (URL + профиль, максимально полно)" \
    FALSE "Mention (ПКМ -> Mention, быстрее)" \
    FALSE "URL (через профиль URL)" \
    --height=280 \
    --width=560
)"
if [[ -z "${deep_mode_choice:-}" ]]; then
  exit 0
fi
if [[ "${deep_mode_choice}" == "Полный (URL + профиль, максимально полно)" ]]; then
  chat_deep_mode="full"
elif [[ "${deep_mode_choice}" == "URL (через профиль URL)" ]]; then
  chat_deep_mode="url"
else
  chat_deep_mode="mention"
fi

chat_min_members="0"
max_members="0"
if is_uint "${target_users}" && [[ "${target_users}" -gt 0 ]]; then
  chat_min_members="${target_users}"
  max_members="${target_users}"
else
  # Disable early unchanged-stop when user wants "collect all possible from chat".
  chat_min_members="999999999"
fi

export_output_path="${output_path}"
temp_export_path=""
if [[ "${output_mode}" == "txt" ]]; then
  temp_export_path="$(mktemp /tmp/telegram_members_export.XXXXXX.md)"
  export_output_path="${temp_export_path}"
fi

cmd=(
  python3
  "${EXPORT_SCRIPT}"
  --server "${server}"
  --token "${token}"
  --group-url "${group_url}"
  --source "${source_mode}"
  --force-navigate
  --timeout "${timeout_value}"
  --chat-scroll-steps "${chat_scroll_steps}"
  --chat-deep-limit "${chat_deep_limit}"
  --chat-max-runtime "${chat_max_runtime}"
  --chat-deep-mode "${chat_deep_mode}"
  --chat-min-members "${chat_min_members}"
  --max-members "${max_members}"
  --deep-usernames
  --output "${export_output_path}"
)

log_file="$(mktemp /tmp/telegram_members_export.XXXXXX.log)"
cleanup() {
  rm -f "${log_file}"
  if [[ -n "${temp_export_path}" ]]; then
    rm -f "${temp_export_path}"
  fi
}
trap cleanup EXIT

set +e
"${cmd[@]}" >"${log_file}" 2>&1
exit_code=$?
set -e

if [[ ${exit_code} -eq 0 ]]; then
  if [[ "${output_mode}" == "txt" ]]; then
    set +e
    usernames_count="$(extract_usernames_from_markdown "${export_output_path}" "${output_path}")"
    extract_exit_code=$?
    set -e
    if [[ ${extract_exit_code} -ne 0 ]]; then
      zenity --error --title="Telegram Members Export" --text="Экспорт прошел, но не удалось собрать .txt с @username.\nПроверьте лог:\n${log_file}"
      exit 1
    fi
    zenity --info --title="Telegram Members Export" --text="Готово.\n\nСобрано @username: ${usernames_count}\nФайл сохранен в:\n${output_path}"
  else
    zenity --info --title="Telegram Members Export" --text="Готово.\n\nФайл сохранен в:\n${output_path}"
  fi
else
  error_text="$(tail -n 25 "${log_file}")"
  zenity --error --title="Telegram Members Export" --text="Ошибка выгрузки.\n\n${error_text}"
fi

exit "${exit_code}"
