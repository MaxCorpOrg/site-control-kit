from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .jobs import (
    DEFAULT_JOB_INDEX_PATH,
    DEFAULT_TELEGRAM_STATE_ROOT,
    append_job_step,
    find_running_step,
    get_job,
    latest_job_step,
    list_jobs,
    normalize_runtime_payload,
    now_utc,
    profile_id_for,
    profile_workspace_snapshot,
    start_job,
    stop_job,
    update_job,
    update_job_step,
    workflow_artifact_index,
)
from .locks import acquire_profile_lock, get_profile_lock, release_profile_lock
from .platform_adapters import platform_capabilities, platform_doctor_report
from .telegram_profiles import get_profile_status


DEFAULT_WORKFLOW_STATE_ROOT = DEFAULT_TELEGRAM_STATE_ROOT / "panel_state"
LEGACY_PANEL_STATE_ROOT = Path("/tmp/telegram-control-center")
WORKFLOW_KINDS = {"invite_batch", "session_run", "combined_pattern"}
COMBINED_PHASES = {"contact_add", "review", "session_ready", "session_running", "stopped"}
RESUMABLE_WORKFLOW_STATUSES = {"planned", "stopped", "completed_with_errors", "error"}


@dataclass(frozen=True)
class CommandSpec:
    argv: list[str]
    cwd: Path


def _safe_slug(value: str, fallback: str) -> str:
    slug = "".join(char if char.isalnum() or char in "._-" else "_" for char in str(value or "").strip())
    slug = slug.strip("._-")
    return slug or fallback


def combined_flow_state_path(
    *,
    profile_name: str,
    profile_dir: str | Path,
    state_root: str | Path = DEFAULT_WORKFLOW_STATE_ROOT,
) -> Path:
    profile_slug = _safe_slug(profile_name, "profile")
    dir_name = Path(profile_dir).expanduser().resolve().name if str(profile_dir or "").strip() else "portable"
    dir_slug = _safe_slug(dir_name, "portable")
    return Path(state_root).expanduser().resolve() / "combined_flows" / f"{profile_slug}__{dir_slug}.json"


