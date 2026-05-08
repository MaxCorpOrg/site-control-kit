#!/usr/bin/env python3
from __future__ import annotations

import atexit
import hashlib
import json
import os
import queue
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango

try:
    from .. import export_telegram_members_non_pii as export_mod
    from .. import telegram_user_registry as registry_mod
    from .. import telegram_workspace_layout as layout_mod
except ImportError:
    SCRIPT_DIR_FALLBACK = Path(__file__).resolve().parents[1]
    if str(SCRIPT_DIR_FALLBACK) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR_FALLBACK))
    import export_telegram_members_non_pii as export_mod  # type: ignore[no-redef]
    import telegram_user_registry as registry_mod  # type: ignore[no-redef]
    import telegram_workspace_layout as layout_mod  # type: ignore[no-redef]

from .adapters.base import TelegramExecutionAdapter
from .adapters.bridge import BridgeAdapter
from .adapters.cdp import CdpAdapter
from .adapters.tdata import TdataAdapter
from .models import (
    AccountOption,
    ArtifactBundle,
    BrowserTarget,
    ChatOption,
    PortableProfileRemovalResult,
    PortableProfileStatus,
    ExportProgressState,
    ExportResult,
    FallbackReadiness,
    PortableProfile,
    PortableRuntimeState,
    PortableSourceInfo,
    PreflightInfo,
    ProgressEvent,
    RunRecord,
    SessionResumeState,
)
from .services.artifact_index import append_index_entry, build_artifact_bundle
from .services.portable_profiles import PortableProfileRegistry, portable_profile_kind, portable_profile_label
from .services.process_runner import ProcessRunner, TaskCancelled, TaskController
from .services.preflight import PreflightService
from .services.run_history import RunHistoryService
from .services.secrets import SecretStore, mask_secret
from .services.ui_tasks import UiTaskService
from .ui.panels import ArtifactPanel, HistoryPanel, PreflightPanel, ProgressPanel
from .ui.styles import install_css


def _optional_timeout_env(name: str, *, default_value: str, minimum: int) -> int | None:
    raw = str(os.getenv(name, default_value) or default_value).strip()
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        parsed = int(default_value or "0")
    if parsed <= 0:
        return None
    return max(parsed, minimum)

PACKAGE_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = PACKAGE_DIR.parent
REPO_ROOT = SCRIPTS_DIR.parent
RUN_ONCE_SCRIPT = SCRIPTS_DIR / "run_chat_export_once.sh"
SAFE_SNAPSHOT_SCRIPT = SCRIPTS_DIR / "write_telegram_safe_snapshot.py"
START_BROWSER_SCRIPT = SCRIPTS_DIR / "start_browser.sh"
EXTENSION_DIR = REPO_ROOT / "extension"
CDP_HELPER_SCRIPT = SCRIPTS_DIR / "telegram_cdp_helper.js"
TDATA_HELPER_SCRIPT = SCRIPTS_DIR / "telegram_tdata_helper.py"
TELEGRAM_API_COLLECTOR_ROOT = Path(
    os.getenv("TELEGRAM_API_COLLECTOR_ROOT", str(Path.home() / "telegram-api-collector"))
).expanduser()
TELEGRAM_API_COLLECTOR_PYTHON = Path(
    os.getenv("TELEGRAM_API_COLLECTOR_PYTHON", str(TELEGRAM_API_COLLECTOR_ROOT / ".venv" / "bin" / "python"))
).expanduser()
TELEGRAM_API_COLLECTOR_TDATA_DIR = Path(
    os.getenv("TELEGRAM_API_COLLECTOR_TDATA_DIR", str(TELEGRAM_API_COLLECTOR_ROOT / "tdata_import" / "tdata"))
).expanduser()

TELEGRAM_WORKSPACE_ROOT = Path(
    os.getenv("TELEGRAM_WORKSPACE_ROOT", str(Path.home() / ".site-control-kit" / "telegram_workspace"))
).expanduser()
WORKSPACE_SLOTS = max(int(os.getenv("TELEGRAM_WORKSPACE_SLOTS", "10") or "10"), 1)
USER_REGISTRY_PATH = Path(
    os.getenv("TELEGRAM_USERS_REGISTRY_FILE", str(TELEGRAM_WORKSPACE_ROOT / "registry" / "users.json"))
).expanduser()
DEFAULT_TOKEN = os.getenv("SITECTL_TOKEN", "local-bridge-quickstart-2026")
DEFAULT_PROFILE_DIR = Path(
    os.getenv("SITECTL_BROWSER_PROFILE", str(TELEGRAM_WORKSPACE_ROOT / "profiles" / "default"))
).expanduser()
PORTABLE_PROFILES_ROOT = TELEGRAM_WORKSPACE_ROOT / "cache" / "unpacked_profiles"
DEFAULT_OUTPUT_DIR = Path.home() / "Загрузки" / "Telegram Desktop"
ARTIFACT_INDEX_PATH = REPO_ROOT / "artifacts" / "telegram_exports" / "INDEX.md"
DEFAULT_MIN_RECORDS = "20"
ACTION_LOG_DIR = TELEGRAM_WORKSPACE_ROOT / "logs"
RUNTIME_DIR = TELEGRAM_WORKSPACE_ROOT / "runtime"
RUNTIME_OWNERS_DIR = RUNTIME_DIR / "owners"
MANAGED_HELPER_ROOT = Path(
    os.getenv("TELEGRAM_MANAGED_HELPER_ROOT", str(TELEGRAM_WORKSPACE_ROOT / "managed_helper"))
).expanduser()
MANAGED_HELPER_VENV_DIR = MANAGED_HELPER_ROOT / ".venv"
MANAGED_HELPER_PYTHON = MANAGED_HELPER_VENV_DIR / "bin" / "python"
HELPER_REQUIREMENTS_FILE = SCRIPTS_DIR / "telegram_helper_requirements.txt"
LOCK_DIR = Path(tempfile.gettempdir()) / "site-control-kit-telegram-members-export-gui.lockdir"
LOCK_PID_FILE = LOCK_DIR / "pid"

CHAT_STEPS = str(max(int(os.getenv("CHAT_SCROLL_STEPS", "60") or "60"), 0))
CHAT_DEEP_LIMIT = str(max(int(os.getenv("CHAT_DEEP_LIMIT", "3") or "3"), 0))
CHAT_TIMEOUT_SEC = str(max(int(os.getenv("CHAT_TIMEOUT_SEC", "12") or "12"), 1))
CHAT_MAX_RUNTIME = str(max(int(os.getenv("CHAT_MAX_RUNTIME", "420") or "420"), 5))
CHAT_DEEP_MODE = os.getenv("CHAT_DEEP_MODE", "mention") or "mention"
TDATA_HISTORY_LIMIT = os.getenv("TELEGRAM_TDATA_HISTORY_LIMIT", "0") or "0"
TDATA_PROGRESS_EVERY = str(max(int(os.getenv("TELEGRAM_TDATA_PROGRESS_EVERY", "250") or "250"), 0))
TDATA_LIST_TIMEOUT_SEC = max(int(os.getenv("TELEGRAM_TDATA_LIST_TIMEOUT_SEC", "30") or "30"), 5)
TDATA_EXPORT_TIMEOUT_SEC = _optional_timeout_env("TELEGRAM_TDATA_EXPORT_TIMEOUT_SEC", default_value="0", minimum=30)
QUICK_CHECK_HISTORY_LIMIT = str(max(int(os.getenv("TELEGRAM_TDATA_QUICK_HISTORY_LIMIT", "400") or "400"), 1))
QUICK_CHECK_TIMEOUT_SEC = max(int(os.getenv("TELEGRAM_TDATA_QUICK_TIMEOUT_SEC", "300") or "300"), 30)
RUN_PRESETS: tuple[tuple[str, str], ...] = (
    ("full_history", "Full History"),
    ("quick_check", "Quick Check"),
    ("resume_last", "Resume Last"),
)

HUB_URL = "http://127.0.0.1:8765"
TELEGRAM_WEB_URL = "https://web.telegram.org/a/"
CDP_PORT_BASE = 9227
CDP_PORT_SPAN = 240
TDATA_SESSION_DIR = RUNTIME_DIR / "tdata_sessions"
TDATA_SIGNATURE_FILES = ("key_datas", "D877F783D5D3EF8Cs", "D877F783D5D3EF8C/maps")
ALLOW_COLLECTOR_TDATA_DEBUG_FALLBACK = str(os.getenv("TELEGRAM_TDATA_ALLOW_COLLECTOR_FALLBACK", "")).strip() == "1"
WINDOW_TITLE = "Telegram Username Collector"
WINDOW_WIDTH = 1380
WINDOW_HEIGHT = 920
CHAT_LIST_READY_SELECTOR = "#LeftColumn a.chatlist-chat, #column-left a.chatlist-chat, a.chatlist-chat, #LeftColumn, #column-left"

TELEGRAM_TITLE_SUFFIX_RE = re.compile(r"\s*\|\s*Telegram\s*$", flags=re.I)
VISIBLE_DIALOGS_SCRIPT = r'''
const compact = (value) => String(value || "").replace(/\s+/g, " ").trim();
const visible = (node) => {
  if (!node) return false;
  const rect = node.getBoundingClientRect();
  if (rect.width < 6 || rect.height < 6) return false;
  if (rect.bottom <= 0 || rect.right <= 0 || rect.top >= window.innerHeight || rect.left >= window.innerWidth) {
    return false;
  }
  const style = window.getComputedStyle(node);
  if (!style) return true;
  return style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity || "1") !== 0;
};
const textOf = (root, selectors) => {
  for (const selector of selectors) {
    const node = root.querySelector(selector);
    const text = compact(node?.innerText || node?.textContent || node?.getAttribute?.("aria-label") || "");
    if (text) return text;
  }
  return "";
};
const modeMatch = String(window.location.href || "").match(/web\.telegram\.org\/([ak])\//i);
const mode = modeMatch ? modeMatch[1].toLowerCase() : "a";
const anchors = Array.from(document.querySelectorAll(
  [
    "#LeftColumn a.chatlist-chat",
    "#column-left a.chatlist-chat",
    "a.chatlist-chat",
    "a[href^='#'][data-peer-id]"
  ].join(",")
));
const items = [];
const seen = new Set();
anchors.forEach((anchor, index) => {
  const href = compact(anchor.getAttribute("href") || "");
  const peerId = compact(anchor.getAttribute("data-peer-id") || "");
  const fragment = href.startsWith("#") ? href.slice(1) : peerId;
  if (!fragment || seen.has(fragment)) return;
  const title = textOf(anchor, [
    ".fullName",
    ".peer-title-inner",
    ".peer-title",
    ".user-title",
    "h3",
    "[dir='auto']"
  ]);
  const subtitle = textOf(anchor, [
    ".row-subtitle",
    ".subtitle",
    ".status",
    ".user-status",
    ".last-message"
  ]);
  const row = anchor.closest("a, .ListItem, .chatlist-chat") || anchor;
  const active = row.classList.contains("active") || anchor.classList.contains("active") || anchor.getAttribute("aria-current") === "true";
  const payload = {
    index,
    title: title || fragment,
    subtitle,
    fragment,
    peer_id: peerId,
    url: `https://web.telegram.org/${mode}/#${fragment}`,
    active,
    visible: visible(anchor) || visible(row)
  };
  seen.add(fragment);
  items.push(payload);
});
return {
  mode,
  current_url: String(window.location.href || ""),
  current_title: String(document.title || ""),
  items
};
'''

CSS = b"""
window {
  background: #efe8db;
}
.hero {
  background: linear-gradient(135deg, #1f5c54 0%, #2a7468 100%);
  border-radius: 22px;
  padding: 24px;
  color: #f5efe2;
}
.hero-title {
  font-size: 22px;
  font-weight: 800;
}
.hero-copy {
  color: rgba(245, 239, 226, 0.88);
}
.badge {
  background: #dbe8e1;
  color: #18473f;
  border-radius: 999px;
  padding: 6px 12px;
  font-weight: 700;
}
.card {
  background: #fffaf0;
  border-radius: 20px;
  padding: 18px;
}
.card-title {
  font-size: 15px;
  font-weight: 800;
  color: #24211d;
}
.meta {
  color: #6a655d;
}
.accent-button {
  background: #c66f21;
  color: #fff8ef;
  border-radius: 14px;
  padding: 10px 16px;
  font-weight: 700;
}
.subtle-button {
  background: #e7ded1;
  color: #302c29;
  border-radius: 14px;
  padding: 10px 14px;
}
.chat-row {
  background: transparent;
  border-radius: 14px;
  padding: 10px 12px;
}
.chat-row-active {
  background: #eef3f0;
}
.chat-title {
  font-weight: 700;
  color: #24211d;
}
.chat-subtitle {
  color: #6b645c;
  font-size: 12px;
}
.art-card {
  background: rgba(255,255,255,0.14);
  border-radius: 18px;
  padding: 16px;
}
.art-chip {
  background: rgba(255,255,255,0.18);
  border-radius: 999px;
  padding: 6px 10px;
  font-weight: 700;
}
.dim-box {
  background: #f6efe1;
  border-radius: 16px;
  padding: 10px 12px;
}
"""


def _mask_known_secrets(text: str, secrets: list[str]) -> str:
    sanitized = str(text or "")
    for raw in secrets:
        token = str(raw or "").strip()
        if not token:
            continue
        sanitized = sanitized.replace(token, mask_secret(token))
    return sanitized

class SingleInstanceLock:
    def __init__(self, lock_dir: Path, pid_file: Path):
        self.lock_dir = lock_dir
        self.pid_file = pid_file
        self.acquired = False

    def acquire(self) -> None:
        try:
            self.lock_dir.mkdir(parents=False, exist_ok=False)
        except FileExistsError:
            existing_pid = self._read_pid()
            if existing_pid and _pid_is_alive(existing_pid):
                raise RuntimeError(f"GUI уже запущен (PID {existing_pid}).")
            shutil.rmtree(self.lock_dir, ignore_errors=True)
            self.lock_dir.mkdir(parents=False, exist_ok=False)
        self.pid_file.write_text(f"{os.getpid()}\n", encoding="utf-8")
        self.acquired = True
        atexit.register(self.release)

    def release(self) -> None:
        if not self.acquired:
            return
        shutil.rmtree(self.lock_dir, ignore_errors=True)
        self.acquired = False

    def _read_pid(self) -> int | None:
        try:
            value = self.pid_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return None
        match = re.search(r"\d+", value or "")
        return int(match.group(0)) if match else None


class PrimarySurfaceBlocked(RuntimeError):
    pass


