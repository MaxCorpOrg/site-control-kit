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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango

try:
    from . import export_telegram_members_non_pii as export_mod
    from . import telegram_user_registry as registry_mod
    from . import telegram_workspace_layout as layout_mod
except ImportError:
    SCRIPT_DIR_FALLBACK = Path(__file__).resolve().parent
    if str(SCRIPT_DIR_FALLBACK) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR_FALLBACK))
    import export_telegram_members_non_pii as export_mod  # type: ignore[no-redef]
    import telegram_user_registry as registry_mod  # type: ignore[no-redef]
    import telegram_workspace_layout as layout_mod  # type: ignore[no-redef]


def _optional_timeout_env(name: str, *, default_value: str, minimum: int) -> int | None:
    raw = str(os.getenv(name, default_value) or default_value).strip()
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        parsed = int(default_value or "0")
    if parsed <= 0:
        return None
    return max(parsed, minimum)

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
RUN_ONCE_SCRIPT = SCRIPT_DIR / "run_chat_export_once.sh"
SAFE_SNAPSHOT_SCRIPT = SCRIPT_DIR / "write_telegram_safe_snapshot.py"
START_BROWSER_SCRIPT = REPO_ROOT / "start-browser.sh"
CDP_HELPER_SCRIPT = SCRIPT_DIR / "telegram_cdp_helper.js"
TDATA_HELPER_SCRIPT = SCRIPT_DIR / "telegram_tdata_helper.py"
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
DEFAULT_MIN_RECORDS = "20"
ACTION_LOG_DIR = TELEGRAM_WORKSPACE_ROOT / "logs"
RUNTIME_DIR = TELEGRAM_WORKSPACE_ROOT / "runtime"
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

HUB_URL = "http://127.0.0.1:8765"
TELEGRAM_WEB_URL = "https://web.telegram.org/a/"
CDP_PORT_BASE = 9227
CDP_PORT_SPAN = 240
TDATA_SESSION_DIR = RUNTIME_DIR / "tdata_sessions"
TDATA_SIGNATURE_FILES = ("key_datas", "D877F783D5D3EF8Cs", "D877F783D5D3EF8C/maps")
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


@dataclass(frozen=True)
class AccountOption:
    key: str
    label: str
    name: str
    token: str
    profile_source: str
    source_kind: str
    sort_key: tuple[int, str, str]


@dataclass(frozen=True)
class BrowserTarget:
    client_id: str
    tab_id: int
    tab_title: str
    tab_url: str


@dataclass(frozen=True)
class ChatOption:
    title: str
    subtitle: str
    url: str
    fragment: str
    peer_id: str
    active: bool
    visible: bool
    ordinal: int


@dataclass(frozen=True)
class ExportResult:
    output_path: Path
    usernames_txt: Path
    safe_count: int
    history_messages_scanned: int
    usernames_found: int
    interrupted: bool
    safe_txt: Path | None
    safe_md: Path | None
    log_path: Path
    action_log_path: Path


@dataclass
class ExportProgressState:
    chat_ref: str = ""
    messages_scanned: int = 0
    usernames_found: int = 0
    started_at: float = 0.0
    last_update_at: float = 0.0
    stage: str = ""
    interrupted: bool = False
    done: bool = False
    failed: bool = False
    total_messages_hint: int | None = None


class TaskCancelled(RuntimeError):
    pass


