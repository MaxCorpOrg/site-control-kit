from __future__ import annotations

import json
import re
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .telegram_runtime import (
    LEGACY_PANEL_LOG_PATH,
    LEGACY_STATE_ROOT,
    job_index_path as runtime_job_index_path,
    panel_log_path as runtime_panel_log_path,
    preferred_read_path,
    runtime_config_root as runtime_runtime_config_root,
    session_repo_binary,
    state_root as runtime_state_root,
)


DEFAULT_TELEGRAM_STATE_ROOT = runtime_state_root()
DEFAULT_JOB_INDEX_PATH = runtime_job_index_path()
DEFAULT_PANEL_LOG_PATH = runtime_panel_log_path()
LEGACY_JOB_INDEX_PATH = LEGACY_STATE_ROOT / "jobs" / "index.json"
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
    "progress_json": "Текущий invite progress",
    "batch_json": "Последний batch json",
    "session_run": "Последний session run",
    "execution_record": "Последний execution record",
    "screenshot": "Последний screenshot",
}
ARTIFACT_HISTORY_LABELS = {
    "session_run": "Session run",
    "plan_json": "Session plan",
    "runtime_config": "Runtime config",
    "state_path": "Session state",
    "progress_json": "Invite progress",
    "batch_json": "Batch json",
    "execution_record": "Execution record",
    "screenshot": "Screenshot",
}
SESSION_ARTIFACT_SHORTCUT_LABELS = {
    "session_run": "Session run",
    "run_dir": "Run dir",
    "plan_json": "Session plan",
    "runtime_config": "Runtime config",
    "state_path": "Session state",
    "screenshot": "Screenshot",
}
SESSION_MESSAGE_PREVIEW_LIMIT = 2
SESSION_RUN_MATCH_TOLERANCE = timedelta(seconds=2)
SESSION_RUN_PREFIX_RE = re.compile(r"^(?P<prefix>\d{8}T\d{6}Z)")


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _session_run_prefix(value: Any) -> str:
    match = SESSION_RUN_PREFIX_RE.match(str(value or "").strip())
    return str(match.group("prefix") or "").strip() if match else ""


