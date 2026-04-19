#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import html as html_lib
import json
import os
import re
import socket
import subprocess
import sys
import time
import webbrowser
from http.client import HTTPException
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_SERVER = "http://127.0.0.1:8765"
DEFAULT_TOKEN = "local-bridge-quickstart-2026"
TOKEN_ENV = "SITECTL_TOKEN"
TERMINAL_STATUSES = {
    "completed",
    "failed",
    "partial",
    "canceled",
    "cancelled",
    "expired",
    "rejected",
}
USERNAME_VALUE_RE = re.compile(r"[A-Za-z0-9_]{5,32}")
USERNAME_SUBTITLE_MARKERS = (
    "username",
    "имя пользователя",
    "nome de usuário",
    "nombre de usuario",
    "benutzername",
    "nom d'utilisateur",
    "nome utente",
    "kullanıcı adı",
)
CHAT_TOP_SELECTOR = ".bubbles .sticky_sentinel--top"
CHAT_SCROLL_SELECTORS = (
    ".bubbles .sticky_sentinel--top",
    ".chat.tabs-tab.active .bubbles .bubbles-group-avatar",
    "#column-center .bubbles [data-mid]",
    ".chat.tabs-tab.active .bubbles",
)
CHAT_ANCHOR_AVATAR_SELECTORS = (
    ".chat.tabs-tab.active .bubbles .bubbles-group-avatar.user-avatar",
    "#column-center .bubbles .bubbles-group-avatar.user-avatar",
    ".bubbles .bubbles-group-avatar.user-avatar",
)
CHAT_ANCHOR_CONTEXT_SELECTORS = (
    ".chat.tabs-tab.active .bubbles .bubbles-group-avatar.user-avatar .avatar-photo",
    ".chat.tabs-tab.active .bubbles .bubbles-group-avatar.user-avatar",
    "#column-center .bubbles .bubbles-group-avatar.user-avatar .avatar-photo",
    "#column-center .bubbles .bubbles-group-avatar.user-avatar",
    ".bubbles .bubbles-group-avatar.user-avatar .avatar-photo",
    ".bubbles .bubbles-group-avatar.user-avatar",
)
CHAT_SCROLL_SETTLE_SEC = 0.35
CHAT_SCROLL_DISTANCE_PX = 900
CHAT_UNCHANGED_STEPS_LIMIT = 6
CHAT_DISCOVERY_MENTION_DEEP_INTERVAL = max(int(os.environ.get("TELEGRAM_CHAT_DISCOVERY_MENTION_INTERVAL", "5") or "5"), 1)
CHAT_DISCOVERY_SCROLL_BURST = max(int(os.environ.get("TELEGRAM_CHAT_DISCOVERY_SCROLL_BURST", "2") or "2"), 1)
CHAT_DISCOVERY_BURST_SETTLE_SEC = max(float(os.environ.get("TELEGRAM_CHAT_DISCOVERY_BURST_SETTLE_SEC", "0.12") or "0.12"), 0.02)
DISCOVERY_STATE_MAX_SIGNATURES = max(int(os.environ.get("TELEGRAM_DISCOVERY_STATE_MAX_SIGNATURES", "400") or "400"), 50)
DISCOVERY_STATE_MAX_PEERS = max(int(os.environ.get("TELEGRAM_DISCOVERY_STATE_MAX_PEERS", "5000") or "5000"), 100)
INFO_SCROLL_SETTLE_SEC = 0.8
CHAT_DEEP_DEFAULT_LIMIT = 3
X11_WHEEL_FALLBACK_ENABLED = os.environ.get("TELEGRAM_X11_WHEEL_FALLBACK", "1").strip().lower() not in {"0", "false", "no"}
X11_WHEEL_BUTTON = int(os.environ.get("TELEGRAM_X11_WHEEL_BUTTON", "5") or "5")
X11_WHEEL_CLICKS = max(int(os.environ.get("TELEGRAM_X11_WHEEL_CLICKS", "8") or "8"), 1)
X11_WHEEL_SETTLE_SEC = max(float(os.environ.get("TELEGRAM_X11_WHEEL_SETTLE_SEC", "0.8") or "0.8"), 0.1)
X11_WHEEL_X_RATIO = min(max(float(os.environ.get("TELEGRAM_X11_WHEEL_X_RATIO", "0.58") or "0.58"), 0.05), 0.95)
X11_WHEEL_Y_RATIO = min(max(float(os.environ.get("TELEGRAM_X11_WHEEL_Y_RATIO", "0.42") or "0.42"), 0.05), 0.95)
SPECIFIC_TG_DIALOG_URL_RE = re.compile(r"^https?://web\.telegram\.org/(k|a)/#[^#\s]+$", flags=re.I)
ACTIVE_CLIENT_MAX_AGE_SEC = 90
ACTIVE_CLIENT_WAIT_SEC = 25
HTTP_REQUEST_TIMEOUT_SEC = max(int(os.environ.get("TELEGRAM_HTTP_TIMEOUT_SEC", "20") or "20"), 5)


def _norm_server(url: str) -> str:
    return url.rstrip("/")


