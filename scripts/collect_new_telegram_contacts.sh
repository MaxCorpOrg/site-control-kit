#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTO_SCRIPT="${SCRIPT_DIR}/auto_collect_usernames.sh"
BATCH_HELPER="${SCRIPT_DIR}/telegram_contact_batches.py"
SAFE_HELPER="${SCRIPT_DIR}/write_telegram_safe_snapshot.py"

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
run_id="$(date -u +%Y%m%dT%H%M%SZ)"
run_dir="${chat_dir}/runs/${run_id}"
export_stats_path="${run_dir}/export_stats.json"

mkdir -p "${chat_dir}"
mkdir -p "${run_dir}"

temp_md="$(mktemp /tmp/telegram_contact_batch.XXXXXX.md)"
temp_txt="${temp_md%.md}_usernames.txt"
backup_latest_full_md=""
backup_latest_full_txt=""
backup_latest_safe_md=""
backup_latest_safe_txt=""
interrupted="0"
partial_review_count="0"
partial_review_path=""
partial_safe_count="0"
partial_safe_md=""
partial_safe_txt=""
latest_full_promoted="1"
latest_full_decision_candidate=""
latest_full_decision_baseline=""
latest_full_best_source=""
latest_safe_promoted="1"
latest_safe_decision_candidate=""
latest_safe_decision_baseline=""
latest_safe_best_source=""

export CHAT_SCROLL_STEPS="${CHAT_SCROLL_STEPS:-12}"
export CHAT_DEEP_LIMIT="${CHAT_DEEP_LIMIT:-40}"
export CHAT_TIMEOUT_SEC="${CHAT_TIMEOUT_SEC:-12}"
export CHAT_MAX_RUNTIME="${CHAT_MAX_RUNTIME:-240}"
export CHAT_DEEP_MODE="${CHAT_DEEP_MODE:-full}"
export CHAT_MIN_MEMBERS="${CHAT_MIN_MEMBERS:-0}"
export CHAT_MAX_MEMBERS="${CHAT_MAX_MEMBERS:-0}"
export CHAT_IDENTITY_HISTORY="${chat_dir}/identity_history.json"
export CHAT_DISCOVERY_STATE="${chat_dir}/discovery_state.json"
export CHAT_STATS_OUTPUT="${export_stats_path}"

cleanup() {
  rm -f "${temp_md}" "${temp_txt}" "${backup_latest_full_md}" "${backup_latest_full_txt}" "${backup_latest_safe_md}" "${backup_latest_safe_txt}"
}
mark_interrupted() {
  interrupted="1"
}
trap mark_interrupted INT TERM
trap cleanup EXIT

extract_usernames_txt() {
  local md_file="$1"
  local txt_file="$2"
  python3 - "$md_file" "$txt_file" <<'PY'
import re
import sys
from pathlib import Path

md = Path(sys.argv[1])
out = Path(sys.argv[2])
text = md.read_text(encoding="utf-8", errors="ignore")
seen = set()
rows = []
for line in text.splitlines():
    m = re.search(r"\|\s*\d+\s*\|.*\|\s*(@[A-Za-z0-9_]{5,32})\s*\|", line)
    if not m:
        continue
    username = m.group(1)
    key = username.lower()
    if key in seen:
        continue
    seen.add(key)
    rows.append(username)
out.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")
PY
}

backup_if_exists() {
  local source_path="$1"
  if [[ ! -f "${source_path}" ]]; then
    return 0
  fi
  local suffix
  suffix=".bak"
  if [[ "${source_path}" == *.md ]]; then
    suffix=".md"
  elif [[ "${source_path}" == *.txt ]]; then
    suffix=".txt"
  fi
  local backup_path
  backup_path="$(mktemp "/tmp/telegram_snapshot_backup.XXXXXX${suffix}")"
  cp "${source_path}" "${backup_path}"
  printf '%s\n' "${backup_path}"
}

