from __future__ import annotations

import json
import shlex
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any

from .locks import get_profile_lock
from .telegram_runtime import (
    LEGACY_PROFILES_ROOT,
    LEGACY_STATE_ROOT,
    hidden_profiles_state_path,
    is_project_local_profile_dir,
    preferred_read_path,
    profiles_root,
    repo_root,
    state_root,
)


DEFAULT_OUTPUT_ROOT = profiles_root()
DEFAULT_TELEGRAM_PROFILE_STATE_ROOT = state_root()
DEFAULT_HIDDEN_PROFILES_STATE_PATH = hidden_profiles_state_path()
LEGACY_OUTPUT_ROOT = LEGACY_PROFILES_ROOT
LEGACY_HIDDEN_PROFILES_STATE_PATH = LEGACY_STATE_ROOT / "profiles" / "hidden_profiles.json"
PORTABLE_SCRIPT_PATH = repo_root() / "scripts" / "telegram_portable.py"
LIVE_ATTACH_READY_STATUSES = {"exact_window", "title_match"}
PROFILE_PREFIX = "TelegramPortable-"
LEGACY_PROFILE_PREFIX_RE = re.compile(r"^TelegramPortable[-_]?", re.I)


def _run_json_command(argv: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        argv,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        command = shlex.join(argv)
        raise RuntimeError(f"command failed ({completed.returncode}): {command}\n{detail}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        command = shlex.join(argv)
        raise RuntimeError(f"command returned invalid JSON: {command}") from exc
    if not isinstance(payload, dict):
        command = shlex.join(argv)
        raise RuntimeError(f"command returned unexpected payload: {command}")
    return payload


def _portable_command(*parts: str) -> list[str]:
    return ["python3", str(PORTABLE_SCRIPT_PATH), *parts]


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _resolved_profile_dir(profile_dir: str | Path) -> Path:
    return Path(profile_dir).expanduser().resolve()


def _resolved_output_root(output_root: str | Path) -> Path:
    return Path(output_root).expanduser().resolve()


def _sanitize_profile_name(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("profile name is required")
    raw = LEGACY_PROFILE_PREFIX_RE.sub("", raw)
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip("-._")
    if not normalized:
        raise ValueError(f"unable to derive safe profile name from: {value}")
    return normalized[:80]


def _project_profile_dir(output_root: str | Path, profile_name: str) -> Path:
    return _resolved_output_root(output_root) / f"{PROFILE_PREFIX}{_sanitize_profile_name(profile_name)}"


def _metadata_path(profile_dir: str | Path) -> Path:
    return _resolved_profile_dir(profile_dir) / "portable-profile.json"


def _load_profile_metadata(profile_dir: str | Path) -> dict[str, Any]:
    metadata_path = _metadata_path(profile_dir)
    if not metadata_path.is_file():
        return {}
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_profile_metadata(profile_dir: str | Path, payload: dict[str, Any]) -> Path:
    metadata_path = _metadata_path(profile_dir)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return metadata_path


def _list_profiles_from_output_root(output_root: str | Path) -> list[dict[str, Any]]:
    payload = _run_json_command(
        _portable_command("list", "--output-root", str(_resolved_output_root(output_root)))
    )
    raw_profiles = payload.get("profiles")
    if not isinstance(raw_profiles, list):
        raise RuntimeError("portable helper returned invalid profiles list")
    return [item for item in raw_profiles if isinstance(item, dict)]


def _hidden_profiles_state(state_path: str | Path = DEFAULT_HIDDEN_PROFILES_STATE_PATH) -> dict[str, Any]:
    resolved = Path(state_path).expanduser().resolve()
    read_path = resolved
    if resolved == DEFAULT_HIDDEN_PROFILES_STATE_PATH:
        read_path = preferred_read_path(resolved, LEGACY_HIDDEN_PROFILES_STATE_PATH)
    if not read_path.is_file():
        return {"schema_version": 1, "hidden_profiles": [], "updated_at": ""}
    try:
        payload = json.loads(read_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema_version": 1, "hidden_profiles": [], "updated_at": ""}
    if not isinstance(payload, dict):
        return {"schema_version": 1, "hidden_profiles": [], "updated_at": ""}
    hidden_profiles = payload.get("hidden_profiles")
    return {
        "schema_version": 1,
        "hidden_profiles": [item for item in hidden_profiles or [] if isinstance(item, dict)],
        "updated_at": str(payload.get("updated_at") or ""),
    }


def _save_hidden_profiles_state(
    payload: dict[str, Any],
    *,
    state_path: str | Path = DEFAULT_HIDDEN_PROFILES_STATE_PATH,
) -> Path:
    resolved = Path(state_path).expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "schema_version": 1,
        "hidden_profiles": [item for item in payload.get("hidden_profiles") or [] if isinstance(item, dict)],
        "updated_at": _now_utc(),
    }
    resolved.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return resolved


def _hidden_profile_key(profile_dir: str | Path) -> str:
    return str(_resolved_profile_dir(profile_dir))


def load_hidden_profile_records(
    state_path: str | Path = DEFAULT_HIDDEN_PROFILES_STATE_PATH,
) -> list[dict[str, Any]]:
    return list(_hidden_profiles_state(state_path).get("hidden_profiles") or [])


def list_hidden_profile_records(
    state_path: str | Path = DEFAULT_HIDDEN_PROFILES_STATE_PATH,
) -> list[dict[str, Any]]:
    records = load_hidden_profile_records(state_path)
    normalized: list[dict[str, Any]] = []
    for item in records:
        profile_dir = _hidden_profile_key(item.get("profile_dir") or "")
        if not profile_dir:
            continue
        profile_path = Path(profile_dir)
        normalized.append(
            {
                "profile_dir": profile_dir,
                "profile_name": str(item.get("profile_name") or "").strip() or profile_path.name,
                "account_username": str(item.get("account_username") or "").strip(),
                "account_label": str(item.get("account_label") or "").strip(),
                "hidden_at": str(item.get("hidden_at") or ""),
                "exists": profile_path.exists(),
            }
        )
    return sorted(normalized, key=lambda item: (0 if item.get("exists") else 1, str(item.get("profile_name") or "").lower()))


def hide_portable_profile(
    *,
    profile_dir: str | Path,
    profile_name: str = "",
    account_username: str = "",
    account_label: str = "",
    state_path: str | Path = DEFAULT_HIDDEN_PROFILES_STATE_PATH,
) -> dict[str, Any]:
    normalized_dir = _hidden_profile_key(profile_dir)
    profile_path = Path(normalized_dir)
    state = _hidden_profiles_state(state_path)
    records = [item for item in state.get("hidden_profiles") or [] if isinstance(item, dict)]
    preserved = [item for item in records if _hidden_profile_key(item.get("profile_dir") or "") != normalized_dir]
    preserved.append(
        {
            "profile_dir": normalized_dir,
            "profile_name": str(profile_name or "").strip() or profile_path.name,
            "account_username": str(account_username or "").strip(),
            "account_label": str(account_label or "").strip(),
            "hidden_at": _now_utc(),
        }
    )
    _save_hidden_profiles_state({"hidden_profiles": preserved}, state_path=state_path)
    return {
        "status": "hidden",
        "profile_dir": normalized_dir,
        "profile_name": str(profile_name or "").strip() or profile_path.name,
    }


def unhide_portable_profile(
    *,
    profile_dir: str | Path,
    state_path: str | Path = DEFAULT_HIDDEN_PROFILES_STATE_PATH,
) -> dict[str, Any]:
    normalized_dir = _hidden_profile_key(profile_dir)
    state = _hidden_profiles_state(state_path)
    records = [item for item in state.get("hidden_profiles") or [] if isinstance(item, dict)]
    updated = [item for item in records if _hidden_profile_key(item.get("profile_dir") or "") != normalized_dir]
    _save_hidden_profiles_state({"hidden_profiles": updated}, state_path=state_path)
    return {"status": "visible", "profile_dir": normalized_dir}


def remove_portable_profile(
    *,
    profile_dir: str | Path,
    hidden_state_path: str | Path = DEFAULT_HIDDEN_PROFILES_STATE_PATH,
) -> dict[str, Any]:
    resolved_dir = _resolved_profile_dir(profile_dir)
    if not resolved_dir.exists():
        raise FileNotFoundError(f"Telegram profile directory not found: {resolved_dir}")
    status = get_profile_status(resolved_dir)
    if bool(status.get("running")):
        raise RuntimeError(
            "Нельзя удалить профиль, пока его процесс запущен. Сначала останови Telegram этого аккаунта."
        )
    profile_name = str(status.get("profile_name") or resolved_dir.name)
    lock = get_profile_lock(profile_name=profile_name, profile_dir=resolved_dir)
    if isinstance(lock, dict):
        raise RuntimeError(
            "Нельзя удалить профиль, пока он удерживается live workflow.\n\n"
            f"Owner: {str(lock.get('owner_tool_id') or '-')}\n"
            f"Job: {str(lock.get('job_id') or '-')}"
        )
    account = status.get("account") if isinstance(status.get("account"), dict) else {}
    shutil.rmtree(resolved_dir)
    unhide_portable_profile(profile_dir=resolved_dir, state_path=hidden_state_path)
    return {
        "status": "deleted",
        "profile_dir": str(resolved_dir),
        "profile_name": profile_name,
        "account": account,
    }


def profile_attach_report(profile: dict[str, Any]) -> dict[str, Any]:
    attach_status = str(profile.get("attach_status") or "").strip() or "unknown"
    attach_message = str(profile.get("attach_message") or "").strip()
    candidates = profile.get("attach_candidates") if isinstance(profile.get("attach_candidates"), list) else []
    return {
        "attach_status": attach_status,
        "attach_message": attach_message,
        "attach_candidates": [item for item in candidates if isinstance(item, dict)],
        "ready_for_live_actions": attach_status in LIVE_ATTACH_READY_STATUSES,
    }


def profile_live_attach_error(profile: dict[str, Any]) -> str:
    report = profile_attach_report(profile)
    if report["ready_for_live_actions"]:
        return ""
    attach_status = str(report.get("attach_status") or "")
    attach_message = str(report.get("attach_message") or "")
    if attach_status == "no_process":
        return ""
    if attach_message:
        return attach_message
    return "У выбранного профиля нет безопасного attach к собственному окну Telegram."


def format_profile_label(profile: dict[str, Any]) -> str:
    account = profile.get("account") if isinstance(profile.get("account"), dict) else {}
    primary = (
        str(account.get("label") or "").strip()
        or str(account.get("username") or "").strip()
        or str(profile.get("profile_name") or "").strip()
        or str(profile.get("profile_dir") or "").strip()
    )
    profile_name = str(profile.get("profile_name") or "").strip()
    if profile_name and profile_name != primary:
        primary = f"{primary} ({profile_name})"
    status = "запущен" if profile.get("running") else "остановлен"
    return f"{primary} [{status}]"


def list_portable_profiles(
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
    *,
    include_hidden: bool = False,
    include_legacy_when_empty: bool = False,
    hidden_state_path: str | Path = DEFAULT_HIDDEN_PROFILES_STATE_PATH,
) -> list[dict[str, Any]]:
    profiles = _list_profiles_from_output_root(output_root)
    if not profiles and include_legacy_when_empty:
        profiles = _list_profiles_from_output_root(LEGACY_OUTPUT_ROOT)
    if not include_hidden:
        hidden_dirs = {
            _hidden_profile_key(item.get("profile_dir") or "")
            for item in load_hidden_profile_records(hidden_state_path)
            if _hidden_profile_key(item.get("profile_dir") or "")
        }
        profiles = [
            item
            for item in profiles
            if _hidden_profile_key(item.get("profile_dir") or "") not in hidden_dirs
        ]
    return sorted(
        profiles,
        key=lambda item: (
            0 if item.get("running") else 1,
            format_profile_label(item).lower(),
        ),
    )


def list_external_portable_profiles(
    *,
    primary_output_root: str | Path = DEFAULT_OUTPUT_ROOT,
    hidden_state_path: str | Path = DEFAULT_HIDDEN_PROFILES_STATE_PATH,
) -> list[dict[str, Any]]:
    if _resolved_output_root(primary_output_root) == _resolved_output_root(LEGACY_OUTPUT_ROOT):
        return []
    hidden_dirs = {
        _hidden_profile_key(item.get("profile_dir") or "")
        for item in load_hidden_profile_records(hidden_state_path)
        if _hidden_profile_key(item.get("profile_dir") or "")
    }
    local_profiles = _list_profiles_from_output_root(primary_output_root)
    project_profile_dirs = {
        _hidden_profile_key(item.get("profile_dir") or "")
        for item in local_profiles
        if _hidden_profile_key(item.get("profile_dir") or "")
    }
    migrated_sources = {
        _hidden_profile_key(_load_profile_metadata(item.get("profile_dir") or "").get("legacy_source_dir") or "")
        for item in local_profiles
        if _hidden_profile_key(_load_profile_metadata(item.get("profile_dir") or "").get("legacy_source_dir") or "")
    }
    external_profiles = []
    for item in _list_profiles_from_output_root(LEGACY_OUTPUT_ROOT):
        normalized_dir = _hidden_profile_key(item.get("profile_dir") or "")
        if not normalized_dir or normalized_dir in hidden_dirs or normalized_dir in project_profile_dirs or normalized_dir in migrated_sources:
            continue
        if is_project_local_profile_dir(normalized_dir):
            continue
        external_profiles.append(item)
    return sorted(
        external_profiles,
        key=lambda item: (
            0 if item.get("running") else 1,
            format_profile_label(item).lower(),
        ),
    )


def get_profile_status(profile_dir: str | Path) -> dict[str, Any]:
    return _run_json_command(
        _portable_command("status", "--profile-dir", str(Path(profile_dir).expanduser().resolve()))
    )


def launch_profile(profile_dir: str | Path) -> dict[str, Any]:
    return _run_json_command(
        _portable_command("launch", "--profile-dir", str(Path(profile_dir).expanduser().resolve()))
    )


def import_tdata_profile(
    *,
    zip_path: str | Path,
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
    profile_name: str = "",
    account_username: str = "",
    account_label: str = "",
    launch: bool = True,
) -> dict[str, Any]:
    argv = _portable_command(
        "import-zip",
        "--zip",
        str(Path(zip_path).expanduser().resolve()),
        "--output-root",
        str(Path(output_root).expanduser().resolve()),
    )
    if profile_name.strip():
        argv.extend(["--profile-name", profile_name.strip()])
    if account_username.strip():
        argv.extend(["--account-username", account_username.strip()])
    if account_label.strip():
        argv.extend(["--account-label", account_label.strip()])
    if launch:
        argv.append("--launch")
    return _run_json_command(argv)


def adopt_existing_profile(
    *,
    profile_dir: str | Path,
    profile_name: str = "",
    account_username: str = "",
    account_label: str = "",
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
) -> dict[str, Any]:
    source_dir = _resolved_profile_dir(profile_dir)
    if not source_dir.exists() or is_project_local_profile_dir(source_dir):
        target_dir = source_dir
    else:
        source_status = get_profile_status(source_dir)
        if bool(source_status.get("running")):
            raise RuntimeError(
                "Нельзя забрать внешний профиль в проект, пока он запущен. "
                "Сначала останови Telegram этого аккаунта, затем повтори миграцию."
            )
        source_metadata = _load_profile_metadata(source_dir)
        resolved_profile_name = (
            profile_name.strip()
            or str(source_status.get("profile_name") or "").strip()
            or str(source_metadata.get("profile_name") or "").strip()
            or source_dir.name
        )
        target_dir = _project_profile_dir(output_root, resolved_profile_name)
        if target_dir.exists() and target_dir != source_dir:
            raise RuntimeError(
                f"В проекте уже существует профиль `{target_dir.name}`.\n"
                f"Путь: {target_dir}"
            )
        shutil.copytree(source_dir, target_dir)
        migrated_metadata = _load_profile_metadata(target_dir)
        migrated_metadata["legacy_source_dir"] = str(source_dir)
        migrated_metadata["migrated_at"] = _now_utc()
        _save_profile_metadata(target_dir, migrated_metadata)

    argv = _portable_command("adopt", "--profile-dir", str(target_dir))
    if profile_name.strip():
        argv.extend(["--profile-name", profile_name.strip()])
    if account_username.strip():
        argv.extend(["--account-username", account_username.strip()])
    if account_label.strip():
        argv.extend(["--account-label", account_label.strip()])
    result = _run_json_command(argv)
    if target_dir != source_dir:
        metadata = _load_profile_metadata(target_dir)
        metadata["legacy_source_dir"] = str(source_dir)
        metadata["migrated_at"] = str(metadata.get("migrated_at") or _now_utc())
        _save_profile_metadata(target_dir, metadata)
        result["migration"] = {
            "mode": "copy_then_switch",
            "legacy_source_dir": str(source_dir),
            "project_profile_dir": str(target_dir),
        }
    return result
