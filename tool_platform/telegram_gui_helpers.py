from __future__ import annotations

from collections import Counter
import csv
from datetime import datetime, timezone
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .telegram_runtime import (
    LEGACY_INVITE_JOBS_ROOT,
    combined_flow_state_root,
    display_path,
    invite_jobs_root,
    panel_log_path,
    preferred_read_path,
    repo_root,
    runtime_config_root,
    session_configs_root,
    session_repo_example_config,
    session_repo_root,
    session_repo_runs_root,
    session_repo_state_file,
    session_runs_root,
    session_state_file,
)
from .workflows import (
    DEFAULT_WORKFLOW_STATE_ROOT,
    combined_state_from_jobs,
    combined_flow_state_path as persistent_combined_flow_state_path,
    migrate_legacy_combined_state,
)


DEFAULT_INVITE_SCRIPT = repo_root() / "scripts" / "telegram_invite_manager.py"
DEFAULT_INVITE_EXECUTOR_SCRIPT = repo_root() / "scripts" / "telegram_invite_executor.py"
DEFAULT_INVITE_OUTPUT_ROOT = invite_jobs_root()
DEFAULT_SESSION_REPO = session_repo_root()
DEFAULT_SESSION_CONFIG = session_configs_root() / "session.example.json"
DEFAULT_SESSION_STATE_FILE = session_state_file()
DEFAULT_SESSION_RUNS_DIR = session_runs_root()
DEFAULT_PANEL_STATE_ROOT = DEFAULT_WORKFLOW_STATE_ROOT
DEFAULT_RUNTIME_CONFIG_ROOT = runtime_config_root()
USERNAME_RE = re.compile(r"^@?[A-Za-z0-9_]{5,32}$")
CONTACT_PENDING_STATUSES = {"new", "checked"}
CONTACT_SUCCESS_STATUSES = {"contact_added"}
CONTACT_ERROR_STATUSES = {"failed"}
COMBINED_PHASES = {"contact_add", "review", "session_ready", "session_running", "stopped"}


@dataclass(frozen=True)
class CommandSpec:
    argv: list[str]
    cwd: Path


