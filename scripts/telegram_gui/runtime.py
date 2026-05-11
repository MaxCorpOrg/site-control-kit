from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..telegram_product_runtime import resolve_product_paths
from webcontrol.settings import RuntimeSettings, load_runtime_settings, venv_python_path


@dataclass(frozen=True, slots=True)
class GuiRuntimePaths:
    settings: RuntimeSettings
    repo_root: Path
    scripts_dir: Path
    extension_dir: Path
    telegram_workspace_root: Path
    user_registry_path: Path
    default_profile_dir: Path
    portable_profiles_root: Path
    default_output_dir: Path
    artifact_index_path: Path
    action_log_dir: Path
    runtime_dir: Path
    runtime_owners_dir: Path
    managed_helper_root: Path
    managed_helper_venv_dir: Path
    managed_helper_python: Path
    artifact_index_path: Path
    product_mode: str
    extension_zip_path: Path
    desktop_file_path: Path
    icon_path: Path
    hub_url: str
    tdata_session_dir: Path


def load_gui_runtime_paths(*, mutate: bool) -> GuiRuntimePaths:
    settings = load_runtime_settings(mutate=mutate)
    repo_root = settings.project_root
    scripts_dir = repo_root / "scripts"
    telegram_workspace_root = settings.telegram_workspace_root
    runtime_dir = telegram_workspace_root / "runtime"
    managed_helper_root = settings.telegram_managed_helper_root
    managed_helper_venv_dir = managed_helper_root / ".venv"
    product_paths = resolve_product_paths(settings=settings)
    artifact_index_path = (
        settings.telegram_default_output_dir / "INDEX.md"
        if product_paths.installed_mode
        else repo_root / "artifacts" / "telegram_exports" / "INDEX.md"
    )
    return GuiRuntimePaths(
        settings=settings,
        repo_root=repo_root,
        scripts_dir=scripts_dir,
        extension_dir=product_paths.extension_dir,
        telegram_workspace_root=telegram_workspace_root,
        user_registry_path=settings.telegram_users_registry_file,
        default_profile_dir=settings.browser_profile_dir,
        portable_profiles_root=telegram_workspace_root / "cache" / "unpacked_profiles",
        default_output_dir=settings.telegram_default_output_dir,
        artifact_index_path=artifact_index_path,
        action_log_dir=telegram_workspace_root / "logs",
        runtime_dir=runtime_dir,
        runtime_owners_dir=runtime_dir / "owners",
        managed_helper_root=managed_helper_root,
        managed_helper_venv_dir=managed_helper_venv_dir,
        managed_helper_python=venv_python_path(managed_helper_venv_dir),
        product_mode=product_paths.mode,
        extension_zip_path=product_paths.extension_zip_path,
        desktop_file_path=product_paths.desktop_file,
        icon_path=product_paths.icon_path,
        hub_url=settings.server_url,
        tdata_session_dir=runtime_dir / "tdata_sessions",
    )
