from __future__ import annotations

import importlib.util
import os
import shutil
import stat
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from webcontrol.settings import RuntimeSettings, load_runtime_settings, resolve_hub_token, venv_python_path

PRODUCT_MODE_ENV = "SITECTL_PRODUCT_MODE"
INSTALLED_PRODUCT_MODE = "installed"
PRODUCT_NAME = "Telegram Username Collector"
PRODUCT_EXECUTABLE_ENV = "SITECTL_PRODUCT_EXECUTABLE"
PRODUCT_APP_ROOT_ENV = "SITECTL_PRODUCT_APP_ROOT"
PRODUCT_VENV_ENV = "SITECTL_PRODUCT_VENV"
PRODUCT_DESKTOP_FILE_ENV = "SITECTL_PRODUCT_DESKTOP_FILE"
PRODUCT_ICON_ENV = "SITECTL_PRODUCT_ICON"
PRODUCT_EXTENSION_DIR_ENV = "SITECTL_PRODUCT_EXTENSION_DIR"
PRODUCT_EXTENSION_ZIP_ENV = "SITECTL_PRODUCT_EXTENSION_ZIP"


@dataclass(frozen=True, slots=True)
class ProductPaths:
    mode: str
    installed_mode: bool
    product_name: str
    app_root: Path
    venv_root: Path
    venv_python: Path
    executable_name: str
    desktop_file: Path
    icon_path: Path
    extension_dir: Path
    extension_zip_path: Path


@dataclass(frozen=True, slots=True)
class ProductDoctorReport:
    mode: str
    overall_status: str
    project_root: Path
    runtime_root: Path
    token_file: Path
    token_present: bool
    logs_root: Path
    reports_root: Path
    workspace_root: Path
    helper_source: str
    helper_python: Path | None
    gtk_runtime: str
    extension_dir: Path
    extension_zip_path: Path
    extension_zip_ready: bool
    desktop_file: Path
    desktop_dir: Path
    hub_url: str
    hub_reachable: bool


def is_installed_product_mode() -> bool:
    return str(os.getenv(PRODUCT_MODE_ENV, "") or "").strip().lower() == INSTALLED_PRODUCT_MODE


def resolve_product_paths(*, settings: RuntimeSettings | None = None) -> ProductPaths:
    runtime_settings = settings or load_runtime_settings(mutate=False)
    installed_mode = is_installed_product_mode()
    app_root = Path(
        str(os.getenv(PRODUCT_APP_ROOT_ENV, "") or "").strip()
        or str(runtime_settings.project_root)
    ).expanduser().resolve()
    venv_root_default = app_root.parent / "venv" if installed_mode else app_root / ".site-control-kit" / "_product_venv_missing"
    venv_root = Path(
        str(os.getenv(PRODUCT_VENV_ENV, "") or "").strip()
        or str(venv_root_default)
    ).expanduser().resolve()
    executable_name = str(os.getenv(PRODUCT_EXECUTABLE_ENV, "") or "").strip() or "telegram-username-collector"
    desktop_file = Path(
        str(os.getenv(PRODUCT_DESKTOP_FILE_ENV, "") or "").strip()
        or f"/usr/share/applications/{executable_name}.desktop"
    ).expanduser().resolve()
    icon_path = Path(
        str(os.getenv(PRODUCT_ICON_ENV, "") or "").strip()
        or f"/usr/share/icons/hicolor/256x256/apps/{executable_name}.png"
    ).expanduser().resolve()
    extension_dir = Path(
        str(os.getenv(PRODUCT_EXTENSION_DIR_ENV, "") or "").strip()
        or str(app_root / "extension")
    ).expanduser().resolve()
    extension_zip_raw = str(os.getenv(PRODUCT_EXTENSION_ZIP_ENV, "") or "").strip()
    if extension_zip_raw:
        extension_zip_path = Path(extension_zip_raw).expanduser().resolve()
    else:
        bundled_zip = (app_root / "resources" / "site-control-bridge-extension.zip").resolve()
        dist_zip = (runtime_settings.project_root / "dist" / "site-control-bridge-extension.zip").resolve()
        extension_zip_path = bundled_zip if bundled_zip.exists() or installed_mode else dist_zip
    return ProductPaths(
        mode=INSTALLED_PRODUCT_MODE if installed_mode else "repo",
        installed_mode=installed_mode,
        product_name=PRODUCT_NAME,
        app_root=app_root,
        venv_root=venv_root,
        venv_python=venv_python_path(venv_root),
        executable_name=executable_name,
        desktop_file=desktop_file,
        icon_path=icon_path,
        extension_dir=extension_dir,
        extension_zip_path=extension_zip_path,
    )


def desktop_dir() -> Path:
    xdg_user_dir = shutil.which("xdg-user-dir")
    if xdg_user_dir:
        try:
            completed = subprocess.run(
                [xdg_user_dir, "DESKTOP"],
                check=True,
                capture_output=True,
                text=True,
            )
            candidate = Path((completed.stdout or "").strip()).expanduser()
            if candidate != Path() and str(candidate).strip():
                return candidate.resolve()
        except Exception:
            pass
    home_dir = _safe_home_dir()
    for candidate in (home_dir / "Desktop", home_dir / "Рабочий стол"):
        if candidate.exists():
            return candidate.resolve()
    return (home_dir / "Desktop").resolve()


