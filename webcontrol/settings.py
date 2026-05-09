from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - exercised only in broken install environments
    yaml = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_RELATIVE = Path("config/default.yaml")
DEFAULT_ENV_FILENAME = ".env"
LOCAL_STATE_DIRNAME = ".site-control-kit"
LOCAL_CONFIG_FILENAME = "local.yaml"
LEGACY_HOME_DIRNAME = ".site-control-kit"
LEGACY_INSECURE_TOKEN = "local-bridge-quickstart-2026"


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    project_root: Path
    config_default_path: Path
    local_config_path: Path
    env_file_path: Path
    local_state_dir: Path
    legacy_home_root: Path
    runtime_root: Path
    logs_root: Path
    reports_root: Path
    hub_state_file: Path
    hub_token_file: Path
    hub_log_file: Path
    runtime_events_log_file: Path
    runtime_errors_log_file: Path
    browser_profile_dir: Path
    firefox_profile_dir: Path
    telegram_workspace_root: Path
    telegram_users_registry_file: Path
    telegram_api_accounts_file: Path
    telegram_managed_helper_root: Path
    telegram_default_output_dir: Path
    hub_host: str
    hub_port: int
    local_config_generated: bool = False
    legacy_runtime_detected: bool = False

    @property
    def server_url(self) -> str:
        return f"http://{self.hub_host}:{self.hub_port}"

    def env_map(self, *, token: str | None = None) -> dict[str, str]:
        rows = {
            "SITECTL_PROJECT_ROOT": str(self.project_root),
            "SITECTL_RUNTIME_ROOT": str(self.runtime_root),
            "SITECTL_HOST": self.hub_host,
            "SITECTL_PORT": str(self.hub_port),
            "SITECTL_SERVER_URL": self.server_url,
            "SITECTL_STATE_FILE": str(self.hub_state_file),
            "SITECTL_LOG_DIR": str(self.logs_root),
            "SITECTL_REPORTS_ROOT": str(self.reports_root),
            "SITECTL_RUNTIME_EVENTS_LOG": str(self.runtime_events_log_file),
            "SITECTL_RUNTIME_ERRORS_LOG": str(self.runtime_errors_log_file),
            "SITECTL_BROWSER_PROFILE": str(self.browser_profile_dir),
            "SITECTL_FIREFOX_PROFILE": str(self.firefox_profile_dir),
            "TELEGRAM_WORKSPACE_ROOT": str(self.telegram_workspace_root),
            "TELEGRAM_USERS_REGISTRY_FILE": str(self.telegram_users_registry_file),
            "TELEGRAM_API_ACCOUNTS_FILE": str(self.telegram_api_accounts_file),
            "TELEGRAM_MANAGED_HELPER_ROOT": str(self.telegram_managed_helper_root),
            "TELEGRAM_DEFAULT_OUTPUT_DIR": str(self.telegram_default_output_dir),
        }
        if token:
            rows["SITECTL_TOKEN"] = token
        return rows