snapshot_decision() {
  local candidate_md="$1"
  local baseline_md="$2"
  python3 - "$BATCH_HELPER" "$candidate_md" "$baseline_md" <<'PY'
import importlib.util
import json
import sys
from pathlib import Path

module_path = Path(sys.argv[1]).expanduser()
candidate_path = Path(sys.argv[2]).expanduser()
baseline_path = Path(sys.argv[3]).expanduser()
spec = importlib.util.spec_from_file_location("telegram_contact_batches", module_path)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Unable to load helper module from {module_path}")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

candidate = module.summarize_markdown_snapshot(candidate_path)
baseline = module.summarize_markdown_snapshot(baseline_path if baseline_path.exists() else None)
promote = 1 if (not baseline_path.exists() or module.should_promote_snapshot(candidate, baseline)) else 0
print(f"promote={promote}")
print("candidate=" + json.dumps(candidate, ensure_ascii=False, sort_keys=True))
print("baseline=" + json.dumps(baseline, ensure_ascii=False, sort_keys=True))
PY
}

best_snapshot_source() {
  local latest_md="$1"
  local snapshot_name="$2"
  python3 - "$BATCH_HELPER" "$chat_dir" "$latest_md" "$snapshot_name" <<'PY'
import importlib.util
import json
import sys
from pathlib import Path

module_path = Path(sys.argv[1]).expanduser()
chat_dir = Path(sys.argv[2]).expanduser()
latest_md = Path(sys.argv[3]).expanduser()
snapshot_name = sys.argv[4]
spec = importlib.util.spec_from_file_location("telegram_contact_batches", module_path)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Unable to load helper module from {module_path}")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

paths = []
if latest_md.exists():
    paths.append(latest_md)
paths.extend(sorted((chat_dir / "runs").glob(f"*/{snapshot_name}")))
best_path, best_summary = module.select_best_snapshot(paths)
print(f"path={best_path if best_path else ''}")
print("summary=" + json.dumps(best_summary, ensure_ascii=False, sort_keys=True))
PY
}

prepare_partial_artifacts() {
  partial_review_count="0"
  partial_review_path=""
  partial_safe_count="0"
  partial_safe_md=""
  partial_safe_txt=""

  if [[ ! -s "${temp_md}" ]]; then
    return 1
  fi

  extract_usernames_txt "${temp_md}" "${temp_txt}"
  cp "${temp_md}" "${run_dir}/snapshot.md"
  cp "${temp_txt}" "${run_dir}/snapshot.txt"

  if [[ -f "${SAFE_HELPER}" ]]; then
    local safe_output
    safe_output="$(python3 "${SAFE_HELPER}" --source-md "${temp_md}" --directory "${run_dir}" 2>/dev/null || true)"
    partial_review_count="$(printf '%s\n' "${safe_output}" | sed -n 's/^review_count=//p')"
    partial_review_path="$(printf '%s\n' "${safe_output}" | sed -n 's/^review_path=//p')"
    partial_safe_count="$(printf '%s\n' "${safe_output}" | sed -n 's/^safe_count=//p')"
    partial_safe_md="$(printf '%s\n' "${safe_output}" | sed -n 's/^safe_md=//p')"
    partial_safe_txt="$(printf '%s\n' "${safe_output}" | sed -n 's/^safe_txt=//p')"

    if [[ -n "${partial_safe_md}" && -f "${partial_safe_md}" ]]; then
      cp "${partial_safe_md}" "${run_dir}/snapshot_safe.md"
      partial_safe_md="${run_dir}/snapshot_safe.md"
    fi
    if [[ -n "${partial_safe_txt}" && -f "${partial_safe_txt}" ]]; then
      cp "${partial_safe_txt}" "${run_dir}/snapshot_safe.txt"
      partial_safe_txt="${run_dir}/snapshot_safe.txt"
    fi
  fi
  return 0
}

