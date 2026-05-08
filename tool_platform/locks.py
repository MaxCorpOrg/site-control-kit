from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from .jobs import now_utc, profile_id_for
from .telegram_runtime import LEGACY_STATE_ROOT, preferred_read_path, profile_locks_path


DEFAULT_PROFILE_LOCKS_PATH = profile_locks_path()
LEGACY_PROFILE_LOCKS_PATH = LEGACY_STATE_ROOT / "locks" / "profiles.json"


def default_profile_locks() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "updated_at": "",
        "locks": {},
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


def load_profile_locks(locks_path: str | Path = DEFAULT_PROFILE_LOCKS_PATH) -> dict[str, Any]:
    resolved = Path(locks_path).expanduser().resolve()
    read_path = resolved
    if resolved == DEFAULT_PROFILE_LOCKS_PATH:
        read_path = preferred_read_path(resolved, LEGACY_PROFILE_LOCKS_PATH)
    payload = _load_json(read_path)
    locks = default_profile_locks()
    raw_locks = payload.get("locks")
    if isinstance(raw_locks, dict):
        locks["locks"] = {str(key): value for key, value in raw_locks.items() if isinstance(value, dict)}
    updated_at = str(payload.get("updated_at") or "").strip()
    if updated_at:
        locks["updated_at"] = updated_at
    return locks


def save_profile_locks(payload: dict[str, Any], locks_path: str | Path = DEFAULT_PROFILE_LOCKS_PATH) -> Path:
    resolved = Path(locks_path).expanduser().resolve()
    locks = default_profile_locks()
    raw_locks = payload.get("locks")
    if isinstance(raw_locks, dict):
        locks["locks"] = {str(key): value for key, value in raw_locks.items() if isinstance(value, dict)}
    locks["updated_at"] = now_utc()
    return _atomic_write_json(resolved, locks)


def get_profile_lock(
    *,
    profile_name: str,
    profile_dir: str | Path,
    locks_path: str | Path = DEFAULT_PROFILE_LOCKS_PATH,
) -> dict[str, Any] | None:
    locks = load_profile_locks(locks_path)
    lock_id = profile_id_for(profile_name, profile_dir)
    value = locks["locks"].get(lock_id)
    return dict(value) if isinstance(value, dict) else None


def acquire_profile_lock(
    *,
    profile_name: str,
    profile_dir: str | Path,
    owner_tool_id: str,
    job_id: str,
    conflict_reason: str = "",
    locks_path: str | Path = DEFAULT_PROFILE_LOCKS_PATH,
) -> dict[str, Any]:
    locks = load_profile_locks(locks_path)
    lock_id = profile_id_for(profile_name, profile_dir)
    existing = locks["locks"].get(lock_id)
    if isinstance(existing, dict) and (
        str(existing.get("owner_tool_id") or "") != str(owner_tool_id)
        or str(existing.get("job_id") or "") != str(job_id)
    ):
        return {
            "acquired": False,
            "lock": dict(existing),
            "conflict_reason": str(existing.get("conflict_reason") or conflict_reason or "profile_locked"),
        }
    lock = {
        "profile_id": lock_id,
        "profile_name": str(profile_name or "").strip() or "profile",
        "profile_dir": str(Path(profile_dir).expanduser().resolve()) if str(profile_dir or "").strip() else "",
        "owner_tool_id": str(owner_tool_id),
        "job_id": str(job_id),
        "conflict_reason": str(conflict_reason or "active_job"),
        "locked_at": now_utc(),
        "updated_at": now_utc(),
    }
    locks["locks"][lock_id] = lock
    save_profile_locks(locks, locks_path)
    return {
        "acquired": True,
        "lock": lock,
        "conflict_reason": "",
    }


def release_profile_lock(
    *,
    profile_name: str,
    profile_dir: str | Path,
    owner_tool_id: str | None = None,
    job_id: str | None = None,
    locks_path: str | Path = DEFAULT_PROFILE_LOCKS_PATH,
) -> bool:
    locks = load_profile_locks(locks_path)
    lock_id = profile_id_for(profile_name, profile_dir)
    existing = locks["locks"].get(lock_id)
    if not isinstance(existing, dict):
        return False
    if owner_tool_id is not None and str(existing.get("owner_tool_id") or "") != str(owner_tool_id):
        return False
    if job_id is not None and str(existing.get("job_id") or "") != str(job_id):
        return False
    locks["locks"].pop(lock_id, None)
    save_profile_locks(locks, locks_path)
    return True


def force_release_profile_lock(
    *,
    profile_name: str,
    profile_dir: str | Path,
    locks_path: str | Path = DEFAULT_PROFILE_LOCKS_PATH,
) -> bool:
    return release_profile_lock(
        profile_name=profile_name,
        profile_dir=profile_dir,
        owner_tool_id=None,
        job_id=None,
        locks_path=locks_path,
    )


def list_profile_locks(locks_path: str | Path = DEFAULT_PROFILE_LOCKS_PATH) -> list[dict[str, Any]]:
    locks = list(load_profile_locks(locks_path)["locks"].values())
    locks.sort(key=lambda item: str(item.get("updated_at") or item.get("locked_at") or ""), reverse=True)
    return locks