def venv_python_path(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def load_runtime_settings(*, project_root: Path | None = None, mutate: bool = False) -> RuntimeSettings:
    root = (project_root or PROJECT_ROOT).expanduser().resolve()
    env_file_path = root / DEFAULT_ENV_FILENAME
    local_state_dir = root / LOCAL_STATE_DIRNAME
    local_config_path = local_state_dir / LOCAL_CONFIG_FILENAME
    config_default_path = root / DEFAULT_CONFIG_RELATIVE
    legacy_home_root = Path.home() / LEGACY_HOME_DIRNAME

    _apply_env_defaults(env_file_path)

    if mutate:
        local_state_dir.mkdir(parents=True, exist_ok=True)

    default_config = _load_yaml_mapping(config_default_path, required=True)
    explicit_runtime_override = _runtime_override_present()
    local_config_generated = False
    legacy_runtime_detected = False

    if mutate and not local_config_path.exists() and not explicit_runtime_override and _legacy_runtime_present(legacy_home_root):
        _write_legacy_local_config(local_config_path, legacy_home_root)
        local_config_generated = True

    local_config = _load_yaml_mapping(local_config_path, required=False)
    legacy_runtime_detected = _legacy_runtime_present(legacy_home_root)

    runtime_root = _resolve_root_value(
        _select_value("SITECTL_RUNTIME_ROOT", local_config, default_config, "runtime.root", "var/site-control-kit"),
        base=root,
    )
    logs_root = _resolve_child_path(
        env_name="SITECTL_LOG_DIR",
        local_config=local_config,
        default_config=default_config,
        dotted_key="logging.root_dir",
        fallback="logs",
        base=runtime_root,
    )
    reports_root = _resolve_child_path(
        env_name="SITECTL_REPORTS_ROOT",
        local_config=local_config,
        default_config=default_config,
        dotted_key="reports.root_dir",
        fallback="reports",
        base=runtime_root,
    )
    hub_state_file = _resolve_child_path(
        env_name="SITECTL_STATE_FILE",
        local_config=local_config,
        default_config=default_config,
        dotted_key="hub.state_file",
        fallback="state/state.json",
        base=runtime_root,
    )
    hub_token_file = _resolve_root_value(
        _select_value(
            "SITECTL_TOKEN_FILE",
            local_config,
            default_config,
            "hub.token_file",
            f"{LOCAL_STATE_DIRNAME}/generated_token.txt",
        ),
        base=root,
    )
    hub_log_file = _resolve_child_path(
        env_name="SITECTL_HUB_LOG_FILE",
        local_config=local_config,
        default_config=default_config,
        dotted_key="hub.log_file",
        fallback="logs/hub.log",
        base=runtime_root,
    )
    runtime_events_log_file = _resolve_child_path(
        env_name="SITECTL_RUNTIME_EVENTS_LOG",
        local_config=local_config,
        default_config=default_config,
        dotted_key="logging.runtime_events_file",
        fallback="logs/runtime_events.jsonl",
        base=runtime_root,
    )
    runtime_errors_log_file = _resolve_child_path(
        env_name="SITECTL_RUNTIME_ERRORS_LOG",
        local_config=local_config,
        default_config=default_config,
        dotted_key="logging.runtime_errors_file",
        fallback="logs/runtime_errors.jsonl",
        base=runtime_root,
    )
    browser_profile_dir = _resolve_child_path(
        env_name="SITECTL_BROWSER_PROFILE",
        local_config=local_config,
        default_config=default_config,
        dotted_key="browser.profile_dir",
        fallback="browser-profile",
        base=runtime_root,
    )
    firefox_profile_dir = _resolve_child_path(
        env_name="SITECTL_FIREFOX_PROFILE",
        local_config=local_config,
        default_config=default_config,
        dotted_key="browser.firefox_profile_dir",
        fallback="firefox-profile",
        base=runtime_root,
    )
    telegram_workspace_root = _resolve_child_path(
        env_name="TELEGRAM_WORKSPACE_ROOT",
        local_config=local_config,
        default_config=default_config,
        dotted_key="telegram.workspace_root",
        fallback="telegram_workspace",
        base=runtime_root,
    )
    telegram_users_registry_file = _resolve_child_path(
        env_name="TELEGRAM_USERS_REGISTRY_FILE",
        local_config=local_config,
        default_config=default_config,
        dotted_key="telegram.users_registry_file",
        fallback="registry/users.json",
        base=telegram_workspace_root,
    )
    telegram_api_accounts_file = _resolve_child_path(
        env_name="TELEGRAM_API_ACCOUNTS_FILE",
        local_config=local_config,
        default_config=default_config,
        dotted_key="telegram.api_accounts_file",
        fallback="registry/api_accounts.json",
        base=telegram_workspace_root,
    )
    telegram_managed_helper_root = _resolve_child_path(
        env_name="TELEGRAM_MANAGED_HELPER_ROOT",
        local_config=local_config,
        default_config=default_config,
        dotted_key="telegram.managed_helper_root",
        fallback="managed_helper",
        base=telegram_workspace_root,
    )
    telegram_default_output_dir = _resolve_child_path(
        env_name="TELEGRAM_DEFAULT_OUTPUT_DIR",
        local_config=local_config,
        default_config=default_config,
        dotted_key="telegram.default_output_dir",
        fallback="reports/telegram_exports",
        base=runtime_root,
    )

    host_raw = _select_value("SITECTL_HOST", local_config, default_config, "hub.host", "127.0.0.1")
    port_raw = _select_value("SITECTL_PORT", local_config, default_config, "hub.port", 8765)
    hub_host = str(host_raw or "127.0.0.1").strip() or "127.0.0.1"
    try:
        hub_port = max(int(str(port_raw).strip() or "8765"), 1)
    except ValueError:
        hub_port = 8765

    settings = RuntimeSettings(
        project_root=root,
        config_default_path=config_default_path,
        local_config_path=local_config_path,
        env_file_path=env_file_path,
        local_state_dir=local_state_dir,
        legacy_home_root=legacy_home_root,
        runtime_root=runtime_root,
        logs_root=logs_root,
        reports_root=reports_root,
        hub_state_file=hub_state_file,
        hub_token_file=hub_token_file,
        hub_log_file=hub_log_file,
        runtime_events_log_file=runtime_events_log_file,
        runtime_errors_log_file=runtime_errors_log_file,
        browser_profile_dir=browser_profile_dir,
        firefox_profile_dir=firefox_profile_dir,
        telegram_workspace_root=telegram_workspace_root,
        telegram_users_registry_file=telegram_users_registry_file,
        telegram_api_accounts_file=telegram_api_accounts_file,
        telegram_managed_helper_root=telegram_managed_helper_root,
        telegram_default_output_dir=telegram_default_output_dir,
        hub_host=hub_host,
        hub_port=hub_port,
        local_config_generated=local_config_generated,
        legacy_runtime_detected=legacy_runtime_detected,
    )
    if mutate:
        ensure_runtime_layout(settings)
    return settings


def ensure_runtime_layout(settings: RuntimeSettings) -> None:
    directories = (
        settings.local_state_dir,
        settings.runtime_root,
        settings.logs_root,
        settings.reports_root,
        settings.hub_state_file.parent,
        settings.hub_token_file.parent,
        settings.runtime_events_log_file.parent,
        settings.runtime_errors_log_file.parent,
        settings.browser_profile_dir,
        settings.firefox_profile_dir,
        settings.telegram_workspace_root,
        settings.telegram_users_registry_file.parent,
        settings.telegram_api_accounts_file.parent,
        settings.telegram_managed_helper_root,
        settings.telegram_default_output_dir,
    )
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)