def migrate_legacy_combined_state(
    *,
    profile_name: str,
    profile_dir: str | Path,
    new_state_root: str | Path = DEFAULT_WORKFLOW_STATE_ROOT,
    legacy_state_root: str | Path = LEGACY_PANEL_STATE_ROOT,
) -> dict[str, Any] | None:
    target_path = combined_flow_state_path(
        profile_name=profile_name,
        profile_dir=profile_dir,
        state_root=new_state_root,
    )
    if target_path.exists():
        try:
            payload = json.loads(target_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    legacy_path = combined_flow_state_path(
        profile_name=profile_name,
        profile_dir=profile_dir,
        state_root=legacy_state_root,
    )
    if not legacy_path.exists():
        return None
    try:
        payload = json.loads(legacy_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def parse_combined_step_pattern(pattern_text: str) -> list[str]:
    return [char for char in str(pattern_text or "") if char in {"1", "2"}]


def combined_step_label(step_code: str) -> str:
    return "добавление контактов" if str(step_code) == "1" else "сессия и сообщения"


def default_combined_workflow_context(profile_name: str, profile_dir: str | Path) -> dict[str, Any]:
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
        "continuous_session": False,
        "invite_batch_limit": 0,
        "message_settings": {
            "auto_send": False,
            "message_targets": [],
            "message_templates": [],
            "messages_per_cycle": 0,
            "total_message_limit": 0,
            "visits_per_cycle": 6,
            "view_min_seconds": 3,
            "view_max_seconds": 6,
            "base_config_path": "",
        },
        "recent_step": {},
    }


def _combined_cache_payload_from_job(job: dict[str, Any]) -> dict[str, Any]:
    context = dict(job.get("context") or {})
    defaults = default_combined_workflow_context(
        str(job.get("profile_name") or ""),
        str(job.get("profile_dir") or ""),
    )
    merged = dict(defaults)
    merged.update({key: value for key, value in context.items() if key in defaults})
    recent_step = dict(merged.get("recent_step") or {})
    if not recent_step:
        latest_step = latest_job_step(job)
        if latest_step:
            recent_step = {
                "workflow_job_id": str(job.get("job_id") or ""),
                "step_id": str(latest_step.get("step_id") or ""),
                "step_index": int(latest_step.get("step_index") or 0),
                "step_code": str(latest_step.get("step_code") or ""),
                "step_kind": str(latest_step.get("step_kind") or ""),
                "step_status": str(latest_step.get("status") or ""),
                "started_at": str(latest_step.get("started_at") or ""),
                "completed_at": str(latest_step.get("completed_at") or ""),
                "artifact_paths": dict(latest_step.get("artifact_paths") or {}),
            }
    merged.update(
        {
            "workflow_job_id": str(job.get("job_id") or ""),
            "job_status": str(job.get("status") or ""),
            "job_summary": str(job.get("summary") or ""),
            "next_hint": str(job.get("next_hint") or ""),
            "steps_total": len([item for item in job.get("steps") or [] if isinstance(item, dict)]),
            "phase": str(job.get("phase") or merged.get("phase") or "contact_add"),
            "last_status": str(job.get("status") or merged.get("last_status") or "idle"),
            "last_summary": str(job.get("summary") or merged.get("last_summary") or ""),
            "updated_at": str(job.get("updated_at") or ""),
            "recent_step": recent_step,
        }
    )
    return merged


def sync_combined_flow_state_from_job(
    job: dict[str, Any],
    *,
    state_root: str | Path = DEFAULT_WORKFLOW_STATE_ROOT,
) -> Path:
    payload = _combined_cache_payload_from_job(job)
    path = combined_flow_state_path(
        profile_name=str(job.get("profile_name") or ""),
        profile_dir=str(job.get("profile_dir") or ""),
        state_root=state_root,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def combined_state_from_jobs(
    *,
    profile_name: str,
    profile_dir: str | Path,
    index_path: str | Path = DEFAULT_JOB_INDEX_PATH,
) -> dict[str, Any] | None:
    profile_id = profile_id_for(profile_name, profile_dir)
    jobs = list_jobs(
        profile_id=profile_id,
        workflow_kind="combined_pattern",
        limit=8,
        index_path=index_path,
    )
    if not jobs:
        return None
    preferred = next((item for item in jobs if str(item.get("status") or "") == "running"), jobs[0])
    return _combined_cache_payload_from_job(preferred)


def _runtime_config_output_path(job_id: str) -> Path:
    output_root = DEFAULT_TELEGRAM_STATE_ROOT / "runtime_configs"
    output_root.mkdir(parents=True, exist_ok=True)
    return output_root / f"{job_id}-{uuid.uuid4().hex[:8]}.json"


def _normalized_message_settings(context: dict[str, Any]) -> dict[str, Any]:
    raw = context.get("message_settings")
    payload = dict(raw) if isinstance(raw, dict) else {}
    return {
        "auto_send": bool(payload.get("auto_send")),
        "message_targets": [dict(item) for item in payload.get("message_targets") or [] if isinstance(item, dict)],
        "message_templates": [str(item).strip() for item in payload.get("message_templates") or [] if str(item).strip()],
        "messages_per_cycle": int(payload.get("messages_per_cycle") or 0),
        "total_message_limit": int(payload.get("total_message_limit") or 0),
        "visits_per_cycle": int(payload.get("visits_per_cycle") or 6),
        "view_min_seconds": int(payload.get("view_min_seconds") or 3),
        "view_max_seconds": int(payload.get("view_max_seconds") or 6),
        "base_config_path": str(payload.get("base_config_path") or "").strip(),
    }


def _stop_hint_for_workflow(workflow_kind: str) -> str:
    if workflow_kind == "invite_batch":
        return "Workflow остановлен. Можно продолжить очередь, повторить ошибки или запустить новый batch."
    if workflow_kind == "session_run":
        return "Workflow остановлен. Можно продолжить session workflow из сохранённого контекста."
    return "Workflow остановлен. Можно продолжить его через `Продолжить workflow` или перезапустить заново."


def plan_workflow(
    *,
    workflow_kind: str,
    tool_id: str,
    profile_name: str,
    profile_dir: str | Path,
    context: dict[str, Any] | None = None,
    summary: str = "",
    acquire_lock: bool = False,
    index_path: str | Path = DEFAULT_JOB_INDEX_PATH,
) -> dict[str, Any]:
    normalized_kind = str(workflow_kind or "").strip()
    if normalized_kind not in WORKFLOW_KINDS:
        raise ValueError(f"unsupported workflow kind: {workflow_kind}")
    normalized_context = dict(context or {})
    if normalized_kind == "combined_pattern":
        defaults = default_combined_workflow_context(profile_name, profile_dir)
        defaults.update({key: value for key, value in normalized_context.items() if key in defaults})
        normalized_context = defaults
    phase = str(normalized_context.get("phase") or ("contact_add" if normalized_kind == "combined_pattern" else "planned"))
    record = start_job(
        tool_id=tool_id,
        workflow_kind=normalized_kind,
        profile_name=profile_name,
        profile_dir=profile_dir,
        phase=phase,
        status="planned",
        summary=summary or "Workflow готов к запуску",
        next_hint="Запусти workflow или возобнови его через control center.",
        context=normalized_context,
        index_path=index_path,
    )
    record = update_job(
        str(record.get("job_id") or ""),
        context_patch={"workflow_job_id": str(record.get("job_id") or "")},
        index_path=index_path,
    )
    if acquire_lock:
        existing_lock = get_profile_lock(
            profile_name=profile_name,
            profile_dir=profile_dir,
        )
        if isinstance(existing_lock, dict):
            existing_job = get_job(str(existing_lock.get("job_id") or ""), index_path=index_path)
            if existing_job is None or str(existing_job.get("status") or "") in {
                "completed",
                "completed_with_errors",
                "dry_run",
                "stopped",
                "error",
            }:
                release_profile_lock(
                    profile_name=profile_name,
                    profile_dir=profile_dir,
                    owner_tool_id=str(existing_lock.get("owner_tool_id") or ""),
                    job_id=str(existing_lock.get("job_id") or ""),
                )
        lock_result = acquire_profile_lock(
            profile_name=profile_name,
            profile_dir=profile_dir,
            owner_tool_id=tool_id,
            job_id=str(record.get("job_id") or ""),
            conflict_reason="workflow_active",
        )
        if not lock_result.get("acquired"):
            conflict_text = (
                "Этот Telegram-профиль уже удерживается другим живым workflow.\n\n"
                f"Owner: {str((lock_result.get('lock') or {}).get('owner_tool_id') or '-')}\n"
                f"Job: {str((lock_result.get('lock') or {}).get('job_id') or '-')}"
            )
            record = update_job(
                str(record.get("job_id") or ""),
                status="error",
                summary=conflict_text,
                last_error=conflict_text,
                recoverable=True,
                completed=True,
                index_path=index_path,
            )
            if normalized_kind == "combined_pattern":
                sync_combined_flow_state_from_job(record)
            raise RuntimeError(conflict_text)
    if normalized_kind == "combined_pattern":
        sync_combined_flow_state_from_job(record)
    return record


def cleanup_failed_workflow_start(
    job_id: str,
    *,
    error_text: str,
    index_path: str | Path = DEFAULT_JOB_INDEX_PATH,
) -> dict[str, Any]:
    job = get_job(job_id, index_path=index_path)
    if job is None:
        raise KeyError(f"unknown job_id: {job_id}")
    phase = "review" if str(job.get("workflow_kind") or "") == "combined_pattern" else str(job.get("phase") or "planned")
    job = update_job(
        job_id,
        status="error",
        phase=phase,
        summary=str(error_text or "Не удалось запустить workflow"),
        last_error=str(error_text or "").strip(),
        recoverable=True,
        completed=True,
        context_patch={
            "phase": phase,
            "last_status": "error",
            "last_summary": str(error_text or "Не удалось запустить workflow"),
        },
        index_path=index_path,
    )
    release_profile_lock(
        profile_name=str(job.get("profile_name") or ""),
        profile_dir=str(job.get("profile_dir") or ""),
        owner_tool_id=str(job.get("tool_id") or ""),
        job_id=job_id,
    )
    if str(job.get("workflow_kind") or "") == "combined_pattern":
        sync_combined_flow_state_from_job(job)
    return job


def status_workflow(job_id: str, *, index_path: str | Path = DEFAULT_JOB_INDEX_PATH) -> dict[str, Any]:
    payload = get_job(job_id, index_path=index_path)
    if payload is None:
        raise KeyError(f"unknown job_id: {job_id}")
    return payload


def artifacts_workflow(job_id: str, *, index_path: str | Path = DEFAULT_JOB_INDEX_PATH) -> dict[str, Any]:
    payload = get_job(job_id, index_path=index_path)
    if payload is None:
        raise KeyError(f"unknown job_id: {job_id}")
    return {
        "job_id": job_id,
        "workflow_kind": str(payload.get("workflow_kind") or ""),
        "artifact_paths": workflow_artifact_index(job_id, index_path=index_path),
        "steps": [dict(item) for item in payload.get("steps") or [] if isinstance(item, dict)],
    }


def _build_invite_batch_command(job: dict[str, Any]) -> CommandSpec:
    from .telegram_gui_helpers import contact_add_batch_command

    context = dict(job.get("context") or {})
    command = contact_add_batch_command(
        input_path=context.get("input_path"),
        job_dir=str(context.get("invite_job_dir") or ""),
        profile_name=str(job.get("profile_name") or ""),
        portable_profile_dir=str(job.get("profile_dir") or ""),
        account_username=str(context.get("account_username") or ""),
        account_label=str(context.get("account_label") or ""),
        limit=int(context.get("invite_batch_limit") or 0),
        output_root=str(context.get("output_root") or ""),
        statuses=[str(item) for item in context.get("statuses") or [] if str(item).strip()] or None,
        dry_run=bool(context.get("dry_run")),
    )
    return CommandSpec(argv=list(command.argv), cwd=command.cwd)


def _build_session_run_command(job: dict[str, Any]) -> tuple[CommandSpec, Path]:
    from .telegram_gui_helpers import build_session_runtime_config, session_run_command

    context = dict(job.get("context") or {})
    settings = _normalized_message_settings(context)
    runtime_config = build_session_runtime_config(
        base_config_path=settings["base_config_path"],
        output_path=_runtime_config_output_path(str(job.get("job_id") or "")),
        message_targets=settings["message_targets"],
        message_templates=settings["message_templates"],
        drafts_per_run=settings["messages_per_cycle"],
        total_message_limit=settings["total_message_limit"],
        portable_profile_dir=str(job.get("profile_dir") or ""),
        auto_send=bool(settings["auto_send"]),
        session_overrides={
            "random_walk_visits_per_run": settings["visits_per_cycle"],
            "view_min_seconds": settings["view_min_seconds"],
            "view_max_seconds": settings["view_max_seconds"],
        },
    )
    command = session_run_command(
        config_path=runtime_config,
        auto_send=bool(settings["auto_send"]),
        continuous=bool(context.get("continuous_session")),
    )
    return CommandSpec(argv=list(command.argv), cwd=command.cwd), runtime_config


def _combined_current_step(context: dict[str, Any]) -> tuple[list[str], int, str]:
    tokens = parse_combined_step_pattern(str(context.get("step_pattern") or ""))
    if not tokens:
        tokens = ["1", "2"]
    raw_cursor = context.get("step_cursor")
    try:
        cursor = int(raw_cursor)
    except (TypeError, ValueError):
        cursor = 0
    cursor = max(cursor, 0) % len(tokens)
    return tokens, cursor, tokens[cursor]


def _combined_advance_cursor(context: dict[str, Any]) -> tuple[list[str], int, str]:
    tokens, cursor, _ = _combined_current_step(context)
    next_cursor = (cursor + 1) % len(tokens)
    return tokens, next_cursor, tokens[next_cursor]


def _combined_contact_transition(context: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    payload_status = str(payload.get("status") or "").strip().lower() or "completed"
    selected_users = int(payload.get("selected_users") or 0)
    remaining_candidates = int(payload.get("remaining_candidates") or 0)
    failed_count = int(payload.get("failed_count") or 0)
    had_previous_session = bool(
        str(context.get("last_session_status") or "").strip()
        or str(context.get("last_session_run_dir") or "").strip()
    )
    session_continuous = bool(context.get("continuous_session"))

    if payload_status == "completed_with_errors":
        if selected_users > 0:
            return {
                "terminal": False,
                "phase": "session_ready",
                "last_action": "combined_contact_add_finished_auto",
                "last_status": payload_status,
                "status_text": (
                    "Часть контактов добавлена, ошибки сохранены, запускаю непрерывную сессию"
                    if session_continuous
                    else "Часть контактов добавлена, ошибки сохранены, запускаю шаг сессии"
                ),
                "auto_step": "2",
                "job_status": "running",
            }
        return {
            "terminal": True,
            "phase": "review",
            "last_action": "combined_contact_add_finished",
            "last_status": payload_status,
            "status_text": "Шаг добавления завершился с ошибками и требует проверки",
            "job_status": "completed_with_errors",
        }

    if selected_users == 0 and failed_count == 0:
        if had_previous_session and remaining_candidates == 0:
            return {
                "terminal": True,
                "phase": "stopped",
                "last_action": "combined_contact_add_noop_after_session",
                "last_status": "completed",
                "status_text": "Очередь контактов закончилась, совместный режим завершён",
                "job_status": "completed",
            }
        return {
            "terminal": True,
            "phase": "stopped",
            "last_action": "combined_contact_add_noop",
            "last_status": "no_new_usernames",
            "status_text": "Новых username для добавления нет; выбери другой файл или запускай сессию",
            "job_status": "completed",
        }

    return {
        "terminal": False,
        "phase": "session_ready",
        "last_action": "combined_contact_add_finished_auto",
        "last_status": payload_status,
        "status_text": (
            "Контакты добавлены, запускаю непрерывную сессию"
            if session_continuous
            else "Контакты добавлены, запускаю шаг сессии"
        ),
        "auto_step": "2",
        "job_status": "running",
    }


def _combined_session_transition(
    context: dict[str, Any],
    payload: dict[str, Any],
    *,
    invite_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    payload_status = str(payload.get("status") or "").strip().lower() or "completed"
    pending_total = int((invite_snapshot or {}).get("pending_total") or 0)
    session_continuous = bool(context.get("continuous_session"))

    if payload_status == "stopped":
        return {
            "terminal": True,
            "phase": "stopped",
            "last_action": "combined_session_finished",
            "last_status": "stopped",
            "status_text": "Сессия остановлена",
            "job_status": "stopped",
        }

    if pending_total > 0 and not session_continuous and payload_status == "completed":
        return {
            "terminal": False,
            "phase": "contact_add",
            "last_action": "combined_session_finished_next_contact",
            "last_status": payload_status,
            "status_text": f"Осталось username: {pending_total}. Запускаю следующий шаг добавления",
            "auto_step": "1",
            "job_status": "running",
        }

    status_text = (
        "Непрерывная сессия завершила свой шаг"
        if session_continuous and payload_status == "completed"
        else "Совместный режим завершил шаг сессии"
        if payload_status == "completed"
        else f"Сессия завершилась со статусом: {payload_status}"
    )
    return {
        "terminal": True,
        "phase": "stopped",
        "last_action": "combined_session_finished",
        "last_status": payload_status,
        "status_text": status_text,
        "job_status": "completed" if payload_status == "completed" else "completed_with_errors",
    }


def _combined_invite_snapshot(job: dict[str, Any]) -> dict[str, Any] | None:
    from .telegram_gui_helpers import contact_job_snapshot

    context = dict(job.get("context") or {})
    invite_job_dir = str(context.get("invite_job_dir") or "").strip()
    if not invite_job_dir:
        return None
    return contact_job_snapshot(invite_job_dir)


def _build_command_for_job(job: dict[str, Any]) -> tuple[str, str, CommandSpec, dict[str, Any]]:
    workflow_kind = str(job.get("workflow_kind") or "").strip()
    context = dict(job.get("context") or {})
    if workflow_kind == "invite_batch":
        command = _build_invite_batch_command(job)
        return (
            "1",
            "invite_batch",
            command,
            {
                "phase": "contact_add",
                "action_label": str(context.get("action_label") or "добавление контактов"),
                "context_patch": {},
            },
        )
    if workflow_kind == "session_run":
        command, runtime_config = _build_session_run_command(job)
        return (
            "2",
            "session_run",
            command,
            {
                "phase": "session_running",
                "action_label": str(context.get("action_label") or "запуск session runner"),
                "context_patch": {"last_runtime_config_path": str(runtime_config)},
            },
        )
    if workflow_kind != "combined_pattern":
        raise ValueError(f"unsupported workflow kind: {workflow_kind}")
    tokens, cursor, step_code = _combined_current_step(context)
    if step_code == "1":
        command = _build_invite_batch_command(
            {
                **job,
                "context": {
                    **context,
                    "input_path": str(context.get("input_path") or ""),
                    "statuses": ["new", "checked"],
                    "action_label": "совместный шаг: добавление контактов",
                },
            }
        )
        return (
            step_code,
            "invite_batch",
            command,
            {
                "phase": "contact_add",
                "action_label": "совместный шаг: добавление контактов",
                "context_patch": {
                    "step_cursor": cursor,
                    "step_label": combined_step_label(step_code),
                    "last_action": "combined_contact_add_started",
                    "last_status": "running",
                },
            },
        )
    command, runtime_config = _build_session_run_command(job)
    return (
        step_code,
        "session_run",
        command,
        {
            "phase": "session_running",
            "action_label": "совместный шаг: запуск сессии",
            "context_patch": {
                "step_cursor": cursor,
                "step_label": combined_step_label(step_code),
                "last_runtime_config_path": str(runtime_config),
                "last_action": "combined_session_started",
                "last_status": "running",
            },
        },
    )


def run_workflow(job_id: str, *, index_path: str | Path = DEFAULT_JOB_INDEX_PATH) -> dict[str, Any]:
    job = get_job(job_id, index_path=index_path)
    if job is None:
        raise KeyError(f"unknown job_id: {job_id}")
    running_step = find_running_step(job)
    if running_step is not None:
        return {"status": "already_running", "job": job, "command": None, "step": dict(running_step)}
    current_status = str(job.get("status") or "").strip().lower()
    current_kind = str(job.get("workflow_kind") or "").strip()
    if current_status in {"completed", "dry_run"} and current_kind != "combined_pattern":
        return {"status": "terminal", "job": job, "command": None}
    if current_status in {"completed_with_errors", "stopped", "error"} and current_kind != "combined_pattern":
        if not bool(job.get("recoverable", True)):
            return {"status": "terminal", "job": job, "command": None}

    step_code, step_kind, command, metadata = _build_command_for_job(job)
    step = append_job_step(
        job_id,
        step_code=step_code,
        step_kind=step_kind,
        action_label=str(metadata["action_label"]),
        status="running",
        summary=f"Выполняется: {metadata['action_label']}",
        index_path=index_path,
    )
    job = update_job(
        job_id,
        status="running",
        phase=str(metadata["phase"]),
        summary=f"Выполняется: {metadata['action_label']}",
        next_hint="Дождись завершения subprocess или нажми `Стоп`.",
        context_patch={
            **dict(metadata.get("context_patch") or {}),
            "recent_step": {
                "workflow_job_id": job_id,
                "step_id": str(step.get("step_id") or ""),
                "step_index": int(step.get("step_index") or 0),
                "step_code": str(step.get("step_code") or ""),
                "step_kind": str(step.get("step_kind") or ""),
                "step_status": "running",
                "started_at": str(step.get("started_at") or ""),
                "completed_at": "",
                "artifact_paths": {},
            },
        },
        index_path=index_path,
    )
    if str(job.get("workflow_kind") or "") == "combined_pattern":
        sync_combined_flow_state_from_job(job)
    return {
        "status": "ready",
        "job": job,
        "command": command,
        "step": step,
        "action_label": str(metadata["action_label"]),
    }


def complete_workflow_step(
    job_id: str,
    *,
    payload: dict[str, Any] | None = None,
    error_text: str = "",
    stopped: bool = False,
    index_path: str | Path = DEFAULT_JOB_INDEX_PATH,
) -> dict[str, Any]:
    job = get_job(job_id, index_path=index_path)
    if job is None:
        raise KeyError(f"unknown job_id: {job_id}")
    running_step = find_running_step(job)
    if running_step is None:
        return {"status": "no_running_step", "job": job, "next_command": None}

    workflow_kind = str(job.get("workflow_kind") or "")
    step_id = str(running_step.get("step_id") or "")
    step_code = str(running_step.get("step_code") or "")
    context = dict(job.get("context") or {})

    if stopped:
        update_job_step(
            job_id,
            step_id=step_id,
            status="stopped",
            summary="Остановлено оператором",
            completed=True,
            index_path=index_path,
        )
        job = stop_job(
            job_id,
            summary="Остановлено оператором",
            phase="stopped",
            index_path=index_path,
        )
        job = update_job(
            job_id,
            next_hint=_stop_hint_for_workflow(workflow_kind),
            recoverable=True,
            index_path=index_path,
        )
        release_profile_lock(
            profile_name=str(job.get("profile_name") or ""),
            profile_dir=str(job.get("profile_dir") or ""),
            owner_tool_id=str(job.get("tool_id") or ""),
            job_id=job_id,
        )
        if workflow_kind == "combined_pattern":
            job = update_job(
                job_id,
                context_patch={
                    "phase": "stopped",
                    "last_action": "combined_session_finished" if step_code == "2" else "combined_contact_add_finished",
                    "last_status": "stopped",
                    "last_summary": "Остановлено оператором",
                    "recent_step": {
                        "workflow_job_id": job_id,
                        "step_id": step_id,
                        "step_index": int(running_step.get("step_index") or 0),
                        "step_code": step_code,
                        "step_kind": str(running_step.get("step_kind") or ""),
                        "step_status": "stopped",
                        "started_at": str(running_step.get("started_at") or ""),
                        "completed_at": now_utc(),
                        "artifact_paths": {},
                    },
                },
                index_path=index_path,
            )
            sync_combined_flow_state_from_job(job)
        return {"status": "stopped", "job": job, "next_command": None}

    if error_text:
        update_job_step(
            job_id,
            step_id=step_id,
            status="error",
            summary=error_text,
            completed=True,
            index_path=index_path,
        )
        terminal_phase = "review" if workflow_kind == "combined_pattern" and step_code == "1" else "stopped"
        terminal_status = "completed_with_errors" if workflow_kind == "combined_pattern" else "error"
        job = update_job(
            job_id,
            status=terminal_status,
            phase=terminal_phase,
            summary=error_text,
            last_error=error_text,
            recoverable=True,
            completed=True,
            context_patch={
                "phase": terminal_phase,
                "last_status": "error",
                "last_summary": error_text,
                "recent_step": {
                    "workflow_job_id": job_id,
                    "step_id": step_id,
                    "step_index": int(running_step.get("step_index") or 0),
                    "step_code": step_code,
                    "step_kind": str(running_step.get("step_kind") or ""),
                    "step_status": "error",
                    "started_at": str(running_step.get("started_at") or ""),
                    "completed_at": now_utc(),
                    "artifact_paths": {},
                },
            },
            index_path=index_path,
        )
        release_profile_lock(
            profile_name=str(job.get("profile_name") or ""),
            profile_dir=str(job.get("profile_dir") or ""),
            owner_tool_id=str(job.get("tool_id") or ""),
            job_id=job_id,
        )
        if workflow_kind == "combined_pattern":
            sync_combined_flow_state_from_job(job)
        return {"status": "error", "job": job, "next_command": None}

    normalized = normalize_runtime_payload(payload, fallback_status="completed", fallback_phase=str(job.get("phase") or ""))
    step_artifacts = dict(normalized["artifact_paths"])
    update_job_step(
        job_id,
        step_id=step_id,
        status=str(normalized["status"]),
        summary=str(normalized["summary"]),
        artifact_paths=step_artifacts,
        completed=True,
        index_path=index_path,
    )
    base_context_patch = {
        "recent_step": {
            "workflow_job_id": job_id,
            "step_id": step_id,
            "step_index": int(running_step.get("step_index") or 0),
            "step_code": step_code,
            "step_kind": str(running_step.get("step_kind") or ""),
            "step_status": str(normalized["status"]),
            "started_at": str(running_step.get("started_at") or ""),
            "completed_at": now_utc(),
            "artifact_paths": step_artifacts,
        },
    }

    if workflow_kind == "invite_batch":
        job = update_job(
            job_id,
            status=str(normalized["status"]),
            phase="stopped" if str(normalized["status"]) in {"completed", "completed_with_errors", "dry_run"} else str(normalized["phase"]),
            summary=str(normalized["summary"]),
            artifact_paths=step_artifacts,
            next_hint=str(normalized["next_hint"] or ("Повтори ошибки или продолжи очередь через control center." if str(normalized["status"]) == "completed_with_errors" else "")),
            recoverable=bool(normalized["recoverable"]),
            completed=True,
            context_patch=base_context_patch,
            index_path=index_path,
        )
        release_profile_lock(
            profile_name=str(job.get("profile_name") or ""),
            profile_dir=str(job.get("profile_dir") or ""),
            owner_tool_id=str(job.get("tool_id") or ""),
            job_id=job_id,
        )
        return {"status": "completed", "job": job, "next_command": None}

    if workflow_kind == "session_run":
        job = update_job(
            job_id,
            status=str(normalized["status"]),
            phase="stopped",
            summary=str(normalized["summary"]),
            artifact_paths=step_artifacts,
            next_hint=str(normalized["next_hint"] or (_stop_hint_for_workflow("session_run") if str(normalized["status"]) in {"stopped", "completed_with_errors", "error"} else "")),
            recoverable=bool(normalized["recoverable"]),
            completed=True,
            context_patch={
                **base_context_patch,
                "last_status": str(normalized["status"]),
                "last_summary": str(normalized["summary"]),
                "last_session_status": str(normalized["status"]),
                "last_session_run_dir": str(step_artifacts.get("run_dir") or ""),
            },
            index_path=index_path,
        )
        release_profile_lock(
            profile_name=str(job.get("profile_name") or ""),
            profile_dir=str(job.get("profile_dir") or ""),
            owner_tool_id=str(job.get("tool_id") or ""),
            job_id=job_id,
        )
        return {"status": "completed", "job": job, "next_command": None}

    invite_snapshot = _combined_invite_snapshot(job)
    if step_code == "1":
        transition = _combined_contact_transition(context, payload or {})
        _, next_cursor, next_step = _combined_advance_cursor(context)
        context_patch = {
            **base_context_patch,
            "phase": str(transition["phase"]),
            "step_cursor": next_cursor,
            "step_label": combined_step_label(next_step),
            "last_action": str(transition["last_action"]),
            "last_status": str(transition["last_status"]),
            "last_summary": str(normalized["summary"]),
            "last_invite_status": str(normalized["status"]),
        }
    else:
        transition = _combined_session_transition(context, payload or {}, invite_snapshot=invite_snapshot)
        _, next_cursor, next_step = _combined_advance_cursor(context)
        context_patch = {
            **base_context_patch,
            "phase": str(transition["phase"]),
            "step_cursor": next_cursor,
            "step_label": combined_step_label(next_step),
            "last_action": str(transition["last_action"]),
            "last_status": str(transition["last_status"]),
            "last_summary": str(normalized["summary"]),
            "last_session_status": str(normalized["status"]),
            "last_session_run_dir": str(step_artifacts.get("run_dir") or ""),
        }

    job = update_job(
        job_id,
        status=str(transition["job_status"]),
        phase=str(transition["phase"]),
        summary=str(transition["status_text"]),
        artifact_paths=step_artifacts,
        next_hint="Стартую следующий шаг по шаблону." if not bool(transition["terminal"]) else "Workflow завершён.",
        recoverable=bool(str(transition["job_status"]) in {"completed_with_errors", "stopped", "error"}),
        completed=bool(transition["terminal"]),
        context_patch=context_patch,
        index_path=index_path,
    )
    sync_combined_flow_state_from_job(job)
    if bool(transition["terminal"]):
        release_profile_lock(
            profile_name=str(job.get("profile_name") or ""),
            profile_dir=str(job.get("profile_dir") or ""),
            owner_tool_id=str(job.get("tool_id") or ""),
            job_id=job_id,
        )
        return {"status": "completed", "job": job, "next_command": None}

    next_execution = run_workflow(job_id, index_path=index_path)
    return {
        "status": "continued",
        "job": next_execution.get("job"),
        "next_command": next_execution.get("command"),
        "next_step": next_execution.get("step"),
        "next_action_label": next_execution.get("action_label"),
    }


def resume_workflow(job_id: str, *, index_path: str | Path = DEFAULT_JOB_INDEX_PATH) -> dict[str, Any]:
    job = get_job(job_id, index_path=index_path)
    if job is None:
        raise KeyError(f"unknown job_id: {job_id}")
    if str(job.get("status") or "") == "running" and find_running_step(job) is not None:
        return {"status": "already_running", "job": job, "command": None}
    return run_workflow(job_id, index_path=index_path)


def stop_workflow_job(job_id: str, *, summary: str = "Остановлено", index_path: str | Path = DEFAULT_JOB_INDEX_PATH) -> dict[str, Any]:
    job = get_job(job_id, index_path=index_path)
    if job is None:
        raise KeyError(f"unknown job_id: {job_id}")
    running_step = find_running_step(job)
    recent_step_patch: dict[str, Any] | None = None
    last_action = "workflow_stopped"
    if running_step is not None:
        step_code = str(running_step.get("step_code") or "")
        recent_step_patch = {
            "workflow_job_id": job_id,
            "step_id": str(running_step.get("step_id") or ""),
            "step_index": int(running_step.get("step_index") or 0),
            "step_code": step_code,
            "step_kind": str(running_step.get("step_kind") or ""),
            "step_status": "stopped",
            "started_at": str(running_step.get("started_at") or ""),
            "completed_at": now_utc(),
            "artifact_paths": dict(running_step.get("artifact_paths") or {}),
        }
        if step_code == "1":
            last_action = "combined_contact_add_stopped"
        elif step_code == "2":
            last_action = "combined_session_stopped"
        update_job_step(
            job_id,
            step_id=str(running_step.get("step_id") or ""),
            status="stopped",
            summary=summary,
            completed=True,
            index_path=index_path,
        )
    job = stop_job(job_id, summary=summary, phase="stopped", index_path=index_path)
    release_profile_lock(
        profile_name=str(job.get("profile_name") or ""),
        profile_dir=str(job.get("profile_dir") or ""),
        owner_tool_id=str(job.get("tool_id") or ""),
        job_id=job_id,
    )
    if str(job.get("workflow_kind") or "") == "combined_pattern":
        job = update_job(
            job_id,
            next_hint="Workflow остановлен. Можно продолжить его через `Продолжить workflow` или перезапустить заново.",
            recoverable=True,
            context_patch={
                "phase": "stopped",
                "last_action": last_action,
                "last_status": "stopped",
                "last_summary": summary,
                "recent_step": recent_step_patch or {},
            },
            index_path=index_path,
        )
        sync_combined_flow_state_from_job(job)
    return job


def profile_health(
    *,
    profile_name: str,
    profile_dir: str | Path,
    index_path: str | Path = DEFAULT_JOB_INDEX_PATH,
) -> dict[str, Any]:
    profile_id = profile_id_for(profile_name, profile_dir)
    doctor = platform_doctor_report()
    capabilities = platform_capabilities()
    jobs = list_jobs(profile_id=profile_id, limit=10, index_path=index_path)
    active_jobs = [item for item in jobs if str(item.get("status") or "") == "running"]
    lock = get_profile_lock(profile_name=profile_name, profile_dir=profile_dir)
    try:
        profile_status = get_profile_status(profile_dir)
    except Exception as exc:
        profile_status = {"status": "error", "error": str(exc), "running": False, "windows": []}
    workspace = profile_workspace_snapshot(
        profile_name=profile_name,
        profile_dir=profile_dir,
        limit=5,
        timeline_limit=8,
        index_path=index_path,
    )
    return {
        "profile_id": profile_id,
        "profile_name": str(profile_name or ""),
        "profile_dir": str(Path(profile_dir).expanduser().resolve()),
        "profile_status": profile_status,
        "lock": lock,
        "active_jobs": active_jobs,
        "recent_jobs": jobs[:5],
        "last_successful_job": workspace.get("last_successful_job"),
        "artifact_index": workspace.get("artifact_index"),
        "workflow_buckets": workspace.get("workflow_buckets"),
        "doctor": doctor,
        "capabilities": capabilities,
    }