class TelegramGuiBackend:
    def __init__(self, *, action_log_path: Path):
        self.action_log_path = action_log_path
        self.export_mod = export_mod
        self.HUB_URL = HUB_URL
        self.TELEGRAM_WEB_URL = TELEGRAM_WEB_URL
        self.VISIBLE_DIALOGS_SCRIPT = VISIBLE_DIALOGS_SCRIPT
        self.process_runner = ProcessRunner()
        self.run_history = RunHistoryService(TELEGRAM_WORKSPACE_ROOT)
        self.secret_store = SecretStore(TELEGRAM_WORKSPACE_ROOT / "registry" / "secrets")
        self.preflight_service = PreflightService(workspace_root=TELEGRAM_WORKSPACE_ROOT, default_token=DEFAULT_TOKEN)
        self.portable_profiles = PortableProfileRegistry(
            workspace_root=TELEGRAM_WORKSPACE_ROOT,
            binary_finder=lambda profile_dir: find_portable_telegram_binary(profile_dir),
            logger=self._log_action,
        )
        self.adapters: tuple[TelegramExecutionAdapter, ...] = (
            TdataAdapter(self),
            BridgeAdapter(self),
            CdpAdapter(self),
        )
        self._adapters_by_key = {adapter.key: adapter for adapter in self.adapters}
        self._last_surface_reason = ""
        self._fallback_readiness_cache: dict[tuple[str, str], FallbackReadiness] = {}
        self._security_info_cache: dict[str, dict[str, Any]] = {}
        self._portable_runtime_cache: dict[tuple[str, bool], tuple[float, PortableRuntimeState]] = {}
        self._tdata_helper_lock = threading.Lock()
        self._prune_runtime_artifacts()

    def resolve_profile_dir(self, source_path: str) -> Path:
        return resolve_profile_dir(source_path)

    def normalize_chat_options(self, payload: Any) -> list[ChatOption]:
        return normalize_chat_options(payload)

    def normalize_tdata_chat_options(self, payload: Any) -> list[ChatOption]:
        return normalize_tdata_chat_options(payload)

    def _clean_tab_title(self, value: str) -> str:
        return _clean_tab_title(value)

    def _format_command_error(self, error: Any) -> str:
        return _format_command_error(error)

    def adapter_for_target(self, target: BrowserTarget) -> TelegramExecutionAdapter:
        for adapter in self.adapters:
            if adapter.matches_target(target):
                return adapter
        return self.adapters[-1]

    def surface_badge_for_target(self, target: BrowserTarget | None) -> str:
        if target is None:
            return "Surface pending"
        return self.adapter_for_target(target).badge

    def _preset_choice(self, preset_key: str) -> tuple[str, str]:
        for key, label in RUN_PRESETS:
            if key == preset_key:
                return key, label
        return RUN_PRESETS[0]

    def preset_limits(self, preset_key: str) -> tuple[str, int | None]:
        if preset_key == "quick_check":
            return QUICK_CHECK_HISTORY_LIMIT, QUICK_CHECK_TIMEOUT_SEC
        return "0", None

    def _account_cache_key(self, account: AccountOption | None) -> str:
        if account is None:
            return ""
        return account.key or _normalize_path_key(account.profile_source)

    def _pending_fallback_readiness(self, surface_key: str) -> FallbackReadiness:
        if surface_key == "cdp":
            return FallbackReadiness(
                surface_key="cdp",
                surface_label="Chrome profile direct",
                surface_badge="Fallback CDP",
                state="pending",
                detail="Проверка CDP surface будет выполнена в фоне или по явному refresh.",
                action_label="Повторить проверку",
            )
        return FallbackReadiness(
            surface_key="bridge",
            surface_label="Telegram Web bridge",
            surface_badge="Fallback Bridge",
            state="pending",
            detail="Проверка bridge surface будет выполнена в фоне или по явному refresh.",
            action_label="Повторить проверку",
        )

    def resolve_profile_dir_safe(self, source_path: str) -> tuple[Path | None, str, str]:
        source = str(source_path or "").strip()
        if not source:
            default_profile = DEFAULT_PROFILE_DIR.expanduser()
            if default_profile.exists():
                return (default_profile.resolve(), "ready", f"Используется default profile: {default_profile}")
            return (None, "missing", f"Default profile не найден: {default_profile}")
        candidate = Path(source).expanduser()
        if candidate.is_dir():
            return (candidate.resolve(), "ready", f"Профиль найден: {candidate}")
        if candidate.is_file() and candidate.suffix.lower() == ".zip":
            try:
                return (resolve_profile_dir(source), "ready", f"ZIP profile готов: {candidate}")
            except Exception as exc:
                return (None, "missing", _compact_error_text(str(exc)) or f"Не удалось подготовить ZIP profile: {candidate}")
        if candidate.exists():
            return (None, "missing", f"Путь профиля не является каталогом Telegram: {candidate}")
        return (None, "missing", f"Путь профиля больше не найден: {candidate}")

    def inspect_account_security(self, account: AccountOption | None, *, deep: bool = False) -> dict[str, Any]:
        if account is None:
            return {
                "slot_number": "",
                "token_source": "missing",
                "security_mode": "No token configured",
                "security_state": "blocked",
                "hub_token_status": "pending",
                "hub_token_detail": "Hub token state будет доступен после выбора профиля.",
                "hub_restart_available": False,
            }
        slot_number = account.slot_number or _slot_number_from_source(account.profile_source)
        token_source = account.token_source or _account_token_source(
            token=account.token,
            secret_ref=account.secret_ref,
            slot_token=_slot_token(slot_number),
            default_token=DEFAULT_TOKEN,
        )
        security_mode, security_state = self.preflight_service.security_mode(account.token)
        cache_key = self._account_cache_key(account)
        if deep:
            hub_state = self._inspect_hub_token_state(account.token)
            cached = {
                "slot_number": slot_number,
                "token_source": token_source,
                "security_mode": security_mode,
                "security_state": security_state,
                "hub_token_status": str(hub_state.get("state") or ""),
                "hub_token_detail": str(hub_state.get("detail") or ""),
                "hub_restart_available": bool(hub_state.get("restart_available")),
            }
            if cache_key:
                self._security_info_cache[cache_key] = cached
            return cached
        cached = self._security_info_cache.get(cache_key)
        hub_token_status = "pending"
        hub_token_detail = "Hub token state будет уточнён в фоне или после явного refresh."
        hub_restart_available = False
        if isinstance(cached, dict):
            hub_token_status = str(cached.get("hub_token_status") or hub_token_status)
            hub_token_detail = str(cached.get("hub_token_detail") or hub_token_detail)
            hub_restart_available = bool(cached.get("hub_restart_available"))
        return {
            "slot_number": slot_number,
            "token_source": token_source,
            "security_mode": security_mode,
            "security_state": security_state,
            "hub_token_status": hub_token_status,
            "hub_token_detail": hub_token_detail,
            "hub_restart_available": hub_restart_available,
        }

    def load_portable_profiles(self) -> list[PortableProfileStatus]:
        layout_mod.ensure_workspace(TELEGRAM_WORKSPACE_ROOT, slots=WORKSPACE_SLOTS)
        accounts_dir = TELEGRAM_WORKSPACE_ROOT / "accounts"
        if accounts_dir.exists():
            for slot_dir in sorted((item for item in accounts_dir.iterdir() if item.is_dir()), key=lambda path: path.name):
                slot_number = slot_dir.name
                self.portable_profiles.sync_legacy_slot_profile(slot_number)
        return self.portable_profiles.list_profiles()

    def portable_profile_for_account(self, account: AccountOption | None) -> PortableProfileStatus | None:
        if account is None:
            return None
        profile_dir = str(account.portable_profile_dir or account.profile_source or "").strip()
        if profile_dir:
            status = self.portable_profiles.status(profile_dir)
            if status is not None:
                return status
            resolved_dir, availability_state, availability_detail = self.resolve_profile_dir_safe(profile_dir)
            if availability_state == "missing" and not (account.slot_number or _slot_number_from_source(account.profile_source)):
                return self._missing_portable_profile_status(
                    profile_dir=resolved_dir or Path(profile_dir).expanduser(),
                    label=account.portable_profile_label or account.label,
                    detail=availability_detail,
                )
        slot_number = account.slot_number or _slot_number_from_source(account.profile_source)
        if slot_number:
            return self.portable_profiles.sync_legacy_slot_profile(
                slot_number,
                profile_name=account.portable_profile_name or account.name,
                account_username="",
                account_label=account.portable_profile_label or account.label,
            )
        return None

    def _account_prefers_portable_profile(
        self,
        account: AccountOption | None,
        profile_status: PortableProfileStatus | None,
    ) -> bool:
        if account is None or profile_status is None:
            return False
        profile_key = _normalize_path_key(str(profile_status.profile_dir))
        if _normalize_path_key(account.profile_source) == profile_key:
            return True
        if account.source_kind == "registry" and _normalize_path_key(account.portable_profile_dir) == profile_key:
            return True
        return False

    def _missing_portable_profile_status(self, *, profile_dir: Path, label: str, detail: str) -> PortableProfileStatus:
        root = profile_dir.expanduser()
        source_kind = "managed_folder" if self.portable_profiles._is_under_profiles_root(root) else "adopted_folder"
        managed = source_kind == "managed_folder"
        return PortableProfileStatus(
            profile=PortableProfile(
                profile_id=hashlib.sha1(str(root).encode("utf-8")).hexdigest()[:16],
                profile_name=label or root.name or "portable-profile",
                profile_dir=root,
                binary_path=None,
                portable_dir=root / "TelegramForcePortable",
                tdata_dir=root / "TelegramForcePortable" / "tdata",
                metadata_path=root / "portable-profile.json",
                account_label=label,
                source_kind=source_kind,
                source_path=root,
                managed=managed,
            ),
            running=False,
            pid=None,
            state="missing",
            detail=detail,
        )

    def ensure_account_for_portable_profile(
        self,
        status: PortableProfileStatus,
        *,
        fallback_token: str = "",
        set_default: bool = False,
    ) -> dict[str, str]:
        registry = registry_mod.load_registry(USER_REGISTRY_PATH)
        existing = registry_mod.find_user_by_profile(registry, profile=str(status.profile_dir))
        token = str(existing.get("token") or "").strip() or str(fallback_token or "").strip() or DEFAULT_TOKEN
        label = status.account_label or status.account_username or status.profile_name
        next_registry = registry_mod.add_or_update_user_by_profile(
            registry,
            name=label,
            token=token,
            profile=str(status.profile_dir),
            secret_ref=str(existing.get("secret_ref") or "").strip(),
            set_default=set_default,
        )
        registry_mod.save_registry(USER_REGISTRY_PATH, next_registry)
        row = registry_mod.find_user_by_profile(next_registry, profile=str(status.profile_dir))
        self._log_action(
            f"portable_profile_account_synced profile={status.profile_dir} user={label} running={int(status.running)}"
        )
        return row

    def _registry_secret_in_use(self, registry: dict[str, Any], secret_ref: str) -> bool:
        target = str(secret_ref or "").strip()
        if not target:
            return False
        return any(str(row.get("secret_ref") or "").strip() == target for row in registry_mod.list_users(registry))

    def _delete_registry_secret_if_unused(self, registry: dict[str, Any], secret_ref: str) -> bool:
        ref = str(secret_ref or "").strip()
        if not ref or self._registry_secret_in_use(registry, ref):
            return False
        return self.secret_store.delete_secret(ref) is not None

    def _portable_profile_uses_isolated_runtime(self, profile_status: PortableProfileStatus | None) -> bool:
        if profile_status is None:
            return False
        return not bool(profile_status.profile.slot_number)

    def _portable_profile_runtime_root(self, profile_dir: Path) -> Path:
        return profile_dir / "runtime"

    def _portable_profile_launch_workdir(self, profile_dir: Path) -> Path:
        return self._portable_profile_runtime_root(profile_dir) / "launch_workdir"

    def _portable_profile_launch_tdata(self, profile_dir: Path) -> Path:
        return self._portable_profile_launch_workdir(profile_dir) / "tdata"

    def _portable_profile_helper_workdir(self, profile_dir: Path) -> Path:
        return self._portable_profile_runtime_root(profile_dir) / "helper_workdir"

    def _portable_profile_helper_tdata(self, profile_dir: Path) -> Path:
        return self._portable_profile_helper_workdir(profile_dir) / "tdata"

    def _portable_profile_clone_state_path(self, profile_dir: Path) -> Path:
        return self._portable_profile_runtime_root(profile_dir) / "clone_state.json"

    def _write_portable_profile_runtime_metadata(
        self,
        profile_dir: Path,
        **updates: str,
    ) -> None:
        metadata_path = profile_dir / "portable-profile.json"
        payload = _read_json_file(metadata_path)
        if not payload:
            return
        runtime = payload.get("runtime") if isinstance(payload.get("runtime"), dict) else {}
        if not isinstance(runtime, dict):
            runtime = {}
        for key, value in updates.items():
            runtime[key] = value
        payload["runtime"] = runtime
        payload["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        _write_json_file(metadata_path, payload)

    def _write_portable_profile_clone_state(self, profile_dir: Path, payload: dict[str, Any]) -> None:
        runtime_root = self._portable_profile_runtime_root(profile_dir)
        runtime_root.mkdir(parents=True, exist_ok=True)
        _chmod_best_effort(runtime_root, 0o700)
        _write_json_file(self._portable_profile_clone_state_path(profile_dir), payload)

    def _sync_isolated_portable_helper_clone(
        self,
        profile_status: PortableProfileStatus,
        *,
        prefer_launch_clone: bool,
    ) -> None:
        profile_dir = profile_status.profile_dir
        source_tdata = profile_status.profile.tdata_dir
        if not _tdata_dir_looks_valid(source_tdata):
            raise RuntimeError("Канонический TelegramForcePortable/tdata больше не читается.")
        launch_tdata = self._portable_profile_launch_tdata(profile_dir)
        helper_tdata = self._portable_profile_helper_tdata(profile_dir)
        helper_workdir = self._portable_profile_helper_workdir(profile_dir)
        helper_workdir.mkdir(parents=True, exist_ok=True)
        _chmod_best_effort(helper_workdir, 0o700)
        source_kind = "source_tdata"
        source_dir = source_tdata
        if prefer_launch_clone and _tdata_dir_looks_valid(launch_tdata):
            source_kind = "launch_workdir"
            source_dir = launch_tdata
        _replace_tree(source_dir, helper_tdata)
        synced_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        payload = {
            "profile_dir": str(profile_dir),
            "source_tdata": str(source_tdata),
            "source_signature": _portable_runtime_signature_from_tdata(source_tdata),
            "launch_workdir": str(self._portable_profile_launch_workdir(profile_dir)),
            "launch_tdata": str(launch_tdata),
            "launch_signature": _portable_runtime_signature_from_tdata(launch_tdata) if _tdata_dir_looks_valid(launch_tdata) else "",
            "helper_workdir": str(helper_workdir),
            "helper_tdata": str(helper_tdata),
            "helper_signature": _portable_runtime_signature_from_tdata(helper_tdata),
            "helper_source": source_kind,
            "helper_synced_at": synced_at,
        }
        self._write_portable_profile_clone_state(profile_dir, payload)
        self._write_portable_profile_runtime_metadata(
            profile_dir,
            launch_workdir=str(self._portable_profile_launch_workdir(profile_dir)),
            helper_workdir=str(helper_workdir),
            helper_source=source_kind,
            helper_last_sync_at=synced_at,
        )

    def _ensure_isolated_portable_helper_clone_seed(self, profile_status: PortableProfileStatus) -> None:
        if not self._portable_profile_uses_isolated_runtime(profile_status):
            return
        helper_tdata = self._portable_profile_helper_tdata(profile_status.profile_dir)
        if _tdata_dir_looks_valid(helper_tdata):
            return
        self._sync_isolated_portable_helper_clone(profile_status, prefer_launch_clone=False)

    def _prepare_isolated_portable_launch_clone(self, profile_status: PortableProfileStatus) -> Path:
        profile_dir = profile_status.profile_dir
        source_tdata = profile_status.profile.tdata_dir
        if not _tdata_dir_looks_valid(source_tdata):
            raise RuntimeError("Не найден канонический TelegramForcePortable/tdata для запуска профиля.")
        launch_workdir = self._portable_profile_launch_workdir(profile_dir)
        launch_tdata = self._portable_profile_launch_tdata(profile_dir)
        source_signature = _portable_runtime_signature_from_tdata(source_tdata)
        launch_signature = _portable_runtime_signature_from_tdata(launch_tdata) if _tdata_dir_looks_valid(launch_tdata) else ""
        if source_signature != launch_signature:
            launch_workdir.mkdir(parents=True, exist_ok=True)
            _chmod_best_effort(launch_workdir, 0o700)
            _replace_tree(source_tdata, launch_tdata)
        self._write_portable_profile_runtime_metadata(
            profile_dir,
            launch_workdir=str(launch_workdir),
        )
        return launch_workdir

    def _isolated_portable_runtime_state(
        self,
        profile_status: PortableProfileStatus,
        *,
        binary_path: Path | None,
    ) -> PortableRuntimeState:
        profile_dir = profile_status.profile_dir
        source_tdata = profile_status.profile.tdata_dir
        launch_workdir = self._portable_profile_launch_workdir(profile_dir)
        launch_tdata = self._portable_profile_launch_tdata(profile_dir)
        helper_workdir = self._portable_profile_helper_workdir(profile_dir)
        helper_tdata = self._portable_profile_helper_tdata(profile_dir)
        clone_state = _read_json_file(self._portable_profile_clone_state_path(profile_dir))
        source_signature = _portable_runtime_signature_from_tdata(source_tdata) if _tdata_dir_looks_valid(source_tdata) else ""
        launch_exists = _tdata_dir_looks_valid(launch_tdata)
        helper_exists = _tdata_dir_looks_valid(helper_tdata)
        launch_signature = _portable_runtime_signature_from_tdata(launch_tdata) if launch_exists else ""
        helper_signature = _portable_runtime_signature_from_tdata(helper_tdata) if helper_exists else ""
        helper_source = str(clone_state.get("helper_source") or "").strip()
        last_sync_at = str(clone_state.get("helper_synced_at") or "").strip()
        helper_matches_launch = bool(launch_exists and helper_exists and helper_signature and helper_signature == launch_signature)
        helper_matches_source = bool(helper_exists and helper_signature and helper_signature == source_signature)
        if not helper_exists:
            state_value = "sync_required"
            detail_value = "Helper-копия ещё не собрана. Закройте профиль и нажмите 'Обновить статус'."
            ready_for_export = False
            needs_rebuild = True
        elif profile_status.running and launch_exists and not helper_matches_launch:
            state_value = "stale"
            detail_value = (
                "Профиль запущен через isolated launch clone. Helper использует последнюю good copy; "
                "после закрытия Telegram нажмите 'Обновить статус' для sync."
            )
            ready_for_export = True
            needs_rebuild = True
        elif profile_status.running:
            state_value = "stale"
            detail_value = (
                "Профиль сейчас запущен. Helper-копия сохранена отдельно, но новый sync разрешён только "
                "после закрытия Telegram и кнопки 'Обновить статус'."
            )
            ready_for_export = True
            needs_rebuild = True
        elif launch_exists and not helper_matches_launch:
            state_value = "sync_required"
            detail_value = "Launch clone остановлена и изменилась. Нажмите 'Обновить статус', чтобы синхронизировать helper-копию."
            ready_for_export = False
            needs_rebuild = True
        elif launch_exists and not launch_signature:
            state_value = "sync_required"
            detail_value = "Launch clone не читается. Пересоберите helper-копию через 'Обновить статус'."
            ready_for_export = False
            needs_rebuild = True
        elif not launch_exists and not helper_matches_source:
            state_value = "sync_required"
            detail_value = "Helper-копия отстаёт от канонического tdata. Нажмите 'Обновить статус' для пересборки."
            ready_for_export = False
            needs_rebuild = True
        elif binary_path is None:
            state_value = "binary_missing"
            detail_value = "Helper-копия готова для helper/export, но binary Telegram не найден."
            ready_for_export = True
            needs_rebuild = False
        else:
            state_value = "ready"
            detail_value = "Helper-копия готова для export; launch работает через отдельный runtime clone."
            ready_for_export = True
            needs_rebuild = False
        return PortableRuntimeState(
            slot_number=profile_status.profile.slot_number,
            state=state_value,
            detail=detail_value,
            source_path=profile_status.profile.source_path or profile_status.profile.profile_dir,
            source_kind=profile_status.profile.source_kind or "profile",
            runtime_dir=helper_tdata,
            tdata_dir=helper_tdata,
            binary_path=binary_path,
            source_signature=source_signature,
            ready_for_export=ready_for_export,
            needs_rebuild=needs_rebuild,
            authorized=False,
            launch_dir=launch_workdir,
            helper_dir=helper_workdir,
            helper_source=helper_source,
            last_sync_at=last_sync_at,
        )

    def inspect_portable_source(self, account: AccountOption | None) -> PortableSourceInfo:
        if account is None:
            return PortableSourceInfo(slot_number="", path=None, kind="missing", detail="Профиль ещё не выбран.")
        profile_status = self.portable_profile_for_account(account)
        if self._account_prefers_portable_profile(account, profile_status):
            detail = (
                f"Portable профиль: {profile_status.profile_name} | "
                f"{profile_status.profile_dir}"
            )
            return PortableSourceInfo(
                slot_number=profile_status.profile.slot_number,
                path=profile_status.profile.profile_dir,
                kind=profile_status.profile.source_kind or "profile",
                detail=detail,
                tdata_dir=profile_status.profile.tdata_dir,
            )
        slot_number = account.slot_number or _slot_number_from_source(account.profile_source)
        if not slot_number:
            return PortableSourceInfo(
                slot_number="",
                path=None,
                kind="missing",
                detail="Для portable tdata нужен slot-based профиль из telegram_workspace/accounts/<N>.",
            )
        return detect_slot_portable_source(slot_number=slot_number, profile_source=account.profile_source)

    def inspect_portable_runtime(
        self,
        account: AccountOption | None,
        *,
        probe_auth: bool = False,
        use_cache: bool = True,
    ) -> PortableRuntimeState:
        if account is None:
            return PortableRuntimeState(
                slot_number="",
                state="missing",
                detail="Профиль ещё не выбран.",
            )
        slot_number = account.slot_number or _slot_number_from_source(account.profile_source)
        cache_key = (account.key, bool(probe_auth))
        if use_cache:
            cached = self._portable_runtime_cache.get(cache_key)
            if cached is not None and (time.monotonic() - cached[0]) <= 3.0:
                return cached[1]

        profile_status = self.portable_profile_for_account(account)
        if self._account_prefers_portable_profile(account, profile_status):
            binary_path = profile_status.profile.binary_path or find_portable_telegram_binary(profile_status.profile.profile_dir)
            if self._portable_profile_uses_isolated_runtime(profile_status):
                state = self._isolated_portable_runtime_state(
                    profile_status,
                    binary_path=binary_path,
                )
            else:
                state_value = profile_status.state
                detail_value = profile_status.detail
                ready = profile_status.state in {"ready", "running", "binary_missing"}
                state = PortableRuntimeState(
                    slot_number=profile_status.profile.slot_number,
                    state=state_value,
                    detail=detail_value,
                    source_path=profile_status.profile.source_path or profile_status.profile.profile_dir,
                    source_kind=profile_status.profile.source_kind or "profile",
                    runtime_dir=profile_status.profile.tdata_dir,
                    tdata_dir=profile_status.profile.tdata_dir,
                    binary_path=binary_path,
                    source_signature="",
                    ready_for_export=ready,
                    needs_rebuild=False,
                    authorized=False,
                )
            if probe_auth and state.runtime_dir is not None and state.ready_for_export:
                try:
                    self._run_tdata_helper(
                        "list-chats",
                        tdata_dir=state.runtime_dir,
                        extra_args=["--limit", "1"],
                        timeout_sec=min(max(int(TDATA_LIST_TIMEOUT_SEC), 5), 12),
                    )
                except Exception as exc:
                    reason = _classify_failure_reason(str(exc))
                    detail = (
                        "Portable профиль найден, но helper не смог открыть сессию. "
                        "Откройте этот Telegram Desktop профиль и дождитесь полной загрузки."
                    )
                    if reason != "auth/session unreadable":
                        detail = f"{detail} {_compact_error_text(str(exc))}".strip()
                    state = PortableRuntimeState(
                        slot_number=state.slot_number,
                        state="unauthorized",
                        detail=detail,
                        source_path=state.source_path,
                        source_kind=state.source_kind,
                        runtime_dir=state.runtime_dir,
                        tdata_dir=state.tdata_dir,
                        binary_path=state.binary_path,
                        source_signature=state.source_signature,
                        ready_for_export=False,
                        needs_rebuild=state.needs_rebuild,
                        authorized=False,
                        launch_dir=state.launch_dir,
                        helper_dir=state.helper_dir,
                        helper_source=state.helper_source,
                        last_sync_at=state.last_sync_at,
                    )
                else:
                    state = PortableRuntimeState(
                        slot_number=state.slot_number,
                        state=state.state,
                        detail=state.detail,
                        source_path=state.source_path,
                        source_kind=state.source_kind,
                        runtime_dir=state.runtime_dir,
                        tdata_dir=state.tdata_dir,
                        binary_path=state.binary_path,
                        source_signature=state.source_signature,
                        ready_for_export=state.ready_for_export,
                        needs_rebuild=state.needs_rebuild,
                        authorized=True,
                        launch_dir=state.launch_dir,
                        helper_dir=state.helper_dir,
                        helper_source=state.helper_source,
                        last_sync_at=state.last_sync_at,
                    )
            now = time.monotonic()
            self._portable_runtime_cache[cache_key] = (now, state)
            if probe_auth:
                self._portable_runtime_cache[(account.key, False)] = (now, state)
            return state

        source_info = self.inspect_portable_source(account)
        profile_dir, availability_state, availability_detail = self.resolve_profile_dir_safe(account.profile_source)
        if profile_dir is None:
            state = PortableRuntimeState(
                slot_number=slot_number,
                state="missing",
                detail=availability_detail or "Путь выбранного профиля больше не доступен.",
                source_path=Path(account.profile_source).expanduser() if account.profile_source else None,
                source_kind=source_info.kind,
                ready_for_export=False,
                authorized=False,
            )
            now = time.monotonic()
            self._portable_runtime_cache[cache_key] = (now, state)
            if probe_auth:
                self._portable_runtime_cache[(account.key, False)] = (now, state)
            return state
        binary_path = find_portable_telegram_binary(profile_dir)
        state = _portable_runtime_state_from_workspace(
            slot_number=slot_number,
            source_info=source_info,
            binary_path=binary_path,
        )
        if probe_auth and state.runtime_dir is not None and state.ready_for_export:
            try:
                self._run_tdata_helper(
                    "list-chats",
                    tdata_dir=state.runtime_dir,
                    extra_args=["--limit", "1"],
                    timeout_sec=min(max(int(TDATA_LIST_TIMEOUT_SEC), 5), 12),
                )
            except Exception as exc:
                reason = _classify_failure_reason(str(exc))
                detail = (
                    "Portable runtime clone не открывается helper'ом. "
                    "Откройте portable Telegram и дождитесь полной загрузки сессии."
                )
                if reason != "auth/session unreadable":
                    detail = f"{detail} {_compact_error_text(str(exc))}".strip()
                state = PortableRuntimeState(
                    slot_number=state.slot_number,
                    state="unauthorized",
                    detail=detail,
                    source_path=state.source_path,
                    source_kind=state.source_kind,
                    runtime_dir=state.runtime_dir,
                    tdata_dir=state.tdata_dir,
                    binary_path=state.binary_path,
                    source_signature=state.source_signature,
                    ready_for_export=False,
                    needs_rebuild=state.needs_rebuild,
                    authorized=False,
                )
            else:
                if state.state == "binary_missing":
                    state = PortableRuntimeState(
                        slot_number=state.slot_number,
                        state=state.state,
                        detail=state.detail,
                        source_path=state.source_path,
                        source_kind=state.source_kind,
                        runtime_dir=state.runtime_dir,
                        tdata_dir=state.tdata_dir,
                        binary_path=state.binary_path,
                        source_signature=state.source_signature,
                        ready_for_export=True,
                        needs_rebuild=state.needs_rebuild,
                        authorized=True,
                    )
                else:
                    state = PortableRuntimeState(
                        slot_number=state.slot_number,
                        state="ready",
                        detail="Portable runtime clone готова для helper/export.",
                        source_path=state.source_path,
                        source_kind=state.source_kind,
                        runtime_dir=state.runtime_dir,
                        tdata_dir=state.tdata_dir,
                        binary_path=state.binary_path,
                        source_signature=state.source_signature,
                        ready_for_export=True,
                        needs_rebuild=state.needs_rebuild,
                        authorized=True,
                    )
        now = time.monotonic()
        self._portable_runtime_cache[cache_key] = (now, state)
        if probe_auth:
            self._portable_runtime_cache[(account.key, False)] = (now, state)
        return state

    def clear_portable_runtime_cache(self, account: AccountOption | None = None) -> None:
        if account is None:
            self._portable_runtime_cache.clear()
            return
        keys = [key for key in self._portable_runtime_cache if key[0] == account.key]
        for key in keys:
            self._portable_runtime_cache.pop(key, None)

    def prepare_portable_runtime(self, account: AccountOption, *, force: bool = False) -> PortableRuntimeState:
        profile_status = self.portable_profile_for_account(account)
        if self._account_prefers_portable_profile(account, profile_status):
            if profile_status is None:
                raise RuntimeError("Portable профиль не найден.")
            if self._portable_profile_uses_isolated_runtime(profile_status):
                if force:
                    if profile_status.running:
                        helper_tdata = self._portable_profile_helper_tdata(profile_status.profile_dir)
                        if _tdata_dir_looks_valid(helper_tdata):
                            self.clear_portable_runtime_cache(account)
                            return self.inspect_portable_runtime(account, probe_auth=True, use_cache=False)
                        raise RuntimeError(
                            "Профиль сейчас запущен; sync helper-копии запрещён до закрытия Telegram. "
                            "Закройте профиль и повторите 'Обновить статус'."
                        )
                    self._sync_isolated_portable_helper_clone(profile_status, prefer_launch_clone=True)
            self.clear_portable_runtime_cache(account)
            return self.inspect_portable_runtime(account, probe_auth=True, use_cache=False)
        slot_number = account.slot_number or _slot_number_from_source(account.profile_source)
        if not slot_number:
            raise RuntimeError("Portable tdata доступен только для slot-based профилей.")
        source_info = self.inspect_portable_source(account)
        if source_info.path is None or (source_info.kind != "zip" and source_info.tdata_dir is None):
            raise RuntimeError(source_info.detail or "Для этого слота нет portable tdata source.")
        runtime_state = self.inspect_portable_runtime(account, probe_auth=False, use_cache=False)
        if not force and runtime_state.state in {"ready", "binary_missing"} and not runtime_state.needs_rebuild:
            _sync_portable_runtime_alias(slot_number)
            return self.inspect_portable_runtime(account, probe_auth=True, use_cache=False)

        runtime_root = _slot_runtime_root(slot_number)
        runtime_root.mkdir(parents=True, exist_ok=True)
        _chmod_best_effort(runtime_root, 0o700)
        target_dir = runtime_root / "portable_tdata"
        temp_dir = runtime_root / f".portable_tdata_tmp_{_utc_timestamp()}"
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        if source_info.kind == "zip":
            _extract_portable_tdata_zip(source_info.path, temp_dir)
        else:
            shutil.copytree(source_info.tdata_dir, temp_dir)
        if target_dir.exists():
            shutil.rmtree(target_dir)
        temp_dir.replace(target_dir)
        _chmod_best_effort(target_dir, 0o700)
        _sync_portable_runtime_alias(slot_number)
        metadata = {
            "slot_number": slot_number,
            "source_path": str(source_info.path),
            "source_kind": source_info.kind,
            "source_signature": _portable_source_signature(source_info),
            "runtime_dir": str(target_dir),
            "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }
        self.secret_store.save_registry_file(
            _slot_portable_state_path(slot_number),
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        )
        self.clear_portable_runtime_cache(account)
        result = self.inspect_portable_runtime(account, probe_auth=True, use_cache=False)
        self._log_action(
            f"portable_runtime_prepared slot={slot_number} state={result.state} source={source_info.kind}:{source_info.path}"
        )
        return result

    def refresh_portable_runtime(self, account: AccountOption) -> PortableRuntimeState:
        return self.prepare_portable_runtime(account, force=True)

    def launch_portable_telegram(self, account: AccountOption) -> str:
        profile_status = self.portable_profile_for_account(account)
        if self._account_prefers_portable_profile(account, profile_status):
            if profile_status is None:
                raise RuntimeError("Portable профиль не найден.")
            latest, already_running = self.launch_portable_profile_dir(str(profile_status.profile_dir))
            label = portable_profile_label(latest)
            if already_running:
                self._log_action(f"portable_profile_already_running profile={latest.profile_dir}")
                return f"Portable профиль уже запущен: {label}."
            return (
                f"Portable профиль запущен: {label}. "
                f"Profile dir: {latest.profile_dir}"
            )
        state = self.prepare_portable_runtime(account, force=False)
        if state.binary_path is None:
            raise RuntimeError(
                "Portable runtime clone подготовлена, но бинарник Telegram не найден. "
                "Проверьте portable-profile.json или путь в ~/Загрузки/Telegram Desktop."
            )
        if state.runtime_dir is None:
            raise RuntimeError("Portable runtime clone ещё не подготовлена.")
        binary_path = state.binary_path
        _sync_portable_runtime_alias(state.slot_number)
        workdir = state.runtime_dir.parent
        try:
            mode = binary_path.stat().st_mode
            if mode & 0o111 == 0:
                binary_path.chmod(mode | 0o755)
        except OSError as exc:
            raise RuntimeError(f"Не удалось подготовить portable binary: {exc}") from exc
        try:
            subprocess.Popen(
                [str(binary_path), "-workdir", str(workdir)],
                cwd=str(binary_path.parent),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            raise RuntimeError(f"Не удалось запустить portable Telegram: {exc}") from exc
        self._log_action(f"portable_launch binary={binary_path} workdir={workdir}")
        return f"Portable Telegram запущен из {binary_path} с workdir {workdir}."

    def import_portable_profile(
        self,
        source_path: str,
        *,
        profile_name: str = "",
        account_username: str = "",
        account_label: str = "",
        launch: bool = False,
        set_default: bool = False,
    ) -> PortableProfileStatus:
        status = self.portable_profiles.import_zip(
            source_path,
            profile_name=profile_name,
            account_username=account_username,
            account_label=account_label,
            launch=False,
        )
        self._ensure_isolated_portable_helper_clone_seed(status)
        self.ensure_account_for_portable_profile(status, fallback_token=DEFAULT_TOKEN, set_default=set_default)
        self.clear_portable_runtime_cache()
        if launch:
            status, _already_running = self.launch_portable_profile_dir(str(status.profile_dir))
        return status

    def adopt_portable_profile(
        self,
        profile_path: str,
        *,
        profile_name: str = "",
        account_username: str = "",
        account_label: str = "",
    ) -> PortableProfileStatus:
        status = self.portable_profiles.adopt_profile(
            profile_path,
            profile_name=profile_name,
            account_username=account_username,
            account_label=account_label,
        )
        self._ensure_isolated_portable_helper_clone_seed(status)
        self.ensure_account_for_portable_profile(status, fallback_token=DEFAULT_TOKEN, set_default=False)
        self.clear_portable_runtime_cache()
        return status

    def profile_status(self, profile_dir: str) -> PortableProfileStatus | None:
        return self.portable_profiles.status(profile_dir)

    def launch_portable_profile_dir(self, profile_dir: str) -> tuple[PortableProfileStatus, bool]:
        current = self.portable_profiles.status(profile_dir)
        if current is None:
            raise RuntimeError(f"Portable профиль не найден: {profile_dir}")
        workdir_override: Path | None = None
        if self._portable_profile_uses_isolated_runtime(current):
            workdir_override = self._prepare_isolated_portable_launch_clone(current)
        status, already_running = self.portable_profiles.launch_profile(profile_dir, workdir_override=workdir_override)
        self.ensure_account_for_portable_profile(status, fallback_token=DEFAULT_TOKEN, set_default=False)
        self.clear_portable_runtime_cache()
        return (status, already_running)

    def refresh_portable_profile_dir(self, profile_dir: str) -> PortableRuntimeState:
        status = self.portable_profiles.status(profile_dir)
        if status is None:
            return PortableRuntimeState(
                slot_number="",
                state="missing",
                detail="Portable профиль больше не найден.",
                ready_for_export=False,
                authorized=False,
            )
        if self._portable_profile_uses_isolated_runtime(status):
            if status.running:
                helper_tdata = self._portable_profile_helper_tdata(status.profile_dir)
                if not _tdata_dir_looks_valid(helper_tdata):
                    raise RuntimeError(
                        "Профиль сейчас запущен; helper-копия ещё не собрана. "
                        "Закройте Telegram и повторите 'Обновить статус'."
                    )
            else:
                self._sync_isolated_portable_helper_clone(status, prefer_launch_clone=True)
            self.clear_portable_runtime_cache()
            account = next(
                (item for item in self.load_accounts() if _normalize_path_key(item.profile_source) == _normalize_path_key(str(status.profile_dir))),
                None,
            )
            if account is not None:
                return self.inspect_portable_runtime(account, probe_auth=True, use_cache=False)
            refreshed = self.portable_profiles.status(profile_dir) or status
            return self._isolated_portable_runtime_state(
                refreshed,
                binary_path=refreshed.profile.binary_path or find_portable_telegram_binary(refreshed.profile.profile_dir),
            )
        return PortableRuntimeState(
            slot_number=status.profile.slot_number,
            state=status.state,
            detail=status.detail,
            source_path=status.profile.source_path or status.profile.profile_dir,
            source_kind=status.profile.source_kind or "profile",
            runtime_dir=status.profile.tdata_dir,
            tdata_dir=status.profile.tdata_dir,
            binary_path=status.profile.binary_path,
            ready_for_export=status.state in {"ready", "running", "binary_missing"},
            authorized=False,
        )

    def remove_portable_profile(self, profile_dir: str) -> PortableProfileRemovalResult:
        registry = registry_mod.load_registry(USER_REGISTRY_PATH)
        existing = registry_mod.find_user_by_profile(registry, profile=profile_dir)
        result = self.portable_profiles.remove_profile(profile_dir)
        next_registry = registry_mod.remove_user_by_profile(registry, profile=profile_dir)
        registry_mod.save_registry(USER_REGISTRY_PATH, next_registry)
        secret_removed = self._delete_registry_secret_if_unused(next_registry, str(existing.get("secret_ref") or "").strip())
        self.clear_portable_runtime_cache()
        if existing:
            self._security_info_cache.pop(f"registry:{str(existing.get('name') or '').strip() or _normalize_path_key(profile_dir)}", None)
        self._log_action(
            f"portable_profile_removed profile={profile_dir} kind={result.profile_kind} preserved={int(result.external_data_preserved)}"
        )
        return PortableProfileRemovalResult(
            profile_dir=result.profile_dir,
            profile_label=result.profile_label,
            profile_kind=result.profile_kind,
            removed_paths=result.removed_paths,
            external_data_preserved=result.external_data_preserved,
            secret_removed=secret_removed,
        )

    def import_portable_source(self, source_path: str, *, preferred_slot: str = "") -> dict[str, str]:
        raw_source = Path(str(source_path or "").strip()).expanduser()
        if not raw_source.exists():
            raise RuntimeError(f"Portable source не найден: {raw_source}")
        slot_number = _resolve_import_slot(preferred_slot)
        slot_root = layout_mod.slot_dir(TELEGRAM_WORKSPACE_ROOT, slot_number)
        profile_dir = slot_root / "profile"
        imports_dir = slot_root / "imports"
        imports_dir.mkdir(parents=True, exist_ok=True)
        source_info = detect_import_payload(raw_source)
        if source_info.path is None:
            raise RuntimeError(source_info.detail or "Не удалось распознать portable tdata source.")

        if source_info.kind == "zip":
            for archive in imports_dir.glob("*.zip"):
                try:
                    archive.unlink()
                except OSError:
                    continue
            target = imports_dir / source_info.path.name
            shutil.copy2(source_info.path, target)
            preferred_profile_source = str(profile_dir if _directory_has_payload(profile_dir) else target)
            imported_source = target
        elif source_info.kind == "tdata":
            target = profile_dir / "tdata"
            _replace_tree(source_info.path, target)
            preferred_profile_source = str(profile_dir)
            imported_source = target
        else:
            parent_target = profile_dir / source_info.path.name
            if source_info.tdata_dir == source_info.path / "tdata":
                _replace_tree(source_info.path, parent_target)
                imported_source = parent_target
            else:
                target = profile_dir / "tdata"
                _replace_tree(source_info.tdata_dir, target)
                imported_source = target
            preferred_profile_source = str(profile_dir)
        self.clear_portable_runtime_cache()
        self._log_action(
            f"portable_source_imported slot={slot_number} kind={source_info.kind} source={source_info.path} target={imported_source}"
        )
        return {
            "slot_number": str(slot_number),
            "portable_source": str(imported_source),
            "portable_kind": source_info.kind,
            "preferred_profile_source": preferred_profile_source,
        }

    def probe_bridge_readiness(self, account: AccountOption) -> FallbackReadiness:
        profile_dir = resolve_profile_dir(account.profile_source)
        hub_state = self._inspect_hub_token_state(account.token)
        hub_status = str(hub_state.get("state") or "").strip()
        if hub_status == "foreign_mismatch":
            return FallbackReadiness(
                surface_key="bridge",
                surface_label="Telegram Web bridge",
                surface_badge="Fallback Bridge",
                state="foreign_hub",
                detail=str(hub_state.get("detail") or "На :8765 уже живёт внешний hub/process с другим токеном."),
                action_label="Повторить проверку",
            )
        if hub_status == "owned_mismatch":
            return FallbackReadiness(
                surface_key="bridge",
                surface_label="Telegram Web bridge",
                surface_badge="Fallback Bridge",
                state="hub_mismatch",
                detail=str(hub_state.get("detail") or "Hub уже запущен этим GUI с другим токеном."),
                action_label="Повторить проверку",
            )
        try:
            target = self._resolve_best_client(account.token, known_client_ids=set(), require_online=True)
        except Exception as exc:
            return FallbackReadiness(
                surface_key="bridge",
                surface_label="Telegram Web bridge",
                surface_badge="Fallback Bridge",
                state="client_offline",
                detail=_compact_error_text(str(exc)) or "Bridge-клиент сейчас недоступен.",
                action_label="Повторить проверку",
            )
        if target is not None:
            return FallbackReadiness(
                surface_key="bridge",
                surface_label="Telegram Web bridge",
                surface_badge="Fallback Bridge",
                state="ready",
                detail=f"Bridge-клиент готов: {target.client_id} | {target.tab_title or 'Telegram'}",
                target=target,
                action_label="Повторить проверку",
            )
        try:
            browser = _detect_browser_binary()
        except Exception as exc:
            return FallbackReadiness(
                surface_key="bridge",
                surface_label="Telegram Web bridge",
                surface_badge="Fallback Bridge",
                state="browser_launch_failed",
                detail=_compact_error_text(str(exc)) or "Не найден совместимый браузер для bridge-profile.",
                action_label="Повторить проверку",
            )
        if Path(browser).name == "google-chrome" and not _profile_has_site_control_extension(profile_dir):
            return FallbackReadiness(
                surface_key="bridge",
                surface_label="Telegram Web bridge",
                surface_badge="Fallback Bridge",
                state="extension_setup_required",
                detail=_bridge_manual_setup_detail(profile_dir),
                action_label="Подготовить bridge profile",
            )
        return FallbackReadiness(
            surface_key="bridge",
            surface_label="Telegram Web bridge",
            surface_badge="Fallback Bridge",
            state="client_offline",
            detail=(
                "Bridge-клиент ещё не подключён. Откройте dedicated bridge profile и дождитесь подключения расширения."
            ),
            action_label="Подготовить bridge profile",
        )

    def prepare_bridge_surface(self, account: AccountOption) -> FallbackReadiness:
        readiness = self.probe_bridge_readiness(account)
        if readiness.state in {"ready", "foreign_hub", "hub_mismatch"}:
            self._cache_fallback_readiness(account, readiness)
            self._log_action(f"fallback_prepare surface=bridge state={readiness.state} detail={_compact_error_text(readiness.detail)}")
            return readiness
        profile_dir = resolve_profile_dir(account.profile_source)
        env = os.environ.copy()
        env["SITECTL_TOKEN"] = account.token
        env["SITECTL_BROWSER_PROFILE"] = str(profile_dir)
        env["SITECTL_START_URL"] = TELEGRAM_WEB_URL
        try:
            run = subprocess.run(
                ["bash", str(START_BROWSER_SCRIPT), "--profile", str(profile_dir), "--url", TELEGRAM_WEB_URL],
                cwd=str(REPO_ROOT),
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=45,
            )
        except Exception as exc:
            readiness = FallbackReadiness(
                surface_key="bridge",
                surface_label="Telegram Web bridge",
                surface_badge="Fallback Bridge",
                state="browser_launch_failed",
                detail=_compact_error_text(str(exc)) or "Не удалось запустить bridge profile.",
                action_label="Подготовить bridge profile",
            )
            self._cache_fallback_readiness(account, readiness)
            self._log_action(f"fallback_prepare surface=bridge state={readiness.state} detail={_compact_error_text(readiness.detail)}")
            return readiness
        launch_output = _mask_known_secrets((run.stdout or "") + "\n" + (run.stderr or ""), [account.token, DEFAULT_TOKEN]).strip()
        if launch_output:
            self._log_action(f"fallback_prepare surface=bridge launcher={_compact_error_text(launch_output)}")
        if run.returncode != 0:
            readiness = FallbackReadiness(
                surface_key="bridge",
                surface_label="Telegram Web bridge",
                surface_badge="Fallback Bridge",
                state="browser_launch_failed",
                detail=_compact_error_text(launch_output) or "Не удалось подготовить bridge profile.",
                action_label="Подготовить bridge profile",
            )
            self._cache_fallback_readiness(account, readiness)
            self._log_action(f"fallback_prepare surface=bridge state={readiness.state} detail={_compact_error_text(readiness.detail)}")
            return readiness
        deadline = time.time() + 12
        latest = self.probe_bridge_readiness(account)
        while time.time() < deadline and latest.state == "client_offline":
            time.sleep(0.75)
            latest = self.probe_bridge_readiness(account)
        self._cache_fallback_readiness(account, latest)
        self._log_action(f"fallback_prepare surface=bridge state={latest.state} detail={_compact_error_text(latest.detail)}")
        return latest

    def probe_cdp_readiness(self, account: AccountOption, *, deep: bool = False) -> FallbackReadiness:
        profile_dir = resolve_profile_dir(account.profile_source)
        try:
            target = self._ensure_cdp_target(profile_dir, launch_browser=False)
        except Exception as exc:
            return FallbackReadiness(
                surface_key="cdp",
                surface_label="Chrome profile direct",
                surface_badge="Fallback CDP",
                state="browser_launch_failed",
                detail=_compact_error_text(str(exc)) or "CDP profile сейчас не готов.",
                action_label="Повторить проверку",
            )
        if target is None:
            try:
                _detect_browser_binary()
            except Exception as exc:
                return FallbackReadiness(
                    surface_key="cdp",
                    surface_label="Chrome profile direct",
                    surface_badge="Fallback CDP",
                    state="browser_launch_failed",
                    detail=_compact_error_text(str(exc)) or "Не найден браузер для CDP профиля.",
                    action_label="Повторить проверку",
                )
            return FallbackReadiness(
                surface_key="cdp",
                surface_label="Chrome profile direct",
                surface_badge="Fallback CDP",
                state="client_offline",
                detail="CDP browser profile ещё не запущен. Нажмите 'Подключить Telegram' или повторите проверку после запуска.",
                action_label="Повторить проверку",
            )
        return self._probe_cdp_target(target, deep=deep)

    def prepare_cdp_surface(self, account: AccountOption) -> FallbackReadiness:
        profile_dir = resolve_profile_dir(account.profile_source)
        try:
            target = self._ensure_cdp_target(profile_dir, launch_browser=True)
        except Exception as exc:
            readiness = FallbackReadiness(
                surface_key="cdp",
                surface_label="Chrome profile direct",
                surface_badge="Fallback CDP",
                state="browser_launch_failed",
                detail=_compact_error_text(str(exc)) or "Не удалось поднять CDP browser profile.",
                action_label="Повторить проверку",
            )
            self._cache_fallback_readiness(account, readiness)
            self._log_action(f"fallback_prepare surface=cdp state={readiness.state} detail={_compact_error_text(readiness.detail)}")
            return readiness
        readiness = self._probe_cdp_target(target, deep=True)
        self._cache_fallback_readiness(account, readiness)
        self._log_action(f"fallback_prepare surface=cdp state={readiness.state} detail={_compact_error_text(readiness.detail)}")
        return readiness

    def clear_fallback_readiness(self, account: AccountOption | None) -> None:
        if account is None:
            return
        profile_key = _normalize_path_key(account.profile_source)
        for surface_key in ("bridge", "cdp"):
            self._fallback_readiness_cache.pop((surface_key, profile_key), None)

    def _cache_fallback_readiness(self, account: AccountOption, readiness: FallbackReadiness) -> None:
        profile_key = _normalize_path_key(account.profile_source)
        self._fallback_readiness_cache[(readiness.surface_key, profile_key)] = readiness

    def _cached_fallback_readiness(self, account: AccountOption, surface_key: str) -> FallbackReadiness | None:
        return self._fallback_readiness_cache.get((surface_key, _normalize_path_key(account.profile_source)))

    def _probe_cdp_target(self, target: BrowserTarget, *, deep: bool) -> FallbackReadiness:
        port = self._cdp_port_from_target(target)
        if port is None:
            return FallbackReadiness(
                surface_key="cdp",
                surface_label="Chrome profile direct",
                surface_badge="Fallback CDP",
                state="client_offline",
                detail="CDP target ещё не готов.",
                action_label="Повторить проверку",
            )
        try:
            if deep:
                payload = self._run_cdp_helper(
                    "list-chats",
                    port=port,
                    timeout_sec=10,
                    extra_args=["--url", TELEGRAM_WEB_URL, "--timeout-ms", "8000"],
                )
            else:
                payload = self._run_cdp_helper(
                    "status",
                    port=port,
                    timeout_sec=5,
                    extra_args=["--timeout-ms", "2500"],
                )
        except Exception as exc:
            text = str(exc or "").strip()
            lower = text.lower()
            state = (
                "telegram_auth_required"
                if "не залогинен" in lower or "auth_required" in lower or "not logged into telegram" in lower
                else "client_offline"
            )
            return FallbackReadiness(
                surface_key="cdp",
                surface_label="Chrome profile direct",
                surface_badge="Fallback CDP",
                state=state,
                detail=_compact_error_text(text) or "CDP profile ещё не готов.",
                target=target,
                action_label="Повторить проверку",
            )
        if deep and payload.get("auth_required"):
            return FallbackReadiness(
                surface_key="cdp",
                surface_label="Chrome profile direct",
                surface_badge="Fallback CDP",
                state="telegram_auth_required",
                detail="В dedicated CDP profile Telegram ещё не залогинен. Выполните вход и повторите проверку.",
                target=target,
                action_label="Повторить проверку",
            )
        if deep:
            title = self._clean_tab_title(str(payload.get("current_title") or target.tab_title or "Telegram"))
            url = str(payload.get("current_url") or target.tab_url or TELEGRAM_WEB_URL)
        else:
            target_meta = payload.get("telegram_target") or {}
            title = self._clean_tab_title(str(target_meta.get("title") or target.tab_title or "Telegram"))
            url = str(target_meta.get("url") or target.tab_url or TELEGRAM_WEB_URL)
        refreshed = BrowserTarget(client_id=target.client_id, tab_id=target.tab_id, tab_title=title, tab_url=url)
        return FallbackReadiness(
            surface_key="cdp",
            surface_label="Chrome profile direct",
            surface_badge="Fallback CDP",
            state="ready",
            detail=f"CDP profile готов: {refreshed.client_id} | {refreshed.tab_title or 'Telegram'}",
            target=refreshed,
            action_label="Повторить проверку",
        )

    def save_secure_token(self, account: AccountOption, token: str) -> None:
        value = str(token or "").strip()
        if not value:
            raise ValueError("Введите token перед сохранением.")
        if value == DEFAULT_TOKEN:
            raise ValueError("Quickstart token нельзя сохранять как secure token.")
        registry = registry_mod.load_registry(USER_REGISTRY_PATH)
        existing = registry_mod.find_user_by_profile(registry, profile=account.profile_source)
        secret_ref = str(existing.get("secret_ref") or account.secret_ref or "").strip()
        next_registry = registry_mod.add_or_update_user_by_profile(
            registry,
            name=self._registry_user_name_for_account(account, existing=existing),
            token=value,
            profile=account.profile_source,
            secret_ref=secret_ref,
            set_default=not bool(registry_mod.list_users(registry)),
        )
        registry_mod.save_registry(USER_REGISTRY_PATH, next_registry)
        if account.slot_number:
            self.clear_slot_token_file(account.slot_number)
        self._log_action(
            f"secure_token_saved account={account.label} profile={account.profile_source} source=gui token_source=secret_ref"
        )

    def import_slot_token_into_registry(self, account: AccountOption) -> bool:
        slot_number = account.slot_number or _slot_number_from_source(account.profile_source)
        slot_token = _slot_token(slot_number)
        if not slot_number or not slot_token:
            return False
        registry = registry_mod.load_registry(USER_REGISTRY_PATH)
        existing = registry_mod.find_user_by_profile(registry, profile=account.profile_source)
        if str(existing.get("secret_ref") or "").strip():
            return False
        next_registry = registry_mod.add_or_update_user_by_profile(
            registry,
            name=self._registry_user_name_for_account(account, existing=existing),
            token=slot_token,
            profile=account.profile_source,
            secret_ref=str(existing.get("secret_ref") or "").strip(),
            set_default=not bool(registry_mod.list_users(registry)),
        )
        registry_mod.save_registry(USER_REGISTRY_PATH, next_registry)
        self.clear_slot_token_file(slot_number)
        self._log_action(f"slot_token_imported slot={slot_number} profile={account.profile_source}")
        return True

    def clear_slot_token_file(self, slot_number: str) -> None:
        if not slot_number:
            return
        token_path = TELEGRAM_WORKSPACE_ROOT / "accounts" / slot_number / "keys" / "api_token.txt"
        self.secret_store.save_registry_file(token_path, "")

    def restart_owned_hub_with_token(self, token: str) -> None:
        hub_state = self._inspect_hub_token_state(token)
        if str(hub_state.get("state") or "") != "owned_mismatch":
            raise RuntimeError("Перезапуск hub доступен только для runtime, который поднял этот GUI.")
        self._terminate_owned_runtime("hub")
        self._ensure_hub(token)
        self._log_action("hub_restarted_with_selected_token")

    def _registry_user_name_for_account(self, account: AccountOption, *, existing: dict[str, str] | None = None) -> str:
        existing_row = existing or {}
        name = str(existing_row.get("name") or "").strip()
        if name:
            return name
        for candidate in (account.name, account.label, _auto_profile_label(account.label, account.profile_source)):
            text = str(candidate or "").strip()
            if text:
                return text
        return "Telegram profile"

    def load_last_session(self) -> SessionResumeState | None:
        return self.run_history.load_last_session()

    def load_recent_runs(self, *, limit: int = 20) -> list[RunRecord]:
        return self.run_history.list_recent(limit=limit)

    def build_preflight(
        self,
        *,
        account: AccountOption | None,
        output_path: Path | None,
        preset_key: str,
        connected_target: BrowserTarget | None,
        deep: bool = False,
    ) -> PreflightInfo:
        preset_key, preset_label = self._preset_choice(preset_key)
        notes: list[str] = []
        security_info = self.inspect_account_security(account, deep=deep)
        tdata_ready = False
        helper_python = _selected_helper_python()
        helper_ready = bool(helper_python is not None and TDATA_HELPER_SCRIPT.exists())
        surface_key = "pending"
        surface_label = "Telegram pending"
        surface_badge = "Surface pending"
        surface_reason = "Профиль ещё не выбран."
        is_primary = False
        fallback_bridge: FallbackReadiness | None = None
        fallback_cdp: FallbackReadiness | None = None
        portable_source: PortableSourceInfo | None = None
        portable_runtime: PortableRuntimeState | None = None
        portable_profile: PortableProfileStatus | None = None
        resume_state = self.load_last_session()
        if account is not None:
            profile_dir, resolved_state, resolved_detail = self.resolve_profile_dir_safe(account.profile_source)
            availability_state = str(account.availability_state or "").strip() or "ready"
            availability_detail = str(account.availability_detail or "").strip()
            if resolved_state != "ready":
                availability_state = resolved_state
                if not availability_detail:
                    availability_detail = resolved_detail
            elif not availability_detail:
                availability_detail = resolved_detail
            portable_profile = self.portable_profile_for_account(account)
            if availability_state == "missing":
                slot_number = account.slot_number or _slot_number_from_source(account.profile_source)
                portable_source = PortableSourceInfo(
                    slot_number=slot_number,
                    path=None,
                    kind="missing",
                    detail=availability_detail or "Путь выбранного профиля больше не доступен.",
                )
                portable_runtime = PortableRuntimeState(
                    slot_number=slot_number,
                    state="missing",
                    detail=availability_detail or "Путь выбранного профиля больше не доступен.",
                    ready_for_export=False,
                    authorized=False,
                )
                if portable_profile is None and account.profile_source:
                    portable_profile = self._missing_portable_profile_status(
                        profile_dir=Path(account.profile_source).expanduser(),
                        label=account.portable_profile_label or account.label,
                        detail=availability_detail or "Путь выбранного профиля больше не доступен.",
                    )
                surface_key = "profile_missing"
                surface_label = "Telegram profile missing"
                surface_badge = "Profile missing"
                surface_reason = availability_detail or "Путь выбранного профиля больше не доступен."
                notes.append(surface_reason)
            else:
                portable_source = self.inspect_portable_source(account)
                portable_runtime = self.inspect_portable_runtime(
                    account,
                    probe_auth=bool(deep and helper_ready),
                    use_cache=not deep,
                )
                direct_tdata = resolve_tdata_dir(profile_dir) if profile_dir is not None else None
                if portable_source.path is not None:
                    tdata_ready = bool(helper_ready and portable_runtime.ready_for_export and portable_runtime.runtime_dir is not None)
                else:
                    tdata_ready = direct_tdata is not None and helper_ready
                if deep:
                    fallback_bridge = self.probe_bridge_readiness(account)
                    self._cache_fallback_readiness(account, fallback_bridge)
                    cached_cdp = self._cached_fallback_readiness(account, "cdp")
                    fallback_cdp = cached_cdp or self.probe_cdp_readiness(account)
                    if fallback_cdp is not None:
                        self._cache_fallback_readiness(account, fallback_cdp)
                else:
                    fallback_bridge = self._cached_fallback_readiness(account, "bridge") or self._pending_fallback_readiness("bridge")
                    fallback_cdp = self._cached_fallback_readiness(account, "cdp") or self._pending_fallback_readiness("cdp")
                if connected_target is not None:
                    adapter = self.adapter_for_target(connected_target)
                    surface_key = adapter.key
                    surface_label = adapter.label
                    surface_badge = adapter.badge
                    is_primary = adapter.primary
                    surface_reason = f"Подключено через {adapter.label}."
                elif portable_source is not None and portable_source.path is not None:
                    surface_key = "tdata"
                    surface_label = "Telegram Desktop tdata"
                    surface_badge = "Primary tdata"
                    is_primary = True
                    if tdata_ready:
                        surface_reason = portable_runtime.detail or "Portable runtime clone готова для tdata export."
                    else:
                        surface_reason = portable_runtime.detail or "Portable runtime clone требует подготовки или авторизации."
                elif tdata_ready:
                    surface_key = "tdata"
                    surface_label = "Telegram Desktop tdata"
                    surface_badge = "Primary tdata"
                    is_primary = True
                    surface_reason = "tdata primary surface доступен."
                else:
                    if fallback_bridge.state == "ready":
                        surface_key = fallback_bridge.surface_key
                        surface_label = fallback_bridge.surface_label
                        surface_badge = fallback_bridge.surface_badge
                        surface_reason = f"tdata недоступен; bridge ready. {fallback_bridge.detail}"
                    elif fallback_cdp.state == "ready":
                        surface_key = fallback_cdp.surface_key
                        surface_label = fallback_cdp.surface_label
                        surface_badge = fallback_cdp.surface_badge
                        surface_reason = (
                            f"tdata недоступен; bridge={fallback_bridge.state}. "
                            f"CDP ready. {fallback_cdp.detail}"
                        )
                    else:
                        surface_key = "fallback"
                        surface_label = "Fallback surface"
                        surface_badge = "Fallback required"
                        surface_reason = (
                            f"tdata недоступен; bridge={fallback_bridge.state}, cdp={fallback_cdp.state}. "
                            "Нужна подготовка secondary surface."
                        )
            if preset_key == "resume_last" and resume_state is None:
                notes.append("Resume Last недоступен: нет сохранённой последней сессии.")
            if not helper_ready:
                notes.append("collector helper недоступен: проверьте venv и telegram_tdata_helper.py.")
            if portable_profile is not None:
                notes.append(f"Portable profile: {portable_profile_label(portable_profile)}")
                notes.append(f"Profile dir: {portable_profile.profile_dir}")
            if portable_source is not None and portable_source.path is not None:
                notes.append(f"Portable source: {portable_source.kind} | {portable_source.path}")
                notes.append(f"Portable runtime: {portable_runtime.state}." if portable_runtime is not None else "Portable runtime: pending.")
                if portable_runtime is not None and portable_runtime.state in {"missing", "sync_required"}:
                    notes.append("Helper-копия не синхронизируется автоматически: используйте кнопку 'Обновить статус'.")
                if portable_runtime is not None and portable_runtime.state == "stale":
                    notes.append("Профиль уже запускался через launch clone; после закрытия Telegram нажмите 'Обновить статус'.")
                if portable_runtime is not None and portable_runtime.state == "unauthorized":
                    notes.append("Откройте portable Telegram, чтобы авторизовать runtime clone и дать helper открыть session.")
                if portable_runtime is not None and portable_runtime.state == "binary_missing":
                    notes.append("Portable binary не найден; helper/export доступен, но кнопка запуска будет недоступна.")
            elif tdata_ready:
                notes.append("tdata доступен и будет использован как основной surface.")
            elif account is not None and availability_state != "missing":
                notes.append("tdata не найден; GUI упадёт в fallback adapter.")
                if fallback_bridge is not None:
                    notes.append(f"Bridge: {fallback_bridge.state}.")
                if fallback_cdp is not None:
                    notes.append(f"CDP: {fallback_cdp.state}.")
        history_limit, timeout_sec = self.preset_limits(preset_key)
        if connected_target is not None:
            connection_label = f"Клиент готов: {connected_target.client_id}"
        elif surface_key == "tdata":
            if tdata_ready:
                connection_label = "Primary tdata path готов без hub."
            else:
                connection_label = surface_reason or "Primary tdata path требует подготовки."
        elif fallback_bridge is not None and fallback_bridge.state == "ready" and surface_key == "bridge":
            connection_label = fallback_bridge.detail
        elif fallback_cdp is not None and fallback_cdp.state == "ready" and surface_key == "cdp":
            connection_label = fallback_cdp.detail
        else:
            connection_label = "Hub ещё не подключён."
        hub_reachable = bool(connected_target) or str(security_info.get("hub_token_status") or "") == "ok"
        workspace_health = self.preflight_service.collect_workspace_health(
            runtime_dir=RUNTIME_DIR,
            logs_dir=ACTION_LOG_DIR,
            helper_available=helper_ready,
            collector_python_available=helper_python is not None,
            node_available=bool(shutil.which("node")),
            hub_reachable=hub_reachable if not deep else (
                bool(connected_target) or (self._hub_reachable(account.token) if account is not None else False)
            ),
            stale_runtime_files=self._count_stale_runtime_files(),
            warning=self._foreign_hub_warning(),
        )
        if workspace_health.warning:
            notes.append(workspace_health.warning)
        if workspace_health.stale_runtime_files:
            notes.append(f"Обнаружены stale runtime files: {workspace_health.stale_runtime_files}.")
        self._last_surface_reason = surface_reason
        return self.preflight_service.build(
            surface_key=surface_key,
            surface_label=surface_label,
            surface_badge=surface_badge,
            surface_reason=surface_reason,
            is_primary=is_primary,
            tdata_ready=tdata_ready,
            helper_ready=helper_ready,
            output_path=output_path,
            preset_key=preset_key,
            preset_label=preset_label,
            history_limit=history_limit,
            timeout_sec=timeout_sec,
            resume_available=resume_state is not None,
            token=account.token if account is not None else "",
            token_source=str(security_info.get("token_source") or ""),
            workspace_health=workspace_health,
            connection_label=connection_label,
            hub_token_status=str(security_info.get("hub_token_status") or ""),
            hub_token_detail=str(security_info.get("hub_token_detail") or ""),
            hub_restart_available=bool(security_info.get("hub_restart_available")),
            fallback_bridge=fallback_bridge,
            fallback_cdp=fallback_cdp,
            portable_source=portable_source,
            portable_runtime=portable_runtime,
            portable_profile=portable_profile,
            notes=tuple(notes),
        )

    def load_accounts(self) -> list[AccountOption]:
        layout_mod.ensure_workspace(TELEGRAM_WORKSPACE_ROOT, slots=WORKSPACE_SLOTS)
        auto_profiles = _group_auto_profile_sources(layout_mod.list_profiles(TELEGRAM_WORKSPACE_ROOT))
        registry = registry_mod.load_registry(USER_REGISTRY_PATH)
        for auto_name, profile_value in auto_profiles:
            slot_number = _slot_number_from_source(profile_value)
            if slot_number:
                self.portable_profiles.sync_legacy_slot_profile(
                    slot_number,
                    profile_name=_auto_profile_label(auto_name, profile_value),
                    account_label=_auto_profile_label(auto_name, profile_value),
                )
            bootstrap_account = AccountOption(
                key=f"auto:{auto_name}",
                label=_auto_profile_label(auto_name, profile_value),
                name=_auto_profile_label(auto_name, profile_value),
                token="",
                profile_source=profile_value,
                source_kind="auto",
                sort_key=(0, "", ""),
                slot_number=slot_number,
                token_source="slot_key" if slot_number else "missing",
            )
            if slot_number and self.import_slot_token_into_registry(bootstrap_account):
                registry = registry_mod.load_registry(USER_REGISTRY_PATH)
        options: list[AccountOption] = []
        seen_profile_keys: set[str] = set()
        seen_slot_numbers: set[str] = set()

        default_user_name = str(registry.get("default_user") or "").strip()
        for row in registry_mod.list_users(registry):
            name = str(row.get("name") or "").strip()
            token = str(row.get("token") or "").strip() or DEFAULT_TOKEN
            profile_source = str(row.get("profile") or "").strip()
            profile_key = _normalize_path_key(profile_source or str(DEFAULT_PROFILE_DIR))
            seen_profile_keys.add(profile_key)
            rank = 0 if name == default_user_name else 1
            label = name if name else "Пользователь из реестра"
            slot_number = _slot_number_from_source(profile_source)
            if slot_number:
                seen_slot_numbers.add(slot_number)
            options.append(
                AccountOption(
                    key=f"registry:{name or profile_key}",
                    label=label,
                    name=name or label,
                    token=token,
                    profile_source=profile_source,
                    source_kind="registry",
                    sort_key=(rank, label.lower(), profile_key),
                    secret_ref=str(row.get("secret_ref") or "").strip(),
                    slot_number=slot_number,
                    token_source=_account_token_source(
                        token=token,
                        secret_ref=str(row.get("secret_ref") or "").strip(),
                        slot_token=_slot_token(slot_number),
                        default_token=DEFAULT_TOKEN,
                    ),
                )
            )

        for auto_name, profile_value in auto_profiles:
            profile_key = _normalize_path_key(profile_value)
            if profile_key in seen_profile_keys:
                continue
            slot_number = _slot_number_from_source(profile_value)
            if slot_number and slot_number in seen_slot_numbers:
                continue
            slot_token = _slot_token(slot_number)
            token = slot_token or DEFAULT_TOKEN
            label = _auto_profile_label(auto_name, profile_value)
            rank = 2 if slot_number else 3
            options.append(
                AccountOption(
                    key=f"auto:{auto_name}",
                    label=label,
                    name=label,
                    token=token,
                    profile_source=profile_value,
                    source_kind="auto",
                    sort_key=(rank, f"{int(slot_number):04d}" if slot_number else label.lower(), profile_key),
                    slot_number=slot_number,
                    token_source=_account_token_source(
                        token=token,
                        secret_ref="",
                        slot_token=slot_token,
                        default_token=DEFAULT_TOKEN,
                    ),
                )
            )

        enriched: list[AccountOption] = []
        for item in options:
            resolved_profile, availability_state, availability_detail = self.resolve_profile_dir_safe(item.profile_source)
            portable_source = self.inspect_portable_source(item)
            portable_profile = self.portable_profile_for_account(item)
            portable_runtime_state = portable_profile.state if portable_profile is not None else ""
            if not portable_runtime_state and item.slot_number and portable_source.path is not None:
                portable_runtime_state = _portable_runtime_state_from_workspace(
                    slot_number=item.slot_number,
                    source_info=portable_source,
                    binary_path=find_portable_telegram_binary(resolved_profile) if resolved_profile is not None else None,
                ).state
            enriched.append(
                AccountOption(
                    key=item.key,
                    label=item.label,
                    name=item.name,
                    token=item.token,
                    profile_source=item.profile_source,
                    source_kind=item.source_kind,
                    sort_key=item.sort_key,
                    secret_ref=item.secret_ref,
                    slot_number=item.slot_number,
                    token_source=item.token_source,
                    availability_state=availability_state,
                    availability_detail=availability_detail,
                    portable_source_path=str(portable_source.path) if portable_source.path is not None else "",
                    portable_source_kind=portable_source.kind,
                    portable_runtime_state=portable_runtime_state,
                    portable_profile_dir=str(portable_profile.profile_dir) if portable_profile is not None else "",
                    portable_profile_name=portable_profile.profile_name if portable_profile is not None else "",
                    portable_profile_label=(
                        (portable_profile.account_label or portable_profile.account_username)
                        if portable_profile is not None
                        else ""
                    ),
                )
            )

        enriched.sort(key=lambda item: item.sort_key)
        return enriched

    def ensure_connected(self, account: AccountOption, *, launch_browser: bool = True) -> BrowserTarget:
        portable_source = self.inspect_portable_source(account)
        if portable_source.path is not None:
            runtime_state = self.prepare_portable_runtime(account, force=False)
            if runtime_state.ready_for_export and runtime_state.runtime_dir is not None:
                target = BrowserTarget(
                    client_id=f"tdata:{_tdata_target_key(runtime_state.runtime_dir)}",
                    tab_id=0,
                    tab_title="Telegram Desktop",
                    tab_url=str(runtime_state.runtime_dir),
                )
                self._log_action(f"client_ready portable_tdata client_id={target.client_id}")
                return target
            raise PrimarySurfaceBlocked(runtime_state.detail or "Portable tdata недоступен. Откройте portable Telegram.")

        try:
            target = self._adapters_by_key["tdata"].connect(account, launch_browser=False)
        except Exception as exc:
            self._log_action(f"tdata_unavailable reason={_compact_error_text(str(exc))}")
        else:
            if target is not None:
                return target

        bridge_status = self.probe_bridge_readiness(account)
        if bridge_status.state == "ready" and bridge_status.target is not None:
            return bridge_status.target
        if launch_browser and bridge_status.state in {"client_offline", "extension_setup_required"}:
            bridge_status = self.prepare_bridge_surface(account)
            if bridge_status.state == "ready" and bridge_status.target is not None:
                return bridge_status.target
        self._log_action(f"bridge_unavailable reason={bridge_status.state} detail={_compact_error_text(bridge_status.detail)}")

        cdp_status = self.probe_cdp_readiness(account)
        if cdp_status.state == "ready" and cdp_status.target is not None:
            cdp_status = self._probe_cdp_target(cdp_status.target, deep=True)
            if cdp_status.state == "ready" and cdp_status.target is not None:
                return cdp_status.target
        if launch_browser and cdp_status.state in {"client_offline", "telegram_auth_required"}:
            cdp_status = self.prepare_cdp_surface(account)
            if cdp_status.state == "ready" and cdp_status.target is not None:
                return cdp_status.target
        self._log_action(f"cdp_unavailable reason={cdp_status.state} detail={_compact_error_text(cdp_status.detail)}")

        if not launch_browser:
            raise RuntimeError("Нет подключённого клиента Telegram. Нажмите 'Подключить Telegram'.")
        raise RuntimeError(self._fallback_connect_error(bridge_status, cdp_status))

    def fetch_chats(self, account: AccountOption, target: BrowserTarget) -> tuple[BrowserTarget, list[ChatOption]]:
        return self.adapter_for_target(target).list_chats(account, target)

    def open_chat(self, account: AccountOption, target: BrowserTarget, chat: ChatOption) -> BrowserTarget:
        return self.adapter_for_target(target).open_chat(account, target, chat)

    def _tdata_dir_for_account(self, account: AccountOption, *, runtime_error_prefix: str = "runtime_unavailable") -> Path:
        portable_source = self.inspect_portable_source(account)
        if portable_source.path is not None:
            runtime_state = self.prepare_portable_runtime(account, force=False)
            if runtime_state.runtime_dir is None or not runtime_state.ready_for_export:
                detail = runtime_state.detail or "Portable runtime недоступна для этого профиля."
                raise RuntimeError(f"{runtime_error_prefix}: {detail}")
            return runtime_state.runtime_dir

        tdata_dir = resolve_tdata_dir(Path(account.profile_source).expanduser())
        if tdata_dir is None:
            raise RuntimeError(f"{runtime_error_prefix}: Для этого профиля не найден рабочий tdata source.")
        return tdata_dir

    def _resolved_chat_option(self, item: dict[str, Any], *, raw_target: str, source_kind: str) -> ChatOption:
        chat_ref = str(item.get("chat_ref") or item.get("peer_id") or "").strip()
        title = _clean_tab_title(str(item.get("title") or chat_ref or raw_target or "Telegram"))
        username = str(item.get("username") or "").strip()
        subtitle_bits = [str(item.get("subtitle") or "").strip()]
        if username:
            subtitle_bits.append(username)
        subtitle_bits.append("resolved target")
        return ChatOption(
            title=title,
            subtitle=" | ".join(bit for bit in subtitle_bits if bit),
            url=username or raw_target or chat_ref,
            fragment=chat_ref or raw_target,
            peer_id=str(item.get("peer_id") or chat_ref or "").strip(),
            active=False,
            visible=True,
            ordinal=-1,
            source_kind=source_kind,
        )

    def resolve_tdata_chat_target(self, account: AccountOption, chat_target: str) -> ChatOption:
        raw_target = str(chat_target or "").strip()
        if not raw_target:
            raise RuntimeError("not_found: Укажите публичную ссылку Telegram, @username или peer id.")

        if _is_invite_like_target(raw_target):
            payload = self.join_tdata_invite(account, raw_target)
            item = payload.get("item") if isinstance(payload, dict) else None
            if not isinstance(item, dict):
                raise RuntimeError("not_found: Invite path не вернул Telegram chat target.")
            chat = self._resolved_chat_option(item, raw_target=raw_target, source_kind="resolved")
            self._log_action(f"chat_resolved invite account={account.name} chat_ref={chat.fragment}")
            return chat

        normalized = _public_chat_target_from_value(raw_target)
        if not normalized:
            raise RuntimeError(f"not_found: Неподдерживаемый публичный target Telegram: {raw_target}")

        tdata_dir = self._tdata_dir_for_account(account)
        payload = self._run_tdata_helper(
            "resolve-chat",
            tdata_dir=tdata_dir,
            extra_args=["--chat", raw_target],
            timeout_sec=_tdata_helper_timeout_seconds("resolve-chat"),
        )
        access_state = str(payload.get("access_state") or "not_found").strip() if isinstance(payload, dict) else "not_found"
        detail = str(payload.get("detail") or "").strip() if isinstance(payload, dict) else ""
        if not isinstance(payload, dict) or not bool(payload.get("ok")) or access_state != "ok":
            message = detail or {
                "not_found": "Target не найден этим профилем.",
                "invite_required": "Этот target требует invite/join path.",
                "resolved_but_no_access": "Target резолвится, но текущий профиль не имеет доступа к истории.",
                "runtime_unavailable": "Portable runtime недоступна.",
            }.get(access_state, "Не удалось подготовить target для экспорта.")
            raise RuntimeError(f"{access_state}: {message}")
        item = payload.get("item")
        if not isinstance(item, dict):
            raise RuntimeError("not_found: resolve-chat не вернул Telegram chat target.")
        chat = self._resolved_chat_option(item, raw_target=normalized, source_kind="resolved")
        self._log_action(f"chat_resolved public account={account.name} chat_ref={chat.fragment}")
        return chat

    def join_tdata_invite(self, account: AccountOption, invite_link: str) -> dict[str, Any]:
        tdata_dir = self._tdata_dir_for_account(account)
        payload = self._run_tdata_helper(
            "join-invite",
            tdata_dir=tdata_dir,
            extra_args=["--invite-link", invite_link],
            timeout_sec=_tdata_helper_timeout_seconds("join-invite"),
        )
        item = payload.get("item") if isinstance(payload, dict) else None
        title = str(item.get("title") or "") if isinstance(item, dict) else ""
        peer_id = str(item.get("peer_id") or "") if isinstance(item, dict) else ""
        self._log_action(
            f"invite_joined account={account.name} title={_compact_error_text(title)} peer_id={peer_id or '-'}"
        )
        return payload

    def _fallback_connect_error(self, bridge_status: FallbackReadiness, cdp_status: FallbackReadiness) -> str:
        if bridge_status.state == "extension_setup_required":
            if cdp_status.state == "ready":
                return cdp_status.detail
            if cdp_status.state == "telegram_auth_required":
                return (
                    f"{bridge_status.detail} "
                    "CDP profile открыт, но Telegram там ещё не залогинен. Выполните вход и повторите подключение."
                )
            return bridge_status.detail
        if bridge_status.state in {"foreign_hub", "hub_mismatch"}:
            if cdp_status.state == "ready":
                return cdp_status.detail
            return bridge_status.detail
        if cdp_status.state == "telegram_auth_required":
            return cdp_status.detail
        if cdp_status.state == "browser_launch_failed":
            return cdp_status.detail
        details = [detail for detail in (bridge_status.detail, cdp_status.detail) if detail]
        return details[0] if details else "Не удалось подключить Telegram Web через выбранный профиль."

    def run_export(
        self,
        account: AccountOption,
        target: BrowserTarget,
        chat: ChatOption,
        output_path: Path,
        emit: Callable[[str], None],
        controller: TaskController | None = None,
        *,
        preset_key: str = "full_history",
    ) -> ExportResult:
        ACTION_LOG_DIR.mkdir(parents=True, exist_ok=True)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        started_at = datetime.now(timezone.utc)
        self._log_action(f"run_start output={output_path} chat={chat.url} client_id={target.client_id}")
        preset_key, preset_label = self._preset_choice(preset_key)
        adapter = self.adapter_for_target(target)
        try:
            result = adapter.run_export(
                account,
                target,
                chat,
                output_path,
                emit,
                controller=controller,
                preset_key=preset_key,
                preset_label=preset_label,
            )
        except Exception as exc:
            self._log_action(f"run_failed error={type(exc).__name__} message={_compact_error_text(str(exc))}")
            self._record_failed_run(
                account=account,
                chat=chat,
                output_path=output_path,
                preset_key=preset_key,
                preset_label=preset_label,
                surface_key=adapter.key,
                surface_label=adapter.label,
                surface_badge=adapter.badge,
                started_at=started_at,
                failure_reason=_classify_failure_reason(str(exc)),
            )
            raise
        finished_at = datetime.now(timezone.utc)
        duration_sec = max(int((finished_at - started_at).total_seconds()), 0)
        if not result.started_at:
            result = ExportResult(
                **{**result.__dict__, "started_at": started_at.isoformat(), "finished_at": finished_at.isoformat(), "duration_sec": duration_sec,
                   "status": result.status or ("partial" if result.interrupted else "done"),
                   "security_mode": result.security_mode or self.preflight_service.security_mode(account.token)[0]}
            )
        self._record_run(
            account=account,
            chat=chat,
            result=result,
            preset_key=preset_key,
            preset_label=preset_label,
        )
        return result

    def _record_run(
        self,
        *,
        account: AccountOption,
        chat: ChatOption,
        result: ExportResult,
        preset_key: str,
        preset_label: str,
    ) -> None:
        self.run_history.ensure()
        created_at = _utc_timestamp()
        surface_key = result.surface_key or "unknown"
        surface_label = result.surface_label or surface_key
        surface_badge = result.surface_badge or surface_label
        artifacts = build_artifact_bundle(result)
        record = RunRecord(
            run_id=created_at,
            created_at=created_at,
            surface_key=surface_key,
            surface_label=surface_label,
            surface_badge=surface_badge,
            preset_key=preset_key,
            preset_label=preset_label,
            account_key=account.key,
            account_label=account.label,
            chat_ref=chat.fragment,
            chat_title=chat.title,
            output_path=result.output_path,
            interrupted=result.interrupted,
            safe_count=result.safe_count,
            usernames_found=result.usernames_found,
            history_messages_scanned=result.history_messages_scanned,
            status=result.status or ("partial" if result.interrupted else "done"),
            duration_sec=result.duration_sec,
            started_at=result.started_at,
            finished_at=result.finished_at,
            security_mode=result.security_mode,
            failure_reason=result.failure_reason,
            artifacts=artifacts,
        )
        session = SessionResumeState(
            account_key=account.key,
            account_label=account.label,
            chat_ref=chat.fragment,
            chat_title=chat.title,
            output_path=result.output_path,
            surface_key=surface_key,
            surface_label=surface_label,
            surface_badge=surface_badge,
            preset_key=preset_key,
            preset_label=preset_label,
            created_at=created_at,
            last_surface_reason=self._last_surface_reason,
            last_output_dir=result.output_path.parent,
            last_status=result.status or ("partial" if result.interrupted else "done"),
        )
        self.run_history.append_run(record)
        self.run_history.save_last_session(session)
        append_index_entry(
            index_path=ARTIFACT_INDEX_PATH,
            created_at=created_at,
            account_label=account.label,
            chat_title=chat.title,
            chat_ref=chat.fragment,
            preset_label=preset_label,
            surface_badge=surface_badge,
            status=record.status,
            artifacts=artifacts,
        )

    def _record_failed_run(
        self,
        *,
        account: AccountOption,
        chat: ChatOption,
        output_path: Path,
        preset_key: str,
        preset_label: str,
        surface_key: str,
        surface_label: str,
        surface_badge: str,
        started_at: datetime,
        failure_reason: str,
    ) -> None:
        finished_at = datetime.now(timezone.utc)
        created_at = _utc_timestamp()
        duration_sec = max(int((finished_at - started_at).total_seconds()), 0)
        record = RunRecord(
            run_id=created_at,
            created_at=created_at,
            surface_key=surface_key,
            surface_label=surface_label,
            surface_badge=surface_badge,
            preset_key=preset_key,
            preset_label=preset_label,
            account_key=account.key,
            account_label=account.label,
            chat_ref=chat.fragment,
            chat_title=chat.title,
            output_path=output_path,
            interrupted=False,
            safe_count=0,
            usernames_found=0,
            history_messages_scanned=0,
            status="failed",
            duration_sec=duration_sec,
            started_at=started_at.isoformat(),
            finished_at=finished_at.isoformat(),
            security_mode=self.preflight_service.security_mode(account.token)[0],
            failure_reason=failure_reason,
            artifacts=ArtifactBundle(
                markdown=output_path,
                usernames_txt=output_path.with_name(f"{output_path.stem}_usernames.txt"),
            ),
        )
        self.run_history.append_run(record)

    def _ensure_cdp_target(self, profile_dir: Path, *, launch_browser: bool) -> BrowserTarget | None:
        port = self._find_active_cdp_port(profile_dir)
        if port is None and not launch_browser:
            return None
        if port is None:
            port = self._launch_cdp_browser(profile_dir)
        payload = self._run_cdp_helper(
            "status",
            port=port,
            timeout_sec=15,
            extra_args=["--timeout-ms", "15000"],
        )
        target_meta = payload.get("telegram_target") or {}
        tab_url = str(target_meta.get("url") or TELEGRAM_WEB_URL)
        tab_title = _clean_tab_title(str(target_meta.get("title") or "Telegram"))
        return BrowserTarget(
            client_id=f"cdp:{port}",
            tab_id=port,
            tab_title=tab_title,
            tab_url=tab_url,
        )

    def _ensure_tdata_target(
        self,
        profile_dir: Path,
        *,
        launch_browser: bool,
        account: AccountOption | None = None,
    ) -> BrowserTarget | None:
        if _selected_helper_python() is None:
            return None
        if account is not None:
            portable_source = self.inspect_portable_source(account)
            if portable_source.path is not None:
                runtime_state = self.prepare_portable_runtime(account, force=False)
                if not runtime_state.ready_for_export or runtime_state.runtime_dir is None:
                    raise PrimarySurfaceBlocked(
                        runtime_state.detail or "Portable tdata недоступен. Откройте portable Telegram."
                    )
                return BrowserTarget(
                    client_id=f"tdata:{_tdata_target_key(runtime_state.runtime_dir)}",
                    tab_id=0,
                    tab_title="Telegram Desktop",
                    tab_url=str(runtime_state.runtime_dir),
                )
        for tdata_dir in list_candidate_tdata_dirs(profile_dir, include_collector_debug=ALLOW_COLLECTOR_TDATA_DEBUG_FALLBACK):
            try:
                self._run_tdata_helper("list-chats", tdata_dir=tdata_dir, extra_args=["--limit", "5"])
            except Exception as exc:
                self._log_action(f"tdata_unavailable dir={tdata_dir} reason={exc}")
                continue
            return BrowserTarget(
                client_id=f"tdata:{_tdata_target_key(tdata_dir)}",
                tab_id=0,
                tab_title="Telegram Desktop",
                tab_url=str(tdata_dir),
            )
        return None

    def _run_export_via_tdata(
        self,
        *,
        tdata_dir: Path,
        chat: ChatOption,
        output_path: Path,
        emit: Callable[[str], None],
        controller: TaskController | None = None,
        preset_key: str,
        preset_label: str,
        surface_key: str,
        surface_label: str,
        surface_badge: str,
    ) -> ExportResult:
        history_limit, timeout_sec = self.preset_limits(preset_key)
        run_log_path = ACTION_LOG_DIR / f"export_run_{_utc_timestamp()}.log"
        payload = self._run_tdata_helper(
            "export-chat",
            tdata_dir=tdata_dir,
            extra_args=[
                "--chat-ref",
                chat.fragment,
                "--source",
                "history",
                "--participants-limit",
                "0",
                "--history-limit",
                history_limit,
                "--progress-every",
                TDATA_PROGRESS_EVERY,
            ],
            emit=emit,
            timeout_sec=timeout_sec,
            controller=controller,
        )
        rows = payload.get("rows") if isinstance(payload, dict) else []
        members = rows if isinstance(rows, list) else []
        export_mod._write_markdown(output_path, members, chat.url or chat.fragment, "tdata-history-authors")
        username_rows = export_mod._collect_username_rows(members)
        sidecars = export_mod._write_username_sidecars(output_path, username_rows, chat.url or chat.fragment, "tdata-history-authors")
        self._write_run_log_json(run_log_path, payload)
        stats = payload.get("stats") or {}
        history_messages_scanned = int(stats.get("history_messages_scanned") or 0)
        interrupted = bool(payload.get("interrupted")) or bool(stats.get("interrupted"))
        emit(f"tdata source=history-only")
        emit(f"tdata history_messages={history_messages_scanned}")
        emit(f"tdata usernames={len(username_rows)}")
        if interrupted:
            emit("tdata interrupted=1")
        payload_map = self._run_snapshot_helper(
            output_path=output_path,
            safe_slug=slugify_filename(chat.title or chat.fragment),
            emit=emit,
            run_log_path=run_log_path,
        )
        safe_txt = _optional_path(payload_map.get("safe_txt"))
        safe_md = _optional_path(payload_map.get("safe_md"))
        safe_count = int(payload_map.get("safe_count") or 0)
        usernames_txt = Path(str(sidecars.get("usernames_txt") or output_path.with_name(f"{output_path.stem}_usernames.txt")))
        usernames_json = output_path.with_name(f"{output_path.stem}_usernames.json")
        self._log_action(f"run_success tdata output={output_path} safe_count={safe_count}")
        return ExportResult(
            output_path=output_path,
            usernames_txt=usernames_txt,
            safe_count=safe_count,
            history_messages_scanned=history_messages_scanned,
            usernames_found=len(username_rows),
            interrupted=interrupted,
            safe_txt=safe_txt,
            safe_md=safe_md,
            log_path=run_log_path,
            action_log_path=self.action_log_path,
            usernames_json=usernames_json if usernames_json.exists() else None,
            surface_key=surface_key,
            surface_label=surface_label,
            surface_badge=surface_badge,
            preset_key=preset_key,
            preset_label=preset_label,
            status="partial" if interrupted else "done",
        )

    def _run_tdata_helper(
        self,
        command: str,
        *,
        tdata_dir: Path,
        extra_args: list[str] | None = None,
        emit: Callable[[str], None] | None = None,
        timeout_sec: int | None = None,
        controller: TaskController | None = None,
    ) -> dict[str, Any]:
        helper_python = _selected_helper_python()
        if helper_python is None:
            raise RuntimeError(
                "runtime_unavailable: Telegram helper python не найден. "
                "Запустите scripts/bootstrap_telegram_workstation.sh или укажите TELEGRAM_API_COLLECTOR_PYTHON."
            )
        session_path = TDATA_SESSION_DIR / f"{_tdata_target_key(tdata_dir)}.session"
        TDATA_SESSION_DIR.mkdir(parents=True, exist_ok=True)
        args = [
            str(helper_python[1]),
            str(TDATA_HELPER_SCRIPT),
            command,
            "--tdata",
            str(tdata_dir),
            "--session",
            str(session_path),
        ]
        if extra_args:
            args.extend(extra_args)
        effective_timeout = timeout_sec if timeout_sec is not None else _tdata_helper_timeout_seconds(command)
        with self._tdata_helper_lock:
            run = self.process_runner.run(
                args,
                cwd=str(REPO_ROOT),
                controller=controller,
                timeout_sec=effective_timeout,
                emit_stderr=emit,
                on_cancel_begin=(lambda: emit("Остановка сканирования: завершаем текущий проход...") if emit else None),
            )
            if run.forced_cancel:
                raise TaskCancelled("Сканирование остановлено пользователем.")
            if run.timed_out:
                progress_hint = _latest_progress_summary(list(run.stderr_lines))
                suffix = f" Последний прогресс: {progress_hint}." if progress_hint else ""
                if command == "export-chat":
                    raise RuntimeError(
                        f"Скан истории Telegram превысил настроенный лимит {effective_timeout}s.{suffix} "
                        "Уберите TELEGRAM_TDATA_EXPORT_TIMEOUT_SEC или поставьте 0 для полного прохода без лимита. "
                        "Если нужен только короткий тестовый прогон, уменьшите TELEGRAM_TDATA_HISTORY_LIMIT."
                    )
                raise RuntimeError(f"tdata helper timed out after {effective_timeout}s: {command}{suffix}")
            if controller is not None and controller.cancel_requested and run.return_code != 0:
                raise TaskCancelled("Сканирование остановлено пользователем.")
            if run.return_code != 0:
                message = (run.stderr or run.stdout).strip()
                raise RuntimeError(message or f"tdata helper failed: {command}")
            try:
                payload = json.loads(run.stdout)
            except json.JSONDecodeError as exc:
                if controller is not None and controller.cancel_requested:
                    raise TaskCancelled("Сканирование остановлено пользователем.") from exc
                raise RuntimeError(f"tdata helper returned invalid JSON for {command}.") from exc
            if not isinstance(payload, dict):
                raise RuntimeError(f"tdata helper returned unexpected payload for {command}.")
            return payload

    def _launch_portable_telegram_best_effort(self, profile_dir: Path, tdata_dir: Path) -> None:
        binary_path = find_portable_telegram_binary(profile_dir)
        if binary_path is None:
            return
        workdir = tdata_dir.parent
        try:
            mode = binary_path.stat().st_mode
            if mode & 0o111 == 0:
                binary_path.chmod(mode | 0o755)
        except OSError:
            return
        try:
            subprocess.Popen(
                [str(binary_path), "-workdir", str(workdir)],
                cwd=str(binary_path.parent),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            self._log_action(f"portable_launch binary={binary_path} workdir={workdir}")
        except OSError:
            return

    def _run_export_via_cdp(
        self,
        *,
        port: int,
        chat: ChatOption,
        output_path: Path,
        emit: Callable[[str], None],
        controller: TaskController | None = None,
        preset_key: str,
        preset_label: str,
        surface_key: str,
        surface_label: str,
        surface_badge: str,
    ) -> ExportResult:
        run_log_path = ACTION_LOG_DIR / f"export_run_{_utc_timestamp()}.log"
        helper_args = [
            "--url",
            chat.url,
            "--steps",
            CHAT_STEPS,
            "--pause-ms",
            str(max(int(float(export_mod.CHAT_SCROLL_SETTLE_SEC) * 1000), 250)),
            "--timeout-ms",
            str(max(int(CHAT_MAX_RUNTIME) * 1000, 90000)),
        ]
        payload = self._run_cdp_helper(
            "collect-chat",
            port=port,
            timeout_sec=max(int(CHAT_MAX_RUNTIME) + 60, 180),
            extra_args=helper_args,
            controller=controller,
        )
        members = merge_cdp_export_payload(payload)
        export_mod._write_markdown(output_path, members, chat.url, "cdp-simple")
        username_rows = export_mod._collect_username_rows(members)
        sidecars = export_mod._write_username_sidecars(output_path, username_rows, chat.url, "cdp-simple")
        self._write_run_log_json(run_log_path, payload)
        emit(f"simple-cdp members={len(members)}")
        emit(f"simple-cdp usernames={len(username_rows)}")
        payload_map = self._run_snapshot_helper(
            output_path=output_path,
            safe_slug=slugify_filename(chat.url),
            emit=emit,
            run_log_path=run_log_path,
        )
        safe_txt = _optional_path(payload_map.get("safe_txt"))
        safe_md = _optional_path(payload_map.get("safe_md"))
        safe_count = int(payload_map.get("safe_count") or 0)
        usernames_txt = Path(str(sidecars.get("usernames_txt") or output_path.with_name(f"{output_path.stem}_usernames.txt")))
        usernames_json = output_path.with_name(f"{output_path.stem}_usernames.json")
        self._log_action(f"run_success cdp output={output_path} safe_count={safe_count}")
        return ExportResult(
            output_path=output_path,
            usernames_txt=usernames_txt,
            safe_count=safe_count,
            history_messages_scanned=0,
            usernames_found=len(username_rows),
            interrupted=False,
            safe_txt=safe_txt,
            safe_md=safe_md,
            log_path=run_log_path,
            action_log_path=self.action_log_path,
            usernames_json=usernames_json if usernames_json.exists() else None,
            surface_key=surface_key,
            surface_label=surface_label,
            surface_badge=surface_badge,
            preset_key=preset_key,
            preset_label=preset_label,
            status="done",
        )

    def _run_export_via_bridge(
        self,
        *,
        account: AccountOption,
        target: BrowserTarget,
        chat: ChatOption,
        output_path: Path,
        emit: Callable[[str], None],
        controller: TaskController | None = None,
        preset_key: str,
        preset_label: str,
        surface_key: str,
        surface_label: str,
        surface_badge: str,
    ) -> ExportResult:
        profile_dir = resolve_profile_dir(account.profile_source)
        run_log_path = ACTION_LOG_DIR / f"export_run_{_utc_timestamp()}.log"
        run_log_path.parent.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["SITECTL_TOKEN"] = account.token
        env["SITECTL_BROWSER_PROFILE"] = str(profile_dir)
        env["CHAT_CLIENT_ID"] = target.client_id
        env["SITECTL_SKIP_HUB_BOOT"] = "1"
        chat_steps = CHAT_STEPS
        chat_max_runtime = CHAT_MAX_RUNTIME
        if preset_key == "quick_check":
            chat_steps = str(min(int(CHAT_STEPS), 10))
            chat_max_runtime = str(min(int(CHAT_MAX_RUNTIME), 120))
        command = [
            str(RUN_ONCE_SCRIPT),
            "",
            str(output_path),
            chat.url,
            chat_steps,
            CHAT_DEEP_LIMIT,
            CHAT_TIMEOUT_SEC,
            chat_max_runtime,
            CHAT_DEEP_MODE,
            DEFAULT_MIN_RECORDS,
            target.client_id,
        ]
        run = self.process_runner.run(
            command,
            cwd=str(REPO_ROOT),
            env=env,
            controller=controller,
            timeout_sec=max(int(chat_max_runtime) + 90, 300),
            emit_stdout=emit,
            emit_stderr=emit,
            on_cancel_begin=(lambda: emit("Остановка bridge-экспорта: завершаем текущий проход...") if emit else None),
        )
        run_log_text = _mask_known_secrets(run.stdout + run.stderr, [account.token, DEFAULT_TOKEN])
        run_log_path.write_text(run_log_text, encoding="utf-8")
        if run.forced_cancel or (controller is not None and controller.cancel_requested and run.return_code != 0):
            raise TaskCancelled("Экспорт остановлен пользователем.")
        if run.timed_out:
            raise RuntimeError(f"Экспорт завершился по timeout. Смотрите лог: {run_log_path}")
        if run.return_code != 0:
            self._log_action(f"run_failed rc={run.return_code} log={run_log_path}")
            raise RuntimeError(f"Экспорт завершился ошибкой. Смотрите лог: {run_log_path}")

        payload_map = self._run_snapshot_helper(
            output_path=output_path,
            safe_slug=slugify_filename(chat.url),
            emit=emit,
            run_log_path=run_log_path,
        )
        usernames_txt = output_path.with_name(f"{output_path.stem}_usernames.txt")
        usernames_json = output_path.with_name(f"{output_path.stem}_usernames.json")
        safe_txt = _optional_path(payload_map.get("safe_txt"))
        safe_md = _optional_path(payload_map.get("safe_md"))
        safe_count = int(payload_map.get("safe_count") or 0)
        self._log_action(f"run_success bridge output={output_path} safe_count={safe_count}")
        return ExportResult(
            output_path=output_path,
            usernames_txt=usernames_txt,
            safe_count=safe_count,
            history_messages_scanned=0,
            usernames_found=safe_count,
            interrupted=False,
            safe_txt=safe_txt,
            safe_md=safe_md,
            log_path=run_log_path,
            action_log_path=self.action_log_path,
            usernames_json=usernames_json if usernames_json.exists() else None,
            surface_key=surface_key,
            surface_label=surface_label,
            surface_badge=surface_badge,
            preset_key=preset_key,
            preset_label=preset_label,
            status="done",
            security_mode=self.preflight_service.security_mode(account.token)[0],
        )

    def _run_cdp_helper(
        self,
        command: str,
        *,
        port: int,
        timeout_sec: int,
        extra_args: list[str] | None = None,
        controller: TaskController | None = None,
    ) -> dict[str, Any]:
        args = ["node", str(CDP_HELPER_SCRIPT), command, "--port", str(port)]
        if extra_args:
            args.extend(extra_args)
        run = self.process_runner.run(
            args,
            cwd=str(REPO_ROOT),
            controller=controller,
            timeout_sec=max(timeout_sec, 5),
        )
        if run.forced_cancel or (controller is not None and controller.cancel_requested and run.return_code != 0):
            raise TaskCancelled("Экспорт остановлен пользователем.")
        if run.timed_out:
            raise RuntimeError(f"CDP helper timed out after {max(timeout_sec, 5)}s: {command}")
        if run.return_code != 0:
            message = (run.stderr or run.stdout or "").strip()
            raise RuntimeError(message or f"CDP helper failed: {command}")
        try:
            payload = json.loads(run.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"CDP helper returned invalid JSON for {command}.") from exc
        if not isinstance(payload, dict):
            raise RuntimeError(f"CDP helper returned unexpected payload for {command}.")
        return payload

    def _write_run_log_json(self, run_log_path: Path, payload: dict[str, Any]) -> None:
        with run_log_path.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2))
            handle.write("\n")

    def _run_snapshot_helper(
        self,
        *,
        output_path: Path,
        safe_slug: str,
        emit: Callable[[str], None],
        run_log_path: Path,
    ) -> dict[str, str]:
        safe_dir = output_path.parent / f"telegram_export_{safe_slug}"
        snapshot_cmd = [
            sys.executable,
            str(SAFE_SNAPSHOT_SCRIPT),
            "--source-md",
            str(output_path),
            "--directory",
            str(safe_dir),
        ]
        snapshot = subprocess.run(
            snapshot_cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        if snapshot.stdout:
            for line in snapshot.stdout.splitlines():
                emit(line)
        if snapshot.stderr:
            for line in snapshot.stderr.splitlines():
                emit(line)
        if snapshot.returncode != 0:
            self._log_action(f"safe_snapshot_failed rc={snapshot.returncode} output={output_path}")
            raise RuntimeError(f"Экспорт сохранён, но safe snapshot не построен. Смотрите лог: {run_log_path}")
        return parse_key_value_output(snapshot.stdout)

    def _find_active_cdp_port(self, profile_dir: Path) -> int | None:
        state = self._load_cdp_state(profile_dir)
        if state is None:
            return None
        port_value = state.get("port")
        try:
            port = int(port_value)
        except (TypeError, ValueError):
            return None
        return port if _cdp_debugger_ready(port) else None

    def _load_cdp_state(self, profile_dir: Path) -> dict[str, Any] | None:
        state_path = _cdp_state_path(profile_dir)
        if not state_path.exists():
            return None
        try:
            payload = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _save_cdp_state(self, profile_dir: Path, *, port: int) -> None:
        state_path = _cdp_state_path(profile_dir)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps({"profile_dir": str(profile_dir), "port": int(port)}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _launch_cdp_browser(self, profile_dir: Path) -> int:
        browser = _detect_browser_binary()
        port = _pick_free_cdp_port(profile_dir)
        log_path = ACTION_LOG_DIR / f"browser_cdp_{_utc_timestamp()}.log"
        profile_dir.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            process = subprocess.Popen(
                [
                    browser,
                    f"--user-data-dir={profile_dir}",
                    f"--remote-debugging-port={port}",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--new-window",
                    TELEGRAM_WEB_URL,
                ],
                cwd=str(REPO_ROOT),
                stdout=handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        self._save_runtime_owner("cdp_browser", pid=process.pid, extra={"port": int(port), "profile_dir": str(profile_dir)})
        deadline = time.time() + 30
        while time.time() < deadline:
            if _cdp_debugger_ready(port):
                self._save_cdp_state(profile_dir, port=port)
                self._log_action(f"cdp_ready port={port} profile={profile_dir}")
                return port
            time.sleep(0.5)
        raise RuntimeError(
            f"Не удалось запустить Telegram в браузерном профиле. Закройте этот профиль в других окнах Chrome и повторите. Лог: {log_path}"
        )

    def _is_cdp_target(self, target: BrowserTarget | None) -> bool:
        return bool(target and str(target.client_id or "").startswith("cdp:"))

    def _cdp_port_from_target(self, target: BrowserTarget | None) -> int | None:
        if target is None:
            return None
        match = re.fullmatch(r"cdp:(\d+)", str(target.client_id or "").strip())
        if match:
            return int(match.group(1))
        if target.tab_id > 0 and _cdp_debugger_ready(target.tab_id):
            return int(target.tab_id)
        return None

    def _is_tdata_target(self, target: BrowserTarget | None) -> bool:
        return bool(target and str(target.client_id or "").startswith("tdata:"))

    def _tdata_dir_from_target(self, target: BrowserTarget | None) -> Path | None:
        if target is None:
            return None
        if self._is_tdata_target(target):
            path = Path(str(target.tab_url or "")).expanduser()
            return path if path.exists() else None
        return None

    def _ensure_hub(self, token: str) -> None:
        try:
            export_mod._http_json(HUB_URL, token, "GET", "/api/clients", request_timeout_sec=1.5)
            return
        except RuntimeError as exc:
            if "HTTP 401" in str(exc):
                raise RuntimeError(
                    "Hub уже запущен с другим токеном. Остановите старый hub или используйте тот же SITECTL token."
                ) from exc

        hub_pids = self._hub_listener_pids()
        if hub_pids:
            owned = self._owned_runtime_pid("hub")
            if owned is not None and owned in hub_pids:
                self._terminate_owned_runtime("hub")
            else:
                raise RuntimeError(
                    "Порт 8765 уже занят чужим процессом. GUI не будет убивать его автоматически; "
                    "освободите порт или используйте уже запущенный hub."
                )
        log_path = ACTION_LOG_DIR / "hub_gui_boot.log"
        ACTION_LOG_DIR.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "webcontrol",
                    "serve",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8765",
                    "--token",
                    token,
                    "--state-file",
                    str(Path.home() / ".site-control-kit" / "state.json"),
                ],
                cwd=str(REPO_ROOT),
                stdout=handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        self._save_runtime_owner("hub", pid=process.pid, extra={"state_file": str(Path.home() / ".site-control-kit" / "state.json")})
        deadline = time.time() + 6
        while time.time() < deadline:
            try:
                export_mod._http_json(HUB_URL, token, "GET", "/api/clients", request_timeout_sec=1.0)
                self._log_action("hub_ready")
                return
            except RuntimeError:
                time.sleep(0.25)
        raise RuntimeError(f"Не удалось поднять hub. Лог: {log_path}")

    def _hub_listener_pids(self) -> list[int]:
        cmd = "ss -ltnp 'sport = :8765' 2>/dev/null | sed -n 's/.*pid=\\([0-9]\\+\\).*/\\1/p' | sort -u"
        result = subprocess.run(["bash", "-lc", cmd], capture_output=True, text=True, check=False)
        pids: list[int] = []
        for raw in result.stdout.splitlines():
            value = raw.strip()
            if not value.isdigit():
                continue
            pids.append(int(value))
        return pids

    def _runtime_owner_path(self, name: str) -> Path:
        return RUNTIME_OWNERS_DIR / f"{name}.json"

    def _save_runtime_owner(self, name: str, *, pid: int, extra: dict[str, Any] | None = None) -> None:
        RUNTIME_OWNERS_DIR.mkdir(parents=True, exist_ok=True)
        payload = {"pid": int(pid), "updated_at": _utc_timestamp()}
        if extra:
            payload.update(extra)
        self._runtime_owner_path(name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _load_runtime_owner(self, name: str) -> dict[str, Any] | None:
        path = self._runtime_owner_path(name)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _owned_runtime_pid(self, name: str) -> int | None:
        payload = self._load_runtime_owner(name)
        if not isinstance(payload, dict):
            return None
        try:
            pid = int(payload.get("pid") or 0)
        except (TypeError, ValueError):
            return None
        return pid if pid > 0 else None

    def _terminate_owned_runtime(self, name: str) -> None:
        pid = self._owned_runtime_pid(name)
        if pid is None:
            return
        try:
            os.kill(pid, signal.SIGTERM)
            self._log_action(f"{name}_owned_runtime_stopped pid={pid}")
        except OSError:
            return
        deadline = time.time() + 2
        while time.time() < deadline and _pid_is_alive(pid):
            time.sleep(0.1)
        if _pid_is_alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass

    def _hub_reachable(self, token: str) -> bool:
        try:
            export_mod._http_json(HUB_URL, token, "GET", "/api/clients", request_timeout_sec=0.8)
        except RuntimeError:
            return False
        return True

    def _inspect_hub_token_state(self, token: str) -> dict[str, Any]:
        hub_pids = self._hub_listener_pids()
        if not hub_pids:
            return {"state": "offline", "detail": "", "restart_available": False}
        try:
            export_mod._http_json(HUB_URL, token, "GET", "/api/clients", request_timeout_sec=0.8)
        except RuntimeError as exc:
            text = str(exc or "").strip()
            if "HTTP 401" in text:
                owned = self._owned_runtime_pid("hub")
                if owned is not None and owned in hub_pids:
                    return {
                        "state": "owned_mismatch",
                        "detail": "Hub на :8765 уже запущен этим GUI с другим токеном.",
                        "restart_available": True,
                    }
                return {
                    "state": "foreign_mismatch",
                    "detail": "На :8765 уже живёт внешний hub/process с другим токеном. GUI не будет убивать его автоматически.",
                    "restart_available": False,
                }
            return {
                "state": "error",
                "detail": _compact_error_text(text) or "Hub на :8765 сейчас недоступен.",
                "restart_available": False,
            }
        return {"state": "ok", "detail": "", "restart_available": False}

    def _foreign_hub_warning(self) -> str:
        hub_pids = self._hub_listener_pids()
        if not hub_pids:
            return ""
        owned = self._owned_runtime_pid("hub")
        if owned is None or owned not in hub_pids:
            return "Порт 8765 занят внешним hub/process; GUI не будет убивать его автоматически."
        return ""

    def _count_stale_runtime_files(self) -> int:
        stale = 0
        cdp_dir = RUNTIME_DIR / "cdp"
        state_paths = list(cdp_dir.glob("*.json")) if cdp_dir.exists() else []
        for state_path in state_paths:
            try:
                payload = json.loads(state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                stale += 1
                continue
            try:
                port = int(payload.get("port") or 0)
            except (TypeError, ValueError):
                stale += 1
                continue
            if port <= 0 or not _cdp_debugger_ready(port):
                stale += 1
        return stale

    def _prune_runtime_artifacts(self) -> None:
        for directory in (ACTION_LOG_DIR, RUNTIME_DIR / "cdp", RUNTIME_OWNERS_DIR):
            if not directory.exists():
                continue
            files = sorted((item for item in directory.iterdir() if item.is_file()), key=lambda path: path.stat().st_mtime, reverse=True)
            for extra in files[40:]:
                try:
                    extra.unlink()
                except OSError:
                    continue

    def _list_clients(self, token: str) -> list[dict[str, Any]]:
        payload = export_mod._http_json_retry(HUB_URL, token, "GET", "/api/clients", retries=2, request_timeout_sec=2.0)
        clients = payload.get("clients") or []
        return clients if isinstance(clients, list) else []

    def _resolve_best_client(
        self,
        token: str,
        *,
        known_client_ids: set[str | None],
        require_online: bool,
    ) -> BrowserTarget | None:
        clients = self._list_clients(token)
        rows: list[tuple[int, int, int, str, str, int, str, str]] = []
        for client in clients:
            client_id = str(client.get("client_id") or "").strip()
            if not client_id:
                continue
            is_online = 1 if bool(client.get("is_online")) else 0
            if require_online and not is_online:
                continue
            tabs = client.get("tabs") or []
            if not isinstance(tabs, list):
                tabs = []
            telegram_tabs = [tab for tab in tabs if "web.telegram.org" in str(tab.get("url") or "")]
            if not telegram_tabs:
                continue
            selected_tab = _pick_telegram_tab(telegram_tabs)
            if not selected_tab:
                continue
            tab_id = selected_tab.get("id")
            if not isinstance(tab_id, int):
                continue
            is_new = 1 if client_id not in known_client_ids else 0
            dialog_tab = 1 if "/#" in str(selected_tab.get("url") or "") else 0
            last_seen = str(client.get("last_seen") or "")
            rows.append(
                (
                    is_new,
                    is_online,
                    dialog_tab,
                    last_seen,
                    client_id,
                    tab_id,
                    _clean_tab_title(str(selected_tab.get("title") or "")),
                    str(selected_tab.get("url") or ""),
                )
            )
        if not rows:
            return None
        rows.sort(reverse=True)
        _is_new, _is_online, _dialog_tab, _last_seen, client_id, tab_id, title, url = rows[0]
        return BrowserTarget(client_id=client_id, tab_id=tab_id, tab_title=title, tab_url=url)

    def _refresh_target(self, token: str, client_id: str, tab_id: int) -> BrowserTarget:
        clients = self._list_clients(token)
        selected_online = False
        for client in clients:
            if str(client.get("client_id") or "").strip() != client_id:
                continue
            selected_online = bool(client.get("is_online"))
            break
        if not selected_online:
            replacement = self._resolve_best_client(token, known_client_ids=set(), require_online=True)
            if replacement is None:
                raise RuntimeError("Нет живого Telegram-клиента. Нажмите 'Подключить Telegram'.")
            return replacement
        try:
            resolved_client_id, resolved_tab_id = export_mod._find_tab(clients, client_id=client_id, tab_id=tab_id, url_pattern="")
        except RuntimeError:
            resolved_client_id, resolved_tab_id = export_mod._find_tab(clients, client_id=client_id, tab_id=None, url_pattern="")
        tab_url, tab_title = export_mod._get_tab_meta_best_effort(HUB_URL, token, resolved_client_id, resolved_tab_id, timeout_sec=1.2)
        return BrowserTarget(
            client_id=resolved_client_id,
            tab_id=resolved_tab_id,
            tab_title=_clean_tab_title(tab_title),
            tab_url=str(tab_url or ""),
        )

    def _log_action(self, message: str) -> None:
        self.action_log_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        with self.action_log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{timestamp}\t{message}\n")

    def _wait_for_chat_list_ready(self, token: str, client_id: str, tab_id: int) -> None:
        export_mod._send_command_result(
            server=HUB_URL,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=4,
            command={
                "type": "wait_selector",
                "selector": CHAT_LIST_READY_SELECTOR,
                "timeout_ms": 3000,
                "visible_only": False,
            },
            raise_on_fail=False,
        )


class TelegramMembersExportWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application, backend: TelegramGuiBackend):
        super().__init__(application=app, title=WINDOW_TITLE)
        self.set_default_size(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.set_resizable(True)
        self.backend = backend

        self.accounts: list[AccountOption] = []
        self.account_map: dict[str, AccountOption] = {}
        self.portable_profiles: list[PortableProfileStatus] = []
        self.portable_profile_map: dict[str, PortableProfileStatus] = {}
        self.chat_rows: list[ChatOption] = []
        self.filtered_chat_rows: list[ChatOption] = []
        self.connected_target: BrowserTarget | None = None
        self.current_task: str | None = None
        self.current_controller: TaskController | None = None
        self.last_export_result: ExportResult | None = None
        self.export_progress_state: ExportProgressState | None = None
        self.last_session: SessionResumeState | None = None
        self.recent_runs: list[RunRecord] = []
        self.history_filter = "all"
        self.pinned_chats = self.backend.run_history.load_pinned_chats()
        self.ui_tasks = UiTaskService(idle_add=GLib.idle_add)
        self.preflight_info: PreflightInfo | None = None
        self._bootstrap_started = False
        self._ui_syncing = False
        self._preflight_revision = 0
        self._close_after_task = False

        self.window_scroll = Gtk.ScrolledWindow()
        self.root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.root_box.set_margin_top(18)
        self.root_box.set_margin_bottom(18)
        self.root_box.set_margin_start(18)
        self.root_box.set_margin_end(18)
        self.root_box.set_valign(Gtk.Align.START)
        self.window_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.window_scroll.set_child(self.root_box)
        self.set_child(self.window_scroll)

        self.hero_status = Gtk.Label(label="Не подключено")
        self.security_status = Gtk.Label(label="Security pending")
        self.connection_status = Gtk.Label(label="Telegram не подключён")
        self.preset_status = Gtk.Label(label="Full History")
        self.client_label = Gtk.Label(label="Клиент Telegram не выбран")
        self.chat_meta_label = Gtk.Label(label="Список чатов ещё не загружен")
        self.chat_title_label = Gtk.Label(label="Чат не выбран")
        self.chat_url_label = Gtk.Label(label="")
        self.last_run_label = Gtk.Label(label="Последний запуск ещё не выполнялся")
        self.output_entry = Gtk.Entry()
        self.search_entry = Gtk.SearchEntry()
        self.chat_target_entry = Gtk.Entry()
        self.account_combo = Gtk.ComboBoxText()
        self.chat_listbox = Gtk.ListBox()
        self.quick_chat_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.preset_combo = Gtk.ComboBoxText()
        self.surface_badge_label = Gtk.Label(label="Surface pending")
        self.preflight_panel = PreflightPanel()
        self.fallback_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.fallback_title_label = Gtk.Label(label="Fallback required")
        self.fallback_bridge_label = Gtk.Label(label="Bridge: pending")
        self.fallback_cdp_label = Gtk.Label(label="CDP: pending")
        self.fallback_hint_label = Gtk.Label(label="Secondary surfaces будут проверяться для выбранного профиля.")
        self.fallback_prepare_bridge_button = Gtk.Button(label="Подготовить bridge profile")
        self.fallback_retry_button = Gtk.Button(label="Повторить проверку")
        self.portable_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.portable_title_label = Gtk.Label(label="Portable tdata")
        self.portable_profile_combo = Gtk.ComboBoxText()
        self.portable_source_label = Gtk.Label(label="Источник ещё не выбран")
        self.portable_runtime_label = Gtk.Label(label="Runtime state: pending")
        self.portable_feedback_label = Gtk.Label(label="")
        self.portable_add_button = Gtk.Button(label="Импортировать tdata.zip")
        self.portable_adopt_button = Gtk.Button(label="Подключить существующую папку")
        self.portable_launch_button = Gtk.Button(label="Запустить профиль")
        self.portable_refresh_button = Gtk.Button(label="Обновить статус")
        self.portable_remove_button = Gtk.Button(label="Убрать из панели")
        self.portable_remove_revealer = Gtk.Revealer()
        self.portable_remove_detail_label = Gtk.Label(label="")
        self.security_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.security_title_label = Gtk.Label(label="Secure token setup")
        self.security_detail_label = Gtk.Label(label="Выберите профиль, чтобы увидеть security status.")
        self.security_feedback_label = Gtk.Label(label="")
        self.security_setup_button = Gtk.Button(label="Настроить secure token")
        self.security_restart_button = Gtk.Button(label="Перезапустить hub этим токеном")
        self.security_form_revealer = Gtk.Revealer()
        self.security_token_entry = Gtk.Entry()
        self.run_stack = Gtk.Stack()
        self.run_switcher = Gtk.StackSwitcher(stack=self.run_stack)
        self.progress_panel = ProgressPanel()
        self.artifact_panel = ArtifactPanel(self._open_artifact_item, self._open_artifact_parent, self._copy_artifact_path)
        self.history_panel = HistoryPanel()
        self.log_buffer = self.progress_panel.log_buffer
        self.log_view = self.progress_panel.log_view
        self.progress_bar = self.progress_panel.progress_bar
        self.progress_status_label = self.progress_panel.progress_status_label
        self.progress_meta_label = self.progress_panel.progress_meta_label
        self.progress_hint_label = self.progress_panel.progress_hint_label
        self.result_label = self.artifact_panel.summary_label
        self.stop_button = Gtk.Button(label="Остановить сбор")
        self.history_panel.listbox.connect("row-selected", lambda *_args: self._on_history_selected())
        self.history_panel.bind_filter(self._set_history_filter)

        self._build_ui()
        self.connect("close-request", self._on_close_request)
        self._apply_preflight_info(
            self.backend.build_preflight(
                account=None,
                output_path=None,
                preset_key=self._selected_preset_key(),
                connected_target=None,
                deep=False,
            )
        )
        GLib.idle_add(self._apply_initial_window_geometry)
        GLib.timeout_add(250, self._tick_progress)

    def bootstrap_async(self) -> None:
        if self._bootstrap_started:
            return
        self._bootstrap_started = True
        self.hero_status.set_label("Загружаем профили...")
        self.client_label.set_label("Панель открыта. Профили и preflight догружаются в фоне.")
        self.chat_meta_label.set_label("Список чатов загрузится после выбора профиля и подключения Telegram.")
        self._append_log("Загружаем профили и preflight в фоне...")
        self.ui_tasks.start(
            worker=self._collect_accounts_snapshot,
            on_success=self._handle_bootstrap_loaded,
            on_error=self._handle_bootstrap_failed,
        )

    def _build_ui(self) -> None:
        self.root_box.append(self._build_hero())
        self.root_box.append(self._build_status_strip())
        split = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        split.set_vexpand(True)
        self.root_box.append(split)

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        left.set_hexpand(True)
        left.set_vexpand(True)
        left.add_css_class("card")
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        right.set_hexpand(True)
        right.set_vexpand(True)
        right.add_css_class("card")

        split.append(left)
        split.append(right)

        left.append(self._build_account_section())
        left.append(self._build_chat_section())
        left.append(self._build_export_section())

        right.append(self._build_run_center())

    def _build_hero(self) -> Gtk.Widget:
        hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        hero.add_css_class("hero")

        title = Gtk.Label(label="Telegram Username Collector")
        title.set_xalign(0)
        title.add_css_class("hero-title")
        copy = Gtk.Label(
            label="Операторский поток: профиль -> чат -> файл -> старт. Основной path: tdata-history-authors.",
            wrap=True,
            justify=Gtk.Justification.LEFT,
            xalign=0,
        )
        copy.add_css_class("hero-copy")
        self.last_run_label.set_xalign(0)
        self.last_run_label.set_wrap(True)
        self.last_run_label.add_css_class("meta")
        hero.append(title)
        hero.append(copy)
        hero.append(self.last_run_label)
        return hero

    def _build_status_strip(self) -> Gtk.Widget:
        strip = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        strip.add_css_class("status-strip")
        for widget in (self.hero_status, self.surface_badge_label, self.preset_status, self.connection_status, self.security_status):
            widget.add_css_class("badge")
            strip.append(widget)
        return strip

    def _build_account_section(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.append(self._section_title("1. Профиль и подключение"))

        self.account_combo.set_hexpand(True)
        self.account_combo.connect("changed", lambda *_args: self._on_account_changed())
        box.append(self.account_combo)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.append(self._button("Подключить Telegram", self._connect_selected_account, accent=True))
        actions.append(self._button("Импортировать tdata.zip", self._choose_portable_zip))
        actions.append(self._button("Обновить профили", self._load_accounts_into_ui))
        box.append(actions)

        self.client_label.set_xalign(0)
        self.client_label.set_wrap(True)
        self.client_label.add_css_class("meta")
        box.append(self.client_label)
        box.append(self._build_portable_card())
        return box

    def _build_chat_section(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_vexpand(True)
        box.append(self._section_title("2. Чаты и группы из Telegram"))

        self.search_entry.set_hexpand(True)
        self.search_entry.set_placeholder_text("Фильтр по названию, описанию или URL")
        self.search_entry.connect("search-changed", lambda *_args: self._apply_chat_filter())
        box.append(self.search_entry)

        resolve_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.chat_target_entry.set_hexpand(True)
        self.chat_target_entry.set_placeholder_text("https://t.me/cosmetologna, @cosmetologna или peer id")
        self.chat_target_entry.connect("activate", lambda *_args: self._resolve_chat_target())
        resolve_row.append(self.chat_target_entry)
        resolve_row.append(self._button("Открыть чат по ссылке / @username", self._resolve_chat_target))
        box.append(resolve_row)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.append(self._button("Обновить список", self._refresh_chats))
        actions.append(self._button("Открыть чат", self._open_selected_chat))
        actions.append(self._button("Закрепить чат", self._pin_selected_chat))
        box.append(actions)

        quick_title = self._meta_label("Pinned / recent")
        box.append(quick_title)
        self.quick_chat_box.add_css_class("dim-box")
        box.append(self.quick_chat_box)

        self.chat_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.chat_listbox.connect("row-selected", lambda *_args: self._on_chat_selected())
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(self.chat_listbox)
        box.append(scroll)

        self.chat_meta_label.set_xalign(0)
        self.chat_meta_label.set_wrap(True)
        self.chat_meta_label.add_css_class("meta")
        box.append(self.chat_meta_label)
        return box

    def _build_export_section(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.append(self._section_title("3. Экспорт и preflight"))

        self.chat_title_label.set_xalign(0)
        self.chat_title_label.set_wrap(True)
        self.chat_title_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.chat_title_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.chat_title_label.set_lines(2)
        self.chat_title_label.set_max_width_chars(44)
        self.chat_title_label.add_css_class("card-title")
        box.append(self.chat_title_label)

        self.chat_url_label.set_xalign(0)
        self.chat_url_label.set_wrap(True)
        self.chat_url_label.add_css_class("meta")
        box.append(self.chat_url_label)

        preset_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        preset_title = self._meta_label("Preset")
        preset_title.set_size_request(92, -1)
        preset_row.append(preset_title)
        self.preset_combo.set_hexpand(True)
        for key, label in RUN_PRESETS:
            self.preset_combo.append(key, label)
        self.preset_combo.set_active_id("full_history")
        self.preset_combo.connect("changed", lambda *_args: self._on_preset_changed())
        preset_row.append(self.preset_combo)
        box.append(preset_row)

        box.append(self.preflight_panel)
        box.append(self._build_fallback_card())
        box.append(self._build_security_card())

        self.output_entry.set_hexpand(True)
        self.output_entry.set_placeholder_text("Путь к .md файлу")
        self.output_entry.connect("changed", lambda *_args: self._on_output_path_changed())
        choose_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        choose_row.append(self.output_entry)
        choose_row.append(self._button("Выбрать .md файл", self._choose_output_file))
        box.append(choose_row)
        box.append(self._meta_label("Откроется системный диалог: там выбираются и папка, и имя итогового файла."))

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.append(self._button("Собрать @username", self._run_export, accent=True))
        actions.append(self._button("Повторить последний запуск", self._repeat_last_run))
        self.stop_button.connect("clicked", lambda *_args: self._request_stop())
        self.stop_button.add_css_class("subtle-button")
        self.stop_button.set_sensitive(False)
        actions.append(self.stop_button)
        box.append(actions)
        bottom_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bottom_actions.append(self._button("Открыть папку результата", self._open_result_directory))
        bottom_actions.append(self._button("Открыть последние артефакты", self._open_last_artifacts))
        box.append(bottom_actions)
        return box

    def _build_security_card(self) -> Gtk.Widget:
        self.security_card.add_css_class("dim-box")
        self.security_title_label.set_xalign(0)
        self.security_title_label.add_css_class("card-title")
        self.security_detail_label.set_xalign(0)
        self.security_detail_label.set_wrap(True)
        self.security_detail_label.add_css_class("meta")
        self.security_feedback_label.set_xalign(0)
        self.security_feedback_label.set_wrap(True)
        self.security_feedback_label.add_css_class("meta")

        action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.security_setup_button.add_css_class("subtle-button")
        self.security_setup_button.connect("clicked", lambda *_args: self._show_security_setup_form())
        self.security_restart_button.add_css_class("subtle-button")
        self.security_restart_button.connect("clicked", lambda *_args: self._restart_owned_hub_with_selected_token())
        action_row.append(self.security_setup_button)
        action_row.append(self.security_restart_button)

        form_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.security_token_entry.set_visibility(False)
        self.security_token_entry.set_hexpand(True)
        self.security_token_entry.set_placeholder_text("Введите secure token")
        form_box.append(self.security_token_entry)
        form_box.append(
            self._meta_label("После сохранения quickstart-token больше не будет использоваться для этого профиля.")
        )
        form_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        save_button = Gtk.Button(label="Сохранить secure token")
        save_button.add_css_class("accent-button")
        save_button.connect("clicked", lambda *_args: self._save_security_token_inline())
        cancel_button = Gtk.Button(label="Отмена")
        cancel_button.add_css_class("subtle-button")
        cancel_button.connect("clicked", lambda *_args: self._cancel_security_setup())
        form_actions.append(save_button)
        form_actions.append(cancel_button)
        form_box.append(form_actions)
        self.security_form_revealer.set_child(form_box)
        self.security_form_revealer.set_reveal_child(False)

        self.security_card.append(self.security_title_label)
        self.security_card.append(self.security_detail_label)
        self.security_card.append(action_row)
        self.security_card.append(self.security_form_revealer)
        self.security_card.append(self.security_feedback_label)
        self.security_card.set_visible(False)
        return self.security_card

    def _build_portable_card(self) -> Gtk.Widget:
        self.portable_card.add_css_class("dim-box")
        self.portable_title_label.set_xalign(0)
        self.portable_title_label.add_css_class("card-title")
        self.portable_profile_combo.set_hexpand(True)
        self.portable_profile_combo.connect("changed", lambda *_args: self._on_portable_profile_changed())
        for widget in (
            self.portable_source_label,
            self.portable_runtime_label,
            self.portable_feedback_label,
            self.portable_remove_detail_label,
        ):
            widget.set_xalign(0)
            widget.set_wrap(True)
            widget.add_css_class("meta")
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.append(self._meta_label("Текущий профиль"))
        row.append(self.portable_profile_combo)
        import_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.portable_add_button.add_css_class("subtle-button")
        self.portable_add_button.connect("clicked", lambda *_args: self._choose_portable_zip())
        self.portable_adopt_button.add_css_class("subtle-button")
        self.portable_adopt_button.connect("clicked", lambda *_args: self._choose_existing_portable_folder())
        self.portable_launch_button.add_css_class("subtle-button")
        self.portable_launch_button.connect("clicked", lambda *_args: self._launch_selected_portable_profile())
        self.portable_refresh_button.add_css_class("subtle-button")
        self.portable_refresh_button.connect("clicked", lambda *_args: self._refresh_selected_portable_profile())
        self.portable_remove_button.add_css_class("subtle-button")
        self.portable_remove_button.connect("clicked", lambda *_args: self._show_remove_portable_profile_confirmation())
        import_row.append(self.portable_add_button)
        import_row.append(self.portable_adopt_button)
        action_row.append(self.portable_launch_button)
        action_row.append(self.portable_refresh_button)
        action_row.append(self.portable_remove_button)
        remove_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        remove_box.append(self.portable_remove_detail_label)
        remove_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        confirm_button = Gtk.Button(label="Подтвердить")
        confirm_button.add_css_class("accent-button")
        confirm_button.connect("clicked", lambda *_args: self._confirm_remove_selected_portable_profile())
        cancel_button = Gtk.Button(label="Отмена")
        cancel_button.add_css_class("subtle-button")
        cancel_button.connect("clicked", lambda *_args: self._cancel_remove_portable_profile())
        remove_actions.append(confirm_button)
        remove_actions.append(cancel_button)
        remove_box.append(remove_actions)
        self.portable_remove_revealer.set_child(remove_box)
        self.portable_remove_revealer.set_reveal_child(False)
        self.portable_card.append(self.portable_title_label)
        self.portable_card.append(row)
        self.portable_card.append(self.portable_source_label)
        self.portable_card.append(self.portable_runtime_label)
        self.portable_card.append(import_row)
        self.portable_card.append(action_row)
        self.portable_card.append(self.portable_remove_revealer)
        self.portable_card.append(self.portable_feedback_label)
        self.portable_card.set_visible(False)
        return self.portable_card

    def _build_fallback_card(self) -> Gtk.Widget:
        self.fallback_card.add_css_class("dim-box")
        self.fallback_title_label.set_xalign(0)
        self.fallback_title_label.add_css_class("card-title")
        for widget in (self.fallback_bridge_label, self.fallback_cdp_label, self.fallback_hint_label):
            widget.set_xalign(0)
            widget.set_wrap(True)
            widget.add_css_class("meta")
        action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.fallback_prepare_bridge_button.add_css_class("subtle-button")
        self.fallback_prepare_bridge_button.connect("clicked", lambda *_args: self._prepare_bridge_profile())
        self.fallback_retry_button.add_css_class("subtle-button")
        self.fallback_retry_button.connect("clicked", lambda *_args: self._retry_fallback_readiness())
        action_row.append(self.fallback_prepare_bridge_button)
        action_row.append(self.fallback_retry_button)
        self.fallback_card.append(self.fallback_title_label)
        self.fallback_card.append(self.fallback_bridge_label)
        self.fallback_card.append(self.fallback_cdp_label)
        self.fallback_card.append(self.fallback_hint_label)
        self.fallback_card.append(action_row)
        self.fallback_card.set_visible(False)
        return self.fallback_card

    def _build_run_center(self) -> Gtk.Widget:
        wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        wrapper.set_vexpand(True)
        wrapper.append(self._section_title("Execution Center"))
        wrapper.append(self.run_switcher)
        self.run_stack.set_vexpand(True)
        self.run_stack.add_titled(self.progress_panel, "progress", "Прогресс")
        self.run_stack.add_titled(self.artifact_panel, "artifacts", "Артефакты")
        self.run_stack.add_titled(self.history_panel, "history", "История")
        wrapper.append(self.run_stack)
        self._append_log("Приложение готово. Выберите профиль и подключите Telegram.")
        return wrapper

    def _section_title(self, text: str) -> Gtk.Widget:
        label = Gtk.Label(label=text)
        label.set_xalign(0)
        label.add_css_class("card-title")
        return label

    def _meta_label(self, text: str) -> Gtk.Widget:
        label = Gtk.Label(label=text)
        label.set_xalign(0)
        label.set_wrap(True)
        label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        label.add_css_class("meta")
        return label

    def _button(self, text: str, callback: Callable[[], None], *, accent: bool = False) -> Gtk.Widget:
        button = Gtk.Button(label=text)
        button.connect("clicked", lambda *_args: callback())
        button.add_css_class("accent-button" if accent else "subtle-button")
        return button

    def _reset_progress_display(self) -> None:
        self.export_progress_state = None
        self.progress_bar.set_fraction(0.0)
        self.progress_bar.set_text("Ожидание")
        self.progress_status_label.set_label("Прогресс появится после старта экспорта")
        self.progress_meta_label.set_label("Сообщений: 0 | @username: 0")
        self.progress_hint_label.set_label(
            "Долгие чаты сканируются по истории. Кнопка остановки активируется во время сбора."
        )
        self.stop_button.set_sensitive(False)

    def _begin_export_progress(self, chat: ChatOption) -> None:
        now = time.monotonic()
        history_limit, _timeout_sec = self.backend.preset_limits(self._selected_preset_key())
        self.export_progress_state = ExportProgressState(
            chat_ref=chat.fragment,
            started_at=now,
            last_update_at=now,
            stage="start",
            failed=False,
            total_messages_hint=_positive_int(history_limit),
        )
        self.stop_button.set_sensitive(True)
        self.run_stack.set_visible_child(self.progress_panel)
        self._render_progress_state()

    def _request_stop(self) -> None:
        if self.current_task != "export" or self.current_controller is None:
            self._show_warning("Сейчас нечего останавливать.")
            return
        if self.export_progress_state is not None and self.export_progress_state.done:
            self.stop_button.set_sensitive(False)
            return
        if self.current_controller.cancel_requested:
            return
        self.current_controller.request_cancel()
        self.hero_status.set_label("Останавливаем...")
        self.stop_button.set_sensitive(False)
        if self.export_progress_state is not None:
            self.export_progress_state.stage = "stop-requested"
            self.export_progress_state.last_update_at = time.monotonic()
        self._append_log("Запрошена остановка текущего экспорта.")
        self._render_progress_state()

    def _close_window_now(self) -> bool:
        app = self.get_application()
        if app is not None:
            app.quit()
        else:
            self.destroy()
        return False

    def _finalize_pending_close(self) -> None:
        if not self._close_after_task:
            return
        self._close_after_task = False
        self._append_log("Закрываем окно после завершения операции.")
        GLib.idle_add(self._close_window_now)

    def _on_close_request(self, *_args: Any) -> bool:
        if self.current_task != "export" or self.current_controller is None:
            GLib.idle_add(self._close_window_now)
            return False
        if self.export_progress_state is not None and self.export_progress_state.done:
            GLib.idle_add(self._close_window_now)
            return False
        self._close_after_task = True
        if not self.current_controller.cancel_requested:
            self.current_controller.request_cancel()
        self.hero_status.set_label("Останавливаем и закрываем...")
        if self.export_progress_state is not None:
            self.export_progress_state.stage = "stop-requested"
            self.export_progress_state.last_update_at = time.monotonic()
        self._append_log("Запрошено закрытие окна после мягкой остановки экспорта.")
        self._render_progress_state()
        return True

    def _consume_progress_message(self, message: str) -> None:
        event = ProgressEvent.from_progress_line(parse_progress_line(message))
        if not event.stage and not event.done and not event.interrupted and event.messages_scanned == 0 and event.usernames_found == 0:
            return
        state = self.export_progress_state
        now = time.monotonic()
        if state is None:
            state = ExportProgressState(
                chat_ref=event.chat_ref,
                started_at=now,
                last_update_at=now,
                total_messages_hint=_positive_int(self.backend.preset_limits(self._selected_preset_key())[0]),
            )
            self.export_progress_state = state
        state.chat_ref = event.chat_ref or state.chat_ref
        state.messages_scanned = max(state.messages_scanned, event.messages_scanned)
        state.usernames_found = max(state.usernames_found, event.usernames_found)
        state.last_update_at = now
        state.interrupted = event.interrupted
        state.done = event.done
        state.failed = False
        state.stage = event.stage or ("done" if state.done else state.stage or "scan")
        if state.done:
            self.stop_button.set_sensitive(False)
        self._render_progress_state()

    def _render_progress_state(self) -> None:
        state = self.export_progress_state
        if state is None:
            return
        elapsed = max(int(time.monotonic() - state.started_at), 0)
        since_update = max(int(time.monotonic() - state.last_update_at), 0)
        if state.total_messages_hint and state.messages_scanned > 0:
            fraction = min(state.messages_scanned / max(state.total_messages_hint, 1), 1.0)
            self.progress_bar.set_fraction(fraction)
        elif not state.done:
            self.progress_bar.pulse()
        elif state.interrupted or state.failed:
            self.progress_bar.set_fraction(0.0)
        else:
            self.progress_bar.set_fraction(1.0)
        self.progress_bar.set_text(f"{state.messages_scanned} сообщений / {state.usernames_found} @username")

        if state.done and state.interrupted:
            status = "Сбор остановлен пользователем"
        elif state.done and state.failed:
            status = "Сканирование остановилось с ошибкой"
        elif state.done:
            status = "Сканирование истории завершено"
        elif self.current_controller is not None and self.current_controller.cancel_requested:
            status = "Останавливаем после текущего шага истории..."
        elif state.stage == "start" and state.messages_scanned == 0:
            status = "Подключаемся к истории Telegram..."
        else:
            status = "Идёт сканирование истории Telegram"
        self.progress_status_label.set_label(status)

        scope = (
            f"Лимит истории: {state.total_messages_hint} сообщений"
            if state.total_messages_hint
            else "Лимит истории: полный доступный чат"
        )
        self.progress_meta_label.set_label(
            f"Сообщений: {state.messages_scanned} | @username: {state.usernames_found} | Время: {_format_duration(elapsed)} | {scope}"
        )
        self.progress_hint_label.set_label(
            f"Последнее обновление: {since_update}s назад. Чат: {state.chat_ref or '—'}."
        )
        progress_panel = getattr(self, "progress_panel", None)
        if progress_panel is not None and hasattr(progress_panel, "set_summary"):
            progress_panel.set_summary(
                status,
                f"messages={state.messages_scanned} | safe-progress={state.usernames_found} | elapsed={_format_duration(elapsed)}",
            )

    def _tick_progress(self) -> bool:
        if self.current_task == "export" and self.export_progress_state is not None:
            self._render_progress_state()
        return True

    def _apply_initial_window_geometry(self) -> bool:
        display = self.get_display()
        monitor = display.get_monitors().get_item(0) if display is not None and display.get_monitors() is not None else None
        if monitor is None:
            return False
        geometry = monitor.get_geometry()
        width = max(860, min(920, int(geometry.width) - 160))
        height = max(620, min(640, int(geometry.height) - 140))
        self.set_default_size(width, height)
        return False

    def _collect_accounts_snapshot(self) -> tuple[list[AccountOption], SessionResumeState | None, list[RunRecord], list[PortableProfileStatus]]:
        return (
            self.backend.load_accounts(),
            self.backend.load_last_session(),
            self.backend.load_recent_runs(),
            self.backend.load_portable_profiles(),
        )

    def _handle_bootstrap_loaded(
        self,
        payload: tuple[list[AccountOption], SessionResumeState | None, list[RunRecord], list[PortableProfileStatus]],
    ) -> bool:
        self._apply_accounts_snapshot(payload, schedule_deep=True)
        return False

    def _handle_bootstrap_failed(self, exc: Exception) -> bool:
        text = self._sanitize_text(str(exc))
        self.hero_status.set_label("Ошибка старта")
        self.client_label.set_label(text)
        self.chat_meta_label.set_label("Панель не смогла загрузить профили. Исправьте проблему и нажмите 'Обновить профили'.")
        self.fallback_card.set_visible(False)
        self.security_card.set_visible(False)
        self.portable_feedback_label.set_label(text)
        self._append_log(f"Ошибка bootstrap: {text}")
        return False

    def _apply_accounts_snapshot(
        self,
        payload: tuple[list[AccountOption], SessionResumeState | None, list[RunRecord], list[PortableProfileStatus]],
        *,
        preferred_account_key: str = "",
        preferred_profile_source: str = "",
        preserve_output: str = "",
        schedule_deep: bool = True,
    ) -> None:
        accounts, last_session, recent_runs, portable_profiles = payload
        self.accounts = accounts
        self.last_session = last_session
        self.recent_runs = recent_runs
        self.portable_profiles = portable_profiles
        self.account_map = {item.label: item for item in self.accounts}
        self._ui_syncing = True
        try:
            self.account_combo.remove_all()
            for item in self.accounts:
                self.account_combo.append_text(item.label)
            if self.accounts:
                target_index = 0
                for index, item in enumerate(self.accounts):
                    if preferred_account_key and item.key == preferred_account_key:
                        target_index = index
                        break
                    if preferred_profile_source and _normalize_path_key(item.profile_source) == _normalize_path_key(preferred_profile_source):
                        target_index = index
                        break
                self.account_combo.set_active(target_index)
                self._append_log(f"Профили загружены: {len(self.accounts)}")
                self._load_portable_profiles_into_ui(
                    portable_profiles=self.portable_profiles,
                    preferred_profile_source=preferred_profile_source or self.accounts[target_index].profile_source,
                )
                if preserve_output:
                    self.output_entry.set_text(preserve_output)
            else:
                self._load_portable_profiles_into_ui(
                    portable_profiles=self.portable_profiles,
                    preferred_profile_source=preferred_profile_source,
                )
        finally:
            self._ui_syncing = False
        if self.accounts:
            self._on_account_changed(schedule_deep=schedule_deep)
        else:
            self.hero_status.set_label("Нет профиля")
            self.client_label.set_label("Профили не найдены. Положите Telegram-профиль в ~/.site-control-kit/telegram_workspace/accounts/1/profile")
            self.fallback_card.set_visible(False)
            self.security_card.set_visible(False)
            self._append_log("Профили не найдены")
        self._refresh_history_panel()
        self._refresh_quick_chats()

    def _load_accounts_into_ui(
        self,
        *,
        preferred_account_key: str = "",
        preferred_profile_source: str = "",
        preserve_output: str = "",
    ) -> None:
        try:
            payload = self._collect_accounts_snapshot()
        except Exception as exc:
            self._show_error(str(exc))
            return
        self._apply_accounts_snapshot(
            payload,
            preferred_account_key=preferred_account_key,
            preferred_profile_source=preferred_profile_source,
            preserve_output=preserve_output,
            schedule_deep=True,
        )

    def _load_portable_profiles_into_ui(
        self,
        *,
        portable_profiles: list[PortableProfileStatus] | None = None,
        preferred_profile_source: str = "",
    ) -> None:
        if portable_profiles is None:
            try:
                portable_profiles = self.backend.load_portable_profiles()
            except Exception as exc:
                self.portable_profiles = []
                self.portable_profile_map = {}
                self.portable_profile_combo.remove_all()
                self.portable_feedback_label.set_label(self._sanitize_text(str(exc)))
                return
        self.portable_profiles = portable_profiles
        self.portable_profile_map = {}
        self.portable_profile_combo.remove_all()
        selected_key = _normalize_path_key(preferred_profile_source)
        current_account = self._selected_account()
        if not selected_key and current_account is not None:
            selected_key = _normalize_path_key(current_account.portable_profile_dir or current_account.profile_source)
        matched_index = -1
        for index, status in enumerate(self.portable_profiles):
            label = portable_profile_label(status)
            profile_id = str(status.profile_dir)
            self.portable_profile_map[profile_id] = status
            self.portable_profile_combo.append(profile_id, label)
            if selected_key and _normalize_path_key(str(status.profile_dir)) == selected_key:
                matched_index = index
        if matched_index >= 0:
            self.portable_profile_combo.set_active(matched_index)
        else:
            self.portable_profile_combo.set_active(-1)

    def _selected_account(self) -> AccountOption | None:
        label = self.account_combo.get_active_text()
        return self.account_map.get(label) if label else None

    def _selected_portable_profile(self) -> PortableProfileStatus | None:
        profile_id = self.portable_profile_combo.get_active_id()
        return self.portable_profile_map.get(profile_id) if profile_id else None

    def _active_portable_profile(self) -> PortableProfileStatus | None:
        account = self._selected_account()
        info_profile = self.preflight_info.portable_profile if self.preflight_info is not None else None
        if account is not None and info_profile is not None:
            if _normalize_path_key(str(info_profile.profile_dir)) == _normalize_path_key(account.profile_source):
                return info_profile
        return self._selected_portable_profile()

    def _selected_chat(self) -> ChatOption | None:
        row = self.chat_listbox.get_selected_row()
        return getattr(row, "chat", None) if row is not None else None

    def _selected_preset_key(self) -> str:
        return str(self.preset_combo.get_active_id() or "full_history")

    def _on_output_path_changed(self) -> None:
        if self._ui_syncing:
            return
        self._refresh_preflight()

    def _refresh_preflight(self, *, schedule_deep: bool = False) -> None:
        account = self._selected_account()
        info = self.backend.build_preflight(
            account=account,
            output_path=Path(self.output_entry.get_text().strip()).expanduser() if self.output_entry.get_text().strip() else None,
            preset_key=self._selected_preset_key(),
            connected_target=self.connected_target,
            deep=False,
        )
        self._apply_preflight_info(info)
        if schedule_deep and account is not None and account.availability_state != "missing":
            self._queue_deep_preflight(account)

    def _apply_preflight_info(self, info: PreflightInfo) -> None:
        self.preflight_info = info
        self.surface_badge_label.set_label(info.surface_badge)
        self.preflight_panel.set_info(info)
        self.security_status.set_label(info.security_mode or "Security pending")
        self.preset_status.set_label(info.preset_label)
        account = self._selected_account()
        self._refresh_portable_card(info, account)
        self._refresh_fallback_card(info, account)
        self._refresh_security_card(info, account)
        if self.connected_target is not None:
            self.connection_status.set_label("Connected")
        elif info.surface_key == "tdata" and info.tdata_ready:
            self.connection_status.set_label("Primary ready")
        else:
            self.connection_status.set_label("Not connected")

    def _queue_deep_preflight(self, account: AccountOption) -> None:
        self._preflight_revision += 1
        revision = self._preflight_revision
        output_path = Path(self.output_entry.get_text().strip()).expanduser() if self.output_entry.get_text().strip() else None
        preset_key = self._selected_preset_key()
        connected_target = self.connected_target
        account_key = account.key

        self.ui_tasks.start(
            worker=lambda: self.backend.build_preflight(
                account=account,
                output_path=output_path,
                preset_key=preset_key,
                connected_target=connected_target,
                deep=True,
            ),
            on_success=lambda _info, rev=revision, key=account_key: self._handle_deep_preflight_complete(rev, key),
            on_error=lambda exc, rev=revision, key=account_key: self._handle_deep_preflight_error(rev, key, exc),
        )

    def _handle_deep_preflight_complete(self, revision: int, account_key: str) -> bool:
        current_account = self._selected_account()
        if revision != self._preflight_revision or current_account is None or current_account.key != account_key:
            return False
        self._refresh_preflight()
        return False

    def _handle_deep_preflight_error(self, revision: int, account_key: str, exc: Exception) -> bool:
        current_account = self._selected_account()
        if revision != self._preflight_revision or current_account is None or current_account.key != account_key:
            return False
        text = self._sanitize_text(str(exc))
        self._append_log(f"Background preflight error: {text}")
        if current_account.availability_state == "missing":
            self.portable_feedback_label.set_label(text)
        return False

    def _refresh_fallback_card(self, info: PreflightInfo, account: AccountOption | None) -> None:
        visible = account is not None and info.surface_key != "profile_missing"
        self.fallback_card.set_visible(visible)
        if not visible:
            return
        bridge = info.fallback_bridge
        cdp = info.fallback_cdp
        if bridge is not None and bridge.state == "ready":
            self.fallback_title_label.set_label("Fallback Bridge")
        elif cdp is not None and cdp.state == "ready":
            self.fallback_title_label.set_label("Fallback CDP")
        else:
            self.fallback_title_label.set_label("Fallback required")
        self.fallback_bridge_label.set_label(
            f"Bridge: {self._fallback_state_label(bridge)}"
        )
        self.fallback_cdp_label.set_label(
            f"CDP: {self._fallback_state_label(cdp)}"
        )
        details = [item.detail for item in (bridge, cdp) if item is not None and item.detail]
        self.fallback_hint_label.set_label(details[0] if details else "Secondary surfaces будут проверяться для выбранного профиля.")
        self.fallback_prepare_bridge_button.set_sensitive(self.current_task is None)
        self.fallback_retry_button.set_sensitive(self.current_task is None)

    def _refresh_portable_card(self, info: PreflightInfo, account: AccountOption | None) -> None:
        visible = account is not None or bool(self.portable_profiles)
        self.portable_card.set_visible(visible)
        if not visible:
            self.portable_feedback_label.set_label("")
            self.portable_remove_revealer.set_reveal_child(False)
            return
        portable_profile = info.portable_profile or self._active_portable_profile()
        portable_source = info.portable_source
        portable_runtime = info.portable_runtime
        self.portable_title_label.set_label("Portable Telegram Desktop")
        if portable_profile is None:
            self.portable_source_label.set_label(
                "Portable profile ещё не выбран. Импортируйте tdata.zip или подключите существующую portable-папку."
            )
            self.portable_runtime_label.set_label(
                "Status: pending | После выбора профиля панель покажет portable-profile.json, tdata и runtime state."
            )
            self.portable_launch_button.set_sensitive(False)
            self.portable_refresh_button.set_sensitive(self.current_task is None)
            self.portable_remove_button.set_visible(False)
            self.portable_remove_revealer.set_reveal_child(False)
            return
        profile_label = portable_profile.account_label or portable_profile.account_username or portable_profile.profile_name
        profile_dir = portable_profile.profile_dir
        source_kind = portable_profile.profile.source_kind or (portable_source.kind if portable_source is not None else "profile")
        self.portable_source_label.set_label(
            f"Профиль: {profile_label} | {source_kind} | {profile_dir}"
        )
        runtime_state = portable_runtime.state if portable_runtime is not None else portable_profile.state
        runtime_detail = portable_runtime.detail if portable_runtime is not None else portable_profile.detail
        pid_text = f" pid={portable_profile.pid}" if portable_profile.pid else ""
        window_text = f" | {portable_profile.window_title}" if portable_profile.window_title else ""
        self.portable_runtime_label.set_label(
            f"Status: {runtime_state}{pid_text}{window_text} | {runtime_detail}"
        )
        can_launch = bool(
            portable_profile.profile.binary_path is not None
            and portable_profile.state not in {"missing", "binary_missing"}
            and self.current_task is None
        )
        self.portable_launch_button.set_sensitive(can_launch)
        self.portable_refresh_button.set_sensitive(self.current_task is None)
        removable = self._portable_profile_is_removable(portable_profile)
        self.portable_remove_button.set_visible(removable)
        self.portable_remove_button.set_sensitive(removable and self.current_task is None)
        if removable and self.portable_remove_revealer.get_reveal_child():
            self.portable_remove_detail_label.set_label(self._portable_remove_prompt(portable_profile))
        elif not removable:
            self.portable_remove_revealer.set_reveal_child(False)
            self.portable_remove_detail_label.set_label("")

    def _refresh_security_card(self, info: PreflightInfo, account: AccountOption | None) -> None:
        visible = bool(account is not None and (info.security_attention_required or info.security_restart_available))
        self.security_card.set_visible(visible)
        if not visible:
            self.security_form_revealer.set_reveal_child(False)
            self.security_feedback_label.set_label("")
            return
        self.security_title_label.set_label(info.security_mode or "Secure token setup")
        self.security_detail_label.set_label(info.security_detail or "Проверьте security mode выбранного профиля.")
        self.security_setup_button.set_visible(bool(info.security_setup_available))
        self.security_setup_button.set_sensitive(bool(info.security_setup_available))
        self.security_restart_button.set_visible(bool(info.security_restart_available))
        self.security_restart_button.set_sensitive(bool(info.security_restart_available))
        if not info.security_setup_available:
            self.security_form_revealer.set_reveal_child(False)

    def _on_portable_profile_changed(self) -> None:
        if self._ui_syncing:
            return
        self.portable_remove_revealer.set_reveal_child(False)
        self.portable_remove_detail_label.set_label("")
        status = self._selected_portable_profile()
        if status is None:
            self._refresh_preflight()
            return
        target_key = _normalize_path_key(str(status.profile_dir))
        selected_account = self._selected_account()
        if selected_account is not None and _normalize_path_key(selected_account.profile_source) == target_key:
            self._refresh_preflight(schedule_deep=True)
            return
        for index, item in enumerate(self.accounts):
            if _normalize_path_key(item.profile_source) == target_key:
                self.account_combo.set_active(index)
                return
        preserved_output = self.output_entry.get_text().strip()
        self.backend.ensure_account_for_portable_profile(status, fallback_token=DEFAULT_TOKEN, set_default=False)
        self._load_accounts_into_ui(preferred_profile_source=str(status.profile_dir), preserve_output=preserved_output)

    def _choose_portable_zip(self) -> None:
        chooser = Gtk.FileChooserDialog(
            title="Импортировать tdata.zip",
            transient_for=self,
            modal=True,
            action=Gtk.FileChooserAction.OPEN,
        )
        chooser.add_button("Отмена", Gtk.ResponseType.CANCEL)
        chooser.add_button("Импортировать", Gtk.ResponseType.ACCEPT)
        chooser.set_default_response(Gtk.ResponseType.ACCEPT)
        chooser.set_current_folder(Gio.File.new_for_path(str(Path.home())))

        def on_response(native: Gtk.FileChooserDialog, response: int) -> None:
            if response == Gtk.ResponseType.ACCEPT:
                file_obj = native.get_file()
                path = Path(file_obj.get_path()).expanduser() if file_obj is not None and file_obj.get_path() else None
                if path is not None:
                    profile_name = suggest_portable_profile_name(path)
                    self._start_task(
                        task_name="import_portable_profile",
                        busy_status="Импортируем portable tdata.zip...",
                        worker=lambda: self.backend.import_portable_profile(str(path), profile_name=profile_name),
                        on_success=self._handle_portable_profile_imported,
                    )
            native.destroy()

        chooser.connect("response", on_response)
        chooser.show()

    def _choose_existing_portable_folder(self) -> None:
        chooser = Gtk.FileChooserDialog(
            title="Подключить существующую portable-папку",
            transient_for=self,
            modal=True,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
        )
        chooser.add_button("Отмена", Gtk.ResponseType.CANCEL)
        chooser.add_button("Подключить", Gtk.ResponseType.ACCEPT)
        chooser.set_default_response(Gtk.ResponseType.ACCEPT)
        chooser.set_current_folder(Gio.File.new_for_path(str(Path.home())))

        def on_response(native: Gtk.FileChooserDialog, response: int) -> None:
            if response == Gtk.ResponseType.ACCEPT:
                file_obj = native.get_file()
                path = Path(file_obj.get_path()).expanduser() if file_obj is not None and file_obj.get_path() else None
                if path is not None:
                    self._start_task(
                        task_name="adopt_portable_profile",
                        busy_status="Подключаем существующую portable-папку...",
                        worker=lambda: self.backend.adopt_portable_profile(str(path), profile_name=path.name),
                        on_success=self._handle_portable_profile_adopted,
                    )
            native.destroy()

        chooser.connect("response", on_response)
        chooser.show()

    def _handle_portable_profile_imported(self, status: PortableProfileStatus) -> None:
        self.hero_status.set_label("Portable профиль импортирован")
        self.portable_feedback_label.set_label(
            f"Создан профиль {portable_profile_label(status)}."
        )
        self._append_log(f"Portable профиль импортирован: {status.profile_dir}")
        self._load_accounts_into_ui(preferred_profile_source=str(status.profile_dir))

    def _handle_portable_profile_adopted(self, status: PortableProfileStatus) -> None:
        self.hero_status.set_label("Portable профиль подключён")
        self.portable_feedback_label.set_label(
            f"Подключён профиль {portable_profile_label(status)}."
        )
        self._append_log(f"Portable профиль подключён: {status.profile_dir}")
        self._load_accounts_into_ui(preferred_profile_source=str(status.profile_dir))

    def _launch_selected_portable_profile(self) -> None:
        status = self._active_portable_profile()
        if status is None:
            self._show_warning("Сначала выберите portable профиль.")
            return
        self._start_task(
            task_name="launch_portable_profile",
            busy_status="Запускаем portable профиль...",
            worker=lambda: self.backend.launch_portable_profile_dir(str(status.profile_dir)),
            on_success=self._handle_portable_profile_launched,
        )

    def _handle_portable_profile_launched(self, payload: tuple[PortableProfileStatus, bool]) -> None:
        status, already_running = payload
        if already_running:
            self.hero_status.set_label("Portable профиль уже запущен")
            self.portable_feedback_label.set_label(f"Уже запущен: {portable_profile_label(status)}.")
        else:
            self.hero_status.set_label("Portable профиль запущен")
            self.portable_feedback_label.set_label(f"Запущен: {portable_profile_label(status)}.")
        self._append_log(f"Portable профиль: {status.state} | {status.profile_dir}")
        self._load_accounts_into_ui(preferred_profile_source=str(status.profile_dir), preserve_output=self.output_entry.get_text().strip())

    def _refresh_selected_portable_profile(self) -> None:
        status = self._active_portable_profile()
        if status is None:
            self._show_warning("Сначала выберите portable профиль.")
            return
        self._start_task(
            task_name="portable_profile_runtime",
            busy_status="Обновляем helper-копию portable профиля...",
            worker=lambda: self.backend.refresh_portable_profile_dir(str(status.profile_dir)),
            on_success=self._handle_portable_runtime_refreshed,
        )

    def _handle_portable_profile_refreshed(self, status: PortableProfileStatus | None) -> None:
        if status is None:
            self.portable_feedback_label.set_label("Portable профиль больше не найден.")
            self._load_accounts_into_ui(preserve_output=self.output_entry.get_text().strip())
            return
        self.hero_status.set_label("Portable статус обновлён")
        self.portable_feedback_label.set_label(f"{portable_profile_label(status)} | {status.detail}")
        self._append_log(f"Portable status: {status.state} | {status.profile_dir}")
        self._load_accounts_into_ui(preferred_profile_source=str(status.profile_dir), preserve_output=self.output_entry.get_text().strip())

    def _portable_profile_is_removable(self, status: PortableProfileStatus | None) -> bool:
        return status is not None and portable_profile_kind(status) != "legacy"

    def _portable_remove_prompt(self, status: PortableProfileStatus) -> str:
        kind = portable_profile_kind(status)
        label = portable_profile_label(status)
        if kind == "managed":
            return (
                f"{label} будет удалён из панели и registry, а workspace-managed profile folder "
                f"{status.profile_dir} будет удалён с диска."
            )
        if status.state == "missing":
            return (
                f"{label} будет удалён из панели и registry. External folder {status.profile_dir} "
                "уже отсутствует на диске; если в workspace остались links, они тоже будут очищены."
            )
        return (
            f"{label} будет удалён из панели и registry. External folder {status.profile_dir} "
            "останется на диске вместе с portable-profile.json."
        )

    def _show_remove_portable_profile_confirmation(self) -> None:
        status = self._active_portable_profile()
        if not self._portable_profile_is_removable(status):
            self._show_warning("Этот portable профиль нельзя убрать из панели.")
            return
        assert status is not None
        self.portable_remove_detail_label.set_label(self._portable_remove_prompt(status))
        self.portable_remove_revealer.set_reveal_child(True)

    def _cancel_remove_portable_profile(self) -> None:
        self.portable_remove_revealer.set_reveal_child(False)
        self.portable_remove_detail_label.set_label("")

    def _confirm_remove_selected_portable_profile(self) -> None:
        status = self._active_portable_profile()
        if not self._portable_profile_is_removable(status):
            self._show_warning("Этот portable профиль нельзя убрать из панели.")
            return
        assert status is not None
        self._start_task(
            task_name="remove_portable_profile",
            busy_status="Убираем portable профиль из панели...",
            worker=lambda: self.backend.remove_portable_profile(str(status.profile_dir)),
            on_success=self._handle_portable_profile_removed,
        )

    def _handle_portable_profile_removed(self, result: PortableProfileRemovalResult) -> None:
        self._cancel_remove_portable_profile()
        self.hero_status.set_label("Portable профиль убран")
        detail = "external data сохранены" if result.external_data_preserved else "managed profile folder удалён"
        self.portable_feedback_label.set_label(f"Убран профиль {result.profile_label}. {detail}.")
        self._append_log(
            f"Portable профиль удалён: {result.profile_dir} | kind={result.profile_kind} | removed={len(result.removed_paths)}"
        )
        self._load_accounts_into_ui(preserve_output=self.output_entry.get_text().strip())

    def _choose_portable_source(self) -> None:
        self._choose_portable_zip()

    def _handle_portable_imported(self, payload: dict[str, str]) -> None:
        profile_source = str(payload.get("preferred_profile_source") or "")
        self._load_accounts_into_ui(preferred_profile_source=profile_source)

    def _launch_selected_portable(self) -> None:
        self._launch_selected_portable_profile()

    def _handle_portable_launched(self, message: str) -> None:
        self.portable_feedback_label.set_label(message)
        self._refresh_preflight(schedule_deep=True)

    def _refresh_selected_portable_runtime(self) -> None:
        self._refresh_selected_portable_profile()

    def _handle_portable_runtime_refreshed(self, state: PortableRuntimeState) -> None:
        self.hero_status.set_label("Portable runtime обновлён")
        self.portable_feedback_label.set_label(f"{state.state} | {state.detail}")
        self._append_log(f"Portable runtime: {state.state} | {state.detail}")
        self._refresh_preflight(schedule_deep=True)

    def _show_security_setup_form(self) -> None:
        self.security_feedback_label.set_label("")
        self.security_token_entry.set_text("")
        self.security_form_revealer.set_reveal_child(True)
        self.security_token_entry.grab_focus()

    def _cancel_security_setup(self) -> None:
        self.security_token_entry.set_text("")
        self.security_feedback_label.set_label("")
        self.security_form_revealer.set_reveal_child(False)

    def _save_security_token_inline(self) -> None:
        account = self._selected_account()
        if account is None:
            self.security_feedback_label.set_label("Сначала выберите профиль.")
            return
        token = str(self.security_token_entry.get_text() or "").strip()
        if not token:
            self.security_feedback_label.set_label("Введите token перед сохранением.")
            return
        if token == DEFAULT_TOKEN:
            self.security_feedback_label.set_label("Quickstart token нельзя сохранять как secure token.")
            return
        preserved_output = self.output_entry.get_text().strip()
        try:
            self.backend.save_secure_token(account, token)
        except Exception as exc:
            self.security_feedback_label.set_label(f"Не удалось сохранить secure token: {self._sanitize_text(str(exc))}")
            return
        self.security_token_entry.set_text("")
        self.security_form_revealer.set_reveal_child(False)
        self._append_log(f"Secure token сохранён для профиля: {account.label}")
        self._load_accounts_into_ui(preferred_profile_source=account.profile_source, preserve_output=preserved_output)
        self.hero_status.set_label("Secure token сохранён")
        self.security_feedback_label.set_label(
            "Secure token сохранён. Теперь этот профиль будет использовать registry secret store."
        )

    def _fallback_state_label(self, readiness: FallbackReadiness | None) -> str:
        if readiness is None:
            return "pending"
        return f"{readiness.state} | {readiness.detail}"

    def _prepare_bridge_profile(self) -> None:
        account = self._selected_account()
        if account is None:
            self._show_warning("Сначала выберите профиль.")
            return
        self._start_task(
            task_name="prepare_bridge",
            busy_status="Подготавливаем bridge profile...",
            worker=lambda: self.backend.prepare_bridge_surface(account),
            on_success=self._handle_bridge_prepared,
        )

    def _retry_fallback_readiness(self) -> None:
        self.backend.clear_fallback_readiness(self._selected_account())
        self._append_log("Повторная проверка fallback surfaces запущена.")
        self._refresh_preflight(schedule_deep=True)

    def _handle_bridge_prepared(self, readiness: FallbackReadiness) -> None:
        if readiness.state == "ready" and readiness.target is not None:
            self.connected_target = readiness.target
            self.hero_status.set_label("Bridge profile готов")
        elif readiness.state == "extension_setup_required":
            self.hero_status.set_label("Нужен manual Load unpacked")
        elif readiness.state == "foreign_hub":
            self.hero_status.set_label("Внешний hub не трогаем")
        else:
            self.hero_status.set_label("Bridge profile проверен")
        self._append_log(f"Fallback bridge: {readiness.state} | {readiness.detail}")
        self._refresh_preflight(schedule_deep=True)

    def _restart_owned_hub_with_selected_token(self) -> None:
        account = self._selected_account()
        if account is None:
            self.security_feedback_label.set_label("Сначала выберите профиль.")
            return
        try:
            self.backend.restart_owned_hub_with_token(account.token)
        except Exception as exc:
            self.security_feedback_label.set_label(f"Не удалось перезапустить hub: {self._sanitize_text(str(exc))}")
            return
        self.hero_status.set_label("Hub перезапущен")
        self.security_feedback_label.set_label("Hub перезапущен токеном выбранного профиля.")
        self._append_log("Hub перезапущен токеном выбранного профиля.")
        self._refresh_preflight(schedule_deep=True)

    def _refresh_history_panel(self) -> None:
        self.last_session = self.backend.load_last_session()
        self.recent_runs = self.backend.load_recent_runs()
        self.history_panel.set_resume_state(self.last_session)
        self.history_panel.set_runs(self.recent_runs, filter_key=self.history_filter)
        if self.recent_runs:
            last = self.recent_runs[0]
            self.last_run_label.set_label(
                f"Последний запуск: {last.chat_title or last.chat_ref} | {last.summary().status} | safe {last.safe_count}"
            )
        else:
            self.last_run_label.set_label("Последний запуск ещё не выполнялся")

    def _on_preset_changed(self) -> None:
        if self._selected_preset_key() == "resume_last":
            self._apply_resume_last()
        self._refresh_preflight()

    def _apply_resume_last(self) -> None:
        session = self.backend.load_last_session()
        self.last_session = session
        if session is None:
            self._append_log("Resume Last недоступен: нет сохранённой сессии.")
            return
        for index, account in enumerate(self.accounts):
            if account.key == session.account_key or account.label == session.account_label:
                self.account_combo.set_active(index)
                break
        if not self.output_entry.get_text().strip():
            self.output_entry.set_text(str(session.output_path))
        self._append_log(f"Resume Last: {session.chat_title or session.chat_ref} -> {session.output_path}")

    def _resume_chat_option(self, session: SessionResumeState) -> ChatOption:
        return ChatOption(
            title=session.chat_title or session.chat_ref,
            subtitle=f"resume/{session.surface_key}",
            url=session.chat_ref,
            fragment=session.chat_ref,
            peer_id=session.chat_ref,
            active=False,
            visible=True,
            ordinal=0,
            source_kind="resume",
        )

    def _set_history_filter(self, value: str) -> None:
        self.history_filter = value
        self.history_panel.set_active_filter(value)
        self.history_panel.set_runs(self.recent_runs, filter_key=value)

    def _refresh_quick_chats(self) -> None:
        while True:
            child = self.quick_chat_box.get_first_child()
            if child is None:
                break
            self.quick_chat_box.remove(child)
        rows: list[tuple[str, str, str]] = []
        seen: set[tuple[str, str]] = set()
        for row in self.pinned_chats:
            key = (str(row.get("account_key") or ""), str(row.get("chat_ref") or ""))
            if key in seen:
                continue
            seen.add(key)
            rows.append((str(row.get("account_key") or ""), str(row.get("chat_ref") or ""), str(row.get("chat_title") or "")))
        for run in self.recent_runs:
            key = (run.account_key, run.chat_ref)
            if key in seen:
                continue
            seen.add(key)
            rows.append((run.account_key, run.chat_ref, run.chat_title))
            if len(rows) >= 6:
                break
        if not rows:
            self.quick_chat_box.append(self._meta_label("Быстрые чаты появятся после первых запусков или закрепления."))
            return
        for account_key, chat_ref, chat_title in rows:
            button = Gtk.Button(label=chat_title or chat_ref)
            button.add_css_class("subtle-button")
            button.connect("clicked", lambda _btn, a=account_key, c=chat_ref, t=chat_title: self._select_quick_chat(a, c, t))
            self.quick_chat_box.append(button)

    def _select_quick_chat(self, account_key: str, chat_ref: str, chat_title: str) -> None:
        for index, account in enumerate(self.accounts):
            if account.key == account_key:
                self.account_combo.set_active(index)
                break
        if self._select_chat_by_ref(chat_ref):
            return
        self.chat_title_label.set_label(chat_title or chat_ref)
        self.chat_url_label.set_label(chat_ref)

    def _merge_known_chat_rows(self, chats: list[ChatOption]) -> list[ChatOption]:
        merged = list(chats)
        seen_refs: set[str] = set()
        for chat in merged:
            ref = str(chat.fragment or chat.url or "").strip()
            if ref:
                seen_refs.add(ref)

        account = self._selected_account()
        known_rows: list[tuple[int, str, ChatOption]] = []
        known_seen: set[str] = set()

        def add_known_chat(chat_ref: str, chat_title: str, subtitle: str, rank: int) -> None:
            ref = str(chat_ref or "").strip()
            if not ref or ref in seen_refs or ref in known_seen:
                return
            label = str(chat_title or ref).strip() or ref
            known_seen.add(ref)
            known_rows.append(
                (
                    rank,
                    label.lower(),
                    ChatOption(
                        title=label,
                        subtitle=subtitle,
                        url=ref,
                        fragment=ref,
                        peer_id=ref,
                        active=False,
                        visible=True,
                        ordinal=0,
                        source_kind="known",
                    ),
                )
            )

        for row in self.pinned_chats:
            row_account_key = str(row.get("account_key") or "").strip()
            rank = 0 if account is not None and row_account_key == account.key else 1
            add_known_chat(
                str(row.get("chat_ref") or ""),
                str(row.get("chat_title") or ""),
                "known chat | pinned",
                rank,
            )

        for run in self.recent_runs:
            rank = 2 if account is not None and run.account_key == account.key else 3
            subtitle_parts = ["known chat", "history"]
            if run.account_label:
                subtitle_parts.append(run.account_label)
            add_known_chat(
                run.chat_ref,
                run.chat_title,
                " | ".join(subtitle_parts),
                rank,
            )

        if not known_rows:
            return merged

        next_ordinal = max((chat.ordinal for chat in merged), default=-1) + 1
        for _rank, _label_key, chat in sorted(known_rows, key=lambda item: (item[0], item[1])):
            merged.append(
                ChatOption(
                    title=chat.title,
                    subtitle=chat.subtitle,
                    url=chat.url,
                    fragment=chat.fragment,
                    peer_id=chat.peer_id,
                    active=chat.active,
                    visible=chat.visible,
                    ordinal=next_ordinal,
                    source_kind=chat.source_kind,
                )
            )
            next_ordinal += 1
        return merged

    def _pin_selected_chat(self) -> None:
        account = self._selected_account()
        chat = self._selected_chat()
        if account is None or chat is None:
            self._show_warning("Сначала выберите профиль и чат.")
            return
        key = {"account_key": account.key, "chat_ref": chat.fragment, "chat_title": chat.title}
        if all(not (row.get("account_key") == account.key and row.get("chat_ref") == chat.fragment) for row in self.pinned_chats):
            self.pinned_chats.insert(0, key)
            self.pinned_chats = self.pinned_chats[:8]
            self.backend.run_history.save_pinned_chats(self.pinned_chats)
            self._refresh_quick_chats()
            self._append_log(f"Чат закреплён: {chat.title}")

    def _on_account_changed(self, *, schedule_deep: bool = True) -> None:
        if self._ui_syncing:
            return
        account = self._selected_account()
        self.connected_target = None
        self.chat_rows = []
        self.filtered_chat_rows = []
        self.portable_feedback_label.set_label("")
        self.portable_remove_detail_label.set_label("")
        self.portable_remove_revealer.set_reveal_child(False)
        self.security_feedback_label.set_label("")
        self.security_form_revealer.set_reveal_child(False)
        self._reset_progress_display()
        self._render_chat_rows()
        if account is None:
            return
        account_profile_key = _normalize_path_key(account.portable_profile_dir or account.profile_source)
        self.portable_profile_combo.set_active(-1)
        for index, status in enumerate(self.portable_profiles):
            if _normalize_path_key(str(status.profile_dir)) == account_profile_key:
                if self.portable_profile_combo.get_active() != index:
                    self.portable_profile_combo.set_active(index)
                break
        self.hero_status.set_label("Профиль выбран")
        if account.availability_state == "missing":
            self.client_label.set_label(f"Профиль недоступен: {account.label}")
            self.chat_meta_label.set_label(account.availability_detail or "Выбранный профиль больше не найден на диске.")
        else:
            self.client_label.set_label(f"Выбран профиль: {account.label}")
            self.chat_meta_label.set_label("Нажмите 'Подключить Telegram'. Список чатов загрузится автоматически.")
        self.result_label.set_label("Результат экспорта появится здесь")
        self.output_entry.set_text("")
        self.chat_title_label.set_label("Чат не выбран")
        self.chat_url_label.set_label("")
        self.artifact_panel.set_artifacts(None, summary="Артефакты текущего запуска появятся здесь")
        self._refresh_preflight(schedule_deep=schedule_deep)

    def _connect_selected_account(self) -> None:
        account = self._selected_account()
        if account is None:
            self._show_error("Сначала выберите профиль.")
            return
        if account.availability_state == "missing":
            self._show_error(account.availability_detail or "Выбранный профиль больше не найден на диске.")
            return
        self._start_task(
            task_name="connect",
            busy_status="Подключаем Telegram...",
            worker=lambda: self.backend.ensure_connected(account, launch_browser=True),
            on_success=self._handle_connected_target,
        )

    def _refresh_chats(self) -> None:
        account = self._selected_account()
        if account is None:
            self._show_error("Сначала выберите профиль.")
            return
        if account.availability_state == "missing":
            self._show_error(account.availability_detail or "Выбранный профиль больше не найден на диске.")
            return

        def worker() -> tuple[BrowserTarget, list[ChatOption]]:
            target = self.connected_target or self.backend.ensure_connected(account, launch_browser=True)
            return self.backend.fetch_chats(account, target)

        self._start_task(
            task_name="refresh_chats",
            busy_status="Читаем список диалогов...",
            worker=worker,
            on_success=self._handle_chats_loaded,
        )

    def _resolve_chat_target(self) -> None:
        account = self._selected_account()
        raw_target = self.chat_target_entry.get_text().strip()
        if account is None:
            self._show_error("Сначала выберите профиль.")
            return
        if account.availability_state == "missing":
            self._show_error(account.availability_detail or "Выбранный профиль больше не найден на диске.")
            return
        if not raw_target:
            self._show_error("Укажите Telegram ссылку, @username или peer id.")
            return

        def worker() -> tuple[BrowserTarget, ChatOption]:
            target = self.connected_target or self.backend.ensure_connected(account, launch_browser=True)
            if not self.backend._is_tdata_target(target):
                raise RuntimeError(
                    "runtime_unavailable: Открытие чата по ссылке / @username доступно только для Primary tdata профиля."
                )
            chat = self.backend.resolve_tdata_chat_target(account, raw_target)
            return target, chat

        self._start_task(
            task_name="resolve_chat_target",
            busy_status="Резолвим Telegram target по ссылке / @username...",
            worker=worker,
            on_success=self._handle_chat_target_resolved,
        )

    def _handle_chat_target_resolved(self, payload: tuple[BrowserTarget, ChatOption]) -> None:
        target, chat = payload
        self.connected_target = target
        merged = [chat]
        for existing in self.chat_rows:
            if existing.fragment == chat.fragment or existing.url == chat.url:
                continue
            merged.append(existing)
        self.chat_rows = merged
        self._apply_chat_filter()
        if not self._select_chat_by_ref(chat.fragment):
            if self.search_entry.get_text().strip():
                self.search_entry.set_text("")
                self._apply_chat_filter()
                self._select_chat_by_ref(chat.fragment)
        self.hero_status.set_label("Target резолвнут")
        self.chat_meta_label.set_label(
            f"Чат подготовлен по public target: {chat.url}. "
            "Можно сразу выбирать файл и запускать экспорт."
        )
        self._append_log(f"Target резолвнут: {chat.title} / {chat.fragment}")
        self._refresh_preflight()

    def _open_selected_chat(self) -> None:
        account = self._selected_account()
        chat = self._selected_chat()
        if account is None or chat is None:
            self._show_error("Выберите профиль и чат.")
            return
        if self.connected_target is None:
            self._show_error("Сначала подключите Telegram.")
            return
        self._start_task(
            task_name="open_chat",
            busy_status="Открываем чат в Telegram...",
            worker=lambda: self.backend.open_chat(account, self.connected_target, chat),
            on_success=self._handle_chat_opened,
        )

    def _choose_output_file(self) -> None:
        chat = self._selected_chat()
        current_value = self.output_entry.get_text().strip()
        suggested = slugify_filename(chat.title if chat else "telegram_export") + ".md"
        chooser = Gtk.FileChooserDialog(
            title="Куда сохранить Telegram export",
            transient_for=self,
            modal=True,
            action=Gtk.FileChooserAction.SAVE,
        )
        chooser.add_button("Отмена", Gtk.ResponseType.CANCEL)
        chooser.add_button("Сохранить", Gtk.ResponseType.ACCEPT)
        chooser.set_default_response(Gtk.ResponseType.ACCEPT)
        chooser.set_create_folders(True)
        chooser.set_current_name(Path(current_value).name if current_value else suggested)
        folder = _preferred_output_dir(current_value)
        chooser.set_current_folder(Gio.File.new_for_path(str(folder)))

        def on_response(native: Gtk.FileChooserDialog, response: int) -> None:
            if response == Gtk.ResponseType.ACCEPT:
                file_obj = native.get_file()
                if file_obj is not None:
                    path = file_obj.get_path() or ""
                    self.output_entry.set_text(path)
                    self._append_log(f"Файл результата: {path}")
            native.destroy()

        chooser.connect("response", on_response)
        chooser.present()

    def _run_export(self) -> None:
        account = self._selected_account()
        chat = self._selected_chat()
        output_text = self.output_entry.get_text().strip()
        preset_key = self._selected_preset_key()
        if preset_key == "resume_last" and self.last_session is not None:
            if not output_text:
                output_text = str(self.last_session.output_path)
                self.output_entry.set_text(output_text)
            if chat is None:
                chat = self._resume_chat_option(self.last_session)
        if account is None or chat is None:
            self._show_error("Выберите профиль и чат.")
            return
        if self.connected_target is None:
            self._show_error("Сначала подключите Telegram и загрузите список чатов.")
            return
        if self.backend._is_tdata_target(self.connected_target) and getattr(chat, "source_kind", "live") == "known":
            self._show_error(
                "Этот чат показан только как known chat из истории/закреплений и не появился в текущем списке диалогов выбранного профиля. "
                "Для Primary tdata export нужен чат, который реально виден этому профилю в live dialog list."
            )
            return
        if not output_text:
            self._show_error("Выберите итоговый .md файл через системный диалог.")
            return
        output_path = Path(output_text).expanduser()
        controller = TaskController()
        self._begin_export_progress(chat)

        def worker() -> ExportResult:
            return self.backend.run_export(
                account,
                self.connected_target,
                chat,
                output_path,
                emit=self._queue_log,
                controller=controller,
                preset_key=preset_key,
            )

        self._start_task(
            task_name="export",
            busy_status="Идёт сбор @username...",
            worker=worker,
            on_success=self._handle_export_finished,
            controller=controller,
        )

    def _open_result_directory(self) -> None:
        target = self.output_entry.get_text().strip()
        path = Path(target).expanduser().parent if target else _preferred_output_dir()
        try:
            open_path_in_file_manager(path)
        except Exception as exc:
            self._show_error(str(exc))

    def _repeat_last_run(self) -> None:
        if self.last_session is None:
            self._show_warning("Повторить нечего: нет последней сессии.")
            return
        self.preset_combo.set_active_id(self.last_session.preset_key or "resume_last")
        self._apply_resume_last()
        self._run_export()

    def _open_last_artifacts(self) -> None:
        if self.last_export_result is not None:
            self._open_artifact_parent(self.last_export_result.output_path)
            return
        if self.recent_runs:
            self._open_artifact_parent(self.recent_runs[0].output_path)
            return
        self._show_warning("Пока нет артефактов для открытия.")

    def _handle_connected_target(self, target: BrowserTarget) -> None:
        self.connected_target = target
        self.hero_status.set_label("Telegram подключён")
        self.connection_status.set_label("Connected")
        client_label = f"Режим: {self.backend.adapter_for_target(target).label}"
        self.client_label.set_label(f"{client_label} | вкладка: {target.tab_title or target.tab_url or 'Telegram'}")
        meta_label = (
            "Сессия прочитана из Telegram Desktop tdata. Загружаем список чатов напрямую из аккаунта..."
            if self.backend._is_tdata_target(target)
            else "Клиент найден. Загружаем список чатов через fallback adapter..."
        )
        self.chat_meta_label.set_label(meta_label)
        self._append_log(f"Клиент готов: {target.client_id} / tab {target.tab_id}")
        self._refresh_preflight(schedule_deep=True)
        self._refresh_chats()

    def _handle_chats_loaded(self, payload: tuple[BrowserTarget, list[ChatOption]]) -> None:
        target, chats = payload
        self.connected_target = target
        fetched_count = len(chats)
        self.chat_rows = self._merge_known_chat_rows(chats)
        self._apply_chat_filter()
        refresh_quick = getattr(self, "_refresh_quick_chats", None)
        if callable(refresh_quick):
            refresh_quick()
        active_count = sum(1 for item in chats if item.active)
        known_count = max(len(self.chat_rows) - fetched_count, 0)
        self.hero_status.set_label("Список чатов загружен")
        if self.backend._is_tdata_target(target):
            detail = f"Загружено {fetched_count} диалогов напрямую из Telegram-сессии."
            if known_count:
                detail = f"{detail} Дополнительно показаны {known_count} known chats из истории/закреплений."
            self.chat_meta_label.set_label(f"{detail} Если нужного чата нет, обновите список ещё раз.")
        else:
            detail = f"Загружено {fetched_count} диалогов из Telegram Web. Активных в выдаче: {active_count}."
            if known_count:
                detail = f"{detail} Дополнительно показаны {known_count} known chats из истории/закреплений."
            self.chat_meta_label.set_label(
                f"{detail} Если нужного чата нет, прокрутите список слева в Telegram и обновите снова."
            )
        if known_count:
            self._append_log(f"Чаты загружены: {fetched_count} (+{known_count} known)")
        else:
            self._append_log(f"Чаты загружены: {fetched_count}")
        refresh = getattr(self, "_refresh_preflight", None)
        if callable(refresh):
            refresh()

    def _handle_chat_opened(self, target: BrowserTarget) -> None:
        self.connected_target = target
        chat = self._selected_chat()
        if chat:
            self._append_log(f"Открыт чат: {chat.title}")
        if self.backend._is_tdata_target(target):
            self.hero_status.set_label("Работаем напрямую по сессии")
            self._append_log("В режиме tdata отдельное окно Telegram не требуется.")
        else:
            self.hero_status.set_label("Чат открыт в Telegram")
        self._refresh_preflight()

    def _handle_export_finished(self, result: ExportResult) -> None:
        self.last_export_result = result
        lines = [
            f"Markdown: {result.output_path}",
            f"Usernames TXT: {result.usernames_txt}",
            f"History messages: {result.history_messages_scanned}",
            f"@username найдено: {result.usernames_found}",
            f"Safe usernames: {result.safe_count}",
        ]
        if result.safe_txt:
            lines.append(f"Safe TXT: {result.safe_txt}")
        if result.safe_md:
            lines.append(f"Safe MD: {result.safe_md}")
        lines.append(f"Run log: {result.log_path}")
        lines.append(f"Action log: {result.action_log_path}")
        self.result_label.set_label("\n".join(lines))
        self.artifact_panel.set_artifacts(result.artifact_bundle(), summary="\n".join(lines))
        self.last_run_label.set_label(
            f"Последний запуск: {result.output_path.name} | {result.status or ('partial' if result.interrupted else 'done')} | safe {result.safe_count}"
        )
        if result.interrupted:
            self.hero_status.set_label("Остановлено")
            self._append_log(f"Сохранён частичный экспорт: {result.output_path}")
            self._show_warning("Сканирование остановлено пользователем. Частичный результат сохранён.")
        else:
            self.hero_status.set_label("Экспорт завершён")
            self._append_log(f"Экспорт завершён: {result.output_path}")
            self._show_info("Экспорт завершён. Сводка доступна справа.")
        if self.export_progress_state is not None:
            self.export_progress_state.messages_scanned = max(
                self.export_progress_state.messages_scanned, result.history_messages_scanned
            )
            self.export_progress_state.usernames_found = max(self.export_progress_state.usernames_found, result.usernames_found)
            self.export_progress_state.interrupted = result.interrupted
            self.export_progress_state.done = True
            self.export_progress_state.last_update_at = time.monotonic()
        self._render_progress_state()
        self._refresh_history_panel()
        self._refresh_quick_chats()
        self._refresh_preflight()
        self.run_stack.set_visible_child(self.artifact_panel)

    def _on_chat_selected(self) -> None:
        chat = self._selected_chat()
        if chat is None:
            self.chat_title_label.set_label("Чат не выбран")
            self.chat_url_label.set_label("")
            return
        self.chat_title_label.set_label(chat.title)
        subtitle = f"{chat.subtitle}\n" if chat.subtitle else ""
        self.chat_url_label.set_label(f"{subtitle}{chat.url}")
        refresh_sent = False
        if not self.output_entry.get_text().strip():
            suggested = DEFAULT_OUTPUT_DIR / f"{slugify_filename(chat.title or chat.fragment)}.md"
            self.output_entry.set_text(str(suggested))
            refresh_sent = True
        if not refresh_sent:
            self._refresh_preflight()

    def _apply_chat_filter(self) -> None:
        query = self.search_entry.get_text().strip().lower()
        if not query:
            self.filtered_chat_rows = list(self.chat_rows)
        else:
            self.filtered_chat_rows = [
                item
                for item in self.chat_rows
                if query in item.title.lower() or query in item.subtitle.lower() or query in item.url.lower()
            ]
        self._render_chat_rows()

    def _render_chat_rows(self) -> None:
        while True:
            child = self.chat_listbox.get_first_child()
            if child is None:
                break
            self.chat_listbox.remove(child)
        for chat in self.filtered_chat_rows:
            row = Gtk.ListBoxRow()
            row.chat = chat  # type: ignore[attr-defined]
            wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            wrapper.set_hexpand(True)
            wrapper.add_css_class("chat-row")
            if chat.active:
                wrapper.add_css_class("chat-row-active")
            title = Gtk.Label(label=("• " if chat.active else "") + chat.title)
            title.set_xalign(0)
            title.set_hexpand(True)
            title.set_ellipsize(Pango.EllipsizeMode.END)
            title.set_single_line_mode(True)
            title.set_max_width_chars(36)
            title.add_css_class("chat-title")
            subtitle = Gtk.Label(label=chat.subtitle or "—")
            subtitle.set_xalign(0)
            subtitle.add_css_class("chat-subtitle")
            subtitle.set_wrap(True)
            subtitle.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            subtitle.set_lines(2)
            subtitle.set_max_width_chars(40)
            wrapper.append(title)
            wrapper.append(subtitle)
            row.set_child(wrapper)
            self.chat_listbox.append(row)
        if self.filtered_chat_rows:
            row = self.chat_listbox.get_row_at_index(0)
            if row is not None:
                self.chat_listbox.select_row(row)
            self._on_chat_selected()
        else:
            self.chat_title_label.set_label("Чат не выбран")
            self.chat_url_label.set_label("")

    def _on_history_selected(self) -> None:
        row = self.history_panel.listbox.get_selected_row()
        record = getattr(row, "run_record", None) if row is not None else None
        if not isinstance(record, RunRecord):
            return
        if record.account_label in self.account_map:
            self.account_combo.set_active(list(self.account_map).index(record.account_label))
        self.output_entry.set_text(str(record.output_path))
        self.chat_title_label.set_label(record.chat_title or record.chat_ref)
        self.chat_url_label.set_label(f"{record.surface_badge}\n{record.chat_ref}")
        self._select_chat_by_ref(record.chat_ref)
        self.artifact_panel.set_artifacts(record.artifacts, summary=f"Исторический запуск {record.created_at}")
        if record.preset_key:
            self.preset_combo.set_active_id(record.preset_key)
        self._append_log(f"История: выбран запуск {record.created_at} для {record.chat_title or record.chat_ref}")
        self.run_stack.set_visible_child(self.artifact_panel)
        self._refresh_preflight()

    def _select_chat_by_ref(self, chat_ref: str) -> bool:
        target = str(chat_ref or "").strip()
        if not target:
            return False
        for index, chat in enumerate(self.filtered_chat_rows):
            if chat.fragment != target and chat.url != target:
                continue
            row = self.chat_listbox.get_row_at_index(index)
            if row is not None:
                self.chat_listbox.select_row(row)
                self._on_chat_selected()
                return True
        return False

    def _open_artifact_item(self, path: Path) -> None:
        target = path.expanduser()
        try:
            open_item_with_default_app(target)
        except Exception as exc:
            self._show_error(str(exc))

    def _open_artifact_parent(self, path: Path) -> None:
        target = path.expanduser()
        try:
            open_path_in_file_manager(target if target.is_dir() else target.parent)
        except Exception as exc:
            self._show_error(str(exc))

    def _copy_artifact_path(self, path: Path) -> None:
        display = self.get_display()
        if display is None:
            self._show_warning(str(path))
            return
        display.get_clipboard().set(str(path.expanduser()))
        self._append_log(f"Скопирован путь: {path}")

    def _known_tokens(self) -> list[str]:
        tokens = [DEFAULT_TOKEN]
        account = self._selected_account()
        if account is not None:
            tokens.append(account.token)
        for row in self.accounts:
            tokens.append(row.token)
        return [token for token in tokens if token]

    def _sanitize_text(self, text: str) -> str:
        return _mask_known_secrets(text, self._known_tokens())

    def _start_task(
        self,
        *,
        task_name: str,
        busy_status: str,
        worker: Callable[[], Any],
        on_success: Callable[[Any], None],
        controller: TaskController | None = None,
    ) -> None:
        if self.current_task is not None:
            self._show_warning("Дождитесь завершения текущей операции.")
            return
        self.current_task = task_name
        self.current_controller = controller
        self.hero_status.set_label(busy_status)
        self._append_log(busy_status)
        self.ui_tasks.start(worker=worker, on_success=lambda result: self._finish_task_success(on_success, result), on_error=self._finish_task_error)

    def _finish_task_success(self, callback: Callable[[Any], None], result: Any) -> bool:
        self.current_task = None
        self.current_controller = None
        self.stop_button.set_sensitive(False)
        callback(result)
        self._finalize_pending_close()
        return False

    def _finish_task_error(self, exc: Exception) -> bool:
        failed_task = self.current_task
        self.current_task = None
        self.current_controller = None
        self.stop_button.set_sensitive(False)
        if isinstance(exc, TaskCancelled):
            self.hero_status.set_label("Остановлено")
            self._append_log(str(exc))
            if self.export_progress_state is not None:
                self.export_progress_state.interrupted = True
                self.export_progress_state.done = True
                self.export_progress_state.failed = False
                self.export_progress_state.last_update_at = time.monotonic()
                self._render_progress_state()
            self._show_warning(str(exc))
            return False
        self.hero_status.set_label("Ошибка")
        self._append_log(f"Ошибка: {exc}")
        if self.export_progress_state is not None and failed_task == "export":
            self.export_progress_state.done = True
            self.export_progress_state.failed = True
            self.export_progress_state.last_update_at = time.monotonic()
            self._render_progress_state()
        self._show_error(str(exc))
        return False

    def _queue_log(self, message: str) -> None:
        GLib.idle_add(self._append_log, self._sanitize_text(message))

    def _append_log(self, message: str) -> bool:
        if not message:
            return False
        message = self._sanitize_text(message)
        self._consume_progress_message(message)
        stamp = datetime.now().strftime("%H:%M:%S")
        end_iter = self.log_buffer.get_end_iter()
        self.log_buffer.insert(end_iter, f"[{stamp}] {message}\n")
        mark = self.log_buffer.create_mark(None, self.log_buffer.get_end_iter(), False)
        self.log_view.scroll_mark_onscreen(mark)
        return False

    def _show_dialog(self, message_type: Gtk.MessageType, text: str) -> None:
        safe_text = self._sanitize_text(text)
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=message_type,
            buttons=Gtk.ButtonsType.OK,
            text=WINDOW_TITLE,
            secondary_text=safe_text,
        )
        dialog.connect("response", lambda dlg, _response: dlg.destroy())
        dialog.show()

    def _show_error(self, text: str) -> None:
        self._show_dialog(Gtk.MessageType.ERROR, text)

    def _show_info(self, text: str) -> None:
        self._show_dialog(Gtk.MessageType.INFO, text)

    def _show_warning(self, text: str) -> None:
        self._show_dialog(Gtk.MessageType.WARNING, text)


def slugify_filename(value: str) -> str:
    text = str(value or "").strip().lower()
    text = TELEGRAM_TITLE_SUFFIX_RE.sub("", text)
    text = re.sub(r"https?://", "", text)
    text = text.replace("@", "at-")
    text = re.sub(r"[^a-zа-я0-9._-]+", "_", text, flags=re.I)
    text = text.strip("._-")
    return text or "telegram_export"


def resolve_profile_dir(source_path: str) -> Path:
    source = str(source_path or "").strip()
    if not source:
        DEFAULT_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        return DEFAULT_PROFILE_DIR.resolve()

    candidate = Path(source).expanduser()
    if candidate.is_dir():
        return candidate.resolve()

    if candidate.is_file() and candidate.suffix.lower() == ".zip":
        PORTABLE_PROFILES_ROOT.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha1(str(candidate.resolve()).encode("utf-8")).hexdigest()[:12]
        slug = slugify_filename(candidate.stem)
        target = PORTABLE_PROFILES_ROOT / f"{slug}_{digest}"
        signature = f"{candidate.stat().st_size}:{int(candidate.stat().st_mtime)}"
        signature_path = target / ".zip_signature"
        needs_extract = True
        if signature_path.exists() and target.exists():
            current_signature = signature_path.read_text(encoding="utf-8", errors="ignore").strip()
            if current_signature == signature:
                needs_extract = False
        if needs_extract:
            if target.exists():
                shutil.rmtree(target)
            target.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(candidate) as archive:
                archive.extractall(target)
            signature_path.write_text(signature + "\n", encoding="utf-8")
        children = [item for item in target.iterdir()]
        if not (target / "Default").exists() and len(children) == 1 and children[0].is_dir() and (children[0] / "Default").exists():
            return children[0].resolve()
        return target.resolve()

    raise RuntimeError(f"Не удалось подготовить профиль: {source_path}")


def normalize_chat_options(payload: Any) -> list[ChatOption]:
    if not isinstance(payload, dict):
        return []
    raw_items = payload.get("items")
    current_url = str(payload.get("current_url") or "").strip()
    current_title = _clean_tab_title(str(payload.get("current_title") or ""))
    items = raw_items if isinstance(raw_items, list) else []
    rows: list[ChatOption] = []
    seen_urls: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        fragment = str(item.get("fragment") or "").strip()
        if not url and fragment:
            mode = str(payload.get("mode") or "a").strip() or "a"
            url = f"https://web.telegram.org/{mode}/#{fragment}"
        if not url or url in seen_urls or "/#" not in url:
            continue
        seen_urls.add(url)
        rows.append(
            ChatOption(
                title=_clean_tab_title(str(item.get("title") or fragment or url)),
                subtitle=str(item.get("subtitle") or "").strip(),
                url=url,
                fragment=fragment or url.split("#", 1)[1],
                peer_id=str(item.get("peer_id") or "").strip(),
                active=bool(item.get("active")) or url == current_url,
                visible=bool(item.get("visible", True)),
                ordinal=int(item.get("index") or index),
            )
        )
    if current_url and "/#" in current_url and current_url not in seen_urls:
        rows.append(
            ChatOption(
                title=current_title or current_url.split("#", 1)[1],
                subtitle="Текущий открытый чат",
                url=current_url,
                fragment=current_url.split("#", 1)[1],
                peer_id="",
                active=True,
                visible=True,
                ordinal=-1,
            )
        )
    rows.sort(key=lambda item: (0 if item.active else 1, item.ordinal, item.title.lower()))
    return rows


def normalize_tdata_chat_options(payload: Any) -> list[ChatOption]:
    items = payload.get("items") if isinstance(payload, dict) else []
    rows: list[ChatOption] = []
    for index, item in enumerate(items if isinstance(items, list) else []):
        if not isinstance(item, dict):
            continue
        chat_ref = str(item.get("chat_ref") or "").strip()
        title = _clean_tab_title(str(item.get("title") or chat_ref or "Telegram"))
        subtitle_bits = [str(item.get("subtitle") or "").strip(), str(item.get("username") or "").strip()]
        subtitle = " | ".join(bit for bit in subtitle_bits if bit)
        if not chat_ref:
            continue
        rows.append(
            ChatOption(
                title=title,
                subtitle=subtitle,
                url=chat_ref,
                fragment=chat_ref,
                peer_id=str(item.get("peer_id") or "").strip(),
                active=False,
                visible=True,
                ordinal=index,
            )
        )
    rows.sort(key=lambda item: (item.ordinal, item.title.lower()))
    return rows


def merge_cdp_export_payload(payload: Any) -> list[dict[str, str]]:
    snapshots = payload.get("snapshots") if isinstance(payload, dict) else []
    rows_by_key: dict[str, dict[str, str]] = {}
    mentions: set[str] = set()

    def normalize_row(raw: Any) -> dict[str, str] | None:
        if not isinstance(raw, dict):
            return None
        peer_id = str(raw.get("peer_id") or "").strip()
        name = str(raw.get("name") or "—").strip() or "—"
        username = export_mod._normalize_username(str(raw.get("username") or "").strip())
        status = str(raw.get("status") or "—").strip() or "—"
        role = str(raw.get("role") or "—").strip() or "—"
        if not peer_id and username == "—" and name == "—":
            return None
        return {
            "peer_id": peer_id or f"name:{slugify_filename(name)}",
            "name": name,
            "username": username,
            "status": status,
            "role": role,
        }

    def row_key(row: dict[str, str]) -> str:
        peer_id = str(row.get("peer_id") or "").strip()
        username = export_mod._normalize_username(str(row.get("username") or "").strip())
        if peer_id and not peer_id.startswith("name:"):
            return f"peer:{peer_id}"
        if username != "—":
            return f"user:{username.lower()}"
        return f"name:{str(row.get('name') or '').strip().lower()}"

    for snapshot in snapshots if isinstance(snapshots, list) else []:
        if not isinstance(snapshot, dict):
            continue
        for field_name in ("info_members", "members"):
            values = snapshot.get(field_name)
            if not isinstance(values, list):
                continue
            for value in values:
                row = normalize_row(value)
                if row is None:
                    continue
                key = row_key(row)
                existing = rows_by_key.get(key)
                if existing is None:
                    rows_by_key[key] = row
                    continue
                if existing["username"] == "—" and row["username"] != "—":
                    existing["username"] = row["username"]
                if existing["status"] in {"", "—", "из чата"} and row["status"] not in {"", "—"}:
                    existing["status"] = row["status"]
                if existing["role"] in {"", "—"} and row["role"] not in {"", "—"}:
                    existing["role"] = row["role"]
                if existing["name"] in {"", "—"} and row["name"] not in {"", "—"}:
                    existing["name"] = row["name"]
        raw_mentions = snapshot.get("mentions")
        if isinstance(raw_mentions, list):
            for raw in raw_mentions:
                username = export_mod._normalize_username(str(raw or "").strip())
                if username != "—":
                    mentions.add(username)

    known_usernames = {
        export_mod._normalize_username(str(row.get("username") or "").strip()).lower()
        for row in rows_by_key.values()
        if export_mod._normalize_username(str(row.get("username") or "").strip()) != "—"
    }
    for username in sorted(mentions):
        if username.lower() in known_usernames:
            continue
        rows_by_key[f"mention:{username.lower()}"] = {
            "peer_id": f"mention:{username.lstrip('@').lower()}",
            "name": f"Mention {username}",
            "username": username,
            "status": "из упоминаний",
            "role": "—",
        }

    rows = list(rows_by_key.values())
    rows.sort(
        key=lambda item: (
            1 if str(item.get("peer_id") or "").startswith("mention:") else 0,
            str(item.get("name") or "").lower(),
            str(item.get("peer_id") or ""),
        )
    )
    return rows


def parse_key_value_output(stdout: str) -> dict[str, str]:
    payload: dict[str, str] = {}
    for line in str(stdout or "").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        payload[key.strip()] = value.strip()
    return payload


def parse_progress_line(message: str) -> dict[str, str] | None:
    text = str(message or "").strip()
    if not text.startswith("PROGRESS "):
        return None
    payload: dict[str, str] = {}
    for chunk in text.split()[1:]:
        if "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        payload[key.strip()] = value.strip()
    return payload or None


def _progress_int(payload: dict[str, str] | None, key: str) -> int:
    if not payload:
        return 0
    try:
        return int(str(payload.get(key) or "0").strip())
    except (TypeError, ValueError):
        return 0


def _latest_progress_summary(lines: list[str]) -> str:
    for raw in reversed(lines):
        payload = parse_progress_line(raw)
        if not payload:
            continue
        messages = _progress_int(payload, "messages")
        usernames = _progress_int(payload, "usernames")
        return f"{messages} сообщений, {usernames} @username"
    return ""


def _positive_int(value: str | int | None) -> int | None:
    try:
        parsed = int(str(value or "").strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _format_duration(total_seconds: int) -> str:
    seconds = max(int(total_seconds), 0)
    minutes, secs = divmod(seconds, 60)
    hours, mins = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def open_path_in_file_manager(path: Path) -> None:
    directory = path.expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    target = str(directory)
    opener = shutil.which("xdg-open")
    if not opener:
        raise RuntimeError("Не найден xdg-open для открытия папки.")
    subprocess.Popen([opener, target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def open_item_with_default_app(path: Path) -> None:
    target = path.expanduser()
    opener = shutil.which("xdg-open")
    if not opener:
        raise RuntimeError("Не найден xdg-open для открытия файла.")
    subprocess.Popen([opener, str(target)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def _auto_profile_label(auto_name: str, profile_value: str) -> str:
    slot_number = _slot_number_from_source(profile_value)
    if auto_name.startswith("auto-default"):
        return "Профиль по умолчанию"
    if slot_number:
        if auto_name.startswith(f"auto-slot-{slot_number}-zip-"):
            return f"Слот {slot_number} · portable ZIP"
        return f"Слот {slot_number}"
    return auto_name.replace("auto-", "")


def _clean_tab_title(value: str) -> str:
    text = str(value or "").strip()
    text = TELEGRAM_TITLE_SUFFIX_RE.sub("", text).strip()
    return text or "Telegram"


def _slot_number_from_source(profile_value: str) -> str:
    match = re.search(r"/accounts/(\d+)/", str(profile_value or ""))
    return match.group(1) if match else ""


def _chmod_best_effort(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def _directory_has_payload(path: Path) -> bool:
    if not path.exists() or not path.is_dir():
        return False
    try:
        next(path.iterdir())
    except StopIteration:
        return False
    return True


def _slot_runtime_root(slot_number: str) -> Path:
    return TELEGRAM_WORKSPACE_ROOT / "accounts" / slot_number / "runtime"


def _slot_portable_state_path(slot_number: str) -> Path:
    return _slot_runtime_root(slot_number) / "portable_state.json"


def _slot_runtime_workdir_tdata(slot_number: str) -> Path:
    return _slot_runtime_root(slot_number) / "tdata"


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _chmod_best_effort(path, 0o600)


def _replace_tree(source: Path, target: Path) -> None:
    source = source.expanduser().resolve()
    target = target.expanduser()
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    _chmod_best_effort(target, 0o700)


def _path_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _group_auto_profile_sources(rows: list[tuple[str, str]]) -> list[tuple[str, str]]:
    grouped: dict[str, dict[str, list[tuple[str, str]] | tuple[str, str] | None]] = {}
    ordered: list[tuple[str, str]] = []
    for name, value in rows:
        slot_number = _slot_number_from_source(value)
        if not slot_number:
            ordered.append((name, value))
            continue
        bucket = grouped.setdefault(slot_number, {"profile": None, "others": []})
        if name.startswith(f"auto-slot-{slot_number}-profile"):
            bucket["profile"] = (name, value)
        else:
            others = bucket.setdefault("others", [])
            assert isinstance(others, list)
            others.append((name, value))
    for slot_number in sorted(grouped, key=lambda item: int(item)):
        bucket = grouped[slot_number]
        profile_row = bucket.get("profile")
        if isinstance(profile_row, tuple):
            ordered.append(profile_row)
            continue
        others = bucket.get("others")
        if not isinstance(others, list) or not others:
            continue
        others.sort(key=lambda item: (_path_mtime(Path(item[1]).expanduser()), item[0]), reverse=True)
        ordered.append(others[0])
    return ordered


def _portable_payload_from_directory(source_dir: Path) -> PortableSourceInfo:
    root = source_dir.expanduser().resolve()
    zip_candidates = sorted(root.glob("tdata-*.zip"), key=_path_mtime, reverse=True)
    if zip_candidates:
        chosen = zip_candidates[0]
        return PortableSourceInfo(
            slot_number="",
            path=chosen,
            kind="zip",
            detail=f"Будет использоваться ZIP source: {chosen}",
        )

    extracted_candidates = sorted(
        (item for item in root.iterdir() if item.is_dir() and item.name.startswith("tdata-") and (item / "tdata").is_dir()),
        key=_path_mtime,
        reverse=True,
    ) if root.exists() else []
    if extracted_candidates:
        chosen = extracted_candidates[0]
        return PortableSourceInfo(
            slot_number="",
            path=chosen,
            kind="folder",
            detail=f"Будет использоваться extracted source: {chosen / 'tdata'}",
            tdata_dir=chosen / "tdata",
        )

    direct_tdata = root / "tdata"
    if direct_tdata.is_dir():
        return PortableSourceInfo(
            slot_number="",
            path=direct_tdata,
            kind="tdata",
            detail=f"Будет использоваться direct tdata source: {direct_tdata}",
            tdata_dir=direct_tdata,
        )
    if root.name == "tdata" and root.is_dir():
        return PortableSourceInfo(
            slot_number="",
            path=root,
            kind="tdata",
            detail=f"Будет использоваться direct tdata source: {root}",
            tdata_dir=root,
        )
    return PortableSourceInfo(
        slot_number="",
        path=None,
        kind="missing",
        detail="В выбранной папке не найден tdata-*.zip, tdata-*/tdata или direct tdata/.",
    )


def detect_import_payload(source: Path) -> PortableSourceInfo:
    candidate = source.expanduser().resolve()
    if candidate.is_file() and candidate.suffix.lower() == ".zip":
        return PortableSourceInfo(slot_number="", path=candidate, kind="zip", detail=f"ZIP source: {candidate}")
    if candidate.is_dir():
        return _portable_payload_from_directory(candidate)
    return PortableSourceInfo(slot_number="", path=None, kind="missing", detail=f"Неподдерживаемый source: {candidate}")


def suggest_portable_profile_name(source: Path) -> str:
    candidate = source.expanduser().resolve()
    parts = candidate.parts
    if "TG_CONTACT" in parts:
        index = parts.index("TG_CONTACT")
        if index + 1 < len(parts):
            slot_label = str(parts[index + 1] or "").strip()
            if slot_label.isdigit():
                return f"TG_CONTACT {slot_label}"
    if candidate.is_file() and candidate.suffix.lower() == ".zip":
        return candidate.stem
    return candidate.name or "portable-profile"


def detect_slot_portable_source(*, slot_number: str, profile_source: str) -> PortableSourceInfo:
    slot_root = TELEGRAM_WORKSPACE_ROOT / "accounts" / slot_number
    imports_dir = slot_root / "imports"
    import_archives = sorted(imports_dir.glob("*.zip"), key=_path_mtime, reverse=True) if imports_dir.is_dir() else []
    if import_archives:
        chosen = import_archives[0]
        return PortableSourceInfo(
            slot_number=slot_number,
            path=chosen,
            kind="zip",
            detail=f"Portable source слота {slot_number}: ZIP {chosen}",
        )

    source_path = Path(str(profile_source or "")).expanduser()
    if source_path.is_file() and source_path.suffix.lower() == ".zip":
        return PortableSourceInfo(
            slot_number=slot_number,
            path=source_path.resolve(),
            kind="zip",
            detail=f"Portable source слота {slot_number}: ZIP {source_path}",
        )

    profile_dir = source_path if source_path.is_dir() else resolve_profile_dir(profile_source)
    payload = _portable_payload_from_directory(profile_dir)
    return PortableSourceInfo(
        slot_number=slot_number,
        path=payload.path,
        kind=payload.kind,
        detail=payload.detail or f"Portable source слота {slot_number} не найден.",
        tdata_dir=payload.tdata_dir,
    )


def _portable_source_signature(source_info: PortableSourceInfo) -> str:
    if source_info.path is None:
        return ""
    if source_info.kind == "zip":
        try:
            stat = source_info.path.stat()
        except OSError:
            return ""
        rows = _tdata_signature_from_zip(source_info.path)
        return f"zip|{source_info.path}|{stat.st_size}|{int(stat.st_mtime)}|{'|'.join(rows)}"
    tdata_dir = source_info.tdata_dir or source_info.path
    rows = _tdata_signature_from_dir(tdata_dir)
    if rows:
        return f"{source_info.kind}|{tdata_dir}|{'|'.join(rows)}"
    try:
        stat = tdata_dir.stat()
    except OSError:
        return ""
    return f"{source_info.kind}|{tdata_dir}|{int(stat.st_mtime)}"


def _tdata_dir_looks_valid(path: Path) -> bool:
    if not path.is_dir():
        return False
    return any((path / relative).exists() for relative in TDATA_SIGNATURE_FILES) or (path / "key_datas").exists()


def _portable_runtime_signature_from_tdata(tdata_dir: Path) -> str:
    if not _tdata_dir_looks_valid(tdata_dir):
        return ""
    rows = _tdata_signature_from_dir(tdata_dir)
    if rows:
        return "|".join(rows)
    try:
        stat = tdata_dir.stat()
    except OSError:
        return ""
    return f"{int(stat.st_mtime)}"


def _portable_runtime_state_from_workspace(
    *,
    slot_number: str,
    source_info: PortableSourceInfo,
    binary_path: Path | None,
) -> PortableRuntimeState:
    if not slot_number:
        return PortableRuntimeState(slot_number="", state="missing", detail="Portable runtime доступен только для slot-based профилей.")
    runtime_dir = _slot_runtime_root(slot_number) / "portable_tdata"
    source_signature = _portable_source_signature(source_info)
    payload = _read_json_file(_slot_portable_state_path(slot_number))
    metadata_source = str(payload.get("source_path") or "").strip()
    metadata_signature = str(payload.get("source_signature") or "").strip()
    runtime_exists = _tdata_dir_looks_valid(runtime_dir)
    needs_rebuild = bool(
        source_info.path is not None and (
            not runtime_exists
            or metadata_source != str(source_info.path)
            or metadata_signature != source_signature
        )
    )
    if source_info.path is None:
        return PortableRuntimeState(
            slot_number=slot_number,
            state="missing",
            detail=source_info.detail or "В слоте нет portable source.",
            source_path=None,
            source_kind=source_info.kind,
            runtime_dir=runtime_dir if runtime_dir.exists() else None,
            tdata_dir=runtime_dir if runtime_dir.exists() else None,
            binary_path=binary_path,
            source_signature=source_signature,
            ready_for_export=False,
            needs_rebuild=False,
            authorized=False,
        )
    if not runtime_exists:
        detail = "Portable runtime clone ещё не собрана. Нажмите 'Обновить portable-копию' или 'Открыть portable Telegram'."
        state = "missing"
        ready_for_export = False
    elif needs_rebuild:
        detail = "Portable source изменился. Обновите portable-копию перед export или запуском Telegram."
        state = "stale"
        ready_for_export = False
    elif binary_path is None:
        detail = "Portable runtime clone готова для helper/export, но binary Telegram не найден."
        state = "binary_missing"
        ready_for_export = True
    else:
        detail = "Portable runtime clone готова."
        state = "ready"
        ready_for_export = True
    return PortableRuntimeState(
        slot_number=slot_number,
        state=state,
        detail=detail,
        source_path=source_info.path,
        source_kind=source_info.kind,
        runtime_dir=runtime_dir if runtime_exists else runtime_dir,
        tdata_dir=runtime_dir if runtime_exists else runtime_dir,
        binary_path=binary_path,
        source_signature=source_signature,
        ready_for_export=ready_for_export,
        needs_rebuild=needs_rebuild,
        authorized=False,
    )


def _extract_portable_tdata_zip(archive: Path, target_dir: Path) -> None:
    extract_root = target_dir.parent / f".portable_extract_{_utc_timestamp()}"
    if extract_root.exists():
        shutil.rmtree(extract_root, ignore_errors=True)
    extract_root.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(archive) as handle:
            handle.extractall(extract_root)
        candidates: list[Path] = []
        direct = extract_root / "tdata"
        if direct.is_dir():
            candidates.append(direct)
        for item in extract_root.iterdir():
            if item.is_dir() and (item / "tdata").is_dir():
                candidates.append(item / "tdata")
        if not candidates:
            raise RuntimeError(f"В ZIP не найден каталог tdata: {archive}")
        shutil.copytree(candidates[0], target_dir)
    finally:
        shutil.rmtree(extract_root, ignore_errors=True)


def _sync_portable_runtime_alias(slot_number: str) -> None:
    runtime_dir = _slot_runtime_root(slot_number) / "portable_tdata"
    workdir_tdata = _slot_runtime_workdir_tdata(slot_number)
    if not runtime_dir.exists():
        return
    if workdir_tdata.is_symlink():
        try:
            if workdir_tdata.resolve() == runtime_dir.resolve():
                return
        except OSError:
            pass
        workdir_tdata.unlink(missing_ok=True)
    elif workdir_tdata.exists():
        shutil.rmtree(workdir_tdata, ignore_errors=True)
    workdir_tdata.symlink_to(runtime_dir, target_is_directory=True)


def _resolve_import_slot(preferred_slot: str) -> int:
    text = str(preferred_slot or "").strip()
    if text.isdigit() and int(text) >= 1:
        return int(text)
    return int(layout_mod.first_empty_slot(TELEGRAM_WORKSPACE_ROOT, max_slots=WORKSPACE_SLOTS))


def _slot_token(slot_number: str) -> str:
    if not slot_number:
        return ""
    token_path = TELEGRAM_WORKSPACE_ROOT / "accounts" / slot_number / "keys" / "api_token.txt"
    try:
        return token_path.read_text(encoding="utf-8", errors="ignore").strip()
    except OSError:
        return ""


def _account_token_source(*, token: str, secret_ref: str, slot_token: str, default_token: str) -> str:
    if str(secret_ref or "").strip():
        return "secret_ref"
    if str(slot_token or "").strip():
        return "slot_key"
    if str(token or "").strip() == str(default_token or "").strip() and str(default_token or "").strip():
        return "quickstart"
    if str(token or "").strip():
        return "secret_ref"
    return "missing"


def _profile_has_site_control_extension(profile_dir: Path) -> bool:
    pref_file = profile_dir / "Default" / "Preferences"
    if not pref_file.is_file():
        return False
    try:
        payload = json.loads(pref_file.read_text(encoding="utf-8"))
    except Exception:
        return False
    settings = ((payload.get("extensions") or {}).get("settings") or {}) if isinstance(payload, dict) else {}
    if not isinstance(settings, dict):
        return False
    for row in settings.values():
        if not isinstance(row, dict):
            continue
        manifest = row.get("manifest") or {}
        if isinstance(manifest, dict) and str(manifest.get("name") or "").strip() == "Site Control Bridge":
            return True
        raw_path = str(row.get("path") or "").strip()
        if not raw_path:
            continue
        candidate = (pref_file.parent / raw_path).resolve() if not Path(raw_path).is_absolute() else Path(raw_path).resolve()
        if candidate == EXTENSION_DIR.resolve():
            return True
    return False


def _bridge_manual_setup_detail(profile_dir: Path) -> str:
    return (
        "Bridge profile требует one-time manual setup в branded Chrome: откройте chrome://extensions, "
        f"включите Developer mode, нажмите Load unpacked и выберите {EXTENSION_DIR}. "
        f"После этого переиспользуйте тот же профиль: {profile_dir}."
    )


def _normalize_path_key(value: str) -> str:
    return str(Path(value).expanduser()) if value else ""


def _pick_telegram_tab(tabs: list[dict[str, Any]]) -> dict[str, Any] | None:
    ranked: list[tuple[int, int, str, dict[str, Any]]] = []
    for tab in tabs:
        url = str(tab.get("url") or "")
        if "web.telegram.org" not in url:
            continue
        has_dialog = 1 if "/#" in url else 0
        is_active = 1 if bool(tab.get("active")) else 0
        ranked.append((has_dialog, is_active, url, tab))
    if not ranked:
        return None
    ranked.sort(reverse=True)
    return ranked[0][3]


def _optional_path(value: str | None) -> Path | None:
    text = str(value or "").strip()
    return Path(text).expanduser() if text else None


def _cdp_state_path(profile_dir: Path) -> Path:
    digest = hashlib.sha1(str(profile_dir.resolve()).encode("utf-8")).hexdigest()[:16]
    return RUNTIME_DIR / "cdp" / f"{digest}.json"


def _tdata_target_key(tdata_dir: Path) -> str:
    return hashlib.sha1(str(tdata_dir.resolve()).encode("utf-8")).hexdigest()[:16]


def resolve_tdata_dir(profile_dir: Path) -> Path | None:
    candidates = list_candidate_tdata_dirs(profile_dir, include_collector_debug=ALLOW_COLLECTOR_TDATA_DEBUG_FALLBACK)
    if candidates:
        return candidates[0]
    return None


def list_candidate_tdata_dirs(profile_dir: Path, *, include_collector_debug: bool = False) -> list[Path]:
    root = profile_dir.expanduser().resolve()
    candidates: list[Path] = []
    candidates.extend(_local_tdata_dirs(root))
    candidates.extend(_tdata_dirs_from_metadata(root))
    if include_collector_debug:
        collector_tdata = TELEGRAM_API_COLLECTOR_TDATA_DIR.expanduser().resolve()
        if collector_tdata.is_dir() and _collector_tdata_matches_profile(root, collector_tdata):
            candidates.append(collector_tdata)
    return _dedupe_paths(candidates)


def _local_tdata_dirs(root: Path) -> list[Path]:
    candidates: list[Path] = []
    if not root.exists():
        return candidates
    direct_tdata = root / "tdata"
    if direct_tdata.exists() and direct_tdata.is_dir():
        candidates.append(direct_tdata)

    extracted_dirs = sorted((item for item in root.iterdir() if item.is_dir() and item.name.startswith("tdata-")), key=lambda p: p.name)
    for item in extracted_dirs:
        candidate = item / "tdata"
        if candidate.exists() and candidate.is_dir():
            candidates.append(candidate)

    archives = sorted(root.glob("tdata-*.zip"), key=lambda p: p.name.lower())
    for archive in archives:
        target = root / archive.stem
        signature = f"{archive.stat().st_size}:{int(archive.stat().st_mtime)}"
        signature_path = target / ".zip_signature"
        needs_extract = True
        if signature_path.exists() and (target / "tdata").exists():
            current = signature_path.read_text(encoding="utf-8", errors="ignore").strip()
            if current == signature:
                needs_extract = False
        if needs_extract:
            if target.exists():
                shutil.rmtree(target)
            target.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(archive) as handle:
                handle.extractall(target)
            signature_path.write_text(signature + "\n", encoding="utf-8")
        candidate = target / "tdata"
        if candidate.exists() and candidate.is_dir():
            candidates.append(candidate)
    return candidates


def _tdata_dirs_from_metadata(profile_dir: Path) -> list[Path]:
    meta_files: list[Path] = []
    for base in [profile_dir, *profile_dir.parents[:3]]:
        meta = base / "portable-profile.json"
        if meta.is_file():
            meta_files.append(meta)

    downloads_root = Path.home() / "Загрузки" / "Telegram Desktop"
    if downloads_root.exists():
        meta_files.extend(sorted(downloads_root.glob("**/portable-profile.json")))

    candidates: list[Path] = []
    for meta in _dedupe_paths(meta_files):
        try:
            payload = json.loads(meta.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        for raw in (
            payload.get("tdata_dir"),
            payload.get("portable_dir"),
            ((payload.get("runtime") or {}).get("cache_dir") if isinstance(payload.get("runtime"), dict) else None),
        ):
            candidate = _coerce_tdata_dir(raw)
            if candidate is not None:
                candidates.append(candidate)
    return candidates


def _coerce_tdata_dir(value: Any) -> Path | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    candidate = Path(raw).expanduser()
    if candidate.is_dir() and candidate.name == "tdata":
        return candidate.resolve()
    nested = candidate / "tdata"
    if nested.is_dir():
        return nested.resolve()
    return None


def _collector_tdata_matches_profile(profile_dir: Path, collector_tdata: Path) -> bool:
    collector_signature = _tdata_signature_from_dir(collector_tdata)
    if not collector_signature:
        return False
    for archive in sorted(profile_dir.glob("tdata-*.zip"), key=lambda p: p.name.lower()):
        if _tdata_signature_from_zip(archive) == collector_signature:
            return True
    return False


def _tdata_signature_from_dir(tdata_dir: Path) -> tuple[str, ...]:
    rows: list[str] = []
    for relative in TDATA_SIGNATURE_FILES:
        path = tdata_dir / relative
        if not path.is_file():
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        rows.append(f"{relative}:{len(data)}:{hashlib.sha1(data).hexdigest()}")
    return tuple(rows)


def _tdata_signature_from_zip(archive: Path) -> tuple[str, ...]:
    rows: list[str] = []
    try:
        with zipfile.ZipFile(archive) as handle:
            names = set(handle.namelist())
            for relative in TDATA_SIGNATURE_FILES:
                member = f"tdata/{relative}"
                if member not in names:
                    continue
                data = handle.read(member)
                rows.append(f"{relative}:{len(data)}:{hashlib.sha1(data).hexdigest()}")
    except (OSError, zipfile.BadZipFile):
        return ()
    return tuple(rows)


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        resolved = path.expanduser().resolve()
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        unique.append(resolved)
    return unique


def _compact_error_text(text: str) -> str:
    return " ".join(str(text or "").split())[:400]


def _classify_failure_reason(text: str) -> str:
    value = str(text or "").strip().lower()
    if "offline" in value:
        return "offline client"
    if "helper" in value:
        return "helper missing"
    if "no account has been loaded" in value or "openteleexception" in value or "auth" in value or "session unreadable" in value:
        return "auth/session unreadable"
    if "profile" in value and "busy" in value:
        return "browser profile busy"
    if "different token" in value or "401" in value or "token mismatch" in value:
        return "hub token mismatch"
    return "runtime error"


def _is_invite_like_target(value: str | None) -> bool:
    text = str(value or "").strip()
    return bool(
        re.search(r"(?:https?://)?t\.me/\+", text, flags=re.I)
        or re.search(r"(?:https?://)?t\.me/joinchat/", text, flags=re.I)
        or re.search(r"tg://join\?invite=", text, flags=re.I)
    )


def _public_chat_target_from_value(value: str | None) -> str:
    text = str(value or "").strip()
    if not text or _is_invite_like_target(text):
        return ""
    if re.fullmatch(r"-?\d+", text):
        return text
    for pattern in (
        r"(?:https?://)?t\.me/(?!joinchat/|\+)([A-Za-z0-9_]{5,32})(?:[/?].*)?$",
        r"@([A-Za-z0-9_]{5,32})",
    ):
        match = re.search(pattern, text, flags=re.I)
        if match:
            candidate = str(match.group(1) or "").strip()
            if re.fullmatch(r"[A-Za-z0-9_]{5,32}", candidate) and not candidate.isdigit():
                return f"@{candidate}"
    candidate = text[1:] if text.startswith("@") else text
    if re.fullmatch(r"[A-Za-z0-9_]{5,32}", candidate) and not candidate.isdigit():
        return f"@{candidate}"
    return ""


def _helper_python_candidates() -> list[tuple[str, Path]]:
    rows: list[tuple[str, Path]] = []
    explicit = str(os.getenv("TELEGRAM_API_COLLECTOR_PYTHON", "") or "").strip()
    if explicit:
        rows.append(("explicit", Path(explicit).expanduser()))
    rows.append(("managed", MANAGED_HELPER_PYTHON))
    rows.append(("legacy", TELEGRAM_API_COLLECTOR_PYTHON))
    deduped: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for source, path in rows:
        key = str(path.expanduser())
        if key in seen:
            continue
        seen.add(key)
        deduped.append((source, path.expanduser()))
    return deduped


def _selected_helper_python() -> tuple[str, Path] | None:
    for source, path in _helper_python_candidates():
        if path.exists():
            return (source, path)
    return None


def _tdata_helper_timeout_seconds(command: str) -> int | None:
    return TDATA_EXPORT_TIMEOUT_SEC if command == "export-chat" else TDATA_LIST_TIMEOUT_SEC


def _preferred_output_dir(current_value: str | None = None) -> Path:
    if current_value:
        parent = Path(current_value).expanduser().parent
        try:
            parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        if parent.is_dir():
            return parent
    for candidate in (DEFAULT_OUTPUT_DIR, Path.home() / "Загрузки", Path.home()):
        try:
            candidate.mkdir(parents=True, exist_ok=True)
        except OSError:
            continue
        if candidate.is_dir():
            return candidate
    return Path.home()


def find_portable_telegram_binary(profile_dir: Path) -> Path | None:
    profile_dir = profile_dir.expanduser().resolve()
    candidates: list[Path] = []

    for base in [profile_dir, *profile_dir.parents[:3]]:
        binary = base / "Telegram"
        if binary.is_file():
            candidates.append(binary)
        meta = base / "portable-profile.json"
        if meta.is_file():
            sibling = meta.parent / "Telegram"
            if sibling.is_file():
                candidates.append(sibling)

    downloads_root = Path.home() / "Загрузки" / "Telegram Desktop"
    if downloads_root.exists():
        for meta in sorted(downloads_root.glob("**/portable-profile.json")):
            sibling = meta.parent / "Telegram"
            if sibling.is_file():
                candidates.append(sibling)

    seen: set[str] = set()
    for path in candidates:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        return path.resolve()
    return None


def _detect_browser_binary() -> str:
    for candidate in ("chromium", "chromium-browser", "google-chrome"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise RuntimeError("Не найден Chromium/Google Chrome для прямого запуска Telegram.")


def _pick_free_cdp_port(profile_dir: Path) -> int:
    digest = hashlib.sha1(str(profile_dir.resolve()).encode("utf-8")).hexdigest()
    preferred = CDP_PORT_BASE + (int(digest[:8], 16) % CDP_PORT_SPAN)
    for offset in range(CDP_PORT_SPAN):
        port = CDP_PORT_BASE + ((preferred - CDP_PORT_BASE + offset) % CDP_PORT_SPAN)
        if not _tcp_port_open(port):
            return port
    raise RuntimeError("Не удалось подобрать свободный CDP port.")


def _tcp_port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        handle.settimeout(0.25)
        return handle.connect_ex(("127.0.0.1", int(port))) == 0


def _cdp_debugger_ready(port: int) -> bool:
    try:
        request = urllib.request.Request(f"http://127.0.0.1:{int(port)}/json/version", headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=0.8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return False
    return isinstance(payload, dict) and bool(str(payload.get("Browser") or "").strip())


def _format_command_error(error: Any) -> str:
    if isinstance(error, dict):
        return str(error.get("message") or "").strip()
    return str(error or "").strip()


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


class TelegramMembersExportApp(Gtk.Application):
    def __init__(self, backend: TelegramGuiBackend):
        super().__init__(application_id="local.sitecontrol.telegram_members_export_gui")
        self.backend = backend
        self.window: TelegramMembersExportWindow | None = None

    def do_activate(self) -> None:
        install_css()
        if self.window is None:
            self.window = TelegramMembersExportWindow(self, self.backend)
        self.window.present()
        self.window.bootstrap_async()


def main() -> int:
    for path, label in (
        (RUN_ONCE_SCRIPT, "run script"),
        (SAFE_SNAPSHOT_SCRIPT, "safe snapshot script"),
        (START_BROWSER_SCRIPT, "browser launcher"),
        (CDP_HELPER_SCRIPT, "CDP helper"),
        (TDATA_HELPER_SCRIPT, "tdata helper"),
        (HELPER_REQUIREMENTS_FILE, "helper requirements"),
    ):
        if not path.exists():
            print(f"WARNING: missing {label}: {path}", file=sys.stderr)
    helper_python = _selected_helper_python()
    if helper_python is None:
        print(
            "WARNING: Telegram helper python is not available; run scripts/bootstrap_telegram_workstation.sh "
            "or set TELEGRAM_API_COLLECTOR_PYTHON.",
            file=sys.stderr,
        )
    else:
        print(f"INFO: Telegram helper python ({helper_python[0]}): {helper_python[1]}", file=sys.stderr)
    if not shutil.which("node"):
        print("WARNING: node is not available; CDP fallback will stay disabled until node is installed.", file=sys.stderr)

    lock = SingleInstanceLock(LOCK_DIR, LOCK_PID_FILE)
    lock.acquire()
    ACTION_LOG_DIR.mkdir(parents=True, exist_ok=True)
    action_log_path = ACTION_LOG_DIR / f"gui_actions_{_utc_timestamp()}.log"
    backend = TelegramGuiBackend(action_log_path=action_log_path)
    app = TelegramMembersExportApp(backend)
    exit_code = app.run(sys.argv)
    lock.release()
    return int(exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