def resolve_hub_token(
    settings: RuntimeSettings,
    *,
    explicit_token: str = "",
    mutate: bool = False,
) -> str:
    token = str(explicit_token or "").strip()
    if token:
        return token
    token = str(os.getenv("SITECTL_TOKEN", "") or "").strip()
    if token:
        return token
    if settings.hub_token_file.exists():
        try:
            token = settings.hub_token_file.read_text(encoding="utf-8").strip()
        except OSError:
            token = ""
        if token:
            return token
    if not mutate:
        return ""
    generated = "sitectl-" + secrets.token_hex(24)
    settings.hub_token_file.parent.mkdir(parents=True, exist_ok=True)
    settings.hub_token_file.write_text(generated + "\n", encoding="utf-8")
    return generated


def format_runtime_env(settings: RuntimeSettings, *, token: str | None = None, shell: str = "shell") -> str:
    rows = settings.env_map(token=token)
    if shell == "json":
        import json

        return json.dumps(rows, ensure_ascii=False, indent=2) + "\n"
    if shell == "powershell":
        lines = []
        for key, value in rows.items():
            escaped = value.replace("`", "``").replace('"', '`"')
            lines.append(f'$env:{key} = "{escaped}"')
        return "\n".join(lines) + "\n"
    if shell != "shell":
        raise ValueError(f"unsupported shell format: {shell}")
    import shlex

    lines = [f"export {key}={shlex.quote(value)}" for key, value in rows.items()]
    return "\n".join(lines) + "\n"


def _apply_env_defaults(path: Path) -> None:
    if not path.exists():
        return
    for key, value in _parse_env_file(path).items():
        os.environ.setdefault(key, value)


