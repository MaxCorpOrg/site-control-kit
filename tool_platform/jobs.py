from __future__ import annotations

import json
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_TELEGRAM_STATE_ROOT = Path.home() / ".site-control-kit" / "telegram"
DEFAULT_JOB_INDEX_PATH = DEFAULT_TELEGRAM_STATE_ROOT / "jobs" / "index.json"
DEFAULT_PANEL_LOG_PATH = Path("/tmp/telegram-control-center-panel.log")
DEFAULT_TIMELINE_LIMIT = 20
WORKSPACE_WORKFLOW_KINDS = ("invite_batch", "session_run", "combined_pattern")
JOB_STATUSES = {
    "idle",
    "planned",
    "running",
    "completed",
    "completed_with_errors",
    "dry_run",
    "stopped",
    "error",
}
WORKFLOW_KINDS = {
    "",
    "invite_batch",
    "session_run",
    "combined_pattern",
}
STEP_STATUSES = {
    "planned",
    "running",
    "completed",
    "completed_with_errors",
    "dry_run",
    "stopped",
    "error",
}
RESUMABLE_JOB_STATUSES = {"planned", "stopped", "completed_with_errors", "error"}
SUCCESSFUL_JOB_STATUSES = {"completed", "dry_run"}
ARTIFACT_CENTER_LABELS = {
    "panel_log": "Лог панели",
    "batch_json": "Последний batch json",
    "session_run": "Последний session run",
    "execution_record": "Последний execution record",
    "screenshot": "Последний screenshot",
}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_slug(value: str, fallback: str) -> str:
    filtered = "".join(char if char.isalnum() or char in "._-" else "_" for char in str(value or "").strip())
    filtered = filtered.strip("._-")
    return filtered or fallback


def profile_id_for(profile_name: str, profile_dir: str | Path) -> str:
    profile_slug = _safe_slug(profile_name, "profile")
    dir_name = Path(profile_dir).expanduser().resolve().name if str(profile_dir or "").strip() else "portable"
    return f"{profile_slug}__{_safe_slug(dir_name, 'portable')}"


def default_job_index() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "updated_at": "",
        "jobs": [],
    }


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(path.parent)) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temp_path = Path(handle.name)
    temp_path.replace(path)
    return path


def _normalize_artifact_paths(payload: Any) -> dict[str, str]:
    if not isinstance(payload, dict):
        return {}
    return {
        str(key): str(value)
        for key, value in payload.items()
        if str(key).strip() and str(value).strip()
    }


def _job_status(job: dict[str, Any] | None) -> str:
    if not isinstance(job, dict):
        return ""
    return str(job.get("status") or "").strip().lower()


def _job_timestamp(job: dict[str, Any] | None) -> str:
    if not isinstance(job, dict):
        return ""
    return str(
        job.get("updated_at")
        or job.get("completed_at")
        or job.get("started_at")
        or ""
    ).strip()


def _job_is_resumable(job: dict[str, Any] | None) -> bool:
    status = _job_status(job)
    if status == "planned":
        return True
    if status in {"stopped", "completed_with_errors", "error"}:
        return bool((job or {}).get("recoverable", True))
    return False


def _job_is_success_like(job: dict[str, Any] | None) -> bool:
    return _job_status(job) in SUCCESSFUL_JOB_STATUSES


def _normalize_step_record(step: dict[str, Any], *, position: int) -> dict[str, Any]:
    payload = dict(step)
    status = str(payload.get("status") or "planned").strip().lower() or "planned"
    if status not in STEP_STATUSES:
        status = "planned"
    completed_at = str(payload.get("completed_at") or "").strip()
    if not completed_at and status in {"completed", "completed_with_errors", "dry_run", "stopped", "error"}:
        completed_at = str(payload.get("updated_at") or payload.get("started_at") or now_utc()).strip()
    return {
        "workflow_job_id": str(payload.get("workflow_job_id") or "").strip(),
        "step_id": str(payload.get("step_id") or f"step-{position + 1}").strip(),
        "step_index": int(payload.get("step_index") if str(payload.get("step_index") or "").strip() else position),
        "step_code": str(payload.get("step_code") or "").strip(),
        "step_kind": str(payload.get("step_kind") or "").strip(),
        "status": status,
        "summary": str(payload.get("summary") or "").strip(),
        "started_at": str(payload.get("started_at") or "").strip(),
        "completed_at": completed_at,
        "artifact_paths": _normalize_artifact_paths(payload.get("artifact_paths")),
        "action_label": str(payload.get("action_label") or "").strip(),
    }


