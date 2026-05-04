from __future__ import annotations

import json
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_TELEGRAM_STATE_ROOT = Path.home() / ".site-control-kit" / "telegram"
DEFAULT_JOB_INDEX_PATH = DEFAULT_TELEGRAM_STATE_ROOT / "jobs" / "index.json"
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
    for status in ("planned", "stopped", "completed_with_errors", "error"):
        for item in jobs:
            if str(item.get("status") or "") != status:
                continue
            if status in {"stopped", "completed_with_errors", "error"} and not bool(item.get("recoverable", True)):
                continue
            return item
    return None


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
    anchor_job = active_job or last_job or recoverable_job
    artifact_index = (
        workflow_artifact_index(str(anchor_job.get("job_id") or ""), index_path=index_path)
        if isinstance(anchor_job, dict)
        else {}
    )
    return {
        "workflow_kind": workflow_kind,
        "active_job": active_job,
        "last_job": last_job,
        "recent_jobs": workflow_jobs[:limit],
        "timeline": _job_timeline(anchor_job or {}, limit=timeline_limit),
        "artifact_index": artifact_index,
        "recoverable_job": recoverable_job,
    }


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
    return [
        {
            "job": item,
            "steps": _job_timeline(item, limit=step_limit),
        }
        for item in jobs[: max(limit, 1)]
    ]


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
    artifact_index = _profile_artifact_index_from_jobs(
        jobs,
        workflow_buckets=workflow_buckets,
        index_path=index_path,
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
    return {
        "profile_id": profile_id,
        "active_jobs": active_jobs,
        "recent_jobs": recent_jobs,
        "current_lock": current_lock,
        "health": health,
        "last_successful_job": last_success,
        "artifact_index": artifact_index,
        "workflow_buckets": workflow_buckets,
    }