def _load_json_file(path: str | Path) -> Any:
    return json.loads(Path(path).expanduser().resolve().read_text(encoding="utf-8"))


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_utc_timestamp(value: Any) -> datetime | None:
    raw_value = str(value or "").strip()
    if not raw_value:
        return None
    try:
        return datetime.fromisoformat(raw_value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _elapsed_seconds_from_timestamps(started_at: Any, completed_at: Any) -> int | None:
    started = _parse_utc_timestamp(started_at)
    completed = _parse_utc_timestamp(completed_at)
    if started is None or completed is None:
        return None
    return max(int((completed - started).total_seconds()), 0)


def _invite_rate_per_minute(processed_count: int, elapsed_seconds: int | None) -> float | None:
    if processed_count <= 0 or elapsed_seconds is None or elapsed_seconds <= 0:
        return None
    return round((float(processed_count) * 60.0) / float(elapsed_seconds), 2)


def _invite_progress_summary_from_payload(payload: dict[str, Any], *, history_source: str) -> dict[str, Any]:
    selected_target = _safe_int(payload.get("selected_target") or payload.get("selected_users"))
    processed_count = _safe_int(payload.get("processed_count") or len(payload.get("results") or []))
    remaining_in_run = _safe_int(payload.get("remaining_in_run"), default=max(selected_target - processed_count, 0))
    queue_remaining_total = _safe_int(payload.get("queue_remaining_total") or payload.get("remaining_candidates"))
    elapsed_seconds = _safe_int(payload.get("elapsed_seconds"), default=-1)
    if elapsed_seconds < 0:
        elapsed_seconds = _elapsed_seconds_from_timestamps(payload.get("started_at"), payload.get("completed_at")) or 0
    rate_per_minute = payload.get("rate_per_minute")
    if rate_per_minute in {"", None}:
        rate_per_minute = _invite_rate_per_minute(processed_count, elapsed_seconds)
    else:
        rate_per_minute = _safe_float(rate_per_minute, 0.0)
        if rate_per_minute <= 0:
            rate_per_minute = None
    eta_seconds: int | None
    if rate_per_minute and rate_per_minute > 0 and remaining_in_run > 0:
        eta_seconds = max(int(round((float(remaining_in_run) * 60.0) / float(rate_per_minute))), 0)
    else:
        eta_seconds = None
    return {
        "status": str(payload.get("status") or "").strip() or "unknown",
        "history_source": history_source,
        "started_at": str(payload.get("started_at") or "").strip(),
        "completed_at": str(payload.get("completed_at") or "").strip(),
        "elapsed_seconds": max(elapsed_seconds, 0),
        "selected_target": selected_target,
        "processed_count": processed_count,
        "remaining_in_run": remaining_in_run,
        "queue_remaining_total": queue_remaining_total,
        "added_count": _safe_int(payload.get("added_count")),
        "already_present_count": _safe_int(payload.get("already_present_count")),
        "failed_count": _safe_int(payload.get("failed_count")),
        "rate_per_minute": rate_per_minute,
        "eta_seconds": eta_seconds,
        "current_username": str(payload.get("current_username") or "").strip(),
        "last_outcome": str(payload.get("last_outcome") or "").strip(),
        "execution_id": str(payload.get("execution_id") or "").strip(),
    }


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_profile_workspace_details(
    profile: dict[str, Any],
    workspace: dict[str, Any],
    *,
    attach_summary: str,
    attach_message: str,
    workflow_line_formatter: Callable[[dict[str, Any]], str],
) -> str:
    health = workspace.get("health") if isinstance(workspace.get("health"), dict) else {}
    lock = workspace.get("current_lock") if isinstance(workspace.get("current_lock"), dict) else None
    workflow_buckets = workspace.get("workflow_buckets") if isinstance(workspace.get("workflow_buckets"), dict) else {}
    active_bucket = next(
        (
            bucket
            for bucket in workflow_buckets.values()
            if isinstance(bucket, dict) and isinstance(bucket.get("active_job"), dict)
        ),
        None,
    )
    recoverable_bucket = next(
        (
            bucket
            for bucket in workflow_buckets.values()
            if isinstance(bucket, dict) and isinstance(bucket.get("recoverable_job"), dict)
        ),
        None,
    )
    lines = [
        "",
        "Workspace",
        f"Профиль ID: {workspace.get('profile_id') or '-'}",
        f"Активных jobs: {len(workspace.get('active_jobs') or [])}",
        f"Последних jobs: {len(workspace.get('recent_jobs') or [])}",
        f"Текущая ОС: {health.get('platform_id') or '-'}",
        f"Profile runtime: {'запущен' if health.get('profile_running') else 'остановлен'}",
        f"Attach: {attach_summary}",
        f"Window automation: {'доступно' if health.get('window_automation_available') else 'недоступно'}",
        f"Accessibility: {'доступно' if health.get('accessibility_available') else 'недоступно'}",
        f"Session runtime: {'доступен' if health.get('session_runtime_reachable') else 'недоступен'}",
    ]
    if attach_message:
        lines.append(f"Attach detail: {attach_message}")
    if lock:
        lines.append(f"Lock: {lock.get('owner_tool_id') or '-'} · job {lock.get('job_id') or '-'}")
    else:
        lines.append("Lock: свободен")
    if isinstance(active_bucket, dict) and isinstance(active_bucket.get("active_job"), dict):
        lines.append(f"Активный workflow: {workflow_line_formatter(active_bucket['active_job'])}")
    else:
        lines.append("Активный workflow: нет")
    if isinstance(recoverable_bucket, dict) and isinstance(recoverable_bucket.get("recoverable_job"), dict):
        lines.append(f"Recoverable workflow: {workflow_line_formatter(recoverable_bucket['recoverable_job'])}")
    else:
        lines.append("Recoverable workflow: нет")
    last_success = workspace.get("last_successful_job") if isinstance(workspace.get("last_successful_job"), dict) else {}
    if last_success:
        lines.append(
            f"Последний успешный job: {last_success.get('tool_id') or '-'} · {last_success.get('status') or '-'}"
        )
    active_jobs = workspace.get("active_jobs") if isinstance(workspace.get("active_jobs"), list) else []
    if active_jobs:
        lines.extend(["", "Активные jobs"])
        for item in active_jobs[:4]:
            lines.append(workflow_line_formatter(item))
    recent_jobs = workspace.get("recent_jobs") if isinstance(workspace.get("recent_jobs"), list) else []
    if recent_jobs:
        lines.extend(["", "Последние jobs"])
        for item in recent_jobs[:4]:
            lines.append(workflow_line_formatter(item))
    artifact_index = workspace.get("artifact_index") if isinstance(workspace.get("artifact_index"), dict) else {}
    if artifact_index:
        lines.extend(["", "Последние артефакты"])
        for key, value in sorted(artifact_index.items()):
            lines.append(f"- {key}: {display_path(value)}")
    return "\n".join(lines)


def build_profile_workspace_summary(
    profile: dict[str, Any],
    workspace: dict[str, Any],
    *,
    attach_summary: str,
    attach_message: str,
    workflow_line_formatter: Callable[[dict[str, Any]], str],
    resume_hint: str,
) -> str:
    account = profile.get("account") if isinstance(profile.get("account"), dict) else {}
    windows = profile.get("attach_candidates") if isinstance(profile.get("attach_candidates"), list) else []
    if not windows:
        windows = profile.get("windows") if isinstance(profile.get("windows"), list) else []
    first_window = windows[0] if windows else {}
    profile_name = str(profile.get("profile_name") or "").strip() or "profile"
    profile_dir = str(profile.get("profile_dir") or "").strip()
    active_job = workspace.get("active_workflow") if isinstance(workspace.get("active_workflow"), dict) else None
    recoverable_job = workspace.get("recoverable_workflow") if isinstance(workspace.get("recoverable_workflow"), dict) else None
    lock = workspace.get("current_lock") if isinstance(workspace.get("current_lock"), dict) else None
    last_success = workspace.get("last_successful_job") if isinstance(workspace.get("last_successful_job"), dict) else None
    lines = [
        "Профиль и workflow",
        f"Профиль: {profile_name}",
        f"Аккаунт: {account.get('username') or 'не задан'}",
        f"Метка: {account.get('label') or 'не задана'}",
        f"Состояние: {'запущен' if profile.get('running') else 'остановлен'}",
        f"Attach: {attach_summary}",
        f"Окно: {first_window.get('title') or 'недоступно'}",
        f"Папка профиля: {display_path(profile_dir) if profile_dir else '-'}",
        "",
        f"Активный workflow: {workflow_line_formatter(active_job) if active_job else 'нет'}",
        f"Recoverable workflow: {workflow_line_formatter(recoverable_job) if recoverable_job else 'нет'}",
        f"Подсказка resume: {str(workspace.get('resume_hint') or resume_hint)}",
        f"Очередь invite: {str(workspace.get('continue_queue_hint') or 'нет данных')}",
        f"Ошибки invite: {str(workspace.get('retry_failed_hint') or 'нет данных')}",
        f"Следующее действие: {str(workspace.get('next_operator_action') or 'не определено')}",
    ]
    if lock:
        lines.append(f"Lock: {lock.get('owner_tool_id') or '-'} · job {lock.get('job_id') or '-'}")
    else:
        lines.append("Lock: свободен")
    if attach_message:
        lines.append(f"Подсказка attach: {attach_message}")
    if last_success:
        lines.append(f"Последний успешный workflow: {workflow_line_formatter(last_success)}")
    profile_dir = str(profile.get("profile_dir") or "").strip()
    if profile_dir:
        lines.extend(
            [
                "",
                "Где лежат данные",
                f"Профиль: {display_path(profile_dir)}",
                f"Runtime root: {display_path(invite_jobs_root().parent)}",
            ]
        )
    return "\n".join(lines)


def build_profile_workspace_history(
    workspace: dict[str, Any],
    *,
    workflow_line_formatter: Callable[[dict[str, Any]], str],
) -> str:
    def _safe_index(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _session_lines(session_summary: dict[str, Any], *, prefix: str) -> list[str]:
        if not isinstance(session_summary, dict) or not session_summary:
            return []
        lines = [
            prefix
            + (
                f"run {session_summary.get('run_id') or '-'} · "
                f"визитов {session_summary.get('visit_count') or 0} · "
                f"сообщений {session_summary.get('message_count') or 0} · "
                f"отправлено {session_summary.get('sent_count') or 0} · "
                f"черновиков {session_summary.get('draft_count') or 0} · "
                f"адресат {session_summary.get('message_target_username') or 'не выбран'}"
            )
        ]
        sent_messages = session_summary.get("sent_messages") if isinstance(session_summary.get("sent_messages"), list) else []
        draft_messages = session_summary.get("draft_messages") if isinstance(session_summary.get("draft_messages"), list) else []
        if sent_messages:
            lines.append(prefix + "sent: " + " | ".join(str(item).strip() for item in sent_messages if str(item).strip()))
        if draft_messages:
            lines.append(prefix + "draft: " + " | ".join(str(item).strip() for item in draft_messages if str(item).strip()))
        return lines

    groups = workspace.get("history_groups") if isinstance(workspace.get("history_groups"), list) else []
    lines = ["История профиля"]
    if not groups:
        lines.append("Для этого профиля пока нет unified workflow history.")
        return "\n".join(lines)
    for group in groups:
        job = group.get("job") if isinstance(group.get("job"), dict) else {}
        steps = group.get("steps") if isinstance(group.get("steps"), list) else []
        lines.extend(["", workflow_line_formatter(job)])
        lines.extend(_session_lines(job.get("session_summary") if isinstance(job.get("session_summary"), dict) else {}, prefix="  "))
        if not steps:
            lines.append("  Child steps пока не зафиксированы.")
            continue
        for step in steps:
            started_at = str(step.get("started_at") or "").strip() or "-"
            completed_at = str(step.get("completed_at") or "").strip() or "..."
            lines.append(
                "  "
                + f"#{_safe_index(step.get('step_index')) + 1} · "
                + f"{step.get('step_code') or '-'} · "
                + f"{step.get('step_kind') or '-'} · "
                + f"{step.get('status') or '-'} · "
                + f"{str(step.get('summary') or '').strip() or '-'} · "
                + f"{started_at} -> {completed_at}"
            )
            lines.extend(_session_lines(step.get("session_summary") if isinstance(step.get("session_summary"), dict) else {}, prefix="    "))
    return "\n".join(lines)


def build_artifact_center_text(
    artifact_index: dict[str, Any] | list[dict[str, Any]] | None,
) -> str:
    lines = ["Artifact center"]
    if isinstance(artifact_index, list):
        for item in artifact_index:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or item.get("artifact_kind") or "Артефакт").strip()
            value = str(item.get("path") or "").strip()
            lines.append(f"- {label}: {display_path(value) if value else 'пока нет'}")
        return "\n".join(lines)
    artifacts = artifact_index if isinstance(artifact_index, dict) else {}
    previews = [
        ("Последний batch json", artifacts.get("batch_json") or artifacts.get("job_dir") or ""),
        ("Последний session run", artifacts.get("session_run") or artifacts.get("run_dir") or ""),
        ("Последний execution record", artifacts.get("execution_record") or artifacts.get("job_dir") or ""),
        ("Последний screenshot", artifacts.get("screenshot_path") or artifacts.get("run_dir") or ""),
        ("Лог панели", str(panel_log_path())),
    ]
    for label, value in previews:
        lines.append(f"- {label}: {display_path(value) if value else 'пока нет'}")
    return "\n".join(lines)


def build_profile_workspace_artifacts_health(
    profile: dict[str, Any],
    workspace: dict[str, Any],
    *,
    attach_summary: str,
    attach_message: str,
    artifact_center_formatter: Callable[[dict[str, Any] | list[dict[str, Any]] | None], str],
) -> str:
    health = workspace.get("health") if isinstance(workspace.get("health"), dict) else {}
    artifacts = workspace.get("artifact_center") if isinstance(workspace.get("artifact_center"), list) else workspace.get("artifact_shortcuts")
    artifact_history = workspace.get("artifact_history") if isinstance(workspace.get("artifact_history"), list) else []
    lines = [
        "Артефакты и здоровье",
        "",
        "Здоровье профиля",
        f"- Profile runtime: {'запущен' if health.get('profile_running') else 'остановлен'}",
        f"- Window automation: {'доступно' if health.get('window_automation_available') else 'недоступно'}",
        f"- Accessibility: {'доступно' if health.get('accessibility_available') else 'недоступно'}",
        f"- Session runtime: {'доступен' if health.get('session_runtime_reachable') else 'недоступен'}",
        f"- Panel/backend: {health.get('panel_backend_status') or '-'}",
        f"- Attach: {attach_summary}",
        "",
        artifact_center_formatter(artifacts),
    ]
    if attach_message:
        lines.extend(["", f"Attach detail: {attach_message}"])
    if artifact_history:
        lines.extend(["", "История артефактов"])
        for item in artifact_history[:8]:
            lines.append(
                f"- {item.get('label') or item.get('artifact_kind') or '-'} · "
                f"{item.get('workflow_kind') or '-'} · "
                f"{item.get('status') or '-'} · "
                f"{item.get('updated_at') or '-'}"
            )
            lines.append(f"  {display_path(item.get('path') or '-')}")
    profile_dir = str(profile.get("profile_dir") or "").strip()
    if profile_dir:
        lines.extend(
            [
                "",
                "Где лежат данные",
                f"- Профиль: {display_path(profile_dir)}",
                f"- Runtime root: {display_path(invite_jobs_root().parent)}",
            ]
        )
    return "\n".join(lines)


def build_profile_manager_selected_text(
    *,
    profile: dict[str, Any],
    workspace: dict[str, Any] | None,
    attach_summary: str,
    attach_message: str,
) -> str:
    account = profile.get("account") if isinstance(profile.get("account"), dict) else {}
    first_window = {}
    candidates = profile.get("attach_candidates") if isinstance(profile.get("attach_candidates"), list) else []
    if candidates:
        first_window = candidates[0] if isinstance(candidates[0], dict) else {}
    elif isinstance(profile.get("windows"), list) and profile.get("windows"):
        candidate = profile.get("windows")[0]
        if isinstance(candidate, dict):
            first_window = candidate
    lines = [
        "Выбранный аккаунт",
        f"Профиль: {profile.get('profile_name') or 'неизвестно'}",
        f"Аккаунт: {account.get('label') or account.get('username') or 'не задан'}",
        f"Состояние: {'запущен' if profile.get('running') else 'остановлен'}",
        f"Attach: {attach_summary}",
        f"Окно: {first_window.get('title') or 'недоступно'}",
        "",
        "Что делать дальше",
        f"- {str((workspace or {}).get('next_operator_action') or 'Подготовь и запусти нужный workflow.')}",
        f"- Очередь invite: {str((workspace or {}).get('continue_queue_hint') or 'нет данных')}",
        f"- Ошибки invite: {str((workspace or {}).get('retry_failed_hint') or 'нет данных')}",
        "",
        "Где лежат данные",
        f"- Папка профиля: {display_path(profile.get('profile_dir') or '-') if profile.get('profile_dir') else '-'}",
        f"- Лог Telegram: {display_path(profile.get('telegram_log_path') or '-') if profile.get('telegram_log_path') else '-'}",
        f"- Runtime root: {display_path(invite_jobs_root().parent)}",
    ]
    if attach_message:
        lines.extend(["", f"Подсказка attach: {attach_message}"])
    active_job = (workspace or {}).get("active_workflow") if isinstance((workspace or {}).get("active_workflow"), dict) else None
    if active_job:
        lines.extend(
            [
                "",
                "Активный workflow",
                f"- {active_job.get('workflow_kind') or active_job.get('tool_id') or '-'} · {active_job.get('status') or '-'} · {active_job.get('summary') or '-'}",
            ]
        )
    return "\n".join(lines)


def format_seconds_hms(value: Any) -> str:
    try:
        total_seconds = max(int(float(value)), 0)
    except (TypeError, ValueError):
        total_seconds = 0
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _rate_text(value: Any) -> str:
    try:
        rate = float(value)
    except (TypeError, ValueError):
        return "н/д"
    return f"{rate:.2f}/мин"


def _artifact_line(label: str, key: str, artifacts: dict[str, Any], provenance: dict[str, Any]) -> str:
    value = str(artifacts.get(key) or "").strip()
    source = str(provenance.get(key) or "").strip()
    source_suffix = f" · source: {source}" if source else ""
    return f"- {label}: {display_path(value) if value else 'пока нет'}{source_suffix}"


def format_session_artifact_shortcuts(
    artifacts: dict[str, Any] | None,
    provenance: dict[str, Any] | None = None,
) -> str:
    payload = artifacts if isinstance(artifacts, dict) else {}
    source = provenance if isinstance(provenance, dict) else {}
    lines = ["Session artifacts"]
    lines.append(_artifact_line("run.json", "session_run", payload, source))
    lines.append(_artifact_line("run dir", "run_dir", payload, source))
    lines.append(_artifact_line("plan.json", "plan_json", payload, source))
    lines.append(_artifact_line("runtime config", "runtime_config", payload, source))
    lines.append(_artifact_line("state file", "state_path", payload, source))
    lines.append(_artifact_line("screenshot", "screenshot", payload, source))
    return "\n".join(lines)


def format_session_progress_summary(progress: dict[str, Any] | None) -> str:
    payload = progress if isinstance(progress, dict) else {}
    if not payload:
        return ""
    eta_mode = str(payload.get("eta_mode") or "unknown")
    eta_available = bool(payload.get("eta_available"))
    eta_text = format_seconds_hms(payload.get("eta_seconds")) if eta_available else f"н/д ({payload.get('eta_reason') or eta_mode})"
    artifact_status = payload.get("artifact_status") if isinstance(payload.get("artifact_status"), dict) else {}
    missing_artifacts = ", ".join(str(item) for item in artifact_status.get("missing") or [] if str(item).strip())
    lines = [
        "Session progress",
        f"Статус: {payload.get('status') or '-'} · фаза: {payload.get('current_phase') or '-'}",
        f"Обработано сообщений: {payload.get('processed_count') or 0}/{payload.get('selected_target') or 0}",
        f"Осталось в запуске: {payload.get('remaining_in_run') if payload.get('remaining_in_run') is not None else '-'}",
        f"Скорость: {_rate_text(payload.get('rate_per_minute'))}",
        f"ETA: {eta_text}",
        f"Текущий адресат: {payload.get('current_target_label') or 'не выбран'}",
        f"Текущий шаблон: {payload.get('current_template_preview') or 'не выбран'}",
        f"Режим: {payload.get('run_mode') or '-'}",
        f"Следующее действие: {payload.get('next_action_text') or 'не определено'}",
        f"Артефакты: {artifact_status.get('status') or 'unknown'}",
    ]
    if missing_artifacts:
        lines.append(f"Не хватает: {missing_artifacts}")
    return "\n".join(lines)


def build_session_dashboard_text(
    bucket: dict[str, Any] | None,
    snapshot: dict[str, Any],
    *,
    preview_context: dict[str, Any],
    operator_action_formatter: Callable[[dict[str, Any] | None], str],
    operator_summary_formatter: Callable[..., str],
    history_formatter: Callable[[dict[str, Any]], str],
    progress_formatter: Callable[[dict[str, Any] | None], str] | None = None,
    artifact_formatter: Callable[[dict[str, Any] | None, dict[str, Any] | None], str] | None = None,
) -> dict[str, str]:
    payload = bucket if isinstance(bucket, dict) else {}
    progress_text = progress_formatter(payload.get("progress_summary")) if progress_formatter else ""
    artifact_text = (
        artifact_formatter(payload.get("artifact_shortcuts"), payload.get("artifact_provenance"))
        if artifact_formatter
        else ""
    )
    summary_parts = [
        operator_action_formatter(bucket),
        progress_text,
        operator_summary_formatter(snapshot, **preview_context),
        artifact_text,
    ]
    return {
        "summary": "\n\n".join(part for part in summary_parts if str(part or "").strip()),
        "history": history_formatter(snapshot),
    }


def build_invite_dashboard_texts(
    *,
    action_block: str,
    job_dir_text: str,
    preview_path: str,
    bucket_snapshot: dict[str, Any] | None,
    bucket_progress: dict[str, Any] | None,
    invite_input_preview_loader: Callable[[str | Path], dict[str, Any]],
    contact_job_snapshot_loader: Callable[[str], dict[str, Any]],
    invite_preview_formatter: Callable[[dict[str, Any]], str],
    contact_snapshot_formatter: Callable[[dict[str, Any]], str],
    contact_error_formatter: Callable[[dict[str, Any]], str],
    contact_history_formatter: Callable[[dict[str, Any]], str],
    username_block_formatter: Callable[[str, list[str], str], str],
    progress_preview_formatter: Callable[[dict[str, Any]], str],
) -> dict[str, str]:
    if not job_dir_text:
        if preview_path:
            preview = invite_input_preview_loader(preview_path)
            return {
                "summary": action_block + "\n\n" + invite_preview_formatter(preview),
                "queue": username_block_formatter(
                    "Первые username из файла",
                    list(preview.get("usernames") or []),
                    "В файле пока нет корректных username.",
                ),
                "added": "Уже добавлены\nЗадача ещё не запускалась.",
                "failed": "Последние ошибки\nОшибок пока нет.",
                "history": "История batch-запусков\nПока нет запусков.",
                "preview": (
                    f"Уникальных username: {preview.get('unique_usernames') or 0}"
                    f" · дубликатов: {preview.get('duplicates') or 0}"
                    f" · ошибок: {preview.get('invalid_count') or 0}"
                ),
            }
        return {
            "summary": action_block
            + "\n\n"
            + "Файл контактов ещё не выбран. Загрузи TXT / CSV / JSON и затем запускай batch-добавление.",
            "queue": "",
            "added": "",
            "failed": "",
            "history": "",
            "preview": "",
        }

    snapshot = dict(bucket_snapshot) if bucket_snapshot else contact_job_snapshot_loader(job_dir_text)
    if isinstance(bucket_progress, dict) and bucket_progress and not isinstance(snapshot.get("progress_summary"), dict):
        snapshot["progress_summary"] = dict(bucket_progress)
    progress_preview = progress_preview_formatter(snapshot.get("progress_summary") or {})
    if not progress_preview:
        progress_preview = (
            f"Осталось: {snapshot.get('pending_total') or 0}"
            f" · добавлено: {snapshot.get('added_total') or 0}"
            f" · ошибок: {snapshot.get('failed_total') or 0}"
        )
    return {
        "summary": action_block + "\n\n" + contact_snapshot_formatter(snapshot),
        "queue": username_block_formatter(
            "Осталось в очереди",
            list(snapshot.get("pending_usernames") or []),
            "Очередь сейчас пуста.",
        ),
        "added": username_block_formatter(
            "Уже добавлены",
            list(snapshot.get("added_usernames") or []),
            "Пока никто не добавлен.",
        ),
        "failed": contact_error_formatter(snapshot),
        "history": contact_history_formatter(snapshot),
        "preview": progress_preview,
    }


def resolve_combined_contact_preview(
    *,
    input_path: str,
    invite_job_dir: str,
    contact_job_snapshot_loader: Callable[[str], dict[str, Any]],
    invite_input_preview_loader: Callable[[str | Path], dict[str, Any]],
) -> dict[str, Any]:
    invite_snapshot: dict[str, Any] | None = None
    preview_text = "Список ещё не выбран"
    preview_payload: dict[str, Any] | None = None
    preview_error = ""
    if invite_job_dir:
        invite_snapshot = contact_job_snapshot_loader(invite_job_dir)
    if input_path:
        try:
            preview_payload = invite_input_preview_loader(input_path)
            preview_text = (
                f"Уникальных username: {preview_payload.get('unique_usernames') or 0} · "
                f"дубликатов: {preview_payload.get('duplicates') or 0} · "
                f"ошибок: {preview_payload.get('invalid_count') or 0}"
            )
        except Exception as exc:
            preview_error = str(exc)
            preview_text = f"Не удалось прочитать файл: {exc}"
    return {
        "invite_snapshot": invite_snapshot,
        "preview_text": preview_text,
        "preview_payload": preview_payload,
        "preview_error": preview_error,
    }


def format_combined_progress_summary(progress: dict[str, Any] | None) -> str:
    payload = progress if isinstance(progress, dict) else {}
    if not payload:
        return ""
    child_progress = payload.get("child_progress") if isinstance(payload.get("child_progress"), dict) else {}
    child_eta = (
        format_seconds_hms(payload.get("child_eta_seconds"))
        if payload.get("child_eta_available") and payload.get("child_eta_seconds") is not None
        else "н/д"
    )
    lines = [
        "Combined progress",
        f"Parent: {payload.get('status') or '-'} · {payload.get('phase_label') or payload.get('phase') or '-'}",
        f"Текущий шаг: {payload.get('current_step_label') or '-'}",
        f"Следующий шаг: {payload.get('next_step_label') or '-'}",
        f"Recoverable: {'да' if payload.get('recoverable') else 'нет'} · {payload.get('recoverable_hint') or '-'}",
        f"Child source: {payload.get('child_history_source') or '-'}",
        f"Child status: {payload.get('child_status') or child_progress.get('status') or '-'}",
        f"Child processed: {payload.get('child_processed_count') or 0}/{payload.get('child_selected_target') or 0}",
        f"Child remaining: {payload.get('child_remaining_in_run') if payload.get('child_remaining_in_run') is not None else '-'}",
        f"Child ETA: {child_eta}",
        f"Invite queue: осталось {payload.get('invite_pending_total') or 0}, добавлено {payload.get('invite_added_total') or 0}, ошибок {payload.get('invite_failed_total') or 0}",
    ]
    blocker = str(payload.get("pattern_advancement_blocker") or "").strip()
    if blocker:
        lines.append(f"Pattern blocker: {blocker}")
    waiting = str(payload.get("waiting_reason") or "").strip()
    if waiting:
        lines.append(f"Waiting reason: {waiting}")
    return "\n".join(lines)


def format_combined_artifact_shortcuts(
    parent_artifacts: dict[str, Any] | None,
    child_artifacts: dict[str, Any] | None = None,
    provenance: dict[str, Any] | None = None,
) -> str:
    parent = parent_artifacts if isinstance(parent_artifacts, dict) else {}
    children = child_artifacts if isinstance(child_artifacts, dict) else {}
    source = provenance if isinstance(provenance, dict) else {}
    lines = ["Combined artifacts", "Parent workflow"]
    for key, label in (
        ("job_dir", "job dir"),
        ("run_dir", "run dir"),
        ("progress_json", "invite progress"),
        ("batch_json", "batch json"),
        ("session_run", "session run"),
        ("plan_json", "session plan"),
        ("runtime_config", "runtime config"),
        ("state_path", "state file"),
        ("execution_record", "execution record"),
        ("screenshot", "screenshot"),
    ):
        if key in parent or key in {"session_run", "plan_json", "runtime_config", "state_path"}:
            lines.append(_artifact_line(label, key, parent, source))
    invite_child = children.get("invite_batch") if isinstance(children.get("invite_batch"), dict) else {}
    session_child = children.get("session_run") if isinstance(children.get("session_run"), dict) else {}
    if invite_child:
        lines.extend(["", "Child invite"])
        for key, label in (("progress_json", "progress"), ("batch_json", "batch"), ("execution_record", "execution")):
            lines.append(_artifact_line(label, key, invite_child, {}))
    if session_child:
        lines.extend(["", "Child session"])
        for key, label in (("session_run", "run.json"), ("plan_json", "plan.json"), ("runtime_config", "runtime config"), ("state_path", "state")):
            lines.append(_artifact_line(label, key, session_child, {}))
    return "\n".join(lines)


def build_combined_dashboard_texts(
    *,
    action_block: str,
    state: dict[str, Any],
    profile_label: str,
    invite_snapshot: dict[str, Any] | None,
    session_snapshot: dict[str, Any],
    preview_context: dict[str, Any],
    input_path: str,
    preview_payload: dict[str, Any] | None,
    preview_error: str,
    combined_state_formatter: Callable[..., str],
    contact_snapshot_formatter: Callable[[dict[str, Any]], str],
    contact_error_formatter: Callable[[dict[str, Any]], str],
    invite_preview_formatter: Callable[[dict[str, Any]], str],
    session_snapshot_formatter: Callable[[dict[str, Any]], str],
    targets_summary_text: str,
    progress_summary: dict[str, Any] | None = None,
    progress_formatter: Callable[[dict[str, Any] | None], str] | None = None,
    parent_artifacts: dict[str, Any] | None = None,
    child_artifacts: dict[str, Any] | None = None,
    artifact_provenance: dict[str, Any] | None = None,
    artifact_formatter: Callable[[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None], str] | None = None,
) -> dict[str, str]:
    state_parts = [
        action_block,
        combined_state_formatter(
            state,
            profile_label=profile_label,
            invite_snapshot=invite_snapshot,
            session_snapshot=session_snapshot,
            **preview_context,
        ),
    ]
    if progress_formatter:
        progress_text = progress_formatter(progress_summary)
        if progress_text:
            state_parts.append(progress_text)
    if artifact_formatter:
        artifact_text = artifact_formatter(parent_artifacts, child_artifacts, artifact_provenance)
        if artifact_text:
            state_parts.append(artifact_text)
    state_text = "\n\n".join(part for part in state_parts if str(part or "").strip())
    if invite_snapshot is None:
        if input_path:
            if preview_error:
                contact_text = f"Не удалось прочитать список username:\n{preview_error}"
            elif isinstance(preview_payload, dict):
                contact_text = invite_preview_formatter(preview_payload)
            else:
                contact_text = "Контакты\nСписок ещё не выбран."
        else:
            contact_text = "Контакты\nВыбери файл контактов и нажми `Старт совместного режима`."
    else:
        contact_text = contact_snapshot_formatter(invite_snapshot)
        contact_text += "\n\n" + contact_error_formatter(invite_snapshot)
    return {
        "state_text": state_text,
        "contact_text": contact_text,
        "session_text": session_snapshot_formatter(session_snapshot),
        "targets_text": targets_summary_text,
    }


def ensure_session_base_config(config_path: str | Path = DEFAULT_SESSION_CONFIG) -> Path:
    resolved = Path(config_path).expanduser().resolve()
    if resolved.exists():
        return resolved
    fallback = session_repo_example_config()
    if fallback.is_file():
        resolved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fallback, resolved)
    return resolved


