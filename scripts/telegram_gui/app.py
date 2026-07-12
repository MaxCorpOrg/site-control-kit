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
import types
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .gtk_compat import Gdk, Gio, GLib, Gtk, Pango

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
from .logging import GuiRunLogger, tail_text_file
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
    normalize_operation_kind,
    operation_metric_count,
    operation_metric_label,
    operation_metric_summary,
)
from .services.artifact_index import append_index_entry, build_artifact_bundle
from .services.portable_profiles import PortableProfileRegistry, portable_profile_kind, portable_profile_label
from .process_runner import ProcessRunner, TaskCancelled, TaskController
from .services.preflight import PreflightService
from .services.run_history import RunHistoryService
from .services.secrets import SecretStore, mask_secret
from .services.ui_tasks import UiTaskService
from .runtime import load_gui_runtime_paths
from .ui.panels import ArtifactPanel, HistoryPanel, PreflightPanel, ProgressPanel
from .ui.styles import attach_button_feedback, install_css, resolve_ui_scale
from webcontrol.runtime_logging import RuntimeEventLogger
from webcontrol.settings import LEGACY_INSECURE_TOKEN, venv_python_path


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
_legacy_collector_root_raw = str(os.getenv("TELEGRAM_API_COLLECTOR_ROOT", "") or "").strip()
TELEGRAM_API_COLLECTOR_ROOT = (
    Path(_legacy_collector_root_raw).expanduser()
    if _legacy_collector_root_raw
    else REPO_ROOT / ".site-control-kit" / "_legacy_collector_disabled"
)
_legacy_collector_python_raw = str(os.getenv("TELEGRAM_API_COLLECTOR_PYTHON", "") or "").strip()
TELEGRAM_API_COLLECTOR_PYTHON = (
    Path(_legacy_collector_python_raw).expanduser()
    if _legacy_collector_python_raw
    else venv_python_path(TELEGRAM_API_COLLECTOR_ROOT / ".venv")
)
_legacy_collector_tdata_raw = str(os.getenv("TELEGRAM_API_COLLECTOR_TDATA_DIR", "") or "").strip()
TELEGRAM_API_COLLECTOR_TDATA_DIR = (
    Path(_legacy_collector_tdata_raw).expanduser()
    if _legacy_collector_tdata_raw
    else TELEGRAM_API_COLLECTOR_ROOT / "tdata_import" / "tdata"
)
TELEGRAM_WORKSPACE_ROOT = Path(".")
WORKSPACE_SLOTS = max(int(os.getenv("TELEGRAM_WORKSPACE_SLOTS", "10") or "10"), 1)
USER_REGISTRY_PATH = Path(".")
DEFAULT_TOKEN = LEGACY_INSECURE_TOKEN
DEFAULT_PROFILE_DIR = Path(".")
PORTABLE_PROFILES_ROOT = Path(".")
DEFAULT_OUTPUT_DIR = Path(".")
ARTIFACT_INDEX_PATH = REPO_ROOT / "artifacts" / "telegram_exports" / "INDEX.md"
DEFAULT_MIN_RECORDS = "20"
ACTION_LOG_DIR = Path(".")
RUNTIME_DIR = Path(".")
RUNTIME_OWNERS_DIR = Path(".")
RUNTIME_EVENTS_LOG_FILE = Path(".")
RUNTIME_ERRORS_LOG_FILE = Path(".")
MANAGED_HELPER_ROOT = Path(".")
MANAGED_HELPER_VENV_DIR = Path(".")
MANAGED_HELPER_PYTHON = Path(".")
PRODUCT_MODE = "repo"
PRODUCT_EXTENSION_ZIP = Path(".")
PRODUCT_DESKTOP_FILE = Path(".")
PRODUCT_ICON_PATH = Path(".")
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
UI_SCALE = resolve_ui_scale()
WINDOW_WIDTH = int(round(1380 * UI_SCALE))
WINDOW_HEIGHT = int(round(920 * UI_SCALE))
CHAT_LIST_READY_SELECTOR = "#LeftColumn a.chatlist-chat, #column-left a.chatlist-chat, a.chatlist-chat, #LeftColumn, #column-left"

TELEGRAM_TITLE_SUFFIX_RE = re.compile(r"\s*\|\s*Telegram\s*$", flags=re.I)


