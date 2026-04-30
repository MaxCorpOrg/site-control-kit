#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import html as html_lib
import json
import os
import re
import socket
import shutil
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_SERVER = "http://127.0.0.1:8765"
DEFAULT_TOKEN = "local-bridge-quickstart-2026"
TOKEN_ENV = "SITECTL_TOKEN"
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVE_DIR = REPO_ROOT / "artifacts" / "telegram_exports"
ARCHIVE_STATE_DIRNAME = "state"
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
BOT_TEXT_RE = re.compile(r"(^|[^a-zа-я0-9_])(bot|бот)([^a-zа-я0-9_]|$)", flags=re.I)
CHAT_TOP_SELECTOR = ".MessageList.custom-scroll .backwards-trigger"
CHAT_SCROLL_SELECTORS = (
    ".MessageList.custom-scroll .backwards-trigger",
    ".messages-layout .MessageList.custom-scroll .backwards-trigger",
    ".messages-container > :first-child",
    ".message-date-group.first-message-date-group",
    ".bubbles .sticky_sentinel--top",
    ".chat.tabs-tab.active .bubbles .bubbles-group-avatar",
    "#column-center .bubbles [data-mid]",
    ".chat.tabs-tab.active .bubbles",
)
CHAT_SCROLL_SETTLE_SEC = 0.35
CHAT_SCROLL_DISTANCE_PX = 900
INFO_SCROLL_SETTLE_SEC = 0.8
CHAT_DEEP_DEFAULT_LIMIT = 3
CHAT_AUTO_EXTRA_DEFAULT = 12
try:
    CHAT_DEEP_STEP_MAX_SEC = max(float(os.getenv("TELEGRAM_CHAT_DEEP_STEP_MAX_SEC", "0") or "0"), 0.0)
except ValueError:
    CHAT_DEEP_STEP_MAX_SEC = 0.0
try:
    CHAT_JUMP_SCROLL_TRIGGER_STALL = max(int(os.getenv("TELEGRAM_CHAT_JUMP_SCROLL_TRIGGER_STALL", "0") or "0"), 0)
except ValueError:
    CHAT_JUMP_SCROLL_TRIGGER_STALL = 0
try:
    CHAT_MENTION_DEEP_MAX_PER_STEP = max(int(os.getenv("TELEGRAM_CHAT_MENTION_DEEP_MAX_PER_STEP", "0") or "0"), 0)
except ValueError:
    CHAT_MENTION_DEEP_MAX_PER_STEP = 0
