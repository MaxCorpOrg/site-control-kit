from __future__ import annotations

import os
import sys
from pathlib import Path


APP_SLUG = "site-control-kit"
TELEGRAM_RUNTIME_NAME = "telegram"
PRODUCTION_MODE_ENV = "SITE_CONTROL_KIT_RUNTIME_MODE"
APP_ROOT_ENV = "SITE_CONTROL_KIT_APP_ROOT"
CONFIG_DIR_ENV = "SITE_CONTROL_KIT_CONFIG_DIR"
DATA_DIR_ENV = "SITE_CONTROL_KIT_DATA_DIR"
LOG_DIR_ENV = "SITE_CONTROL_KIT_LOG_DIR"
CACHE_DIR_ENV = "SITE_CONTROL_KIT_CACHE_DIR"
SESSION_REPO_ENV = "SITE_CONTROL_KIT_SESSION_REPO"


def _env_path(name: str) -> Path | None:
    raw = str(os.environ.get(name) or "").strip()
    return Path(raw).expanduser().resolve() if raw else None


def _default_repo_root() -> Path:
    override = _env_path(APP_ROOT_ENV)
    if override is not None:
        return override
    frozen_root = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False) and frozen_root:
        return Path(str(frozen_root)).expanduser().resolve()
    return Path(__file__).resolve().parent.parent


REPO_ROOT = _default_repo_root()
RUNTIME_ROOT = REPO_ROOT / "runtime" / TELEGRAM_RUNTIME_NAME

LEGACY_PROFILES_ROOT = Path.home()
LEGACY_INVITE_JOBS_ROOT = Path.home() / "telegram_invite_jobs"
LEGACY_STATE_ROOT = Path.home() / ".site-control-kit" / "telegram"
LEGACY_RUNTIME_CACHE_DIR = Path.home() / ".cache" / "site-control-kit" / "telegram-portable-runtime"
LEGACY_SESSION_REPO = Path.home() / "telegram-portable-session-tool"
LEGACY_PANEL_LOG_PATH = Path("/tmp/telegram-control-center-panel.log")
LEGACY_PANEL_STATE_ROOT = Path("/tmp/telegram-control-center")


def repo_root() -> Path:
    return REPO_ROOT


def production_mode_enabled() -> bool:
    mode = str(os.environ.get(PRODUCTION_MODE_ENV) or "").strip().lower()
    return mode in {"1", "true", "yes", "on", "production", "prod", "release"} or bool(
        getattr(sys, "frozen", False)
    )


def _xdg_root(env_name: str, fallback: Path) -> Path:
    raw = str(os.environ.get(env_name) or "").strip()
    return Path(raw).expanduser().resolve() if raw else fallback.expanduser().resolve()


def _windows_roaming_root() -> Path:
    return Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming")).expanduser().resolve()


def _windows_local_root() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")).expanduser().resolve()


def config_root() -> Path:
    override = _env_path(CONFIG_DIR_ENV)
    if override is not None:
        return override
    if not production_mode_enabled():
        return runtime_root() / "config"
    if sys.platform.startswith("win"):
        return _windows_roaming_root() / "SiteControlKit" / "config"
    return _xdg_root("XDG_CONFIG_HOME", Path.home() / ".config") / APP_SLUG


def data_root() -> Path:
    override = _env_path(DATA_DIR_ENV)
    if override is not None:
        return override
    if not production_mode_enabled():
        return REPO_ROOT / "runtime"
    if sys.platform.startswith("win"):
        return _windows_local_root() / "SiteControlKit" / "data"
    return _xdg_root("XDG_DATA_HOME", Path.home() / ".local" / "share") / APP_SLUG


def log_root() -> Path:
    override = _env_path(LOG_DIR_ENV)
    if override is not None:
        return override
    if not production_mode_enabled():
        return runtime_root() / "logs"
    if sys.platform.startswith("win"):
        return _windows_local_root() / "SiteControlKit" / "logs"
    return _xdg_root("XDG_STATE_HOME", Path.home() / ".local" / "state") / APP_SLUG / "logs"


def cache_base_root() -> Path:
    override = _env_path(CACHE_DIR_ENV)
    if override is not None:
        return override
    if not production_mode_enabled():
        return runtime_root() / "cache"
    if sys.platform.startswith("win"):
        return _windows_local_root() / "SiteControlKit" / "cache"
    return _xdg_root("XDG_CACHE_HOME", Path.home() / ".cache") / APP_SLUG