def render_desktop_entry(executable_name: str = "telegram-username-collector") -> str:
    return (
        "[Desktop Entry]\n"
        "Version=1.0\n"
        "Type=Application\n"
        f"Name={PRODUCT_NAME}\n"
        "Comment=Collect Telegram usernames from Telegram Desktop history\n"
        "Comment[ru]=Сбор Telegram username из истории Telegram Desktop\n"
        f"Exec={executable_name}\n"
        f"Icon={executable_name}\n"
        "Terminal=false\n"
        "Categories=Utility;Network;\n"
        "Keywords=telegram;username;collector;\n"
        f"StartupWMClass={PRODUCT_NAME}\n"
        "StartupNotify=true\n"
    )


def create_desktop_shortcut(*, destination: Path | None = None) -> Path:
    product_paths = resolve_product_paths()
    target_dir = (destination or desktop_dir()).expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{PRODUCT_NAME}.desktop"
    if product_paths.desktop_file.exists():
        content = product_paths.desktop_file.read_text(encoding="utf-8")
    else:
        content = render_desktop_entry(product_paths.executable_name)
    target_path.write_text(content, encoding="utf-8")
    target_path.chmod(target_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return target_path


def gather_doctor_report(*, project_root: Path | None = None, mutate: bool = True) -> ProductDoctorReport:
    settings = load_runtime_settings(project_root=project_root, mutate=mutate)
    product_paths = resolve_product_paths(settings=settings)
    token = resolve_hub_token(settings, mutate=mutate)
    helper_source, helper_python = _detect_helper_python(settings, product_paths)
    gtk_runtime = _gtk_runtime_status()
    hub_reachable = _hub_reachable(settings.server_url)
    extension_zip_ready = product_paths.extension_zip_path.exists()
    overall_status = "ok"
    if gtk_runtime != "ok" or helper_python is None:
        overall_status = "blocked"
    elif not extension_zip_ready or not hub_reachable:
        overall_status = "warning"
    return ProductDoctorReport(
        mode=product_paths.mode,
        overall_status=overall_status,
        project_root=settings.project_root,
        runtime_root=settings.runtime_root,
        token_file=settings.hub_token_file,
        token_present=bool(token),
        logs_root=settings.logs_root,
        reports_root=settings.reports_root,
        workspace_root=settings.telegram_workspace_root,
        helper_source=helper_source,
        helper_python=helper_python,
        gtk_runtime=gtk_runtime,
        extension_dir=product_paths.extension_dir,
        extension_zip_path=product_paths.extension_zip_path,
        extension_zip_ready=extension_zip_ready,
        desktop_file=product_paths.desktop_file,
        desktop_dir=desktop_dir(),
        hub_url=settings.server_url,
        hub_reachable=hub_reachable,
    )


def format_doctor_report(report: ProductDoctorReport) -> str:
    lines = [
        f"product_name={PRODUCT_NAME}",
        f"mode={report.mode}",
        f"overall_status={report.overall_status}",
        f"project_root={report.project_root}",
        f"runtime_root={report.runtime_root}",
        f"token_file={report.token_file}",
        f"token_present={1 if report.token_present else 0}",
        f"logs_root={report.logs_root}",
        f"reports_root={report.reports_root}",
        f"workspace_root={report.workspace_root}",
        f"helper_source={report.helper_source}",
        f"helper_python={report.helper_python or '-'}",
        f"gtk_runtime={report.gtk_runtime}",
        f"extension_dir={report.extension_dir}",
        f"extension_zip={report.extension_zip_path}",
        f"extension_zip_ready={1 if report.extension_zip_ready else 0}",
        f"desktop_file={report.desktop_file}",
        f"desktop_dir={report.desktop_dir}",
        f"hub_url={report.hub_url}",
        f"hub_reachable={1 if report.hub_reachable else 0}",
    ]
    return "\n".join(lines) + "\n"


def _detect_helper_python(
    settings: RuntimeSettings,
    product_paths: ProductPaths,
) -> tuple[str, Path | None]:
    explicit_raw = str(os.getenv("TELEGRAM_API_COLLECTOR_PYTHON", "") or "").strip()
    if explicit_raw:
        explicit = Path(explicit_raw).expanduser()
    else:
        explicit = None
    if explicit is not None and explicit.exists():
        return "explicit", explicit.resolve()
    if product_paths.venv_python.exists():
        return "product", product_paths.venv_python.resolve()
    managed_helper = venv_python_path(settings.telegram_managed_helper_root / ".venv")
    if managed_helper.exists():
        return "managed", managed_helper.resolve()
    return "missing", None


def _gtk_runtime_status() -> str:
    if importlib.util.find_spec("gi") is None:
        return "missing"
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk  # noqa: F401
    except Exception:
        return "broken"
    return "ok"


def _safe_home_dir() -> Path:
    for env_name in ("HOME", "USERPROFILE"):
        raw = str(os.getenv(env_name, "") or "").strip()
        if raw:
            return Path(raw).expanduser().resolve()
    try:
        return Path.home().resolve()
    except RuntimeError:
        return Path.cwd().resolve()


def _hub_reachable(server_url: str) -> bool:
    url = f"{server_url.rstrip('/')}/health"
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return int(getattr(response, "status", 0) or 0) == 200
    except (OSError, urllib.error.URLError, ValueError):
        return False