def _session_run_prefix_from_timestamp(value: Any) -> str:
    raw_value = str(value or "").strip()
    if not raw_value:
        return ""
    try:
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError:
        return ""
    return parsed.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _session_run_timestamp(prefix: str) -> datetime | None:
    normalized = _session_run_prefix(prefix)
    if not normalized:
        return None
    try:
        return datetime.strptime(normalized, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _session_runtime_defaults() -> tuple[Path, Path]:
    from .telegram_gui_helpers import DEFAULT_SESSION_RUNS_DIR, DEFAULT_SESSION_STATE_FILE

    return (
        preferred_read_path(DEFAULT_SESSION_STATE_FILE),
        preferred_read_path(DEFAULT_SESSION_RUNS_DIR),
    )


def _session_runtime_config_root() -> Path:
    return runtime_runtime_config_root().expanduser().resolve()


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


def _existing_path(value: Any) -> Path | None:
    raw_value = str(value or "").strip()
    if not raw_value:
        return None
    path = Path(raw_value).expanduser().resolve()
    return path if path.exists() else None


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


def _elapsed_seconds_between(started_at: Any, completed_at: Any | None = None) -> int | None:
    started = _parse_utc_timestamp(started_at)
    if started is None:
        return None
    completed = _parse_utc_timestamp(completed_at) if completed_at else datetime.now(timezone.utc)
    if completed is None:
        return None
    return max(int((completed - started).total_seconds()), 0)


def _session_run_index(
    runs_dir: str | Path,
    *,
    cache: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    resolved_runs_dir = Path(runs_dir).expanduser().resolve()
    cache_key = f"session-run-index:{resolved_runs_dir}"
    if isinstance(cache, dict):
        cached = cache.get(cache_key)
        if isinstance(cached, list):
            return cached

    rows: list[dict[str, Any]] = []
    if resolved_runs_dir.is_dir():
        for child in sorted(resolved_runs_dir.iterdir()):
            if not child.is_dir():
                continue
            prefix = _session_run_prefix(child.name)
            if not prefix:
                continue
            rows.append(
                {
                    "path": child.resolve(),
                    "prefix": prefix,
                    "timestamp": _session_run_timestamp(prefix),
                }
            )
    if isinstance(cache, dict):
        cache[cache_key] = rows
    return rows


def _session_run_matches_by_prefix(
    runs_dir: str | Path,
    prefix: str,
    *,
    cache: dict[str, Any] | None = None,
) -> list[Path]:
    normalized = _session_run_prefix(prefix)
    if not normalized:
        return []
    return [
        Path(item["path"]).resolve()
        for item in _session_run_index(runs_dir, cache=cache)
        if str(item.get("prefix") or "") == normalized
    ]


def _session_run_matches_near_timestamp(
    runs_dir: str | Path,
    timestamp_value: Any,
    *,
    tolerance: timedelta = SESSION_RUN_MATCH_TOLERANCE,
    cache: dict[str, Any] | None = None,
) -> list[Path]:
    prefix = _session_run_prefix(timestamp_value) or _session_run_prefix_from_timestamp(timestamp_value)
    timestamp = _session_run_timestamp(prefix)
    if timestamp is None:
        return []
    matches: list[tuple[float, Path]] = []
    for item in _session_run_index(runs_dir, cache=cache):
        run_timestamp = item.get("timestamp")
        run_path = item.get("path")
        if not isinstance(run_timestamp, datetime) or not isinstance(run_path, Path):
            continue
        delta = abs((run_timestamp - timestamp).total_seconds())
        if delta <= tolerance.total_seconds():
            matches.append((delta, run_path.resolve()))
    matches.sort(key=lambda payload: (payload[0], str(payload[1])))
    return [path for _, path in matches]


def _session_step_records(job: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _normalize_step_record(item, position=index)
        for index, item in enumerate(job.get("steps") or [])
        if isinstance(item, dict) and str(item.get("step_kind") or "").strip() == "session_run"
    ]


def _is_latest_session_step(job: dict[str, Any], step: dict[str, Any]) -> bool:
    steps = _session_step_records(job)
    if not steps:
        return False
    return str(steps[-1].get("step_id") or "") == str(step.get("step_id") or "")


def _session_runtime_config_path(
    job: dict[str, Any],
    *,
    step: dict[str, Any] | None = None,
) -> Path | None:
    context = _job_context(job)
    context_path = _existing_path(context.get("last_runtime_config_path"))
    if context_path is not None:
        if step is None:
            return context_path
        session_steps = _session_step_records(job)
        if len(session_steps) <= 1 or _is_latest_session_step(job, step):
            return context_path

    runtime_root = _session_runtime_config_root()
    if not runtime_root.is_dir():
        return None
    job_id = str(job.get("job_id") or "").strip()
    if not job_id:
        return None
    matches = sorted(runtime_root.glob(f"{job_id}-*.json"))
    if step is None and len(matches) == 1:
        return matches[0].resolve()
    if step is not None and len(_session_step_records(job)) <= 1 and len(matches) == 1:
        return matches[0].resolve()
    return None


def _session_artifact_result(
    artifact_paths: dict[str, str],
    *,
    run_match_strategy: str = "",
    unresolved: list[str] | None = None,
    artifact_provenance: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "artifact_paths": _normalize_artifact_paths(artifact_paths),
        "run_match_strategy": str(run_match_strategy or "").strip(),
        "unresolved": [str(item).strip() for item in unresolved or [] if str(item).strip()],
        "artifact_provenance": {
            str(key): str(value)
            for key, value in (artifact_provenance or {}).items()
            if str(key).strip() and str(value).strip()
        },
    }


def _resolve_session_artifacts(
    job: dict[str, Any],
    *,
    step: dict[str, Any] | None = None,
    cache: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target = dict(step) if isinstance(step, dict) else dict(job)
    raw_artifacts = _normalize_artifact_paths(target.get("artifact_paths"))
    if step is not None and not raw_artifacts and str(job.get("workflow_kind") or "") == "session_run" and _is_latest_session_step(job, step):
        raw_artifacts = _normalize_artifact_paths(job.get("artifact_paths"))

    resolved: dict[str, str] = {}
    provenance: dict[str, str] = {}
    unresolved: list[str] = []
    run_match_strategy = ""

    state_path_default, runs_dir_default = _session_runtime_defaults()
    context = _job_context(job)

    state_path_source = ""
    state_path = _existing_path(raw_artifacts.get("state_path"))
    if state_path is not None:
        state_path_source = "stored"
    if state_path is None:
        state_path = _existing_path(context.get("last_session_state_path"))
        if state_path is not None:
            state_path_source = "context"
    if state_path is None and state_path_default.exists():
        state_path = state_path_default
        state_path_source = "fallback"
    if state_path is not None:
        resolved["state_path"] = str(state_path)
        provenance["state_path"] = state_path_source

    runs_dir_source = ""
    runs_dir = _existing_path(raw_artifacts.get("runs_dir"))
    if runs_dir is not None:
        runs_dir_source = "stored"
    if runs_dir is None:
        runs_dir = _existing_path(context.get("last_session_runs_dir"))
        if runs_dir is not None:
            runs_dir_source = "context"
    if runs_dir is None and runs_dir_default.exists():
        runs_dir = runs_dir_default
        runs_dir_source = "fallback"
    if runs_dir is not None:
        resolved["runs_dir"] = str(runs_dir)
        provenance["runs_dir"] = runs_dir_source

    runtime_config_source = ""
    runtime_config = _existing_path(raw_artifacts.get("runtime_config"))
    if runtime_config is not None:
        runtime_config_source = "stored"
    if runtime_config is None:
        runtime_config = _session_runtime_config_path(job, step=step)
        if runtime_config is not None:
            runtime_config_source = "resolved"
    if runtime_config is not None:
        resolved["runtime_config"] = str(runtime_config)
        provenance["runtime_config"] = runtime_config_source
    elif str(target.get("step_kind") or target.get("workflow_kind") or "").strip() == "session_run":
        unresolved.append("runtime_config")

    run_dir_candidates: list[Path] = []
    run_dir_candidate_source = ""
    for key in ("session_run", "path", "run_dir"):
        candidate = _existing_path(raw_artifacts.get(key))
        if candidate is None:
            continue
        run_dir = candidate.parent if candidate.is_file() else candidate
        if run_dir not in run_dir_candidates:
            run_dir_candidates.append(run_dir)
            run_dir_candidate_source = "stored"
    if len(run_dir_candidates) == 1:
        resolved_run_dir = run_dir_candidates[0]
        run_match_strategy = "existing_artifact"
        run_dir_source = run_dir_candidate_source or "stored"
    else:
        resolved_run_dir = None
        run_dir_source = ""
        if len(run_dir_candidates) > 1:
            unresolved.append("ambiguous_existing_run_dir")

    if resolved_run_dir is None and runs_dir is not None:
        exact_anchors = (
            ("exact_started_at", _session_run_prefix_from_timestamp(target.get("started_at"))),
            ("exact_completed_at", _session_run_prefix_from_timestamp(target.get("completed_at"))),
            ("exact_job_id", _session_run_prefix(target.get("workflow_job_id") or job.get("job_id"))),
        )
        for strategy, prefix in exact_anchors:
            matches = _session_run_matches_by_prefix(runs_dir, prefix, cache=cache)
            if len(matches) == 1:
                resolved_run_dir = matches[0]
                run_match_strategy = strategy
                run_dir_source = "resolved"
                break
            if len(matches) > 1:
                unresolved.append(f"ambiguous_{strategy}")

    if resolved_run_dir is None and runs_dir is not None:
        near_anchors = (
            ("near_started_at", target.get("started_at")),
            ("near_completed_at", target.get("completed_at")),
            ("near_job_id", str(job.get("job_id") or "").split("-", 1)[0]),
        )
        for strategy, raw_timestamp in near_anchors:
            matches = _session_run_matches_near_timestamp(runs_dir, raw_timestamp, cache=cache)
            if len(matches) == 1:
                resolved_run_dir = matches[0]
                run_match_strategy = strategy
                run_dir_source = "resolved"
                break
            if len(matches) > 1:
                unresolved.append(f"ambiguous_{strategy}")

    if resolved_run_dir is None:
        unresolved.append("run_dir")
        return _session_artifact_result(
            resolved,
            run_match_strategy=run_match_strategy,
            unresolved=unresolved,
            artifact_provenance=provenance,
        )

    resolved["run_dir"] = str(resolved_run_dir)
    provenance["run_dir"] = run_dir_source or "resolved"
    run_json = resolved_run_dir / "run.json"
    if run_json.exists():
        resolved["session_run"] = str(run_json)
        resolved["path"] = str(run_json)
        provenance["session_run"] = provenance["run_dir"]
        provenance["path"] = provenance["run_dir"]
    else:
        unresolved.append("session_run")
    plan_json = resolved_run_dir / "plan.json"
    if plan_json.exists():
        resolved["plan_json"] = str(plan_json)
        provenance["plan_json"] = provenance["run_dir"]
    else:
        unresolved.append("plan_json")
    screenshots = sorted(
        resolved_run_dir.glob("*.png"),
        key=lambda item: item.stat().st_mtime if item.exists() else 0,
        reverse=True,
    )
    if screenshots:
        resolved["screenshot_path"] = str(screenshots[0])
        provenance["screenshot_path"] = provenance["run_dir"]
    return _session_artifact_result(
        resolved,
        run_match_strategy=run_match_strategy,
        unresolved=unresolved,
        artifact_provenance=provenance,
    )


def _invite_run_prefix(value: Any) -> str:
    raw_value = str(value or "").strip()
    if not raw_value:
        return ""
    if SESSION_RUN_PREFIX_RE.match(raw_value):
        return raw_value[:16]
    parsed = _parse_utc_timestamp(raw_value)
    if parsed is None:
        return ""
    return parsed.strftime("%Y%m%dT%H%M%SZ")


def _invite_run_index(job_dir: str | Path, *, cache: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    resolved_job_dir = Path(job_dir).expanduser().resolve()
    cache_key = f"invite-run-index:{resolved_job_dir}"
    if isinstance(cache, dict):
        cached = cache.get(cache_key)
        if isinstance(cached, list):
            return cached
    rows: list[dict[str, Any]] = []
    executions_dir = resolved_job_dir / "executions"
    if executions_dir.is_dir():
        for child in sorted(executions_dir.iterdir()):
            if not child.is_dir():
                continue
            prefix = _invite_run_prefix(child.name)
            rows.append(
                {
                    "path": child.resolve(),
                    "prefix": prefix,
                    "timestamp": _parse_utc_timestamp(prefix) if prefix else None,
                }
            )
    if isinstance(cache, dict):
        cache[cache_key] = rows
    return rows


def _invite_run_matches_by_prefix(
    job_dir: str | Path,
    prefix: str,
    *,
    cache: dict[str, Any] | None = None,
) -> list[Path]:
    normalized_prefix = _invite_run_prefix(prefix)
    if not normalized_prefix:
        return []
    matches: list[Path] = []
    for row in _invite_run_index(job_dir, cache=cache):
        row_prefix = str(row.get("prefix") or "").strip()
        if row_prefix == normalized_prefix and isinstance(row.get("path"), Path):
            matches.append(row["path"])
    return matches


def _invite_resolved_job_dir(value: Any) -> Path | None:
    raw_value = str(value or "").strip()
    if not raw_value:
        return None
    from .telegram_gui_helpers import resolve_invite_job_dir

    resolved = resolve_invite_job_dir(raw_value)
    return resolved if resolved.exists() else None


def _invite_artifact_result(
    stored_artifact_paths: dict[str, str],
    canonical_artifact_paths: dict[str, str],
    *,
    job_dir_match_strategy: str = "",
    run_match_strategy: str = "",
    unresolved: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "stored_artifact_paths": _normalize_artifact_paths(stored_artifact_paths),
        "artifact_paths": _normalize_artifact_paths(canonical_artifact_paths),
        "job_dir_match_strategy": str(job_dir_match_strategy or "").strip(),
        "run_match_strategy": str(run_match_strategy or "").strip(),
        "unresolved": [str(item).strip() for item in unresolved or [] if str(item).strip()],
    }


def _resolve_invite_artifacts(
    job: dict[str, Any],
    *,
    step: dict[str, Any] | None = None,
    cache: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target = dict(step) if isinstance(step, dict) else dict(job)
    raw_artifacts = _normalize_artifact_paths(target.get("artifact_paths"))
    context = _job_context(job)
    stored_artifacts = dict(raw_artifacts)
    unresolved: list[str] = []
    job_dir_match_strategy = ""
    run_match_strategy = ""

    stored_job_dir = (
        raw_artifacts.get("job_dir")
        or context.get("invite_job_dir")
        or ""
    )
    job_dir = _invite_resolved_job_dir(stored_job_dir)
    if job_dir is not None:
        job_dir_match_strategy = "stored_or_context"
    else:
        unresolved.append("job_dir")
        return _invite_artifact_result(stored_artifacts, {}, unresolved=unresolved)

    resolved: dict[str, str] = {"job_dir": str(job_dir)}
    state_path = job_dir / "invite_state.json"
    if state_path.exists():
        resolved["state_path"] = str(state_path)

    run_dir: Path | None = None
    stored_run_dir = raw_artifacts.get("run_dir") or context.get("last_invite_run_dir") or ""
    if stored_run_dir:
        stored_path = Path(stored_run_dir).expanduser().resolve()
        canonical_candidate = job_dir / "executions" / stored_path.name
        if canonical_candidate.exists():
            run_dir = canonical_candidate
            run_match_strategy = "stored_run_dir"
        elif stored_path.exists():
            run_dir = stored_path
            run_match_strategy = "stored_run_dir"
    if run_dir is None:
        execution_id = str(context.get("invite_execution_id") or "").strip()
        if execution_id:
            candidate = job_dir / "executions" / execution_id
            if candidate.exists():
                run_dir = candidate
                run_match_strategy = "context_execution_id"
    if run_dir is None:
        for strategy, value in (
            ("exact_started_at", target.get("started_at")),
            ("exact_completed_at", target.get("completed_at")),
            ("exact_job_id", target.get("workflow_job_id") or job.get("job_id")),
        ):
            matches = _invite_run_matches_by_prefix(job_dir, value, cache=cache)
            if len(matches) == 1:
                run_dir = matches[0]
                run_match_strategy = strategy
                break
            if len(matches) > 1:
                unresolved.append(f"ambiguous_{strategy}")

    if run_dir is not None:
        resolved["run_dir"] = str(run_dir)
        progress_json = run_dir / "batch_progress.json"
        batch_json = run_dir / "batch_contact_add.json"
        execution_record = run_dir / "execution_record.json"
        log_path = run_dir / "batch_contact_add.log"
        if progress_json.exists():
            resolved["progress_json"] = str(progress_json)
        if batch_json.exists():
            resolved["batch_json"] = str(batch_json)
        if execution_record.exists():
            resolved["execution_record"] = str(execution_record)
        if log_path.exists():
            resolved["log_path"] = str(log_path)
    else:
        unresolved.append("run_dir")

    return _invite_artifact_result(
        stored_artifacts,
        resolved,
        job_dir_match_strategy=job_dir_match_strategy,
        run_match_strategy=run_match_strategy,
        unresolved=unresolved,
    )


def _session_run_record_from_path(
    run_path: str | Path,
    *,
    cache: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    path = Path(run_path).expanduser().resolve()
    if path.is_dir():
        path = path / "run.json"
    cache_key = str(path)
    if isinstance(cache, dict) and cache_key in cache:
        return dict(cache[cache_key])
    payload = _load_json(path)
    if not isinstance(payload, dict):
        if isinstance(cache, dict):
            cache[cache_key] = {}
        return {}
    messages = payload.get("messages") if isinstance(payload.get("messages"), list) else []
    sent_messages = [
        {
            "index": int(item.get("index") or 0),
            "text": str(item.get("text") or ""),
            "sent": bool(item.get("sent")),
            "send_mode": str(item.get("send_mode") or ""),
        }
        for item in messages
        if isinstance(item, dict) and bool(item.get("sent"))
    ]
    unsent_messages = [
        {
            "index": int(item.get("index") or 0),
            "text": str(item.get("text") or ""),
            "sent": bool(item.get("sent")),
            "send_mode": str(item.get("send_mode") or ""),
        }
        for item in messages
        if isinstance(item, dict) and not bool(item.get("sent"))
    ]
    plan_payload = payload.get("plan") if isinstance(payload.get("plan"), dict) else {}
    record = {
        "run_id": str(payload.get("run_id") or path.parent.name),
        "status": str(payload.get("status") or "").strip(),
        "visit_count": len(payload.get("visits") or []),
        "message_count": len(messages),
        "draft_count": len(unsent_messages),
        "sent_count": int(payload.get("sent_count") or sum(1 for item in messages if isinstance(item, dict) and bool(item.get("sent")))),
        "message_target_username": str(plan_payload.get("message_target_username") or "").strip(),
        "run_dir": str(path.parent),
        "path": str(path),
        "sent_messages": sent_messages[:5],
        "unsent_messages": unsent_messages[:5],
        "sent_preview": [str(item.get("text") or "").strip() for item in sent_messages[:SESSION_MESSAGE_PREVIEW_LIMIT] if str(item.get("text") or "").strip()],
        "draft_preview": [str(item.get("text") or "").strip() for item in unsent_messages[:SESSION_MESSAGE_PREVIEW_LIMIT] if str(item.get("text") or "").strip()],
    }
    if isinstance(cache, dict):
        cache[cache_key] = dict(record)
    return record


def _session_run_record_from_artifact_index(
    artifact_index: dict[str, str],
    *,
    cache: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    run_candidates = _artifact_candidates_from_index(artifact_index, "session_run")
    if not run_candidates:
        return {}
    return _session_run_record_from_path(run_candidates[0], cache=cache)


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
    read_path = resolved
    if resolved == DEFAULT_JOB_INDEX_PATH and not resolved.exists() and LEGACY_JOB_INDEX_PATH.exists():
        read_path = LEGACY_JOB_INDEX_PATH
    payload = _load_json(read_path)
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
    for key in ("run_dir", "job_dir", "state_path", "runtime_config", "log_path", "screenshot_path", "progress_json", "batch_json"):
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


def _workflow_artifact_details_from_job(
    job: dict[str, Any],
    *,
    cache: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolve_cache = cache if isinstance(cache, dict) else {}
    artifacts = dict(job.get("artifact_paths") or {})
    provenance = {str(key): "stored" for key in artifacts if str(key).strip()}
    unresolved: list[str] = []
    if str(job.get("workflow_kind") or "") == "session_run":
        resolved = _resolve_session_artifacts(job, cache=resolve_cache)
        artifacts.update(resolved["artifact_paths"])
        provenance.update(resolved.get("artifact_provenance") or {})
        unresolved.extend(str(item) for item in resolved.get("unresolved") or [] if str(item).strip())
    for step in job.get("steps") or []:
        if not isinstance(step, dict):
            continue
        step_artifacts = _normalize_artifact_paths(step.get("artifact_paths"))
        step_provenance = {str(key): "stored" for key in step_artifacts if str(key).strip()}
        if str(step.get("step_kind") or "") == "session_run":
            resolved = _resolve_session_artifacts(job, step=step, cache=resolve_cache)
            step_artifacts.update(resolved["artifact_paths"])
            step_provenance.update(resolved.get("artifact_provenance") or {})
            unresolved.extend(str(item) for item in resolved.get("unresolved") or [] if str(item).strip())
        artifacts.update(step_artifacts)
        provenance.update(step_provenance)
    return {
        "artifact_paths": artifacts,
        "artifact_provenance": provenance,
        "unresolved": sorted(set(unresolved)),
    }


def workflow_artifact_details(job_id: str, index_path: str | Path = DEFAULT_JOB_INDEX_PATH) -> dict[str, Any]:
    job = get_job(job_id, index_path=index_path)
    if job is None:
        raise KeyError(f"unknown job_id: {job_id}")
    return _workflow_artifact_details_from_job(job)


def workflow_artifact_index(job_id: str, index_path: str | Path = DEFAULT_JOB_INDEX_PATH) -> dict[str, str]:
    details = workflow_artifact_details(job_id, index_path=index_path)
    return dict(details.get("artifact_paths") or {})


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
    invite_job_dir = str(context.get("invite_job_dir") or "").strip()
    if invite_job_dir:
        try:
            from .telegram_gui_helpers import resolve_invite_job_dir

            invite_job_dir = str(resolve_invite_job_dir(invite_job_dir))
        except Exception:
            invite_job_dir = str(Path(invite_job_dir).expanduser().resolve())
    return {
        "input_path": str(context.get("input_path") or "").strip(),
        "invite_job_dir": invite_job_dir,
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
        "progress_summary": dict(snapshot.get("progress_summary") or {}) if isinstance(snapshot, dict) else {},
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
        workflow_artifact_details(str(anchor_job.get("job_id") or ""), index_path=index_path)
        if isinstance(anchor_job, dict)
        else {}
    )
    artifact_paths = dict(artifact_index.get("artifact_paths") or {}) if isinstance(artifact_index, dict) else {}
    payload = {
        "workflow_kind": workflow_kind,
        "active_job": active_job,
        "last_job": last_job,
        "recent_jobs": workflow_jobs[:limit],
        "timeline": _job_timeline(anchor_job or {}, limit=timeline_limit),
        "artifact_index": artifact_paths,
        "artifact_provenance": dict(artifact_index.get("artifact_provenance") or {}) if isinstance(artifact_index, dict) else {},
        "artifact_unresolved": list(artifact_index.get("unresolved") or []) if isinstance(artifact_index, dict) else [],
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
    session_cache: dict[str, dict[str, Any]] = {}
    resolve_cache: dict[str, Any] = {}
    for item in jobs[: max(limit, 1)]:
        job_payload = dict(item)
        if str(job_payload.get("workflow_kind") or "") == "session_run":
            job_artifacts = dict(job_payload.get("artifact_paths") or {})
            job_artifacts.update(_resolve_session_artifacts(job_payload, cache=resolve_cache)["artifact_paths"])
            session_summary = _session_summary_from_artifact_index(
                job_artifacts,
                cache=session_cache,
            )
            if session_summary:
                job_payload["session_summary"] = session_summary
        steps: list[dict[str, Any]] = []
        for step in _job_timeline(item, limit=step_limit):
            if not isinstance(step, dict):
                continue
            step_payload = dict(step)
            if str(step_payload.get("step_kind") or "") == "session_run":
                artifact_source = dict(step_payload.get("artifact_paths") or {})
                artifact_source.update(_resolve_session_artifacts(job_payload, step=step_payload, cache=resolve_cache)["artifact_paths"])
                if not artifact_source:
                    artifact_source = dict(job_payload.get("artifact_paths") or {})
                session_summary = _session_summary_from_artifact_index(
                    artifact_source,
                    cache=session_cache,
                )
                if session_summary:
                    step_payload["session_summary"] = session_summary
            steps.append(step_payload)
        groups.append(
            {
                "job": job_payload,
                "steps": steps,
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
                    "session_summary": dict(job.get("session_summary") or {})
                    if isinstance(job.get("session_summary"), dict)
                    else {},
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
                    "session_summary": dict(step.get("session_summary") or {})
                    if isinstance(step.get("session_summary"), dict)
                    else {},
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
        _append_candidate(LEGACY_PANEL_LOG_PATH)
    elif artifact_kind == "progress_json":
        _append_candidate(artifact_index.get("progress_json"))
        run_dir = artifact_index.get("run_dir")
        if str(run_dir or "").strip():
            _append_candidate(Path(str(run_dir)) / "batch_progress.json")
        _append_from_glob(artifact_index.get("job_dir"), "executions/*/batch_progress.json")
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
    elif artifact_kind == "plan_json":
        _append_candidate(artifact_index.get("plan_json"))
        run_dir = artifact_index.get("run_dir")
        if str(run_dir or "").strip():
            _append_candidate(Path(str(run_dir)) / "plan.json")
    elif artifact_kind == "runtime_config":
        _append_candidate(artifact_index.get("runtime_config"))
    elif artifact_kind == "state_path":
        _append_candidate(artifact_index.get("state_path"))
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


def _session_artifact_shortcuts(artifact_index: dict[str, str]) -> dict[str, str]:
    shortcuts: dict[str, str] = {}
    for artifact_kind in SESSION_ARTIFACT_SHORTCUT_LABELS:
        if artifact_kind in {"run_dir", "runs_dir"}:
            raw_value = str(artifact_index.get(artifact_kind) or "").strip()
            if raw_value:
                shortcuts[artifact_kind] = raw_value
            continue
        candidates = _artifact_candidates_from_index(artifact_index, artifact_kind)
        if candidates:
            shortcuts[artifact_kind] = str(candidates[0])
    return shortcuts


def _workflow_artifact_shortcuts(artifact_index: dict[str, str]) -> dict[str, str]:
    shortcuts: dict[str, str] = {}
    for raw_key in ("job_dir", "run_dir", "runs_dir"):
        raw_value = str(artifact_index.get(raw_key) or "").strip()
        if raw_value:
            shortcuts[raw_key] = raw_value
    for artifact_kind in ARTIFACT_HISTORY_LABELS:
        candidates = _artifact_candidates_from_index(artifact_index, artifact_kind)
        if candidates:
            shortcuts[artifact_kind] = str(candidates[0])
    return shortcuts


def _artifact_status(
    shortcuts: dict[str, str],
    *,
    required: tuple[str, ...],
    unresolved: list[str] | None = None,
) -> dict[str, Any]:
    available = [key for key in required if str(shortcuts.get(key) or "").strip()]
    missing = [key for key in required if key not in available]
    unresolved_clean = [str(item).strip() for item in unresolved or [] if str(item).strip()]
    if not available:
        status = "missing"
    elif missing or unresolved_clean:
        status = "partial"
    else:
        status = "complete"
    return {
        "status": status,
        "available": available,
        "missing": missing,
        "unresolved": unresolved_clean,
    }


def _safe_message_preview(value: Any, *, limit: int = 80) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 1)].rstrip() + "…"


def _session_summary_from_artifact_index(
    artifact_index: dict[str, str],
    *,
    cache: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    record = _session_run_record_from_artifact_index(artifact_index, cache=cache)
    if not record:
        return {}
    return {
        "run_id": str(record.get("run_id") or "").strip(),
        "status": str(record.get("status") or "").strip(),
        "visit_count": int(record.get("visit_count") or 0),
        "message_count": int(record.get("message_count") or 0),
        "draft_count": int(record.get("draft_count") or 0),
        "sent_count": int(record.get("sent_count") or 0),
        "message_target_username": str(record.get("message_target_username") or "").strip(),
        "sent_messages": list(record.get("sent_preview") or []),
        "draft_messages": list(record.get("draft_preview") or []),
        "path": str(record.get("path") or "").strip(),
        "run_dir": str(record.get("run_dir") or "").strip(),
    }


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


def _session_history_state_snapshot() -> dict[str, Any]:
    from .telegram_gui_helpers import session_history_snapshot

    try:
        snapshot = session_history_snapshot()
    except Exception:
        return {}
    return snapshot if isinstance(snapshot, dict) else {}


def _session_history_records_from_jobs(
    jobs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    run_cache: dict[str, dict[str, Any]] = {}
    resolve_cache: dict[str, Any] = {}
    records: list[dict[str, Any]] = []
    seen_paths: set[str] = set()

    def _append_record(job: dict[str, Any], *, step: dict[str, Any] | None = None) -> None:
        resolved = _resolve_session_artifacts(job, step=step, cache=resolve_cache)
        record = _session_run_record_from_artifact_index(
            resolved.get("artifact_paths") if isinstance(resolved.get("artifact_paths"), dict) else {},
            cache=run_cache,
        )
        if not record:
            return
        path = str(record.get("path") or "").strip()
        if not path or path in seen_paths:
            return
        seen_paths.add(path)
        record_with_meta = dict(record)
        record_with_meta["workflow_job_id"] = str(job.get("job_id") or "").strip()
        record_with_meta["workflow_kind"] = str(job.get("workflow_kind") or "").strip()
        record_with_meta["step_id"] = str((step or {}).get("step_id") or "").strip()
        record_with_meta["updated_at"] = str(
            (step or {}).get("completed_at")
            or (step or {}).get("started_at")
            or job.get("updated_at")
            or job.get("completed_at")
            or job.get("started_at")
            or ""
        ).strip()
        records.append(record_with_meta)

    for job in jobs:
        if not isinstance(job, dict):
            continue
        workflow_kind = str(job.get("workflow_kind") or "").strip()
        if workflow_kind == "session_run":
            session_steps = _session_step_records(job)
            if session_steps:
                for step in session_steps:
                    _append_record(job, step=step)
            else:
                _append_record(job)
            continue
        for step in _session_step_records(job):
            _append_record(job, step=step)

    records.sort(
        key=lambda item: (
            str(item.get("updated_at") or ""),
            str(item.get("run_id") or ""),
        )
    )
    return records


def _session_message_settings(job: dict[str, Any] | None) -> dict[str, Any]:
    context = _job_context(job)
    raw = context.get("message_settings")
    return dict(raw) if isinstance(raw, dict) else {}


def _session_current_target_label(job: dict[str, Any] | None, snapshot: dict[str, Any]) -> str:
    settings = _session_message_settings(job)
    targets = [dict(item) for item in settings.get("message_targets") or [] if isinstance(item, dict)]
    cursor = max(_safe_int(snapshot.get("message_target_cursor")), 0)
    if targets:
        target = targets[cursor % len(targets)]
        return str(target.get("label") or target.get("handle") or target.get("username") or "").strip()
    last_run = snapshot.get("last_run") if isinstance(snapshot.get("last_run"), dict) else {}
    return str(last_run.get("message_target_username") or "").strip()


def _session_current_template_preview(job: dict[str, Any] | None, snapshot: dict[str, Any]) -> str:
    settings = _session_message_settings(job)
    templates = [str(item).strip() for item in settings.get("message_templates") or [] if str(item).strip()]
    cursor = max(_safe_int(snapshot.get("message_cursor")), 0)
    if templates:
        return templates[cursor % len(templates)]
    last_run = snapshot.get("last_run") if isinstance(snapshot.get("last_run"), dict) else {}
    for preview_key in ("draft_preview", "sent_preview"):
        items = last_run.get(preview_key) if isinstance(last_run.get(preview_key), list) else []
        for item in items:
            text = str(item or "").strip()
            if text:
                return text
    return ""


def _session_progress_summary_from_jobs(
    jobs: list[dict[str, Any]],
    *,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    session_jobs = [item for item in jobs if str(item.get("workflow_kind") or "").strip() == "session_run"]
    active_job = next((item for item in session_jobs if _job_status(item) == "running"), None)
    last_job = session_jobs[0] if session_jobs else None
    anchor_job = active_job or last_job
    if anchor_job is None:
        eta_reason = "no_session_workflow"
        return {
            "status": str(snapshot.get("status") or "missing"),
            "history_source": str(snapshot.get("history_source") or "missing"),
            "current_phase": "idle",
            "elapsed_seconds": 0,
            "processed_count": 0,
            "selected_target": 0,
            "remaining_in_run": None,
            "messages_sent_total": _safe_int(snapshot.get("messages_sent_total")),
            "rate_per_minute": None,
            "eta_seconds": None,
            "eta_available": False,
            "eta_reason": eta_reason,
            "eta_mode": "unknown",
            "current_target_label": _session_current_target_label(None, snapshot),
            "current_template_preview": _session_current_template_preview(None, snapshot),
            "run_mode": "idle",
            "continuous": False,
            "workflow_job_id": "",
            "next_action_text": "Подготовить и запустить session_run workflow.",
        }

    context = _job_context(anchor_job)
    settings = _session_message_settings(anchor_job)
    continuous = bool(context.get("continuous_session"))
    messages_per_cycle = max(_safe_int(settings.get("messages_per_cycle")), 0)
    total_message_limit = max(_safe_int(settings.get("total_message_limit")), 0)
    messages_sent_total = max(_safe_int(snapshot.get("messages_sent_total")), 0)
    baseline_sent_total = max(_safe_int(context.get("session_baseline_sent_total")), 0)
    bounded_target_total = context.get("session_target_sent_total")
    bounded_target_total_int = _safe_int(bounded_target_total, default=-1)
    if bounded_target_total_int >= 0:
        selected_target = max(bounded_target_total_int - baseline_sent_total, 0)
    elif not continuous and messages_per_cycle > 0:
        selected_target = messages_per_cycle
    else:
        selected_target = 0
    if active_job:
        processed_count = max(messages_sent_total - baseline_sent_total, 0)
        elapsed_seconds = _elapsed_seconds_between(anchor_job.get("started_at")) or 0
    else:
        last_run = snapshot.get("last_run") if isinstance(snapshot.get("last_run"), dict) else {}
        processed_count = max(_safe_int(last_run.get("sent_count") or last_run.get("message_count")), 0)
        elapsed_seconds = _elapsed_seconds_between(anchor_job.get("started_at"), anchor_job.get("completed_at")) or 0
    rate_per_minute = None
    if processed_count > 0 and elapsed_seconds > 0:
        rate_per_minute = round((float(processed_count) * 60.0) / float(elapsed_seconds), 2)
    eta_seconds: int | None
    remaining_in_run: int | None
    eta_mode = "unknown"
    if continuous:
        remaining_in_run = None
        eta_seconds = None
        eta_mode = "continuous"
        eta_available = False
        eta_reason = "continuous_session"
    elif selected_target > 0:
        remaining_in_run = max(selected_target - processed_count, 0)
        if remaining_in_run <= 0:
            eta_seconds = 0
            eta_mode = "bounded"
            eta_available = True
            eta_reason = "bounded_target_complete"
        elif rate_per_minute and rate_per_minute > 0:
            eta_seconds = max(int(round((float(remaining_in_run) * 60.0) / float(rate_per_minute))), 0)
            eta_mode = "bounded"
            eta_available = True
            eta_reason = "bounded_target"
        else:
            eta_seconds = None
            eta_mode = "bounded"
            eta_available = False
            eta_reason = "insufficient_rate"
    else:
        remaining_in_run = None
        eta_seconds = None
        eta_available = False
        eta_reason = "no_bounded_target"

    return {
        "status": _job_status(anchor_job) or str(snapshot.get("status") or "ready"),
        "history_source": str(snapshot.get("history_source") or "unified_jobs"),
        "current_phase": str(anchor_job.get("phase") or anchor_job.get("status") or "ready"),
        "elapsed_seconds": elapsed_seconds,
        "processed_count": processed_count,
        "selected_target": selected_target,
        "remaining_in_run": remaining_in_run,
        "messages_sent_total": messages_sent_total,
        "messages_per_cycle": messages_per_cycle,
        "total_message_limit": total_message_limit,
        "rate_per_minute": rate_per_minute,
        "eta_seconds": eta_seconds,
        "eta_available": eta_available,
        "eta_reason": eta_reason,
        "eta_mode": eta_mode,
        "current_target_label": _session_current_target_label(anchor_job, snapshot),
        "current_template_preview": _session_current_template_preview(anchor_job, snapshot),
        "run_mode": "continuous" if continuous else "bounded",
        "continuous": continuous,
        "workflow_job_id": str(anchor_job.get("job_id") or ""),
        "next_action_text": "Ждать завершения session_run workflow." if active_job else "Запустить новый session_run workflow.",
    }


def _session_snapshot_from_jobs(jobs: list[dict[str, Any]]) -> dict[str, Any]:
    fallback = _session_history_state_snapshot()
    records = _session_history_records_from_jobs(jobs)
    if not records and not fallback:
        return {
            "status": "missing",
            "state_file": str(_session_runtime_defaults()[0]),
            "runs_dir": str(_session_runtime_defaults()[1]),
            "messages_sent_total": 0,
            "message_cursor": 0,
            "message_target_cursor": 0,
            "history": [],
            "latest_runs": [],
            "last_run": {},
            "history_source": "missing",
            "progress_summary": {
                "status": "missing",
                "history_source": "missing",
                "current_phase": "idle",
                "elapsed_seconds": 0,
                "processed_count": 0,
                "selected_target": 0,
                "remaining_in_run": None,
                "messages_sent_total": 0,
                "rate_per_minute": None,
                "eta_seconds": None,
                "eta_available": False,
                "eta_reason": "missing_history",
                "eta_mode": "unknown",
                "current_target_label": "",
                "current_template_preview": "",
                "run_mode": "idle",
                "continuous": False,
                "workflow_job_id": "",
                "next_action_text": "Подготовить и запустить session_run workflow.",
            },
        }
    if not records:
        snapshot = dict(fallback)
        snapshot["history_source"] = "session_history_fallback"
        snapshot["progress_summary"] = _session_progress_summary_from_jobs(jobs, snapshot=snapshot)
        return snapshot

    latest_runs = records[-8:]
    messages_sent_total = int(fallback.get("messages_sent_total") or sum(int(item.get("sent_count") or 0) for item in records))
    snapshot = {
        "status": "ready",
        "state_file": str(fallback.get("state_file") or _session_runtime_defaults()[0]),
        "runs_dir": str(fallback.get("runs_dir") or _session_runtime_defaults()[1]),
        "messages_sent_total": messages_sent_total,
        "message_cursor": int(fallback.get("message_cursor") or 0),
        "message_target_cursor": int(fallback.get("message_target_cursor") or 0),
        "history": list(fallback.get("history") or [])[-8:] if isinstance(fallback.get("history"), list) else [],
        "latest_runs": latest_runs,
        "last_run": latest_runs[-1] if latest_runs else {},
        "history_source": "unified_jobs+state_fallback" if fallback else "unified_jobs",
    }
    snapshot["progress_summary"] = _session_progress_summary_from_jobs(jobs, snapshot=snapshot)
    return snapshot


def repair_session_artifacts(
    *,
    job_id: str | None = None,
    profile_name: str | None = None,
    profile_dir: str | Path | None = None,
    apply: bool = False,
    index_path: str | Path = DEFAULT_JOB_INDEX_PATH,
) -> dict[str, Any]:
    index = load_job_index(index_path)
    resolve_cache: dict[str, Any] = {}
    matched_jobs: list[str] = []
    matched_steps: list[dict[str, Any]] = []
    repaired_jobs: list[dict[str, Any]] = []
    repaired_steps: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    changed = False

    resolved_profile_dir = str(Path(profile_dir).expanduser().resolve()) if profile_dir is not None else ""
    for raw_job_index, raw_job in enumerate(index.get("jobs", [])):
        if not isinstance(raw_job, dict):
            continue
        job = normalize_job_record(raw_job)
        if job_id is not None and str(job.get("job_id") or "") != str(job_id):
            continue
        if profile_name is not None and str(job.get("profile_name") or "") != str(profile_name):
            continue
        if profile_dir is not None and str(job.get("profile_dir") or "") != resolved_profile_dir:
            continue
        workflow_kind = str(job.get("workflow_kind") or "").strip()
        session_steps = _session_step_records(job)
        is_session_parent = workflow_kind == "session_run"
        if not is_session_parent and not session_steps:
            continue
        matched_jobs.append(str(job.get("job_id") or ""))

        repaired_step_records: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for step in session_steps:
            resolved = _resolve_session_artifacts(job, step=step, cache=resolve_cache)
            matched_steps.append(
                {
                    "job_id": str(job.get("job_id") or ""),
                    "step_id": str(step.get("step_id") or ""),
                    "artifact_paths": dict(resolved.get("artifact_paths") or {}),
                    "run_match_strategy": str(resolved.get("run_match_strategy") or ""),
                    "unresolved": list(resolved.get("unresolved") or []),
                }
            )
            resolved_artifacts = dict(resolved.get("artifact_paths") or {})
            has_session_run = bool(resolved_artifacts.get("run_dir") or resolved_artifacts.get("session_run"))
            if has_session_run:
                repaired_step_records.append((step, resolved))
                existing_step_artifacts = _normalize_artifact_paths(step.get("artifact_paths"))
                additions = {key: value for key, value in resolved_artifacts.items() if existing_step_artifacts.get(key) != value}
                if additions:
                    repaired_steps.append(
                        {
                            "job_id": str(job.get("job_id") or ""),
                            "step_id": str(step.get("step_id") or ""),
                            "artifact_paths": additions,
                            "run_match_strategy": str(resolved.get("run_match_strategy") or ""),
                        }
                    )
                    if apply:
                        raw_steps = [dict(item) for item in raw_job.get("steps") or [] if isinstance(item, dict)]
                        for raw_index, raw_step in enumerate(raw_steps):
                            if not isinstance(raw_step, dict):
                                continue
                            if str(raw_step.get("step_id") or "") != str(step.get("step_id") or ""):
                                continue
                            merged = dict(raw_step.get("artifact_paths") or {})
                            merged.update(additions)
                            raw_step["artifact_paths"] = merged
                            raw_steps[raw_index] = raw_step
                            raw_job["steps"] = raw_steps
                            changed = True
                            break
            else:
                unresolved.append(
                    {
                        "job_id": str(job.get("job_id") or ""),
                        "step_id": str(step.get("step_id") or ""),
                        "kind": "step",
                        "issues": list(resolved.get("unresolved") or []),
                    }
                )

        if is_session_parent:
            freshest_step_resolution: dict[str, Any] | None = None
            if repaired_step_records:
                freshest_step_resolution = repaired_step_records[-1][1]
            else:
                parent_resolution = _resolve_session_artifacts(job, cache=resolve_cache)
                parent_artifacts = dict(parent_resolution.get("artifact_paths") or {})
                if parent_artifacts.get("run_dir") or parent_artifacts.get("session_run"):
                    freshest_step_resolution = parent_resolution
                else:
                    unresolved.append(
                        {
                            "job_id": str(job.get("job_id") or ""),
                            "kind": "job",
                            "issues": list(parent_resolution.get("unresolved") or []),
                        }
                    )

            if freshest_step_resolution is not None:
                resolved_artifacts = dict(freshest_step_resolution.get("artifact_paths") or {})
                existing_job_artifacts = _normalize_artifact_paths(raw_job.get("artifact_paths"))
                additions = {key: value for key, value in resolved_artifacts.items() if existing_job_artifacts.get(key) != value}
                context_patch: dict[str, Any] = {}
                if resolved_artifacts.get("run_dir"):
                    existing_run_dir = str(((raw_job.get("context") or {}) if isinstance(raw_job.get("context"), dict) else {}).get("last_session_run_dir") or "").strip()
                    if existing_run_dir != str(resolved_artifacts.get("run_dir") or ""):
                        context_patch["last_session_run_dir"] = str(resolved_artifacts.get("run_dir") or "")
                recent_step = ((raw_job.get("context") or {}) if isinstance(raw_job.get("context"), dict) else {}).get("recent_step")
                if isinstance(recent_step, dict):
                    recent_step_artifacts = dict(recent_step.get("artifact_paths") or {})
                    merged_recent_step_artifacts = dict(recent_step_artifacts)
                    merged_recent_step_artifacts.update(resolved_artifacts)
                    if merged_recent_step_artifacts != recent_step_artifacts:
                        updated_recent_step = dict(recent_step)
                        updated_recent_step["artifact_paths"] = merged_recent_step_artifacts
                        context_patch["recent_step"] = updated_recent_step
                if additions or context_patch:
                    repaired_jobs.append(
                        {
                            "job_id": str(job.get("job_id") or ""),
                            "artifact_paths": additions,
                            "context_patch": context_patch,
                            "run_match_strategy": str(freshest_step_resolution.get("run_match_strategy") or ""),
                        }
                    )
                    if apply:
                        merged_job_artifacts = dict(raw_job.get("artifact_paths") or {})
                        merged_job_artifacts.update(additions)
                        raw_job["artifact_paths"] = merged_job_artifacts
                        if context_patch:
                            merged_context = dict(raw_job.get("context") or {})
                            merged_context.update(context_patch)
                            raw_job["context"] = merged_context
                        changed = True

        index["jobs"][raw_job_index] = normalize_job_record(raw_job)

    if apply and changed:
        save_job_index(index, index_path=index_path)
    return {
        "status": "completed",
        "apply": bool(apply),
        "changed": bool(changed),
        "matched_jobs": matched_jobs,
        "matched_steps": matched_steps,
        "repaired_jobs": repaired_jobs,
        "repaired_steps": repaired_steps,
        "unresolved": unresolved,
    }


def repair_invite_artifacts(
    *,
    job_id: str | None = None,
    profile_name: str | None = None,
    profile_dir: str | Path | None = None,
    apply: bool = False,
    index_path: str | Path = DEFAULT_JOB_INDEX_PATH,
) -> dict[str, Any]:
    index = load_job_index(index_path)
    resolve_cache: dict[str, Any] = {}
    matched_jobs: list[str] = []
    matched_steps: list[dict[str, Any]] = []
    repaired_jobs: list[dict[str, Any]] = []
    repaired_steps: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    changed = False

    resolved_profile_dir = str(Path(profile_dir).expanduser().resolve()) if profile_dir is not None else ""
    for raw_job_index, raw_job in enumerate(index.get("jobs", [])):
        if not isinstance(raw_job, dict):
            continue
        job = normalize_job_record(raw_job)
        if job_id is not None and str(job.get("job_id") or "") != str(job_id):
            continue
        if profile_name is not None and str(job.get("profile_name") or "") != str(profile_name):
            continue
        if profile_dir is not None and str(job.get("profile_dir") or "") != resolved_profile_dir:
            continue
        workflow_kind = str(job.get("workflow_kind") or "").strip()
        invite_steps = [
            _normalize_step_record(item, position=index)
            for index, item in enumerate(job.get("steps") or [])
            if isinstance(item, dict) and str(item.get("step_kind") or "").strip() == "invite_batch"
        ]
        if workflow_kind not in {"invite_batch", "combined_pattern"} and not invite_steps:
            continue
        matched_jobs.append(str(job.get("job_id") or ""))

        repaired_step_records: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for step in invite_steps:
            resolved = _resolve_invite_artifacts(job, step=step, cache=resolve_cache)
            matched_steps.append(
                {
                    "job_id": str(job.get("job_id") or ""),
                    "step_id": str(step.get("step_id") or ""),
                    "stored_artifact_paths": dict(resolved.get("stored_artifact_paths") or {}),
                    "artifact_paths": dict(resolved.get("artifact_paths") or {}),
                    "job_dir_match_strategy": str(resolved.get("job_dir_match_strategy") or ""),
                    "run_match_strategy": str(resolved.get("run_match_strategy") or ""),
                    "unresolved": list(resolved.get("unresolved") or []),
                }
            )
            resolved_artifacts = dict(resolved.get("artifact_paths") or {})
            if resolved_artifacts.get("job_dir"):
                repaired_step_records.append((step, resolved))
                existing_step_artifacts = _normalize_artifact_paths(step.get("artifact_paths"))
                additions = {
                    key: value
                    for key, value in resolved_artifacts.items()
                    if existing_step_artifacts.get(key) != value
                }
                if additions:
                    repaired_steps.append(
                        {
                            "job_id": str(job.get("job_id") or ""),
                            "step_id": str(step.get("step_id") or ""),
                            "stored_artifact_paths": dict(resolved.get("stored_artifact_paths") or {}),
                            "artifact_paths": additions,
                            "job_dir_match_strategy": str(resolved.get("job_dir_match_strategy") or ""),
                            "run_match_strategy": str(resolved.get("run_match_strategy") or ""),
                        }
                    )
                    if apply:
                        raw_steps = [dict(item) for item in raw_job.get("steps") or [] if isinstance(item, dict)]
                        for raw_step_index, raw_step in enumerate(raw_steps):
                            if str(raw_step.get("step_id") or "") != str(step.get("step_id") or ""):
                                continue
                            merged = dict(raw_step.get("artifact_paths") or {})
                            merged.update(additions)
                            raw_step["artifact_paths"] = merged
                            raw_steps[raw_step_index] = raw_step
                            raw_job["steps"] = raw_steps
                            changed = True
                            break
            else:
                unresolved.append(
                    {
                        "job_id": str(job.get("job_id") or ""),
                        "step_id": str(step.get("step_id") or ""),
                        "kind": "step",
                        "issues": list(resolved.get("unresolved") or []),
                    }
                )

        if workflow_kind not in {"invite_batch", "combined_pattern"}:
            index["jobs"][raw_job_index] = normalize_job_record(raw_job)
            continue

        parent_resolution = _resolve_invite_artifacts(job, cache=resolve_cache)
        resolved_artifacts = dict(parent_resolution.get("artifact_paths") or {})
        existing_job_artifacts = _normalize_artifact_paths(raw_job.get("artifact_paths"))
        parent_artifact_keys = {"job_dir", "state_path"}
        if workflow_kind == "invite_batch":
            parent_artifact_keys.update({"run_dir", "progress_json", "batch_json", "execution_record", "log_path"})
        additions = {
            key: value
            for key, value in resolved_artifacts.items()
            if key in parent_artifact_keys and existing_job_artifacts.get(key) != value
        }
        context_patch: dict[str, Any] = {}
        existing_context = dict(raw_job.get("context") or {}) if isinstance(raw_job.get("context"), dict) else {}
        if resolved_artifacts.get("job_dir") and str(existing_context.get("invite_job_dir") or "").strip() != str(resolved_artifacts.get("job_dir") or ""):
            context_patch["invite_job_dir"] = str(resolved_artifacts.get("job_dir") or "")
        if resolved_artifacts.get("run_dir") and str(existing_context.get("last_invite_run_dir") or "").strip() != str(resolved_artifacts.get("run_dir") or ""):
            context_patch["last_invite_run_dir"] = str(resolved_artifacts.get("run_dir") or "")
        recent_step = existing_context.get("recent_step")
        if isinstance(recent_step, dict) and str(recent_step.get("step_kind") or "") == "invite_batch" and resolved_artifacts:
            recent_step_artifacts = dict(recent_step.get("artifact_paths") or {})
            merged_recent_step_artifacts = dict(recent_step_artifacts)
            merged_recent_step_artifacts.update(resolved_artifacts)
            if merged_recent_step_artifacts != recent_step_artifacts:
                updated_recent_step = dict(recent_step)
                updated_recent_step["artifact_paths"] = merged_recent_step_artifacts
                context_patch["recent_step"] = updated_recent_step
        if additions or context_patch:
            repaired_jobs.append(
                {
                    "job_id": str(job.get("job_id") or ""),
                    "stored_artifact_paths": dict(parent_resolution.get("stored_artifact_paths") or {}),
                    "artifact_paths": additions,
                    "context_patch": context_patch,
                    "job_dir_match_strategy": str(parent_resolution.get("job_dir_match_strategy") or ""),
                    "run_match_strategy": str(parent_resolution.get("run_match_strategy") or ""),
                }
            )
            if apply:
                merged_job_artifacts = dict(raw_job.get("artifact_paths") or {})
                merged_job_artifacts.update(additions)
                raw_job["artifact_paths"] = merged_job_artifacts
                if context_patch:
                    merged_context = dict(raw_job.get("context") or {})
                    merged_context.update(context_patch)
                    raw_job["context"] = merged_context
                changed = True
        elif not resolved_artifacts.get("job_dir"):
            unresolved.append(
                {
                    "job_id": str(job.get("job_id") or ""),
                    "kind": "job",
                    "issues": list(parent_resolution.get("unresolved") or []),
                }
            )

        index["jobs"][raw_job_index] = normalize_job_record(raw_job)

    if apply and changed:
        save_job_index(index, index_path=index_path)
    return {
        "status": "completed",
        "apply": bool(apply),
        "changed": bool(changed),
        "matched_jobs": matched_jobs,
        "matched_steps": matched_steps,
        "repaired_jobs": repaired_jobs,
        "repaired_steps": repaired_steps,
        "unresolved": unresolved,
    }


def _repair_report_would_change(report: dict[str, Any]) -> bool:
    return bool(report.get("repaired_jobs") or report.get("repaired_steps"))


def _repair_report_counts(report: dict[str, Any]) -> dict[str, int]:
    return {
        "matched_jobs": len(report.get("matched_jobs") or []),
        "matched_steps": len(report.get("matched_steps") or []),
        "repaired_jobs": len(report.get("repaired_jobs") or []),
        "repaired_steps": len(report.get("repaired_steps") or []),
        "unresolved": len(report.get("unresolved") or []),
    }


def _tagged_unresolved(source: str, report: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in report.get("unresolved") or []:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        row["source"] = source
        rows.append(row)
    return rows


def repair_historical_artifacts(
    *,
    job_id: str | None = None,
    profile_name: str | None = None,
    profile_dir: str | Path | None = None,
    apply: bool = False,
    index_path: str | Path = DEFAULT_JOB_INDEX_PATH,
) -> dict[str, Any]:
    session_report = repair_session_artifacts(
        job_id=job_id,
        profile_name=profile_name,
        profile_dir=profile_dir,
        apply=apply,
        index_path=index_path,
    )
    invite_report = repair_invite_artifacts(
        job_id=job_id,
        profile_name=profile_name,
        profile_dir=profile_dir,
        apply=apply,
        index_path=index_path,
    )
    session_counts = _repair_report_counts(session_report)
    invite_counts = _repair_report_counts(invite_report)
    would_change = _repair_report_would_change(session_report) or _repair_report_would_change(invite_report)
    changed = bool(session_report.get("changed") or invite_report.get("changed"))
    unresolved = _tagged_unresolved("session", session_report) + _tagged_unresolved("invite", invite_report)
    matched_jobs = sorted(
        {
            str(item)
            for item in (session_report.get("matched_jobs") or []) + (invite_report.get("matched_jobs") or [])
            if str(item).strip()
        }
    )
    return {
        "status": "completed",
        "apply": bool(apply),
        "changed": changed,
        "would_change": would_change,
        "matched_jobs": matched_jobs,
        "repair_counts": {
            "session": session_counts,
            "invite": invite_counts,
            "total": {
                "matched_jobs": len(matched_jobs),
                "matched_steps": session_counts["matched_steps"] + invite_counts["matched_steps"],
                "repaired_jobs": session_counts["repaired_jobs"] + invite_counts["repaired_jobs"],
                "repaired_steps": session_counts["repaired_steps"] + invite_counts["repaired_steps"],
                "unresolved": session_counts["unresolved"] + invite_counts["unresolved"],
            },
        },
        "session_report": session_report,
        "invite_report": invite_report,
        "unresolved": unresolved,
    }


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
        "progress_json": [_bucket_artifacts("invite_batch"), artifact_index],
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
    session_artifacts = _bucket_artifacts("session_run")
    for key, value in _session_artifact_shortcuts(session_artifacts).items():
        shortcuts.setdefault(key, value)
    return shortcuts


def _provenance_for_path(
    artifact_index: dict[str, str],
    artifact_provenance: dict[str, str],
    path: str,
) -> str:
    normalized_path = str(path or "").strip()
    if not normalized_path:
        return ""
    for key, value in artifact_index.items():
        if str(value or "").strip() == normalized_path:
            provenance = str(artifact_provenance.get(key) or "").strip()
            if provenance:
                return provenance
    return ""


def _artifact_shortcut_provenance(
    shortcuts: dict[str, str],
    *,
    artifact_index: dict[str, str],
    artifact_provenance: dict[str, str],
) -> dict[str, str]:
    result: dict[str, str] = {}
    for artifact_kind, path in shortcuts.items():
        provenance = str(artifact_provenance.get(artifact_kind) or "").strip()
        if not provenance:
            provenance = _provenance_for_path(artifact_index, artifact_provenance, str(path))
        if not provenance and artifact_kind in {"session_run", "screenshot"}:
            provenance = "fallback"
        if provenance:
            result[artifact_kind] = provenance
    return result


def _artifact_center_rows(shortcuts: dict[str, str], provenance: dict[str, str] | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for artifact_kind, label in ARTIFACT_CENTER_LABELS.items():
        path = str(shortcuts.get(artifact_kind) or "").strip()
        rows.append(
            {
                "artifact_kind": artifact_kind,
                "label": label,
                "path": path,
                "available": bool(path),
                "provenance": str((provenance or {}).get(artifact_kind) or ""),
            }
        )
    return rows


def _profile_artifact_history_from_jobs(
    jobs: list[dict[str, Any]],
    *,
    index_path: str | Path,
    limit: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for job in jobs:
        details = workflow_artifact_details(str(job.get("job_id") or ""), index_path=index_path)
        artifact_index = dict(details.get("artifact_paths") or {})
        artifact_provenance = {
            str(key): str(value)
            for key, value in (details.get("artifact_provenance") or {}).items()
            if str(key).strip() and str(value).strip()
        }
        for artifact_kind, label in ARTIFACT_HISTORY_LABELS.items():
            candidates = _artifact_candidates_from_index(artifact_index, artifact_kind)
            if not candidates:
                continue
            path = str(candidates[0])
            provenance = str(artifact_provenance.get(artifact_kind) or "").strip()
            if not provenance:
                provenance = _provenance_for_path(artifact_index, artifact_provenance, path)
            dedupe_key = (artifact_kind, path)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            rows.append(
                {
                    "artifact_kind": artifact_kind,
                    "label": label,
                    "path": path,
                    "workflow_kind": str(job.get("workflow_kind") or "").strip(),
                    "job_id": str(job.get("job_id") or "").strip(),
                    "status": _job_status(job),
                    "summary": str(job.get("summary") or "").strip(),
                    "updated_at": _job_timestamp(job),
                    "provenance": provenance,
                }
            )
            if len(rows) >= max(limit, 1):
                return rows
    return rows


def _profile_artifact_details_from_jobs(
    jobs: list[dict[str, Any]],
    *,
    workflow_buckets: dict[str, dict[str, Any]],
    index_path: str | Path,
) -> dict[str, Any]:
    artifact_index: dict[str, str] = {}
    artifact_provenance: dict[str, str] = {}

    def _merge_job_artifacts(job: dict[str, Any] | None, *, overwrite: bool) -> None:
        if not isinstance(job, dict) or not job:
            return
        payload = workflow_artifact_details(str(job.get("job_id") or ""), index_path=index_path)
        artifact_paths = dict(payload.get("artifact_paths") or {})
        provenance = dict(payload.get("artifact_provenance") or {})
        for key, value in artifact_paths.items():
            if overwrite or key not in artifact_index:
                artifact_index[key] = value
                artifact_provenance[key] = str(provenance.get(key) or "stored")

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
        bucket_provenance = bucket.get("artifact_provenance") if isinstance(bucket.get("artifact_provenance"), dict) else {}
        for key, value in bucket_artifacts.items():
            normalized_key = str(key).strip()
            normalized_value = str(value).strip()
            if normalized_key and normalized_value and normalized_key not in artifact_index:
                artifact_index[normalized_key] = normalized_value
                artifact_provenance[normalized_key] = str(bucket_provenance.get(normalized_key) or "stored")
    return {
        "artifact_paths": artifact_index,
        "artifact_provenance": artifact_provenance,
    }


def _profile_artifact_index_from_jobs(
    jobs: list[dict[str, Any]],
    *,
    workflow_buckets: dict[str, dict[str, Any]],
    index_path: str | Path,
) -> dict[str, str]:
    details = _profile_artifact_details_from_jobs(
        jobs,
        workflow_buckets=workflow_buckets,
        index_path=index_path,
    )
    return dict(details.get("artifact_paths") or {})


def _combined_phase_label(phase: str) -> str:
    mapping = {
        "contact_add": "Шаг 1: добавление контактов",
        "review": "Добавление завершилось с ошибками",
        "session_ready": "Шаг 2 готов: можно запускать сессию",
        "session_running": "Шаг 2 выполняется: сессия работает",
        "stopped": "Остановлено / завершено",
    }
    return mapping.get(str(phase or "").strip(), "Неизвестная фаза")


def _combined_progress_summary(
    *,
    bucket: dict[str, Any],
    state: dict[str, Any],
    session_snapshot: dict[str, Any],
) -> dict[str, Any]:
    from .telegram_gui_helpers import contact_job_snapshot, parse_combined_step_pattern

    active_job = bucket.get("active_job") if isinstance(bucket.get("active_job"), dict) else None
    resume_decision = bucket.get("resume_decision") if isinstance(bucket.get("resume_decision"), dict) else {}
    phase = str(state.get("phase") or "contact_add").strip() or "contact_add"
    pattern_tokens = parse_combined_step_pattern(str(state.get("step_pattern") or ""))
    cursor = max(_safe_int(state.get("step_cursor")), 0)
    current_step_code = pattern_tokens[cursor % len(pattern_tokens)] if pattern_tokens else "1"
    next_step_code = pattern_tokens[(cursor + 1) % len(pattern_tokens)] if pattern_tokens else "2"
    invite_snapshot = {}
    invite_job_dir = str(state.get("invite_job_dir") or "").strip()
    if invite_job_dir:
        try:
            invite_snapshot = contact_job_snapshot(invite_job_dir)
        except Exception:
            invite_snapshot = {}
    elapsed_seconds = (
        _elapsed_seconds_between((active_job or {}).get("started_at"))
        if isinstance(active_job, dict)
        else _elapsed_seconds_between(state.get("updated_at"), state.get("updated_at"))
    ) or 0
    waiting_reason = str(state.get("next_hint") or state.get("last_summary") or resume_decision.get("action_text") or "").strip()
    child_progress = {}
    child_history_source = ""
    if phase in {"contact_add", "review", "session_ready"} and isinstance(invite_snapshot.get("progress_summary"), dict):
        child_progress = dict(invite_snapshot.get("progress_summary") or {})
        child_history_source = str(child_progress.get("history_source") or "invite")
    elif phase in {"session_running", "stopped"} and isinstance(session_snapshot.get("progress_summary"), dict):
        child_progress = dict(session_snapshot.get("progress_summary") or {})
        child_history_source = str(child_progress.get("history_source") or "session")
    child_eta_mode = str(child_progress.get("eta_mode") or "")
    child_eta_seconds = child_progress.get("eta_seconds")
    child_eta_available = bool(child_progress.get("eta_available")) or (
        child_eta_mode == "bounded" and child_eta_seconds is not None
    )
    session_run_mode = str((session_snapshot.get("progress_summary") or {}).get("run_mode") or "")
    continuous_blocker = phase == "session_running" and session_run_mode == "continuous"
    recoverable = bool((bucket.get("recoverable_job") if isinstance(bucket.get("recoverable_job"), dict) else None))
    return {
        "status": str((active_job or {}).get("status") or state.get("job_status") or state.get("last_status") or "idle"),
        "phase": phase,
        "phase_label": _combined_phase_label(phase),
        "current_step_code": current_step_code,
        "current_step_label": "добавление контактов" if current_step_code == "1" else "сессия и сообщения",
        "next_step_code": next_step_code,
        "next_step_label": "добавление контактов" if next_step_code == "1" else "сессия и сообщения",
        "elapsed_seconds": elapsed_seconds,
        "waiting_reason": waiting_reason,
        "recoverable": recoverable,
        "recoverable_hint": str(resume_decision.get("hint") or ""),
        "child_history_source": child_history_source,
        "child_progress": child_progress,
        "child_status": str(child_progress.get("status") or ""),
        "child_processed_count": _safe_int(child_progress.get("processed_count")),
        "child_selected_target": _safe_int(child_progress.get("selected_target")),
        "child_remaining_in_run": child_progress.get("remaining_in_run"),
        "child_rate_per_minute": child_progress.get("rate_per_minute"),
        "child_eta_seconds": child_eta_seconds if child_eta_available else None,
        "child_eta_available": child_eta_available,
        "child_eta_mode": child_eta_mode,
        "invite_pending_total": _safe_int(invite_snapshot.get("pending_total")),
        "invite_failed_total": _safe_int(invite_snapshot.get("failed_total")),
        "invite_added_total": _safe_int(invite_snapshot.get("added_total")),
        "session_eta_mode": str((session_snapshot.get("progress_summary") or {}).get("eta_mode") or ""),
        "session_run_mode": session_run_mode,
        "continuous_blocker": continuous_blocker,
        "pattern_advancement_blocked": continuous_blocker,
        "pattern_advancement_blocker": (
            "Непрерывный session_run выполняется до ручного Стопа; следующий шаг pattern не продвинется автоматически."
            if continuous_blocker
            else ""
        ),
        "workflow_job_id": str(state.get("workflow_job_id") or ""),
    }


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
    from .workflows import combined_state_from_jobs

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
    session_snapshot = _session_snapshot_from_jobs(jobs)
    session_bucket = workflow_buckets.get("session_run") if isinstance(workflow_buckets.get("session_run"), dict) else None
    if isinstance(session_bucket, dict):
        session_artifacts = (
            session_bucket.get("artifact_index")
            if isinstance(session_bucket.get("artifact_index"), dict)
            else {}
        )
        session_shortcuts = _session_artifact_shortcuts(
            {str(key): str(value) for key, value in session_artifacts.items()}
        )
        session_artifact_status = _artifact_status(
            session_shortcuts,
            required=("session_run", "plan_json", "runtime_config", "state_path"),
            unresolved=list(session_bucket.get("artifact_unresolved") or []),
        )
        session_progress = dict(session_snapshot.get("progress_summary") or {})
        session_progress["next_action_text"] = str(session_bucket.get("next_operator_action") or session_progress.get("next_action_text") or "")
        session_progress["artifact_status"] = session_artifact_status
        session_progress["artifact_shortcuts"] = dict(session_shortcuts)
        session_progress["artifact_provenance"] = dict(session_bucket.get("artifact_provenance") or {})
        session_snapshot["progress_summary"] = session_progress
        session_bucket["progress_summary"] = dict(session_progress)
        session_bucket["session_snapshot"] = dict(session_snapshot)
        session_bucket["artifact_shortcuts"] = dict(session_shortcuts)
        session_bucket["artifact_status"] = session_artifact_status
    invite_bucket = workflow_buckets.get("invite_batch") if isinstance(workflow_buckets.get("invite_batch"), dict) else {}
    combined_state = combined_state_from_jobs(
        profile_name=profile_name,
        profile_dir=profile_dir,
        index_path=index_path,
    ) or {}
    combined_bucket = workflow_buckets.get("combined_pattern") if isinstance(workflow_buckets.get("combined_pattern"), dict) else None
    if isinstance(combined_bucket, dict):
        combined_artifacts = (
            combined_bucket.get("artifact_index")
            if isinstance(combined_bucket.get("artifact_index"), dict)
            else {}
        )
        combined_shortcuts = _workflow_artifact_shortcuts(
            {str(key): str(value) for key, value in combined_artifacts.items()}
        )
        combined_bucket["combined_state"] = dict(combined_state)
        combined_bucket["progress_summary"] = _combined_progress_summary(
            bucket=combined_bucket,
            state=combined_state,
            session_snapshot=session_snapshot,
        )
        combined_bucket["parent_artifact_shortcuts"] = dict(combined_shortcuts)
        combined_bucket["artifact_shortcuts"] = dict(combined_shortcuts)
        combined_bucket["child_artifact_shortcuts"] = {
            "invite_batch": dict(invite_bucket.get("artifact_index") or {}),
            "session_run": dict((session_bucket or {}).get("artifact_shortcuts") or {}),
        }
        combined_bucket["child_artifact_provenance"] = {
            "invite_batch": dict(invite_bucket.get("artifact_provenance") or {}),
            "session_run": dict((session_bucket or {}).get("artifact_provenance") or {}),
        }
    resume_decision = _workflow_resume_decision(
        active_job=active_workflow,
        recoverable_job=recoverable_workflow,
        last_job=recent_jobs[0] if recent_jobs else None,
    )
    artifact_details = _profile_artifact_details_from_jobs(
        jobs,
        workflow_buckets=workflow_buckets,
        index_path=index_path,
    )
    artifact_index = dict(artifact_details.get("artifact_paths") or {})
    artifact_index_provenance = dict(artifact_details.get("artifact_provenance") or {})
    artifact_shortcuts = _resolved_artifact_shortcuts(
        artifact_index,
        workflow_buckets=workflow_buckets,
    )
    artifact_provenance = _artifact_shortcut_provenance(
        artifact_shortcuts,
        artifact_index=artifact_index,
        artifact_provenance=artifact_index_provenance,
    )
    artifact_history = _profile_artifact_history_from_jobs(
        jobs,
        index_path=index_path,
        limit=max(limit * 3, 10),
    )
    current_lock = get_profile_lock(profile_name=profile_name, profile_dir=profile_dir)
    try:
        profile_status = get_profile_status(profile_dir)
    except Exception as exc:
        profile_status = {"status": "error", "error": str(exc), "running": False, "windows": []}
    capabilities = platform_capabilities()
    display_session = capabilities.get("display_session") if isinstance(capabilities.get("display_session"), dict) else {}
    window_automation = capabilities.get("window_automation") if isinstance(capabilities.get("window_automation"), dict) else {}
    capability_warnings: list[str] = []
    for raw_items in (display_session.get("warnings"), window_automation.get("warnings")):
        if not isinstance(raw_items, list):
            continue
        for item in raw_items:
            text = str(item or "").strip()
            if text and text not in capability_warnings:
                capability_warnings.append(text)
    health = {
        "platform_id": current_platform_id(),
        "profile_running": bool(profile_status.get("running")),
        "attach_status": str(profile_status.get("attach_status") or ""),
        "attach_message": str(profile_status.get("attach_message") or ""),
        "attach_ready": str(profile_status.get("attach_status") or "") in {"exact_window", "title_match"},
        "attach_candidate_count": len(
            profile_status.get("attach_candidates")
            if isinstance(profile_status.get("attach_candidates"), list)
            else profile_status.get("windows") or []
        ),
        "window_automation_available": bool((capabilities.get("window_automation") or {}).get("available")),
        "accessibility_available": bool((capabilities.get("accessibility") or {}).get("available")),
        "session_runtime_reachable": session_repo_binary().exists(),
        "panel_backend_status": "ready",
        "session_type": str(profile_status.get("session_type") or display_session.get("session_type") or ""),
        "display": str(profile_status.get("display") or display_session.get("display") or ""),
        "wayland_display": str(profile_status.get("wayland_display") or display_session.get("wayland_display") or ""),
        "display_backend": str(profile_status.get("display_backend") or "auto"),
        "attach_proof_mode": str(profile_status.get("attach_proof_mode") or ""),
        "capability_warnings": capability_warnings,
        "window_automation_warning": " | ".join(str(item) for item in window_automation.get("warnings") or [] if str(item or "").strip()),
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
        "session_snapshot": session_snapshot,
        "combined_state": combined_state,
        "artifact_index": artifact_index,
        "artifact_shortcuts": artifact_shortcuts,
        "artifact_provenance": artifact_provenance,
        "artifact_index_provenance": artifact_index_provenance,
        "artifact_center": _artifact_center_rows(artifact_shortcuts, artifact_provenance),
        "artifact_history": artifact_history,
        "workflow_buckets": workflow_buckets,
    }
