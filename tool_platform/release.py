from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .catalog import DEFAULT_REGISTRY_PATH
from .platform_adapters import platform_doctor_report
from .telegram_runtime import (
    cache_root,
    config_root,
    logs_root,
    production_mode_enabled,
    profiles_root,
    repo_root,
    runtime_config_root,
    runtime_root,
    session_repo_binary,
    state_root,
)


def _path_status(path: Path, *, create: bool = False) -> dict[str, Any]:
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return {
        "path": str(path),
        "exists": path.exists(),
        "is_dir": path.is_dir(),
        "writable": path.exists() and path.is_dir(),
    }


def release_self_test(*, create_dirs: bool = True) -> dict[str, Any]:
    paths = {
        "repo_root": {"path": str(repo_root()), "exists": repo_root().exists(), "is_dir": repo_root().is_dir()},
        "runtime_root": _path_status(runtime_root(), create=create_dirs),
        "config_root": _path_status(config_root(), create=create_dirs),
        "runtime_config_root": _path_status(runtime_config_root(), create=create_dirs),
        "state_root": _path_status(state_root(), create=create_dirs),
        "profiles_root": _path_status(profiles_root(), create=create_dirs),
        "logs_root": _path_status(logs_root(), create=create_dirs),
        "cache_root": _path_status(cache_root(), create=create_dirs),
        "registry": {
            "path": str(DEFAULT_REGISTRY_PATH),
            "exists": DEFAULT_REGISTRY_PATH.is_file(),
            "is_dir": False,
        },
        "session_runner": {
            "path": str(session_repo_binary()),
            "exists": session_repo_binary().exists(),
            "is_dir": False,
        },
    }
    doctor = platform_doctor_report()
    ok = bool(paths["registry"]["exists"] and paths["session_runner"]["exists"])
    return {
        "status": "ok" if ok else "error",
        "ok": ok,
        "production_mode": production_mode_enabled(),
        "frozen": bool(getattr(sys, "frozen", False)),
        "executable": sys.executable,
        "platform": sys.platform,
        "paths": paths,
        "doctor": doctor,
    }


def print_release_self_test(*, create_dirs: bool = True) -> int:
    payload = release_self_test(create_dirs=create_dirs)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1