def runtime_root() -> Path:
    if production_mode_enabled() or _env_path(DATA_DIR_ENV) is not None:
        return data_root() / TELEGRAM_RUNTIME_NAME
    return RUNTIME_ROOT


def profiles_root() -> Path:
    return runtime_root() / "profiles"


def invite_jobs_root() -> Path:
    return runtime_root() / "invite_jobs"


def session_root() -> Path:
    return runtime_root() / "session"


def session_configs_root() -> Path:
    return session_root() / "configs"


def session_state_root() -> Path:
    return session_root() / "state"


def session_state_file() -> Path:
    return session_state_root() / "session_state.json"


def session_runs_root() -> Path:
    return session_root() / "runs"


def state_root() -> Path:
    return runtime_root() / "state"


def state_jobs_root() -> Path:
    return state_root() / "jobs"


def job_index_path() -> Path:
    return state_jobs_root() / "index.json"


def state_locks_root() -> Path:
    return state_root() / "locks"


def profile_locks_path() -> Path:
    return state_locks_root() / "profiles.json"


def state_agent_root() -> Path:
    return state_root() / "agent"


def agent_state_path() -> Path:
    return state_agent_root() / "agent_state.json"


def state_panel_root() -> Path:
    return state_root() / "panel"


def combined_flow_state_root() -> Path:
    return state_panel_root() / "combined_flows"


def state_profiles_root() -> Path:
    return state_root() / "profiles"


def hidden_profiles_state_path() -> Path:
    return state_profiles_root() / "hidden_profiles.json"


def runtime_config_root() -> Path:
    if production_mode_enabled() or _env_path(CONFIG_DIR_ENV) is not None:
        return config_root() / TELEGRAM_RUNTIME_NAME / "runtime_configs"
    return state_root() / "runtime_configs"


def logs_root() -> Path:
    if production_mode_enabled() or _env_path(LOG_DIR_ENV) is not None:
        return log_root() / TELEGRAM_RUNTIME_NAME
    return runtime_root() / "logs"


def panel_logs_root() -> Path:
    return logs_root() / "panel"


def panel_log_path() -> Path:
    return panel_logs_root() / "telegram-control-center-panel.log"


def cache_root() -> Path:
    if production_mode_enabled() or _env_path(CACHE_DIR_ENV) is not None:
        return cache_base_root() / TELEGRAM_RUNTIME_NAME
    return runtime_root() / "cache"


def telegram_desktop_cache_root() -> Path:
    return cache_root() / "telegram-desktop"


def session_repo_root() -> Path:
    override = _env_path(SESSION_REPO_ENV)
    if override is not None:
        return override
    embedded = repo_root() / "telegram_portable_session_tool"
    if embedded.exists():
        return repo_root()
    return LEGACY_SESSION_REPO


def session_repo_example_config() -> Path:
    embedded = repo_root() / "tools" / "telegram" / "session_runner" / "examples" / "session.example.json"
    if embedded.is_file():
        return embedded
    return session_repo_root() / "examples" / "session.example.json"


def session_repo_runs_root() -> Path:
    return session_repo_root() / "runs"


def session_repo_state_file() -> Path:
    return session_repo_root() / ".state" / "session_state.json"


def session_repo_binary() -> Path:
    embedded = repo_root() / "telegram_portable_session_tool" / "cli.py"
    if embedded.is_file():
        return embedded
    return session_repo_root() / "bin" / "telegram-portable-session-tool"


def preferred_read_path(primary: str | Path, *fallbacks: str | Path) -> Path:
    candidate_paths = [Path(primary).expanduser().resolve(), *[Path(item).expanduser().resolve() for item in fallbacks]]
    for candidate in candidate_paths:
        if candidate.exists():
            return candidate
    return candidate_paths[0]


def display_path(path: str | Path) -> str:
    resolved = Path(path).expanduser().resolve()
    try:
        return str(resolved.relative_to(repo_root()))
    except ValueError:
        return str(resolved)


def is_project_local_profile_dir(path: str | Path) -> bool:
    resolved = Path(path).expanduser().resolve()
    try:
        resolved.relative_to(profiles_root())
    except ValueError:
        return False
    return True