def _http_json(
    server: str,
    token: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    endpoint = f"{_norm_server(server)}{path}"
    body = None
    headers = {
        "Accept": "application/json",
        "X-Access-Token": token,
    }
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = Request(endpoint, data=body, method=method, headers=headers)
    try:
        with urlopen(request, timeout=HTTP_REQUEST_TIMEOUT_SEC) as response:
            raw = response.read().decode("utf-8")
            if not raw:
                return {"ok": True}
            return json.loads(raw)
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
        raise RuntimeError(f"HTTP {exc.code}: {raw or exc.reason}") from exc
    except (URLError, TimeoutError, socket.timeout, HTTPException, ConnectionError, OSError) as exc:
        reason = getattr(exc, "reason", None) or str(exc) or exc.__class__.__name__
        raise RuntimeError(f"Network error: {reason}") from exc


def _http_json_retry(
    server: str,
    token: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    retries: int = 3,
) -> dict[str, Any]:
    last_error: RuntimeError | None = None
    for attempt in range(retries):
        try:
            return _http_json(server, token, method, path, payload)
        except RuntimeError as exc:
            last_error = exc
            if attempt >= retries - 1:
                break
            time.sleep(0.3 * (attempt + 1))
    raise last_error or RuntimeError("HTTP request failed")


def _compact(value: str) -> str:
    value = html_lib.unescape(value)
    value = re.sub(r"<[^>]+>", " ", value)
    return " ".join(value.split()).strip()


def _parse_iso_datetime(value: str) -> dt.datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def _format_command_error(error: Any) -> str:
    if isinstance(error, dict):
        for key in ("message", "error", "detail", "reason"):
            value = str(error.get(key) or "").strip()
            if value:
                return value
        try:
            return json.dumps(error, ensure_ascii=False)
        except Exception:  # noqa: BLE001
            return str(error)
    if error is None:
        return ""
    return str(error).strip()


def _fresh_clients(clients: list[dict[str, Any]], max_age_sec: int) -> tuple[list[dict[str, Any]], str]:
    now = dt.datetime.now(dt.timezone.utc)
    max_age = max(5, int(max_age_sec))
    fresh: list[dict[str, Any]] = []
    newest_seen_text = ""
    newest_seen_dt: dt.datetime | None = None

    for client in clients:
        if not isinstance(client, dict):
            continue
        seen_raw = str(client.get("last_seen") or "").strip()
        seen_dt = _parse_iso_datetime(seen_raw)
        if seen_dt is None:
            fresh.append(client)
            continue
        if seen_dt and (newest_seen_dt is None or seen_dt > newest_seen_dt):
            newest_seen_dt = seen_dt
            newest_seen_text = seen_raw
        age_sec = (now - seen_dt).total_seconds()
        if age_sec <= max_age:
            fresh.append(client)

    return fresh, newest_seen_text


def _load_clients(server: str, token: str) -> list[dict[str, Any]]:
    clients_response = _http_json_retry(server, token, "GET", "/api/clients")
    clients_all = clients_response.get("clients") or []
    if not isinstance(clients_all, list):
        raise RuntimeError("Invalid clients payload from hub")
    return clients_all


def _wait_for_fresh_clients(
    server: str,
    token: str,
    *,
    max_age_sec: int = ACTIVE_CLIENT_MAX_AGE_SEC,
    wait_sec: int = ACTIVE_CLIENT_WAIT_SEC,
) -> tuple[list[dict[str, Any]], str]:
    started_at = time.time()
    newest_seen = ""
    while True:
        clients_all = _load_clients(server, token)
        clients, newest_seen = _fresh_clients(clients_all, max_age_sec)
        if clients:
            return clients, newest_seen
        if time.time() - started_at >= max(0, int(wait_sec)):
            return [], newest_seen
        time.sleep(0.5)


def _is_specific_tg_dialog_url(value: str) -> bool:
    return bool(SPECIFIC_TG_DIALOG_URL_RE.match((value or "").strip()))


def _alternate_tg_dialog_url(url: str) -> str | None:
    value = (url or "").strip()
    if "/k/#" in value:
        return value.replace("/k/#", "/a/#", 1)
    if "/a/#" in value:
        return value.replace("/a/#", "/k/#", 1)
    return None


def _tg_web_mode_from_url(url: str) -> str:
    value = (url or "").strip().lower()
    return "a" if "/a/#" in value else "k"


def _dialog_fragment_from_url(url: str) -> str:
    value = (url or "").strip()
    if "#" not in value:
        return ""
    return value.split("#", 1)[1].strip()


def _get_tab_url(server: str, token: str, client_id: str, tab_id: int) -> str:
    clients_response = _http_json_retry(server, token, "GET", "/api/clients")
    clients = clients_response.get("clients") or []
    if isinstance(clients, list):
        for client in clients:
            if str(client.get("client_id") or "").strip() != client_id:
                continue
            tabs = client.get("tabs") or []
            if not isinstance(tabs, list):
                break
            for tab in tabs:
                if tab.get("id") == tab_id:
                    return str(tab.get("url") or "").strip()
            break
    return ""


def _detect_current_dialog_url(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    timeout_sec: int,
) -> str:
    url = _get_tab_url(server, token, client_id, tab_id)
    return url if _is_specific_tg_dialog_url(url) else ""


def _ensure_group_dialog_url(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    group_url: str,
    timeout_sec: int,
) -> bool:
    if not _is_specific_tg_dialog_url(group_url):
        return True

    current_url = _get_tab_url(server, token, client_id, tab_id)
    target_fragment = group_url.split("#", 1)[1] if "#" in group_url else ""
    current_fragment = current_url.split("#", 1)[1] if "#" in current_url else ""
    if current_url and current_fragment and (not target_fragment or target_fragment in current_fragment):
        return True

    nav_result = _send_command_result(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        timeout_sec=min(timeout_sec, 15),
        command={"type": "navigate", "url": group_url},
        raise_on_fail=False,
    )
    if not nav_result.get("ok"):
        alt = _alternate_tg_dialog_url(group_url)
        if alt:
            nav_result = _send_command_result(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=tab_id,
                timeout_sec=min(timeout_sec, 15),
                command={"type": "navigate", "url": alt},
                raise_on_fail=False,
            )
    if not nav_result.get("ok"):
        return False

    _send_command_result(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        timeout_sec=min(timeout_sec, 10),
        command={
            "type": "wait_selector",
            "selector": "body",
            "timeout_ms": 9000,
            "visible_only": False,
        },
        raise_on_fail=False,
    )
    time.sleep(0.8)
    fixed_url = _get_tab_url(server, token, client_id, tab_id)
    fixed_fragment = fixed_url.split("#", 1)[1] if "#" in fixed_url else ""
    return bool(fixed_url and fixed_fragment and (not target_fragment or target_fragment in fixed_fragment))


def _normalize_username(value: str) -> str:
    text = _compact(value)
    if not text:
        return "—"

    patterns = (
        r"https?://t\.me/([A-Za-z0-9_]{5,32})",
        r"t\.me/([A-Za-z0-9_]{5,32})",
        r"@([A-Za-z0-9_]{5,32})",
        r"\b([A-Za-z0-9_]{5,32})\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            username = match.group(1)
            if USERNAME_VALUE_RE.fullmatch(username):
                return f"@{username}"
    return "—"


def _parse_wmctrl_windows(output: str) -> list[dict[str, Any]]:
    windows: list[dict[str, Any]] = []
    for raw_line in str(output or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(None, 7)
        if len(parts) < 8:
            continue
        window_id, desktop, x, y, width, height, host, title = parts
        try:
            windows.append(
                {
                    "window_id": window_id,
                    "desktop": int(desktop),
                    "x": int(x),
                    "y": int(y),
                    "width": int(width),
                    "height": int(height),
                    "host": host,
                    "title": title,
                }
            )
        except ValueError:
            continue
    return windows


def _pick_telegram_x11_window(windows: list[dict[str, Any]]) -> dict[str, Any] | None:
    preferred: dict[str, Any] | None = None
    fallback: dict[str, Any] | None = None
    for item in windows:
        title = str(item.get("title") or "").strip()
        if not title or "telegram web" not in title.lower():
            continue
        if "chrome" in title.lower():
            preferred = item
            break
        fallback = fallback or item
    return preferred or fallback


def _get_active_x11_window_id() -> str:
    try:
        proc = subprocess.run(
            ["xprop", "-root", "_NET_ACTIVE_WINDOW"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return ""
    output = f"{proc.stdout}\n{proc.stderr}"
    match = re.search(r"window id # (0x[0-9a-fA-F]+)", output)
    return str(match.group(1) if match else "").strip()


def _x11_wheel_scroll_telegram() -> bool:
    if not X11_WHEEL_FALLBACK_ENABLED:
        return False
    if sys.platform != "linux" or not os.environ.get("DISPLAY"):
        return False

    try:
        proc = subprocess.run(
            ["wmctrl", "-lG"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return False
    windows = _parse_wmctrl_windows(proc.stdout)
    window = _pick_telegram_x11_window(windows)
    if window is None:
        return False

    try:
        from Xlib import X, display  # type: ignore
        from Xlib.ext import xtest  # type: ignore
    except Exception:
        return False

    try:
        current_active = _get_active_x11_window_id()
        d = display.Display()
        root = d.screen().root
        pointer = root.query_pointer()
        original_x = int(pointer.root_x)
        original_y = int(pointer.root_y)

        subprocess.run(["wmctrl", "-ia", str(window["window_id"])], check=False)
        time.sleep(0.18)

        target_x = int(window["x"]) + max(1, min(int(int(window["width"]) * X11_WHEEL_X_RATIO), int(window["width"]) - 2))
        target_y = int(window["y"]) + max(1, min(int(int(window["height"]) * X11_WHEEL_Y_RATIO), int(window["height"]) - 2))

        xtest.fake_input(d, X.MotionNotify, x=target_x, y=target_y)
        d.sync()
        time.sleep(0.08)

        for _ in range(X11_WHEEL_CLICKS):
            xtest.fake_input(d, X.ButtonPress, X11_WHEEL_BUTTON)
            xtest.fake_input(d, X.ButtonRelease, X11_WHEEL_BUTTON)
        d.sync()
        time.sleep(X11_WHEEL_SETTLE_SEC)

        xtest.fake_input(d, X.MotionNotify, x=original_x, y=original_y)
        d.sync()
        if current_active:
            subprocess.run(["wmctrl", "-ia", current_active], check=False)
        return True
    except Exception:
        return False


def _normalize_username_from_mention_input(value: str) -> str:
    text = _compact(value)
    if not text:
        return "—"

    for pattern in (
        r"@([A-Za-z0-9_]{5,32})",
        r"https?://t\.me/([A-Za-z0-9_]{5,32})",
        r"t\.me/([A-Za-z0-9_]{5,32})",
    ):
        match = re.search(pattern, text, flags=re.I)
        if not match:
            continue
        candidate = match.group(1)
        if USERNAME_VALUE_RE.fullmatch(candidate):
            return f"@{candidate}"
    return "—"


def _username_from_tg_url(url: str) -> str:
    text = (url or "").strip()
    if not text:
        return "—"
    match = re.search(r"/[ka]/#@([A-Za-z0-9_]{5,32})", text, flags=re.I)
    if not match:
        return "—"
    return _normalize_username(match.group(1))


def _poll_username_from_tab_url(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    timeout_sec: float = 2.0,
) -> tuple[str, str]:
    deadline = time.time() + max(timeout_sec, 0.2)
    last_url = _get_tab_url(server, token, client_id, tab_id)
    while True:
        username = _username_from_tg_url(last_url)
        if username != "—":
            return username, last_url
        if time.time() >= deadline:
            return "—", last_url
        time.sleep(0.2)
        last_url = _get_tab_url(server, token, client_id, tab_id)


def _poll_username_from_page_location(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    timeout_sec: float = 2.0,
) -> tuple[str, str]:
    deadline = time.time() + max(timeout_sec, 0.2)
    last_url = ""
    while True:
        result = _send_command_result(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=2,
            command={"type": "get_page_url"},
            raise_on_fail=False,
        )
        data = result.get("data") or {}
        value = data.get("url") if isinstance(data, dict) else ""
        last_url = str(value or "").strip()
        username = _username_from_tg_url(last_url)
        if username != "—":
            return username, last_url
        if time.time() >= deadline:
            return "—", last_url
        time.sleep(0.2)


def _read_username_from_composer(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
) -> str:
    selectors = (
        ".chat-input-main .input-message-input[contenteditable='true']:not(.input-field-input-fake)",
        ".chat-input .input-message-input[contenteditable='true']:not(.input-field-input-fake)",
        ".new-message-wrapper .input-message-input[contenteditable='true']:not(.input-field-input-fake)",
        "#editable-message-text",
        ".input-message-input[contenteditable='true']",
        ".input-message-input",
        ".composer_rich_textarea",
        ".new-message-wrapper [contenteditable='true']",
    )
    for selector in selectors:
        result = _send_command_result(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=2,
            command={"type": "extract_text", "selector": selector, "timeout_ms": 600},
            raise_on_fail=False,
        )
        data = result.get("data") or {}
        text = str(data.get("text") or "").strip() if isinstance(data, dict) else ""
        username = _normalize_username_from_mention_input(text)
        if username != "—":
            return username
    return "—"


def _clear_composer_text(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
) -> None:
    _send_command_result(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        timeout_sec=2,
        command={
            "type": "clear_editable",
            "selectors": [
                ".chat-input-main .input-message-input[contenteditable='true']:not(.input-field-input-fake)",
                ".chat-input .input-message-input[contenteditable='true']:not(.input-field-input-fake)",
                ".new-message-wrapper .input-message-input[contenteditable='true']:not(.input-field-input-fake)",
                "#editable-message-text",
                ".input-message-input[contenteditable='true']",
                ".input-message-input",
                ".composer_rich_textarea",
                ".new-message-wrapper [contenteditable='true']",
            ],
        },
        raise_on_fail=False,
    )


def _get_chat_anchor_peer_id(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
) -> str:
    # Telegram frequently exposes the currently anchored sender avatar as the
    # first visible group avatar while scrolling. Use that stable element when
    # message-local selectors are flaky.
    for selector in CHAT_ANCHOR_AVATAR_SELECTORS:
        result = _send_command_result(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=2,
            command={"type": "get_attribute", "selector": selector, "attribute": "data-peer-id"},
            raise_on_fail=False,
        )
        data = result.get("data") or {}
        peer_id = str(data.get("value") or "").strip() if isinstance(data, dict) else ""
        if peer_id.isdigit():
            return peer_id
    return ""


def _chat_peer_context_selectors(peer_id: str) -> tuple[str, ...]:
    return (
        f'.bubbles .bubbles-group-avatar.user-avatar[data-peer-id="{peer_id}"] .avatar-photo',
        f'.bubbles .bubbles-group-avatar.user-avatar[data-peer-id="{peer_id}"]',
        f'.peer-title.bubble-name-first[data-peer-id="{peer_id}"]',
        f'.bubbles .peer-title[data-peer-id="{peer_id}"]',
    )


def _open_chat_peer_context_menu(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    peer_id: str,
) -> tuple[bool, str]:
    tried_selectors: set[str] = set()
    anchor_peer_id = _get_chat_anchor_peer_id(server, token, client_id, tab_id)
    selector_groups: list[tuple[str, tuple[str, ...]]] = []
    if anchor_peer_id and anchor_peer_id == peer_id:
        selector_groups.append(("anchor", CHAT_ANCHOR_CONTEXT_SELECTORS))
    selector_groups.append(("peer", _chat_peer_context_selectors(peer_id)))

    for route, selectors in selector_groups:
        for selector in selectors:
            if selector in tried_selectors:
                continue
            tried_selectors.add(selector)
            opened = _send_command_result(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=tab_id,
                timeout_sec=2,
                command={"type": "context_click", "selector": selector, "timeout_ms": 900},
                raise_on_fail=False,
            )
            if opened.get("ok"):
                return True, route
    return False, ""


def _try_username_via_mention_action(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    peer_id: str,
) -> str:
    # Prevent stale @username from previous attempts.
    _clear_composer_text(server, token, client_id, tab_id)

    clicked_context, context_route = _open_chat_peer_context_menu(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        peer_id=peer_id,
    )
    if not clicked_context:
        print(f"WARN: mention context menu not opened for peer {peer_id}")
        return "—"
    if context_route == "anchor":
        print(f"INFO: mention context for peer {peer_id} opened via anchor avatar")

    _send_command_result(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        timeout_sec=2,
        command={
            "type": "wait_selector",
            "selector": "#bubble-contextmenu.active, .btn-menu.contextmenu.active, #bubble-contextmenu, .btn-menu.contextmenu",
            "timeout_ms": 1200,
            "visible_only": False,
        },
        raise_on_fail=False,
    )

    mention_click_ok = False
    mention_terms = [
        "mention",
        "упомянуть",
        "mencionar",
        "erwähnen",
        "menziona",
        "menção",
        "mencao",
    ]
    if not mention_click_ok:
        for _ in range(3):
            for root_selector in (
                "#bubble-contextmenu.active",
                "#bubble-contextmenu",
                ".btn-menu.contextmenu.active",
                ".btn-menu.contextmenu",
            ):
                mention_click = _send_command_result(
                    server=server,
                    token=token,
                    client_id=client_id,
                    tab_id=tab_id,
                    timeout_sec=2,
                    command={
                        "type": "click_text",
                        "root_selector": root_selector,
                        "terms": mention_terms,
                        "near_last_context": True,
                    },
                    raise_on_fail=False,
                )
                if mention_click.get("ok"):
                    mention_click_ok = True
                    break
            if mention_click_ok:
                break
            time.sleep(0.12)
    if not mention_click_ok:
        print(f"WARN: mention item not clicked for peer {peer_id}")
        return "—"

    deadline = time.time() + 1.8
    while time.time() < deadline:
        username = _read_username_from_composer(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
        )
        if username != "—":
            _clear_composer_text(server, token, client_id, tab_id)
            return username
        time.sleep(0.15)

    _clear_composer_text(server, token, client_id, tab_id)
    print(f"WARN: mention clicked but username not read from composer for peer {peer_id}")
    return "—"


def _open_peer_dialog_from_group_chat(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    peer_id: str,
    timeout_sec: int,
) -> bool:
    for selector in (
        f'.bubbles .bubbles-group-avatar.user-avatar[data-peer-id="{peer_id}"] .avatar-photo',
        f'.colored-name.name.floating-part[data-peer-id="{peer_id}"]',
        f'.bubbles .bubbles-group-avatar.user-avatar[data-peer-id="{peer_id}"]',
        f'.peer-title.bubble-name-first[data-peer-id="{peer_id}"]',
        f'.bubbles .peer-title[data-peer-id="{peer_id}"]',
    ):
        result = _send_command_result(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=max(2, timeout_sec),
            command={"type": "click", "selector": selector, "timeout_ms": 1200},
            raise_on_fail=False,
        )
        if result.get("ok"):
            return True
    return False


def _open_current_chat_user_info_and_read_username(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    timeout_sec: int,
) -> str:
    clicked_any = False
    for selector in (
        ".chat-info",
        ".chat-info .person",
        ".chat-info .person-avatar",
        ".chat-info-container .chat-info",
        "#column-center .chat-info",
        ".sidebar-header .chat-info",
    ):
        click_result = _send_command_result(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=min(max(timeout_sec, 2), 6),
            command={
                "type": "click",
                "selector": selector,
                "timeout_ms": 2200,
            },
            raise_on_fail=False,
        )
        if click_result.get("ok"):
            clicked_any = True
            break
    if not clicked_any:
        return "—"

    _send_command_result(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        timeout_sec=min(max(timeout_sec, 2), 7),
        command={
            "type": "wait_selector",
            "selector": "#column-right .profile-content",
            "timeout_ms": 4500,
            "visible_only": False,
        },
        raise_on_fail=False,
    )

    username = "—"
    try:
        profile_html = _send_get_html(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=min(max(timeout_sec, 2), 7),
            selector="#column-right",
        )
        username = _extract_username_from_profile_html(profile_html)
    finally:
        _close_profile_card(server, token, client_id, tab_id)
        time.sleep(0.08)

    return username


def _return_to_group_dialog_reliable(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    group_url: str,
    timeout_sec: int,
    allow_navigate_fallback: bool = True,
) -> bool:
    if _is_specific_tg_dialog_url(group_url):
        target_fragment = group_url.split("#", 1)[1] if "#" in group_url else ""
        current_url = _get_tab_url(server, token, client_id, tab_id)
        current_fragment = current_url.split("#", 1)[1] if "#" in current_url else ""
        if target_fragment and current_fragment and target_fragment in current_fragment:
            _close_profile_card(server, token, client_id, tab_id)
            return True

    if _return_to_group_dialog_fast(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        group_url=group_url,
        timeout_sec=min(max(timeout_sec, 2), 5),
    ):
        return True
    if not allow_navigate_fallback:
        return False
    return _ensure_group_dialog_url(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        group_url=group_url,
        timeout_sec=min(max(timeout_sec, 2), 8),
    )


def _url_matches_expected_dialog(expected_url: str, current_url: str) -> bool:
    expected = str(expected_url or "").strip()
    current = str(current_url or "").strip()
    if not expected:
        return True
    if current == expected:
        return True
    if _is_specific_tg_dialog_url(expected):
        expected_fragment = expected.split("#", 1)[1] if "#" in expected else ""
        current_fragment = current.split("#", 1)[1] if "#" in current else ""
        return bool(expected_fragment and current_fragment and expected_fragment == current_fragment)
    return False


def _restore_tab_url_from_history(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    expected_url: str,
    timeout_sec: int,
    attempts: int = 3,
) -> bool:
    if not expected_url:
        return True
    current_url = _get_tab_url(server, token, client_id, tab_id)
    if _url_matches_expected_dialog(expected_url, current_url):
        return True

    for _ in range(max(attempts, 1)):
        _close_profile_card(server, token, client_id, tab_id)
        _send_command_result(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=min(max(timeout_sec, 2), 4),
            command={"type": "back"},
            raise_on_fail=False,
        )
        deadline = time.time() + min(max(timeout_sec, 2), 4)
        while time.time() < deadline:
            current_url = _get_tab_url(server, token, client_id, tab_id)
            if _url_matches_expected_dialog(expected_url, current_url):
                return True
            time.sleep(0.15)
    return False


def _get_current_opened_peer_id(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    timeout_sec: int,
) -> str:
    for selector in (
        ".chat-info .peer-title[data-peer-id]",
        ".sidebar-header .peer-title[data-peer-id]",
        "#column-right .profile-name .peer-title[data-peer-id]",
    ):
        result = _send_command_result(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=max(3, timeout_sec),
            command={"type": "get_attribute", "selector": selector, "attribute": "data-peer-id", "timeout_ms": 1200},
            raise_on_fail=False,
        )
        data = result.get("data") or {}
        value = data.get("value") if isinstance(data, dict) else ""
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _get_current_opened_title(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    timeout_sec: int,
) -> str:
    for selector in (
        ".chat-info .peer-title",
        ".sidebar-header .peer-title",
        "#column-right .profile-name .peer-title",
    ):
        result = _send_command_result(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=max(3, timeout_sec),
            command={"type": "extract_text", "selector": selector, "timeout_ms": 1200},
            raise_on_fail=False,
        )
        data = result.get("data") or {}
        value = data.get("text") if isinstance(data, dict) else ""
        text = _compact(str(value or ""))
        if text:
            return text
    return ""


def _name_key(value: str) -> str:
    text = _compact(value).lower()
    text = re.sub(r"[^a-zа-я0-9]+", "", text, flags=re.I)
    return text


def _name_match(expected: str, actual: str) -> bool:
    a = _name_key(expected)
    b = _name_key(actual)
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) >= 4 and a in b:
        return True
    if len(b) >= 4 and b in a:
        return True
    return False


def _extract_chat_mention_usernames(html_payload: str) -> list[str]:
    found: set[str] = set()
    for pattern in (
        r"https?://t\.me/([A-Za-z0-9_]{5,32})",
        r'href="[^"]*#@([A-Za-z0-9_]{5,32})"',
        r'class="mention"[^>]*>@([A-Za-z0-9_]{5,32})<',
        r'@([A-Za-z0-9_]{5,32})',
    ):
        for value in re.findall(pattern, html_payload, flags=re.I):
            username = _normalize_username(value)
            if username != "—":
                found.add(username.lstrip("@"))
    return sorted(found)


def _extract_username(row_html: str) -> str:
    # Prefer explicit username from links, then fallback to visible text in the row.
    patterns = (
        r'href="[^"]*#@([A-Za-z0-9_]{5,32})"',
        r'href="[^"]*/@([A-Za-z0-9_]{5,32})"',
        r'href="[^"]*[?&]domain=([A-Za-z0-9_]{5,32})"',
        r'@([A-Za-z0-9_]{5,32})',
    )
    for pattern in patterns:
        match = re.search(pattern, row_html, flags=re.I)
        if match:
            username = _normalize_username(match.group(1))
            if username != "—":
                return username
    return "—"


def _extract_username_from_profile_html(profile_html: str) -> str:
    rows = re.findall(
        r'<div dir="auto" class="row-title(?: pre-wrap)?">(.*?)</div>\s*'
        r'<div dir="auto" class="row-subtitle">(.*?)</div>',
        profile_html,
        flags=re.S,
    )
    for title_html, subtitle_html in rows:
        subtitle = _compact(subtitle_html).lower()
        if any(marker in subtitle for marker in USERNAME_SUBTITLE_MARKERS):
            username = _normalize_username(title_html)
            if username != "—":
                return username

    for pattern in (
        r"https?://t\.me/([A-Za-z0-9_]{5,32})",
        r"t\.me/([A-Za-z0-9_]{5,32})",
    ):
        match = re.search(pattern, profile_html, flags=re.I)
        if match:
            username = _normalize_username(match.group(1))
            if username != "—":
                return username

    return "—"


def _extract_total_members_hint(html_payload: str) -> int | None:
    patterns = (
        r'([0-9][0-9\s.,]*)\s+members',
        r'([0-9][0-9\s.,]*)\s+участ',
    )
    for pattern in patterns:
        matches = re.findall(pattern, html_payload, flags=re.I)
        for raw in matches:
            cleaned = re.sub(r"[^\d]", "", raw)
            if not cleaned:
                continue
            value = int(cleaned)
            if value > 0:
                return value
    return None


def _should_run_chat_deep_step(
    *,
    step: int,
    members_count: int,
    min_members_target: int,
    mode: str,
    chat_target_peer_id: str,
    chat_target_name: str,
    known_view_signature: bool = False,
) -> bool:
    if chat_target_peer_id or chat_target_name:
        return True

    target = max(int(min_members_target), 0)
    if target <= 0 or members_count >= target:
        return True
    if known_view_signature:
        return False

    normalized_mode = str(mode or "").strip().lower()
    if normalized_mode in ("url", "full"):
        return False

    return step == 0 or step % CHAT_DISCOVERY_MENTION_DEEP_INTERVAL == 0


def _extract_chat_view_signature(html_payload: str) -> str:
    if not html_payload:
        return ""

    top_mids = re.findall(r'data-mid="([^"]+)"', html_payload, flags=re.I)[:3]
    top_timestamps = re.findall(r'data-timestamp="([^"]+)"', html_payload, flags=re.I)[:3]
    top_peers = re.findall(
        r'class="(?=[^"]*bubbles-group-avatar)(?=[^"]*user-avatar)[^"]*"[^>]*data-peer-id="([^"]+)"',
        html_payload,
        flags=re.I,
    )[:3]
    parts = []
    if top_mids:
        parts.append("mid=" + ",".join(top_mids))
    if top_peers:
        parts.append("peer=" + ",".join(top_peers))
    if top_timestamps:
        parts.append("ts=" + ",".join(top_timestamps))
    return "|".join(parts)


def _dedupe_members(members: list[dict[str, str]]) -> list[dict[str, str]]:
    merged: dict[str, dict[str, str]] = {}
    order: list[str] = []
    for item in members:
        peer_id = str(item.get("peer_id", "")).strip()
        username = str(item.get("username", "—")).strip()
        name = str(item.get("name", "")).strip()
        dedupe_key = peer_id or f"{username.lower()}::{name.lower()}"
        if dedupe_key not in merged:
            merged[dedupe_key] = {
                "peer_id": peer_id or "—",
                "name": name or "—",
                "username": username or "—",
                "status": str(item.get("status", "—")) or "—",
                "role": str(item.get("role", "—")) or "—",
            }
            order.append(dedupe_key)
            continue

        current = merged[dedupe_key]
        if current.get("name") in ("", "—") and name and name != "—":
            current["name"] = name
        if current.get("username") == "—" and username and username != "—":
            current["username"] = username
        if current.get("role") == "—" and item.get("role") and item.get("role") != "—":
            current["role"] = str(item["role"])
        if current.get("status") == "—" and item.get("status") and item.get("status") != "—":
            current["status"] = str(item["status"])

    return [merged[key] for key in order]


def _extract_chat_name_from_block(block_html: str, peer_id: str) -> str:
    peer_id_re = re.escape(peer_id)
    patterns = (
        rf'<(?:div|span)[^>]*class="(?=[^"]*colored-name)(?=[^"]*floating-part)[^"]*"[^>]*data-peer-id="{peer_id_re}"[^>]*>(.*?)</(?:div|span)>',
        rf'<span[^>]*class="(?=[^"]*peer-title)(?=[^"]*bubble-name-first)[^"]*"[^>]*data-peer-id="{peer_id_re}"[^>]*>(.*?)</span>',
        rf'<span[^>]*class="(?=[^"]*peer-title)[^"]*"[^>]*data-peer-id="{peer_id_re}"[^>]*>(.*?)</span>',
    )
    for pattern in patterns:
        match = re.search(pattern, block_html, flags=re.S)
        if not match:
            continue
        raw = match.group(1)
        inner = re.search(r'<span class="peer-title-inner"[^>]*>(.*?)</span>', raw, flags=re.S)
        if inner:
            name = _compact(inner.group(1))
            if name:
                return name
        cleaned = re.sub(r'<span class="bubble-name-rank"[^>]*>.*?</span>', " ", raw, flags=re.S)
        cleaned = re.sub(r'<span class="bubble-name-boosts"[^>]*>.*?</span>', " ", cleaned, flags=re.S)
        cleaned = re.sub(r'<[^>]+>', " ", cleaned)
        name = _compact(cleaned)
        if name:
            return name
    return ""


def _parse_chat_members(html_payload: str) -> list[dict[str, str]]:
    # Telegram Web markup for sender labels varies between releases.
    sender_openings: list[tuple[int, int, str, str]] = []
    sender_patterns = (
        r'<(?:div|span)([^>]*)class="(?=[^"]*colored-name)(?=[^"]*floating-part)[^"]*"([^>]*)>',
        r'<span([^>]*)class="(?=[^"]*peer-title)(?=[^"]*bubble-name-first)[^"]*"([^>]*)>',
    )
    for pattern in sender_patterns:
        for match in re.finditer(pattern, html_payload, flags=re.S):
            attrs = f"{match.group(1)} {match.group(2)}"
            sender_openings.append((match.start(), 0, attrs, ""))
    avatar_pattern = r'<div([^>]*)class="(?=[^"]*bubbles-group-avatar)(?=[^"]*user-avatar)[^"]*"([^>]*)>(.*?)</div>'
    for match in re.finditer(avatar_pattern, html_payload, flags=re.S):
        attrs = f"{match.group(1)} {match.group(2)}"
        sender_openings.append((match.start(), 1, attrs, match.group(3)))
    sender_openings.sort(key=lambda item: (item[0], item[1]))

    members: list[dict[str, str]] = []

    for start_pos, _priority, attrs, avatar_inner in sender_openings:
        peer_match = re.search(r'data-peer-id="([^"]+)"', attrs)
        if not peer_match:
            continue
        peer_id = peer_match.group(1)
        if peer_id.startswith("-"):
            continue

        block_html = html_payload[start_pos : start_pos + 2400]
        name = _extract_chat_name_from_block(block_html, peer_id)
        if not name and avatar_inner:
            initials = _compact(re.sub(r"<[^>]+>", " ", avatar_inner))
            if initials:
                name = initials

        role = "—"
        role_match = re.search(r'<span class="bubble-name-rank"[^>]*>(.*?)</span>', block_html, flags=re.S)
        if role_match:
            parsed_role = _compact(role_match.group(1))
            if parsed_role:
                role = parsed_role

        members.append(
            {
                "peer_id": peer_id,
                "name": name or "—",
                "status": "из чата",
                "role": role,
                "username": _extract_username(block_html),
            }
        )
    return _dedupe_members(members)


def _scroll_chat_up(server: str, token: str, client_id: str, tab_id: int, timeout_sec: int) -> bool:
    for selector in (
        ".bubbles .scrollable.scrollable-y",
        ".chat.tabs-tab.active .bubbles .scrollable-y",
        "#column-center .bubbles .scrollable-y",
        "#column-center .scrollable-y",
    ):
        result = _send_command_result(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=timeout_sec,
            command={
                "type": "scroll_by",
                "selector": selector,
                "delta_y": -CHAT_SCROLL_DISTANCE_PX,
                "delta_x": 0,
            },
            raise_on_fail=False,
        )
        if not result.get("ok"):
            continue
        data = result.get("data") or {}
        before_top = data.get("beforeTop")
        after_top = data.get("afterTop")
        moved = data.get("moved")
        if isinstance(moved, bool):
            if moved:
                return True
        elif isinstance(before_top, (int, float)) and isinstance(after_top, (int, float)):
            if abs(float(after_top) - float(before_top)) >= 1:
                return True
        else:
            # Older extension builds don't report before/after; treat as success.
            return True

        print(
            "INFO: chat scroll no immediate movement "
            f"(selector={selector}, top={before_top}->{after_top}, "
            f"height={data.get('scrollHeight')}, client={data.get('clientHeight')})"
        )

        wheel_result = _send_command_result(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=timeout_sec,
            command={
                "type": "wheel",
                "selector": selector,
                "delta_y": -CHAT_SCROLL_DISTANCE_PX,
                "delta_x": 0,
            },
            raise_on_fail=False,
        )
        if wheel_result.get("ok"):
            wheel_data = wheel_result.get("data") or {}
            wheel_moved = wheel_data.get("moved")
            if isinstance(wheel_moved, bool) and wheel_moved:
                print(f"INFO: chat wheel moved container for selector={selector}")
                return True

            print(f"INFO: chat wheel dispatched for selector={selector}")
            time.sleep(0.22)

            probe = _send_command_result(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=tab_id,
                timeout_sec=timeout_sec,
                command={
                    "type": "scroll_by",
                    "selector": selector,
                    "delta_y": 0,
                    "delta_x": 0,
                },
                raise_on_fail=False,
            )
            if probe.get("ok"):
                probe_data = probe.get("data") or {}
                probe_top = probe_data.get("beforeTop")
                probe_height = probe_data.get("scrollHeight")
                if isinstance(before_top, (int, float)) and isinstance(probe_top, (int, float)):
                    if abs(float(probe_top) - float(before_top)) >= 1:
                        print(
                            "INFO: chat wheel changed container position "
                            f"(selector={selector}, top={before_top}->{probe_top})"
                        )
                        return True
                if isinstance(data.get("scrollHeight"), (int, float)) and isinstance(probe_height, (int, float)):
                    if abs(float(probe_height) - float(data.get("scrollHeight"))) >= 1:
                        print(
                            "INFO: chat wheel changed scroll height "
                            f"(selector={selector}, height={data.get('scrollHeight')}->{probe_height})"
                        )
                        return True

        x11_before_height = data.get("scrollHeight")
        if _x11_wheel_scroll_telegram():
            probe = _send_command_result(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=tab_id,
                timeout_sec=timeout_sec,
                command={
                    "type": "scroll_by",
                    "selector": selector,
                    "delta_y": 0,
                    "delta_x": 0,
                },
                raise_on_fail=False,
            )
            if probe.get("ok"):
                probe_data = probe.get("data") or {}
                probe_top = probe_data.get("beforeTop")
                probe_height = probe_data.get("scrollHeight")
                if isinstance(before_top, (int, float)) and isinstance(probe_top, (int, float)):
                    if abs(float(probe_top) - float(before_top)) >= 1:
                        print(
                            "INFO: chat X11 wheel moved container "
                            f"(selector={selector}, top={before_top}->{probe_top})"
                        )
                        return True
                if isinstance(x11_before_height, (int, float)) and isinstance(probe_height, (int, float)):
                    if abs(float(probe_height) - float(x11_before_height)) >= 1:
                        print(
                            "INFO: chat X11 wheel changed scroll height "
                            f"(selector={selector}, height={x11_before_height}->{probe_height})"
                        )
                        return True

        for anchor_selector in CHAT_SCROLL_SELECTORS:
            fallback = _send_command_result(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=tab_id,
                timeout_sec=timeout_sec,
                command={
                    "type": "scroll",
                    "selector": anchor_selector,
                    "timeout_ms": 1800,
                },
                raise_on_fail=False,
            )
            if not fallback.get("ok"):
                continue

            probe = _send_command_result(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=tab_id,
                timeout_sec=timeout_sec,
                command={
                    "type": "scroll_by",
                    "selector": selector,
                    "delta_y": 0,
                    "delta_x": 0,
                },
                raise_on_fail=False,
            )
            if not probe.get("ok"):
                continue
            probe_data = probe.get("data") or {}
            probe_top = probe_data.get("beforeTop")
            if isinstance(before_top, (int, float)) and isinstance(probe_top, (int, float)):
                if abs(float(probe_top) - float(before_top)) >= 1:
                    print(
                        "INFO: chat scroll fallback moved container "
                        f"(anchor={anchor_selector}, top={before_top}->{probe_top})"
                    )
                    return True
        return False

    return False


def _scroll_info_members_down(server: str, token: str, client_id: str, tab_id: int, timeout_sec: int) -> bool:
    # Scroll the members list by moving to the last currently visible member row.
    for selector in (
        '#column-right a.chatlist-chat.chatlist-chat-abitbigger[data-dialog="0"]:last-of-type',
        '#column-right a.chatlist-chat-abitbigger[data-dialog="0"]:last-of-type',
        'a.chatlist-chat.chatlist-chat-abitbigger[data-dialog="0"]:last-of-type',
        'a.chatlist-chat-abitbigger[data-dialog="0"]:last-of-type',
    ):
        result = _send_command_result(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=timeout_sec,
            command={
                "type": "scroll",
                "selector": selector,
                "timeout_ms": 4000,
            },
            raise_on_fail=False,
        )
        if result.get("ok"):
            return True

    return False


def _collect_members_from_info(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    timeout_sec: int,
    scroll_steps: int,
    deep_usernames: bool = False,
    max_members: int = 0,
    historical_username_to_peer: dict[str, str] | None = None,
    historical_peer_to_username: dict[str, str] | None = None,
    on_progress: Callable[[list[dict[str, str]], str], None] | None = None,
) -> tuple[list[dict[str, str]], dict[str, int]]:
    members: list[dict[str, str]] = []
    max_members_effective = max(int(max_members), 0)
    scroll_steps_done = 0
    no_growth_steps = 0
    total_hint: int | None = None
    deep_seen_peer_ids: set[str] = set()
    deep_attempted_total = 0
    deep_updated_total = 0

    for step in range(max(0, scroll_steps) + 1):
        html_payload = _send_get_html(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=max(timeout_sec, 5),
            selector="#column-right",
        )

        step_members = _parse_members(html_payload)
        before_count = len(members)
        if step_members:
            members.extend(step_members)
            members = _dedupe_members(members)
        added = len(members) - before_count

        hint = _extract_total_members_hint(html_payload)
        if hint:
            total_hint = max(total_hint or 0, hint)

        if deep_usernames and step_members and members:
            visible_peer_ids = {item["peer_id"] for item in step_members if item.get("peer_id")}
            deep_targets = [
                item
                for item in members
                if item.get("peer_id") in visible_peer_ids
                and item.get("username") == "—"
                and item.get("peer_id") not in deep_seen_peer_ids
            ]
            if deep_targets:
                attempted, updated, opened_peer_ids = _enrich_usernames_deep(
                    server=server,
                    token=token,
                    client_id=client_id,
                    tab_id=tab_id,
                    timeout_sec=max(timeout_sec, 5),
                    members=deep_targets,
                    all_members=members,
                    historical_username_to_peer=historical_username_to_peer,
                    historical_peer_to_username=historical_peer_to_username,
                )
                deep_attempted_total += attempted
                deep_updated_total += updated
                for peer_id in opened_peer_ids:
                    deep_seen_peer_ids.add(peer_id)
                print(
                    f"INFO: info deep step {step}: processed {attempted}, "
                    f"filled {updated}, total_filled {deep_updated_total}"
                )

        if max_members_effective and len(members) > max_members_effective:
            members = members[:max_members_effective]

        hint_text = str(total_hint) if total_hint else "unknown"
        print(f"INFO: info step {step} collected {len(members)} unique users (hint {hint_text})")
        if on_progress is not None:
            on_progress(members, f"info step {step}")

        if max_members_effective and len(members) >= max_members_effective:
            print(f"INFO: info max-members reached ({max_members_effective}), stopping")
            break
        if step >= scroll_steps:
            break
        if total_hint and len(members) >= total_hint:
            break
        if added <= 0:
            no_growth_steps += 1
        else:
            no_growth_steps = 0
        if no_growth_steps >= 3:
            break
        if not _scroll_info_members_down(server, token, client_id, tab_id, timeout_sec=min(timeout_sec, 10)):
            break
        scroll_steps_done += 1
        time.sleep(INFO_SCROLL_SETTLE_SEC)

    stats = {
        "unique_members": len(members),
        "scroll_steps_done": scroll_steps_done,
        "total_hint": int(total_hint or 0),
        "deep_attempted": deep_attempted_total,
        "deep_updated": deep_updated_total,
    }
    return members, stats


def _seed_username_to_peer(members: list[dict[str, str]]) -> dict[str, str]:
    username_to_peer: dict[str, str] = {}
    for item in members:
        username = str(item.get("username") or "").strip()
        peer_id = str(item.get("peer_id") or "").strip()
        if not username or username == "—" or not peer_id:
            continue
        username_to_peer.setdefault(username.lower(), peer_id)
    return username_to_peer


def _load_identity_history(history_path: Path | None) -> tuple[dict[str, str], dict[str, str]]:
    if history_path is None or not history_path.exists():
        return {}, {}
    try:
        payload = json.loads(history_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}, {}
    if not isinstance(payload, dict):
        return {}, {}
    username_to_peer_raw = payload.get("username_to_peer")
    peer_to_username_raw = payload.get("peer_to_username")
    username_to_peer = {
        str(key).strip().lower(): str(value).strip()
        for key, value in (username_to_peer_raw.items() if isinstance(username_to_peer_raw, dict) else [])
        if str(key).strip() and str(value).strip()
    }
    peer_to_username = {
        str(key).strip(): _normalize_username(str(value))
        for key, value in (peer_to_username_raw.items() if isinstance(peer_to_username_raw, dict) else [])
        if str(key).strip() and _normalize_username(str(value)) != "—"
    }
    return username_to_peer, peer_to_username


def _load_discovery_state(discovery_state_path: Path | None) -> dict[str, Any]:
    if discovery_state_path is None or not discovery_state_path.exists():
        return {
            "version": 1,
            "updated_at": "",
            "seen_view_signatures": [],
            "seen_peer_ids": [],
        }
    try:
        payload = json.loads(discovery_state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "version": 1,
            "updated_at": "",
            "seen_view_signatures": [],
            "seen_peer_ids": [],
        }
    if not isinstance(payload, dict):
        payload = {}
    seen_view_signatures_raw = payload.get("seen_view_signatures")
    seen_peer_ids_raw = payload.get("seen_peer_ids")
    seen_view_signatures = []
    if isinstance(seen_view_signatures_raw, list):
        seen_view_signatures = [str(value).strip() for value in seen_view_signatures_raw if str(value).strip()]
    seen_peer_ids = []
    if isinstance(seen_peer_ids_raw, list):
        seen_peer_ids = [str(value).strip() for value in seen_peer_ids_raw if str(value).strip()]
    return {
        "version": 1,
        "updated_at": str(payload.get("updated_at") or ""),
        "seen_view_signatures": seen_view_signatures[-DISCOVERY_STATE_MAX_SIGNATURES:],
        "seen_peer_ids": seen_peer_ids[-DISCOVERY_STATE_MAX_PEERS:],
    }


def _save_discovery_state(discovery_state_path: Path | None, discovery_state: dict[str, Any] | None) -> None:
    if discovery_state_path is None or discovery_state is None:
        return
    discovery_state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "updated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "seen_view_signatures": list((discovery_state.get("seen_view_signatures") or []))[-DISCOVERY_STATE_MAX_SIGNATURES:],
        "seen_peer_ids": list((discovery_state.get("seen_peer_ids") or []))[-DISCOVERY_STATE_MAX_PEERS:],
    }
    discovery_state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _log_username_assignment_conflict(username: str, peer_id: str, conflict_value: str | None, reason: str | None) -> None:
    if reason == "historical_username_owner":
        print(
            f"WARN: skip historical username-owner conflict {username} for peer {peer_id} "
            f"(known owner {conflict_value or 'unknown'})"
        )
        return
    if reason == "historical_peer_username":
        print(
            f"WARN: skip historical peer-username conflict {username} for peer {peer_id} "
            f"(known username {conflict_value or 'unknown'})"
        )
        return
    if reason == "runtime_duplicate" and conflict_value and conflict_value != peer_id:
        print(f"WARN: skip duplicate username {username} for peer {peer_id} (already {conflict_value})")
        return
    print(f"WARN: skip username {username} for peer {peer_id}")


def _assign_username_if_unique(
    *,
    members_by_peer: dict[str, dict[str, str]],
    username_to_peer: dict[str, str],
    peer_id: str,
    username: str,
    historical_username_to_peer: dict[str, str] | None = None,
    historical_peer_to_username: dict[str, str] | None = None,
) -> tuple[bool, str | None, str | None]:
    normalized = _normalize_username(username)
    if normalized == "—":
        return False, "", "empty"

    key = normalized.lower()
    historical_owner = str((historical_username_to_peer or {}).get(key) or "").strip()
    if historical_owner and historical_owner != peer_id:
        return False, historical_owner, "historical_username_owner"

    historical_username = _normalize_username(str((historical_peer_to_username or {}).get(peer_id) or ""))
    if historical_username != "—" and historical_username.lower() != key:
        return False, historical_username, "historical_peer_username"

    existing_peer = username_to_peer.get(key)
    if existing_peer and existing_peer != peer_id:
        return False, existing_peer, "runtime_duplicate"

    member = members_by_peer.get(peer_id)
    if member is None:
        return False, existing_peer, "missing_member"

    member["username"] = normalized
    username_to_peer[key] = peer_id
    return True, existing_peer, None


def _enrich_chat_usernames_via_info(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    timeout_sec: int,
    chat_members: list[dict[str, str]],
    info_scroll_steps: int,
) -> tuple[int, int]:
    if not chat_members:
        return 0, 0

    if not _open_info_members_view(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        timeout_sec=max(timeout_sec, 5),
    ):
        return 0, 0

    info_members, info_stats = _collect_members_from_info(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        timeout_sec=max(timeout_sec, 5),
        scroll_steps=max(info_scroll_steps, 0),
        deep_usernames=True,
    )
    info_usernames = {
        str(item.get("peer_id") or "").strip(): str(item.get("username") or "—").strip()
        for item in info_members
        if str(item.get("username") or "").strip() not in ("", "—")
    }

    updated = 0
    for item in chat_members:
        peer_id = str(item.get("peer_id") or "").strip()
        if not peer_id:
            continue
        if str(item.get("username") or "—").strip() != "—":
            continue
        username = info_usernames.get(peer_id)
        if username:
            item["username"] = username
            updated += 1

    attempted = int(info_stats.get("deep_attempted", 0))
    return attempted, updated


def _enrich_chat_usernames_via_mentions(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    timeout_sec: int,
    group_url: str,
    members: list[dict[str, str]],
    deep_limit: int,
    historical_username_to_peer: dict[str, str] | None = None,
    historical_peer_to_username: dict[str, str] | None = None,
) -> tuple[int, int]:
    if deep_limit <= 0 or not members:
        return 0, 0

    body_html = _send_get_html(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        timeout_sec=max(timeout_sec, 5),
    )
    candidates = _extract_chat_mention_usernames(body_html)[:deep_limit]
    if not candidates:
        return 0, 0

    members_by_peer = {str(item.get("peer_id") or "").strip(): item for item in members}
    username_to_peer = _seed_username_to_peer(members)
    tg_mode = _tg_web_mode_from_url(group_url)
    attempted = 0
    updated = 0
    for username_raw in candidates:
        attempted += 1
        username = _normalize_username(username_raw)
        if username == "—":
            continue
        user_url = f"https://web.telegram.org/{tg_mode}/#{username}"
        _send_command_result(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=min(timeout_sec, 8),
            command={"type": "navigate", "url": user_url},
            raise_on_fail=False,
        )
        time.sleep(0.35)
        user_html = _send_get_html(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=min(timeout_sec, 6),
            selector="body",
        )
        peer_match = re.search(
            r'<div class="chat-info[^"]*".*?<span class="peer-title"[^>]*data-peer-id="([^"]+)"',
            user_html,
            flags=re.S,
        )
        peer_id = peer_match.group(1) if peer_match else ""
        if peer_id and peer_id in members_by_peer and members_by_peer[peer_id].get("username") == "—":
            assigned, existing_peer, conflict_reason = _assign_username_if_unique(
                members_by_peer=members_by_peer,
                username_to_peer=username_to_peer,
                peer_id=peer_id,
                username=username,
                historical_username_to_peer=historical_username_to_peer,
                historical_peer_to_username=historical_peer_to_username,
            )
            if assigned:
                updated += 1
                print(f"INFO: chat mention deep mapped {username} -> peer {peer_id}")
            else:
                _log_username_assignment_conflict(username, peer_id, existing_peer, conflict_reason)

        if _is_specific_tg_dialog_url(group_url):
            _send_command_result(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=tab_id,
                timeout_sec=min(timeout_sec, 8),
                command={"type": "navigate", "url": group_url},
                raise_on_fail=False,
            )
            _send_command_result(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=tab_id,
                timeout_sec=min(timeout_sec, 7),
                command={
                    "type": "wait_selector",
                    "selector": ".bubbles .sticky_sentinel--top, .bubbles [data-mid], .bubbles .bubbles-group-avatar",
                    "timeout_ms": 5000,
                    "visible_only": False,
                },
                raise_on_fail=False,
            )
            time.sleep(0.25)
    return attempted, updated


def _collect_members_from_chat(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    timeout_sec: int,
    scroll_steps: int,
    group_url: str,
    deep_usernames: bool = False,
    chat_deep_limit: int = CHAT_DEEP_DEFAULT_LIMIT,
    max_runtime_sec: int = 40,
    chat_deep_mode: str = "mention",
    chat_target_peer_id: str = "",
    chat_target_name: str = "",
    min_members_target: int = 0,
    max_members: int = 0,
    historical_username_to_peer: dict[str, str] | None = None,
    historical_peer_to_username: dict[str, str] | None = None,
    discovery_state: dict[str, Any] | None = None,
    on_progress: Callable[[list[dict[str, str]], str], None] | None = None,
) -> tuple[list[dict[str, str]], dict[str, int]]:
    members: list[dict[str, str]] = []
    max_members_effective = max(int(max_members), 0)
    chat_html_timeout = max(5, min(timeout_sec, 8))
    started_at = time.time()
    previous_min_ts: int | None = None
    previous_member_count: int | None = None
    previous_view_signature = ""
    unchanged_steps = 0
    empty_steps = 0
    no_scroll_steps = 0
    scroll_steps_done = 0
    burst_scrolls_done = 0
    discovery_stall_steps = 0
    revisited_view_steps = 0
    deep_seen_peer_ids: set[str] = set()
    deep_attempted_total = 0
    deep_updated_total = 0
    deep_deferred_steps = 0
    runtime_limited = False
    seen_view_signatures: list[str] = []
    seen_view_signature_set: set[str] = set()
    seen_peer_ids: list[str] = []
    seen_peer_id_set: set[str] = set()

    if isinstance(discovery_state, dict):
        raw_view_signatures = discovery_state.get("seen_view_signatures") or []
        raw_peer_ids = discovery_state.get("seen_peer_ids") or []
        if isinstance(raw_view_signatures, list):
            for value in raw_view_signatures:
                signature = str(value or "").strip()
                if not signature or signature in seen_view_signature_set:
                    continue
                seen_view_signatures.append(signature)
                seen_view_signature_set.add(signature)
        if isinstance(raw_peer_ids, list):
            for value in raw_peer_ids:
                peer_id = str(value or "").strip()
                if not peer_id or peer_id in seen_peer_id_set:
                    continue
                seen_peer_ids.append(peer_id)
                seen_peer_id_set.add(peer_id)

    for step in range(max(0, scroll_steps) + 1):
        if time.time() - started_at > max(max_runtime_sec, 5):
            print(f"WARN: chat runtime limit reached ({max_runtime_sec}s), stopping")
            runtime_limited = True
            break
        if _is_specific_tg_dialog_url(group_url):
            if not _return_to_group_dialog_reliable(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=tab_id,
                group_url=group_url,
                timeout_sec=min(timeout_sec, 8),
                allow_navigate_fallback=False,
            ):
                print("WARN: cannot restore target group dialog, stopping chat export")
                break

        html_payload = _send_get_html(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=chat_html_timeout,
        )

        chat_members = _parse_chat_members(html_payload)
        current_view_signature = _extract_chat_view_signature(html_payload)
        known_view_signature = bool(current_view_signature and current_view_signature in seen_view_signature_set)

        if chat_members:
            members.extend(chat_members)
            members = _dedupe_members(members)
            empty_steps = 0
            for item in chat_members:
                peer_id = str(item.get("peer_id") or "").strip()
                if not peer_id or peer_id in seen_peer_id_set:
                    continue
                seen_peer_ids.append(peer_id)
                seen_peer_id_set.add(peer_id)
        else:
            empty_steps += 1

        # Write intermediate snapshot as soon as visible members are parsed,
        # before potentially slow deep-username enrichment starts.
        if on_progress is not None:
            on_progress(members, f"chat step {step} collecting")

        deep_deferred_this_step = False
        if deep_usernames and members and chat_members:
            if time.time() - started_at > max(max_runtime_sec, 5):
                print(f"WARN: skip deep (runtime limit {max_runtime_sec}s reached)")
            else:
                # Process visible users bottom->top and only one deep target per scroll step.
                # This avoids repeatedly hitting a "sticky" avatar while chat is being scrolled.
                members_by_peer = {str(item.get("peer_id") or ""): item for item in members if item.get("peer_id")}
                ordered_visible_peer_ids: list[str] = []
                seen_visible_peer_ids: set[str] = set()
                for item in reversed(chat_members):
                    peer_id = str(item.get("peer_id") or "").strip()
                    if not peer_id or peer_id in seen_visible_peer_ids:
                        continue
                    seen_visible_peer_ids.add(peer_id)
                    ordered_visible_peer_ids.append(peer_id)

                deep_targets = []
                for peer_id in ordered_visible_peer_ids:
                    member = members_by_peer.get(peer_id)
                    if member is None:
                        continue
                    if member.get("username") != "—":
                        continue
                    if peer_id in deep_seen_peer_ids:
                        continue
                    deep_targets.append(member)
                if chat_target_peer_id:
                    deep_targets = [item for item in deep_targets if str(item.get("peer_id") or "").strip() == chat_target_peer_id]
                if chat_target_name:
                    target_key = _name_key(chat_target_name)
                    if target_key:
                        deep_targets = [item for item in deep_targets if target_key in _name_key(str(item.get("name") or ""))]
                chat_anchor_peer_id = ""
                if deep_targets:
                    chat_anchor_peer_id = _get_chat_anchor_peer_id(server, token, client_id, tab_id)
                if chat_anchor_peer_id:
                    deep_targets = sorted(
                        deep_targets,
                        key=lambda item: 0 if str(item.get("peer_id") or "").strip() == chat_anchor_peer_id else 1,
                    )
                limit = max(int(chat_deep_limit), 0)
                if limit <= 0:
                    deep_targets = []
                else:
                    deep_targets = deep_targets[:limit]
                if deep_targets:
                    deep_targets = deep_targets[:1]
                if deep_targets:
                    if not _should_run_chat_deep_step(
                        step=step,
                        members_count=len(members),
                        min_members_target=min_members_target,
                        mode=chat_deep_mode,
                        chat_target_peer_id=chat_target_peer_id,
                        chat_target_name=chat_target_name,
                        known_view_signature=known_view_signature,
                    ):
                        deep_deferred_steps += 1
                        deep_deferred_this_step = True
                        print(
                            f"INFO: defer chat deep at step {step} "
                            f"(members {len(members)}/{max(int(min_members_target), 0)}, mode={chat_deep_mode})"
                        )
                    else:
                        elapsed = time.time() - started_at
                        remaining_runtime = max(2.0, float(max_runtime_sec) - elapsed - 2.0)
                        deep_runtime_budget = remaining_runtime
                        attempted, updated, opened, opened_peer_ids = _enrich_usernames_deep_chat(
                            server=server,
                            token=token,
                            client_id=client_id,
                            tab_id=tab_id,
                            timeout_sec=max(timeout_sec, 5),
                            members=deep_targets,
                            all_members=members,
                            group_url=group_url,
                            max_runtime_sec=deep_runtime_budget,
                            mode=chat_deep_mode,
                            historical_username_to_peer=historical_username_to_peer,
                            historical_peer_to_username=historical_peer_to_username,
                        )
                        deep_attempted_total += attempted
                        deep_updated_total += updated
                        for peer_id in opened_peer_ids:
                            deep_seen_peer_ids.add(peer_id)
                        print(
                            f"INFO: chat deep step {step}: processed {attempted}, "
                            f"opened {opened}, filled {updated}, total_filled {deep_updated_total}"
                        )

        if max_members_effective and len(members) > max_members_effective:
            members = members[:max_members_effective]

        print(f"INFO: chat step {step} collected {len(members)} unique users")
        if on_progress is not None:
            on_progress(members, f"chat step {step}")

        if max_members_effective and len(members) >= max_members_effective:
            print(f"INFO: chat max-members reached ({max_members_effective}), stopping")
            break

        timestamps = [int(value) for value in re.findall(r'data-timestamp="(\d+)"', html_payload)]
        min_ts = min(timestamps) if timestamps else None
        current_member_count = len(members)
        view_changed = bool(current_view_signature and current_view_signature != previous_view_signature)
        if (
            min_ts is not None
            and min_ts == previous_min_ts
            and current_member_count == previous_member_count
            and not view_changed
        ):
            unchanged_steps += 1
            discovery_stall_steps += 1
        else:
            unchanged_steps = 0
            discovery_stall_steps = 0
        if known_view_signature and min_members_target > 0 and current_member_count < min_members_target:
            revisited_view_steps += 1
            discovery_stall_steps += 1
            print(
                f"INFO: revisit known chat view at step {step} "
                f"(members {current_member_count}/{min_members_target})"
            )
        previous_min_ts = min_ts
        previous_member_count = current_member_count
        previous_view_signature = current_view_signature
        if current_view_signature and current_view_signature not in seen_view_signature_set:
            seen_view_signatures.append(current_view_signature)
            seen_view_signature_set.add(current_view_signature)
            if len(seen_view_signatures) > DISCOVERY_STATE_MAX_SIGNATURES:
                drop = seen_view_signatures.pop(0)
                seen_view_signature_set.discard(drop)
        if len(seen_peer_ids) > DISCOVERY_STATE_MAX_PEERS:
            overflow = len(seen_peer_ids) - DISCOVERY_STATE_MAX_PEERS
            for _ in range(overflow):
                drop = seen_peer_ids.pop(0)
                seen_peer_id_set.discard(drop)

        if step >= scroll_steps:
            break
        if empty_steps >= 2 and not members:
            print("WARN: чат не читается (пустой DOM/не открыт диалог), останавливаюсь")
            break
        if not _scroll_chat_up(server, token, client_id, tab_id, timeout_sec=min(timeout_sec, 10)):
            no_scroll_steps += 1
            if no_scroll_steps >= 3:
                print("WARN: chat scroll stuck after 3 attempts, stopping")
                break
            time.sleep(CHAT_SCROLL_SETTLE_SEC)
            continue
        no_scroll_steps = 0
        scroll_steps_done += 1
        extra_bursts = 0
        if (
            CHAT_DISCOVERY_SCROLL_BURST > 1
            and min_members_target > 0
            and len(members) < min_members_target
            and deep_deferred_this_step
            and discovery_stall_steps >= 1
        ):
            extra_bursts = CHAT_DISCOVERY_SCROLL_BURST - 1
        if extra_bursts > 0:
            for burst_index in range(extra_bursts):
                time.sleep(CHAT_DISCOVERY_BURST_SETTLE_SEC)
                if not _scroll_chat_up(server, token, client_id, tab_id, timeout_sec=min(timeout_sec, 10)):
                    break
                burst_scrolls_done += 1
                scroll_steps_done += 1
                print(
                    f"INFO: discovery burst scroll {burst_index + 1}/{extra_bursts} "
                    f"at step {step} (stall={discovery_stall_steps})"
                )
        time.sleep(CHAT_SCROLL_SETTLE_SEC)

    stats = {
        "unique_members": len(members),
        "scroll_steps_done": scroll_steps_done,
        "burst_scrolls_done": burst_scrolls_done,
        "revisited_view_steps": revisited_view_steps,
        "deep_attempted": deep_attempted_total,
        "deep_updated": deep_updated_total,
        "deep_deferred_steps": deep_deferred_steps,
        "runtime_limited": int(runtime_limited),
    }
    if isinstance(discovery_state, dict):
        discovery_state["seen_view_signatures"] = seen_view_signatures[-DISCOVERY_STATE_MAX_SIGNATURES:]
        discovery_state["seen_peer_ids"] = seen_peer_ids[-DISCOVERY_STATE_MAX_PEERS:]
    return members, stats


def _enrich_usernames_deep_chat(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    timeout_sec: int,
    members: list[dict[str, str]],
    all_members: list[dict[str, str]] | None = None,
    group_url: str = "",
    max_runtime_sec: float = 12.0,
    mode: str = "url",
    historical_username_to_peer: dict[str, str] | None = None,
    historical_peer_to_username: dict[str, str] | None = None,
) -> tuple[int, int, int, list[str]]:
    members_by_peer = {item["peer_id"]: item for item in members}
    pending_peer_ids = [item["peer_id"] for item in members if item.get("username") == "—"]
    username_to_peer = _seed_username_to_peer(all_members or members)
    target_fragment = group_url.split("#", 1)[1] if "#" in group_url else ""
    tg_mode = _tg_web_mode_from_url(group_url)

    attempted = 0
    updated = 0
    opened = 0
    opened_peer_ids: list[str] = []
    started_at = time.time()

    for peer_id in pending_peer_ids:
        if time.time() - started_at > max_runtime_sec:
            print("WARN: deep chat step budget exhausted, continue with next scroll step")
            break
        attempted += 1
        # Mark as processed for this run to avoid re-clicking the same peer again and again.
        opened_peer_ids.append(peer_id)
        if not _is_specific_tg_dialog_url(group_url):
            break

        if not _return_to_group_dialog_reliable(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            group_url=group_url,
            timeout_sec=min(timeout_sec, 3),
            allow_navigate_fallback=False,
        ):
            print("WARN: deep chat could not restore group dialog, skipping user")
            continue

        current_url_before = _get_tab_url(server, token, client_id, tab_id)
        current_fragment_before = current_url_before.split("#", 1)[1] if "#" in current_url_before else ""
        if target_fragment and (not current_fragment_before or target_fragment not in current_fragment_before):
            print("WARN: deep chat not in target group dialog, skipping user")
            continue

        if mode in ("mention", "full"):
            mention_username = _try_username_via_mention_action(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=tab_id,
                peer_id=peer_id,
            )
            if mention_username != "—":
                assigned, existing_peer, conflict_reason = _assign_username_if_unique(
                    members_by_peer=members_by_peer,
                    username_to_peer=username_to_peer,
                    peer_id=peer_id,
                    username=mention_username,
                    historical_username_to_peer=historical_username_to_peer,
                    historical_peer_to_username=historical_peer_to_username,
                )
                if not assigned:
                    _log_username_assignment_conflict(mention_username, peer_id, existing_peer, conflict_reason)
                    continue
                if assigned:
                    updated += 1
                    print(f"INFO: chat mention {peer_id} -> {mention_username}")
                _return_to_group_dialog_reliable(
                    server=server,
                    token=token,
                    client_id=client_id,
                    tab_id=tab_id,
                    group_url=group_url,
                    timeout_sec=min(timeout_sec, 2),
                    allow_navigate_fallback=False,
                )
                time.sleep(0.03)
                continue

        if mode == "mention":
            # Safe mode: do not leave group chat if mention did not resolve username.
            continue

        clicked = _open_peer_dialog_from_group_chat(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            peer_id=peer_id,
            timeout_sec=min(timeout_sec, 3),
        )
        if not clicked:
            peer_url = f"https://web.telegram.org/{tg_mode}/#{peer_id}"
            nav_result = _send_command_result(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=tab_id,
                timeout_sec=min(timeout_sec, 3),
                command={"type": "navigate", "url": peer_url},
                raise_on_fail=False,
            )
            if nav_result.get("ok"):
                clicked = True

        if not clicked:
            _return_to_group_dialog_reliable(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=tab_id,
                group_url=group_url,
                timeout_sec=min(timeout_sec, 3),
                allow_navigate_fallback=False,
            )
            time.sleep(0.05)
            continue

        opened += 1

        # Fast path: Telegram often switches URL to /#@username immediately.
        quick_username, _quick_url = _poll_username_from_tab_url(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=1.2,
        )
        if quick_username != "—":
            assigned, existing_peer, conflict_reason = _assign_username_if_unique(
                members_by_peer=members_by_peer,
                username_to_peer=username_to_peer,
                peer_id=peer_id,
                username=quick_username,
                historical_username_to_peer=historical_username_to_peer,
                historical_peer_to_username=historical_peer_to_username,
            )
            if not assigned:
                _log_username_assignment_conflict(quick_username, peer_id, existing_peer, conflict_reason)
            elif assigned:
                updated += 1
                print(f"INFO: chat url {peer_id} -> {quick_username}")
            _return_to_group_dialog_reliable(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=tab_id,
                group_url=group_url,
                timeout_sec=min(timeout_sec, 3),
                allow_navigate_fallback=False,
            )
            time.sleep(0.05)
            continue

        if mode == "url":
            _return_to_group_dialog_reliable(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=tab_id,
                group_url=group_url,
                timeout_sec=min(timeout_sec, 3),
                allow_navigate_fallback=False,
            )
            time.sleep(0.05)
            continue

        _send_command_result(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=min(timeout_sec, 4),
            command={
                "type": "wait_selector",
                "selector": ".chat-info .peer-title, .sidebar-header .peer-title",
                "timeout_ms": 2200,
                "visible_only": False,
            },
            raise_on_fail=False,
        )

        username = _open_current_chat_user_info_and_read_username(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=min(timeout_sec, 4),
        )

        if username != "—":
            assigned, existing_peer, conflict_reason = _assign_username_if_unique(
                members_by_peer=members_by_peer,
                username_to_peer=username_to_peer,
                peer_id=peer_id,
                username=username,
                historical_username_to_peer=historical_username_to_peer,
                historical_peer_to_username=historical_peer_to_username,
            )
            if not assigned:
                _log_username_assignment_conflict(username, peer_id, existing_peer, conflict_reason)
            elif assigned:
                updated += 1
                print(f"INFO: chat deep {peer_id} -> {username}")

        if not _return_to_group_dialog_reliable(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            group_url=group_url,
            timeout_sec=min(timeout_sec, 4),
            allow_navigate_fallback=False,
        ):
            print("WARN: deep chat failed to return to group dialog; continue")
            continue

        _send_command_result(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=min(timeout_sec, 3),
            command={
                "type": "wait_selector",
                "selector": ".bubbles .sticky_sentinel--top, .bubbles [data-mid], .bubbles .bubbles-group-avatar",
                "timeout_ms": 2000,
                "visible_only": False,
            },
            raise_on_fail=False,
        )
        time.sleep(0.08)

    return attempted, updated, opened, opened_peer_ids


def _find_tab(clients: list[dict[str, Any]], client_id: str | None, tab_id: int | None, url_pattern: str) -> tuple[str, int]:
    selected_client: dict[str, Any] | None = None
    if client_id:
        for client in clients:
            if client.get("client_id") == client_id:
                selected_client = client
                break
        if selected_client is None:
            raise RuntimeError(f"client_id not found: {client_id}")
    else:
        if not clients:
            raise RuntimeError("No connected clients found")
        selected_client = clients[0]

    cid = str(selected_client.get("client_id", "")).strip()
    tabs = selected_client.get("tabs") or []
    if not isinstance(tabs, list):
        tabs = []

    if tab_id is not None:
        for tab in tabs:
            if tab.get("id") == tab_id:
                return cid, int(tab_id)
        raise RuntimeError(f"tab_id not found in client {cid}: {tab_id}")

    # 1) Exact/pattern match requested by user; prefer active tab if duplicates exist.
    pattern_matches: list[tuple[int, int]] = []
    for tab in tabs:
        url = str(tab.get("url") or "")
        if url_pattern and url_pattern in url:
            tid = tab.get("id")
            if isinstance(tid, int):
                priority = 0 if bool(tab.get("active")) else 1
                pattern_matches.append((priority, tid))
    if pattern_matches:
        pattern_matches.sort()
        return cid, pattern_matches[0][1]

    # 2) Prefer explicit dialog URLs with hash fragment, avoid bare /k/ root.
    for tab in tabs:
        url = str(tab.get("url") or "")
        if "web.telegram.org/k/#" in url or "web.telegram.org/a/#" in url:
            tid = tab.get("id")
            if isinstance(tid, int):
                return cid, tid

    # 3) As a final fallback use active Telegram tab, but still avoid /k/ root.
    for tab in tabs:
        url = str(tab.get("url") or "")
        is_active = bool(tab.get("active"))
        if is_active and "web.telegram.org" in url and ("/k/#" in url or "/a/#" in url):
            tid = tab.get("id")
            if isinstance(tid, int):
                return cid, tid

    # 4) Last-resort fallback: use any active Telegram tab (including /a/ or /k/ root),
    # then explicit navigation will move it to --group-url.
    for tab in tabs:
        url = str(tab.get("url") or "")
        if bool(tab.get("active")) and "web.telegram.org" in url:
            tid = tab.get("id")
            if isinstance(tid, int):
                return cid, tid

    # 5) Absolute last fallback: first Telegram tab.
    for tab in tabs:
        url = str(tab.get("url") or "")
        if "web.telegram.org" in url:
            tid = tab.get("id")
            if isinstance(tid, int):
                return cid, tid

    opened_urls = ", ".join(str(tab.get("url") or "") for tab in tabs[:5]) or "none"
    raise RuntimeError(
        f"Telegram group tab not found (pattern: {url_pattern}). "
        f"Open target group dialog (URL with #) and rerun. Opened tabs: {opened_urls}"
    )


def _navigate_to_group_if_requested(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    group_url: str,
    timeout_sec: int,
) -> None:
    # If caller passed explicit dialog URL, force target tab to this dialog first.
    if not _is_specific_tg_dialog_url(group_url):
        return
    current_url = _get_tab_url(server, token, client_id, tab_id)
    target_fragment = group_url.split("#", 1)[1] if "#" in group_url else ""
    current_fragment = current_url.split("#", 1)[1] if "#" in current_url else ""
    if current_url and current_fragment and (not target_fragment or target_fragment in current_fragment):
        return

    def _navigate_once(url: str) -> str:
        nav_result = _send_command_result(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=min(timeout_sec, 15),
            command={
                "type": "navigate",
                "url": url,
            },
            raise_on_fail=False,
        )
        if not nav_result.get("ok"):
            return ""

        _send_command_result(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=min(timeout_sec, 15),
            command={
                "type": "wait_selector",
                "selector": "body",
                "timeout_ms": 12000,
                "visible_only": False,
            },
            raise_on_fail=False,
        )
        time.sleep(1.0)

        current_url = ""
        clients_response = _http_json_retry(server, token, "GET", "/api/clients")
        clients = clients_response.get("clients") or []
        if isinstance(clients, list):
            for client in clients:
                if str(client.get("client_id") or "").strip() != client_id:
                    continue
                tabs = client.get("tabs") or []
                if not isinstance(tabs, list):
                    break
                for tab in tabs:
                    if tab.get("id") == tab_id:
                        current_url = str(tab.get("url") or "").strip()
                        break
                break
        return current_url

    current_url = _navigate_once(group_url)
    current_fragment = current_url.split("#", 1)[1] if "#" in current_url else ""
    if current_url and current_fragment and (not target_fragment or target_fragment in current_fragment):
        return

    alt_url = _alternate_tg_dialog_url(group_url)
    if alt_url:
        alt_current_url = _navigate_once(alt_url)
        alt_fragment = alt_current_url.split("#", 1)[1] if "#" in alt_current_url else ""
        if alt_current_url and alt_fragment and (not target_fragment or target_fragment in alt_fragment):
            return

    raise RuntimeError(
        f"Telegram redirected to root page: {current_url or 'unknown'}. "
        f"Expected group URL with fragment: {group_url}"
    )


def _force_return_to_group_dialog(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    group_url: str,
    timeout_sec: int,
) -> bool:
    if not _is_specific_tg_dialog_url(group_url):
        return True
    target_fragment = group_url.split("#", 1)[1] if "#" in group_url else ""
    if not target_fragment:
        return True

    alt = _alternate_tg_dialog_url(group_url)
    candidates = [group_url]
    if alt:
        candidates.append(alt)

    for url in candidates:
        _send_command_result(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=min(timeout_sec, 3),
            command={"type": "navigate", "url": url},
            raise_on_fail=False,
        )
        deadline = time.time() + 1.2
        while time.time() < deadline:
            current_url = _get_tab_url(server, token, client_id, tab_id)
            current_fragment = current_url.split("#", 1)[1] if "#" in current_url else ""
            if current_fragment and target_fragment in current_fragment:
                return True
            time.sleep(0.15)
    return False


def _return_to_group_dialog_fast(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    group_url: str,
    timeout_sec: int,
) -> bool:
    if not _is_specific_tg_dialog_url(group_url):
        return True
    target_fragment = group_url.split("#", 1)[1] if "#" in group_url else ""
    if not target_fragment:
        return True

    # Fast path: browser history back only.
    _send_command_result(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        timeout_sec=2,
        command={"type": "back"},
        raise_on_fail=False,
    )
    deadline = time.time() + min(max(timeout_sec, 1), 2)
    while time.time() < deadline:
        loc = _send_command_result(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=2,
            command={"type": "get_page_url"},
            raise_on_fail=False,
        )
        data = loc.get("data") or {}
        value = data.get("url") if isinstance(data, dict) else ""
        current_url = str(value or "").strip()
        current_fragment = current_url.split("#", 1)[1] if "#" in current_url else ""
        if current_fragment and target_fragment in current_fragment:
            return True
        time.sleep(0.12)
    return False


def _open_info_members_view(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    timeout_sec: int,
) -> bool:
    html_right = ""
    try:
        html_right = _send_get_html(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=max(timeout_sec, 5),
            selector="#column-right",
        )
    except RuntimeError:
        html_right = ""
    if _parse_members(html_right):
        return True

    # Open chat/group profile from header.
    for selector in (
        ".chat-info",
        ".chat-info .person",
        ".chat-info-container .chat-info",
        ".sidebar-header .chat-info",
    ):
        clicked = _send_command_result(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=min(timeout_sec, 8),
            command={"type": "click", "selector": selector, "timeout_ms": 2500},
            raise_on_fail=False,
        )
        if clicked.get("ok"):
            break

    _send_command_result(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        timeout_sec=min(timeout_sec, 10),
        command={
            "type": "wait_selector",
            "selector": "#column-right .profile-content",
            "timeout_ms": 8000,
            "visible_only": False,
        },
        raise_on_fail=False,
    )

    # Click members row in profile sidebar.
    _send_command_result(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        timeout_sec=min(timeout_sec, 10),
        command={
            "type": "click_text",
            "root_selector": "#column-right",
            "terms": ["members", "member", "участ", "подписчик"],
        },
        raise_on_fail=False,
    )

    _send_command_result(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        timeout_sec=min(timeout_sec, 12),
        command={
            "type": "wait_selector",
            "selector": "#column-right a.chatlist-chat-abitbigger[data-dialog=\"0\"]",
            "timeout_ms": 9000,
            "visible_only": False,
        },
        raise_on_fail=False,
    )
    time.sleep(0.8)

    try:
        html_right = _send_get_html(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=max(timeout_sec, 5),
            selector="#column-right",
        )
    except RuntimeError:
        html_right = ""
    return bool(_parse_members(html_right))


def _send_command_result(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    timeout_sec: int,
    command: dict[str, Any],
    *,
    raise_on_fail: bool = True,
) -> dict[str, Any]:
    payload = {
        "issued_by": "telegram-members-non-pii-export",
        "timeout_ms": max(1000, timeout_sec * 1000),
        "target": {
            "client_id": client_id,
            "tab_id": tab_id,
            "active": True,
        },
        "command": command,
    }
    created = _http_json_retry(server, token, "POST", "/api/commands", payload)
    if not created.get("ok") or not created.get("command_id"):
        raise RuntimeError(f"Command creation failed: {created}")

    command_id = str(created["command_id"])
    deadline = time.time() + timeout_sec
    while True:
        response = _http_json_retry(server, token, "GET", f"/api/commands/{command_id}")
        command_state = response.get("command") or {}
        status = str(command_state.get("status") or "")
        if status in TERMINAL_STATUSES:
            deliveries = command_state.get("deliveries") or {}
            delivery: dict[str, Any] = {}
            if isinstance(deliveries, dict):
                candidate = (deliveries.get(client_id) or {}).get("result")
                if isinstance(candidate, dict):
                    delivery = dict(candidate)
                else:
                    for payload in deliveries.values():
                        if not isinstance(payload, dict):
                            continue
                        result_payload = payload.get("result")
                        if isinstance(result_payload, dict):
                            delivery = dict(result_payload)
                            break

            if "ok" not in delivery:
                delivery["ok"] = False
            if "status" not in delivery and status:
                delivery["status"] = status
            if not delivery.get("ok") and not delivery.get("error"):
                delivery["error"] = {
                    "message": (
                        f"command={command.get('type')} status={status} "
                        f"no delivery result for client_id={client_id}"
                    )
                }

            if raise_on_fail and not delivery.get("ok"):
                err = delivery.get("error") or {}
                msg = _format_command_error(err)
                if "Receiving end does not exist" in msg and command.get("type") != "navigate":
                    # Content script not attached yet; refresh dialog and retry once.
                    _send_command_result(
                        server=server,
                        token=token,
                        client_id=client_id,
                        tab_id=tab_id,
                        timeout_sec=min(timeout_sec, 6),
                        command={"type": "navigate", "url": _get_tab_url(server, token, client_id, tab_id) or "https://web.telegram.org/k/#"},
                        raise_on_fail=False,
                    )
                    time.sleep(0.5)
                    retry = _send_command_result(
                        server=server,
                        token=token,
                        client_id=client_id,
                        tab_id=tab_id,
                        timeout_sec=timeout_sec,
                        command=command,
                        raise_on_fail=False,
                    )
                    if retry.get("ok"):
                        return retry
                raise RuntimeError(f"Command failed ({command.get('type')}): {msg or 'unknown error'}")
            return delivery
        if time.time() >= deadline:
            if raise_on_fail:
                raise RuntimeError(f"Timeout waiting for command: {command.get('type')}")
            return {"ok": False, "error": f"timeout waiting for command: {command.get('type')}"}
        time.sleep(0.2)


def _send_get_html(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    timeout_sec: int,
    selector: str = "body",
) -> str:
    delivery = _send_command_result(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        timeout_sec=timeout_sec,
        command={
            "type": "get_html",
            "selector": selector,
            "timeout_ms": 10000,
        },
    )
    html_payload = (delivery.get("data") or {}).get("html")
    if not isinstance(html_payload, str) or not html_payload:
        raise RuntimeError("Command succeeded but HTML payload is empty")
    return html_payload


def _close_profile_card(server: str, token: str, client_id: str, tab_id: int) -> None:
    # Important: close only the right profile sidebar.
    for selector in (
        "#column-right button.sidebar-close-button",
        "#column-right .sidebar-header button.sidebar-close-button",
    ):
        result = _send_command_result(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=8,
            command={
                "type": "click",
                "selector": selector,
                "timeout_ms": 3000,
            },
            raise_on_fail=False,
        )
        if result.get("ok"):
            return


def _enrich_usernames_deep(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    timeout_sec: int,
    members: list[dict[str, str]],
    all_members: list[dict[str, str]] | None = None,
    historical_username_to_peer: dict[str, str] | None = None,
    historical_peer_to_username: dict[str, str] | None = None,
) -> tuple[int, int, list[str]]:
    members_by_peer = {item["peer_id"]: item for item in members}
    pending_peer_ids = [item["peer_id"] for item in members if item.get("username") == "—"]
    username_to_peer = _seed_username_to_peer(all_members or members)

    attempted = 0
    updated = 0
    opened_peer_ids: list[str] = []

    for peer_id in pending_peer_ids:
        attempted += 1
        origin_url = _get_tab_url(server, token, client_id, tab_id)

        click_result = {"ok": False}
        for selector in (
            f'#column-right a.chatlist-chat.chatlist-chat-abitbigger[data-peer-id="{peer_id}"]',
            f'#column-right a.chatlist-chat-abitbigger[data-peer-id="{peer_id}"]',
            f'a.chatlist-chat.chatlist-chat-abitbigger[data-peer-id="{peer_id}"]',
        ):
            click_result = _send_command_result(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=tab_id,
                timeout_sec=min(timeout_sec, 6),
                command={
                    "type": "click",
                    "selector": selector,
                    "timeout_ms": 2500,
                },
                raise_on_fail=False,
            )
            if click_result.get("ok"):
                break
        if not click_result.get("ok"):
            continue
        opened_peer_ids.append(peer_id)

        try:
            wait_result = _send_command_result(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=tab_id,
                timeout_sec=min(timeout_sec, 7),
                command={
                    "type": "wait_selector",
                    "selector": f'.profile-content .profile-name .peer-title[data-peer-id="{peer_id}"]',
                    "timeout_ms": 3000,
                    "visible_only": False,
                },
                raise_on_fail=False,
            )
            if not wait_result.get("ok"):
                continue

            profile_html = _send_get_html(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=tab_id,
                timeout_sec=min(timeout_sec, 7),
                selector="#column-right",
            )
            username = _extract_username_from_profile_html(profile_html)
            if username != "—":
                assigned, existing_peer, conflict_reason = _assign_username_if_unique(
                    members_by_peer=members_by_peer,
                    username_to_peer=username_to_peer,
                    peer_id=peer_id,
                    username=username,
                    historical_username_to_peer=historical_username_to_peer,
                    historical_peer_to_username=historical_peer_to_username,
                )
                if assigned:
                    updated += 1
                else:
                    _log_username_assignment_conflict(username, peer_id, existing_peer, conflict_reason)
        finally:
            _close_profile_card(server, token, client_id, tab_id)
            time.sleep(0.15)
            if not _restore_tab_url_from_history(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=tab_id,
                expected_url=origin_url,
                timeout_sec=min(timeout_sec, 6),
            ):
                print("WARN: info deep failed to restore original tab URL, stopping")
                break

    return attempted, updated, opened_peer_ids


def _parse_members(html_payload: str) -> list[dict[str, str]]:
    rows = re.findall(
        r'<a class="[^"]*chatlist-chat-abitbigger[^"]*"[^>]*data-peer-id="([^"]+)"[^>]*>(.*?)</a>',
        html_payload,
        flags=re.S,
    )

    members: list[dict[str, str]] = []
    seen_peer_ids: set[str] = set()

    for peer_id, row_html in rows:
        if 'data-dialog="0"' not in row_html:
            continue
        if peer_id in seen_peer_ids:
            continue

        name = ""
        with_icons = re.search(r'<span class="peer-title with-icons"[^>]*>(.*?)</span>', row_html, flags=re.S)
        if with_icons:
            inner = re.search(r'<span class="peer-title-inner"[^>]*>(.*?)</span>', with_icons.group(1), flags=re.S)
            name = _compact(inner.group(1) if inner else with_icons.group(1))
        else:
            plain = re.search(r'<span class="peer-title"[^>]*>(.*?)</span>', row_html, flags=re.S)
            if plain:
                name = _compact(plain.group(1))

        if not name:
            continue

        status = ""
        status_match = re.search(r'<div class="row-subtitle no-wrap"[^>]*>(.*?)</div>', row_html, flags=re.S)
        if status_match:
            status = _compact(status_match.group(1))

        role = ""
        role_match = re.search(r">(owner|admin)</span>", row_html, flags=re.I)
        if role_match:
            role = role_match.group(1).lower()

        username = _extract_username(row_html)

        members.append(
            {
                "peer_id": peer_id,
                "name": name,
                "status": status or "—",
                "role": role or "—",
                "username": username,
            }
        )
        seen_peer_ids.add(peer_id)

    return members


def _write_markdown(
    path: Path,
    members: list[dict[str, str]],
    group_url: str,
    source_mode: str,
    progress_note: str = "",
) -> None:
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = []
    lines.append("# Участники Telegram-группы")
    lines.append("")
    lines.append(f"Источник: `{group_url}`")
    lines.append(f"Режим сбора: `{source_mode}`")
    if progress_note:
        lines.append(f"Статус: **в процессе** ({progress_note})")
    lines.append(f"Дата выгрузки: {ts}")
    lines.append(f"Количество участников в текущем видимом списке: **{len(members)}**")
    lines.append("")
    lines.append("| # | Имя | Username | Статус | Роль | Peer ID |")
    lines.append("|---|---|---|---|---|---|")
    for index, item in enumerate(members, start=1):
        name = item["name"].replace("|", r"\|")
        username = item["username"].replace("|", r"\|")
        status = item["status"].replace("|", r"\|")
        role = item["role"].replace("|", r"\|")
        peer_id = item["peer_id"].replace("|", r"\|")
        lines.append(f"| {index} | {name} | {username} | {status} | {role} | {peer_id} |")
    lines.append("")
    lines.append("Примечание: телефоны намеренно не собираются этим скриптом.")
    lines.append("Для более полного сбора @username используйте флаг `--deep-usernames`.")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Экспорт участников Telegram-группы (из Info Members или из чата, без телефонов, с @username если доступен)."
    )
    parser.add_argument("--server", default=DEFAULT_SERVER, help=f"URL хаба (default: {DEFAULT_SERVER})")
    parser.add_argument(
        "--token",
        default="",
        help=f"Токен доступа (fallback: env {TOKEN_ENV}, потом {DEFAULT_TOKEN})",
    )
    parser.add_argument("--client-id", default="", help="Целевой client_id (опционально)")
    parser.add_argument("--tab-id", type=int, default=None, help="Целевой tab_id (опционально)")
    parser.add_argument(
        "--group-url",
        default="https://web.telegram.org/a/#-",
        help="URL/паттерн для поиска Telegram вкладки",
    )
    parser.add_argument(
        "--output",
        default="/home/max/Загрузки/Telegram Desktop/MadCoreChat_members_non_pii.md",
        help="Путь к выходному .md файлу",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=25,
        help="Таймаут запроса HTML в секундах",
    )
    parser.add_argument(
        "--source",
        choices=("info", "chat", "both"),
        default="info",
        help="Источник участников: info, chat, или both (объединить info + chat без дублей).",
    )
    parser.add_argument(
        "--max-members",
        type=int,
        default=0,
        help="Максимум пользователей в результате (0 = без лимита).",
    )
    parser.add_argument(
        "--chat-scroll-steps",
        type=int,
        default=10,
        help="Число прокруток вверх для режима --source chat.",
    )
    parser.add_argument(
        "--info-scroll-steps",
        type=int,
        default=0,
        help="Число прокруток вниз списка Members для режима --source info.",
    )
    parser.add_argument(
        "--deep-usernames",
        action="store_true",
        help="Открывать карточки участников и собирать @username максимально полно (медленнее).",
    )
    parser.add_argument(
        "--chat-deep-limit",
        type=int,
        default=CHAT_DEEP_DEFAULT_LIMIT,
        help="Максимум пользователей для deep-прохода/mention-обогащения в режиме --source chat/both.",
    )
    parser.add_argument(
        "--chat-max-runtime",
        type=int,
        default=180,
        help="Максимальное время (сек) на весь chat-проход, чтобы не зависал.",
    )
    parser.add_argument(
        "--chat-deep-mode",
        choices=("mention", "url", "full"),
        default="mention",
        help="Режим chat deep: mention (ПКМ->Mention), url (переход в профиль и чтение @ из URL), full (url + профиль справа).",
    )
    parser.add_argument(
        "--chat-target-peer-id",
        default="",
        help="Для точечного теста chat deep: обрабатывать только этот peer_id.",
    )
    parser.add_argument(
        "--chat-target-name",
        default="",
        help="Для точечного теста chat deep: обрабатывать только имя (подстрока, без учета регистра/символов).",
    )
    parser.add_argument(
        "--chat-min-members",
        type=int,
        default=0,
        help="Минимум уникальных людей в chat-режиме; пока меньше, ранняя остановка по unchanged отключается.",
    )
    parser.add_argument(
        "--force-navigate",
        action="store_true",
        help="Принудительно навигировать вкладку Telegram на --group-url перед сбором.",
    )
    parser.add_argument(
        "--identity-history",
        default="",
        help="JSON-файл с историей peer_id <-> username для защиты от ложных переназначений.",
    )
    parser.add_argument(
        "--discovery-state",
        default="",
        help="JSON-файл с историей discovery-проходов чата (виденные view signatures и peer_id).",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    token = args.token or os.getenv(TOKEN_ENV, "") or DEFAULT_TOKEN
    server = _norm_server(args.server)
    group_url = args.group_url
    out_path = Path(args.output).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    identity_history_path = Path(args.identity_history).expanduser() if args.identity_history else None
    discovery_state_path = Path(args.discovery_state).expanduser() if args.discovery_state else None
    historical_username_to_peer, historical_peer_to_username = _load_identity_history(identity_history_path)
    discovery_state = _load_discovery_state(discovery_state_path)
    if historical_username_to_peer or historical_peer_to_username:
        print(
            f"INFO: loaded identity history: usernames={len(historical_username_to_peer)}, "
            f"peers={len(historical_peer_to_username)}"
        )
    if discovery_state.get("seen_view_signatures") or discovery_state.get("seen_peer_ids"):
        print(
            f"INFO: loaded discovery state: signatures={len(discovery_state.get('seen_view_signatures') or [])}, "
            f"peers={len(discovery_state.get('seen_peer_ids') or [])}"
        )

    def _write_progress_snapshot(current_members: list[dict[str, str]], mode_label: str, stage: str) -> None:
        snapshot = _dedupe_members(current_members)
        try:
            _write_markdown(out_path, snapshot, group_url, mode_label, progress_note=stage)
        except Exception as progress_exc:  # noqa: BLE001
            print(f"WARN: cannot write progress snapshot: {progress_exc}", file=sys.stderr)

    try:
        clients_all_initial = _load_clients(server, token)
        initial_fresh, initial_newest_seen = _fresh_clients(clients_all_initial, ACTIVE_CLIENT_MAX_AGE_SEC)
        if not initial_fresh and _is_specific_tg_dialog_url(group_url):
            try:
                if webbrowser.open(group_url, new=2, autoraise=True):
                    print(f"INFO: opened browser tab for heartbeat wake-up: {group_url}")
            except Exception as browser_exc:  # noqa: BLE001
                print(f"WARN: cannot auto-open browser tab: {browser_exc}")
        if not initial_fresh and clients_all_initial:
            print(
                f"INFO: waiting up to {ACTIVE_CLIENT_WAIT_SEC}s for fresh bridge heartbeat "
                f"(last seen: {initial_newest_seen or 'unknown'})"
            )
        clients, newest_seen = _wait_for_fresh_clients(
            server=server,
            token=token,
            max_age_sec=ACTIVE_CLIENT_MAX_AGE_SEC,
            wait_sec=ACTIVE_CLIENT_WAIT_SEC,
        )
        if not clients:
            if clients_all_initial:
                print(
                    "WARN: no fresh clients after wait; using stale client list. "
                    "If commands fail, click Heartbeat in extension popup and retry."
                )
                clients = clients_all_initial
            else:
                hint = (
                    f" Последний heartbeat: {newest_seen}."
                    if newest_seen
                    else ""
                )
                raise RuntimeError(
                    "Нет активных bridge-клиентов (старые/неактуальные сессии). "
                    "Откройте Telegram Web, убедитесь что расширение подключено, нажмите Heartbeat в popup расширения и повторите."
                    f"{hint}"
                )

        client_id, tab_id = _find_tab(
            clients=clients,
            client_id=args.client_id or None,
            tab_id=args.tab_id,
            url_pattern=group_url,
        )
        if args.source in ("chat", "both") and not _is_specific_tg_dialog_url(group_url):
            detected_group_url = _detect_current_dialog_url(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=tab_id,
                timeout_sec=max(args.timeout, 5),
            )
            if detected_group_url:
                group_url = detected_group_url
                print(f"INFO: auto-detected dialog URL: {group_url}")
            else:
                raise RuntimeError(
                    "Не удалось определить текущий чат. Откройте нужную группу/чат и повторите, "
                    "или передайте --group-url c # (пример: https://web.telegram.org/a/#-2181640359)."
                )

        if args.force_navigate:
            _navigate_to_group_if_requested(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=tab_id,
                group_url=group_url,
                timeout_sec=max(args.timeout, 5),
            )

        source_label = args.source
        chat_stats: dict[str, int] = {}
        info_stats: dict[str, int] = {}
        info_members: list[dict[str, str]] = []
        chat_members: list[dict[str, str]] = []

        _write_progress_snapshot([], source_label, "start")

        if args.source in ("info", "both"):
            def _on_info_progress(current_info_members: list[dict[str, str]], stage: str) -> None:
                mode_label = "info" if args.source == "info" else "both(info+chat)"
                _write_progress_snapshot(current_info_members, mode_label, stage)

            if not _open_info_members_view(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=tab_id,
                timeout_sec=max(args.timeout, 5),
            ):
                raise RuntimeError(
                    "Не удалось открыть Group Info -> Members автоматически. "
                    "Откройте список участников вручную и повторите."
                )
            info_members, info_stats = _collect_members_from_info(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=tab_id,
                timeout_sec=max(args.timeout, 5),
                scroll_steps=max(args.info_scroll_steps, 0),
                deep_usernames=bool(args.deep_usernames),
                max_members=max(args.max_members, 0),
                historical_username_to_peer=historical_username_to_peer,
                historical_peer_to_username=historical_peer_to_username,
                on_progress=_on_info_progress,
            )
            if not info_members:
                raise RuntimeError(
                    "Не найден список участников. Откройте в Telegram Web: Group Info -> Members, "
                    "затем повторите команду."
                )
            total_hint = int(info_stats.get("total_hint", 0))
            if total_hint and len(info_members) < total_hint:
                print(
                    f"WARN: в DOM загружено только {len(info_members)} из примерно {total_hint} участников. "
                    "Прокрутите список Members в Telegram Web и повторите выгрузку для более полного результата.",
                    file=sys.stderr,
                )
            print(
                f"INFO: info mode collected {info_stats.get('unique_members', len(info_members))} unique users "
                f"after {info_stats.get('scroll_steps_done', 0)} downward scroll steps"
            )

        if args.source in ("chat", "both"):
            def _on_chat_progress(current_chat_members: list[dict[str, str]], stage: str) -> None:
                if args.source == "both":
                    merged = _dedupe_members(info_members + current_chat_members)
                    _write_progress_snapshot(merged, "both(info+chat)", stage)
                    return
                _write_progress_snapshot(current_chat_members, "chat", stage)

            # If deep mode requested, apply it to chat collection for both chat and both modes.
            chat_deep = bool(args.deep_usernames)
            chat_scroll_steps_effective = max(args.chat_scroll_steps, 0)
            if chat_deep and chat_scroll_steps_effective < 2:
                chat_scroll_steps_effective = 2
                print("INFO: deep mode -> using 3 chat passes (2 upward scrolls) to refresh visible users")
            chat_members, chat_stats = _collect_members_from_chat(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=tab_id,
                timeout_sec=max(args.timeout, 5),
                scroll_steps=chat_scroll_steps_effective,
                group_url=group_url,
                deep_usernames=chat_deep,
                chat_deep_limit=max(args.chat_deep_limit, 0),
                max_runtime_sec=max(args.chat_max_runtime, 5),
                chat_deep_mode=args.chat_deep_mode,
                chat_target_peer_id=str(args.chat_target_peer_id or "").strip(),
                chat_target_name=str(args.chat_target_name or "").strip(),
                min_members_target=max(args.chat_min_members, 0),
                max_members=max(args.max_members, 0),
                historical_username_to_peer=historical_username_to_peer,
                historical_peer_to_username=historical_peer_to_username,
                discovery_state=discovery_state,
                on_progress=_on_chat_progress,
            )
            if not chat_members:
                raise RuntimeError(
                    "Не найдены авторы сообщений в чате. Откройте группу в режиме чата "
                    "(не только боковую панель Info), затем повторите."
                )
            print(
                f"INFO: chat mode collected {chat_stats['unique_members']} unique users "
                f"after {chat_stats['scroll_steps_done']} upward scroll steps"
            )

        if args.source == "both":
            members = _dedupe_members(info_members + chat_members)
            source_label = "both(info+chat)"
        elif args.source == "info":
            members = info_members
            source_label = "info"
        else:
            members = chat_members
            source_label = "chat"

        if not members:
            raise RuntimeError(
                "Не удалось собрать участников. Откройте группу/список участников и повторите."
            )

        members = _dedupe_members(members)
        if args.max_members > 0 and len(members) > args.max_members:
            members = members[: args.max_members]

        if args.deep_usernames:
            attempted = 0
            updated = 0

            if args.source in ("chat", "both"):
                chat_attempted = int(chat_stats.get("deep_attempted", 0))
                chat_updated = int(chat_stats.get("deep_updated", 0))
                deep_deferred_steps = int(chat_stats.get("deep_deferred_steps", 0))
                runtime_limited = bool(int(chat_stats.get("runtime_limited", 0)))
                mention_attempted = 0
                mention_updated = 0
                unresolved = sum(1 for item in members if str(item.get("username") or "—").strip() == "—")
                if unresolved > 0 and not runtime_limited and args.chat_deep_mode in ("url", "full"):
                    mention_attempted, mention_updated = _enrich_chat_usernames_via_mentions(
                        server=server,
                        token=token,
                        client_id=client_id,
                        tab_id=tab_id,
                        timeout_sec=max(args.timeout, 5),
                        group_url=group_url,
                        members=members,
                        deep_limit=max(args.chat_deep_limit, 0),
                        historical_username_to_peer=historical_username_to_peer,
                        historical_peer_to_username=historical_peer_to_username,
                    )
                    if mention_attempted:
                        print(
                            f"INFO: chat mention deep done: processed {mention_attempted}, "
                            f"filled {mention_updated}"
                        )
                elif runtime_limited:
                    print("INFO: skip mention deep because chat runtime limit was reached")
                elif unresolved > 0 and args.chat_deep_mode == "mention":
                    if deep_deferred_steps > 0:
                        mention_attempted, mention_updated = _enrich_chat_usernames_via_mentions(
                            server=server,
                            token=token,
                            client_id=client_id,
                            tab_id=tab_id,
                            timeout_sec=max(args.timeout, 5),
                            group_url=group_url,
                            members=members,
                            deep_limit=max(args.chat_deep_limit, 0),
                            historical_username_to_peer=historical_username_to_peer,
                            historical_peer_to_username=historical_peer_to_username,
                        )
                        if mention_attempted:
                            print(
                                f"INFO: chat mention catch-up done: processed {mention_attempted}, "
                                f"filled {mention_updated}"
                            )
                    else:
                        print("INFO: skip extra mention-deep pass in mention mode")

                attempted += chat_attempted + mention_attempted
                updated += chat_updated + mention_updated
                members = _dedupe_members(members)

            if args.source in ("info", "both"):
                attempted += int(info_stats.get("deep_attempted", 0))
                updated += int(info_stats.get("deep_updated", 0))

            print(f"INFO: deep mode processed {attempted} profiles, filled {updated} usernames")

        _write_markdown(out_path, members, group_url, source_label)
        _save_discovery_state(discovery_state_path, discovery_state)

        print(f"OK: saved {len(members)} members to {out_path}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