CHAT_MENTION_TRACE = str(os.getenv("TELEGRAM_CHAT_MENTION_TRACE", "") or "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
SPECIFIC_TG_DIALOG_URL_RE = re.compile(r"^https?://web\.telegram\.org/(k|a)/#[^#\s]+$", flags=re.I)
RIGHT_COLUMN_SELECTOR = "#RightColumn, #column-right"
RIGHT_PANEL_READY_SELECTOR = (
    "#RightColumn .content.members-list, "
    "#RightColumn .Profile, "
    "#column-right .profile-content, "
    "#column-right a.chatlist-chat-abitbigger[data-dialog=\"0\"]"
)


def _norm_server(url: str) -> str:
    return url.rstrip("/")


def _effective_timeout_sec(value: float, *, minimum: float = 0.8) -> float:
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        timeout = minimum
    return max(minimum, timeout)


def _remaining_timeout_sec(deadline: float, *, minimum: float = 0.4) -> float:
    return max(minimum, deadline - time.time())


def _deadline_timeout(deadline: float, requested: float, *, minimum: float = 0.4) -> float:
    try:
        requested_timeout = float(requested)
    except (TypeError, ValueError):
        requested_timeout = minimum
    return min(max(minimum, requested_timeout), _remaining_timeout_sec(deadline, minimum=minimum))


def _mention_trace_step(username: str, step: str, started_at: float, **fields: Any) -> None:
    if not CHAT_MENTION_TRACE:
        return
    extras: list[str] = []
    for key, value in fields.items():
        if value in ("", None):
            continue
        extras.append(f"{key}={value}")
    suffix = f" {' '.join(extras)}" if extras else ""
    elapsed = max(time.time() - started_at, 0.0)
    print(f"INFO: chat mention trace {username} {step} {elapsed:.2f}s{suffix}")


def _http_json(
    server: str,
    token: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    request_timeout_sec: float | None = None,
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
    timeout_sec = 30.0
    if request_timeout_sec is not None:
        try:
            timeout_sec = max(0.5, float(request_timeout_sec))
        except (TypeError, ValueError):
            timeout_sec = 30.0
    try:
        with urlopen(request, timeout=timeout_sec) as response:
            raw = response.read().decode("utf-8")
            if not raw:
                return {"ok": True}
            return json.loads(raw)
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
        raise RuntimeError(f"HTTP {exc.code}: {raw or exc.reason}") from exc
    except (URLError, TimeoutError, socket.timeout) as exc:
        reason = getattr(exc, "reason", None) or str(exc) or exc.__class__.__name__
        raise RuntimeError(f"Network error: {reason}") from exc


def _http_json_retry(
    server: str,
    token: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    retries: int = 3,
    *,
    request_timeout_sec: float | None = None,
) -> dict[str, Any]:
    last_error: RuntimeError | None = None
    for attempt in range(retries):
        try:
            return _http_json(
                server,
                token,
                method,
                path,
                payload,
                request_timeout_sec=request_timeout_sec,
            )
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


def _is_valid_username_candidate(value: str) -> bool:
    candidate = str(value or "").strip()
    return bool(USERNAME_VALUE_RE.fullmatch(candidate) and re.search(r"[A-Za-z]", candidate))


def _path_slug(value: str, fallback: str = "export") -> str:
    text = _compact(value).lower()
    text = text.replace("@", "at-")
    text = re.sub(r"[^a-zа-я0-9]+", "-", text, flags=re.I)
    text = text.strip("-")
    return text or fallback


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


def _archive_identity_slug(group_url: str) -> str:
    fragment = _dialog_fragment_from_url(group_url)
    if fragment:
        return _path_slug(fragment, fallback="telegram-dialog")
    return _path_slug(group_url, fallback="telegram-dialog")


def _default_identity_history_path(archive_dir: Path | None, group_url: str) -> Path | None:
    if archive_dir is None:
        return None
    state_dir = archive_dir / ARCHIVE_STATE_DIRNAME
    return state_dir / f"{_archive_identity_slug(group_url)}_identity_history.json"


def _dialog_row_fragment(fragment: str) -> str:
    value = (fragment or "").strip()
    if value.startswith("-100") and len(value) > 4:
        return f"-{value[4:]}"
    return value


def _extract_tab_meta_from_clients(clients: Any, client_id: str, tab_id: int) -> tuple[str, str]:
    if not isinstance(clients, list):
        return "", ""
    for client in clients:
        if str(client.get("client_id") or "").strip() != client_id:
            continue
        tabs = client.get("tabs") or []
        if not isinstance(tabs, list):
            return "", ""
        for tab in tabs:
            if tab.get("id") != tab_id:
                continue
            tab_url = str(tab.get("url") or "").strip()
            tab_title = _compact(str(tab.get("title") or ""))
            return tab_url, tab_title
        return "", ""
    return "", ""


def _get_tab_url(server: str, token: str, client_id: str, tab_id: int) -> str:
    clients_response = _http_json_retry(server, token, "GET", "/api/clients")
    tab_url, _tab_title = _extract_tab_meta_from_clients(clients_response.get("clients") or [], client_id, tab_id)
    return tab_url


def _get_tab_meta_best_effort(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    timeout_sec: float,
) -> tuple[str, str]:
    request_timeout_sec = min(max(float(timeout_sec), 0.3), 1.0)
    try:
        clients_response = _http_json(
            server,
            token,
            "GET",
            "/api/clients",
            request_timeout_sec=request_timeout_sec,
        )
    except RuntimeError:
        return "", ""
    return _extract_tab_meta_from_clients(clients_response.get("clients") or [], client_id, tab_id)


def _get_page_url_best_effort(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    timeout_sec: int = 2,
) -> str:
    result = _send_command_result(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        timeout_sec=min(max(timeout_sec, 0.3), 4),
        command={"type": "get_page_url"},
        raise_on_fail=False,
    )
    data = result.get("data") or {}
    value = data.get("url") if isinstance(data, dict) else ""
    return str(value or "").strip()


def _read_dialog_fragment_best_effort(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    timeout_sec: float,
) -> str:
    page_url = _get_page_url_best_effort(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        timeout_sec=min(max(timeout_sec, 0.3), 0.8),
    )
    fragment = _dialog_fragment_from_url(page_url)
    if fragment:
        return fragment
    return _dialog_fragment_from_url(_get_tab_url(server, token, client_id, tab_id))


def _detect_current_dialog_url(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    timeout_sec: int,
) -> str:
    page_url = _get_page_url_best_effort(server, token, client_id, tab_id, timeout_sec=min(timeout_sec, 2))
    if _is_specific_tg_dialog_url(page_url):
        return page_url
    url = _get_tab_url(server, token, client_id, tab_id)
    return url if _is_specific_tg_dialog_url(url) else ""


def _is_dialog_surface_open(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    timeout_sec: int,
) -> bool:
    result = _send_command_result(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        timeout_sec=min(max(timeout_sec, 2), 6),
        command={
            "type": "wait_selector",
            "selector": (
                ".MiddleHeader .ChatInfo .fullName, "
                ".middle-column-footer, "
                ".messages-container .Message, "
                ".bubbles .Message"
            ),
            "timeout_ms": 2500,
            "visible_only": False,
        },
        raise_on_fail=False,
    )
    return bool(result.get("ok"))


def _open_group_from_dialog_list(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    target_fragment: str,
    timeout_sec: int,
) -> bool:
    row_fragment = _dialog_row_fragment(target_fragment)
    candidate_ids = [value for value in {target_fragment, row_fragment} if value]
    if not candidate_ids:
        return False
    selectors: list[str] = []
    for candidate_id in candidate_ids:
        selectors.extend(
            [
                f'a.chatlist-chat[href="#{candidate_id}"]',
                f'a[href="#{candidate_id}"]',
                f'a.chatlist-chat[data-peer-id="{candidate_id}"]',
                f'a[data-peer-id="{candidate_id}"]',
                f'[data-peer-id="{candidate_id}"]',
            ]
        )
    for selector in selectors:
        click_result = _send_command_result(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=min(timeout_sec, 8),
            command={"type": "click", "selector": selector, "timeout_ms": 2500},
            raise_on_fail=False,
        )
        if not click_result.get("ok"):
            continue
        time.sleep(0.6)
        current_url = _get_tab_url(server, token, client_id, tab_id)
        current_fragment = current_url.split("#", 1)[1] if "#" in current_url else ""
        if current_fragment and target_fragment in current_fragment and _is_dialog_surface_open(
            server, token, client_id, tab_id, timeout_sec
        ):
            return True
    return False


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

    current_url = _detect_current_dialog_url(server, token, client_id, tab_id, timeout_sec=min(timeout_sec, 2))
    target_fragment = group_url.split("#", 1)[1] if "#" in group_url else ""
    current_fragment = current_url.split("#", 1)[1] if "#" in current_url else ""
    if current_url and current_fragment and (not target_fragment or target_fragment in current_fragment):
        if _is_dialog_surface_open(server, token, client_id, tab_id, timeout_sec):
            return True
    if current_url and current_fragment and (not target_fragment or target_fragment in current_fragment):
        if _open_group_from_dialog_list(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            target_fragment=target_fragment or current_fragment,
            timeout_sec=timeout_sec,
        ):
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
    fixed_url = _detect_current_dialog_url(server, token, client_id, tab_id, timeout_sec=min(timeout_sec, 2))
    fixed_fragment = fixed_url.split("#", 1)[1] if "#" in fixed_url else ""
    if fixed_url and fixed_fragment and (not target_fragment or target_fragment in fixed_fragment):
        if _is_dialog_surface_open(server, token, client_id, tab_id, timeout_sec):
            return True
        if _open_group_from_dialog_list(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            target_fragment=target_fragment or fixed_fragment,
            timeout_sec=timeout_sec,
        ):
            return True
    if _open_group_from_dialog_list(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        target_fragment=target_fragment,
        timeout_sec=timeout_sec,
    ):
        return True
    return False


def _normalize_username(value: str) -> str:
    text = _compact(value)
    if not text:
        return "—"

    patterns = (
        r"https?://t\.me/([A-Za-z0-9_]{5,32})",
        r"t\.me/([A-Za-z0-9_]{5,32})",
        r"@([A-Za-z0-9_]{5,32})",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            username = match.group(1)
            if _is_valid_username_candidate(username):
                return f"@{username}"
    if _is_valid_username_candidate(text):
        return f"@{text}"
    return "—"


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
        if _is_valid_username_candidate(candidate):
            return f"@{candidate}"
    if _is_valid_username_candidate(text):
        return f"@{text}"
    return "—"


def _contains_bot_marker(value: str) -> bool:
    text = _compact(value).lower()
    if not text:
        return False
    return bool(BOT_TEXT_RE.search(text))


def _is_probable_bot_member(member: dict[str, str]) -> bool:
    username = _normalize_username(str(member.get("username") or ""))
    if username != "—" and username.lower().endswith("bot"):
        return True
    if _contains_bot_marker(str(member.get("status") or "")):
        return True
    if _contains_bot_marker(str(member.get("role") or "")):
        return True
    return _contains_bot_marker(str(member.get("name") or ""))


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
        remaining = deadline - time.time()
        if remaining <= 0:
            return "—", last_url
        result = _send_command_result(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=min(max(remaining, 0.4), 1.0),
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


def _format_command_error(error: Any) -> str:
    if isinstance(error, dict):
        message = str(error.get("message") or "").strip()
        if message:
            return message
        return str(error).strip()
    return str(error or "").strip()


def _is_no_visible_menu_item_error(message: str) -> bool:
    text = str(message or "").strip().lower()
    return "no visible menu item found by text" in text


def _is_delivery_failure_error(message: str) -> bool:
    text = str(message or "").strip().lower()
    if not text:
        return False
    return (
        "finished without result" in text
        or "delivery_status=expired" in text
        or "command_status=expired" in text
        or "no delivery result" in text
        or "timeout waiting for command" in text
    )


def _chat_peer_anchor_selectors(peer_id: str) -> tuple[str, ...]:
    # Current Telegram Web exposes chat authors via `sender-group-container`
    # and a clickable sender-name block. Prefer name/title anchors first so we
    # open the message-specific context menu before falling back to avatar roots.
    return (
        f'.sender-group-container:has(.Avatar[data-peer-id="{peer_id}"]) .message-title-name-container.interactive',
        f'.sender-group-container:has(.Avatar[data-peer-id="{peer_id}"]) .message-title-name',
        f'.sender-group-container:has(.Avatar[data-peer-id="{peer_id}"]) .sender-title',
        f'.sender-group-container .Avatar.interactive[data-peer-id="{peer_id}"]',
        f'.sender-group-container .Avatar[data-peer-id="{peer_id}"]',
        f'.MessageList .Avatar.interactive[data-peer-id="{peer_id}"]',
        f'.MessageList .Avatar[data-peer-id="{peer_id}"]',
        f'.bubbles .bubbles-group-avatar.user-avatar[data-peer-id="{peer_id}"] .avatar-photo',
        f'.bubbles .bubbles-group-avatar.user-avatar[data-peer-id="{peer_id}"]',
        f'.colored-name.name.floating-part[data-peer-id="{peer_id}"]',
        f'.peer-title.bubble-name-first[data-peer-id="{peer_id}"]',
        f'.bubbles .peer-title[data-peer-id="{peer_id}"]',
    )


def _try_username_via_mention_action(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    peer_id: str,
    *,
    supports_click_menu_text: bool = True,
    use_sticky_anchor: bool = False,
) -> tuple[str, str]:
    # Prevent stale @username from previous attempts.
    _clear_composer_text(server, token, client_id, tab_id)

    clicked_context = False
    if use_sticky_anchor:
        opened = _telegram_sticky_author_command(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=2,
            context_click=True,
            expected_peer_id=peer_id,
        )
        if (
            opened
            and opened.get("context_clicked")
            and str(opened.get("peer_id") or "").strip() == str(peer_id or "").strip()
        ):
            clicked_context = True
    else:
        for selector in _chat_peer_anchor_selectors(peer_id):
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
                clicked_context = True
                break
    if not clicked_context:
        print(f"WARN: mention context menu not opened for peer {peer_id}")
        return "—", "context_missing"

    _send_command_result(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        timeout_sec=2,
        command={
            "type": "wait_selector",
            "selector": (
                "#bubble-contextmenu.active, .btn-menu.contextmenu.active, #bubble-contextmenu, "
                ".btn-menu.contextmenu, .btn-menu, .btn-menu-item, [role='menuitem']"
            ),
            "timeout_ms": 1200,
            "visible_only": False,
        },
        raise_on_fail=False,
    )

    menu_snapshot = _send_command_result(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        timeout_sec=1,
        command={
            "type": "extract_text",
            "selector": (
                ".MessageContextMenu_items, "
                ".menu-container.shown.open, "
                ".menu-container.open, "
                "#bubble-contextmenu.active, "
                ".btn-menu.contextmenu.active"
            ),
            "timeout_ms": 900,
        },
        raise_on_fail=False,
    )
    menu_snapshot_data = menu_snapshot.get("data") or {}
    menu_snapshot_text = _compact(
        str((menu_snapshot_data.get("text") if isinstance(menu_snapshot_data, dict) else "") or "")
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
    lowered_menu_snapshot = menu_snapshot_text.lower()
    if lowered_menu_snapshot and not any(term in lowered_menu_snapshot for term in mention_terms):
        print(
            f"INFO: current Telegram context menu for peer {peer_id} does not expose Mention, "
            "switch to helper fallback"
        )
        return "—", "menu_missing"

    no_visible_menu_item_misses = 0
    delivery_failure = False
    menu_missing_detected = False
    if not mention_click_ok:
        for attempt_index in range(3):
            click_menu_error_text = ""
            if supports_click_menu_text:
                mention_click = _send_command_result(
                    server=server,
                    token=token,
                    client_id=client_id,
                    tab_id=tab_id,
                    timeout_sec=2,
                    command={
                        "type": "click_menu_text",
                        "terms": mention_terms,
                        "near_last_context": True,
                    },
                    raise_on_fail=False,
                )
                if mention_click.get("ok"):
                    mention_click_ok = True
                    break
                click_menu_error_text = _format_command_error(mention_click.get("error"))
                if click_menu_error_text:
                    print(
                        f"INFO: mention click_menu_text miss on attempt {attempt_index + 1} "
                        f"for peer {peer_id}: {click_menu_error_text}"
                    )
                    if _is_delivery_failure_error(click_menu_error_text):
                        delivery_failure = True
                        break
                    if _is_no_visible_menu_item_error(click_menu_error_text):
                        menu_missing_detected = True
                        print(
                            f"INFO: mention menu item is not visible for peer {peer_id}, "
                            "switch to helper fallback"
                        )
                        break
            click_text_error = ""
            for root_selector in (
                "#bubble-contextmenu.active",
                "#bubble-contextmenu",
                ".btn-menu.contextmenu.active",
                ".btn-menu.contextmenu",
                "body",
            ):
                mention_click = _send_command_result(
                    server=server,
                    token=token,
                    client_id=client_id,
                    tab_id=tab_id,
                    timeout_sec=1,
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
                click_text_error = _format_command_error(mention_click.get("error"))
                if _is_delivery_failure_error(click_text_error):
                    delivery_failure = True
                    break
                if _is_no_visible_menu_item_error(click_text_error):
                    menu_missing_detected = True
                    break
            if mention_click_ok:
                break
            if delivery_failure:
                break
            if menu_missing_detected:
                break
            if _is_no_visible_menu_item_error(click_menu_error_text):
                no_visible_menu_item_misses += 1
                if no_visible_menu_item_misses >= 2:
                    print(
                        f"INFO: mention menu item still invisible after {no_visible_menu_item_misses} "
                        f"attempts for peer {peer_id}, switch to helper fallback"
                    )
                    break
            else:
                no_visible_menu_item_misses = 0
            time.sleep(0.14)
    if not mention_click_ok:
        print(f"WARN: mention item not clicked for peer {peer_id}")
        if delivery_failure:
            return "—", "delivery_failure"
        if menu_missing_detected:
            return "—", "menu_missing"
        if no_visible_menu_item_misses >= 2:
            return "—", "menu_missing"
        return "—", "menu_click_failed"

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
            return username, "success"
        time.sleep(0.15)

    _clear_composer_text(server, token, client_id, tab_id)
    print(f"WARN: mention clicked but username not read from composer for peer {peer_id}")
    return "—", "composer_unresolved"


def _open_peer_dialog_from_group_chat(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    peer_id: str,
    timeout_sec: int,
) -> bool:
    for selector in _chat_peer_anchor_selectors(peer_id):
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
    *,
    deadline: float | None = None,
) -> str:
    read_deadline = deadline if deadline is not None else time.time() + _effective_timeout_sec(timeout_sec, minimum=0.8)
    profile_html = ""

    def _profile_panel_has_content(html_payload: str) -> bool:
        html = str(html_payload or "")
        return (
            'class="Profile' in html
            or 'class="profile-info"' in html
            or 'class="multiline-item"' in html
            or '<h3 class="title">User Info</h3>' in html
        )

    for selector in (
        ".MiddleHeader .ChatInfo .fullName",
        ".MiddleHeader .ChatInfo",
        ".MiddleHeader .chat-info-wrapper .ChatInfo",
        ".MiddleHeader .ChatInfo .Avatar[data-peer-id]",
        ".MiddleHeader .ChatInfo [role=\"button\"]",
        ".MiddleHeader .ChatInfo .group-status",
        ".MiddleHeader .ChatInfo .info",
        ".MiddleHeader .ChatInfo .title",
        ".chat-info .peer-title",
        ".sidebar-header .peer-title",
        ".chat-info",
        ".chat-info .person",
        ".chat-info .person-avatar",
        ".sidebar-header .chat-info",
        ".chat-info-container .chat-info",
        "#column-center .chat-info",
    ):
        if time.time() >= read_deadline:
            break
        click_result = _send_command_result(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=_deadline_timeout(read_deadline, min(max(timeout_sec, 2), 3)),
            command={
                "type": "click",
                "selector": selector,
                "timeout_ms": 900,
            },
            raise_on_fail=False,
        )
        if not click_result.get("ok"):
            continue
        if time.time() >= read_deadline:
            break
        ready = _send_command_result(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=_deadline_timeout(read_deadline, min(max(timeout_sec, 2), 4)),
            command={
                "type": "wait_selector",
                "selector": RIGHT_PANEL_READY_SELECTOR,
                "timeout_ms": 1800,
                "visible_only": False,
            },
            raise_on_fail=False,
        )
        if not ready.get("ok"):
            continue
        if time.time() >= read_deadline:
            break
        try:
            candidate_html = _send_get_html(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=tab_id,
                timeout_sec=_deadline_timeout(read_deadline, min(max(timeout_sec, 2), 4)),
                selector=RIGHT_COLUMN_SELECTOR,
            )
        except RuntimeError:
            candidate_html = ""
        if _profile_panel_has_content(candidate_html):
            profile_html = candidate_html
            break
        _close_profile_card(server, token, client_id, tab_id)
        time.sleep(0.05)
    if not profile_html:
        return "—"

    if time.time() >= read_deadline:
        return "—"

    username = "—"
    try:
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
    return _ensure_group_dialog_url(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        group_url=group_url,
        timeout_sec=min(max(timeout_sec, 2), 8),
    )


def _get_current_opened_peer_id(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    timeout_sec: float,
    *,
    deadline: float | None = None,
) -> str:
    read_deadline = deadline if deadline is not None else time.time() + _effective_timeout_sec(timeout_sec)
    for selector in (
        "#RightColumn .Profile .Avatar[data-peer-id]",
        "#RightColumn .Avatar[data-peer-id]",
        ".MiddleHeader .ChatInfo .Avatar[data-peer-id]",
        ".ChatInfo .Avatar[data-peer-id]",
        ".chat-info .peer-title[data-peer-id]",
        ".sidebar-header .peer-title[data-peer-id]",
        "#RightColumn .profile-name .peer-title[data-peer-id]",
        "#column-right .profile-name .peer-title[data-peer-id]",
    ):
        if time.time() >= read_deadline:
            break
        result = _send_command_result(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=_remaining_timeout_sec(read_deadline),
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
    timeout_sec: float,
    *,
    deadline: float | None = None,
) -> str:
    read_deadline = deadline if deadline is not None else time.time() + _effective_timeout_sec(timeout_sec)
    for selector in (
        "#RightColumn .Profile .fullName",
        ".MiddleHeader .ChatInfo .fullName",
        ".ChatInfo .fullName",
        ".chat-info .peer-title",
        ".sidebar-header .peer-title",
        "#RightColumn .profile-name .peer-title",
        "#column-right .profile-name .peer-title",
    ):
        if time.time() >= read_deadline:
            break
        result = _send_command_result(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=_remaining_timeout_sec(read_deadline),
            command={"type": "extract_text", "selector": selector, "timeout_ms": 1200},
            raise_on_fail=False,
        )
        data = result.get("data") or {}
        value = data.get("text") if isinstance(data, dict) else ""
        text = _compact(str(value or ""))
        if text:
            return text
    return ""


def _read_current_opened_identity(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    timeout_sec: float,
    *,
    deadline: float | None = None,
) -> tuple[str, str]:
    read_deadline = deadline if deadline is not None else time.time() + _effective_timeout_sec(timeout_sec)
    peer_id, title = _read_helper_header_identity(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        timeout_sec=timeout_sec,
        deadline=read_deadline,
    )
    if not peer_id:
        peer_id = _get_current_opened_peer_id(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=timeout_sec,
            deadline=read_deadline,
        )
    if not title:
        title = _get_current_opened_title(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=timeout_sec,
            deadline=read_deadline,
        )
    return peer_id, title


def _wait_for_current_opened_identity(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    timeout_sec: float,
) -> tuple[str, str]:
    deadline = time.time() + _effective_timeout_sec(timeout_sec, minimum=0.6)
    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            return "", ""
        read_budget = max(min(remaining, 1.2), 0.4)
        peer_id, title = _read_current_opened_identity(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=read_budget,
            deadline=time.time() + read_budget,
        )
        if peer_id or title:
            return peer_id, title
        if time.time() >= deadline:
            return "", ""
        time.sleep(0.2)


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


def _extract_peer_id_from_helper_header_html(header_html: str) -> str:
    match = re.search(r'data-peer-id="(\d+)"', header_html or "", flags=re.I)
    return str(match.group(1) or "").strip() if match else ""


def _extract_title_from_helper_header_html(header_html: str) -> str:
    for pattern in (
        r'<h3[^>]*class="[^"]*fullName[^"]*"[^>]*>(.*?)</h3>',
        r'<span[^>]*class="[^"]*peer-title-inner[^"]*"[^>]*>(.*?)</span>',
        r'<span[^>]*class="[^"]*sender-title[^"]*"[^>]*>(.*?)</span>',
        r'<span[^>]*class="[^"]*peer-title[^"]*"[^>]*>(.*?)</span>',
        r'<img[^>]*class="[^"]*Avatar__media[^"]*"[^>]*alt="([^"]+)"',
        r'<div class="Avatar[^"]*"[^>]*title="([^"]+)"',
        r'<div class="Avatar[^"]*"[^>]*aria-label="([^"]+)"',
    ):
        match = re.search(pattern, header_html or "", flags=re.I | re.S)
        if not match:
            continue
        title = _compact(re.sub(r"<[^>]+>", " ", html_lib.unescape(match.group(1) or "")))
        if title:
            return title
    return ""


def _read_helper_header_identity(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    timeout_sec: float,
    *,
    deadline: float | None = None,
) -> tuple[str, str]:
    read_deadline = deadline if deadline is not None else time.time() + _effective_timeout_sec(timeout_sec)
    if time.time() >= read_deadline:
        return "", ""
    result = _send_command_result(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        timeout_sec=_remaining_timeout_sec(read_deadline),
        command={
            "type": "get_html",
            "selector": ".MiddleHeader, .chat-info, .sidebar-header",
            "timeout_ms": 1200,
        },
        raise_on_fail=False,
    )
    data = result.get("data") or {}
    header_html = str(data.get("html") or "") if isinstance(data, dict) else ""
    if not header_html:
        return "", ""
    return _extract_peer_id_from_helper_header_html(header_html), _extract_title_from_helper_header_html(header_html)


def _wait_for_helper_target_identity(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    expected_peer_id: str,
    expected_name: str,
    timeout_sec: float,
) -> bool:
    normalized_peer_id = str(expected_peer_id or "").strip()
    normalized_name = _compact(expected_name)
    if not normalized_peer_id and not normalized_name:
        return True

    deadline = time.time() + _effective_timeout_sec(timeout_sec, minimum=0.6)
    matching_route_streak = 0
    mismatching_route_streak = 0
    last_mismatching_route = ""
    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            return False

        route_fragment = ""
        if normalized_peer_id:
            route_fragment = _read_dialog_fragment_best_effort(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=tab_id,
                timeout_sec=min(max(remaining * 0.2, 0.25), 0.6),
            )
            if route_fragment == normalized_peer_id:
                matching_route_streak += 1
                mismatching_route_streak = 0
                last_mismatching_route = ""
            elif route_fragment:
                matching_route_streak = 0
                if route_fragment == last_mismatching_route:
                    mismatching_route_streak += 1
                else:
                    last_mismatching_route = route_fragment
                    mismatching_route_streak = 1
            else:
                matching_route_streak = 0
                mismatching_route_streak = 0
                last_mismatching_route = ""

        remaining = deadline - time.time()
        if remaining <= 0:
            return False
        read_budget = max(min(remaining, 0.55 if route_fragment else 0.85), 0.3)
        current_peer_id, current_title = _read_helper_header_identity(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=read_budget,
            deadline=time.time() + read_budget,
        )
        if normalized_peer_id and current_peer_id == normalized_peer_id:
            return True
        if normalized_name and current_title and _name_match(normalized_name, current_title):
            return True
        has_peer_conflict = bool(normalized_peer_id and current_peer_id and current_peer_id != normalized_peer_id)
        has_name_conflict = bool(normalized_name and current_title and not _name_match(normalized_name, current_title))
        if has_peer_conflict or has_name_conflict:
            matching_route_streak = 0
            mismatching_route_streak = 0
            last_mismatching_route = ""
        elif normalized_peer_id and matching_route_streak >= 2:
            return True
        elif normalized_peer_id and route_fragment and mismatching_route_streak >= 2:
            return False
        if time.time() >= deadline:
            return False
        time.sleep(0.08 if route_fragment else 0.12)


def _soft_confirm_helper_target_route(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    expected_peer_id: str,
    expected_name: str,
    timeout_sec: float,
) -> bool:
    normalized_peer_id = str(expected_peer_id or "").strip()
    normalized_name = _compact(expected_name)
    if not normalized_peer_id:
        return False

    route_fragment = _read_dialog_fragment_best_effort(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        timeout_sec=min(max(timeout_sec, 0.3), 0.8),
    )
    if route_fragment != normalized_peer_id:
        return False

    current_peer_id, current_title = _read_helper_header_identity(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        timeout_sec=min(max(timeout_sec, 0.3), 0.8),
    )
    if current_peer_id and current_peer_id != normalized_peer_id:
        return False
    if normalized_name and current_title and not _name_match(normalized_name, current_title):
        return False
    return True


def _trace_token(value: str, *, limit: int = 80) -> str:
    text = _compact(str(value or ""))
    if not text:
        return "—"
    text = text.replace(" ", "_")
    return text[:limit]


def _trace_helper_route_probe(
    *,
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    expected_peer_id: str,
    expected_name: str,
    timeout_sec: float,
    step: str,
) -> None:
    if not CHAT_MENTION_TRACE:
        return

    started_at = time.time()
    target_peer_id = str(expected_peer_id or "").strip()
    target_name = _compact(expected_name)
    read_timeout_sec = min(max(float(timeout_sec), 0.3), 0.8)

    page_url = _get_page_url_best_effort(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        timeout_sec=read_timeout_sec,
    )
    page_fragment = _dialog_fragment_from_url(page_url)

    tab_url, tab_title = _get_tab_meta_best_effort(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        timeout_sec=read_timeout_sec,
    )
    tab_fragment = _dialog_fragment_from_url(tab_url)

    header_peer_id, header_title = _read_helper_header_identity(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        timeout_sec=read_timeout_sec,
    )

    route_match = int(bool(target_peer_id and (page_fragment == target_peer_id or tab_fragment == target_peer_id)))
    header_match = int(
        bool(
            (target_peer_id and header_peer_id == target_peer_id)
            or (target_name and header_title and _name_match(target_name, header_title))
        )
    )
    _mention_trace_step(
        f"peer:{target_peer_id or '—'}",
        step,
        started_at,
        tab_id=tab_id,
        target=target_peer_id or "—",
        page=page_fragment or "—",
        tab=tab_fragment or "—",
        tab_title=_trace_token(tab_title),
        header_peer=header_peer_id or "—",
        header_title=_trace_token(header_title),
        route_match=route_match,
        header_match=header_match,
    )


def _match_unique_member_peer_id_by_title(
    members: list[dict[str, str]],
    title: str,
) -> str:
    title_key = _name_key(title)
    if len(title_key) < 5:
        return ""
    matched_peer_ids = [
        str(item.get("peer_id") or "").strip()
        for item in members
        if str(item.get("peer_id") or "").strip()
        and _name_key(str(item.get("name") or "")) == title_key
    ]
    unique_peer_ids = sorted({peer_id for peer_id in matched_peer_ids if peer_id})
    return unique_peer_ids[0] if len(unique_peer_ids) == 1 else ""


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


def _extract_username_from_chat_author_block(block_html: str) -> str:
    author_fragments: list[str] = []
    for pattern in (
        r'<span class="sender-title">(.*?)</span>',
        r'<span class="message-title-name">(.*?)</span>',
        r'<span class="peer-title-inner"[^>]*>(.*?)</span>',
        r'<span class="peer-title(?: bubble-name-first)?[^"]*"[^>]*>(.*?)</span>',
        r'<img[^>]*class="[^"]*Avatar__media[^"]*"[^>]*alt="([^"]+)"',
        r'<div class="Avatar[^"]*"[^>]*title="([^"]+)"',
        r'<div class="Avatar[^"]*"[^>]*aria-label="([^"]+)"',
    ):
        author_fragments.extend(re.findall(pattern, block_html, flags=re.I | re.S))

    for fragment in author_fragments:
        username = _extract_username(fragment)
        if username != "—":
            return username
    return "—"


def _extract_username_from_profile_html(profile_html: str) -> str:
    for block in re.findall(r'<div class="multiline-item">(.*?)</div>', profile_html, flags=re.S):
        subtitle_match = re.search(r'<span class="subtitle">(.*?)</span>', block, flags=re.I | re.S)
        subtitle = _compact(subtitle_match.group(1) if subtitle_match else "").lower()
        if "username" not in subtitle and "имя пользователя" not in subtitle:
            continue
        title_match = re.search(r'<span class="title[^"]*"[^>]*>(.*?)</span>', block, flags=re.I | re.S)
        if not title_match:
            continue
        username = _normalize_username(title_match.group(1))
        if username != "—":
            return username

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


def _detect_info_members_view_kind(html_payload: str) -> str:
    if not html_payload:
        return "unknown"
    has_members_list = (
        'class="content members-list"' in html_payload
        or 'class="members-list"' in html_payload
    )
    if not has_members_list:
        return "none"
    has_profile_shell = 'class="profile-info"' in html_payload or 'class="ProfileInfo' in html_payload
    has_shared_media = 'class="shared-media"' in html_payload
    has_tabs = 'class="SquareTabList' in html_payload
    has_group_info_shell = 'class="ChatExtra"' in html_payload or '<h3 class="title">Group Info</h3>' in html_payload
    if has_profile_shell and has_shared_media and has_tabs and has_group_info_shell:
        return "preview"
    return "list"


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
        if current.get("username") == "—" and username and username != "—":
            current["username"] = username
        if current.get("role") == "—" and item.get("role") and item.get("role") != "—":
            current["role"] = str(item["role"])
        if current.get("status") == "—" and item.get("status") and item.get("status") != "—":
            current["status"] = str(item["status"])

    return [merged[key] for key in order]


def _seed_username_to_peer(members: list[dict[str, str]]) -> dict[str, str]:
    username_to_peer: dict[str, str] = {}
    for item in members:
        peer_id = str(item.get("peer_id") or "").strip()
        username = _normalize_username(str(item.get("username") or ""))
        if not peer_id or username == "—":
            continue
        username_to_peer.setdefault(username.lower(), peer_id)
    return username_to_peer


def _merge_identity_username(
    *,
    username_to_peer: dict[str, str],
    peer_to_username: dict[str, str],
    peer_id: str,
    username: str,
) -> None:
    normalized_peer_id = str(peer_id or "").strip()
    normalized_username = _normalize_username(username)
    if not normalized_peer_id or normalized_username == "—":
        return

    previous_username = _normalize_username(str(peer_to_username.get(normalized_peer_id) or ""))
    if (
        previous_username != "—"
        and previous_username.lower() != normalized_username.lower()
        and username_to_peer.get(previous_username.lower()) == normalized_peer_id
    ):
        username_to_peer.pop(previous_username.lower(), None)

    existing_peer = username_to_peer.get(normalized_username.lower())
    if existing_peer and existing_peer != normalized_peer_id:
        return

    username_to_peer[normalized_username.lower()] = normalized_peer_id
    peer_to_username[normalized_peer_id] = normalized_username


def _normalize_identity_history_maps(
    username_to_peer_raw: dict[str, Any] | None,
    peer_to_username_raw: dict[str, Any] | None,
) -> tuple[dict[str, str], dict[str, str]]:
    username_to_peer = {
        normalized_username.lower(): str(value).strip()
        for key, value in ((username_to_peer_raw or {}).items() if isinstance(username_to_peer_raw, dict) else [])
        for normalized_username in [_normalize_username(str(key))]
        if normalized_username != "—" and str(value).strip()
    }
    peer_to_username = {
        str(key).strip(): _normalize_username(str(value))
        for key, value in ((peer_to_username_raw or {}).items() if isinstance(peer_to_username_raw, dict) else [])
        if str(key).strip() and _normalize_username(str(value)) != "—"
    }
    return username_to_peer, peer_to_username


def _parse_iso_datetime_utc(value: str) -> dt.datetime:
    text = str(value or "").strip()
    if not text:
        return dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _identity_history_updated_at(value: str) -> dt.datetime:
    return _parse_iso_datetime_utc(value)


def _load_identity_history_source(path: Path | None) -> tuple[dt.datetime, dict[str, str], dict[str, str]]:
    if path is None or not path.exists():
        return dt.datetime.min.replace(tzinfo=dt.timezone.utc), {}, {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dt.datetime.min.replace(tzinfo=dt.timezone.utc), {}, {}
    if not isinstance(payload, dict):
        return dt.datetime.min.replace(tzinfo=dt.timezone.utc), {}, {}
    username_to_peer, peer_to_username = _normalize_identity_history_maps(
        payload.get("username_to_peer"),
        payload.get("peer_to_username"),
    )
    return _identity_history_updated_at(str(payload.get("updated_at") or "")), username_to_peer, peer_to_username


def _iter_identity_history_records(
    username_to_peer: dict[str, str],
    peer_to_username: dict[str, str],
) -> list[tuple[str, str]]:
    records: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for peer_id, username in peer_to_username.items():
        normalized_peer_id = str(peer_id or "").strip()
        normalized_username = _normalize_username(str(username))
        if not normalized_peer_id or normalized_username == "—":
            continue
        key = (normalized_peer_id, normalized_username.lower())
        if key in seen:
            continue
        seen.add(key)
        records.append((normalized_peer_id, normalized_username))
    for username, peer_id in username_to_peer.items():
        normalized_peer_id = str(peer_id or "").strip()
        normalized_username = _normalize_username(str(username))
        if not normalized_peer_id or normalized_username == "—":
            continue
        key = (normalized_peer_id, normalized_username.lower())
        if key in seen:
            continue
        seen.add(key)
        records.append((normalized_peer_id, normalized_username))
    return records


def _merge_identity_history_fill_missing(
    *,
    primary_username_to_peer: dict[str, str],
    primary_peer_to_username: dict[str, str],
    secondary_username_to_peer: dict[str, str],
    secondary_peer_to_username: dict[str, str],
) -> tuple[dict[str, str], dict[str, str]]:
    merged_username_to_peer = dict(primary_username_to_peer)
    merged_peer_to_username = dict(primary_peer_to_username)
    for peer_id, username in _iter_identity_history_records(secondary_username_to_peer, secondary_peer_to_username):
        if peer_id in merged_peer_to_username:
            continue
        key = username.lower()
        if key in merged_username_to_peer:
            continue
        merged_peer_to_username[peer_id] = username
        merged_username_to_peer[key] = peer_id
    return merged_username_to_peer, merged_peer_to_username


def _identity_history_from_archive_source(
    archive_dir: Path | None,
    group_url: str,
) -> tuple[dt.datetime, dict[str, str], dict[str, str]]:
    if archive_dir is None or not archive_dir.exists():
        return dt.datetime.min.replace(tzinfo=dt.timezone.utc), {}, {}

    archive_state_path = _default_identity_history_path(archive_dir, group_url)
    if archive_state_path is not None and archive_state_path.exists():
        updated_at, username_to_peer, peer_to_username = _load_identity_history_source(archive_state_path)
        if username_to_peer or peer_to_username:
            return updated_at, username_to_peer, peer_to_username

    target_fragment = _dialog_fragment_from_url(group_url)
    if not target_fragment:
        return dt.datetime.min.replace(tzinfo=dt.timezone.utc), {}, {}

    username_to_peer: dict[str, str] = {}
    peer_to_username: dict[str, str] = {}
    for sidecar_path in sorted(archive_dir.glob("*_usernames_json.json")):
        try:
            payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        payload_group_url = str(payload.get("group_url") or "").strip()
        if _dialog_fragment_from_url(payload_group_url) != target_fragment:
            continue
        rows = payload.get("rows") or []
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            _merge_identity_username(
                username_to_peer=username_to_peer,
                peer_to_username=peer_to_username,
                peer_id=str(row.get("peer_id") or "").strip(),
                username=str(row.get("username") or ""),
            )
    return dt.datetime.min.replace(tzinfo=dt.timezone.utc), username_to_peer, peer_to_username


def _identity_history_from_archive(
    archive_dir: Path | None,
    group_url: str,
) -> tuple[dict[str, str], dict[str, str]]:
    _updated_at, username_to_peer, peer_to_username = _identity_history_from_archive_source(archive_dir, group_url)
    return username_to_peer, peer_to_username


def _build_identity_history_payload(
    *,
    members: list[dict[str, str]],
    historical_username_to_peer: dict[str, str] | None = None,
    historical_peer_to_username: dict[str, str] | None = None,
) -> dict[str, Any]:
    username_to_peer = {
        normalized_username.lower(): str(value).strip()
        for key, value in (historical_username_to_peer or {}).items()
        for normalized_username in [_normalize_username(str(key))]
        if normalized_username != "—" and str(value).strip()
    }
    peer_to_username = {
        str(key).strip(): _normalize_username(str(value))
        for key, value in (historical_peer_to_username or {}).items()
        if str(key).strip() and _normalize_username(str(value)) != "—"
    }

    for item in members:
        _merge_identity_username(
            username_to_peer=username_to_peer,
            peer_to_username=peer_to_username,
            peer_id=str(item.get("peer_id") or "").strip(),
            username=str(item.get("username") or ""),
        )

    return {
        "version": 1,
        "updated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "username_to_peer": dict(sorted(username_to_peer.items())),
        "peer_to_username": dict(sorted(peer_to_username.items())),
    }


def _load_identity_history(
    history_path: Path | None,
    *,
    archive_dir: Path | None = None,
    group_url: str = "",
) -> tuple[dict[str, str], dict[str, str]]:
    archive_updated_at, archive_username_to_peer, archive_peer_to_username = _identity_history_from_archive_source(
        archive_dir,
        group_url,
    )
    if history_path is None:
        return archive_username_to_peer, archive_peer_to_username
    if not history_path.exists():
        return archive_username_to_peer, archive_peer_to_username

    file_updated_at, file_username_to_peer, file_peer_to_username = _load_identity_history_source(history_path)
    if not archive_username_to_peer and not archive_peer_to_username:
        return file_username_to_peer, file_peer_to_username
    if not file_username_to_peer and not file_peer_to_username:
        return archive_username_to_peer, archive_peer_to_username

    archive_state_path = _default_identity_history_path(archive_dir, group_url)
    if archive_state_path is not None and history_path == archive_state_path:
        return file_username_to_peer, file_peer_to_username

    if archive_updated_at >= file_updated_at:
        return _merge_identity_history_fill_missing(
            primary_username_to_peer=archive_username_to_peer,
            primary_peer_to_username=archive_peer_to_username,
            secondary_username_to_peer=file_username_to_peer,
            secondary_peer_to_username=file_peer_to_username,
        )
    return _merge_identity_history_fill_missing(
        primary_username_to_peer=file_username_to_peer,
        primary_peer_to_username=file_peer_to_username,
        secondary_username_to_peer=archive_username_to_peer,
        secondary_peer_to_username=archive_peer_to_username,
    )


def _save_identity_history(
    history_path: Path | None,
    *,
    members: list[dict[str, str]],
    historical_username_to_peer: dict[str, str] | None = None,
    historical_peer_to_username: dict[str, str] | None = None,
) -> None:
    if history_path is None:
        return
    payload = _build_identity_history_payload(
        members=members,
        historical_username_to_peer=historical_username_to_peer,
        historical_peer_to_username=historical_peer_to_username,
    )
    try:
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"WARN: cannot write identity history: {exc}", file=sys.stderr)


def _load_discovery_state(discovery_state_path: Path | None) -> dict[str, Any]:
    if discovery_state_path is None or not discovery_state_path.exists():
        return {
            "version": 2,
            "updated_at": "",
            "seen_view_signatures": [],
            "seen_peer_ids": [],
            "peer_states": {},
            "mention_candidate_states": {},
        }
    try:
        payload = json.loads(discovery_state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "version": 2,
            "updated_at": "",
            "seen_view_signatures": [],
            "seen_peer_ids": [],
            "peer_states": {},
            "mention_candidate_states": {},
        }
    if not isinstance(payload, dict):
        payload = {}
    seen_view_signatures_raw = payload.get("seen_view_signatures")
    seen_peer_ids_raw = payload.get("seen_peer_ids")
    peer_states_raw = payload.get("peer_states")
    mention_candidate_states_raw = payload.get("mention_candidate_states")
    seen_view_signatures = []
    if isinstance(seen_view_signatures_raw, list):
        seen_view_signatures = [str(value).strip() for value in seen_view_signatures_raw if str(value).strip()]
    seen_peer_ids = []
    if isinstance(seen_peer_ids_raw, list):
        seen_peer_ids = [str(value).strip() for value in seen_peer_ids_raw if str(value).strip()]
    peer_states: dict[str, dict[str, Any]] = {}
    if isinstance(peer_states_raw, dict):
        for peer_id, state in peer_states_raw.items():
            normalized_peer_id = str(peer_id or "").strip()
            if not normalized_peer_id or not isinstance(state, dict):
                continue
            peer_states[normalized_peer_id] = {
                "attempt_count": max(int(state.get("attempt_count") or 0), 0),
                "success_count": max(int(state.get("success_count") or 0), 0),
                "failure_count": max(int(state.get("failure_count") or 0), 0),
                "last_outcome": str(state.get("last_outcome") or "").strip(),
                "last_attempted_at": str(state.get("last_attempted_at") or "").strip(),
                "last_username": _normalize_username(str(state.get("last_username") or "")),
                "cooldown_until": str(state.get("cooldown_until") or "").strip(),
            }
    mention_candidate_states: dict[str, dict[str, Any]] = {}
    if isinstance(mention_candidate_states_raw, dict):
        for username, state in mention_candidate_states_raw.items():
            mention_key = _normalize_username_from_mention_input(str(username or "")).lower()
            if mention_key == "—" or not isinstance(state, dict):
                continue
            mention_candidate_states[mention_key] = {
                "attempt_count": max(int(state.get("attempt_count") or 0), 0),
                "success_count": max(int(state.get("success_count") or 0), 0),
                "failure_count": max(int(state.get("failure_count") or 0), 0),
                "last_outcome": str(state.get("last_outcome") or "").strip(),
                "last_attempted_at": str(state.get("last_attempted_at") or "").strip(),
                "last_peer_id": str(state.get("last_peer_id") or "").strip(),
                "cooldown_until": str(state.get("cooldown_until") or "").strip(),
            }
    return {
        "version": 2,
        "updated_at": str(payload.get("updated_at") or ""),
        "seen_view_signatures": seen_view_signatures[-400:],
        "seen_peer_ids": seen_peer_ids[-5000:],
        "peer_states": peer_states,
        "mention_candidate_states": mention_candidate_states,
    }


def _discovery_peer_states(discovery_state: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(discovery_state, dict):
        return {}
    value = discovery_state.get("peer_states")
    return value if isinstance(value, dict) else {}


def _discovery_mention_states(discovery_state: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(discovery_state, dict):
        return {}
    value = discovery_state.get("mention_candidate_states")
    return value if isinstance(value, dict) else {}


def _discovery_mention_key(username: str) -> str:
    normalized_username = _normalize_username_from_mention_input(username)
    return normalized_username.lower() if normalized_username != "—" else ""


def _discovery_mention_state(discovery_state: dict[str, Any] | None, username: str) -> dict[str, Any]:
    mention_key = _discovery_mention_key(username)
    if not mention_key:
        return {}
    return dict(_discovery_mention_states(discovery_state).get(mention_key) or {})


def _discovery_mention_cooldown_until(discovery_state: dict[str, Any] | None, username: str) -> dt.datetime:
    state = _discovery_mention_state(discovery_state, username)
    return _parse_iso_datetime_utc(str(state.get("cooldown_until") or ""))


def _discovery_mention_in_cooldown(
    discovery_state: dict[str, Any] | None,
    username: str,
    *,
    now: dt.datetime | None = None,
) -> bool:
    reference = now or dt.datetime.now(dt.timezone.utc)
    return _discovery_mention_cooldown_until(discovery_state, username) > reference


def _discovery_seen_peer_ids(discovery_state: dict[str, Any] | None) -> set[str]:
    if not isinstance(discovery_state, dict):
        return set()
    values = discovery_state.get("seen_peer_ids") or []
    if not isinstance(values, list):
        return set()
    return {str(value).strip() for value in values if str(value).strip()}


def _discovery_note_visible_peers(discovery_state: dict[str, Any] | None, peer_ids: set[str]) -> None:
    if not isinstance(discovery_state, dict) or not peer_ids:
        return
    current = list(discovery_state.get("seen_peer_ids") or [])
    seen = {str(value).strip() for value in current if str(value).strip()}
    for peer_id in sorted(peer_ids):
        normalized_peer_id = str(peer_id or "").strip()
        if not normalized_peer_id or normalized_peer_id in seen:
            continue
        seen.add(normalized_peer_id)
        current.append(normalized_peer_id)
    discovery_state["seen_peer_ids"] = current[-5000:]


def _discovery_note_view_signature(discovery_state: dict[str, Any] | None, peer_ids: set[str]) -> str:
    if not isinstance(discovery_state, dict) or not peer_ids:
        return ""
    signature = ",".join(sorted(str(peer_id).strip() for peer_id in peer_ids if str(peer_id).strip()))
    if not signature:
        return ""
    current = list(discovery_state.get("seen_view_signatures") or [])
    if signature not in current:
        current.append(signature)
    discovery_state["seen_view_signatures"] = current[-400:]
    return signature


def _discovery_peer_state(discovery_state: dict[str, Any] | None, peer_id: str) -> dict[str, Any]:
    normalized_peer_id = str(peer_id or "").strip()
    if not normalized_peer_id:
        return {}
    return dict(_discovery_peer_states(discovery_state).get(normalized_peer_id) or {})


def _discovery_peer_cooldown_until(discovery_state: dict[str, Any] | None, peer_id: str) -> dt.datetime:
    state = _discovery_peer_state(discovery_state, peer_id)
    return _parse_iso_datetime_utc(str(state.get("cooldown_until") or ""))


def _discovery_peer_in_cooldown(
    discovery_state: dict[str, Any] | None,
    peer_id: str,
    *,
    now: dt.datetime | None = None,
) -> bool:
    reference = now or dt.datetime.now(dt.timezone.utc)
    return _discovery_peer_cooldown_until(discovery_state, peer_id) > reference


def _discovery_failure_cooldown(
    outcome: str,
    failure_count: int,
) -> dt.timedelta:
    normalized = str(outcome or "").strip().lower()
    failures = max(int(failure_count), 1)
    if normalized in {"group_restore_failed", "context_missing"}:
        hours = 1
    elif "menu_missing" in normalized or "delivery_failure" in normalized:
        hours = min(12, 2 * failures)
    else:
        hours = min(24, 3 * failures)
    return dt.timedelta(hours=max(hours, 1))


def _discovery_note_peer_attempt(
    discovery_state: dict[str, Any] | None,
    *,
    peer_id: str,
    outcome: str,
    username: str = "—",
) -> None:
    if not isinstance(discovery_state, dict):
        return
    normalized_peer_id = str(peer_id or "").strip()
    if not normalized_peer_id:
        return
    peer_states = _discovery_peer_states(discovery_state)
    state = dict(peer_states.get(normalized_peer_id) or {})
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    normalized_username = _normalize_username(username)
    normalized_outcome = str(outcome or "").strip()

    state["attempt_count"] = max(int(state.get("attempt_count") or 0), 0) + 1
    state["last_attempted_at"] = now.isoformat()
    state["last_outcome"] = normalized_outcome

    if normalized_username != "—":
        state["success_count"] = max(int(state.get("success_count") or 0), 0) + 1
        state["last_username"] = normalized_username
        state["cooldown_until"] = ""
    else:
        failure_count = max(int(state.get("failure_count") or 0), 0) + 1
        state["failure_count"] = failure_count
        state["cooldown_until"] = (now + _discovery_failure_cooldown(normalized_outcome, failure_count)).isoformat()

    peer_states[normalized_peer_id] = state
    discovery_state["peer_states"] = peer_states


def _discovery_note_mention_attempt(
    discovery_state: dict[str, Any] | None,
    *,
    username: str,
    outcome: str,
    peer_id: str = "",
) -> None:
    if not isinstance(discovery_state, dict):
        return
    mention_key = _discovery_mention_key(username)
    if not mention_key:
        return
    mention_states = _discovery_mention_states(discovery_state)
    state = dict(mention_states.get(mention_key) or {})
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    normalized_outcome = str(outcome or "").strip()
    normalized_peer_id = str(peer_id or "").strip()

    state["attempt_count"] = max(int(state.get("attempt_count") or 0), 0) + 1
    state["last_attempted_at"] = now.isoformat()
    state["last_outcome"] = normalized_outcome
    state["last_peer_id"] = normalized_peer_id

    if "success" in normalized_outcome:
        state["success_count"] = max(int(state.get("success_count") or 0), 0) + 1
        state["cooldown_until"] = ""
    else:
        failure_count = max(int(state.get("failure_count") or 0), 0) + 1
        state["failure_count"] = failure_count
        state["cooldown_until"] = (now + _discovery_failure_cooldown(normalized_outcome, failure_count)).isoformat()

    mention_states[mention_key] = state
    discovery_state["mention_candidate_states"] = mention_states


def _discovery_target_priority(
    item: dict[str, str],
    *,
    discovery_state: dict[str, Any] | None,
    seen_peer_ids_before_step: set[str],
    now: dt.datetime,
) -> tuple[int, int, int, str]:
    peer_id = str(item.get("peer_id") or "").strip()
    state = _discovery_peer_state(discovery_state, peer_id)
    unseen_priority = 0 if peer_id and peer_id not in seen_peer_ids_before_step else 1
    cooldown_priority = 1 if _discovery_peer_in_cooldown(discovery_state, peer_id, now=now) else 0
    attempt_priority = max(int(state.get("attempt_count") or 0), 0)
    failure_priority = max(int(state.get("failure_count") or 0), 0)
    return (cooldown_priority, unseen_priority, attempt_priority + failure_priority, peer_id)


def _write_stats_output(stats_output_path: Path | None, payload: dict[str, Any]) -> None:
    if stats_output_path is None:
        return
    try:
        stats_output_path.parent.mkdir(parents=True, exist_ok=True)
        stats_output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"WARN: cannot write stats output: {exc}", file=sys.stderr)


def _count_members_with_username(members: list[dict[str, str]]) -> int:
    return sum(1 for item in members if _normalize_username(str(item.get("username") or "").strip()) != "—")


def _build_export_stats_payload(
    *,
    status: str,
    group_url: str,
    source: str,
    source_label: str,
    out_path: Path,
    members: list[dict[str, str]] | None = None,
    info_stats: dict[str, Any] | None = None,
    chat_stats: dict[str, Any] | None = None,
    deep_usernames: bool = False,
    max_members: int = 0,
    deep_attempted_total: int = 0,
    deep_updated_total: int = 0,
    history_backfilled_total: int = 0,
    output_usernames_restored_total: int = 0,
    output_usernames_cleared_total: int = 0,
    error: str = "",
) -> dict[str, Any]:
    members = list(members or [])
    info_stats = dict(info_stats or {})
    chat_stats = dict(chat_stats or {})
    members_total = len(members)
    members_with_username = _count_members_with_username(members)
    payload: dict[str, Any] = {
        "status": status,
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "group_url": group_url,
        "source": source,
        "source_label": source_label,
        "output": str(out_path),
        "deep_usernames": bool(deep_usernames),
        "max_members": int(max_members),
        "members_total": members_total,
        "members_with_username": members_with_username,
        "members_without_username": max(members_total - members_with_username, 0),
        "deep_attempted_total": int(deep_attempted_total),
        "deep_updated_total": int(deep_updated_total),
        "history_backfilled_total": int(history_backfilled_total),
        "output_usernames_restored_total": int(output_usernames_restored_total),
        "output_usernames_cleared_total": int(output_usernames_cleared_total),
        "info_stats": info_stats,
        "chat_stats": chat_stats,
    }
    if error:
        payload["error"] = error
    return payload


def _save_discovery_state(discovery_state_path: Path | None, discovery_state: dict[str, Any] | None) -> None:
    if discovery_state_path is None or discovery_state is None:
        return
    discovery_state_path.parent.mkdir(parents=True, exist_ok=True)
    peer_states = _discovery_peer_states(discovery_state)
    serialized_peer_states = {
        peer_id: {
            "attempt_count": max(int(state.get("attempt_count") or 0), 0),
            "success_count": max(int(state.get("success_count") or 0), 0),
            "failure_count": max(int(state.get("failure_count") or 0), 0),
            "last_outcome": str(state.get("last_outcome") or "").strip(),
            "last_attempted_at": str(state.get("last_attempted_at") or "").strip(),
            "last_username": _normalize_username(str(state.get("last_username") or "")),
            "cooldown_until": str(state.get("cooldown_until") or "").strip(),
        }
        for peer_id, state in peer_states.items()
        if str(peer_id or "").strip()
    }
    mention_candidate_states = _discovery_mention_states(discovery_state)
    serialized_mention_candidate_states = {
        mention_key: {
            "attempt_count": max(int(state.get("attempt_count") or 0), 0),
            "success_count": max(int(state.get("success_count") or 0), 0),
            "failure_count": max(int(state.get("failure_count") or 0), 0),
            "last_outcome": str(state.get("last_outcome") or "").strip(),
            "last_attempted_at": str(state.get("last_attempted_at") or "").strip(),
            "last_peer_id": str(state.get("last_peer_id") or "").strip(),
            "cooldown_until": str(state.get("cooldown_until") or "").strip(),
        }
        for mention_key, state in mention_candidate_states.items()
        if _discovery_mention_key(str(mention_key or ""))
    }
    payload = {
        "version": 2,
        "updated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "seen_view_signatures": list((discovery_state.get("seen_view_signatures") or []))[-400:],
        "seen_peer_ids": list((discovery_state.get("seen_peer_ids") or []))[-5000:],
        "peer_states": serialized_peer_states,
        "mention_candidate_states": serialized_mention_candidate_states,
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


def _backfill_usernames_from_history(
    *,
    members: list[dict[str, str]],
    historical_username_to_peer: dict[str, str] | None = None,
    historical_peer_to_username: dict[str, str] | None = None,
) -> tuple[int, int]:
    if not members or not historical_peer_to_username:
        return 0, 0

    members_by_peer = {
        str(item.get("peer_id") or "").strip(): item
        for item in members
        if str(item.get("peer_id") or "").strip()
    }
    username_to_peer = _seed_username_to_peer(members)
    updated = 0
    conflicts = 0

    for peer_id, historical_username in historical_peer_to_username.items():
        member = members_by_peer.get(str(peer_id).strip())
        if member is None:
            continue
        if _normalize_username(str(member.get("username") or "").strip()) != "—":
            continue
        assigned, conflict_value, reason = _assign_username_if_unique(
            members_by_peer=members_by_peer,
            username_to_peer=username_to_peer,
            peer_id=str(peer_id).strip(),
            username=str(historical_username or "").strip(),
            historical_username_to_peer=historical_username_to_peer,
            historical_peer_to_username=historical_peer_to_username,
        )
        if assigned:
            updated += 1
            continue
        if reason not in {"empty", "missing_member"}:
            conflicts += 1
            _log_username_assignment_conflict(str(historical_username or "").strip(), str(peer_id).strip(), conflict_value, reason)

    return updated, conflicts


def _sanitize_member_usernames_for_output(
    *,
    members: list[dict[str, str]],
    historical_username_to_peer: dict[str, str] | None = None,
    historical_peer_to_username: dict[str, str] | None = None,
) -> tuple[int, int]:
    if not members:
        return 0, 0

    normalized_peer_history = {
        str(peer_id).strip(): _normalize_username(str(username))
        for peer_id, username in (historical_peer_to_username or {}).items()
        if str(peer_id).strip() and _normalize_username(str(username)) != "—"
    }
    username_to_peer: dict[str, str] = {}
    restored = 0
    cleared = 0

    def can_use_username(peer_id: str, username: str) -> tuple[bool, str | None, str | None]:
        normalized = _normalize_username(str(username or ""))
        if normalized == "—":
            return False, "", "empty"
        key = normalized.lower()
        historical_owner = str((historical_username_to_peer or {}).get(key) or "").strip()
        if historical_owner and historical_owner != peer_id:
            return False, historical_owner, "historical_username_owner"
        existing_peer = username_to_peer.get(key)
        if existing_peer and existing_peer != peer_id:
            return False, existing_peer, "runtime_duplicate"
        return True, None, None

    for item in members:
        peer_id = str(item.get("peer_id") or "").strip()
        current_username = _normalize_username(str(item.get("username") or ""))
        historical_username = normalized_peer_history.get(peer_id, "—")
        if historical_username != "—" and current_username != "—" and historical_username.lower() != current_username.lower():
            current_ok, _, _ = can_use_username(peer_id, current_username)
            if not current_ok:
                historical_ok, _, _ = can_use_username(peer_id, historical_username)
                if historical_ok:
                    item["username"] = historical_username
                    current_username = historical_username
                    restored += 1
                else:
                    item["username"] = "—"
                    cleared += 1
                    continue

        if current_username == "—":
            continue

        current_ok, _, _ = can_use_username(peer_id, current_username)
        if not current_ok:
            if historical_username != "—" and historical_username.lower() != current_username.lower():
                historical_ok, _, _ = can_use_username(peer_id, historical_username)
                if historical_ok:
                    item["username"] = historical_username
                    current_username = historical_username
                    restored += 1
                else:
                    item["username"] = "—"
                    cleared += 1
                    continue
            else:
                item["username"] = "—"
                cleared += 1
                continue

        username_to_peer[current_username.lower()] = peer_id

    return restored, cleared


def _parse_chat_members(html_payload: str) -> list[dict[str, str]]:
    members: list[dict[str, str]] = []
    seen_peer_ids: set[str] = set()

    # Telegram Web markup for sender labels varies between releases.
    # Current releases wrap grouped user messages with `sender-group-container`
    # and expose the author via the leading Avatar + sender-title block.
    for match in re.finditer(r'<div id="message-group-[^"]+" class="sender-group-container[^"]*">', html_payload, flags=re.S):
        block_html = html_payload[match.start() : match.start() + 3500]
        peer_match = re.search(r'<div class="Avatar[^"]*" data-peer-id="([^"]+)"', block_html)
        if not peer_match:
            continue
        peer_id = peer_match.group(1)
        if peer_id.startswith("-") or peer_id in seen_peer_ids:
            continue

        name = ""
        sender_title = re.search(r'<span class="sender-title">(.*?)</span>', block_html, flags=re.S)
        if sender_title:
            name = _compact(sender_title.group(1))
        if not name:
            title_name = re.search(r'<span class="message-title-name">(.*?)</span>', block_html, flags=re.S)
            if title_name:
                name = _compact(title_name.group(1))
        if not name:
            avatar_name = re.search(r'<img[^>]*class="[^"]*Avatar__media[^"]*"[^>]*alt="([^"]+)"', block_html, flags=re.S)
            if avatar_name:
                name = _compact(avatar_name.group(1))
        if not name:
            continue

        role = "—"
        role_match = re.search(r'<[^>]+class="[^"]*admin-title-badge[^"]*"[^>]*>(.*?)</[^>]+>', block_html, flags=re.S)
        if role_match:
            parsed_role = _compact(role_match.group(1))
            if parsed_role:
                role = parsed_role

        members.append(
            {
                "peer_id": peer_id,
                "name": name,
                "status": "из чата",
                "role": role,
                "username": _extract_username_from_chat_author_block(block_html),
            }
        )
        seen_peer_ids.add(peer_id)

    sender_openings: list[tuple[int, str]] = []
    sender_patterns = (
        r'<(?:div|span)([^>]*)class="(?=[^"]*colored-name)(?=[^"]*floating-part)[^"]*"([^>]*)>',
        r'<span([^>]*)class="(?=[^"]*peer-title)(?=[^"]*bubble-name-first)[^"]*"([^>]*)>',
    )
    for pattern in sender_patterns:
        for match in re.finditer(pattern, html_payload, flags=re.S):
            attrs = f"{match.group(1)} {match.group(2)}"
            sender_openings.append((match.start(), attrs))
    sender_openings.sort(key=lambda item: item[0])

    for start_pos, attrs in sender_openings:
        peer_match = re.search(r'data-peer-id="([^"]+)"', attrs)
        if not peer_match:
            continue
        peer_id = peer_match.group(1)
        if peer_id.startswith("-") or peer_id in seen_peer_ids:
            continue

        block_html = html_payload[start_pos : start_pos + 1800]
        name = ""
        with_icons = re.search(
            r'<span class="(?=[^"]*peer-title)(?=[^"]*with-icons)[^"]*"[^>]*>(.*?)</span>',
            block_html,
            flags=re.S,
        )
        if with_icons:
            inner = re.search(r'<span class="peer-title-inner"[^>]*>(.*?)</span>', with_icons.group(1), flags=re.S)
            name = _compact(inner.group(1) if inner else with_icons.group(1))
        else:
            plain = re.search(r'<span class="peer-title(?: bubble-name-first)?"[^>]*>(.*?)</span>', block_html, flags=re.S)
            if plain:
                name = _compact(plain.group(1))
            else:
                inner = re.search(r'<span[^>]*>(.*?)</span>', block_html, flags=re.S)
                if inner and "peer-title" in attrs:
                    name = _compact(inner.group(1))

        if not name:
            continue

        role = "—"
        role_match = re.search(r'<span class="bubble-name-rank"[^>]*>(.*?)</span>', block_html, flags=re.S)
        if role_match:
            parsed_role = _compact(role_match.group(1))
            if parsed_role:
                role = parsed_role

        members.append(
            {
                "peer_id": peer_id,
                "name": name,
                "status": "из чата",
                "role": role,
                "username": _extract_username_from_chat_author_block(block_html),
            }
        )
        seen_peer_ids.add(peer_id)

    return members


def _member_from_sticky_author_payload(value: dict[str, Any] | None) -> dict[str, str] | None:
    if not isinstance(value, dict) or not value.get("found"):
        return None
    peer_id = str(value.get("peer_id") or "").strip()
    if not peer_id or peer_id.startswith("-"):
        return None
    name = _compact(str(value.get("name") or ""))
    if not name:
        name = "—"
    role = _compact(str(value.get("role") or "")) or "—"
    username = _normalize_username(str(value.get("username") or ""))
    return {
        "peer_id": peer_id,
        "name": name,
        "status": "из чата",
        "role": role,
        "username": username,
    }


def _telegram_sticky_author_command(
    *,
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    timeout_sec: int,
    click: bool = False,
    context_click: bool = False,
    expected_peer_id: str = "",
) -> dict[str, Any] | None:
    command: dict[str, Any] = {
        "type": "telegram_sticky_author",
        "click": bool(click),
        "context_click": bool(context_click),
    }
    expected_peer_id = str(expected_peer_id or "").strip()
    if expected_peer_id:
        command["expected_peer_id"] = expected_peer_id
    result = _send_command_result(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        timeout_sec=min(max(timeout_sec, 2), 4),
        command=command,
        raise_on_fail=False,
    )
    if not result.get("ok"):
        return None
    data = result.get("data") or {}
    if isinstance(data, dict) and isinstance(data.get("value"), dict):
        data = data["value"]
    return data if isinstance(data, dict) else None


def _read_sticky_chat_author_member(
    *,
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    timeout_sec: int,
) -> dict[str, str] | None:
    return _member_from_sticky_author_payload(
        _telegram_sticky_author_command(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=timeout_sec,
        )
    )


def _scroll_chat_up(server: str, token: str, client_id: str, tab_id: int, timeout_sec: int) -> bool:
    # Current Telegram Web scrolls the chat by bringing the top sentinel/first loaded
    # message block into view, not by scrolling old `.bubbles` containers.
    for selector in CHAT_SCROLL_SELECTORS:
        result = _send_command_result(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=timeout_sec,
            command={
                "type": "scroll",
                "selector": selector,
                "timeout_ms": 2200,
            },
            raise_on_fail=False,
        )
        if result.get("ok"):
            return True

    for selector in (
        ".bubbles .scrollable.scrollable-y",
        ".chat.tabs-tab.active .bubbles .scrollable-y",
        "#column-center .bubbles .scrollable-y",
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
                "delta_y": -900,
                "delta_x": 0,
            },
            raise_on_fail=False,
        )
        if result.get("ok"):
            return True
    return False


def _repeated_view_signature_stop_streak() -> int:
    return max(CHAT_JUMP_SCROLL_TRIGGER_STALL + 1, 3)


def _scroll_info_members_down(server: str, token: str, client_id: str, tab_id: int, timeout_sec: int) -> bool:
    # New Telegram Web renders Members inside the right Profile scroller.
    for selector in (
        "#RightColumn .Profile.custom-scroll",
        "#column-right .profile-content",
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
                "delta_x": 0,
                "delta_y": 900,
            },
            raise_on_fail=False,
        )
        if result.get("ok"):
            return True

    # Fallback for older Telegram DOMs: move to the last visible row.
    for selector in (
        '#RightColumn .members-list .ListItem:last-of-type',
        '#RightColumn .members-list .contact-list-item:last-of-type',
        '#RightColumn a.chatlist-chat.chatlist-chat-abitbigger[data-dialog="0"]:last-of-type',
        '#RightColumn a.chatlist-chat-abitbigger[data-dialog="0"]:last-of-type',
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
    group_url: str = "",
    deep_usernames: bool = False,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    members: list[dict[str, str]] = []
    scroll_steps_done = 0
    no_growth_steps = 0
    total_hint: int | None = None
    deep_seen_peer_ids: set[str] = set()
    deep_attempted_total = 0
    deep_updated_total = 0
    view_kind = "unknown"

    for step in range(max(0, scroll_steps) + 1):
        html_payload = _send_get_html(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=max(timeout_sec, 5),
            selector="#RightColumn, #column-right",
        )
        if view_kind in ("unknown", "none"):
            view_kind = _detect_info_members_view_kind(html_payload)

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
                and not _is_probable_bot_member(item)
            ]
            if deep_targets:
                attempted, updated, opened_peer_ids = _enrich_usernames_deep(
                    server=server,
                    token=token,
                    client_id=client_id,
                    tab_id=tab_id,
                    timeout_sec=max(timeout_sec, 5),
                    group_url=group_url,
                    members=deep_targets,
                )
                deep_attempted_total += attempted
                deep_updated_total += updated
                for peer_id in opened_peer_ids:
                    deep_seen_peer_ids.add(peer_id)
                print(
                    f"INFO: info deep step {step}: processed {attempted}, "
                    f"filled {updated}, total_filled {deep_updated_total}"
                )

        hint_text = str(total_hint) if total_hint else "unknown"
        kind_suffix = f", view {view_kind}" if view_kind not in ("", "unknown") else ""
        print(f"INFO: info step {step} collected {len(members)} unique users (hint {hint_text}{kind_suffix})")

        if view_kind == "preview":
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
        "view_kind": view_kind,
    }
    return members, stats


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
        group_url="",
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
    discovery_state: dict[str, Any] | None = None,
    max_runtime_sec: float = 30.0,
) -> tuple[int, int]:
    if deep_limit <= 0 or not members:
        return 0, 0

    body_started_at = time.time()
    body_html = _send_get_html_best_effort(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        timeout_sec=min(max(timeout_sec, 2), 4),
    )
    _mention_trace_step("*", "initial-body", body_started_at, html=int(bool(body_html)))
    if not body_html:
        return 0, 0
    candidates: list[str] = []
    candidate_limit = max(int(deep_limit), 0)
    if CHAT_MENTION_DEEP_MAX_PER_STEP > 0:
        candidate_limit = min(candidate_limit, CHAT_MENTION_DEEP_MAX_PER_STEP)
    for username_raw in _extract_chat_mention_usernames(body_html):
        normalized_mention = _normalize_username_from_mention_input(username_raw)
        if normalized_mention == "—":
            continue
        if _discovery_mention_in_cooldown(discovery_state, normalized_mention):
            continue
        candidates.append(username_raw)
        if len(candidates) >= candidate_limit:
            break
    if CHAT_MENTION_TRACE:
        print(f"INFO: chat mention trace candidates found={len(candidates)} limit={candidate_limit}")
    if not candidates:
        return 0, 0

    members_by_peer = {str(item.get("peer_id") or "").strip(): item for item in members}
    tg_mode = _tg_web_mode_from_url(group_url)
    attempted = 0
    updated = 0
    started_at = time.time()
    for username_raw in candidates:
        if time.time() - started_at > max(max_runtime_sec, 1.0):
            print("WARN: mention deep budget exhausted, stop extra mention pass")
            break
        normalized_mention = _normalize_username_from_mention_input(username_raw)
        attempted += 1
        username = _normalize_username(username_raw)
        if username == "—":
            continue
        user_url = f"https://web.telegram.org/{tg_mode}/#{username}"
        navigate_started_at = time.time()
        navigate_result = _send_command_result(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=min(timeout_sec, 4),
            command={"type": "navigate", "url": user_url},
            raise_on_fail=False,
        )
        _mention_trace_step(
            username,
            "navigate-user",
            navigate_started_at,
            ok=int(bool(navigate_result.get("ok"))),
        )
        wait_started_at = time.time()
        peer_id, opened_title = _wait_for_current_opened_identity(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=min(float(timeout_sec), 1.2),
        )
        _mention_trace_step(
            username,
            "wait-identity",
            wait_started_at,
            peer_id=peer_id or "—",
            title=opened_title or "—",
        )
        if not peer_id or not opened_title:
            fallback_started_at = time.time()
            user_html = _send_get_html_best_effort(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=tab_id,
                timeout_sec=min(timeout_sec, 3),
                selector="body",
            )
            if not peer_id:
                peer_id = _extract_peer_id_from_helper_header_html(user_html)
            if not opened_title:
                opened_title = _extract_title_from_helper_header_html(user_html)
            _mention_trace_step(
                username,
                "fallback-body",
                fallback_started_at,
                html=int(bool(user_html)),
                peer_id=peer_id or "—",
                title=opened_title or "—",
            )
        matched_by_title = False
        if not peer_id and opened_title:
            peer_id = _match_unique_member_peer_id_by_title(members, opened_title)
            matched_by_title = bool(peer_id)
        if peer_id and peer_id in members_by_peer and members_by_peer[peer_id].get("username") == "—":
            members_by_peer[peer_id]["username"] = username
            updated += 1
            _discovery_note_peer_attempt(
                discovery_state,
                peer_id=peer_id,
                outcome="mention_deep_success",
                username=username,
            )
            _discovery_note_mention_attempt(
                discovery_state,
                username=normalized_mention,
                outcome="mention_deep_success",
                peer_id=peer_id,
            )
            if matched_by_title:
                print(f"INFO: chat mention deep title-mapped {username} -> peer {peer_id}")
            else:
                print(f"INFO: chat mention deep mapped {username} -> peer {peer_id}")
        else:
            mention_outcome = "mention_peer_unknown"
            if peer_id and peer_id in members_by_peer:
                mention_outcome = "mention_already_known"
            elif peer_id:
                mention_outcome = "mention_non_target"
            _discovery_note_mention_attempt(
                discovery_state,
                username=normalized_mention,
                outcome=mention_outcome,
                peer_id=peer_id,
            )

        if _is_specific_tg_dialog_url(group_url):
            return_started_at = time.time()
            return_result = _send_command_result(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=tab_id,
                timeout_sec=min(timeout_sec, 4),
                command={"type": "navigate", "url": group_url},
                raise_on_fail=False,
            )
            _mention_trace_step(
                username,
                "return-group-navigate",
                return_started_at,
                ok=int(bool(return_result.get("ok"))),
            )
            wait_return_started_at = time.time()
            wait_return_result = _send_command_result(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=tab_id,
                timeout_sec=min(timeout_sec, 3),
                command={
                    "type": "wait_selector",
                    "selector": (
                        ".MessageList .backwards-trigger, "
                        ".MessageList .sender-group-container, "
                        ".MessageList .Message, "
                        ".messages-container > :first-child, "
                        ".bubbles .sticky_sentinel--top, "
                        ".bubbles [data-mid], "
                        ".bubbles .bubbles-group-avatar"
                    ),
                    "timeout_ms": 2500,
                    "visible_only": False,
                },
                raise_on_fail=False,
            )
            _mention_trace_step(
                username,
                "return-group-wait",
                wait_return_started_at,
                ok=int(bool(wait_return_result.get("ok"))),
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
    auto_extra_steps: int = CHAT_AUTO_EXTRA_DEFAULT,
    chat_deep_mode: str = "mention",
    chat_target_peer_id: str = "",
    chat_target_name: str = "",
    supports_click_menu_text: bool = False,
    historical_username_to_peer: dict[str, str] | None = None,
    historical_peer_to_username: dict[str, str] | None = None,
    discovery_state: dict[str, Any] | None = None,
) -> tuple[list[dict[str, str]], dict[str, int]]:
    members: list[dict[str, str]] = []
    chat_html_timeout = max(5, min(timeout_sec, 8))
    started_at = time.time()
    previous_min_ts: int | None = None
    unchanged_steps = 0
    empty_steps = 0
    scroll_steps_done = 0
    deep_seen_peer_ids: set[str] = set()
    deep_attempted_total = 0
    deep_updated_total = 0
    runtime_limited = False
    no_growth_steps = 0
    minimum_steps = max(0, scroll_steps)
    maximum_steps = minimum_steps + max(0, auto_extra_steps)
    deep_runtime_hints: dict[str, Any] = {}
    history_prefilled_total = 0
    history_prefill_conflicts_total = 0
    sticky_seen_peer_ids: set[str] = set()
    sticky_mention_attempted_total = 0
    sticky_mention_updated_total = 0
    sticky_helper_attempted_total = 0
    sticky_helper_updated_total = 0
    discovery_new_visible_total = 0
    discovery_cooldown_skips_total = 0
    discovery_revisit_steps_total = 0
    revisited_view_steps_total = 0
    repeated_view_signature_streak = 0
    previous_view_signature = ""
    chat_helper_session: dict[str, Any] = {"tab_id": None}

    def matches_chat_target(item: dict[str, str]) -> bool:
        if chat_target_peer_id and str(item.get("peer_id") or "").strip() != chat_target_peer_id:
            return False
        if chat_target_name:
            target_key = _name_key(chat_target_name)
            if target_key and target_key not in _name_key(str(item.get("name") or "")):
                return False
        return True

    try:
        for step in range(maximum_steps + 1):
            if time.time() - started_at > max(max_runtime_sec, 5):
                print(f"WARN: chat runtime limit reached ({max_runtime_sec}s), stopping")
                runtime_limited = True
                break

            html_payload = _send_get_html(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=tab_id,
                timeout_sec=chat_html_timeout,
            )

            chat_members = _parse_chat_members(html_payload)
            sticky_member = _read_sticky_chat_author_member(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=tab_id,
                timeout_sec=min(timeout_sec, 4),
            )
            if sticky_member:
                sticky_peer_id = str(sticky_member.get("peer_id") or "").strip()
                if sticky_peer_id and sticky_peer_id not in sticky_seen_peer_ids:
                    sticky_seen_peer_ids.add(sticky_peer_id)
                    print(f"INFO: sticky chat author {sticky_peer_id} ({sticky_member.get('name', '—')})")
                if sticky_peer_id and not any(str(item.get("peer_id") or "").strip() == sticky_peer_id for item in chat_members):
                    chat_members.append(sticky_member)
            visible_peer_ids_before_step = {
                str(item.get("peer_id") or "").strip()
                for item in chat_members
                if str(item.get("peer_id") or "").strip()
            }
            discovery_seen_before_step = _discovery_seen_peer_ids(discovery_state)
            discovery_new_visible_ids = visible_peer_ids_before_step - discovery_seen_before_step
            if visible_peer_ids_before_step and not discovery_new_visible_ids:
                discovery_revisit_steps_total += 1
            discovery_new_visible_total += len(discovery_new_visible_ids)
            _discovery_note_visible_peers(discovery_state, visible_peer_ids_before_step)
            current_view_signature = _discovery_note_view_signature(discovery_state, visible_peer_ids_before_step)
            if current_view_signature and current_view_signature == previous_view_signature:
                revisited_view_steps_total += 1
                repeated_view_signature_streak += 1
            else:
                repeated_view_signature_streak = 0
            previous_view_signature = current_view_signature
            before_count = len(members)

            if chat_members:
                members.extend(chat_members)
                members = _dedupe_members(members)
                history_prefilled, history_prefill_conflicts = _backfill_usernames_from_history(
                    members=members,
                    historical_username_to_peer=historical_username_to_peer,
                    historical_peer_to_username=historical_peer_to_username,
                )
                history_prefilled_total += history_prefilled
                history_prefill_conflicts_total += history_prefill_conflicts
                empty_steps = 0
            else:
                empty_steps += 1
            added = len(members) - before_count

            if deep_usernames and members and chat_members:
                if time.time() - started_at > max(max_runtime_sec, 5):
                    print(f"WARN: skip deep (runtime limit {max_runtime_sec}s reached)")
                else:
                    visible_peer_ids = {item["peer_id"] for item in chat_members if item.get("peer_id")}
                    sticky_peer_id_for_step = str((sticky_member or {}).get("peer_id") or "").strip()
                    sticky_peer_on_cooldown = False
                    if sticky_peer_id_for_step:
                        sticky_peer_on_cooldown = _discovery_peer_in_cooldown(
                            discovery_state,
                            sticky_peer_id_for_step,
                        )
                    if sticky_peer_id_for_step and not sticky_peer_on_cooldown:
                        visible_peer_ids = {sticky_peer_id_for_step}
                    elif sticky_peer_on_cooldown:
                        print(f"INFO: sticky peer {sticky_peer_id_for_step} is cooling down, use other visible peers first")
                    deep_targets = [
                        item
                        for item in members
                        if item.get("peer_id") in visible_peer_ids
                        and item.get("username") == "—"
                        and item.get("peer_id") not in deep_seen_peer_ids
                        and not _is_probable_bot_member(item)
                    ]
                    if chat_target_peer_id:
                        deep_targets = [item for item in deep_targets if str(item.get("peer_id") or "").strip() == chat_target_peer_id]
                    if chat_target_name:
                        target_key = _name_key(chat_target_name)
                        if target_key:
                            deep_targets = [item for item in deep_targets if target_key in _name_key(str(item.get("name") or ""))]
                    limit = max(int(chat_deep_limit), 0)
                    if limit <= 0:
                        deep_targets = []
                    else:
                        prioritized_targets = sorted(
                            deep_targets,
                            key=lambda item: _discovery_target_priority(
                                item,
                                discovery_state=discovery_state,
                                seen_peer_ids_before_step=discovery_seen_before_step,
                                now=dt.datetime.now(dt.timezone.utc),
                            ),
                        )
                        ready_targets = [
                            item
                            for item in prioritized_targets
                            if not _discovery_peer_in_cooldown(discovery_state, str(item.get("peer_id") or "").strip())
                        ]
                        if ready_targets:
                            discovery_cooldown_skips_total += max(len(prioritized_targets) - len(ready_targets), 0)
                            deep_targets = ready_targets[:limit]
                        else:
                            if prioritized_targets:
                                discovery_cooldown_skips_total += len(prioritized_targets)
                            deep_targets = []
                    sticky_attempted_this_step = 0
                    if sticky_member and limit > 0:
                        sticky_peer_id = str(sticky_member.get("peer_id") or "").strip()
                        members_by_peer = {
                            str(item.get("peer_id") or "").strip(): item
                            for item in members
                            if str(item.get("peer_id") or "").strip()
                        }
                        sticky_target = members_by_peer.get(sticky_peer_id)
                        if (
                            sticky_target
                            and sticky_target.get("username") == "—"
                            and sticky_peer_id not in deep_seen_peer_ids
                            and matches_chat_target(sticky_target)
                            and not _discovery_peer_in_cooldown(discovery_state, sticky_peer_id)
                            and not _is_probable_bot_member(sticky_target)
                        ):
                            sticky_username, sticky_outcome = _try_username_via_mention_action(
                                server=server,
                                token=token,
                                client_id=client_id,
                                tab_id=tab_id,
                                peer_id=sticky_peer_id,
                                supports_click_menu_text=supports_click_menu_text,
                                use_sticky_anchor=True,
                            )
                            if sticky_outcome != "context_missing":
                                sticky_attempted_this_step = 1
                                sticky_mention_attempted_total += 1
                                deep_attempted_total += 1
                                deep_seen_peer_ids.add(sticky_peer_id)
                                deep_targets = [
                                    item
                                    for item in deep_targets
                                    if str(item.get("peer_id") or "").strip() != sticky_peer_id
                                ]
                                if sticky_username != "—":
                                    assigned, conflict_value, reason = _assign_username_if_unique(
                                        members_by_peer=members_by_peer,
                                        username_to_peer=_seed_username_to_peer(members),
                                        peer_id=sticky_peer_id,
                                        username=sticky_username,
                                        historical_username_to_peer=historical_username_to_peer,
                                        historical_peer_to_username=historical_peer_to_username,
                                    )
                                    if assigned:
                                        sticky_mention_updated_total += 1
                                        deep_updated_total += 1
                                        print(f"INFO: sticky mention {sticky_peer_id} -> {sticky_username}")
                                        _discovery_note_peer_attempt(
                                            discovery_state,
                                            peer_id=sticky_peer_id,
                                            outcome="sticky_mention_success",
                                            username=sticky_username,
                                        )
                                    else:
                                        _log_username_assignment_conflict(
                                            sticky_username,
                                            sticky_peer_id,
                                            conflict_value,
                                            reason,
                                        )
                                else:
                                    if sticky_outcome == "menu_missing":
                                        deep_runtime_hints["mention_unavailable"] = True
                                    print(f"INFO: sticky mention unresolved for peer {sticky_peer_id} ({sticky_outcome})")
                                    if sticky_outcome in {"menu_missing", "delivery_failure", "unresolved"}:
                                        remaining_runtime = float(max_runtime_sec) - (time.time() - started_at)
                                        if remaining_runtime > 4.0:
                                            sticky_helper_username, sticky_helper_opened = _read_username_via_helper_tab(
                                                server=server,
                                                token=token,
                                                client_id=client_id,
                                                base_tab_id=tab_id,
                                                peer_id=sticky_peer_id,
                                                expected_name=str(sticky_target.get("name") or ""),
                                                timeout_sec=max(5, min(timeout_sec, 8)),
                                                tg_mode=_tg_web_mode_from_url(group_url),
                                                helper_session=chat_helper_session,
                                                restore_base_tab=False,
                                            )
                                            if sticky_helper_opened:
                                                sticky_helper_attempted_total += 1
                                                deep_attempted_total += 1
                                            if sticky_helper_username != "—":
                                                assigned, conflict_value, reason = _assign_username_if_unique(
                                                    members_by_peer=members_by_peer,
                                                    username_to_peer=_seed_username_to_peer(members),
                                                    peer_id=sticky_peer_id,
                                                    username=sticky_helper_username,
                                                    historical_username_to_peer=historical_username_to_peer,
                                                    historical_peer_to_username=historical_peer_to_username,
                                                )
                                                if assigned:
                                                    sticky_helper_updated_total += 1
                                                    deep_updated_total += 1
                                                    print(f"INFO: sticky helper {sticky_peer_id} -> {sticky_helper_username}")
                                                    _discovery_note_peer_attempt(
                                                        discovery_state,
                                                        peer_id=sticky_peer_id,
                                                        outcome="sticky_helper_success",
                                                        username=sticky_helper_username,
                                                    )
                                                else:
                                                    _log_username_assignment_conflict(
                                                        sticky_helper_username,
                                                        sticky_peer_id,
                                                        conflict_value,
                                                        reason,
                                                    )
                                            else:
                                                _discovery_note_peer_attempt(
                                                    discovery_state,
                                                    peer_id=sticky_peer_id,
                                                    outcome=f"sticky_helper_blank:{sticky_outcome}",
                                                )
                                    else:
                                        _discovery_note_peer_attempt(
                                            discovery_state,
                                            peer_id=sticky_peer_id,
                                            outcome=f"sticky:{sticky_outcome}",
                                        )
                    if sticky_attempted_this_step and limit > 0:
                        deep_targets = deep_targets[: max(limit - sticky_attempted_this_step, 0)]
                    if deep_targets:
                        elapsed = time.time() - started_at
                        remaining_runtime = max(2.0, float(max_runtime_sec) - elapsed - 2.0)
                        deep_runtime_budget = remaining_runtime
                        if CHAT_DEEP_STEP_MAX_SEC > 0:
                            deep_runtime_budget = min(deep_runtime_budget, max(6.0, CHAT_DEEP_STEP_MAX_SEC))
                        attempted, updated, opened, opened_peer_ids = _enrich_usernames_deep_chat(
                            server=server,
                            token=token,
                            client_id=client_id,
                            tab_id=tab_id,
                            timeout_sec=max(timeout_sec, 5),
                            members=deep_targets,
                            group_url=group_url,
                            max_runtime_sec=deep_runtime_budget,
                            mode=chat_deep_mode,
                            supports_click_menu_text=supports_click_menu_text,
                            helper_only_initial=bool(deep_runtime_hints.get("mention_unavailable")),
                            runtime_hints=deep_runtime_hints,
                            discovery_state=discovery_state,
                            helper_session=chat_helper_session,
                        )
                        deep_attempted_total += attempted
                        deep_updated_total += updated
                        for peer_id in opened_peer_ids:
                            deep_seen_peer_ids.add(peer_id)
                        print(
                            f"INFO: chat deep step {step}: processed {attempted}, "
                            f"opened {opened}, filled {updated}, total_filled {deep_updated_total}"
                        )

            print(f"INFO: chat step {step} collected {len(members)} unique users")

            timestamps = [int(value) for value in re.findall(r'data-timestamp="(\d+)"', html_payload)]
            min_ts = min(timestamps) if timestamps else None
            if min_ts is not None and min_ts == previous_min_ts:
                unchanged_steps += 1
            else:
                unchanged_steps = 0
            previous_min_ts = min_ts

            if step >= minimum_steps:
                discovery_productive = bool(discovery_state) and bool(discovery_new_visible_ids)
                if added <= 0 and not discovery_productive:
                    no_growth_steps += 1
                else:
                    no_growth_steps = 0

            if (
                discovery_state
                and step >= 1
                and added <= 0
                and repeated_view_signature_streak >= _repeated_view_signature_stop_streak()
            ):
                print(
                    "INFO: chat auto-stop after repeated identical discovery view "
                    f"({repeated_view_signature_streak + 1} steps)"
                )
                break

            if step >= maximum_steps:
                break
            if empty_steps >= 2 and not members:
                print("WARN: чат не читается (пустой DOM/не открыт диалог), останавливаюсь")
                break
            if step >= minimum_steps and no_growth_steps >= 2:
                print("INFO: chat auto-stop after 2 no-growth steps")
                break
            if step >= minimum_steps and unchanged_steps >= 2:
                break

            if not _scroll_chat_up(server, token, client_id, tab_id, timeout_sec=min(timeout_sec, 10)):
                break
            scroll_steps_done += 1
            time.sleep(CHAT_SCROLL_SETTLE_SEC)
    finally:
        _close_helper_session_best_effort(
            server=server,
            token=token,
            client_id=client_id,
            base_tab_id=tab_id,
            helper_session=chat_helper_session,
            timeout_sec=min(timeout_sec, 4),
        )

    stats = {
        "unique_members": len(members),
        "scroll_steps_done": scroll_steps_done,
        "deep_attempted": deep_attempted_total,
        "deep_updated": deep_updated_total,
        "runtime_limited": int(runtime_limited),
        "auto_extra_steps": max(0, scroll_steps_done - minimum_steps),
        "history_prefilled": history_prefilled_total,
        "history_prefill_conflicts": history_prefill_conflicts_total,
        "sticky_authors_seen": len(sticky_seen_peer_ids),
        "sticky_mention_attempted": sticky_mention_attempted_total,
        "sticky_mention_updated": sticky_mention_updated_total,
        "sticky_helper_attempted": sticky_helper_attempted_total,
        "sticky_helper_updated": sticky_helper_updated_total,
        "burst_scrolls_done": 0,
        "jump_scrolls_done": 0,
        "revisited_view_steps": revisited_view_steps_total,
        "discovery_new_visible": discovery_new_visible_total,
        "discovery_cooldown_skips": discovery_cooldown_skips_total,
        "discovery_revisit_steps": discovery_revisit_steps_total,
    }
    return members, stats


def _enrich_usernames_deep_chat(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    timeout_sec: int,
    members: list[dict[str, str]],
    group_url: str = "",
    max_runtime_sec: float = 12.0,
    mode: str = "url",
    supports_click_menu_text: bool = False,
    helper_only_initial: bool = False,
    runtime_hints: dict[str, Any] | None = None,
    discovery_state: dict[str, Any] | None = None,
    helper_session: dict[str, Any] | None = None,
) -> tuple[int, int, int, list[str]]:
    members_by_peer = {item["peer_id"]: item for item in members}
    pending_peer_ids = [
        item["peer_id"]
        for item in members
        if item.get("username") == "—" and not _is_probable_bot_member(item)
    ]
    username_to_peer: dict[str, str] = {}
    for item in members:
        u = str(item.get("username") or "").strip()
        p = str(item.get("peer_id") or "").strip()
        if u and u != "—" and p:
            username_to_peer[u.lower()] = p
    target_fragment = group_url.split("#", 1)[1] if "#" in group_url else ""
    tg_mode = _tg_web_mode_from_url(group_url)

    attempted = 0
    updated = 0
    opened = 0
    opened_peer_ids: list[str] = []
    started_at = time.time()
    active_helper_session = helper_session if isinstance(helper_session, dict) else {"tab_id": None}
    owns_helper_session = helper_session is None
    helper_only_for_rest = helper_only_initial

    try:
        for peer_id in pending_peer_ids:
            if time.time() - started_at > max_runtime_sec:
                print("WARN: deep chat step budget exhausted, continue with next scroll step")
                break
            attempted += 1
            # Mark as processed for this run to avoid re-clicking the same peer again and again.
            opened_peer_ids.append(peer_id)
            final_outcome = "unresolved"
            final_username = "—"
            if not _is_specific_tg_dialog_url(group_url):
                _discovery_note_peer_attempt(
                    discovery_state,
                    peer_id=peer_id,
                    outcome="non_specific_dialog",
                )
                break

            if not helper_only_for_rest:
                if not _return_to_group_dialog_reliable(
                    server=server,
                    token=token,
                    client_id=client_id,
                    tab_id=tab_id,
                    group_url=group_url,
                    timeout_sec=min(timeout_sec, 3),
                ):
                    print("WARN: deep chat could not restore group dialog, skipping user")
                    _discovery_note_peer_attempt(
                        discovery_state,
                        peer_id=peer_id,
                        outcome="group_restore_failed",
                    )
                    continue

                current_url_before = _get_tab_url(server, token, client_id, tab_id)
                current_fragment_before = current_url_before.split("#", 1)[1] if "#" in current_url_before else ""
                if target_fragment and (not current_fragment_before or target_fragment not in current_fragment_before):
                    print("WARN: deep chat not in target group dialog, skipping user")
                    _discovery_note_peer_attempt(
                        discovery_state,
                        peer_id=peer_id,
                        outcome="wrong_group_dialog",
                    )
                    continue

            mention_outcome = "helper_only" if helper_only_for_rest else "unresolved"
            if not helper_only_for_rest and mode in ("mention", "full"):
                mention_result = _try_username_via_mention_action(
                    server=server,
                    token=token,
                    client_id=client_id,
                    tab_id=tab_id,
                    peer_id=peer_id,
                    supports_click_menu_text=supports_click_menu_text,
                )
                if isinstance(mention_result, tuple):
                    mention_username, mention_outcome = mention_result
                else:
                    mention_username = str(mention_result or "—")
                    mention_outcome = "success" if mention_username != "—" else "unresolved"
                if mention_username != "—":
                    key = mention_username.lower()
                    existing_peer = username_to_peer.get(key)
                    if existing_peer and existing_peer != peer_id:
                        print(f"WARN: skip duplicate username {mention_username} for peer {peer_id} (already {existing_peer})")
                        _discovery_note_peer_attempt(
                            discovery_state,
                            peer_id=peer_id,
                            outcome="mention_duplicate",
                            username=mention_username,
                        )
                        continue
                    members_by_peer[peer_id]["username"] = mention_username
                    username_to_peer[key] = peer_id
                    updated += 1
                    final_outcome = "mention_success"
                    final_username = mention_username
                    print(f"INFO: chat mention {peer_id} -> {mention_username}")
                    _return_to_group_dialog_reliable(
                        server=server,
                        token=token,
                        client_id=client_id,
                        tab_id=tab_id,
                        group_url=group_url,
                        timeout_sec=min(timeout_sec, 2),
                    )
                    _discovery_note_peer_attempt(
                        discovery_state,
                        peer_id=peer_id,
                        outcome=final_outcome,
                        username=final_username,
                    )
                    time.sleep(0.03)
                    continue
                if mention_outcome == "menu_missing":
                    helper_only_for_rest = True
                    if isinstance(runtime_hints, dict):
                        runtime_hints["mention_unavailable"] = True
                    print("INFO: current menu lacks Mention; switching remaining peers in this step to helper-only")
                if mode == "mention":
                    if mention_outcome == "delivery_failure":
                        print(f"INFO: mention delivery failed for peer {peer_id}, fallback to helper tab")
                    else:
                        print(f"INFO: mention unresolved for peer {peer_id}, fallback to helper tab")

            helper_username, helper_opened = _read_username_via_helper_tab(
                server=server,
                token=token,
                client_id=client_id,
                base_tab_id=tab_id,
                peer_id=peer_id,
                expected_name=str(members_by_peer[peer_id].get("name") or ""),
                timeout_sec=min(timeout_sec, 5),
                tg_mode=tg_mode,
                helper_session=active_helper_session,
                restore_base_tab=not helper_only_for_rest,
            )
            if helper_opened:
                opened += 1
            if helper_username != "—":
                key = helper_username.lower()
                existing_peer = username_to_peer.get(key)
                if existing_peer and existing_peer != peer_id:
                    print(f"WARN: skip duplicate username {helper_username} for peer {peer_id} (already {existing_peer})")
                    _discovery_note_peer_attempt(
                        discovery_state,
                        peer_id=peer_id,
                        outcome="helper_duplicate",
                        username=helper_username,
                    )
                else:
                    members_by_peer[peer_id]["username"] = helper_username
                    username_to_peer[key] = peer_id
                    updated += 1
                    final_outcome = "helper_success"
                    final_username = helper_username
                    print(f"INFO: chat helper {peer_id} -> {helper_username}")
                    _discovery_note_peer_attempt(
                        discovery_state,
                        peer_id=peer_id,
                        outcome=final_outcome,
                        username=final_username,
                    )
            else:
                _discovery_note_peer_attempt(
                    discovery_state,
                    peer_id=peer_id,
                    outcome=f"helper_blank:{mention_outcome}",
                )
            time.sleep(0.03)
    finally:
        if owns_helper_session:
            _close_helper_session_best_effort(
                server=server,
                token=token,
                client_id=client_id,
                base_tab_id=tab_id,
                helper_session=active_helper_session,
                timeout_sec=min(timeout_sec, 4),
            )
        else:
            _activate_tab_best_effort(
                server,
                token,
                client_id,
                tab_id,
                timeout_sec=min(timeout_sec, 3),
            )

    return attempted, updated, opened, opened_peer_ids


def _find_tab(clients: list[dict[str, Any]], client_id: str | None, tab_id: int | None, url_pattern: str) -> tuple[str, int]:
    def _client_tabs(client: dict[str, Any]) -> list[dict[str, Any]]:
        tabs = client.get("tabs") or []
        return tabs if isinstance(tabs, list) else []

    def _is_online(client: dict[str, Any]) -> bool:
        return bool(client.get("is_online", True))

    if client_id:
        selected_client = None
        for client in clients:
            if str(client.get("client_id") or "").strip() == client_id:
                selected_client = client
                break
        if selected_client is None:
            raise RuntimeError(f"client_id not found: {client_id}")
        search_clients = [selected_client]
    else:
        if not clients:
            raise RuntimeError("No connected clients found")
        online_clients = [client for client in clients if _is_online(client)]
        search_clients = online_clients or clients

    if tab_id is not None:
        for client in search_clients:
            cid = str(client.get("client_id", "")).strip()
            for tab in _client_tabs(client):
                if tab.get("id") == tab_id:
                    return cid, int(tab_id)
        raise RuntimeError(f"tab_id not found in selected Telegram clients: {tab_id}")

    def _find_match(predicate) -> tuple[str, int] | None:
        for client in search_clients:
            cid = str(client.get("client_id", "")).strip()
            for tab in _client_tabs(client):
                tid = tab.get("id")
                if isinstance(tid, int) and predicate(tab):
                    return cid, tid
        return None

    checks = (
        lambda tab: bool(url_pattern) and url_pattern in str(tab.get("url") or ""),
        lambda tab: "web.telegram.org/k/#" in str(tab.get("url") or "") or "web.telegram.org/a/#" in str(tab.get("url") or ""),
        lambda tab: bool(tab.get("active")) and "web.telegram.org" in str(tab.get("url") or "") and ("/k/#" in str(tab.get("url") or "") or "/a/#" in str(tab.get("url") or "")),
        lambda tab: bool(tab.get("active")) and "web.telegram.org" in str(tab.get("url") or ""),
        lambda tab: "web.telegram.org" in str(tab.get("url") or ""),
    )
    for predicate in checks:
        matched = _find_match(predicate)
        if matched is not None:
            return matched

    opened_urls: list[str] = []
    for client in search_clients[:3]:
        cid = str(client.get("client_id", "")).strip() or "unknown-client"
        urls = [str(tab.get("url") or "") for tab in _client_tabs(client)[:3]]
        opened_urls.append(f"{cid}: {', '.join(urls) if urls else 'no tabs'}")
    opened = " | ".join(opened_urls) or "none"
    raise RuntimeError(
        f"Telegram group tab not found (pattern: {url_pattern}). "
        f"Open target group dialog (URL with #) and rerun. Checked: {opened}"
    )


def _client_supports_content_command(
    clients: list[dict[str, Any]],
    client_id: str,
    command_name: str,
) -> bool:
    target_client_id = str(client_id or "").strip()
    target_command = str(command_name or "").strip()
    if not target_client_id or not target_command:
        return False
    for client in clients:
        if str(client.get("client_id") or "").strip() != target_client_id:
            continue
        meta = client.get("meta") or {}
        capabilities = meta.get("capabilities") or {}
        content_commands = capabilities.get("content_commands") or []
        if not isinstance(content_commands, list):
            return False
        return target_command in {str(item) for item in content_commands}
    return False


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
    current_url = _detect_current_dialog_url(server, token, client_id, tab_id, timeout_sec=min(timeout_sec, 2))
    target_fragment = group_url.split("#", 1)[1] if "#" in group_url else ""
    current_fragment = current_url.split("#", 1)[1] if "#" in current_url else ""
    if target_fragment and current_fragment.startswith("@"):
        if _return_to_group_dialog_fast(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            group_url=group_url,
            timeout_sec=min(max(timeout_sec, 2), 4),
        ):
            return
    if _ensure_group_dialog_url(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        group_url=group_url,
        timeout_sec=max(timeout_sec, 5),
    ):
        return
    if _force_return_to_group_dialog(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        group_url=group_url,
        timeout_sec=min(max(timeout_sec, 2), 5),
    ):
        return
    current_url = _detect_current_dialog_url(server, token, client_id, tab_id, timeout_sec=min(timeout_sec, 2))
    current_fragment = current_url.split("#", 1)[1] if "#" in current_url else ""
    if current_url and current_fragment and (not target_fragment or target_fragment in current_fragment):
        return
    if current_url and _username_from_tg_url(current_url) != "—":
        if _is_dialog_surface_open(server, token, client_id, tab_id, timeout_sec=min(max(timeout_sec, 2), 5)):
            print(
                f"WARN: proceeding from Telegram username route {current_url} because the dialog surface is still open"
            )
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
            current_url = _detect_current_dialog_url(server, token, client_id, tab_id, timeout_sec=2)
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
    html_right = _send_get_html(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        timeout_sec=max(timeout_sec, 5),
        selector=RIGHT_COLUMN_SELECTOR,
    )
    if _parse_members(html_right):
        return True

    # Open chat/group profile from header.
    for selector in (
        ".MiddleHeader .ChatInfo .fullName",
        ".MiddleHeader .ChatInfo [role=\"button\"]",
        ".MiddleHeader .ChatInfo .group-status",
        ".MiddleHeader .ChatInfo .info",
        ".MiddleHeader .ChatInfo .title",
        ".MiddleHeader .ChatInfo .Avatar[data-peer-id]",
        ".MiddleHeader .chat-info-wrapper .ChatInfo",
        ".MiddleHeader .ChatInfo",
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
        if not clicked.get("ok"):
            continue
        ready = _send_command_result(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=min(timeout_sec, 10),
            command={
                "type": "wait_selector",
                "selector": RIGHT_PANEL_READY_SELECTOR,
                "timeout_ms": 8000,
                "visible_only": False,
            },
            raise_on_fail=False,
        )
        if ready.get("ok"):
            break

    html_right = _send_get_html(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        timeout_sec=max(timeout_sec, 5),
        selector=RIGHT_COLUMN_SELECTOR,
    )
    if _parse_members(html_right):
        return True

    # Click members row in profile sidebar.
    _send_command_result(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        timeout_sec=min(timeout_sec, 10),
        command={
            "type": "click_text",
            "root_selector": "#RightColumn, #column-right",
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
            "selector": "#RightColumn a.chatlist-chat-abitbigger[data-dialog=\"0\"], #column-right a.chatlist-chat-abitbigger[data-dialog=\"0\"]",
            "timeout_ms": 9000,
            "visible_only": False,
        },
        raise_on_fail=False,
    )
    time.sleep(0.8)

    html_right = _send_get_html(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        timeout_sec=max(timeout_sec, 5),
        selector=RIGHT_COLUMN_SELECTOR,
    )
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
    command_timeout_sec = max(float(timeout_sec), 0.8)
    create_request_timeout = min(max(command_timeout_sec, 0.8), 5.0)
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
    created = _http_json_retry(
        server,
        token,
        "POST",
        "/api/commands",
        payload,
        retries=2,
        request_timeout_sec=create_request_timeout,
    )
    if not created.get("ok") or not created.get("command_id"):
        raise RuntimeError(f"Command creation failed: {created}")

    command_id = str(created["command_id"])
    deadline = time.time() + timeout_sec
    missing_result_grace_deadline: float | None = None
    while True:
        poll_request_timeout = min(max(deadline - time.time(), 0.5), 5.0)
        try:
            response = _http_json_retry(
                server,
                token,
                "GET",
                f"/api/commands/{command_id}",
                retries=1,
                request_timeout_sec=poll_request_timeout,
            )
        except RuntimeError as exc:
            if time.time() >= deadline:
                if raise_on_fail:
                    raise RuntimeError(f"Timeout waiting for command: {command.get('type')} ({exc})") from exc
                return {"ok": False, "error": f"timeout waiting for command: {command.get('type')} ({exc})"}
            time.sleep(0.2)
            continue
        command_state = response.get("command") or {}
        status = str(command_state.get("status") or "")
        if status in TERMINAL_STATUSES:
            delivery_state = ((command_state.get("deliveries") or {}).get(client_id) or {})
            delivery = delivery_state.get("result")
            if not isinstance(delivery, dict):
                if missing_result_grace_deadline is None:
                    # Telegram Web + large hub state writes can yield a terminal delivery status
                    # noticeably earlier than the actual browser result becomes readable.
                    if raise_on_fail:
                        grace_sec = max(15.0, min(90.0, float(timeout_sec) * 18.0))
                    else:
                        # Best-effort selectors are used heavily in Telegram fallback paths.
                        # A missing result here is normally a selector miss/expired delivery;
                        # waiting tens of seconds per miss destroys helper throughput.
                        grace_sec = max(0.4, min(1.2, float(timeout_sec) * 0.25))
                    missing_result_grace_deadline = time.time() + grace_sec
                if time.time() < missing_result_grace_deadline:
                    time.sleep(0.2)
                    continue

                delivery_status = str(delivery_state.get("status") or status or "unknown")
                synthetic = {
                    "ok": False,
                    "status": delivery_status,
                    "data": None,
                    "error": {
                        "message": (
                            f"command {command.get('type')} finished without result "
                            f"(command_status={status}, delivery_status={delivery_status})"
                        )
                    },
                    "logs": [],
                }
                if raise_on_fail:
                    raise RuntimeError(str((synthetic["error"] or {}).get("message") or "command finished without result"))
                return synthetic

            if raise_on_fail and not delivery.get("ok"):
                err = delivery.get("error") or {}
                msg = str((err.get("message") if isinstance(err, dict) else err) or "")
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
                if not msg:
                    delivery_status = str(delivery_state.get("status") or status or "unknown")
                    msg = f"command_status={status}, delivery_status={delivery_status}"
                raise RuntimeError(f"Command failed: {msg}")
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


def _send_get_html_best_effort(
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
        raise_on_fail=False,
    )
    html_payload = (delivery.get("data") or {}).get("html")
    return html_payload if isinstance(html_payload, str) else ""


def _open_helper_tab(
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    url: str,
    timeout_sec: int,
) -> int | None:
    result = _send_command_result(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        timeout_sec=max(4, timeout_sec),
        command={"type": "new_tab", "url": url, "active": False},
        raise_on_fail=False,
    )
    data = result.get("data") or {}
    value = data.get("tabId") if isinstance(data, dict) else None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _activate_tab_best_effort(server: str, token: str, client_id: str, tab_id: int, timeout_sec: int) -> None:
    _send_command_result(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        timeout_sec=max(2, timeout_sec),
        command={"type": "activate_tab"},
        raise_on_fail=False,
    )


def _close_tab_best_effort(server: str, token: str, client_id: str, tab_id: int, timeout_sec: int) -> None:
    _send_command_result(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        timeout_sec=max(2, timeout_sec),
        command={"type": "close_tab"},
        raise_on_fail=False,
    )


def _helper_session_tab_id(helper_session: dict[str, Any] | None) -> int | None:
    if not isinstance(helper_session, dict):
        return None
    value = helper_session.get("tab_id")
    try:
        tab_id = int(value)
    except (TypeError, ValueError):
        return None
    return tab_id if tab_id > 0 else None


def _close_helper_session_best_effort(
    server: str,
    token: str,
    client_id: str,
    base_tab_id: int,
    helper_session: dict[str, Any] | None,
    timeout_sec: int,
) -> None:
    helper_tab_id = _helper_session_tab_id(helper_session)
    if helper_tab_id is not None:
        _close_tab_best_effort(server, token, client_id, helper_tab_id, timeout_sec=max(2, timeout_sec))
        needs_restore = bool((helper_session or {}).get("needs_base_restore")) if isinstance(helper_session, dict) else False
        if needs_restore:
            _activate_tab_best_effort(server, token, client_id, base_tab_id, timeout_sec=min(max(timeout_sec, 2), 3))
    if isinstance(helper_session, dict):
        helper_session["tab_id"] = None
        helper_session["needs_base_restore"] = False


def _read_username_via_helper_tab(
    server: str,
    token: str,
    client_id: str,
    base_tab_id: int,
    peer_id: str,
    timeout_sec: int,
    tg_mode: str,
    helper_session: dict[str, Any] | None = None,
    restore_base_tab: bool = True,
    *,
    expected_name: str = "",
) -> tuple[str, bool]:
    helper_deadline = time.time() + _effective_timeout_sec(timeout_sec, minimum=1.0)
    mode = tg_mode if tg_mode in {"a", "k"} else "a"
    helper_url = f"https://web.telegram.org/{mode}/#{peer_id}"
    created_now = False
    helper_tab_id = _helper_session_tab_id(helper_session)
    helper_session_dict = helper_session if isinstance(helper_session, dict) else None
    if helper_tab_id is None:
        if time.time() >= helper_deadline:
            return "—", False
        open_started_at = time.time()
        helper_tab_id = _open_helper_tab(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=base_tab_id,
            url=helper_url,
            timeout_sec=_deadline_timeout(helper_deadline, max(4, timeout_sec), minimum=0.8),
        )
        _mention_trace_step(
            f"peer:{peer_id}",
            "helper-open-tab",
            open_started_at,
            tab_id=helper_tab_id or "—",
        )
        if helper_tab_id is None:
            return "—", False
        created_now = True
        if helper_session_dict is not None:
            helper_session_dict["tab_id"] = helper_tab_id
            helper_session_dict["needs_base_restore"] = False
    else:
        if time.time() >= helper_deadline:
            return "—", True
        navigate_started_at = time.time()
        navigate_result = _send_command_result(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=helper_tab_id,
            timeout_sec=_deadline_timeout(helper_deadline, max(3, timeout_sec), minimum=0.8),
            command={"type": "navigate", "url": helper_url},
            raise_on_fail=False,
        )
        _mention_trace_step(
            f"peer:{peer_id}",
            "helper-navigate",
            navigate_started_at,
            ok=int(bool(navigate_result.get("ok"))),
            tab_id=helper_tab_id,
        )
        if not navigate_result.get("ok"):
            if helper_session_dict is not None:
                helper_session_dict["tab_id"] = None
                helper_session_dict["needs_base_restore"] = False
            _close_tab_best_effort(server, token, client_id, helper_tab_id, timeout_sec=min(max(timeout_sec, 2), 3))
            helper_tab_id = _open_helper_tab(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=base_tab_id,
                url=helper_url,
                timeout_sec=_deadline_timeout(helper_deadline, max(4, timeout_sec), minimum=0.8),
            )
            if helper_tab_id is None:
                return "—", False
            created_now = True
            if helper_session_dict is not None:
                helper_session_dict["tab_id"] = helper_tab_id
                helper_session_dict["needs_base_restore"] = False

    try:
        if time.time() >= helper_deadline:
            return "—", True
        if CHAT_MENTION_TRACE:
            remaining_probe = helper_deadline - time.time()
            if remaining_probe > 0:
                _trace_helper_route_probe(
                    server=server,
                    token=token,
                    client_id=client_id,
                    tab_id=helper_tab_id,
                    expected_peer_id=peer_id,
                    expected_name=expected_name,
                    timeout_sec=min(0.6, max(remaining_probe, 0.3)),
                    step="helper-route-probe-prewait",
                )
        wait_identity_started_at = time.time()
        identity_confirmed = _wait_for_helper_target_identity(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=helper_tab_id,
            expected_peer_id=peer_id,
            expected_name=expected_name,
            timeout_sec=min(
                _deadline_timeout(helper_deadline, min(max(float(timeout_sec) * 0.4, 0.8), 2.5)),
                2.5,
            ),
        )
        route_soft_confirmed = False
        if not identity_confirmed and time.time() < helper_deadline:
            route_soft_started_at = time.time()
            route_soft_confirmed = _soft_confirm_helper_target_route(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=helper_tab_id,
                expected_peer_id=peer_id,
                expected_name=expected_name,
                timeout_sec=min(
                    _deadline_timeout(helper_deadline, 0.5, minimum=0.3),
                    0.5,
                ),
            )
            _mention_trace_step(
                f"peer:{peer_id}",
                "helper-soft-route",
                route_soft_started_at,
                matched=int(route_soft_confirmed),
                tab_id=helper_tab_id,
            )
            if route_soft_confirmed:
                # Route-only soft confirm means Telegram loaded the target helper URL
                # but did not expose a stable header in time; foreground once, then continue.
                activate_soft_started_at = time.time()
                remaining_soft_activate = helper_deadline - time.time()
                if remaining_soft_activate > 0.35:
                    _send_command_result(
                        server=server,
                        token=token,
                        client_id=client_id,
                        tab_id=helper_tab_id,
                        timeout_sec=_deadline_timeout(helper_deadline, min(0.8, remaining_soft_activate), minimum=0.35),
                        command={"type": "activate_tab"},
                        raise_on_fail=False,
                    )
                    _mention_trace_step(
                        f"peer:{peer_id}",
                        "helper-soft-activate",
                        activate_soft_started_at,
                        tab_id=helper_tab_id,
                    )
                    if helper_session_dict is not None and not restore_base_tab:
                        helper_session_dict["needs_base_restore"] = True
                if CHAT_MENTION_TRACE:
                    remaining_probe = helper_deadline - time.time()
                    if remaining_probe > 0:
                        _trace_helper_route_probe(
                            server=server,
                            token=token,
                            client_id=client_id,
                            tab_id=helper_tab_id,
                            expected_peer_id=peer_id,
                            expected_name=expected_name,
                            timeout_sec=min(0.6, max(remaining_probe, 0.3)),
                            step="helper-route-probe-soft",
                        )
        identity_confirmed = identity_confirmed or route_soft_confirmed
        _mention_trace_step(
            f"peer:{peer_id}",
            "helper-wait-identity",
            wait_identity_started_at,
            matched=int(identity_confirmed),
            soft=int(route_soft_confirmed),
            tab_id=helper_tab_id,
        )
        if not identity_confirmed:
            if CHAT_MENTION_TRACE:
                remaining_probe = helper_deadline - time.time()
                if remaining_probe > 0:
                    _trace_helper_route_probe(
                        server=server,
                        token=token,
                        client_id=client_id,
                        tab_id=helper_tab_id,
                        expected_peer_id=peer_id,
                        expected_name=expected_name,
                        timeout_sec=min(0.6, max(remaining_probe, 0.3)),
                        step="helper-route-probe-miss",
                    )
            return "—", True

        prefer_profile_after_soft_route = bool(route_soft_confirmed and _username_from_tg_url(helper_url) == "—")
        if not prefer_profile_after_soft_route:
            remaining_quick = helper_deadline - time.time()
            if remaining_quick <= 0:
                return "—", True
            quick_url_started_at = time.time()
            quick_username, _ = _poll_username_from_tab_url(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=helper_tab_id,
                timeout_sec=min(0.7, max(remaining_quick, 0.2)),
            )
            _mention_trace_step(
                f"peer:{peer_id}",
                "helper-quick-url",
                quick_url_started_at,
                value=quick_username,
                tab_id=helper_tab_id,
            )
            if quick_username != "—":
                return quick_username, True

            remaining_page = helper_deadline - time.time()
            if remaining_page <= 0:
                return "—", True
            page_url_started_at = time.time()
            page_username, _ = _poll_username_from_page_location(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=helper_tab_id,
                timeout_sec=min(0.7, max(remaining_page, 0.2)),
            )
            _mention_trace_step(
                f"peer:{peer_id}",
                "helper-page-url",
                page_url_started_at,
                value=page_username,
                tab_id=helper_tab_id,
            )
            if page_username != "—":
                return page_username, True

        if time.time() >= helper_deadline:
            return "—", True
        header_html = ""
        try:
            header_started_at = time.time()
            header_html = _send_get_html(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=helper_tab_id,
                timeout_sec=_deadline_timeout(helper_deadline, max(3, min(timeout_sec, 5))),
                selector=".MiddleHeader, .chat-info, .sidebar-header",
            )
            _mention_trace_step(
                f"peer:{peer_id}",
                "helper-header-html",
                header_started_at,
                html=int(bool(header_html)),
                tab_id=helper_tab_id,
            )
        except RuntimeError:
            header_html = ""
        header_username = _extract_username(header_html)
        if header_username != "—":
            return header_username, True

        header_status_match = re.search(
            r'<span class="user-status"[^>]*>(.*?)</span>',
            header_html,
            flags=re.I | re.S,
        )
        header_status = _compact(header_status_match.group(1) if header_status_match else "").lower()
        if "bot" in header_status or "monthly users" in header_status:
            return "—", True

        if time.time() >= helper_deadline:
            return "—", True
        wait_profile_started_at = time.time()
        _send_command_result(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=helper_tab_id,
            timeout_sec=_deadline_timeout(helper_deadline, max(4, timeout_sec)),
            command={
                "type": "wait_selector",
                "selector": ".MiddleHeader .ChatInfo .fullName, .chat-info .peer-title, .sidebar-header .peer-title, body",
                "timeout_ms": 3500,
                "visible_only": False,
            },
            raise_on_fail=False,
        )
        _mention_trace_step(
            f"peer:{peer_id}",
            "helper-wait-profile",
            wait_profile_started_at,
            tab_id=helper_tab_id,
        )
        if time.time() >= helper_deadline:
            return "—", True
        profile_started_at = time.time()
        username = _open_current_chat_user_info_and_read_username(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=helper_tab_id,
            timeout_sec=max(4, timeout_sec),
            deadline=helper_deadline,
        )
        _mention_trace_step(
            f"peer:{peer_id}",
            "helper-read-profile",
            profile_started_at,
            value=username,
            tab_id=helper_tab_id,
        )
        return username, True
    finally:
        if restore_base_tab:
            _activate_tab_best_effort(server, token, client_id, base_tab_id, timeout_sec=min(timeout_sec, 3))
        if helper_session is None:
            _close_tab_best_effort(server, token, client_id, helper_tab_id, timeout_sec=min(timeout_sec, 4))
        elif created_now and helper_session_dict is not None:
            helper_session_dict["tab_id"] = helper_tab_id


def _close_profile_card(server: str, token: str, client_id: str, tab_id: int) -> None:
    # Important: close only the right profile sidebar.
    for selector in (
        "#RightColumn button.close-button",
        "#RightColumn .RightHeader button.close-button",
        "#RightColumn button.sidebar-close-button",
        "#RightColumn .sidebar-header button.sidebar-close-button",
        "#column-right button.close-button",
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
    group_url: str,
    members: list[dict[str, str]],
) -> tuple[int, int, list[str]]:
    members_by_peer = {item["peer_id"]: item for item in members}
    pending_peer_ids = [
        item["peer_id"]
        for item in members
        if item.get("username") == "—" and not _is_probable_bot_member(item)
    ]
    username_to_peer = {
        str(item.get("username") or "").strip().lower(): item["peer_id"]
        for item in members
        if str(item.get("username") or "").strip() and str(item.get("username") or "").strip() != "—"
    }
    tg_mode = _tg_web_mode_from_url(group_url or _get_tab_url(server, token, client_id, tab_id))

    attempted = 0
    updated = 0
    opened_peer_ids: list[str] = []
    helper_session: dict[str, Any] = {"tab_id": None}

    try:
        for peer_id in pending_peer_ids:
            attempted += 1
            opened_peer_ids.append(peer_id)
            username, _opened = _read_username_via_helper_tab(
                server=server,
                token=token,
                client_id=client_id,
                base_tab_id=tab_id,
                peer_id=peer_id,
                expected_name=str(members_by_peer[peer_id].get("name") or ""),
                timeout_sec=min(timeout_sec, 8),
                tg_mode=tg_mode,
                helper_session=helper_session,
            )
            if username == "—":
                continue
            key = username.lower()
            existing_peer = username_to_peer.get(key)
            if existing_peer and existing_peer != peer_id:
                print(f"WARN: skip duplicate username {username} for peer {peer_id} (already {existing_peer})")
                continue
            members_by_peer[peer_id]["username"] = username
            username_to_peer[key] = peer_id
            updated += 1
            time.sleep(0.03)
    finally:
        _close_helper_session_best_effort(
            server=server,
            token=token,
            client_id=client_id,
            base_tab_id=tab_id,
            helper_session=helper_session,
            timeout_sec=min(timeout_sec, 4),
        )

    return attempted, updated, opened_peer_ids


def _parse_members(html_payload: str) -> list[dict[str, str]]:
    members: list[dict[str, str]] = []
    seen_peer_ids: set[str] = set()

    members_section = ""
    section_start = html_payload.find('class="content members-list"')
    if section_start >= 0:
        section_end = len(html_payload)
        for marker in ('<div class="SquareTabList', '<button type="button" class="Button FloatingActionButton'):
            pos = html_payload.find(marker, section_start)
            if pos >= 0:
                section_end = min(section_end, pos)
        members_section = html_payload[section_start:section_end]

    if members_section:
        for match in re.finditer(r'data-peer-id="([^"]+)"', members_section):
            peer_id = match.group(1)
            if peer_id.startswith("-") or peer_id in seen_peer_ids:
                continue

            block_start = max(0, match.start() - 220)
            block_html = members_section[block_start : match.start() + 1800]
            if "contact-list-item" not in block_html:
                continue

            name = ""
            name_match = re.search(r'<h3[^>]*class="[^"]*fullName[^"]*"[^>]*>(.*?)</h3>', block_html, flags=re.S)
            if name_match:
                name = _compact(name_match.group(1))
            if not name:
                avatar_name = re.search(r'<img[^>]*class="[^"]*Avatar__media[^"]*"[^>]*alt="([^"]+)"', block_html, flags=re.S)
                if avatar_name:
                    name = _compact(avatar_name.group(1))
            if not name:
                continue

            status = "—"
            status_match = re.search(r'<span class="user-status"[^>]*>(.*?)</span>', block_html, flags=re.S)
            if status_match:
                parsed_status = _compact(status_match.group(1))
                if parsed_status:
                    status = parsed_status

            role = "—"
            role_match = re.search(r'<div class="hJUqHi4B[^"]*"[^>]*>(.*?)</div>', block_html, flags=re.S)
            if role_match:
                parsed_role = _compact(role_match.group(1))
                if parsed_role:
                    role = parsed_role

            members.append(
                {
                    "peer_id": peer_id,
                    "name": name,
                    "status": status,
                    "role": role,
                    "username": _extract_username(block_html),
                }
            )
            seen_peer_ids.add(peer_id)

    rows = re.findall(
        r'<a class="[^"]*chatlist-chat-abitbigger[^"]*"[^>]*data-peer-id="([^"]+)"[^>]*>(.*?)</a>',
        html_payload,
        flags=re.S,
    )

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


def _write_markdown(path: Path, members: list[dict[str, str]], group_url: str, source_mode: str) -> None:
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = []
    history_authors_mode = "history-authors" in source_mode
    lines.append("# Username из сообщений Telegram" if history_authors_mode else "# Участники Telegram-группы")
    lines.append("")
    lines.append(f"Источник: `{group_url}`")
    lines.append(f"Режим сбора: `{source_mode}`")
    lines.append(f"Дата выгрузки: {ts}")
    if history_authors_mode:
        lines.append(f"Количество уникальных username из сообщений: **{len(members)}**")
    else:
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
    if "preview" in source_mode:
        lines.append(
            "Примечание: Telegram Web в этом чате отдал только preview админов/модераторов из Group Info, а не полный каталог участников."
        )
    lines.append("Примечание: телефоны намеренно не собираются этим скриптом.")
    lines.append("Для более полного сбора @username используйте флаг `--deep-usernames`.")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _collect_username_rows(members: list[dict[str, str]], *, include_bots: bool = False) -> list[dict[str, str]]:
    seen: set[str] = set()
    rows: list[dict[str, str]] = []
    for item in members:
        if not include_bots and _is_probable_bot_member(item):
            continue
        username = _normalize_username(str(item.get("username") or "").strip())
        if username == "—":
            continue
        key = username.lower()
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "username": username,
                "peer_id": str(item.get("peer_id") or "—").strip() or "—",
                "name": str(item.get("name") or "—").strip() or "—",
                "status": str(item.get("status") or "—").strip() or "—",
                "role": str(item.get("role") or "—").strip() or "—",
            }
        )
    return rows


def _write_username_sidecars(
    output_path: Path,
    username_rows: list[dict[str, str]],
    group_url: str,
    source_mode: str,
) -> dict[str, Path]:
    base_path = output_path.with_suffix("")
    txt_path = base_path.parent / f"{base_path.name}_usernames.txt"
    json_path = base_path.parent / f"{base_path.name}_usernames.json"

    usernames = [row["username"] for row in username_rows]
    txt_body = "\n".join(usernames)
    if usernames:
        txt_body += "\n"
    txt_path.write_text(txt_body, encoding="utf-8")

    payload = {
        "group_url": group_url,
        "source_mode": source_mode,
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "count": len(username_rows),
        "usernames": usernames,
        "rows": username_rows,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "usernames_txt": txt_path,
        "usernames_json": json_path,
    }


def _archive_export_copy(
    *,
    archive_dir: Path,
    output_path: Path,
    group_url: str,
    source_mode: str,
    members: list[dict[str, str]],
    sidecar_paths: dict[str, Path] | None = None,
) -> dict[str, Path]:
    archive_dir.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    group_slug = _path_slug(_dialog_fragment_from_url(group_url) or group_url or "group", fallback="group")
    mode_slug = _path_slug(source_mode, fallback="mode")
    archive_path = archive_dir / f"{timestamp}_{mode_slug}_{group_slug}_{len(members)}.md"
    shutil.copyfile(output_path, archive_path)
    archived_paths: dict[str, Path] = {"markdown": archive_path}

    for key, source_path in (sidecar_paths or {}).items():
        if not source_path.exists():
            continue
        archive_sidecar = archive_dir / f"{timestamp}_{mode_slug}_{group_slug}_{len(members)}_{key}{source_path.suffix}"
        shutil.copyfile(source_path, archive_sidecar)
        archived_paths[key] = archive_sidecar

    index_path = archive_dir / "INDEX.md"
    entry_lines = [
        f"## {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Группа: `{group_url}`",
        f"Режим: `{source_mode}`",
        f"Участников: **{len(members)}**",
        f"Основной файл: `{output_path}`",
        f"Архивная копия: `{archive_path}`",
    ]
    if sidecar_paths and sidecar_paths.get("usernames_txt"):
        entry_lines.append(f"Usernames TXT: `{sidecar_paths['usernames_txt']}`")
    if sidecar_paths and sidecar_paths.get("usernames_json"):
        entry_lines.append(f"Usernames JSON: `{sidecar_paths['usernames_json']}`")
    if archived_paths.get("usernames_txt"):
        entry_lines.append(f"Архив usernames TXT: `{archived_paths['usernames_txt']}`")
    if archived_paths.get("usernames_json"):
        entry_lines.append(f"Архив usernames JSON: `{archived_paths['usernames_json']}`")
    entry_lines.append("")
    entry_text = "\n".join(entry_lines).rstrip() + "\n"
    if index_path.exists():
        previous = index_path.read_text(encoding="utf-8").rstrip()
        prefix = f"{previous}\n\n" if previous else ""
        index_path.write_text(prefix + entry_text, encoding="utf-8")
    else:
        index_path.write_text("# Telegram Export Index\n\n" + entry_text, encoding="utf-8")
    return archived_paths


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
        default="both",
        help="Источник участников: info, chat, или both (объединить info + chat без дублей; default: both).",
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
        "--chat-min-members",
        type=int,
        default=0,
        help="Минимум уникальных людей в chat-режиме; пока меньше, ранняя остановка по no-growth отключается.",
    )
    parser.add_argument(
        "--max-members",
        type=int,
        default=0,
        help="Мягкий лимит на итоговое число участников в отчёте (0 = без ограничения).",
    )
    parser.add_argument(
        "--chat-auto-extra-steps",
        type=int,
        default=CHAT_AUTO_EXTRA_DEFAULT,
        help="Сколько дополнительных chat-скроллов разрешено после --chat-scroll-steps, если ещё появляются новые участники.",
    )
    parser.add_argument(
        "--chat-deep-mode",
        choices=("mention", "url", "full"),
        default="url",
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
        "--force-navigate",
        action="store_true",
        help="Принудительно навигировать вкладку Telegram на --group-url перед сбором.",
    )
    parser.add_argument(
        "--identity-history",
        default="",
        help=(
            "JSON-файл с историей peer_id <-> username для защиты от ложных переназначений. "
            "Если не задан, используется per-chat history в <archive-dir>/state/."
        ),
    )
    parser.add_argument(
        "--discovery-state",
        default="",
        help="JSON-файл с историей discovery-проходов чата.",
    )
    parser.add_argument(
        "--stats-output",
        default="",
        help="JSON-файл для сохранения телеметрии экспорта (опционально).",
    )
    parser.add_argument(
        "--archive-dir",
        default=str(DEFAULT_ARCHIVE_DIR),
        help=f"Каталог для архивных копий экспортов и индекса (default: {DEFAULT_ARCHIVE_DIR}).",
    )
    parser.add_argument(
        "--include-bots",
        action="store_true",
        help="Не исключать bot-аккаунты из итогового списка @username.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    token = args.token or os.getenv(TOKEN_ENV, "") or DEFAULT_TOKEN
    server = _norm_server(args.server)
    group_url = args.group_url
    out_path = Path(args.output).expanduser()
    archive_dir_value = str(args.archive_dir or "").strip()
    archive_dir_path = Path(archive_dir_value).expanduser() if archive_dir_value else None
    stats_output_path = Path(args.stats_output).expanduser() if args.stats_output else None
    discovery_state_path = Path(args.discovery_state).expanduser() if args.discovery_state else None
    identity_history_path: Path | None = None
    historical_username_to_peer: dict[str, str] = {}
    historical_peer_to_username: dict[str, str] = {}
    discovery_state = _load_discovery_state(discovery_state_path)
    source_label = args.source
    chat_stats: dict[str, Any] = {}
    info_stats: dict[str, Any] = {}
    members: list[dict[str, str]] = []
    attempted = 0
    updated = 0
    history_backfilled = 0
    output_usernames_restored = 0
    output_usernames_cleared = 0

    try:
        clients_response = _http_json_retry(server, token, "GET", "/api/clients")
        clients = clients_response.get("clients") or []
        if not isinstance(clients, list):
            raise RuntimeError("Invalid clients payload from hub")

        client_id, tab_id = _find_tab(
            clients=clients,
            client_id=args.client_id or None,
            tab_id=args.tab_id,
            url_pattern=group_url,
        )
        supports_click_menu_text = _client_supports_content_command(clients, client_id, "click_menu_text")
        if (
            args.deep_usernames
            and args.source in ("chat", "both")
            and args.chat_deep_mode in ("mention", "full")
            and not supports_click_menu_text
        ):
            print(
                "WARN: current bridge runtime does not advertise click_menu_text. "
                "Telegram mention-deep will use legacy text-click fallback until the unpacked extension is reloaded.",
                file=sys.stderr,
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
            if CHAT_MENTION_TRACE:
                print("INFO: chat mention trace stage force-navigate:start")
            _navigate_to_group_if_requested(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=tab_id,
                group_url=group_url,
                timeout_sec=max(args.timeout, 5),
            )
            if CHAT_MENTION_TRACE:
                print("INFO: chat mention trace stage force-navigate:done")

        identity_history_path = (
            Path(args.identity_history).expanduser()
            if args.identity_history
            else _default_identity_history_path(archive_dir_path, group_url)
        )
        historical_username_to_peer, historical_peer_to_username = _load_identity_history(
            identity_history_path,
            archive_dir=archive_dir_path,
            group_url=group_url,
        )

        info_members: list[dict[str, str]] = []
        chat_members: list[dict[str, str]] = []
        info_mode_ready = False
        info_view_kind = ""

        if args.source in ("info", "both"):
            info_mode_ready = _open_info_members_view(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=tab_id,
                timeout_sec=max(args.timeout, 5),
            )
            if not info_mode_ready:
                if args.source == "info":
                    raise RuntimeError(
                        "Не удалось открыть Group Info -> Members автоматически. "
                        "Откройте список участников вручную и повторите."
                    )
                print(
                    "WARN: не удалось открыть Group Info -> Members автоматически; "
                    "продолжаю в chat-only fallback для source=both.",
                    file=sys.stderr,
                )
            else:
                info_members, info_stats = _collect_members_from_info(
                    server=server,
                    token=token,
                    client_id=client_id,
                    tab_id=tab_id,
                    timeout_sec=max(args.timeout, 5),
                    scroll_steps=max(args.info_scroll_steps, 0),
                    group_url=group_url,
                    deep_usernames=bool(args.deep_usernames),
                )
                info_view_kind = str(info_stats.get("view_kind") or "")
                if not info_members:
                    if args.source == "info":
                        raise RuntimeError(
                            "Не найден список участников. Откройте в Telegram Web: Group Info -> Members, "
                            "затем повторите команду."
                        )
                    print(
                        "WARN: info mode не вернул участников; продолжаю в chat-only fallback для source=both.",
                        file=sys.stderr,
                    )
                total_hint = int(info_stats.get("total_hint", 0))
                if total_hint and len(info_members) < total_hint:
                    if info_view_kind == "preview":
                        print(
                            f"WARN: Telegram Web показал только preview {len(info_members)} из примерно {total_hint} участников. "
                            "Для этой группы info-режим даёт только админов/модераторов/ботов из Group Info; "
                            "используйте --source both, чтобы дополнить результат участниками из чата.",
                            file=sys.stderr,
                        )
                    else:
                        print(
                            f"WARN: в DOM загружено только {len(info_members)} из примерно {total_hint} участников. "
                            "Прокрутите список Members в Telegram Web и повторите выгрузку для более полного результата.",
                            file=sys.stderr,
                        )
                if info_members:
                    if info_view_kind == "preview":
                        print(
                            f"INFO: info mode collected {info_stats.get('unique_members', len(info_members))} visible preview users "
                            f"after {info_stats.get('scroll_steps_done', 0)} downward scroll steps"
                        )
                    else:
                        print(
                            f"INFO: info mode collected {info_stats.get('unique_members', len(info_members))} unique users "
                            f"after {info_stats.get('scroll_steps_done', 0)} downward scroll steps"
                        )

        if args.source in ("chat", "both"):
            # If deep mode requested, apply it to chat collection for both chat and both modes.
            chat_deep = bool(args.deep_usernames)
            chat_scroll_steps_effective = max(args.chat_scroll_steps, 0)
            if chat_deep and chat_scroll_steps_effective < 2:
                chat_scroll_steps_effective = 2
                print("INFO: deep mode -> using 3 chat passes (2 upward scrolls) to refresh visible users")
            if CHAT_MENTION_TRACE:
                print("INFO: chat mention trace stage chat-collect:start")
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
                auto_extra_steps=max(args.chat_auto_extra_steps, 0),
                chat_deep_mode=args.chat_deep_mode,
                chat_target_peer_id=str(args.chat_target_peer_id or "").strip(),
                chat_target_name=str(args.chat_target_name or "").strip(),
                supports_click_menu_text=supports_click_menu_text,
                historical_username_to_peer=historical_username_to_peer,
                historical_peer_to_username=historical_peer_to_username,
                discovery_state=discovery_state,
            )
            if CHAT_MENTION_TRACE:
                print("INFO: chat mention trace stage chat-collect:done")
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
            if info_members:
                source_label = "both(info-preview+chat)" if info_view_kind == "preview" else "both(info+chat)"
            else:
                source_label = "chat(fallback-from-both)"
        elif args.source == "info":
            members = info_members
            source_label = "info-preview" if info_view_kind == "preview" else "info"
        else:
            members = chat_members
            source_label = "chat"

        if not members:
            raise RuntimeError(
                "Не удалось собрать участников. Откройте группу/список участников и повторите."
            )

        members = _dedupe_members(members)
        history_backfilled, history_conflicts = _backfill_usernames_from_history(
            members=members,
            historical_username_to_peer=historical_username_to_peer,
            historical_peer_to_username=historical_peer_to_username,
        )
        history_prefilled = int(chat_stats.get("history_prefilled", 0))
        history_prefill_conflicts = int(chat_stats.get("history_prefill_conflicts", 0))
        if history_prefilled:
            print(f"INFO: pre-deep history backfill restored {history_prefilled} username(s)")
        if history_prefill_conflicts:
            print(f"WARN: pre-deep history backfill detected {history_prefill_conflicts} conflict(s)")
        history_backfilled += history_prefilled
        history_conflicts += history_prefill_conflicts
        if history_backfilled:
            print(f"INFO: history backfill restored {history_backfilled} username(s)")
        if history_conflicts:
            print(f"WARN: history backfill detected {history_conflicts} conflict(s)")

        if args.deep_usernames:
            if args.source in ("chat", "both"):
                chat_attempted = int(chat_stats.get("deep_attempted", 0))
                chat_updated = int(chat_stats.get("deep_updated", 0))
                runtime_limited = bool(int(chat_stats.get("runtime_limited", 0)))
                mention_attempted = 0
                mention_updated = 0
                unresolved = sum(1 for item in members if str(item.get("username") or "—").strip() == "—")
                if unresolved > 0 and not runtime_limited and args.chat_deep_mode in ("url", "full"):
                    mention_runtime_budget = min(float(max(args.chat_max_runtime, 5)), 30.0)
                    if CHAT_DEEP_STEP_MAX_SEC > 0:
                        mention_runtime_budget = min(mention_runtime_budget, max(6.0, CHAT_DEEP_STEP_MAX_SEC))
                    mention_runtime_budget = max(6.0, mention_runtime_budget)
                    mention_attempted, mention_updated = _enrich_chat_usernames_via_mentions(
                        server=server,
                        token=token,
                        client_id=client_id,
                        tab_id=tab_id,
                        timeout_sec=max(args.timeout, 5),
                        group_url=group_url,
                        members=members,
                        deep_limit=max(args.chat_deep_limit, 0),
                        discovery_state=discovery_state,
                        max_runtime_sec=mention_runtime_budget,
                    )
                    if mention_attempted:
                        print(
                            f"INFO: chat mention deep done: processed {mention_attempted}, "
                            f"filled {mention_updated}"
                        )
                elif runtime_limited:
                    print("INFO: skip mention deep because chat runtime limit was reached")
                elif unresolved > 0 and args.chat_deep_mode == "mention":
                    print("INFO: skip extra mention-deep pass in mention mode")

                attempted += chat_attempted + mention_attempted
                updated += chat_updated + mention_updated
                members = _dedupe_members(members)

            if args.source in ("info", "both"):
                attempted += int(info_stats.get("deep_attempted", 0))
                updated += int(info_stats.get("deep_updated", 0))

            print(f"INFO: deep mode processed {attempted} profiles, filled {updated} usernames")

        output_usernames_restored, output_usernames_cleared = _sanitize_member_usernames_for_output(
            members=members,
            historical_username_to_peer=historical_username_to_peer,
            historical_peer_to_username=historical_peer_to_username,
        )
        if output_usernames_restored > 0:
            print(f"INFO: output sanitize restored {output_usernames_restored} historical username(s)")
        if output_usernames_cleared > 0:
            print(f"WARN: output sanitize cleared {output_usernames_cleared} conflicting username(s)")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        _write_markdown(out_path, members, group_url, source_label)
        _save_discovery_state(discovery_state_path, discovery_state)
        _write_stats_output(
            stats_output_path,
            _build_export_stats_payload(
                status="completed",
                group_url=group_url,
                source=args.source,
                source_label=source_label,
                out_path=out_path,
                members=members,
                info_stats=info_stats,
                chat_stats=chat_stats,
                deep_usernames=bool(args.deep_usernames),
                max_members=max(args.max_members, 0),
                deep_attempted_total=attempted,
                deep_updated_total=updated,
                history_backfilled_total=history_backfilled,
                output_usernames_restored_total=output_usernames_restored,
                output_usernames_cleared_total=output_usernames_cleared,
            ),
        )
        username_rows = _collect_username_rows(members, include_bots=bool(args.include_bots))
        if not args.include_bots:
            skipped_bot_usernames = sum(
                1
                for item in members
                if _normalize_username(str(item.get("username") or "").strip()) != "—" and _is_probable_bot_member(item)
            )
            if skipped_bot_usernames > 0:
                print(f"INFO: filtered out {skipped_bot_usernames} bot username(s) from sidecars")
        username_sidecars = _write_username_sidecars(
            out_path,
            username_rows,
            group_url,
            source_label,
        )
        _save_identity_history(
            identity_history_path,
            members=members,
            historical_username_to_peer=historical_username_to_peer,
            historical_peer_to_username=historical_peer_to_username,
        )
        archive_paths: dict[str, Path] | None = None
        if archive_dir_value:
            archive_paths = _archive_export_copy(
                archive_dir=archive_dir_path or Path(archive_dir_value).expanduser(),
                output_path=out_path,
                group_url=group_url,
                source_mode=source_label,
                members=members,
                sidecar_paths=username_sidecars,
            )

        print(f"OK: saved {len(members)} members to {out_path}")
        print(f"OK: saved {len(username_rows)} usernames to {username_sidecars['usernames_txt']}")
        print(f"OK: saved username metadata to {username_sidecars['usernames_json']}")
        if archive_paths is not None:
            print(f"OK: archived copy saved to {archive_paths['markdown']}")
            if archive_paths.get("usernames_txt"):
                print(f"OK: archived usernames txt saved to {archive_paths['usernames_txt']}")
            if archive_paths.get("usernames_json"):
                print(f"OK: archived usernames json saved to {archive_paths['usernames_json']}")
        return 0
    except Exception as exc:  # noqa: BLE001
        _write_stats_output(
            stats_output_path,
            _build_export_stats_payload(
                status="failed",
                group_url=group_url,
                source=args.source,
                source_label=source_label,
                out_path=out_path,
                members=members,
                info_stats=info_stats,
                chat_stats=chat_stats,
                deep_usernames=bool(args.deep_usernames),
                max_members=max(args.max_members, 0),
                deep_attempted_total=attempted,
                deep_updated_total=updated,
                history_backfilled_total=history_backfilled,
                output_usernames_restored_total=output_usernames_restored,
                output_usernames_cleared_total=output_usernames_cleared,
                error=str(exc),
            ),
        )
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