def _apply_runtime_settings(*, mutate: bool) -> None:
    global REPO_ROOT
    global RUN_ONCE_SCRIPT
    global SAFE_SNAPSHOT_SCRIPT
    global START_BROWSER_SCRIPT
    global EXTENSION_DIR
    global CDP_HELPER_SCRIPT
    global TDATA_HELPER_SCRIPT
    global TELEGRAM_WORKSPACE_ROOT
    global USER_REGISTRY_PATH
    global DEFAULT_PROFILE_DIR
    global PORTABLE_PROFILES_ROOT
    global DEFAULT_OUTPUT_DIR
    global ARTIFACT_INDEX_PATH
    global ACTION_LOG_DIR
    global RUNTIME_DIR
    global RUNTIME_OWNERS_DIR
    global RUNTIME_EVENTS_LOG_FILE
    global RUNTIME_ERRORS_LOG_FILE
    global MANAGED_HELPER_ROOT
    global MANAGED_HELPER_VENV_DIR
    global MANAGED_HELPER_PYTHON
    global PRODUCT_MODE
    global PRODUCT_EXTENSION_ZIP
    global PRODUCT_DESKTOP_FILE
    global PRODUCT_ICON_PATH
    global HUB_URL
    global TDATA_SESSION_DIR

    runtime_paths = load_gui_runtime_paths(mutate=mutate)
    settings = runtime_paths.settings
    REPO_ROOT = settings.project_root
    RUN_ONCE_SCRIPT = SCRIPTS_DIR / "run_chat_export_once.sh"
    SAFE_SNAPSHOT_SCRIPT = SCRIPTS_DIR / "write_telegram_safe_snapshot.py"
    START_BROWSER_SCRIPT = SCRIPTS_DIR / "start_browser.sh"
    EXTENSION_DIR = runtime_paths.extension_dir
    CDP_HELPER_SCRIPT = SCRIPTS_DIR / "telegram_cdp_helper.js"
    TDATA_HELPER_SCRIPT = SCRIPTS_DIR / "telegram_tdata_helper.py"
    TELEGRAM_WORKSPACE_ROOT = runtime_paths.telegram_workspace_root
    USER_REGISTRY_PATH = runtime_paths.user_registry_path
    DEFAULT_PROFILE_DIR = runtime_paths.default_profile_dir
    PORTABLE_PROFILES_ROOT = runtime_paths.portable_profiles_root
    DEFAULT_OUTPUT_DIR = runtime_paths.default_output_dir
    ARTIFACT_INDEX_PATH = runtime_paths.artifact_index_path
    ACTION_LOG_DIR = runtime_paths.action_log_dir
    RUNTIME_DIR = runtime_paths.runtime_dir
    RUNTIME_OWNERS_DIR = runtime_paths.runtime_owners_dir
    RUNTIME_EVENTS_LOG_FILE = settings.runtime_events_log_file
    RUNTIME_ERRORS_LOG_FILE = settings.runtime_errors_log_file
    MANAGED_HELPER_ROOT = runtime_paths.managed_helper_root
    MANAGED_HELPER_VENV_DIR = runtime_paths.managed_helper_venv_dir
    MANAGED_HELPER_PYTHON = runtime_paths.managed_helper_python
    PRODUCT_MODE = runtime_paths.product_mode
    PRODUCT_EXTENSION_ZIP = runtime_paths.extension_zip_path
    PRODUCT_DESKTOP_FILE = runtime_paths.desktop_file_path
    PRODUCT_ICON_PATH = runtime_paths.icon_path
    HUB_URL = runtime_paths.hub_url
    TDATA_SESSION_DIR = runtime_paths.tdata_session_dir
    sync_hook = globals().get("_sync_module_exports")
    if callable(sync_hook):
        sync_hook()


_apply_runtime_settings(mutate=False)
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


def operation_busy_status(operation_kind: str) -> str:
    if normalize_operation_kind(operation_kind) == "public_phones":
        return "Идёт сбор номеров..."
    return "Идёт сбор @username..."


def operation_output_path(path: Path, operation_kind: str) -> Path:
    candidate = path.expanduser()
    suffix = candidate.suffix if candidate.suffix else ".md"
    candidate = candidate.with_suffix(suffix)
    if normalize_operation_kind(operation_kind) != "public_phones":
        return candidate
    if candidate.stem.endswith("_phones"):
        return candidate
    return candidate.with_name(f"{candidate.stem}_phones{candidate.suffix}")


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
        phones = _progress_int(payload, "phones")
        if phones > 0:
            return f"{messages} сообщений, {phones} номеров"
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
    normalized = str(profile_value or "").replace("\\", "/")
    match = re.search(r"/accounts/(\d+)/", normalized)
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
    try:
        workdir_tdata.symlink_to(runtime_dir, target_is_directory=True)
    except OSError:
        shutil.copytree(runtime_dir, workdir_tdata)
        _chmod_best_effort(workdir_tdata, 0o700)


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
    return TDATA_EXPORT_TIMEOUT_SEC if str(command or "").startswith("export-") else TDATA_LIST_TIMEOUT_SEC


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



from .backend import TelegramGuiBackend
from .ui.window import TelegramMembersExportApp, TelegramMembersExportWindow

_MIRROR_MODULES = ("scripts.telegram_gui.backend", "scripts.telegram_gui.ui.window")
_MIRROR_SKIP = {
    "_MIRROR_MODULES",
    "_MIRROR_SKIP",
    "_mirror_globals",
    "_sync_module_exports",
    "_TelegramGuiAppModule",
    "_current_module",
}


def _mirror_globals() -> dict[str, Any]:
    return {
        name: value
        for name, value in globals().items()
        if name not in _MIRROR_SKIP and not name.startswith("__")
    }


def _sync_module_exports() -> None:
    mirrored = _mirror_globals()
    for module_name in _MIRROR_MODULES:
        module = sys.modules.get(module_name)
        if module is None:
            continue
        module.__dict__.update(mirrored)


class _TelegramGuiAppModule(types.ModuleType):
    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        if name.startswith("__") or name in _MIRROR_SKIP:
            return
        for module_name in _MIRROR_MODULES:
            module = sys.modules.get(module_name)
            if module is None:
                continue
            module.__dict__[name] = value


_current_module = sys.modules.get(__name__)
if _current_module is not None and not isinstance(_current_module, _TelegramGuiAppModule):
    _current_module.__class__ = _TelegramGuiAppModule
_sync_module_exports()



def main() -> int:
    _apply_runtime_settings(mutate=True)
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
    backend._log_action(
        f"app_started mode={PRODUCT_MODE} workspace={TELEGRAM_WORKSPACE_ROOT} "
        f"helper_python={TELEGRAM_API_COLLECTOR_PYTHON}"
    )
    app = TelegramMembersExportApp(backend)
    exit_code = app.run(sys.argv)
    lock.release()
    return int(exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
