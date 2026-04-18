#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTO_SCRIPT="${SCRIPT_DIR}/auto_collect_usernames.sh"
BATCH_HELPER="${SCRIPT_DIR}/telegram_contact_batches.py"

GROUP_URL="${1:-}"
OUTPUT_ROOT="${2:-${HOME}/telegram_contact_batches}"

if [[ -z "${GROUP_URL}" ]]; then
  echo "ERROR: pass Telegram group URL as first argument" >&2
  echo "Example: $0 'https://web.telegram.org/k/#-2465948544'" >&2
  exit 1
fi

if [[ ! -x "${AUTO_SCRIPT}" ]]; then
  echo "ERROR: auto export script is missing or not executable: ${AUTO_SCRIPT}" >&2
  exit 1
fi

if [[ ! -f "${BATCH_HELPER}" ]]; then
  echo "ERROR: batch helper not found: ${BATCH_HELPER}" >&2
  exit 1
fi

chat_fragment="${GROUP_URL##*#}"
chat_fragment="${chat_fragment:-chat}"
chat_slug="$(printf '%s' "${chat_fragment}" | tr -c 'A-Za-z0-9._-' '_')"
chat_dir="${OUTPUT_ROOT}/chat_${chat_slug}"

mkdir -p "${chat_dir}"

temp_md="$(mktemp /tmp/telegram_contact_batch.XXXXXX.md)"
temp_txt="${temp_md%.md}_usernames.txt"

export CHAT_SCROLL_STEPS="${CHAT_SCROLL_STEPS:-12}"
export CHAT_DEEP_LIMIT="${CHAT_DEEP_LIMIT:-40}"
export CHAT_TIMEOUT_SEC="${CHAT_TIMEOUT_SEC:-12}"
export CHAT_MAX_RUNTIME="${CHAT_MAX_RUNTIME:-240}"
export CHAT_DEEP_MODE="${CHAT_DEEP_MODE:-full}"
export CHAT_MIN_MEMBERS="${CHAT_MIN_MEMBERS:-0}"

cleanup() {
  rm -f "${temp_md}" "${temp_txt}"
}
trap cleanup EXIT

bash "${AUTO_SCRIPT}" "${GROUP_URL}" "${temp_md}"

cp "${temp_md}" "${chat_dir}/latest_full.md"
cp "${temp_txt}" "${chat_dir}/latest_full.txt"

helper_output="$(python3 "${BATCH_HELPER}" --source "${temp_txt}" --directory "${chat_dir}" --full-md "${temp_md}")"

created="$(printf '%s\n' "${helper_output}" | sed -n 's/^created=//p')"
count="$(printf '%s\n' "${helper_output}" | sed -n 's/^count=//p')"
path="$(printf '%s\n' "${helper_output}" | sed -n 's/^path=//p')"
review_count="$(printf '%s\n' "${helper_output}" | sed -n 's/^review_count=//p')"
review_path="$(printf '%s\n' "${helper_output}" | sed -n 's/^review_path=//p')"

if [[ "${created}" == "1" && -n "${path}" ]]; then
  echo "DONE: saved ${count} new usernames"
  echo "  Chat dir: ${chat_dir}"
  echo "  Batch:    ${path}"
  echo "  Latest:   ${chat_dir}/latest_full.txt"
else
  echo "DONE: no new usernames found"
  echo "  Chat dir: ${chat_dir}"
  echo "  Latest:   ${chat_dir}/latest_full.txt"
fi

if [[ -n "${review_count}" && "${review_count}" != "0" && -n "${review_path}" ]]; then
  echo "  Review:   ${review_path} (${review_count} conflict(s))"
fi