write_run_json() {
  local status="$1"
  local created_value="$2"
  local count_value="$3"
  local batch_path_value="$4"
  local review_count_value="$5"
  local review_path_value="$6"
  local safe_count_value="$7"
  local safe_md_value="$8"
  local safe_txt_value="$9"
  local exit_code_value="${10}"
  local interrupted_value="${11}"
  python3 - "${run_dir}/run.json" <<PY
import json
import os
import sys

stats_path = ${export_stats_path@Q}
export_stats = {}
if stats_path and os.path.exists(stats_path):
    try:
        with open(stats_path, "r", encoding="utf-8") as fh:
            loaded = json.load(fh)
        if isinstance(loaded, dict):
            export_stats = loaded
    except (OSError, json.JSONDecodeError):
        export_stats = {}

chat_stats = export_stats.get("chat_stats") if isinstance(export_stats.get("chat_stats"), dict) else {}
info_stats = export_stats.get("info_stats") if isinstance(export_stats.get("info_stats"), dict) else {}

payload = {
    "status": ${status@Q},
    "group_url": ${GROUP_URL@Q},
    "chat_dir": ${chat_dir@Q},
    "run_dir": ${run_dir@Q},
    "run_id": ${run_id@Q},
    "scroll_steps": int(${CHAT_SCROLL_STEPS@Q}),
    "deep_limit": int(${CHAT_DEEP_LIMIT@Q}),
    "timeout_sec": int(${CHAT_TIMEOUT_SEC@Q}),
    "max_runtime_sec": int(${CHAT_MAX_RUNTIME@Q}),
    "deep_mode": ${CHAT_DEEP_MODE@Q},
    "min_members": int(${CHAT_MIN_MEMBERS@Q}),
    "max_members": int(${CHAT_MAX_MEMBERS@Q}),
    "identity_history_path": ${CHAT_IDENTITY_HISTORY@Q},
    "discovery_state_path": ${CHAT_DISCOVERY_STATE@Q},
    "created": int(${created_value@Q}),
    "new_usernames": int(${count_value@Q}),
    "batch_path": ${batch_path_value@Q},
    "review_count": int(${review_count_value@Q}),
    "review_path": ${review_path_value@Q},
    "safe_count": int(${safe_count_value@Q}),
    "latest_safe_md": ${safe_md_value@Q},
    "latest_safe_txt": ${safe_txt_value@Q},
    "exit_code": int(${exit_code_value@Q}),
    "interrupted": bool(int(${interrupted_value@Q})),
    "latest_full_promoted": bool(int(${latest_full_promoted@Q})),
    "latest_full_decision_candidate": ${latest_full_decision_candidate@Q},
    "latest_full_decision_baseline": ${latest_full_decision_baseline@Q},
    "latest_full_best_source": ${latest_full_best_source@Q},
    "latest_safe_promoted": bool(int(${latest_safe_promoted@Q})),
    "latest_safe_decision_candidate": ${latest_safe_decision_candidate@Q},
    "latest_safe_decision_baseline": ${latest_safe_decision_baseline@Q},
    "latest_safe_best_source": ${latest_safe_best_source@Q},
    "latest_full_md": ${chat_dir@Q} + "/latest_full.md",
    "latest_full_txt": ${chat_dir@Q} + "/latest_full.txt",
    "snapshot_safe_md": ${run_dir@Q} + "/snapshot_safe.md",
    "snapshot_safe_txt": ${run_dir@Q} + "/snapshot_safe.txt",
    "snapshot_md": ${run_dir@Q} + "/snapshot.md",
    "snapshot_txt": ${run_dir@Q} + "/snapshot.txt",
    "export_log": ${run_dir@Q} + "/export.log",
    "export_stats_path": stats_path if export_stats else "",
    "export_stats_status": str(export_stats.get("status") or ""),
    "unique_members": int(export_stats.get("members_total", 0) or 0),
    "members_with_username": int(export_stats.get("members_with_username", 0) or 0),
    "members_without_username": int(export_stats.get("members_without_username", 0) or 0),
    "deep_attempted_total": int(export_stats.get("deep_attempted_total", 0) or 0),
    "deep_updated_total": int(export_stats.get("deep_updated_total", 0) or 0),
    "history_backfilled_total": int(export_stats.get("history_backfilled_total", 0) or 0),
    "output_usernames_restored_total": int(export_stats.get("output_usernames_restored_total", 0) or 0),
    "output_usernames_cleared_total": int(export_stats.get("output_usernames_cleared_total", 0) or 0),
    "chat_scroll_steps_done": int(chat_stats.get("scroll_steps_done", 0) or 0),
    "chat_burst_scrolls_done": int(chat_stats.get("burst_scrolls_done", 0) or 0),
    "chat_jump_scrolls_done": int(chat_stats.get("jump_scrolls_done", 0) or 0),
    "chat_revisited_view_steps": int(chat_stats.get("revisited_view_steps", 0) or 0),
    "chat_deep_attempted": int(chat_stats.get("deep_attempted", 0) or 0),
    "chat_deep_updated": int(chat_stats.get("deep_updated", 0) or 0),
    "chat_deep_deferred_steps": int(chat_stats.get("deep_deferred_steps", 0) or 0),
    "chat_runtime_limited": int(chat_stats.get("runtime_limited", 0) or 0),
    "info_scroll_steps_done": int(info_stats.get("scroll_steps_done", 0) or 0),
    "info_total_hint": int(info_stats.get("total_hint", 0) or 0),
    "info_deep_attempted": int(info_stats.get("deep_attempted", 0) or 0),
    "info_deep_updated": int(info_stats.get("deep_updated", 0) or 0),
    "chat_stats": chat_stats,
    "info_stats": info_stats,
}
with open(sys.argv[1], "w", encoding="utf-8") as fh:
    json.dump(payload, fh, ensure_ascii=False, indent=2)
    fh.write("\\n")
PY
}