def parse_json_payload(stdout: str) -> dict[str, Any]:
    payload = json.loads(stdout)
    if not isinstance(payload, dict):
        raise RuntimeError("command returned unexpected JSON payload")
    return payload


def run_json_command(argv: list[str], *, cwd: str | Path | None = None) -> dict[str, Any]:
    completed = subprocess.run(
        argv,
        cwd=str(cwd) if cwd is not None else None,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(detail or f"command failed with code {completed.returncode}")
    return parse_json_payload(completed.stdout)


def chat_slug_from_chat_url(chat_url: str) -> str:
    fragment = str(chat_url or "").split("#", 1)[1] if "#" in str(chat_url or "") else str(chat_url or "")
    fragment = fragment or "chat"
    return re.sub(r"[^A-Za-z0-9._-]", "_", fragment)


def default_invite_job_dir(chat_url: str, output_root: str | Path = DEFAULT_INVITE_OUTPUT_ROOT) -> Path:
    return Path(output_root).expanduser().resolve() / f"chat_{chat_slug_from_chat_url(chat_url)}"


def _safe_slug(value: str, fallback: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]", "_", str(value or "").strip())
    slug = slug.strip("._-")
    return slug or fallback


def default_contact_add_job_dir(
    *,
    profile_name: str,
    input_path: str | Path,
    output_root: str | Path = DEFAULT_INVITE_OUTPUT_ROOT,
) -> Path:
    input_stem = Path(input_path).expanduser().resolve().stem if str(input_path or "").strip() else "list"
    profile_slug = _safe_slug(profile_name, "profile")
    input_slug = _safe_slug(input_stem, "list")
    return Path(output_root).expanduser().resolve() / f"contact_add__{profile_slug}__{input_slug}"


def resolve_invite_job_dir(job_dir: str | Path) -> Path:
    resolved = Path(job_dir).expanduser().resolve()
    canonical_candidate = DEFAULT_INVITE_OUTPUT_ROOT / resolved.name
    legacy_root = LEGACY_INVITE_JOBS_ROOT.expanduser().resolve()
    try:
        resolved.relative_to(legacy_root)
    except ValueError:
        return canonical_candidate if canonical_candidate.exists() else resolved
    return canonical_candidate if canonical_candidate.exists() else resolved


def contact_add_chat_url(*, profile_name: str, account_username: str = "") -> str:
    identity = _safe_slug(account_username or profile_name, "profile")
    return f"contacts://{identity}"


def combined_flow_state_path(
    *,
    profile_name: str,
    profile_dir: str | Path,
    state_root: str | Path = DEFAULT_PANEL_STATE_ROOT,
) -> Path:
    return persistent_combined_flow_state_path(
        profile_name=profile_name,
        profile_dir=profile_dir,
        state_root=state_root,
    )


def default_combined_flow_state(profile_name: str, profile_dir: str | Path) -> dict[str, Any]:
    return {
        "workflow_job_id": "",
        "job_status": "planned",
        "job_summary": "",
        "next_hint": "",
        "steps_total": 0,
        "profile_name": str(profile_name or "").strip() or "profile",
        "profile_dir": str(Path(profile_dir).expanduser().resolve()) if str(profile_dir or "").strip() else "",
        "phase": "contact_add",
        "step_pattern": "12",
        "step_cursor": 0,
        "step_label": "добавление контактов",
        "input_path": "",
        "invite_job_dir": "",
        "session_config_path": "",
        "last_runtime_config_path": "",
        "last_action": "",
        "last_status": "idle",
        "last_summary": "",
        "last_invite_status": "",
        "last_session_status": "",
        "last_session_run_dir": "",
        "recent_step": {},
        "updated_at": "",
    }


def load_combined_flow_state(
    *,
    profile_name: str,
    profile_dir: str | Path,
    state_root: str | Path = DEFAULT_PANEL_STATE_ROOT,
) -> dict[str, Any]:
    state_from_jobs = combined_state_from_jobs(
        profile_name=profile_name,
        profile_dir=profile_dir,
    )
    if isinstance(state_from_jobs, dict):
        state = default_combined_flow_state(profile_name, profile_dir)
        state.update({key: value for key, value in state_from_jobs.items() if key in state})
        if str(state.get("phase") or "") not in COMBINED_PHASES:
            state["phase"] = "contact_add"
        return state
    path = combined_flow_state_path(
        profile_name=profile_name,
        profile_dir=profile_dir,
        state_root=state_root,
    )
    if not path.exists():
        migrate_legacy_combined_state(
            profile_name=profile_name,
            profile_dir=profile_dir,
            new_state_root=state_root,
        )
    if not path.exists():
        return default_combined_flow_state(profile_name, profile_dir)
    payload = _load_json_file(path)
    if not isinstance(payload, dict):
        raise ValueError("combined flow state must contain a JSON object")
    state = default_combined_flow_state(profile_name, profile_dir)
    state.update({key: value for key, value in payload.items() if key in state})
    if str(state.get("phase") or "") not in COMBINED_PHASES:
        state["phase"] = "contact_add"
    return state


def save_combined_flow_state(
    *,
    profile_name: str,
    profile_dir: str | Path,
    payload: dict[str, Any],
    state_root: str | Path = DEFAULT_PANEL_STATE_ROOT,
) -> Path:
    state = default_combined_flow_state(profile_name, profile_dir)
    state.update({key: value for key, value in payload.items() if key in state})
    if str(state.get("phase") or "") not in COMBINED_PHASES:
        state["phase"] = "contact_add"
    state["updated_at"] = _now_utc()
    path = combined_flow_state_path(
        profile_name=profile_name,
        profile_dir=profile_dir,
        state_root=state_root,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def active_profile_conflict(
    active_profiles: dict[str, str],
    requested_profile_dir: str | Path,
    *,
    current_tool_id: str | None = None,
) -> tuple[str, str] | None:
    requested = str(Path(requested_profile_dir).expanduser().resolve()) if str(requested_profile_dir or "").strip() else ""
    if not requested:
        return None
    for tool_id, profile_dir in active_profiles.items():
        if current_tool_id is not None and tool_id == current_tool_id:
            continue
        normalized = str(Path(profile_dir).expanduser().resolve()) if str(profile_dir or "").strip() else ""
        if normalized and normalized == requested:
            return tool_id, normalized
    return None


def parse_plaintext_usernames(text: str) -> list[str]:
    usernames: list[str] = []
    seen: set[str] = set()
    for raw_line in str(text or "").splitlines():
        candidate = raw_line.strip()
        if not candidate or candidate.startswith("#"):
            continue
        if not USERNAME_RE.fullmatch(candidate):
            raise ValueError(f"invalid username in txt list: {candidate}")
        normalized = candidate if candidate.startswith("@") else f"@{candidate}"
        normalized = normalized.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        usernames.append(normalized)
    return usernames


def preview_invite_input_file(source_path: str | Path) -> dict[str, Any]:
    path = Path(source_path).expanduser().resolve()
    suffix = path.suffix.lower()
    unique_usernames: list[str] = []
    seen: set[str] = set()
    duplicates = 0
    invalid_entries: list[str] = []
    rows_total = 0

    def _register_username(raw_value: Any) -> None:
        nonlocal duplicates, rows_total
        rows_total += 1
        candidate = str(raw_value or "").strip()
        if not candidate or candidate.startswith("#"):
            return
        if not USERNAME_RE.fullmatch(candidate):
            invalid_entries.append(candidate)
            return
        normalized = candidate if candidate.startswith("@") else f"@{candidate}"
        normalized = normalized.lower()
        if normalized in seen:
            duplicates += 1
            return
        seen.add(normalized)
        unique_usernames.append(normalized)

    if suffix == ".txt":
        for line in path.read_text(encoding="utf-8").splitlines():
            _register_username(line)
    elif suffix == ".csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                _register_username((row or {}).get("username"))
    elif suffix == ".json":
        payload = _load_json_file(path)
        if isinstance(payload, dict):
            raw_items = payload.get("users")
        else:
            raw_items = payload
        if not isinstance(raw_items, list):
            raise ValueError("json input must contain a list or object with users[]")
        for item in raw_items:
            if isinstance(item, dict):
                _register_username(item.get("username"))
    else:
        raise ValueError("supported invite input formats: .txt, .csv, .json")

    return {
        "status": "ready",
        "path": str(path),
        "format": suffix.lstrip(".") or "unknown",
        "rows_total": rows_total,
        "unique_usernames": len(unique_usernames),
        "duplicates": duplicates,
        "invalid_count": len(invalid_entries),
        "invalid_entries": invalid_entries[:10],
        "usernames": unique_usernames[:20],
    }


def _iter_contact_batch_runs(job_dir: str | Path, *, history_limit: int) -> list[dict[str, Any]]:
    executions_dir = Path(job_dir).expanduser().resolve() / "executions"
    if not executions_dir.exists():
        return []
    history: list[dict[str, Any]] = []
    for path in sorted(executions_dir.glob("*/batch_contact_add.json"))[-history_limit:]:
        try:
            payload = _load_json_file(path)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        processed_count = _safe_int(payload.get("processed_count") or len(payload.get("results") or []))
        elapsed_seconds = _safe_int(payload.get("elapsed_seconds"), default=-1)
        if elapsed_seconds < 0:
            elapsed_seconds = _elapsed_seconds_from_timestamps(payload.get("started_at"), payload.get("completed_at")) or 0
        raw_rate = payload.get("rate_per_minute")
        if raw_rate in {"", None}:
            rate_per_minute = _invite_rate_per_minute(processed_count, elapsed_seconds) or 0.0
        else:
            rate_per_minute = _safe_float(raw_rate, 0.0)
        history.append(
            {
                "execution_id": str(payload.get("execution_id") or path.parent.name),
                "status": str(payload.get("status") or ""),
                "added_count": _safe_int(payload.get("added_count")),
                "already_present_count": _safe_int(payload.get("already_present_count")),
                "failed_count": _safe_int(payload.get("failed_count")),
                "remaining_candidates": _safe_int(payload.get("remaining_candidates")),
                "selected_users": _safe_int(payload.get("selected_users")),
                "processed_count": processed_count,
                "started_at": str(payload.get("started_at") or ""),
                "completed_at": str(payload.get("completed_at") or ""),
                "elapsed_seconds": elapsed_seconds,
                "rate_per_minute": rate_per_minute,
                "run_dir": str(payload.get("run_dir") or path.parent),
                "path": str(path),
            }
        )
    return history


def _latest_contact_batch_progress(job_dir: str | Path) -> dict[str, Any]:
    executions_dir = Path(job_dir).expanduser().resolve() / "executions"
    if not executions_dir.exists():
        return {}
    progress_paths = sorted(executions_dir.glob("*/batch_progress.json"))
    if not progress_paths:
        return {}
    latest_path = max(
        progress_paths,
        key=lambda item: (item.stat().st_mtime if item.exists() else 0, str(item)),
    )
    try:
        payload = _load_json_file(latest_path)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    payload = dict(payload)
    payload.setdefault("run_dir", str(latest_path.parent))
    payload.setdefault("progress_path", str(latest_path))
    payload.setdefault("execution_id", str(payload.get("execution_id") or latest_path.parent.name))
    return payload


def contact_job_snapshot(
    job_dir: str | Path,
    *,
    queue_limit: int = 12,
    history_limit: int = 8,
) -> dict[str, Any]:
    resolved_job_dir = resolve_invite_job_dir(job_dir)
    state_path = resolved_job_dir / "invite_state.json"
    if not state_path.exists():
        return {
            "status": "missing",
            "job_dir": str(resolved_job_dir),
            "state_path": str(state_path),
        }

    payload = _load_json_file(state_path)
    if not isinstance(payload, dict):
        raise ValueError("invite_state.json must contain an object")
    users = [row for row in payload.get("users") or [] if isinstance(row, dict)]
    counts = Counter(str(row.get("status") or "") for row in users)
    pending_users = [str(row.get("username") or "") for row in users if str(row.get("status") or "") in CONTACT_PENDING_STATUSES]
    added_users = [str(row.get("username") or "") for row in users if str(row.get("status") or "") in CONTACT_SUCCESS_STATUSES]
    failed_rows = [row for row in users if str(row.get("status") or "") in CONTACT_ERROR_STATUSES]
    failed_users = [str(row.get("username") or "") for row in failed_rows]
    failed_details = [
        {
            "username": str(row.get("username") or ""),
            "attempts": _safe_int(row.get("attempts")),
            "last_attempt_at": str(row.get("last_attempt_at") or ""),
            "last_reason": str((row.get("history") or [{}])[-1].get("reason") or "")
            if isinstance(row.get("history"), list) and row.get("history")
            else "",
        }
        for row in failed_rows[:queue_limit]
    ]
    latest_runs = _iter_contact_batch_runs(resolved_job_dir, history_limit=history_limit)
    latest_progress = _latest_contact_batch_progress(resolved_job_dir)
    latest_errors: list[dict[str, Any]] = []
    if latest_runs:
        latest_run_path = Path(latest_runs[-1]["path"])
        try:
            latest_payload = _load_json_file(latest_run_path)
        except (OSError, json.JSONDecodeError):
            latest_payload = {}
        if isinstance(latest_payload, dict):
            for item in latest_payload.get("results") or []:
                if not isinstance(item, dict):
                    continue
                if str(item.get("status") or "").strip().lower() == "failed" or str(item.get("returncode") or "") not in {"", "0"}:
                    latest_errors.append(
                        {
                            "username": str(item.get("username") or ""),
                            "error": str(item.get("error") or ""),
                            "outcome": str(item.get("outcome") or ""),
                            "run_dir": str(item.get("run_dir") or ""),
                        }
                    )
            latest_errors = latest_errors[:queue_limit]

    progress_summary: dict[str, Any] = {}
    progress_status = str(latest_progress.get("status") or "").strip().lower()
    if latest_progress and (progress_status == "running" or not latest_runs):
        progress_summary = _invite_progress_summary_from_payload(latest_progress, history_source="progress_json")
    elif latest_runs:
        progress_summary = _invite_progress_summary_from_payload(latest_runs[-1], history_source="batch_json")
    else:
        progress_summary = {
            "status": "idle",
            "history_source": "invite_state",
            "started_at": "",
            "completed_at": "",
            "elapsed_seconds": 0,
            "selected_target": 0,
            "processed_count": 0,
            "remaining_in_run": 0,
            "queue_remaining_total": len(pending_users),
            "added_count": len(added_users),
            "already_present_count": 0,
            "failed_count": len(failed_users),
            "rate_per_minute": None,
            "eta_seconds": None,
            "current_username": "",
            "last_outcome": "",
            "execution_id": "",
        }

    return {
        "status": "ready",
        "job_dir": str(resolved_job_dir),
        "state_path": str(state_path),
        "chat_url": str(payload.get("chat_url") or ""),
        "source_file": str(payload.get("source_file") or ""),
        "updated_at": str(payload.get("updated_at") or ""),
        "total_users": len(users),
        "counts": dict(sorted(counts.items())),
        "pending_total": len(pending_users),
        "added_total": len(added_users),
        "failed_total": len(failed_users),
        "pending_usernames": pending_users[:queue_limit],
        "added_usernames": added_users[-queue_limit:],
        "failed_usernames": failed_users[:queue_limit],
        "failed_details": failed_details,
        "latest_runs": latest_runs,
        "latest_progress": latest_progress,
        "progress_summary": progress_summary,
        "latest_errors": latest_errors,
    }


def combined_contact_add_transition(
    *,
    previous_state: dict[str, Any],
    payload: dict[str, Any],
    session_continuous: bool,
) -> dict[str, Any]:
    payload_status = str(payload.get("status") or "").strip().lower() or "completed"
    selected_users = _safe_int(payload.get("selected_users"))
    remaining_candidates = _safe_int(payload.get("remaining_candidates"))
    failed_count = _safe_int(payload.get("failed_count"))
    had_previous_session = bool(
        str(previous_state.get("last_session_status") or "").strip()
        or str(previous_state.get("last_session_run_dir") or "").strip()
    )

    if payload_status == "completed_with_errors":
        if selected_users > 0:
            return {
                "phase": "session_ready",
                "last_action": "combined_contact_add_finished_auto",
                "last_status": payload_status,
                "status_text": (
                    "Часть контактов добавлена, ошибки сохранены, запускаю непрерывную сессию"
                    if session_continuous
                    else "Часть контактов добавлена, ошибки сохранены, запускаю шаг сессии"
                ),
                "auto_start_session": True,
            }
        return {
            "phase": "stopped",
            "last_action": "combined_contact_add_finished",
            "last_status": payload_status,
            "status_text": "Шаг добавления завершился с ошибками и не перешёл к сессии",
            "auto_start_session": False,
        }

    if selected_users == 0 and failed_count == 0:
        if had_previous_session and remaining_candidates == 0:
            return {
                "phase": "stopped",
                "last_action": "combined_contact_add_noop_after_session",
                "last_status": "completed",
                "status_text": "Очередь контактов закончилась, совместный режим завершён",
                "auto_start_session": False,
            }
        return {
            "phase": "session_ready",
            "last_action": "combined_contact_add_noop",
            "last_status": "no_new_usernames",
            "status_text": "Новых username для добавления нет; выбери другой файл или запускай сессию",
            "auto_start_session": False,
        }

    return {
        "phase": "session_ready",
        "last_action": "combined_contact_add_finished_auto",
        "last_status": payload_status,
        "status_text": (
            "Контакты добавлены, запускаю непрерывную сессию"
            if session_continuous
            else "Контакты добавлены, запускаю шаг сессии"
        ),
        "auto_start_session": True,
    }


def combined_session_transition(
    *,
    payload: dict[str, Any],
    invite_snapshot: dict[str, Any] | None,
    session_continuous: bool,
) -> dict[str, Any]:
    payload_status = str(payload.get("status") or "").strip().lower() or "completed"
    pending_total = _safe_int((invite_snapshot or {}).get("pending_total"))

    if payload_status == "stopped":
        return {
            "phase": "stopped",
            "last_action": "combined_session_finished",
            "last_status": "stopped",
            "status_text": "Сессия остановлена",
            "auto_start_contact_add": False,
        }

    if pending_total > 0 and not session_continuous and payload_status == "completed":
        return {
            "phase": "contact_add",
            "last_action": "combined_session_finished_next_contact",
            "last_status": payload_status,
            "status_text": f"Осталось username: {pending_total}. Запускаю следующий шаг добавления",
            "auto_start_contact_add": True,
        }

    if payload_status == "completed":
        status_text = (
            "Непрерывная сессия завершила свой шаг"
            if session_continuous
            else "Совместный режим завершил шаг сессии"
        )
    else:
        status_text = f"Сессия завершилась со статусом: {payload_status}"

    return {
        "phase": "stopped",
        "last_action": "combined_session_finished",
        "last_status": payload_status,
        "status_text": status_text,
        "auto_start_contact_add": False,
    }


def prepare_invite_input_file(source_path: str | Path, temp_dir: str | Path) -> Path:
    path = Path(source_path).expanduser().resolve()
    if path.suffix.lower() in {".csv", ".json"}:
        return path
    if path.suffix.lower() != ".txt":
        raise ValueError("supported invite input formats: .txt, .csv, .json")

    usernames = parse_plaintext_usernames(path.read_text(encoding="utf-8"))
    output_path = Path(temp_dir).expanduser().resolve() / f"{path.stem}.invite-import.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["username", "consent", "source"])
        writer.writeheader()
        for username in usernames:
            writer.writerow(
                {
                    "username": username,
                    "consent": "yes",
                    "source": "panel_txt_import",
                }
            )
    return output_path


def invite_manager_init(
    *,
    chat_url: str,
    input_path: str | Path,
    job_dir: str | Path | None = None,
    output_root: str | Path = DEFAULT_INVITE_OUTPUT_ROOT,
    temp_dir: str | Path = "/tmp/telegram-control-center",
) -> dict[str, Any]:
    spec = invite_manager_init_command(
        chat_url=chat_url,
        input_path=input_path,
        job_dir=job_dir,
        output_root=output_root,
        temp_dir=temp_dir,
    )
    return run_json_command(spec.argv, cwd=spec.cwd)


def invite_manager_init_command(
    *,
    chat_url: str,
    input_path: str | Path,
    job_dir: str | Path | None = None,
    output_root: str | Path = DEFAULT_INVITE_OUTPUT_ROOT,
    temp_dir: str | Path = "/tmp/telegram-control-center",
) -> CommandSpec:
    prepared_input = prepare_invite_input_file(input_path, temp_dir)
    argv = [
        "python3",
        str(DEFAULT_INVITE_SCRIPT),
        "init",
        "--chat-url",
        chat_url,
        "--input",
        str(prepared_input),
        "--output-root",
        str(Path(output_root).expanduser().resolve()),
    ]
    if job_dir:
        argv.extend(["--job-dir", str(Path(job_dir).expanduser().resolve())])
    return CommandSpec(argv=argv, cwd=DEFAULT_INVITE_SCRIPT.parent.parent)


def invite_manager_status(job_dir: str | Path) -> dict[str, Any]:
    spec = invite_manager_status_command(job_dir)
    return run_json_command(spec.argv, cwd=spec.cwd)


def invite_manager_status_command(job_dir: str | Path) -> CommandSpec:
    return CommandSpec(
        argv=[
            "python3",
            str(DEFAULT_INVITE_SCRIPT),
            "status",
            "--job-dir",
            str(resolve_invite_job_dir(job_dir)),
        ],
        cwd=DEFAULT_INVITE_SCRIPT.parent.parent,
    )


def invite_manager_next(job_dir: str | Path, *, limit: int = 10) -> dict[str, Any]:
    spec = invite_manager_next_command(job_dir, limit=limit)
    return run_json_command(spec.argv, cwd=spec.cwd)


def invite_manager_next_command(job_dir: str | Path, *, limit: int = 10) -> CommandSpec:
    return CommandSpec(
        argv=[
            "python3",
            str(DEFAULT_INVITE_SCRIPT),
            "next",
            "--job-dir",
            str(resolve_invite_job_dir(job_dir)),
            "--limit",
            str(max(int(limit), 1)),
        ],
        cwd=DEFAULT_INVITE_SCRIPT.parent.parent,
    )


def contact_add_batch_command(
    *,
    input_path: str | Path | None,
    job_dir: str | Path,
    profile_name: str,
    portable_profile_dir: str | Path,
    account_username: str = "",
    account_label: str = "",
    limit: int = 0,
    output_root: str | Path = DEFAULT_INVITE_OUTPUT_ROOT,
    temp_dir: str | Path = "/tmp/telegram-control-center",
    launch_if_needed: bool = True,
    confirm_add: bool = True,
    dry_run: bool = False,
    statuses: list[str] | tuple[str, ...] | None = None,
    execution_id: str = "",
) -> CommandSpec:
    resolved_job_dir = resolve_invite_job_dir(job_dir)
    argv = [
        "python3",
        str(DEFAULT_INVITE_EXECUTOR_SCRIPT),
        "desktop-add-contact-batch",
        "--job-dir",
        str(resolved_job_dir),
        "--chat-url",
        contact_add_chat_url(profile_name=profile_name, account_username=account_username),
        "--portable-profile-name",
        str(profile_name or "").strip(),
        "--portable-profile-dir",
        str(Path(portable_profile_dir).expanduser().resolve()),
        "--output-root",
        str(Path(output_root).expanduser().resolve()),
    ]
    if input_path is not None and str(input_path).strip():
        prepared_input = prepare_invite_input_file(input_path, temp_dir)
        argv.extend(["--input", str(prepared_input)])
    if account_username:
        argv.extend(["--account-username", str(account_username).strip()])
    if account_label:
        argv.extend(["--account-label", str(account_label).strip()])
    if limit > 0:
        argv.extend(["--limit", str(int(limit))])
    if str(execution_id).strip():
        argv.extend(["--execution-id", str(execution_id).strip()])
    if statuses:
        argv.extend(["--statuses", *[str(item).strip() for item in statuses if str(item).strip()]])
    if launch_if_needed:
        argv.append("--launch-if-needed")
    if confirm_add:
        argv.append("--confirm-add")
    if dry_run:
        argv.append("--dry-run")
    return CommandSpec(argv=argv, cwd=DEFAULT_INVITE_EXECUTOR_SCRIPT.parent.parent)


def load_session_config_payload(config_path: str | Path) -> dict[str, Any]:
    resolved = ensure_session_base_config(config_path)
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("session config must contain a JSON object")
    return payload


def _as_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def parse_combined_step_pattern(pattern_text: str) -> list[str]:
    return [char for char in str(pattern_text or "") if char in {"1", "2"}]


def combined_step_label(step_code: str) -> str:
    return "добавление контактов" if str(step_code) == "1" else "сессия и сообщения"


def _as_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def session_message_targets(config_path: str | Path) -> list[dict[str, Any]]:
    payload = load_session_config_payload(config_path)
    message_policy = payload.get("message_policy")
    if not isinstance(message_policy, dict):
        return []
    raw_targets = message_policy.get("message_targets")
    if not isinstance(raw_targets, list):
        return []
    return [dict(item) for item in raw_targets if isinstance(item, dict)]


def session_config_defaults(config_path: str | Path) -> dict[str, Any]:
    payload = load_session_config_payload(config_path)
    session = payload.get("session")
    if not isinstance(session, dict):
        session = {}
    message_policy = payload.get("message_policy")
    if not isinstance(message_policy, dict):
        message_policy = {}
    raw_targets = message_policy.get("message_targets")
    raw_templates = message_policy.get("templates")
    return {
        "message_targets": [dict(item) for item in raw_targets if isinstance(item, dict)] if isinstance(raw_targets, list) else [],
        "templates": [str(item).strip() for item in raw_templates if str(item).strip()] if isinstance(raw_templates, list) else [],
        "auto_send": _as_bool(message_policy.get("auto_send"), default=False),
        "drafts_per_run": _as_int(message_policy.get("drafts_per_run"), default=1),
        "total_message_limit": _as_int(message_policy.get("total_message_limit"), default=0),
        "random_walk_visits_per_run": _as_int(session.get("random_walk_visits_per_run"), default=6),
        "view_min_seconds": _as_int(session.get("view_min_seconds"), default=3),
        "view_max_seconds": _as_int(session.get("view_max_seconds"), default=6),
    }


def format_session_target_label(item: dict[str, Any]) -> str:
    handle = str(item.get("handle") or "").strip()
    label = str(item.get("label") or "").strip() or handle
    kind = str(item.get("kind") or "contact").strip().lower()
    kind_label = "группа" if kind == "group" else "контакт"
    return f"{label} · {handle} · {kind_label}"


def build_session_runtime_config(
    *,
    base_config_path: str | Path,
    output_path: str | Path,
    message_targets: list[dict[str, Any]],
    message_templates: list[str],
    drafts_per_run: int,
    total_message_limit: int,
    portable_profile_dir: str = "",
    auto_send: bool = False,
    session_overrides: dict[str, Any] | None = None,
) -> Path:
    payload = load_session_config_payload(base_config_path)
    payload["site_control_kit_root"] = str(repo_root())
    payload["python_bin"] = "python3"
    payload["portable_profile_dir"] = portable_profile_dir or str(
        payload.get("portable_profile_dir") or ""
    )
    session = payload.get("session")
    if not isinstance(session, dict):
        session = {}
        payload["session"] = session
    message_policy = payload.get("message_policy")
    if not isinstance(message_policy, dict):
        message_policy = {}
        payload["message_policy"] = message_policy

    message_policy["message_targets"] = message_targets
    message_policy["target_username"] = ""
    kinds = {str(item.get("kind") or "contact").strip().lower() for item in message_targets}
    message_policy["target_mode"] = "rotating_all" if "group" in kinds else "rotating_contacts"
    message_policy["templates"] = [str(item).strip() for item in message_templates if str(item).strip()]
    message_policy["drafts_per_run"] = max(0, int(drafts_per_run))
    message_policy["total_message_limit"] = max(0, int(total_message_limit))
    message_policy["auto_send"] = bool(auto_send)
    if isinstance(session_overrides, dict):
        for key, value in session_overrides.items():
            session[key] = value

    resolved_output = Path(output_path).expanduser().resolve()
    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    resolved_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return resolved_output


def session_history_snapshot(
    *,
    state_file: str | Path = DEFAULT_SESSION_STATE_FILE,
    runs_dir: str | Path = DEFAULT_SESSION_RUNS_DIR,
    limit: int = 8,
) -> dict[str, Any]:
    resolved_state = preferred_read_path(state_file, session_repo_state_file())
    resolved_runs = preferred_read_path(runs_dir, session_repo_runs_root())
    state_payload: dict[str, Any] = {}
    if resolved_state.exists():
        raw_state = _load_json_file(resolved_state)
        if isinstance(raw_state, dict):
            state_payload = raw_state

    history = state_payload.get("history") if isinstance(state_payload.get("history"), list) else []
    latest_runs: list[dict[str, Any]] = []
    if resolved_runs.exists():
        for path in sorted(resolved_runs.glob("*/run.json"))[-limit:]:
            try:
                run_payload = _load_json_file(path)
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(run_payload, dict):
                continue
            messages = run_payload.get("messages") if isinstance(run_payload.get("messages"), list) else []
            sent_count = _safe_int(run_payload.get("sent_count"))
            sent_messages = [
                {
                    "index": _safe_int(item.get("index")),
                    "text": str(item.get("text") or ""),
                    "sent": bool(item.get("sent")),
                    "send_mode": str(item.get("send_mode") or ""),
                }
                for item in messages
                if isinstance(item, dict) and bool(item.get("sent"))
            ]
            unsent_messages = [
                {
                    "index": _safe_int(item.get("index")),
                    "text": str(item.get("text") or ""),
                    "sent": bool(item.get("sent")),
                    "send_mode": str(item.get("send_mode") or ""),
                }
                for item in messages
                if isinstance(item, dict) and not bool(item.get("sent"))
            ]
            latest_runs.append(
                {
                    "run_id": str(run_payload.get("run_id") or path.parent.name),
                    "status": str(run_payload.get("status") or ""),
                    "visit_count": len(run_payload.get("visits") or []),
                    "message_count": len(messages),
                    "draft_count": len(unsent_messages),
                    "sent_count": sent_count,
                    "message_target_username": str(
                        ((run_payload.get("plan") or {}) if isinstance(run_payload.get("plan"), dict) else {}).get("message_target_username")
                        or ""
                    ),
                    "run_dir": str(path.parent),
                    "path": str(path),
                    "sent_messages": sent_messages[:5],
                    "unsent_messages": unsent_messages[:5],
                    "sent_preview": [str(item.get("text") or "").strip() for item in sent_messages[:2] if str(item.get("text") or "").strip()],
                    "draft_preview": [str(item.get("text") or "").strip() for item in unsent_messages[:2] if str(item.get("text") or "").strip()],
                }
            )

    last_run = latest_runs[-1] if latest_runs else {}
    return {
        "status": "ready" if resolved_state.exists() or resolved_runs.exists() else "missing",
        "state_file": str(resolved_state),
        "runs_dir": str(resolved_runs),
        "messages_sent_total": _safe_int(state_payload.get("messages_sent_total")),
        "message_cursor": _safe_int(state_payload.get("message_cursor")),
        "message_target_cursor": _safe_int(state_payload.get("message_target_cursor")),
        "history": history[-limit:],
        "latest_runs": latest_runs,
        "last_run": last_run,
    }


def session_plan(
    *,
    config_path: str | Path,
    state_file: str | Path = DEFAULT_SESSION_STATE_FILE,
) -> dict[str, Any]:
    spec = session_plan_command(config_path=config_path, state_file=state_file)
    return run_json_command(spec.argv, cwd=spec.cwd)


def session_plan_command(
    *,
    config_path: str | Path,
    state_file: str | Path = DEFAULT_SESSION_STATE_FILE,
) -> CommandSpec:
    return CommandSpec(
        argv=[
            "python3",
            "-m",
            "telegram_portable_session_tool.cli",
            "plan-session",
            "--config",
            str(ensure_session_base_config(config_path)),
            "--state-file",
            str(Path(state_file).expanduser().resolve()),
        ],
        cwd=DEFAULT_SESSION_REPO,
    )


def session_run(
    *,
    config_path: str | Path,
    state_file: str | Path = DEFAULT_SESSION_STATE_FILE,
    runs_dir: str | Path = DEFAULT_SESSION_RUNS_DIR,
    auto_send: bool = False,
    launch_if_needed: bool = True,
    continuous: bool = False,
) -> dict[str, Any]:
    spec = session_run_command(
        config_path=config_path,
        state_file=state_file,
        runs_dir=runs_dir,
        auto_send=auto_send,
        launch_if_needed=launch_if_needed,
        continuous=continuous,
    )
    return run_json_command(spec.argv, cwd=spec.cwd)


def session_run_command(
    *,
    config_path: str | Path,
    state_file: str | Path = DEFAULT_SESSION_STATE_FILE,
    runs_dir: str | Path = DEFAULT_SESSION_RUNS_DIR,
    auto_send: bool = False,
    launch_if_needed: bool = True,
    continuous: bool = False,
) -> CommandSpec:
    argv = [
        "python3",
        "-m",
        "telegram_portable_session_tool.cli",
        "run-session",
        "--config",
        str(ensure_session_base_config(config_path)),
        "--state-file",
        str(Path(state_file).expanduser().resolve()),
        "--runs-dir",
        str(Path(runs_dir).expanduser().resolve()),
        "--execute",
    ]
    if launch_if_needed:
        argv.append("--launch-if-needed")
    if auto_send:
        argv.append("--auto-send")
    if continuous:
        argv.append("--continuous")
    return CommandSpec(argv=argv, cwd=DEFAULT_SESSION_REPO)