class TaskController:
    def __init__(self) -> None:
        self._cancel_event = threading.Event()
        self._lock = threading.Lock()
        self._processes: set[subprocess.Popen[str]] = set()

    @property
    def cancel_requested(self) -> bool:
        return self._cancel_event.is_set()

    def attach_process(self, process: subprocess.Popen[str]) -> None:
        with self._lock:
            self._processes.add(process)
        if self.cancel_requested:
            self._terminate_process(process)

    def detach_process(self, process: subprocess.Popen[str]) -> None:
        with self._lock:
            self._processes.discard(process)

    def request_cancel(self) -> None:
        self._cancel_event.set()
        with self._lock:
            processes = list(self._processes)
        for process in processes:
            self._terminate_process(process)

    def _terminate_process(self, process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        try:
            process.terminate()
        except OSError:
            return


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


class TelegramGuiBackend:
    def __init__(self, *, action_log_path: Path):
        self.action_log_path = action_log_path

    def load_accounts(self) -> list[AccountOption]:
        layout_mod.ensure_workspace(TELEGRAM_WORKSPACE_ROOT, slots=WORKSPACE_SLOTS)
        registry = registry_mod.load_registry(USER_REGISTRY_PATH)
        auto_profiles = layout_mod.list_profiles(TELEGRAM_WORKSPACE_ROOT)
        options: list[AccountOption] = []
        seen_profile_keys: set[str] = set()

        default_user_name = str(registry.get("default_user") or "").strip()
        for row in registry_mod.list_users(registry):
            name = str(row.get("name") or "").strip()
            token = str(row.get("token") or "").strip() or DEFAULT_TOKEN
            profile_source = str(row.get("profile") or "").strip()
            profile_key = _normalize_path_key(profile_source or str(DEFAULT_PROFILE_DIR))
            seen_profile_keys.add(profile_key)
            rank = 0 if name == default_user_name else 1
            label = name if name else "Пользователь из реестра"
            options.append(
                AccountOption(
                    key=f"registry:{name or profile_key}",
                    label=label,
                    name=name or label,
                    token=token,
                    profile_source=profile_source,
                    source_kind="registry",
                    sort_key=(rank, label.lower(), profile_key),
                )
            )

        for auto_name, profile_value in auto_profiles:
            profile_key = _normalize_path_key(profile_value)
            if profile_key in seen_profile_keys:
                continue
            slot_number = _slot_number_from_source(profile_value)
            token = _slot_token(slot_number) or DEFAULT_TOKEN
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
                )
            )

        options.sort(key=lambda item: item.sort_key)
        return options

    def ensure_connected(self, account: AccountOption, *, launch_browser: bool = True) -> BrowserTarget:
        profile_dir = resolve_profile_dir(account.profile_source)
        tdata_target = self._ensure_tdata_target(profile_dir, launch_browser=launch_browser)
        if tdata_target is not None:
            self._log_action(f"client_ready tdata client_id={tdata_target.client_id}")
            return tdata_target

        bridge_error = ""
        known_client_ids: set[str | None] = set()
        try:
            self._ensure_hub(account.token)
            known_client_ids = {item.get("client_id") for item in self._list_clients(account.token)}
            target = self._resolve_best_client(account.token, known_client_ids=known_client_ids, require_online=True)
            if target:
                self._log_action(f"client_ready bridge client_id={target.client_id} tab_id={target.tab_id}")
                return target
        except Exception as exc:
            bridge_error = str(exc)
            self._log_action(f"bridge_unavailable reason={bridge_error}")

        cdp_target = self._ensure_cdp_target(profile_dir, launch_browser=launch_browser)
        if cdp_target is not None:
            self._log_action(f"client_ready cdp client_id={cdp_target.client_id} tab_id={cdp_target.tab_id}")
            return cdp_target

        if not launch_browser:
            raise RuntimeError("Нет подключённого клиента Telegram. Нажмите 'Подключить Telegram'.")
        if bridge_error:
            raise RuntimeError(f"Не удалось подключить Telegram: {bridge_error}")
        raise RuntimeError("Не удалось подключить Telegram Web через выбранный профиль.")

    def fetch_chats(self, account: AccountOption, target: BrowserTarget) -> tuple[BrowserTarget, list[ChatOption]]:
        if self._is_tdata_target(target):
            tdata_dir = self._tdata_dir_from_target(target)
            if tdata_dir is None:
                raise RuntimeError("tdata target is invalid.")
            payload = self._run_tdata_helper("list-chats", tdata_dir=tdata_dir, extra_args=["--limit", "200"])
            chats = normalize_tdata_chat_options(payload)
            if not chats:
                raise RuntimeError("В tdata-сессии не удалось прочитать список диалогов.")
            refreshed = BrowserTarget(
                client_id=target.client_id,
                tab_id=target.tab_id,
                tab_title="Telegram Desktop",
                tab_url=str(tdata_dir),
            )
            self._log_action(f"chats_loaded tdata dir={tdata_dir} count={len(chats)}")
            return refreshed, chats

        if self._is_cdp_target(target):
            port = self._cdp_port_from_target(target)
            if port is None:
                raise RuntimeError("CDP target is invalid.")
            payload = self._run_cdp_helper(
                "list-chats",
                port=port,
                timeout_sec=50,
                extra_args=["--url", TELEGRAM_WEB_URL, "--timeout-ms", "45000"],
            )
            if payload.get("auth_required"):
                raise RuntimeError("В выбранном профиле Telegram не залогинен. Откройте Telegram и выполните вход.")
            chats = normalize_chat_options(payload)
            if not chats:
                raise RuntimeError(
                    "Telegram открыт, но список чатов пуст. Дождитесь полной загрузки левой колонки и обновите список."
                )
            refreshed = BrowserTarget(
                client_id=target.client_id,
                tab_id=target.tab_id,
                tab_title=_clean_tab_title(str(payload.get("current_title") or "Telegram")),
                tab_url=str(payload.get("current_url") or TELEGRAM_WEB_URL),
            )
            self._log_action(f"chats_loaded cdp port={port} count={len(chats)}")
            return refreshed, chats

        refreshed = self.ensure_connected(account, launch_browser=True)
        last_error = ""
        for attempt in range(5):
            if self._is_cdp_target(refreshed):
                return self.fetch_chats(account, refreshed)
            self._wait_for_chat_list_ready(account.token, refreshed.client_id, refreshed.tab_id)
            delivery = export_mod._send_command_result(
                server=HUB_URL,
                token=account.token,
                client_id=refreshed.client_id,
                tab_id=refreshed.tab_id,
                timeout_sec=12,
                command={"type": "run_script", "script": VISIBLE_DIALOGS_SCRIPT},
                raise_on_fail=False,
            )
            if delivery.get("ok"):
                payload = ((delivery.get("data") or {}).get("value") or {}) if isinstance(delivery.get("data"), dict) else {}
                chats = normalize_chat_options(payload)
                if chats:
                    self._log_action(f"chats_loaded client_id={refreshed.client_id} count={len(chats)}")
                    return refreshed, chats
                last_error = "Список диалогов пока пустой"
            else:
                last_error = _format_command_error(delivery.get("error")) or "Не удалось получить список чатов из Telegram Web."
            if attempt < 4:
                time.sleep(0.8)
                refreshed = self.ensure_connected(account, launch_browser=True)
        raise RuntimeError(
            f"{last_error or 'Telegram открыт, но список диалогов не прочитан.'} "
            "Откройте Telegram Web, дождитесь загрузки левой колонки и обновите список."
        )

    def open_chat(self, account: AccountOption, target: BrowserTarget, chat: ChatOption) -> BrowserTarget:
        if self._is_tdata_target(target):
            self._log_action(f"chat_opened tdata direct chat_ref={chat.fragment}")
            return target

        if self._is_cdp_target(target):
            port = self._cdp_port_from_target(target)
            if port is None:
                raise RuntimeError("CDP target is invalid.")
            payload = self._run_cdp_helper(
                "open-chat",
                port=port,
                timeout_sec=40,
                extra_args=["--url", chat.url, "--timeout-ms", "30000"],
            )
            final_target = BrowserTarget(
                client_id=target.client_id,
                tab_id=target.tab_id,
                tab_title=_clean_tab_title(str(payload.get("current_title") or chat.title)),
                tab_url=str(payload.get("current_url") or chat.url),
            )
            self._log_action(f"chat_opened cdp port={port} url={chat.url}")
            return final_target

        refreshed = self._refresh_target(account.token, target.client_id, target.tab_id)
        delivery = export_mod._send_command_result(
            server=HUB_URL,
            token=account.token,
            client_id=refreshed.client_id,
            tab_id=refreshed.tab_id,
            timeout_sec=12,
            command={"type": "navigate", "url": chat.url},
            raise_on_fail=False,
        )
        if not delivery.get("ok"):
            raise RuntimeError(_format_command_error(delivery.get("error")) or f"Не удалось открыть чат {chat.title}.")
        time.sleep(0.8)
        final_target = self._refresh_target(account.token, refreshed.client_id, refreshed.tab_id)
        self._log_action(f"chat_opened client_id={final_target.client_id} url={chat.url}")
        return final_target

    def run_export(
        self,
        account: AccountOption,
        target: BrowserTarget,
        chat: ChatOption,
        output_path: Path,
        emit: Callable[[str], None],
        controller: TaskController | None = None,
    ) -> ExportResult:
        profile_dir = resolve_profile_dir(account.profile_source)
        ACTION_LOG_DIR.mkdir(parents=True, exist_ok=True)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = _utc_timestamp()
        run_log_path = ACTION_LOG_DIR / f"export_run_{timestamp}.log"
        self._log_action(f"run_start output={output_path} chat={chat.url} client_id={target.client_id}")
        try:
            if self._is_tdata_target(target):
                tdata_dir = self._tdata_dir_from_target(target)
                if tdata_dir is None:
                    raise RuntimeError("tdata target is invalid.")
                return self._run_export_via_tdata(
                    tdata_dir=tdata_dir,
                    chat=chat,
                    output_path=output_path,
                    run_log_path=run_log_path,
                    emit=emit,
                    controller=controller,
                )

            if self._is_cdp_target(target):
                port = self._cdp_port_from_target(target)
                if port is None:
                    raise RuntimeError("CDP target is invalid.")
                return self._run_export_via_cdp(
                    port=port,
                    chat=chat,
                    output_path=output_path,
                    run_log_path=run_log_path,
                    emit=emit,
                    controller=controller,
                )

            env = os.environ.copy()
            env["SITECTL_TOKEN"] = account.token
            env["SITECTL_BROWSER_PROFILE"] = str(profile_dir)
            env["CHAT_CLIENT_ID"] = target.client_id

            command = [
                str(RUN_ONCE_SCRIPT),
                account.token,
                str(output_path),
                chat.url,
                CHAT_STEPS,
                CHAT_DEEP_LIMIT,
                CHAT_TIMEOUT_SEC,
                CHAT_MAX_RUNTIME,
                CHAT_DEEP_MODE,
                DEFAULT_MIN_RECORDS,
                target.client_id,
            ]

            process = subprocess.Popen(
                command,
                cwd=str(REPO_ROOT),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            if controller is not None:
                controller.attach_process(process)
            with run_log_path.open("w", encoding="utf-8") as handle:
                assert process.stdout is not None
                for raw_line in process.stdout:
                    handle.write(raw_line)
                    handle.flush()
                    emit(raw_line.rstrip())
            return_code = process.wait()
            if controller is not None:
                controller.detach_process(process)
            if controller is not None and controller.cancel_requested:
                raise TaskCancelled("Экспорт остановлен пользователем.")
            if return_code != 0:
                self._log_action(f"run_failed rc={return_code} log={run_log_path}")
                raise RuntimeError(f"Экспорт завершился ошибкой. Смотрите лог: {run_log_path}")

            safe_dir = output_path.parent / f"telegram_export_{slugify_filename(chat.url)}"
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

            payload = parse_key_value_output(snapshot.stdout)
            usernames_txt = output_path.with_name(f"{output_path.stem}_usernames.txt")
            safe_txt = _optional_path(payload.get("safe_txt"))
            safe_md = _optional_path(payload.get("safe_md"))
            safe_count = int(payload.get("safe_count") or 0)
            self._log_action(f"run_success output={output_path} safe_count={safe_count}")
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
            )
        except Exception as exc:
            self._log_action(f"run_failed error={type(exc).__name__} message={_compact_error_text(str(exc))}")
            raise

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

    def _ensure_tdata_target(self, profile_dir: Path, *, launch_browser: bool) -> BrowserTarget | None:
        if not TELEGRAM_API_COLLECTOR_PYTHON.exists():
            return None
        for tdata_dir in list_candidate_tdata_dirs(profile_dir):
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
        run_log_path: Path,
        emit: Callable[[str], None],
        controller: TaskController | None = None,
    ) -> ExportResult:
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
                TDATA_HISTORY_LIMIT,
                "--progress-every",
                TDATA_PROGRESS_EVERY,
            ],
            emit=emit,
            controller=controller,
        )
        rows = payload.get("rows") if isinstance(payload, dict) else []
        members = rows if isinstance(rows, list) else []
        export_mod._write_markdown(output_path, members, chat.url or chat.fragment, "tdata-history-authors")
        username_rows = export_mod._collect_username_rows(members)
        sidecars = export_mod._write_username_sidecars(output_path, username_rows, chat.url or chat.fragment, "tdata-history-authors")
        with run_log_path.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2))
            handle.write("\n")
        stats = payload.get("stats") or {}
        history_messages_scanned = int(stats.get("history_messages_scanned") or 0)
        interrupted = bool(payload.get("interrupted")) or bool(stats.get("interrupted"))
        emit(f"tdata source=history-only")
        emit(f"tdata history_messages={history_messages_scanned}")
        emit(f"tdata usernames={len(username_rows)}")
        if interrupted:
            emit("tdata interrupted=1")

        safe_dir = output_path.parent / f"telegram_export_{slugify_filename(chat.title or chat.fragment)}"
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

        payload_map = parse_key_value_output(snapshot.stdout)
        safe_txt = _optional_path(payload_map.get("safe_txt"))
        safe_md = _optional_path(payload_map.get("safe_md"))
        safe_count = int(payload_map.get("safe_count") or 0)
        usernames_txt = Path(str(sidecars.get("usernames_txt") or output_path.with_name(f"{output_path.stem}_usernames.txt")))
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
        session_path = TDATA_SESSION_DIR / f"{_tdata_target_key(tdata_dir)}.session"
        TDATA_SESSION_DIR.mkdir(parents=True, exist_ok=True)
        args = [
            str(TELEGRAM_API_COLLECTOR_PYTHON),
            str(TDATA_HELPER_SCRIPT),
            command,
            "--tdata",
            str(tdata_dir),
            "--session",
            str(session_path),
        ]
        if extra_args:
            args.extend(extra_args)
        process = subprocess.Popen(
            args,
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        if controller is not None:
            controller.attach_process(process)
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []

        def consume_stdout() -> None:
            assert process.stdout is not None
            for line in process.stdout:
                stdout_lines.append(line)

        def consume_stderr() -> None:
            assert process.stderr is not None
            for line in process.stderr:
                stderr_lines.append(line)
                text = line.rstrip()
                if emit is not None and text:
                    emit(text)

        stdout_thread = threading.Thread(target=consume_stdout, daemon=True)
        stderr_thread = threading.Thread(target=consume_stderr, daemon=True)
        stdout_thread.start()
        stderr_thread.start()

        effective_timeout = timeout_sec if timeout_sec is not None else _tdata_helper_timeout_seconds(command)
        return_code, timed_out, forced_cancel = self._wait_for_process_exit(
            process,
            timeout_sec=effective_timeout,
            controller=controller,
            on_cancel_begin=(lambda: emit("Остановка сканирования: завершаем текущий проход...") if emit else None),
        )
        stdout_thread.join(timeout=1)
        stderr_thread.join(timeout=1)
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()
        if controller is not None:
            controller.detach_process(process)
        if forced_cancel:
            raise TaskCancelled("Сканирование остановлено пользователем.")
        if timed_out:
            progress_hint = _latest_progress_summary(stderr_lines)
            suffix = f" Последний прогресс: {progress_hint}." if progress_hint else ""
            if command == "export-chat":
                raise RuntimeError(
                    f"Скан истории Telegram превысил настроенный лимит {effective_timeout}s.{suffix} "
                    "Уберите TELEGRAM_TDATA_EXPORT_TIMEOUT_SEC или поставьте 0 для полного прохода без лимита. "
                    "Если нужен только короткий тестовый прогон, уменьшите TELEGRAM_TDATA_HISTORY_LIMIT."
                )
            raise RuntimeError(f"tdata helper timed out after {effective_timeout}s: {command}{suffix}")
        stdout_text = "".join(stdout_lines)
        stderr_text = "".join(stderr_lines)
        if controller is not None and controller.cancel_requested and return_code != 0:
            raise TaskCancelled("Сканирование остановлено пользователем.")
        if return_code != 0:
            message = (stderr_text or stdout_text).strip()
            raise RuntimeError(message or f"tdata helper failed: {command}")
        try:
            payload = json.loads(stdout_text)
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
        run_log_path: Path,
        emit: Callable[[str], None],
        controller: TaskController | None = None,
    ) -> ExportResult:
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
        with run_log_path.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2))
            handle.write("\n")
        emit(f"simple-cdp members={len(members)}")
        emit(f"simple-cdp usernames={len(username_rows)}")

        safe_dir = output_path.parent / f"telegram_export_{slugify_filename(chat.url)}"
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

        payload_map = parse_key_value_output(snapshot.stdout)
        safe_txt = _optional_path(payload_map.get("safe_txt"))
        safe_md = _optional_path(payload_map.get("safe_md"))
        safe_count = int(payload_map.get("safe_count") or 0)
        usernames_txt = Path(str(sidecars.get("usernames_txt") or output_path.with_name(f"{output_path.stem}_usernames.txt")))
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
        process = subprocess.Popen(
            args,
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if controller is not None:
            controller.attach_process(process)
        return_code, timed_out, forced_cancel = self._wait_for_process_exit(
            process,
            timeout_sec=max(timeout_sec, 5),
            controller=controller,
        )
        stdout_text, stderr_text = process.communicate()
        if controller is not None:
            controller.detach_process(process)
        if forced_cancel or (controller is not None and controller.cancel_requested and return_code != 0):
            raise TaskCancelled("Экспорт остановлен пользователем.")
        if timed_out:
            raise RuntimeError(f"CDP helper timed out after {max(timeout_sec, 5)}s: {command}")
        if return_code != 0:
            message = (stderr_text or stdout_text or "").strip()
            raise RuntimeError(message or f"CDP helper failed: {command}")
        try:
            payload = json.loads(stdout_text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"CDP helper returned invalid JSON for {command}.") from exc
        if not isinstance(payload, dict):
            raise RuntimeError(f"CDP helper returned unexpected payload for {command}.")
        return payload

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
            subprocess.Popen(
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

        self._terminate_stale_hub_listeners()
        log_path = ACTION_LOG_DIR / "hub_gui_boot.log"
        ACTION_LOG_DIR.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            subprocess.Popen(
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
        deadline = time.time() + 6
        while time.time() < deadline:
            try:
                export_mod._http_json(HUB_URL, token, "GET", "/api/clients", request_timeout_sec=1.0)
                self._log_action("hub_ready")
                return
            except RuntimeError:
                time.sleep(0.25)
        raise RuntimeError(f"Не удалось поднять hub. Лог: {log_path}")

    def _terminate_stale_hub_listeners(self) -> None:
        cmd = "ss -ltnp 'sport = :8765' 2>/dev/null | sed -n 's/.*pid=\\([0-9]\\+\\).*/\\1/p' | sort -u"
        result = subprocess.run(["bash", "-lc", cmd], capture_output=True, text=True, check=False)
        for raw in result.stdout.splitlines():
            value = raw.strip()
            if not value.isdigit():
                continue
            try:
                os.kill(int(value), signal.SIGKILL)
                self._log_action(f"hub_stale_listener_killed pid={value}")
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

    def _wait_for_process_exit(
        self,
        process: subprocess.Popen[str],
        *,
        timeout_sec: int | None,
        controller: TaskController | None,
        on_cancel_begin: Callable[[], None] | None = None,
    ) -> tuple[int, bool, bool]:
        deadline = time.monotonic() + max(timeout_sec, 1) if timeout_sec is not None else None
        cancel_deadline: float | None = None
        cancel_notified = False
        while True:
            return_code = process.poll()
            if return_code is not None:
                return return_code, False, False
            now = time.monotonic()
            if controller is not None and controller.cancel_requested:
                if cancel_deadline is None:
                    cancel_deadline = now + 6.0
                    if on_cancel_begin is not None and not cancel_notified:
                        on_cancel_begin()
                        cancel_notified = True
                    try:
                        process.terminate()
                    except OSError:
                        pass
                elif now >= cancel_deadline:
                    try:
                        process.kill()
                    except OSError:
                        pass
                    process.wait(timeout=1)
                    return process.returncode or -1, False, True
            if deadline is not None and now >= deadline:
                try:
                    process.kill()
                except OSError:
                    pass
                process.wait(timeout=1)
                return process.returncode or -1, True, False
            time.sleep(0.1)

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
        self.chat_rows: list[ChatOption] = []
        self.filtered_chat_rows: list[ChatOption] = []
        self.connected_target: BrowserTarget | None = None
        self.current_task: str | None = None
        self.current_controller: TaskController | None = None
        self.last_export_result: ExportResult | None = None
        self.export_progress_state: ExportProgressState | None = None

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
        self.client_label = Gtk.Label(label="Клиент Telegram не выбран")
        self.chat_meta_label = Gtk.Label(label="Список чатов ещё не загружен")
        self.chat_title_label = Gtk.Label(label="Чат не выбран")
        self.chat_url_label = Gtk.Label(label="")
        self.result_label = Gtk.Label(label="Результат экспорта появится здесь")
        self.output_entry = Gtk.Entry()
        self.search_entry = Gtk.SearchEntry()
        self.account_combo = Gtk.ComboBoxText()
        self.chat_listbox = Gtk.ListBox()
        self.log_buffer = Gtk.TextBuffer()
        self.log_view = Gtk.TextView(buffer=self.log_buffer)
        self.progress_bar = Gtk.ProgressBar()
        self.progress_status_label = Gtk.Label(label="Прогресс появится после старта экспорта")
        self.progress_meta_label = Gtk.Label(label="Сообщений: 0 | @username: 0")
        self.progress_hint_label = Gtk.Label(label="Долгие чаты сканируются по истории. Кнопка остановки активируется во время сбора.")
        self.stop_button = Gtk.Button(label="Остановить сбор")

        self._build_ui()
        self._load_accounts_into_ui()
        GLib.idle_add(self._apply_initial_window_geometry)
        GLib.timeout_add(250, self._tick_progress)

    def _build_ui(self) -> None:
        self.root_box.append(self._build_hero())
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

        right.append(self._build_export_section())
        right.append(self._build_log_section())

    def _build_hero(self) -> Gtk.Widget:
        hero = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
        hero.add_css_class("hero")

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        text_box.set_hexpand(True)
        title = Gtk.Label(label="Telegram Username Collector")
        title.set_xalign(0)
        title.add_css_class("hero-title")
        copy = Gtk.Label(
            label="Выберите профиль, загрузите список диалогов прямо из Telegram и сохраните экспорт в выбранный .md файл.",
            wrap=True,
            justify=Gtk.Justification.LEFT,
            xalign=0,
        )
        copy.add_css_class("hero-copy")
        text_box.append(title)
        text_box.append(copy)
        hero.append(text_box)

        self.hero_status.add_css_class("badge")
        hero.append(self.hero_status)
        hero.append(self._build_hero_art())
        return hero

    def _build_hero_art(self) -> Gtk.Widget:
        art = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        art.add_css_class("art-card")
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        chip_a = Gtk.Label(label="Chats")
        chip_a.add_css_class("art-chip")
        chip_b = Gtk.Label(label="@username")
        chip_b.add_css_class("art-chip")
        top.append(chip_a)
        top.append(chip_b)
        art.append(top)

        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        pill = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        pill.add_css_class("dim-box")
        pill.append(self._meta_label("Open from list"))
        pill.append(self._meta_label("Save via file chooser"))
        token = Gtk.Label(label="ID")
        token.add_css_class("art-chip")
        bottom.append(pill)
        bottom.append(token)
        art.append(bottom)
        return art

    def _build_account_section(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.append(self._section_title("1. Профиль и подключение"))

        self.account_combo.set_hexpand(True)
        self.account_combo.connect("changed", lambda *_args: self._on_account_changed())
        box.append(self.account_combo)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.append(self._button("Подключить Telegram", self._connect_selected_account, accent=True))
        actions.append(self._button("Обновить профили", self._load_accounts_into_ui))
        box.append(actions)

        self.client_label.set_xalign(0)
        self.client_label.set_wrap(True)
        self.client_label.add_css_class("meta")
        box.append(self.client_label)
        return box

    def _build_chat_section(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_vexpand(True)
        box.append(self._section_title("2. Чаты и группы из Telegram"))

        self.search_entry.set_hexpand(True)
        self.search_entry.set_placeholder_text("Фильтр по названию, описанию или URL")
        self.search_entry.connect("search-changed", lambda *_args: self._apply_chat_filter())
        box.append(self.search_entry)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.append(self._button("Обновить список", self._refresh_chats))
        actions.append(self._button("Открыть чат", self._open_selected_chat))
        box.append(actions)

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
        box.append(self._section_title("3. Экспорт и результат"))

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

        self.output_entry.set_hexpand(True)
        self.output_entry.set_placeholder_text("Путь к .md файлу")
        choose_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        choose_row.append(self.output_entry)
        choose_row.append(self._button("Выбрать .md файл", self._choose_output_file))
        box.append(choose_row)
        box.append(self._meta_label("Откроется системный диалог: там выбираются и папка, и имя итогового файла."))

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.append(self._button("Собрать @username", self._run_export, accent=True))
        self.stop_button.connect("clicked", lambda *_args: self._request_stop())
        self.stop_button.add_css_class("subtle-button")
        self.stop_button.set_sensitive(False)
        actions.append(self.stop_button)
        box.append(actions)
        box.append(self._button("Открыть папку результата", self._open_result_directory))
        box.append(self._build_progress_section())

        self.result_label.set_xalign(0)
        self.result_label.set_wrap(True)
        self.result_label.set_selectable(True)
        self.result_label.add_css_class("meta")
        box.append(self.result_label)
        return box

    def _build_progress_section(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.add_css_class("dim-box")
        progress_title = Gtk.Label(label="Прогресс сканирования")
        progress_title.set_xalign(0)
        progress_title.add_css_class("card-title")
        box.append(progress_title)

        self.progress_bar.set_hexpand(True)
        self.progress_bar.set_show_text(True)
        self.progress_bar.set_text("Ожидание")
        self.progress_bar.set_fraction(0.0)
        box.append(self.progress_bar)

        for label in (self.progress_status_label, self.progress_meta_label, self.progress_hint_label):
            label.set_xalign(0)
            label.set_wrap(True)
            label.add_css_class("meta")
            box.append(label)
        return box

    def _build_log_section(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_vexpand(True)
        box.append(self._section_title("Живой лог"))
        self.log_view.set_editable(False)
        self.log_view.set_cursor_visible(False)
        self.log_view.set_monospace(True)
        self.log_view.set_vexpand(True)
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(self.log_view)
        box.append(scroll)
        self._append_log("Приложение готово. Выберите профиль и подключите Telegram.")
        return box

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
        self.export_progress_state = ExportProgressState(
            chat_ref=chat.fragment,
            started_at=now,
            last_update_at=now,
            stage="start",
            failed=False,
            total_messages_hint=_positive_int(TDATA_HISTORY_LIMIT),
        )
        self.stop_button.set_sensitive(True)
        self._render_progress_state()

    def _request_stop(self) -> None:
        if self.current_task != "export" or self.current_controller is None:
            self._show_warning("Сейчас нечего останавливать.")
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

    def _consume_progress_message(self, message: str) -> None:
        payload = parse_progress_line(message)
        if not payload:
            return
        state = self.export_progress_state
        now = time.monotonic()
        if state is None:
            state = ExportProgressState(
                chat_ref=str(payload.get("chat") or ""),
                started_at=now,
                last_update_at=now,
                total_messages_hint=_positive_int(TDATA_HISTORY_LIMIT),
            )
            self.export_progress_state = state
        state.chat_ref = str(payload.get("chat") or state.chat_ref)
        state.messages_scanned = max(state.messages_scanned, _progress_int(payload, "messages"))
        state.usernames_found = max(state.usernames_found, _progress_int(payload, "usernames"))
        state.last_update_at = now
        state.interrupted = bool(_progress_int(payload, "interrupted"))
        state.done = bool(_progress_int(payload, "done"))
        state.failed = False
        state.stage = str(payload.get("stage") or ("done" if state.done else state.stage or "scan")).strip()
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

    def _load_accounts_into_ui(self) -> None:
        try:
            self.accounts = self.backend.load_accounts()
        except Exception as exc:
            self._show_error(str(exc))
            return
        self.account_map = {item.label: item for item in self.accounts}
        self.account_combo.remove_all()
        for item in self.accounts:
            self.account_combo.append_text(item.label)
        if self.accounts:
            self.account_combo.set_active(0)
            self._append_log(f"Профили загружены: {len(self.accounts)}")
            self._on_account_changed()
        else:
            self.hero_status.set_label("Нет профиля")
            self.client_label.set_label("Профили не найдены. Положите Telegram-профиль в ~/.site-control-kit/telegram_workspace/accounts/1/profile")
            self._append_log("Профили не найдены")

    def _selected_account(self) -> AccountOption | None:
        label = self.account_combo.get_active_text()
        return self.account_map.get(label) if label else None

    def _selected_chat(self) -> ChatOption | None:
        row = self.chat_listbox.get_selected_row()
        return getattr(row, "chat", None) if row is not None else None

    def _on_account_changed(self) -> None:
        account = self._selected_account()
        self.connected_target = None
        self.chat_rows = []
        self.filtered_chat_rows = []
        self._reset_progress_display()
        self._render_chat_rows()
        if account is None:
            return
        self.hero_status.set_label("Профиль выбран")
        self.client_label.set_label(f"Выбран профиль: {account.label}")
        self.chat_meta_label.set_label("Нажмите 'Подключить Telegram'. Список чатов загрузится автоматически.")
        self.result_label.set_label("Результат экспорта появится здесь")
        self.output_entry.set_text("")
        self.chat_title_label.set_label("Чат не выбран")
        self.chat_url_label.set_label("")

    def _connect_selected_account(self) -> None:
        account = self._selected_account()
        if account is None:
            self._show_error("Сначала выберите профиль.")
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

        def worker() -> tuple[BrowserTarget, list[ChatOption]]:
            target = self.connected_target or self.backend.ensure_connected(account, launch_browser=True)
            return self.backend.fetch_chats(account, target)

        self._start_task(
            task_name="refresh_chats",
            busy_status="Читаем список диалогов...",
            worker=worker,
            on_success=self._handle_chats_loaded,
        )

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
        if account is None or chat is None:
            self._show_error("Выберите профиль и чат.")
            return
        if self.connected_target is None:
            self._show_error("Сначала подключите Telegram и загрузите список чатов.")
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

    def _handle_connected_target(self, target: BrowserTarget) -> None:
        self.connected_target = target
        self.hero_status.set_label("Telegram подключён")
        client_label = (
            "Режим: Telegram Desktop tdata"
            if str(target.client_id or "").startswith("tdata:")
            else "Режим: Chrome profile direct"
            if str(target.client_id or "").startswith("cdp:")
            else f"Клиент: {target.client_id}"
        )
        self.client_label.set_label(f"{client_label} | вкладка: {target.tab_title or target.tab_url or 'Telegram'}")
        meta_label = (
            "Сессия прочитана из Telegram Desktop tdata. Загружаем список чатов напрямую из аккаунта..."
            if str(target.client_id or "").startswith("tdata:")
            else "Клиент найден. Загружаем список чатов и групп из Telegram Web..."
        )
        self.chat_meta_label.set_label(meta_label)
        self._append_log(f"Клиент готов: {target.client_id} / tab {target.tab_id}")
        self._refresh_chats()

    def _handle_chats_loaded(self, payload: tuple[BrowserTarget, list[ChatOption]]) -> None:
        target, chats = payload
        self.connected_target = target
        self.chat_rows = chats
        self._apply_chat_filter()
        active_count = sum(1 for item in chats if item.active)
        self.hero_status.set_label("Список чатов загружен")
        if self.backend._is_tdata_target(target):
            self.chat_meta_label.set_label(
                f"Загружено {len(chats)} диалогов напрямую из Telegram-сессии. Если нужного чата нет, обновите список ещё раз."
            )
        else:
            self.chat_meta_label.set_label(
                f"Загружено {len(chats)} диалогов из Telegram Web. Активных в выдаче: {active_count}. Если нужного чата нет, прокрутите список слева в Telegram и обновите снова."
            )
        self._append_log(f"Чаты загружены: {len(chats)}")

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

    def _on_chat_selected(self) -> None:
        chat = self._selected_chat()
        if chat is None:
            self.chat_title_label.set_label("Чат не выбран")
            self.chat_url_label.set_label("")
            return
        self.chat_title_label.set_label(chat.title)
        subtitle = f"{chat.subtitle}\n" if chat.subtitle else ""
        self.chat_url_label.set_label(f"{subtitle}{chat.url}")
        if not self.output_entry.get_text().strip():
            suggested = DEFAULT_OUTPUT_DIR / f"{slugify_filename(chat.title or chat.fragment)}.md"
            self.output_entry.set_text(str(suggested))

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

        def run() -> None:
            try:
                result = worker()
            except Exception as exc:
                GLib.idle_add(self._finish_task_error, exc)
                return
            GLib.idle_add(self._finish_task_success, on_success, result)

        threading.Thread(target=run, daemon=True).start()

    def _finish_task_success(self, callback: Callable[[Any], None], result: Any) -> bool:
        self.current_task = None
        self.current_controller = None
        self.stop_button.set_sensitive(False)
        callback(result)
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
        GLib.idle_add(self._append_log, message)

    def _append_log(self, message: str) -> bool:
        if not message:
            return False
        self._consume_progress_message(message)
        stamp = datetime.now().strftime("%H:%M:%S")
        end_iter = self.log_buffer.get_end_iter()
        self.log_buffer.insert(end_iter, f"[{stamp}] {message}\n")
        mark = self.log_buffer.create_mark(None, self.log_buffer.get_end_iter(), False)
        self.log_view.scroll_mark_onscreen(mark)
        return False

    def _show_dialog(self, message_type: Gtk.MessageType, text: str) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=message_type,
            buttons=Gtk.ButtonsType.OK,
            text=WINDOW_TITLE,
            secondary_text=text,
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


def _slot_token(slot_number: str) -> str:
    if not slot_number:
        return ""
    token_path = TELEGRAM_WORKSPACE_ROOT / "accounts" / slot_number / "keys" / "api_token.txt"
    try:
        return token_path.read_text(encoding="utf-8", errors="ignore").strip()
    except OSError:
        return ""


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
    candidates = list_candidate_tdata_dirs(profile_dir)
    if candidates:
        return candidates[0]
    return None


def list_candidate_tdata_dirs(profile_dir: Path) -> list[Path]:
    root = profile_dir.expanduser().resolve()
    candidates: list[Path] = []

    collector_tdata = TELEGRAM_API_COLLECTOR_TDATA_DIR.expanduser().resolve()
    if collector_tdata.is_dir() and _collector_tdata_matches_profile(root, collector_tdata):
        candidates.append(collector_tdata)

    candidates.extend(_tdata_dirs_from_metadata(root))
    candidates.extend(_local_tdata_dirs(root))
    return _dedupe_paths(candidates)


def _local_tdata_dirs(root: Path) -> list[Path]:
    candidates: list[Path] = []
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


def _install_css() -> None:
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS)
    display = Gdk.Display.get_default()
    if display is not None:
        Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


class TelegramMembersExportApp(Gtk.Application):
    def __init__(self, backend: TelegramGuiBackend):
        super().__init__(application_id="local.sitecontrol.telegram_members_export_gui")
        self.backend = backend
        self.window: TelegramMembersExportWindow | None = None

    def do_activate(self) -> None:
        _install_css()
        if self.window is None:
            self.window = TelegramMembersExportWindow(self, self.backend)
        self.window.present()


def main() -> int:
    for path, label in (
        (RUN_ONCE_SCRIPT, "run script"),
        (SAFE_SNAPSHOT_SCRIPT, "safe snapshot script"),
        (START_BROWSER_SCRIPT, "browser launcher"),
        (CDP_HELPER_SCRIPT, "CDP helper"),
        (TDATA_HELPER_SCRIPT, "tdata helper"),
    ):
        if not path.exists():
            raise RuntimeError(f"Не найден {label}: {path}")
    if not shutil.which("node"):
        raise RuntimeError("Не найден node, который нужен для прямого подключения к Chrome CDP.")

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