set +e
bash "${AUTO_SCRIPT}" "${GROUP_URL}" "${temp_md}" 2>&1 | tee "${run_dir}/export.log"
pipe_status=("${PIPESTATUS[@]}")
set -e
export_status="${pipe_status[0]:-1}"
tee_status="${pipe_status[1]:-1}"

if [[ "${interrupted}" == "1" || "${export_status}" == "130" || "${export_status}" == "143" ]]; then
  if prepare_partial_artifacts; then
    write_run_json "partial" "0" "0" "" "${partial_review_count:-0}" "${partial_review_path:-}" "${partial_safe_count:-0}" "${partial_safe_md:-}" "${partial_safe_txt:-}" "${export_status:-130}" "1"
    echo "WARN: export interrupted, partial snapshot saved to ${run_dir}" >&2
  else
    write_run_json "partial" "0" "0" "" "0" "" "0" "" "" "${export_status:-130}" "1"
    echo "WARN: export interrupted before snapshot was written" >&2
  fi
  exit 130
fi

if [[ "${export_status}" != "0" || "${tee_status}" != "0" ]]; then
  write_run_json "failed" "0" "0" "" "0" "" "0" "" "" "${export_status:-1}" "0"
  echo "ERROR: export failed, see ${run_dir}/export.log" >&2
  exit 1
fi

backup_latest_full_md="$(backup_if_exists "${chat_dir}/latest_full.md" || true)"
backup_latest_full_txt="$(backup_if_exists "${chat_dir}/latest_full.txt" || true)"
cp "${temp_md}" "${run_dir}/snapshot.md"
cp "${temp_txt}" "${run_dir}/snapshot.txt"

full_decision="$(snapshot_decision "${temp_md}" "${backup_latest_full_md:-/nonexistent}" )"
latest_full_promoted="$(printf '%s\n' "${full_decision}" | sed -n 's/^promote=//p')"
latest_full_decision_candidate="$(printf '%s\n' "${full_decision}" | sed -n 's/^candidate=//p')"
latest_full_decision_baseline="$(printf '%s\n' "${full_decision}" | sed -n 's/^baseline=//p')"

if [[ "${latest_full_promoted}" == "1" ]]; then
  cp "${temp_md}" "${chat_dir}/latest_full.md"
  cp "${temp_txt}" "${chat_dir}/latest_full.txt"
else
  echo "INFO: kept existing latest_full snapshot because current run is weaker"
fi

backup_latest_safe_md="$(backup_if_exists "${chat_dir}/latest_safe.md" || true)"
backup_latest_safe_txt="$(backup_if_exists "${chat_dir}/latest_safe.txt" || true)"
helper_output="$(python3 "${BATCH_HELPER}" --source "${temp_txt}" --directory "${chat_dir}" --full-md "${temp_md}")"

