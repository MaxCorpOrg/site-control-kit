from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_ROOT = REPO_ROOT / "runtime" / "telegram"

LEGACY_PROFILES_ROOT = Path.home()
LEGACY_INVITE_JOBS_ROOT = Path.home() / "telegram_invite_jobs"
LEGACY_STATE_ROOT = Path.home() / ".site-control-kit" / "telegram"
LEGACY_RUNTIME_CACHE_DIR = Path.home() / ".cache" / "site-control-kit" / "telegram-portable-runtime"
LEGACY_SESSION_REPO = Path("/home/max/telegram-portable-session-tool")
LEGACY_PANEL_LOG_PATH = Path("/tmp/telegram-control-center-panel.log")
LEGACY_PANEL_STATE_ROOT = Path("/tmp/telegram-control-center")


def repo_root() -> Path:
    return REPO_ROOT


def runtime_root() -> Path:
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
    return state_root() / "runtime_configs"


def logs_root() -> Path:
    return runtime_root() / "logs"


def panel_logs_root() -> Path:
    return logs_root() / "panel"


def panel_log_path() -> Path:
    return panel_logs_root() / "telegram-control-center-panel.log"


def cache_root() -> Path:
    return runtime_root() / "cache"


def telegram_desktop_cache_root() -> Path:
    return cache_root() / "telegram-desktop"


def session_repo_root() -> Path:
    return LEGACY_SESSION_REPO


def session_repo_example_config() -> Path:
    return session_repo_root() / "examples" / "session.example.json"


def session_repo_runs_root() -> Path:
    return session_repo_root() / "runs"


def session_repo_state_file() -> Path:
    return session_repo_root() / ".state" / "session_state.json"


def session_repo_binary() -> Path:
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
