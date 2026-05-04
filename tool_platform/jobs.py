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
JOB_STATUSES = {
    "idle",
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
        "schema_version": 1,
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


def load_job_index(index_path: str | Path = DEFAULT_JOB_INDEX_PATH) -> dict[str, Any]:
    resolved = Path(index_path).expanduser().resolve()
    payload = _load_json(resolved)
    index = default_job_index()
    jobs = payload.get("jobs")
    if isinstance(jobs, list):
        index["jobs"] = [item for item in jobs if isinstance(item, dict)]
    updated_at = str(payload.get("updated_at") or "").strip()
    if updated_at:
        index["updated_at"] = updated_at
    return index


def save_job_index(payload: dict[str, Any], index_path: str | Path = DEFAULT_JOB_INDEX_PATH) -> Path:
    resolved = Path(index_path).expanduser().resolve()
    index = default_job_index()
    index["jobs"] = [item for item in list(payload.get("jobs", [])) if isinstance(item, dict)]
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
        normalized_artifacts.update({str(key): str(value) for key, value in artifact_paths.items() if str(value).strip()})
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


def _job_record_defaults(
    *,
    job_id: str,
    tool_id: str,
    profile_name: str,
    profile_dir: str | Path,
    status: str,
    phase: str,
    summary: str,
    artifact_paths: dict[str, str] | None = None,
    next_hint: str = "",
    recoverable: bool = False,
) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "tool_id": str(tool_id),
        "profile_name": str(profile_name or "").strip() or "profile",
        "profile_dir": str(Path(profile_dir).expanduser().resolve()) if str(profile_dir or "").strip() else "",
        "profile_id": profile_id_for(profile_name, profile_dir),
        "status": str(status or "running"),
        "phase": str(phase or "").strip(),
        "summary": str(summary or "").strip(),
        "artifact_paths": dict(artifact_paths or {}),
        "next_hint": str(next_hint or "").strip(),
        "recoverable": bool(recoverable),
        "started_at": now_utc(),
        "updated_at": now_utc(),
        "completed_at": "",
        "last_error": "",
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
    index_path: str | Path = DEFAULT_JOB_INDEX_PATH,
) -> dict[str, Any]:
    index = load_job_index(index_path)
    job_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    record = _job_record_defaults(
        job_id=job_id,
        tool_id=tool_id,
        profile_name=profile_name,
        profile_dir=profile_dir,
        status="running",
        phase=phase,
        summary=summary,
        artifact_paths=artifact_paths,
        next_hint=next_hint,
        recoverable=False,
    )
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
    index_path: str | Path = DEFAULT_JOB_INDEX_PATH,
) -> dict[str, Any]:
    index = load_job_index(index_path)
    position = _find_job_index(index["jobs"], job_id)
    if position < 0:
        raise KeyError(f"unknown job_id: {job_id}")
    record = dict(index["jobs"][position])
    if status is not None:
        normalized_status = str(status or "").strip().lower() or record.get("status", "running")
        record["status"] = normalized_status if normalized_status in JOB_STATUSES else record.get("status", "running")
    if phase is not None:
        record["phase"] = str(phase or "").strip()
    if summary is not None:
        record["summary"] = str(summary or "").strip()
    if artifact_paths is not None:
        merged = dict(record.get("artifact_paths") or {})
        merged.update({str(key): str(value) for key, value in artifact_paths.items() if str(value).strip()})
        record["artifact_paths"] = merged
    if next_hint is not None:
        record["next_hint"] = str(next_hint or "").strip()
    if recoverable is not None:
        record["recoverable"] = bool(recoverable)
    if last_error is not None:
        record["last_error"] = str(last_error or "").strip()
    record["updated_at"] = now_utc()
    if completed or record.get("status") in {"completed", "completed_with_errors", "dry_run", "stopped", "error"}:
        record["completed_at"] = record["updated_at"]
    index["jobs"][position] = record
    save_job_index(index, index_path)
    return record


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
    profile_id: str | None = None,
    status: str | None = None,
    limit: int = DEFAULT_TIMELINE_LIMIT,
    index_path: str | Path = DEFAULT_JOB_INDEX_PATH,
) -> list[dict[str, Any]]:
    jobs = list(load_job_index(index_path)["jobs"])
    if tool_id is not None:
        jobs = [item for item in jobs if str(item.get("tool_id") or "") == str(tool_id)]
    if profile_id is not None:
        jobs = [item for item in jobs if str(item.get("profile_id") or "") == str(profile_id)]
    if status is not None:
        jobs = [item for item in jobs if str(item.get("status") or "") == str(status)]
    jobs.sort(key=lambda item: str(item.get("updated_at") or item.get("started_at") or ""), reverse=True)
    return jobs[: max(int(limit), 1)]


def get_job(job_id: str, index_path: str | Path = DEFAULT_JOB_INDEX_PATH) -> dict[str, Any] | None:
    for item in load_job_index(index_path)["jobs"]:
        if str(item.get("job_id") or "") == str(job_id):
            return dict(item)
    return None


def profile_workspace_snapshot(
    *,
    profile_name: str,
    profile_dir: str | Path,
    limit: int = 5,
    index_path: str | Path = DEFAULT_JOB_INDEX_PATH,
) -> dict[str, Any]:
    profile_id = profile_id_for(profile_name, profile_dir)
    jobs = list_jobs(profile_id=profile_id, limit=max(limit * 4, 10), index_path=index_path)
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
    artifact_index = dict(last_success.get("artifact_paths") or {}) if isinstance(last_success, dict) else {}
    return {
        "profile_id": profile_id,
        "active_jobs": active_jobs,
        "recent_jobs": recent_jobs,
        "last_successful_job": last_success,
        "artifact_index": artifact_index,
    }