created="$(printf '%s\n' "${helper_output}" | sed -n 's/^created=//p')"
count="$(printf '%s\n' "${helper_output}" | sed -n 's/^count=//p')"
path="$(printf '%s\n' "${helper_output}" | sed -n 's/^path=//p')"
review_count="$(printf '%s\n' "${helper_output}" | sed -n 's/^review_count=//p')"
review_path="$(printf '%s\n' "${helper_output}" | sed -n 's/^review_path=//p')"
safe_count="$(printf '%s\n' "${helper_output}" | sed -n 's/^safe_count=//p')"
safe_md="$(printf '%s\n' "${helper_output}" | sed -n 's/^safe_md=//p')"
safe_txt="$(printf '%s\n' "${helper_output}" | sed -n 's/^safe_txt=//p')"

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
if [[ -n "${safe_txt}" ]]; then
  if [[ -n "${safe_md}" && -f "${safe_md}" ]]; then
    cp "${safe_md}" "${run_dir}/snapshot_safe.md"
  fi
  if [[ -f "${safe_txt}" ]]; then
    cp "${safe_txt}" "${run_dir}/snapshot_safe.txt"
  fi

  safe_decision="$(snapshot_decision "${safe_md}" "${backup_latest_safe_md:-/nonexistent}" )"
  latest_safe_promoted="$(printf '%s\n' "${safe_decision}" | sed -n 's/^promote=//p')"
  latest_safe_decision_candidate="$(printf '%s\n' "${safe_decision}" | sed -n 's/^candidate=//p')"
  latest_safe_decision_baseline="$(printf '%s\n' "${safe_decision}" | sed -n 's/^baseline=//p')"
  if [[ "${latest_safe_promoted}" != "1" ]]; then
    if [[ -n "${backup_latest_safe_md}" && -f "${backup_latest_safe_md}" ]]; then
      cp "${backup_latest_safe_md}" "${chat_dir}/latest_safe.md"
    else
      rm -f "${chat_dir}/latest_safe.md"
    fi
    if [[ -n "${backup_latest_safe_txt}" && -f "${backup_latest_safe_txt}" ]]; then
      cp "${backup_latest_safe_txt}" "${chat_dir}/latest_safe.txt"
    else
      rm -f "${chat_dir}/latest_safe.txt"
    fi
    echo "INFO: kept existing latest_safe snapshot because current run is weaker"
  fi
  echo "  Safe:     ${safe_txt} (${safe_count:-0} username(s))"
fi

latest_full_best_source="${chat_dir}/latest_full.md"
full_best="$(best_snapshot_source "${chat_dir}/latest_full.md" "snapshot.md")"
full_best_path="$(printf '%s\n' "${full_best}" | sed -n 's/^path=//p')"
if [[ -n "${full_best_path}" ]]; then
  latest_full_best_source="${full_best_path}"
  if [[ "${full_best_path}" != "${chat_dir}/latest_full.md" ]]; then
    cp "${full_best_path}" "${chat_dir}/latest_full.md"
    full_best_txt="${full_best_path%/snapshot.md}/snapshot.txt"
    if [[ -f "${full_best_txt}" ]]; then
      cp "${full_best_txt}" "${chat_dir}/latest_full.txt"
    else
      extract_usernames_txt "${full_best_path}" "${chat_dir}/latest_full.txt"
    fi
    echo "INFO: refreshed latest_full snapshot from best run artifact ${full_best_path}"
  fi
fi

latest_safe_best_source="${chat_dir}/latest_safe.md"
safe_best="$(best_snapshot_source "${chat_dir}/latest_safe.md" "snapshot_safe.md")"
safe_best_path="$(printf '%s\n' "${safe_best}" | sed -n 's/^path=//p')"
if [[ -n "${safe_best_path}" ]]; then
  latest_safe_best_source="${safe_best_path}"
  if [[ "${safe_best_path}" != "${chat_dir}/latest_safe.md" ]]; then
    cp "${safe_best_path}" "${chat_dir}/latest_safe.md"
    safe_best_txt="${safe_best_path%/snapshot_safe.md}/snapshot_safe.txt"
    if [[ -f "${safe_best_txt}" ]]; then
      cp "${safe_best_txt}" "${chat_dir}/latest_safe.txt"
    fi
    echo "INFO: refreshed latest_safe snapshot from best run artifact ${safe_best_path}"
  fi
fi

echo "  Run dir:  ${run_dir}"
write_run_json "completed" "${created:-0}" "${count:-0}" "${path:-}" "${review_count:-0}" "${review_path:-}" "${safe_count:-0}" "${safe_md:-}" "${safe_txt:-}" "0" "0"