def _job_record_defaults(
    *,
    job_id: str,
    tool_id: str,
    workflow_kind: str,
    profile_name: str,
    profile_dir: str | Path,
    status: str,
    phase: str,
    summary: str,
    artifact_paths: dict[str, str] | None = None,
    next_hint: str = "",
    recoverable: bool = False,
    context: dict[str, Any] | None = None,
    steps: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized_workflow_kind = str(workflow_kind or "").strip()
    if normalized_workflow_kind not in WORKFLOW_KINDS:
        normalized_workflow_kind = ""
    normalized_steps = [
        _normalize_step_record(item, position=index)
        for index, item in enumerate(steps or [])
        if isinstance(item, dict)
    ]
    return {
        "job_id": job_id,
        "tool_id": str(tool_id),
        "workflow_kind": normalized_workflow_kind,
        "profile_name": str(profile_name or "").strip() or "profile",
        "profile_dir": str(Path(profile_dir).expanduser().resolve()) if str(profile_dir or "").strip() else "",
        "profile_id": profile_id_for(profile_name, profile_dir),
        "status": str(status or "running"),
        "phase": str(phase or "").strip(),
        "summary": str(summary or "").strip(),
        "artifact_paths": dict(artifact_paths or {}),
        "next_hint": str(next_hint or "").strip(),
        "recoverable": bool(recoverable),
        "context": dict(context or {}),
        "steps": normalized_steps,
        "started_at": now_utc(),
        "updated_at": now_utc(),
        "completed_at": "",
        "last_error": "",
    }


def normalize_job_record(payload: dict[str, Any]) -> dict[str, Any]:
    job_id = str(payload.get("job_id") or f"legacy-{uuid.uuid4().hex[:8]}")
    record = _job_record_defaults(
        job_id=job_id,
        tool_id=str(payload.get("tool_id") or ""),
        workflow_kind=str(payload.get("workflow_kind") or ""),
        profile_name=str(payload.get("profile_name") or ""),
        profile_dir=str(payload.get("profile_dir") or ""),
        status=str(payload.get("status") or "running"),
        phase=str(payload.get("phase") or ""),
        summary=str(payload.get("summary") or ""),
        artifact_paths=_normalize_artifact_paths(payload.get("artifact_paths")),
        next_hint=str(payload.get("next_hint") or ""),
        recoverable=bool(payload.get("recoverable")),
        context=dict(payload.get("context") or {}) if isinstance(payload.get("context"), dict) else {},
        steps=[item for item in payload.get("steps") or [] if isinstance(item, dict)] if isinstance(payload.get("steps"), list) else [],
    )
    record["started_at"] = str(payload.get("started_at") or record["started_at"]).strip()
    record["updated_at"] = str(payload.get("updated_at") or record["updated_at"]).strip()
    record["completed_at"] = str(payload.get("completed_at") or "").strip()
    record["last_error"] = str(payload.get("last_error") or "").strip()
    normalized_status = str(record.get("status") or "running").strip().lower()
    if normalized_status not in JOB_STATUSES:
        record["status"] = "running"
    else:
        record["status"] = normalized_status
    if not record["completed_at"] and record["status"] in {"completed", "completed_with_errors", "dry_run", "stopped", "error"}:
        record["completed_at"] = record["updated_at"] or now_utc()
    return record


def load_job_index(index_path: str | Path = DEFAULT_JOB_INDEX_PATH) -> dict[str, Any]:
    resolved = Path(index_path).expanduser().resolve()
    payload = _load_json(resolved)
    index = default_job_index()
    jobs = payload.get("jobs")
    if isinstance(jobs, list):
        index["jobs"] = [normalize_job_record(item) for item in jobs if isinstance(item, dict)]
    updated_at = str(payload.get("updated_at") or "").strip()
    if updated_at:
        index["updated_at"] = updated_at
    return index


def save_job_index(payload: dict[str, Any], index_path: str | Path = DEFAULT_JOB_INDEX_PATH) -> Path:
    resolved = Path(index_path).expanduser().resolve()
    index = default_job_index()
    index["jobs"] = [
        normalize_job_record(item)
        for item in list(payload.get("jobs", []))
        if isinstance(item, dict)
    ]
    index["updated_at"] = now_utc()
    return _atomic_write_json(resolved, index)


def normalize_runtime_payload(
    payload: dict[str, Any] | None,
    *,
    fallback_status: str = "completed",
    fallback_phase: str = "",
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        payload = {}
    status = str(payload.get("status") or fallback_status).strip().lower() or fallback_status
    if status not in JOB_STATUSES:
        status = fallback_status
    phase = str(payload.get("phase") or fallback_phase).strip()
    summary = str(payload.get("summary") or "").strip()
    if not summary:
        if status == "completed_with_errors":
            summary = "Завершено с ошибками"
        elif status == "dry_run":
            summary = "Проверка завершена"
        elif status == "stopped":
            summary = "Остановлено"
        elif status == "error":
            summary = str(payload.get("error") or "Ошибка")
        else:
            summary = "Завершено"
    artifact_paths = payload.get("artifact_paths")
    normalized_artifacts: dict[str, str] = {}
    if isinstance(artifact_paths, dict):
        normalized_artifacts.update(_normalize_artifact_paths(artifact_paths))
    for key in ("run_dir", "job_dir", "state_path", "runtime_config", "log_path", "screenshot_path"):
        value = str(payload.get(key) or "").strip()
        if value:
            normalized_artifacts[key] = value
    next_hint = str(payload.get("next_hint") or "").strip()
    recoverable_raw = payload.get("recoverable")
    recoverable = bool(recoverable_raw) if recoverable_raw is not None else status in {"completed_with_errors", "stopped", "error"}
    return {
        "status": status,
        "phase": phase,
        "summary": summary,
        "artifact_paths": normalized_artifacts,
        "next_hint": next_hint,
        "recoverable": recoverable,
    }


def _find_job_index(jobs: list[dict[str, Any]], job_id: str) -> int:
    for index, item in enumerate(jobs):
        if str(item.get("job_id") or "") == str(job_id):
            return index
    return -1


def start_job(
    *,
    tool_id: str,
    profile_name: str,
    profile_dir: str | Path,
    phase: str,
    summary: str,
    artifact_paths: dict[str, str] | None = None,
    next_hint: str = "",
    workflow_kind: str = "",
    context: dict[str, Any] | None = None,
    status: str = "running",
    recoverable: bool = False,
    steps: list[dict[str, Any]] | None = None,
    index_path: str | Path = DEFAULT_JOB_INDEX_PATH,
) -> dict[str, Any]:
    index = load_job_index(index_path)
    job_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    record = _job_record_defaults(
        job_id=job_id,
        tool_id=tool_id,
        workflow_kind=workflow_kind,
        profile_name=profile_name,
        profile_dir=profile_dir,
        status=status,
        phase=phase,
        summary=summary,
        artifact_paths=artifact_paths,
        next_hint=next_hint,
        recoverable=recoverable,
        context=context,
        steps=steps,
    )
    normalized_status = str(status or "running").strip().lower() or "running"
    record["status"] = normalized_status if normalized_status in JOB_STATUSES else "running"
    index["jobs"].append(record)
    save_job_index(index, index_path)
    return record


def update_job(
    job_id: str,
    *,
    status: str | None = None,
    phase: str | None = None,
    summary: str | None = None,
    artifact_paths: dict[str, str] | None = None,
    next_hint: str | None = None,
    recoverable: bool | None = None,
    last_error: str | None = None,
    completed: bool | None = None,
    context_patch: dict[str, Any] | None = None,
    replace_context: dict[str, Any] | None = None,
    steps: list[dict[str, Any]] | None = None,
    workflow_kind: str | None = None,
    index_path: str | Path = DEFAULT_JOB_INDEX_PATH,
) -> dict[str, Any]:
    index = load_job_index(index_path)
    position = _find_job_index(index["jobs"], job_id)
    if position < 0:
        raise KeyError(f"unknown job_id: {job_id}")
    record = normalize_job_record(index["jobs"][position])
    if status is not None:
        normalized_status = str(status or "").strip().lower() or record.get("status", "running")
        record["status"] = normalized_status if normalized_status in JOB_STATUSES else record.get("status", "running")
    if phase is not None:
        record["phase"] = str(phase or "").strip()
    if summary is not None:
        record["summary"] = str(summary or "").strip()
    if artifact_paths is not None:
        merged = dict(record.get("artifact_paths") or {})
        merged.update(_normalize_artifact_paths(artifact_paths))
        record["artifact_paths"] = merged
    if next_hint is not None:
        record["next_hint"] = str(next_hint or "").strip()
    if recoverable is not None:
        record["recoverable"] = bool(recoverable)
    if last_error is not None:
        record["last_error"] = str(last_error or "").strip()
    if workflow_kind is not None:
        normalized_workflow_kind = str(workflow_kind or "").strip()
        record["workflow_kind"] = normalized_workflow_kind if normalized_workflow_kind in WORKFLOW_KINDS else record.get("workflow_kind", "")
    if replace_context is not None:
        record["context"] = dict(replace_context)
    elif context_patch is not None:
        merged_context = dict(record.get("context") or {})
        merged_context.update(dict(context_patch))
        record["context"] = merged_context
    if steps is not None:
        record["steps"] = [
            _normalize_step_record(item, position=index)
            for index, item in enumerate(steps)
            if isinstance(item, dict)
        ]
    record["updated_at"] = now_utc()
    if completed or record.get("status") in {"completed", "completed_with_errors", "dry_run", "stopped", "error"}:
        record["completed_at"] = record["updated_at"]
    index["jobs"][position] = record
    save_job_index(index, index_path)
    return record


def append_job_step(
    job_id: str,
    *,
    step_code: str = "",
    step_kind: str = "",
    action_label: str = "",
    status: str = "running",
    summary: str = "",
    artifact_paths: dict[str, str] | None = None,
    index_path: str | Path = DEFAULT_JOB_INDEX_PATH,
) -> dict[str, Any]:
    job = get_job(job_id, index_path=index_path)
    if job is None:
        raise KeyError(f"unknown job_id: {job_id}")
    steps = list(job.get("steps") or [])
    step_index = len(steps)
    step = _normalize_step_record(
        {
            "workflow_job_id": job_id,
            "step_id": f"{job_id}-step-{step_index + 1}",
            "step_index": step_index,
            "step_code": step_code,
            "step_kind": step_kind,
            "status": status,
            "summary": summary,
            "started_at": now_utc(),
            "completed_at": "",
            "artifact_paths": dict(artifact_paths or {}),
            "action_label": action_label,
        },
        position=step_index,
    )
    steps.append(step)
    update_job(job_id, steps=steps, index_path=index_path)
    return step


def latest_job_step(job: dict[str, Any]) -> dict[str, Any] | None:
    steps = [
        _normalize_step_record(item, position=index)
        for index, item in enumerate(job.get("steps") or [])
        if isinstance(item, dict)
    ]
    if not steps:
        return None
    return steps[-1]


def find_running_step(job: dict[str, Any]) -> dict[str, Any] | None:
    steps = [item for item in job.get("steps") or [] if isinstance(item, dict)]
    for item in reversed(steps):
        if str(item.get("status") or "") == "running":
            return item
    return None


def update_job_step(
    job_id: str,
    *,
    step_id: str,
    status: str | None = None,
    summary: str | None = None,
    artifact_paths: dict[str, str] | None = None,
    completed: bool | None = None,
    index_path: str | Path = DEFAULT_JOB_INDEX_PATH,
) -> dict[str, Any]:
    job = get_job(job_id, index_path=index_path)
    if job is None:
        raise KeyError(f"unknown job_id: {job_id}")
    steps = [dict(item) for item in job.get("steps") or [] if isinstance(item, dict)]
    target: dict[str, Any] | None = None
    for index, item in enumerate(steps):
        if str(item.get("step_id") or "") != str(step_id):
            continue
        target = dict(item)
        if status is not None:
            normalized_status = str(status or "").strip().lower() or str(target.get("status") or "running")
            target["status"] = normalized_status if normalized_status in STEP_STATUSES else str(target.get("status") or "running")
        if summary is not None:
            target["summary"] = str(summary or "").strip()
        if artifact_paths is not None:
            merged = dict(target.get("artifact_paths") or {})
            merged.update(_normalize_artifact_paths(artifact_paths))
            target["artifact_paths"] = merged
        if completed or str(target.get("status") or "") in {"completed", "completed_with_errors", "dry_run", "stopped", "error"}:
            target["completed_at"] = now_utc()
        steps[index] = _normalize_step_record(target, position=index)
        break
    if target is None:
        raise KeyError(f"unknown step_id for job {job_id}: {step_id}")
    update_job(job_id, steps=steps, index_path=index_path)
    return _normalize_step_record(target, position=int(target.get("step_index") or 0))


def finish_job(
    job_id: str,
    *,
    payload: dict[str, Any] | None,
    fallback_status: str = "completed",
    fallback_phase: str = "",
    index_path: str | Path = DEFAULT_JOB_INDEX_PATH,
) -> dict[str, Any]:
    normalized = normalize_runtime_payload(payload, fallback_status=fallback_status, fallback_phase=fallback_phase)
    return update_job(
        job_id,
        status=str(normalized["status"]),
        phase=str(normalized["phase"]),
        summary=str(normalized["summary"]),
        artifact_paths=dict(normalized["artifact_paths"]),
        next_hint=str(normalized["next_hint"]),
        recoverable=bool(normalized["recoverable"]),
        last_error="",
        completed=True,
        index_path=index_path,
    )


def fail_job(
    job_id: str,
    *,
    error_text: str,
    phase: str = "",
    index_path: str | Path = DEFAULT_JOB_INDEX_PATH,
) -> dict[str, Any]:
    return update_job(
        job_id,
        status="error",
        phase=phase,
        summary=str(error_text or "Ошибка").strip() or "Ошибка",
        recoverable=True,
        last_error=str(error_text or "").strip(),
        completed=True,
        index_path=index_path,
    )


def stop_job(
    job_id: str,
    *,
    summary: str = "Остановлено",
    phase: str = "",
    index_path: str | Path = DEFAULT_JOB_INDEX_PATH,
) -> dict[str, Any]:
    return update_job(
        job_id,
        status="stopped",
        phase=phase,
        summary=summary,
        recoverable=True,
        completed=True,
        index_path=index_path,
    )


def list_jobs(
    *,
    tool_id: str | None = None,
    workflow_kind: str | None = None,
    profile_id: str | None = None,
    profile_name: str | None = None,
    profile_dir: str | Path | None = None,
    status: str | None = None,
    limit: int = DEFAULT_TIMELINE_LIMIT,
    index_path: str | Path = DEFAULT_JOB_INDEX_PATH,
) -> list[dict[str, Any]]:
    jobs = list(load_job_index(index_path)["jobs"])
    if tool_id is not None:
        jobs = [item for item in jobs if str(item.get("tool_id") or "") == str(tool_id)]
    if workflow_kind is not None:
        jobs = [item for item in jobs if str(item.get("workflow_kind") or "") == str(workflow_kind)]
    if profile_id is not None:
        jobs = [item for item in jobs if str(item.get("profile_id") or "") == str(profile_id)]
    if profile_name is not None:
        jobs = [item for item in jobs if str(item.get("profile_name") or "") == str(profile_name)]
    if profile_dir is not None:
        resolved_profile_dir = str(Path(profile_dir).expanduser().resolve())
        jobs = [item for item in jobs if str(item.get("profile_dir") or "") == resolved_profile_dir]
    if status is not None:
        jobs = [item for item in jobs if str(item.get("status") or "") == str(status)]
    jobs.sort(key=lambda item: str(item.get("updated_at") or item.get("started_at") or ""), reverse=True)
    return jobs[: max(int(limit), 1)]


def get_job(job_id: str, index_path: str | Path = DEFAULT_JOB_INDEX_PATH) -> dict[str, Any] | None:
    for item in load_job_index(index_path)["jobs"]:
        if str(item.get("job_id") or "") == str(job_id):
            return normalize_job_record(item)
    return None


def workflow_artifact_index(job_id: str, index_path: str | Path = DEFAULT_JOB_INDEX_PATH) -> dict[str, str]:
    job = get_job(job_id, index_path=index_path)
    if job is None:
        raise KeyError(f"unknown job_id: {job_id}")
    artifacts = dict(job.get("artifact_paths") or {})
    for step in job.get("steps") or []:
        if not isinstance(step, dict):
            continue
        artifacts.update(_normalize_artifact_paths(step.get("artifact_paths")))
    return artifacts


def _job_timeline(job: dict[str, Any], *, limit: int = DEFAULT_TIMELINE_LIMIT) -> list[dict[str, Any]]:
    steps = [
        _normalize_step_record(item, position=index)
        for index, item in enumerate(job.get("steps") or [])
        if isinstance(item, dict)
    ]
    return steps[-max(int(limit), 1) :]


def _recoverable_job(jobs: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in jobs:
        if _job_is_resumable(item):
            return item
    return None


def _job_context(job: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(job, dict):
        return {}
    payload = job.get("context")
    return dict(payload) if isinstance(payload, dict) else {}


def _workflow_resume_decision(
    *,
    active_job: dict[str, Any] | None,
    recoverable_job: dict[str, Any] | None,
    last_job: dict[str, Any] | None,
) -> dict[str, Any]:
    if isinstance(active_job, dict):
        return {
            "kind": "running",
            "job": active_job,
            "allowed": False,
            "hint": "workflow уже выполняется",
            "action_text": "Жди завершения текущего workflow или останови его вручную.",
        }
    if _job_is_resumable(last_job):
        return {
            "kind": "resume",
            "job": last_job,
            "allowed": True,
            "hint": "можно продолжить",
            "action_text": "Последний workflow можно продолжить из сохранённого состояния.",
        }
    if _job_is_success_like(last_job):
        return {
            "kind": "restart",
            "job": last_job,
            "allowed": False,
            "hint": "лучше перезапустить",
            "action_text": "Последний workflow уже успешно завершён; для нового прогона лучше запустить его заново.",
        }
    if isinstance(recoverable_job, dict):
        return {
            "kind": "resume",
            "job": recoverable_job,
            "allowed": True,
            "hint": "можно продолжить",
            "action_text": "Последний recoverable workflow можно продолжить без нового запуска.",
        }
    if isinstance(last_job, dict):
        last_status = str(last_job.get("status") or "").strip().lower()
        if last_status in RESUMABLE_JOB_STATUSES:
            return {
                "kind": "resume",
                "job": last_job,
                "allowed": True,
                "hint": "можно продолжить",
                "action_text": "Последний workflow можно продолжить из сохранённого состояния.",
            }
        return {
            "kind": "restart",
            "job": last_job,
            "allowed": False,
            "hint": "лучше перезапустить",
            "action_text": "Последний workflow уже завершён; для нового прогона лучше запустить его заново.",
        }
    return {
        "kind": "missing",
        "job": None,
        "allowed": False,
        "hint": "нет подходящего workflow",
        "action_text": "Для этого режима ещё нет workflow, который можно продолжить.",
    }


def _invite_context_from_job(job: dict[str, Any] | None) -> dict[str, Any]:
    context = _job_context(job)
    return {
        "input_path": str(context.get("input_path") or "").strip(),
        "invite_job_dir": str(context.get("invite_job_dir") or "").strip(),
        "invite_batch_limit": int(context.get("invite_batch_limit") or 0),
        "statuses": [str(item).strip() for item in context.get("statuses") or [] if str(item).strip()],
    }


def _invite_snapshot_from_context(context: dict[str, Any]) -> dict[str, Any]:
    invite_job_dir = str(context.get("invite_job_dir") or "").strip()
    if not invite_job_dir:
        return {}
    from .telegram_gui_helpers import contact_job_snapshot

    try:
        snapshot = contact_job_snapshot(invite_job_dir)
    except Exception:
        return {}
    return snapshot if isinstance(snapshot, dict) else {}


def _invite_queue_decisions(
    *,
    active_job: dict[str, Any] | None,
    recoverable_job: dict[str, Any] | None,
    last_job: dict[str, Any] | None,
) -> dict[str, Any]:
    source_job = active_job or last_job or recoverable_job
    base_context = _invite_context_from_job(source_job)
    snapshot = _invite_snapshot_from_context(base_context)
    pending_total = int(snapshot.get("pending_total") or 0)
    failed_total = int(snapshot.get("failed_total") or 0)
    added_total = int(snapshot.get("added_total") or 0)

    if isinstance(active_job, dict):
        continue_hint = "workflow уже выполняется"
        continue_allowed = False
        retry_hint = "workflow уже выполняется"
        retry_allowed = False
        next_action = "Ждать завершения текущего invite workflow."
    else:
        continue_allowed = pending_total > 0 and bool(base_context.get("invite_job_dir"))
        retry_allowed = failed_total > 0 and bool(base_context.get("invite_job_dir"))
        if continue_allowed:
            continue_hint = f"можно продолжить: осталось {pending_total}"
        elif snapshot:
            continue_hint = "очередь исчерпана"
        else:
            continue_hint = "нет сохранённой очереди"
        if retry_allowed:
            retry_hint = f"ошибки можно повторить: {failed_total}"
        elif snapshot:
            retry_hint = "ошибок для повтора нет"
        else:
            retry_hint = "нет сохранённой истории ошибок"
        if retry_allowed:
            next_action = "Повторить ошибки invite batch."
        elif continue_allowed:
            next_action = "Продолжить очередь invite batch."
        elif added_total > 0:
            next_action = "Очередь закончилась; можно запускать новый batch."
        else:
            next_action = "Запусти новый invite batch."

    return {
        "continue_queue_hint": continue_hint,
        "retry_failed_hint": retry_hint,
        "continue_queue_allowed": continue_allowed,
        "retry_failed_allowed": retry_allowed,
        "continue_queue_context": {
            **base_context,
            "statuses": ["new", "checked"],
        },
        "retry_failed_context": {
            **base_context,
            "statuses": ["failed"],
        },
        "invite_snapshot": snapshot,
        "next_operator_action": next_action,
    }


def _workflow_next_operator_action(
    *,
    workflow_kind: str,
    resume_decision: dict[str, Any],
) -> str:
    decision_kind = str(resume_decision.get("kind") or "")
    if decision_kind == "running":
        return f"Ждать завершения {workflow_kind} workflow."
    if decision_kind == "resume":
        return f"Продолжить {workflow_kind} workflow."
    if decision_kind == "restart":
        return f"Запустить новый {workflow_kind} workflow."
    return f"Подготовить и запустить {workflow_kind} workflow."


def _workflow_bucket_snapshot(
    jobs: list[dict[str, Any]],
    *,
    workflow_kind: str,
    index_path: str | Path,
    limit: int,
    timeline_limit: int,
) -> dict[str, Any]:
    workflow_jobs = [item for item in jobs if str(item.get("workflow_kind") or "") == str(workflow_kind)]
    active_job = next((item for item in workflow_jobs if str(item.get("status") or "") == "running"), None)
    last_job = workflow_jobs[0] if workflow_jobs else None
    recoverable_job = _recoverable_job(workflow_jobs)
    resume_decision = _workflow_resume_decision(
        active_job=active_job,
        recoverable_job=recoverable_job,
        last_job=last_job,
    )
    anchor_job = active_job or last_job or recoverable_job
    artifact_index = (
        workflow_artifact_index(str(anchor_job.get("job_id") or ""), index_path=index_path)
        if isinstance(anchor_job, dict)
        else {}
    )
    payload = {
        "workflow_kind": workflow_kind,
        "active_job": active_job,
        "last_job": last_job,
        "recent_jobs": workflow_jobs[:limit],
        "timeline": _job_timeline(anchor_job or {}, limit=timeline_limit),
        "artifact_index": artifact_index,
        "recoverable_job": recoverable_job,
        "resume_decision": resume_decision,
        "resume_hint": str(resume_decision.get("hint") or ""),
        "next_operator_action": _workflow_next_operator_action(
            workflow_kind=workflow_kind,
            resume_decision=resume_decision,
        ),
    }
    if workflow_kind == "invite_batch":
        payload.update(
            _invite_queue_decisions(
                active_job=active_job,
                recoverable_job=recoverable_job,
                last_job=last_job,
            )
        )
    return payload


def _profile_history_groups_from_jobs(
    jobs: list[dict[str, Any]],
    *,
    limit: int,
    step_limit: int,
) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for item in jobs[: max(limit, 1)]:
        groups.append(
            {
                "job": item,
                "steps": _job_timeline(item, limit=step_limit),
            }
        )
    return groups


def _profile_timeline_from_groups(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    timeline: list[dict[str, Any]] = []
    for group in groups:
        job = group.get("job") if isinstance(group.get("job"), dict) else None
        if isinstance(job, dict):
            timeline.append(
                {
                    "entry_kind": "job",
                    "job_id": str(job.get("job_id") or "").strip(),
                    "workflow_kind": str(job.get("workflow_kind") or job.get("tool_id") or "").strip(),
                    "status": _job_status(job),
                    "phase": str(job.get("phase") or "").strip(),
                    "summary": str(job.get("summary") or "").strip(),
                    "started_at": str(job.get("started_at") or "").strip(),
                    "completed_at": str(job.get("completed_at") or "").strip(),
                }
            )
        for step in group.get("steps") or []:
            if not isinstance(step, dict):
                continue
            timeline.append(
                {
                    "entry_kind": "step",
                    "job_id": str(step.get("workflow_job_id") or job.get("job_id") if isinstance(job, dict) else "").strip(),
                    "workflow_kind": str(job.get("workflow_kind") or job.get("tool_id") or "").strip()
                    if isinstance(job, dict)
                    else "",
                    "step_index": int(step.get("step_index") or 0),
                    "step_code": str(step.get("step_code") or "").strip(),
                    "step_kind": str(step.get("step_kind") or "").strip(),
                    "status": str(step.get("status") or "").strip(),
                    "summary": str(step.get("summary") or "").strip(),
                    "started_at": str(step.get("started_at") or "").strip(),
                    "completed_at": str(step.get("completed_at") or "").strip(),
                }
            )
    return timeline


def _artifact_candidates_from_index(artifact_index: dict[str, str], artifact_kind: str) -> list[Path]:
    candidates: list[Path] = []

    def _append_candidate(raw_value: Any) -> None:
        value = str(raw_value or "").strip()
        if not value:
            return
        path = Path(value).expanduser().resolve()
        if path.exists() and path not in candidates:
            candidates.append(path)

    def _append_from_glob(root_value: Any, pattern: str) -> None:
        value = str(root_value or "").strip()
        if not value:
            return
        root = Path(value).expanduser().resolve()
        if not root.exists():
            return
        matches = sorted(
            root.glob(pattern),
            key=lambda item: item.stat().st_mtime if item.exists() else 0,
            reverse=True,
        )
        for item in matches:
            if item.exists() and item not in candidates:
                candidates.append(item)

    if artifact_kind == "panel_log":
        _append_candidate(DEFAULT_PANEL_LOG_PATH)
    elif artifact_kind == "batch_json":
        _append_candidate(artifact_index.get("batch_json"))
        run_dir = artifact_index.get("run_dir")
        if str(run_dir or "").strip():
            _append_candidate(Path(str(run_dir)) / "batch_contact_add.json")
        _append_from_glob(artifact_index.get("job_dir"), "executions/*/batch_contact_add.json")
    elif artifact_kind == "session_run":
        _append_candidate(artifact_index.get("session_run"))
        _append_candidate(artifact_index.get("path"))
        run_dir = artifact_index.get("run_dir")
        if str(run_dir or "").strip():
            _append_candidate(Path(str(run_dir)) / "run.json")
        _append_candidate(run_dir)
    elif artifact_kind == "execution_record":
        _append_candidate(artifact_index.get("execution_record"))
        run_dir = artifact_index.get("run_dir")
        if str(run_dir or "").strip():
            _append_candidate(Path(str(run_dir)) / "execution_record.json")
        _append_from_glob(artifact_index.get("job_dir"), "executions/*/execution_record.json")
    elif artifact_kind == "screenshot":
        _append_candidate(artifact_index.get("screenshot_path"))
        _append_candidate(artifact_index.get("window_screenshot"))
        run_dir = artifact_index.get("run_dir")
        if str(run_dir or "").strip():
            _append_from_glob(run_dir, "*.png")
    return candidates


def _session_history_artifacts() -> dict[str, str]:
    from .telegram_gui_helpers import session_history_snapshot

    try:
        snapshot = session_history_snapshot()
    except Exception:
        return {}
    last_run = snapshot.get("last_run") if isinstance(snapshot.get("last_run"), dict) else {}
    if not last_run:
        return {}
    payload: dict[str, str] = {}
    for key in ("run_dir", "path"):
        value = str(last_run.get(key) or "").strip()
        if value:
            payload[key] = value
    if payload.get("path"):
        payload["session_run"] = payload["path"]
    return payload


def _resolved_artifact_shortcuts(
    artifact_index: dict[str, str],
    *,
    workflow_buckets: dict[str, dict[str, Any]] | None = None,
) -> dict[str, str]:
    shortcuts: dict[str, str] = {}

    def _bucket_artifacts(workflow_kind: str) -> dict[str, str]:
        bucket = workflow_buckets.get(workflow_kind) if isinstance(workflow_buckets, dict) else None
        payload = bucket.get("artifact_index") if isinstance(bucket, dict) else None
        if not isinstance(payload, dict):
            return {}
        return {str(key): str(value) for key, value in payload.items() if str(key).strip() and str(value).strip()}

    artifact_sources = {
        "panel_log": [artifact_index],
        "batch_json": [_bucket_artifacts("invite_batch"), artifact_index],
        "session_run": [_bucket_artifacts("session_run"), _session_history_artifacts(), artifact_index],
        "execution_record": [
            _bucket_artifacts("combined_pattern"),
            _bucket_artifacts("invite_batch"),
            artifact_index,
        ],
        "screenshot": [
            _bucket_artifacts("session_run"),
            _bucket_artifacts("combined_pattern"),
            _session_history_artifacts(),
            artifact_index,
        ],
    }
    for artifact_kind in ARTIFACT_CENTER_LABELS:
        candidates: list[Path] = []
        for source in artifact_sources.get(artifact_kind, [artifact_index]):
            candidates.extend(_artifact_candidates_from_index(source, artifact_kind))
        if candidates:
            shortcuts[artifact_kind] = str(candidates[0])
    return shortcuts


def _artifact_center_rows(shortcuts: dict[str, str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for artifact_kind, label in ARTIFACT_CENTER_LABELS.items():
        path = str(shortcuts.get(artifact_kind) or "").strip()
        rows.append(
            {
                "artifact_kind": artifact_kind,
                "label": label,
                "path": path,
                "available": bool(path),
            }
        )
    return rows


def _profile_artifact_index_from_jobs(
    jobs: list[dict[str, Any]],
    *,
    workflow_buckets: dict[str, dict[str, Any]],
    index_path: str | Path,
) -> dict[str, str]:
    artifact_index: dict[str, str] = {}

    def _merge_job_artifacts(job: dict[str, Any] | None, *, overwrite: bool) -> None:
        if not isinstance(job, dict) or not job:
            return
        payload = workflow_artifact_index(str(job.get("job_id") or ""), index_path=index_path)
        for key, value in payload.items():
            if overwrite or key not in artifact_index:
                artifact_index[key] = value

    active_job = next((item for item in jobs if str(item.get("status") or "") == "running"), None)
    last_success = next(
        (
            item
            for item in jobs
            if str(item.get("status") or "") in {"completed", "completed_with_errors", "dry_run", "stopped"}
        ),
        None,
    )
    _merge_job_artifacts(active_job, overwrite=True)
    _merge_job_artifacts(last_success, overwrite=False)
    for item in jobs:
        _merge_job_artifacts(item, overwrite=False)
    for workflow_kind in WORKSPACE_WORKFLOW_KINDS:
        bucket = workflow_buckets.get(workflow_kind) if isinstance(workflow_buckets, dict) else None
        bucket_artifacts = bucket.get("artifact_index") if isinstance(bucket, dict) else None
        if not isinstance(bucket_artifacts, dict):
            continue
        for key, value in bucket_artifacts.items():
            normalized_key = str(key).strip()
            normalized_value = str(value).strip()
            if normalized_key and normalized_value and normalized_key not in artifact_index:
                artifact_index[normalized_key] = normalized_value
    return artifact_index


def active_workflow_job(
    *,
    profile_name: str,
    profile_dir: str | Path,
    workflow_kind: str | None = None,
    index_path: str | Path = DEFAULT_JOB_INDEX_PATH,
) -> dict[str, Any] | None:
    profile_id = profile_id_for(profile_name, profile_dir)
    jobs = list_jobs(profile_id=profile_id, workflow_kind=workflow_kind, status="running", limit=10, index_path=index_path)
    return jobs[0] if jobs else None


def recoverable_workflow_job(
    *,
    profile_name: str,
    profile_dir: str | Path,
    workflow_kind: str | None = None,
    index_path: str | Path = DEFAULT_JOB_INDEX_PATH,
) -> dict[str, Any] | None:
    profile_id = profile_id_for(profile_name, profile_dir)
    jobs = list_jobs(profile_id=profile_id, workflow_kind=workflow_kind, limit=20, index_path=index_path)
    return _recoverable_job(jobs)


def profile_history_groups(
    *,
    profile_name: str,
    profile_dir: str | Path,
    limit: int = 6,
    step_limit: int = 4,
    index_path: str | Path = DEFAULT_JOB_INDEX_PATH,
) -> list[dict[str, Any]]:
    profile_id = profile_id_for(profile_name, profile_dir)
    jobs = list_jobs(profile_id=profile_id, limit=max(limit, 1), index_path=index_path)
    return _profile_history_groups_from_jobs(
        jobs,
        limit=limit,
        step_limit=step_limit,
    )


def profile_artifact_index(
    *,
    profile_name: str,
    profile_dir: str | Path,
    index_path: str | Path = DEFAULT_JOB_INDEX_PATH,
) -> dict[str, str]:
    workspace = profile_workspace_snapshot(
        profile_name=profile_name,
        profile_dir=profile_dir,
        index_path=index_path,
    )
    payload = workspace.get("artifact_index")
    return dict(payload) if isinstance(payload, dict) else {}


def profile_workspace_snapshot(
    *,
    profile_name: str,
    profile_dir: str | Path,
    limit: int = 5,
    timeline_limit: int = 8,
    index_path: str | Path = DEFAULT_JOB_INDEX_PATH,
) -> dict[str, Any]:
    from .locks import get_profile_lock
    from .platform_adapters import current_platform_id, platform_capabilities
    from .telegram_profiles import get_profile_status

    profile_id = profile_id_for(profile_name, profile_dir)
    jobs = list_jobs(profile_id=profile_id, limit=max(limit * 8, 24), index_path=index_path)
    active_jobs = [item for item in jobs if str(item.get("status") or "") == "running"][:limit]
    recent_jobs = jobs[:limit]
    active_workflow = active_jobs[0] if active_jobs else None
    recoverable_workflow = _recoverable_job(jobs)
    last_success = next(
        (
            item
            for item in jobs
            if str(item.get("status") or "") in {"completed", "completed_with_errors", "dry_run", "stopped"}
        ),
        None,
    )
    workflow_buckets = {
        workflow_kind: _workflow_bucket_snapshot(
            jobs,
            workflow_kind=workflow_kind,
            index_path=index_path,
            limit=max(limit, timeline_limit),
            timeline_limit=timeline_limit,
        )
        for workflow_kind in WORKSPACE_WORKFLOW_KINDS
    }
    history_groups = _profile_history_groups_from_jobs(
        jobs,
        limit=limit,
        step_limit=timeline_limit,
    )
    profile_timeline = _profile_timeline_from_groups(history_groups)
    resume_decision = _workflow_resume_decision(
        active_job=active_workflow,
        recoverable_job=recoverable_workflow,
        last_job=recent_jobs[0] if recent_jobs else None,
    )
    invite_bucket = workflow_buckets.get("invite_batch") if isinstance(workflow_buckets.get("invite_batch"), dict) else {}
    artifact_index = _profile_artifact_index_from_jobs(
        jobs,
        workflow_buckets=workflow_buckets,
        index_path=index_path,
    )
    artifact_shortcuts = _resolved_artifact_shortcuts(
        artifact_index,
        workflow_buckets=workflow_buckets,
    )
    current_lock = get_profile_lock(profile_name=profile_name, profile_dir=profile_dir)
    try:
        profile_status = get_profile_status(profile_dir)
    except Exception as exc:
        profile_status = {"status": "error", "error": str(exc), "running": False, "windows": []}
    capabilities = platform_capabilities()
    health = {
        "platform_id": current_platform_id(),
        "profile_running": bool(profile_status.get("running")),
        "window_automation_available": bool((capabilities.get("window_automation") or {}).get("available")),
        "accessibility_available": bool((capabilities.get("accessibility") or {}).get("available")),
        "session_runtime_reachable": (Path("/home/max/telegram-portable-session-tool") / "bin" / "telegram-portable-session-tool").exists(),
        "panel_backend_status": "ready",
    }
    if str(resume_decision.get("kind") or "") == "running":
        next_operator_action = "Ждать завершения активного workflow."
    elif bool(invite_bucket.get("retry_failed_allowed")):
        next_operator_action = "Повторить ошибки invite batch."
    elif bool(invite_bucket.get("continue_queue_allowed")):
        next_operator_action = "Продолжить очередь invite batch."
    elif str(resume_decision.get("kind") or "") == "resume":
        next_operator_action = "Продолжить recoverable workflow."
    elif recent_jobs:
        next_operator_action = "Запустить новый workflow."
    else:
        next_operator_action = "Выбери режим и запусти первый workflow."
    return {
        "profile_id": profile_id,
        "active_jobs": active_jobs,
        "recent_jobs": recent_jobs,
        "active_workflow": active_workflow,
        "recoverable_workflow": recoverable_workflow,
        "resume_hint": str(resume_decision.get("hint") or ""),
        "continue_queue_hint": str(invite_bucket.get("continue_queue_hint") or ""),
        "retry_failed_hint": str(invite_bucket.get("retry_failed_hint") or ""),
        "next_operator_action": next_operator_action,
        "current_lock": current_lock,
        "health": health,
        "last_successful_job": last_success,
        "history_groups": history_groups,
        "profile_timeline": profile_timeline,
        "artifact_index": artifact_index,
        "artifact_shortcuts": artifact_shortcuts,
        "artifact_center": _artifact_center_rows(artifact_shortcuts),
        "workflow_buckets": workflow_buckets,
    }