def _parse_env_file(path: Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        rows[key] = value
    return rows


def _load_yaml_mapping(path: Path, *, required: bool) -> dict[str, Any]:
    if not path.exists():
        if required:
            raise RuntimeError(f"Required config file is missing: {path}")
        return {}
    try:
        text = path.read_text(encoding="utf-8")
        if yaml is None:
            payload = _simple_yaml_load(text)
        else:
            payload = yaml.safe_load(text)
    except Exception as exc:  # pragma: no cover - message path for broken user config
        raise RuntimeError(f"Failed to read config file {path}: {exc}") from exc
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise RuntimeError(f"Config file must contain a mapping object: {path}")
    return payload


def _resolve_root_value(value: Any, *, base: Path) -> Path:
    text = str(value or "").strip()
    candidate = Path(text).expanduser()
    if not candidate.is_absolute():
        candidate = (base / candidate).resolve()
    else:
        candidate = candidate.resolve()
    return candidate


def _resolve_child_path(
    *,
    env_name: str,
    local_config: dict[str, Any],
    default_config: dict[str, Any],
    dotted_key: str,
    fallback: Any,
    base: Path,
) -> Path:
    value = _select_value(env_name, local_config, default_config, dotted_key, fallback)
    return _resolve_root_value(value, base=base)


def _select_value(
    env_name: str,
    local_config: dict[str, Any],
    default_config: dict[str, Any],
    dotted_key: str,
    fallback: Any,
) -> Any:
    if env_name in os.environ and str(os.environ.get(env_name, "")).strip():
        return os.environ[env_name]
    local_value = _nested_get(local_config, dotted_key)
    if local_value not in (None, ""):
        return local_value
    default_value = _nested_get(default_config, dotted_key)
    if default_value not in (None, ""):
        return default_value
    return fallback


def _nested_get(payload: dict[str, Any], dotted_key: str) -> Any:
    current: Any = payload
    for chunk in dotted_key.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(chunk)
    return current


def _runtime_override_present() -> bool:
    return any(
        str(os.getenv(name, "") or "").strip()
        for name in (
            "SITECTL_RUNTIME_ROOT",
            "SITECTL_STATE_FILE",
            "SITECTL_LOG_DIR",
            "SITECTL_REPORTS_ROOT",
            "SITECTL_RUNTIME_EVENTS_LOG",
            "SITECTL_RUNTIME_ERRORS_LOG",
            "SITECTL_BROWSER_PROFILE",
            "SITECTL_FIREFOX_PROFILE",
            "TELEGRAM_WORKSPACE_ROOT",
            "TELEGRAM_USERS_REGISTRY_FILE",
            "TELEGRAM_API_ACCOUNTS_FILE",
            "TELEGRAM_MANAGED_HELPER_ROOT",
            "TELEGRAM_DEFAULT_OUTPUT_DIR",
        )
    )


def _legacy_runtime_present(path: Path) -> bool:
    return any(
        candidate.exists()
        for candidate in (
            path / "state.json",
            path / "telegram_workspace",
            path / "browser-profile",
            path / "firefox-profile",
        )
    )


def _write_legacy_local_config(path: Path, legacy_root: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    legacy_text = str(legacy_root)
    payload = (
        "version: 1\n"
        "runtime:\n"
        f'  root: "{legacy_text}"\n'
        "hub:\n"
        f'  state_file: "{legacy_root / "state.json"}"\n'
        "browser:\n"
        f'  profile_dir: "{legacy_root / "browser-profile"}"\n'
        f'  firefox_profile_dir: "{legacy_root / "firefox-profile"}"\n'
        "logging:\n"
        f'  root_dir: "{legacy_root / "logs"}"\n'
        f'  runtime_events_file: "{legacy_root / "logs" / "runtime_events.jsonl"}"\n'
        f'  runtime_errors_file: "{legacy_root / "logs" / "runtime_errors.jsonl"}"\n'
        "reports:\n"
        f'  root_dir: "{legacy_root / "reports"}"\n'
        "telegram:\n"
        f'  workspace_root: "{legacy_root / "telegram_workspace"}"\n'
        "compatibility:\n"
        f'  adopted_legacy_home_root: "{legacy_text}"\n'
    )
    path.write_text(payload, encoding="utf-8")


def _simple_yaml_load(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if ":" not in line:
            raise ValueError(f"unsupported YAML line: {raw}")
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        current = stack[-1][1]
        if not value:
            nested: dict[str, Any] = {}
            current[key] = nested
            stack.append((indent, nested))
            continue
        current[key] = _simple_yaml_scalar(value)
    return root


def _simple_yaml_scalar(value: str) -> Any:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    lowered = text.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none"}:
        return None
    try:
        return int(text)
    except ValueError:
        return text
