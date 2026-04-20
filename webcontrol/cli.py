from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import HubConfig
from .server import run_server
from .store import TERMINAL_COMMAND_STATUSES
from .utils import compact

DEFAULT_SERVER = "http://127.0.0.1:8765"
DEFAULT_TOKEN_ENV = "SITECTL_TOKEN"
DEFAULT_QUICKSTART_TOKEN = "local-bridge-quickstart-2026"


def _norm_server(url: str) -> str:
    return url.rstrip("/")


def _http_json(
    *,
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
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            if not raw:
                return {"ok": True}
            return json.loads(raw)
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
        raise RuntimeError(f"HTTP {exc.code}: {raw or exc.reason}") from exc
    except URLError as exc:
        raise RuntimeError(f"Network error: {exc.reason}") from exc


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _load_json_file(path: str) -> dict[str, Any]:
    content = Path(path).read_text(encoding="utf-8")
    payload = json.loads(content)
    if not isinstance(payload, dict):
        raise ValueError("JSON payload must be an object")
    return payload


def _wait_command(server: str, token: str, command_id: str, timeout_sec: int, interval_sec: float) -> dict[str, Any]:
    deadline = time.time() + timeout_sec
    while True:
        response = _http_json(server=server, token=token, method="GET", path=f"/api/commands/{command_id}")
        command = response.get("command") or {}
        status = command.get("status")
        if status in TERMINAL_COMMAND_STATUSES:
            return command
        if time.time() >= deadline:
            return command
        time.sleep(interval_sec)


def _extract_runtime(args: argparse.Namespace) -> tuple[str, str]:
    token = args.token or os.getenv(DEFAULT_TOKEN_ENV, "") or DEFAULT_QUICKSTART_TOKEN
    server = _norm_server(args.server or DEFAULT_SERVER)
    return server, token


def _get_clients(server: str, token: str) -> list[dict[str, Any]]:
    response = _http_json(server=server, token=token, method="GET", path="/api/clients")
    clients = response.get("clients")
    if not isinstance(clients, list):
        return []
    return clients


def _pick_client(clients: list[dict[str, Any]], requested_client_id: str | None = None) -> dict[str, Any]:
    if not clients:
        raise RuntimeError("No connected browser clients. Check the extension and run `sitectl clients`.")

    if requested_client_id:
        requested = requested_client_id.strip()
        for client in clients:
            if str(client.get("client_id", "")).strip() == requested:
                return client
        raise RuntimeError(f"Browser client not found: {requested}")

    ordered = sorted(clients, key=lambda item: str(item.get("last_seen", "")), reverse=True)
    return ordered[0]


def _extract_command_result(command: dict[str, Any], client_id: str) -> dict[str, Any]:
    deliveries = command.get("deliveries")
    if not isinstance(deliveries, dict):
        return {}
    delivery = deliveries.get(client_id)
    if not isinstance(delivery, dict):
        return {}
    result = delivery.get("result")
    return result if isinstance(result, dict) else {}


def _write_data_url_to_file(data_url: str, output_path: str) -> str:
    prefix = "data:image/png;base64,"
    if not data_url.startswith(prefix):
        raise ValueError("Screenshot payload is not a PNG data URL")

    raw = base64.b64decode(data_url[len(prefix) :])
    path = Path(output_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return str(path)


def _tabs_for_window(client: dict[str, Any], window_id: int) -> list[dict[str, Any]]:
    tabs = client.get("tabs")
    if not isinstance(tabs, list):
        return []
    return [tab for tab in tabs if int(tab.get("windowId", -1)) == int(window_id)]


def _find_browser_tab(client: dict[str, Any], target: dict[str, Any]) -> dict[str, Any] | None:
    tabs = client.get("tabs")
    if not isinstance(tabs, list) or not tabs:
        return None

    tab_id = target.get("tab_id")
    if isinstance(tab_id, int):
        for tab in tabs:
            if int(tab.get("id", -1)) == tab_id:
                return tab

    url_pattern = str(target.get("url_pattern") or "").strip()
    if url_pattern:
        for tab in tabs:
            if url_pattern in str(tab.get("url") or ""):
                return tab

    if target.get("active", True):
        for tab in tabs:
            if bool(tab.get("active")):
                return tab

    return tabs[0]


def _tab_present(client: dict[str, Any], tab_id: int) -> bool:
    tabs = client.get("tabs")
    if not isinstance(tabs, list):
        return False
    for tab in tabs:
        if int(tab.get("id", -1)) == int(tab_id):
            return True
    return False


def _tab_cycle_plan(window_tabs: list[dict[str, Any]], target_tab_id: int) -> tuple[int, bool] | None:
    if not window_tabs:
        return None
    active_index = None
    target_index = None
    for index, tab in enumerate(window_tabs):
        if bool(tab.get("active")):
            active_index = index
        if int(tab.get("id", -1)) == int(target_tab_id):
            target_index = index
    if active_index is None or target_index is None:
        return None
    if active_index == target_index:
        return (0, False)
    total = len(window_tabs)
    forward = (target_index - active_index) % total
    backward = (active_index - target_index) % total
    return (forward, False) if forward <= backward else (backward, True)


def _absolute_tab_hotkey(window_tabs: list[dict[str, Any]], target_tab_id: int) -> str | None:
    for index, tab in enumerate(window_tabs):
        if int(tab.get("id", -1)) != int(target_tab_id):
            continue
        if index <= 7:
            return str(index + 1)
        if index == len(window_tabs) - 1:
            return "9"
        return None
    return None


def _parse_wmctrl_windows(output: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for raw_line in str(output or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        window_id, desktop, wm_class, host, title = parts
        rows.append(
            {
                "window_id": window_id,
                "desktop": desktop,
                "wm_class": wm_class,
                "host": host,
                "title": title,
            }
        )
    return rows


def _parse_wmctrl_geometry_windows(output: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw_line in str(output or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(None, 7)
        if len(parts) < 8:
            continue
        window_id, desktop, x, y, width, height, host, title = parts
        try:
            rows.append(
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
    return rows


def _find_x11_browser_window(window_tabs: list[dict[str, Any]]) -> str:
    if sys.platform != "linux" or not os.environ.get("DISPLAY"):
        return ""
    try:
        proc = subprocess.run(["wmctrl", "-lx"], check=False, capture_output=True, text=True)
    except OSError:
        return ""
    windows = _parse_wmctrl_windows(proc.stdout)
    preferred_titles: list[str] = []
    for tab in window_tabs:
        title = str(tab.get("title") or "").strip()
        if title:
            preferred_titles.append(title)
    active_titles = [str(tab.get("title") or "").strip() for tab in window_tabs if bool(tab.get("active"))]
    title_candidates = active_titles + [title for title in preferred_titles if title not in active_titles]

    for title in title_candidates:
        for window in windows:
            wm_class = str(window.get("wm_class") or "").lower()
            full_title = str(window.get("title") or "")
            if "chrome" not in wm_class:
                continue
            if title and title in full_title:
                return str(window.get("window_id") or "")
    return ""


def _find_x11_browser_window_geometry(window_tabs: list[dict[str, Any]]) -> dict[str, Any] | None:
    if sys.platform != "linux" or not os.environ.get("DISPLAY"):
        return None
    try:
        proc = subprocess.run(["wmctrl", "-lG"], check=False, capture_output=True, text=True)
    except OSError:
        return None
    windows = _parse_wmctrl_geometry_windows(proc.stdout)
    if not windows:
        return None

    preferred_titles: list[str] = []
    for tab in window_tabs:
        title = str(tab.get("title") or "").strip()
        if title:
            preferred_titles.append(title)
    active_titles = [str(tab.get("title") or "").strip() for tab in window_tabs if bool(tab.get("active"))]
    title_candidates = active_titles + [title for title in preferred_titles if title not in active_titles]

    for title in title_candidates:
        for window in windows:
            full_title = str(window.get("title") or "")
            if title and title in full_title:
                return window

    for window in windows:
        full_title = str(window.get("title") or "")
        if "chrome" in full_title.lower():
            return window
    return None


def _x11_window_click_point(window: dict[str, Any], *, x_ratio: float, y_ratio: float) -> tuple[int, int] | None:
    try:
        x = int(window.get("x", 0))
        y = int(window.get("y", 0))
        width = int(window.get("width", 0))
        height = int(window.get("height", 0))
        xr = float(x_ratio)
        yr = float(y_ratio)
    except (TypeError, ValueError):
        return None
    if width <= 2 or height <= 2:
        return None
    xr = min(max(xr, 0.0), 1.0)
    yr = min(max(yr, 0.0), 1.0)
    target_x = x + max(1, min(int(width * xr), width - 2))
    target_y = y + max(1, min(int(height * yr), height - 2))
    return target_x, target_y


def _x11_send_keys(window_id: str, sequences: list[list[str]]) -> bool:
    if not window_id or sys.platform != "linux" or not os.environ.get("DISPLAY"):
        return False
    try:
        from Xlib import X, XK, display  # type: ignore
        from Xlib.ext import xtest  # type: ignore
    except Exception:
        return False


def _x11_click_window(window: dict[str, Any], *, x_ratio: float, y_ratio: float, button: int = 1) -> dict[str, Any] | None:
    window_id = str(window.get("window_id") or "").strip()
    point = _x11_window_click_point(window, x_ratio=x_ratio, y_ratio=y_ratio)
    if not window_id or point is None or sys.platform != "linux" or not os.environ.get("DISPLAY"):
        return None
    if int(button) < 1:
        return None

    try:
        from Xlib import X, display  # type: ignore
        from Xlib.ext import xtest  # type: ignore
    except Exception:
        return None

    try:
        subprocess.run(["wmctrl", "-ia", window_id], check=False)
        time.sleep(0.18)
        d = display.Display()
        root = d.screen().root
        pointer = root.query_pointer()
        original_x = int(pointer.root_x)
        original_y = int(pointer.root_y)
        target_x, target_y = point

        xtest.fake_input(d, X.MotionNotify, x=target_x, y=target_y)
        d.sync()
        time.sleep(0.05)
        xtest.fake_input(d, X.ButtonPress, int(button))
        xtest.fake_input(d, X.ButtonRelease, int(button))
        d.sync()
        time.sleep(0.08)

        xtest.fake_input(d, X.MotionNotify, x=original_x, y=original_y)
        d.sync()
        return {
            "windowId": window_id,
            "x": target_x,
            "y": target_y,
            "button": int(button),
            "via": "x11_click",
        }
    except Exception:
        return None

    try:
        subprocess.run(["wmctrl", "-ia", window_id], check=False)
        time.sleep(0.18)
        d = display.Display()

        def _press(name: str, pressed: bool) -> None:
            keysym = XK.string_to_keysym(name)
            if keysym == 0:
                raise RuntimeError(f"Unknown X11 key: {name}")
            keycode = d.keysym_to_keycode(keysym)
            xtest.fake_input(d, X.KeyPress if pressed else X.KeyRelease, keycode)

        for sequence in sequences:
            if not sequence:
                continue
            modifiers = sequence[:-1]
            main_key = sequence[-1]
            for name in modifiers:
                _press(name, True)
            _press(main_key, True)
            _press(main_key, False)
            for name in reversed(modifiers):
                _press(name, False)
            d.sync()
            time.sleep(0.08)
        return True
    except Exception:
        return False


def _find_client_by_id(clients: list[dict[str, Any]], client_id: str) -> dict[str, Any] | None:
    for client in clients:
        if str(client.get("client_id") or "").strip() == client_id:
            return client
    return None


def _find_created_tab(
    client: dict[str, Any],
    *,
    window_id: int,
    previous_tab_ids: set[int],
    preferred_url: str = "",
    require_active: bool = False,
) -> dict[str, Any] | None:
    candidates = [
        tab
        for tab in _tabs_for_window(client, window_id)
        if int(tab.get("id", -1)) not in previous_tab_ids
    ]
    if require_active:
        candidates = [tab for tab in candidates if bool(tab.get("active"))]
    if not candidates:
        return None

    preferred_url = preferred_url.strip()
    if preferred_url:
        for tab in candidates:
            if preferred_url in str(tab.get("url") or ""):
                return tab
    for tab in candidates:
        if bool(tab.get("active")):
            return tab
    return candidates[0]


def _wait_for_tab_state(
    *,
    server: str,
    token: str,
    client_id: str,
    predicate,
    timeout_sec: float,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    deadline = time.time() + max(timeout_sec, 0.5)
    while time.time() < deadline:
        clients = _get_clients(server, token)
        client = _find_client_by_id(clients, client_id)
        if client:
            matched = predicate(client)
            if matched is not None:
                return client, matched
        time.sleep(0.2)
    return None, None


def _wait_for_tab_absent(
    *,
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    timeout_sec: float,
) -> bool:
    _, payload = _wait_for_tab_state(
        server=server,
        token=token,
        client_id=client_id,
        timeout_sec=timeout_sec,
        predicate=lambda current_client: {"closed": True} if not _tab_present(current_client, tab_id) else None,
    )
    return bool(payload)


def _synthetic_command_record(client_id: str, *, data: dict[str, Any] | None = None, error: dict[str, Any] | None = None) -> dict[str, Any]:
    ok = error is None
    return {
        "status": "completed" if ok else "failed",
        "deliveries": {
            client_id: {
                "result": {
                    "ok": ok,
                    "status": "completed" if ok else "failed",
                    "data": data,
                    "error": error,
                }
            }
        },
    }


def _browser_result_error_message(command: dict[str, Any], client_id: str) -> str:
    result = _extract_command_result(command, client_id)
    error = result.get("error") if isinstance(result, dict) else None
    if isinstance(error, dict):
        return str(error.get("message") or error.get("error") or "").strip()
    return str(error or "").strip()


def _annotate_stale_extension_hint(action: str, client_id: str, command_record: dict[str, Any]) -> dict[str, Any]:
    if action not in {"open", "new-tab", "reload", "activate", "close-tab"}:
        return command_record
    if command_record.get("status") == "completed":
        return command_record

    result = _extract_command_result(command_record, client_id)
    error = result.get("error")
    message = _browser_result_error_message(command_record, client_id)
    if "Unsupported command type in content script" not in message:
        return command_record
    if not isinstance(error, dict):
        return command_record

    error = dict(error)
    error.setdefault(
        "hint",
        "Похоже, браузер работает на устаревшем runtime расширения. Перезагрузите unpacked extension в chrome://extensions.",
    )
    result["error"] = error

    deliveries = command_record.get("deliveries")
    if isinstance(deliveries, dict):
        delivery = deliveries.get(client_id)
        if isinstance(delivery, dict):
            current = delivery.get("result")
            if isinstance(current, dict):
                current["error"] = error
    return command_record


def _x11_activate_tab_fallback(
    *,
    server: str,
    token: str,
    client: dict[str, Any],
    target: dict[str, Any],
    wait_sec: int,
) -> dict[str, Any] | None:
    target_tab = _find_browser_tab(client, target)
    if not target_tab:
        return None
    window_id = int(target_tab.get("windowId", -1))
    window_tabs = _tabs_for_window(client, window_id)
    if not window_tabs:
        return None
    x11_window_id = _find_x11_browser_window(window_tabs)
    if not x11_window_id:
        return None

    plan = _tab_cycle_plan(window_tabs, int(target_tab.get("id", -1)))
    if plan is None:
        return None
    steps, reverse = plan
    if steps == 0:
        return _synthetic_command_record(
            str(client.get("client_id") or "").strip(),
            data={"tabId": target_tab.get("id"), "active": True, "via": "x11_fallback"},
        )
    key_sequence = ["Control_L", "Prior"] if reverse else ["Control_L", "Next"]
    sequences = [key_sequence] * steps

    if not _x11_send_keys(x11_window_id, sequences):
        return None

    client_id = str(client.get("client_id") or "").strip()
    _, activated_tab = _wait_for_tab_state(
        server=server,
        token=token,
        client_id=client_id,
        timeout_sec=max(wait_sec, 3),
        predicate=lambda current_client: next(
            (
                tab
                for tab in _tabs_for_window(current_client, window_id)
                if int(tab.get("id", -1)) == int(target_tab.get("id", -1)) and bool(tab.get("active"))
            ),
            None,
        ),
    )
    if not activated_tab:
        return None
    return _synthetic_command_record(
        client_id,
        data={"tabId": activated_tab.get("id"), "active": True, "via": "x11_fallback"},
    )


def _x11_new_tab_fallback(
    *,
    server: str,
    token: str,
    client: dict[str, Any],
    target: dict[str, Any],
    url: str,
    background: bool,
    timeout_ms: int,
    wait_sec: int,
    poll_interval: float,
) -> dict[str, Any] | None:
    anchor_tab = _find_browser_tab(client, target)
    if not anchor_tab:
        return None
    window_id = int(anchor_tab.get("windowId", -1))
    window_tabs = _tabs_for_window(client, window_id)
    if not window_tabs:
        return None
    x11_window_id = _find_x11_browser_window(window_tabs)
    if not x11_window_id:
        return None
    previous_tab_ids = {int(tab.get("id", -1)) for tab in window_tabs}
    previous_active_tab_id = next((int(tab.get("id", -1)) for tab in window_tabs if bool(tab.get("active"))), -1)
    client_id = str(client.get("client_id") or "").strip()

    refreshed_client, new_tab = _wait_for_tab_state(
        server=server,
        token=token,
        client_id=client_id,
        timeout_sec=1.2,
        predicate=lambda current_client: _find_created_tab(
            current_client,
            window_id=window_id,
            previous_tab_ids=previous_tab_ids,
            preferred_url=url,
        ),
    )
    if not refreshed_client or not new_tab:
        if not _x11_send_keys(x11_window_id, [["Control_L", "t"]]):
            return None

        refreshed_client, new_tab = _wait_for_tab_state(
            server=server,
            token=token,
            client_id=client_id,
            timeout_sec=max(wait_sec, 3),
            predicate=lambda current_client: _find_created_tab(
                current_client,
                window_id=window_id,
                previous_tab_ids=previous_tab_ids,
                preferred_url=url,
                require_active=False,
            ),
        )
    if not refreshed_client or not new_tab:
        return None

    navigate_record = _browser_send_command(
        server=server,
        token=token,
        client_id=client_id,
        target={"client_id": client_id, "tab_id": int(new_tab.get("id", -1)), "active": True},
        command={"type": "navigate", "url": url},
        timeout_ms=timeout_ms,
        wait_sec=wait_sec,
        poll_interval=poll_interval,
    )
    if navigate_record.get("status") != "completed":
        return navigate_record

    updated_client, updated_new_tab = _wait_for_tab_state(
        server=server,
        token=token,
        client_id=client_id,
        timeout_sec=max(wait_sec, 3),
        predicate=lambda current_client: _find_browser_tab(
            current_client,
            {"client_id": client_id, "tab_id": int(new_tab.get("id", -1)), "active": False},
        ),
    )
    if updated_client and updated_new_tab:
        new_tab = updated_new_tab
        refreshed_client = updated_client

    if background:
        if previous_active_tab_id > 0:
            updated_tabs = _tabs_for_window(refreshed_client, window_id)
            previous_target = next((tab for tab in updated_tabs if int(tab.get("id", -1)) == previous_active_tab_id), None)
            if previous_target:
                _x11_activate_tab_fallback(
                    server=server,
                    token=token,
                    client=refreshed_client,
                    target={"client_id": client_id, "tab_id": previous_active_tab_id, "active": True},
                    wait_sec=max(3, wait_sec // 2),
                )
    elif not bool(new_tab.get("active")):
        activated = _x11_activate_tab_fallback(
            server=server,
            token=token,
            client=refreshed_client,
            target={"client_id": client_id, "tab_id": int(new_tab.get("id", -1)), "active": True},
            wait_sec=max(3, wait_sec // 2),
        )
        if activated:
            refreshed_client, activated_tab = _wait_for_tab_state(
                server=server,
                token=token,
                client_id=client_id,
                timeout_sec=max(wait_sec, 3),
                predicate=lambda current_client: _find_browser_tab(
                    current_client,
                    {"client_id": client_id, "tab_id": int(new_tab.get("id", -1)), "active": True},
                ),
            )
            if refreshed_client and activated_tab:
                new_tab = activated_tab

    return _synthetic_command_record(
        client_id,
        data={
            "tabId": new_tab.get("id"),
            "windowId": new_tab.get("windowId"),
            "url": url,
            "active": bool(new_tab.get("active")) if not background else False,
            "via": "x11_fallback",
        },
    )


def _x11_close_tab_fallback(
    *,
    server: str,
    token: str,
    client: dict[str, Any],
    target: dict[str, Any],
    wait_sec: int,
) -> dict[str, Any] | None:
    target_tab = _find_browser_tab(client, target)
    client_id = str(client.get("client_id") or "").strip()
    requested_tab_id = target.get("tab_id")
    if not target_tab:
        if isinstance(requested_tab_id, int):
            if _wait_for_tab_absent(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=requested_tab_id,
                timeout_sec=1.0,
            ):
                return _synthetic_command_record(
                    client_id,
                    data={"tabId": requested_tab_id, "closed": True, "via": "postcheck"},
                )
        return None

    tab_id = int(target_tab.get("id", -1))
    window_id = int(target_tab.get("windowId", -1))
    window_tabs = _tabs_for_window(client, window_id)
    x11_window_id = _find_x11_browser_window(window_tabs)
    if not x11_window_id:
        return None

    active_target = target_tab
    if not bool(target_tab.get("active")):
        activated = _x11_activate_tab_fallback(
            server=server,
            token=token,
            client=client,
            target={"client_id": client_id, "tab_id": tab_id, "active": True},
            wait_sec=wait_sec,
        )
        if not activated:
            return None
        refreshed_client, refreshed_tab = _wait_for_tab_state(
            server=server,
            token=token,
            client_id=client_id,
            timeout_sec=max(wait_sec, 3),
            predicate=lambda current_client: _find_browser_tab(
                current_client, {"client_id": client_id, "tab_id": tab_id, "active": True}
            ),
        )
        if not refreshed_client or not refreshed_tab:
            return None
        active_target = refreshed_tab
        refreshed_window_tabs = _tabs_for_window(refreshed_client, window_id)
        refreshed_window_id = _find_x11_browser_window(refreshed_window_tabs)
        if refreshed_window_id:
            x11_window_id = refreshed_window_id

    if not _x11_send_keys(x11_window_id, [["Control_L", "w"]]):
        return None

    if not _wait_for_tab_absent(
        server=server,
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        timeout_sec=max(wait_sec, 3),
    ):
        return None

    return _synthetic_command_record(
        client_id,
        data={
            "tabId": active_target.get("id"),
            "windowId": active_target.get("windowId"),
            "closed": True,
            "via": "x11_fallback",
        },
    )


def _x11_click_fallback(
    *,
    server: str,
    token: str,
    client: dict[str, Any],
    target: dict[str, Any],
    x_ratio: float,
    y_ratio: float,
    button: int,
    wait_sec: int,
) -> dict[str, Any] | None:
    target_tab = _find_browser_tab(client, target)
    if not target_tab:
        return None
    client_id = str(client.get("client_id") or "").strip()
    tab_id = int(target_tab.get("id", -1))
    if tab_id < 0:
        return None
    window_id = int(target_tab.get("windowId", -1))
    window_tabs = _tabs_for_window(client, window_id)

    active_target = target_tab
    if not bool(target_tab.get("active")) and len(window_tabs) > 1:
        activated = _x11_activate_tab_fallback(
            server=server,
            token=token,
            client=client,
            target={"client_id": client_id, "tab_id": tab_id, "active": True},
            wait_sec=wait_sec,
        )
        if not activated:
            return None
        refreshed_client, refreshed_tab = _wait_for_tab_state(
            server=server,
            token=token,
            client_id=client_id,
            timeout_sec=max(wait_sec, 3),
            predicate=lambda current_client: _find_browser_tab(
                current_client, {"client_id": client_id, "tab_id": tab_id, "active": True}
            ),
        )
        if not refreshed_client or not refreshed_tab:
            return None
        client = refreshed_client
        active_target = refreshed_tab
        window_id = int(active_target.get("windowId", -1))
        window_tabs = _tabs_for_window(client, window_id)
    window = _find_x11_browser_window_geometry(window_tabs)
    if not window:
        return None
    data = _x11_click_window(window, x_ratio=x_ratio, y_ratio=y_ratio, button=button)
    if not data:
        return None
    data["tabId"] = tab_id
    data["windowBrowserId"] = window_id
    return _synthetic_command_record(client_id, data=data)


def _maybe_apply_browser_tab_fallback(
    *,
    action: str,
    server: str,
    token: str,
    client: dict[str, Any],
    target: dict[str, Any],
    command: dict[str, Any],
    timeout_ms: int,
    wait_sec: int,
    poll_interval: float,
    command_record: dict[str, Any],
) -> dict[str, Any]:
    if command_record.get("status") == "completed":
        return command_record

    if action == "activate":
        fallback = _x11_activate_tab_fallback(
            server=server,
            token=token,
            client=client,
            target=target,
            wait_sec=wait_sec,
        )
        return _annotate_stale_extension_hint(
            action,
            str(client.get("client_id") or "").strip(),
            fallback or command_record,
        )

    if action == "new-tab":
        fallback = _x11_new_tab_fallback(
            server=server,
            token=token,
            client=client,
            target=target,
            url=str(command.get("url") or ""),
            background=command.get("active") is False,
            timeout_ms=timeout_ms,
            wait_sec=wait_sec,
            poll_interval=poll_interval,
        )
        return _annotate_stale_extension_hint(
            action,
            str(client.get("client_id") or "").strip(),
            fallback or command_record,
        )

    if action == "close-tab":
        fallback = _x11_close_tab_fallback(
            server=server,
            token=token,
            client=client,
            target=target,
            wait_sec=wait_sec,
        )
        return _annotate_stale_extension_hint(
            action,
            str(client.get("client_id") or "").strip(),
            fallback or command_record,
        )

    return _annotate_stale_extension_hint(action, str(client.get("client_id") or "").strip(), command_record)


def _browser_target(args: argparse.Namespace, client_id: str) -> dict[str, Any]:
    return compact(
        {
            "client_id": client_id,
            "tab_id": args.tab_id,
            "url_pattern": args.url_pattern,
            "active": args.active,
        }
    )


def _browser_send_command(
    *,
    server: str,
    token: str,
    client_id: str,
    target: dict[str, Any],
    command: dict[str, Any],
    timeout_ms: int,
    wait_sec: int,
    poll_interval: float,
) -> dict[str, Any]:
    response = _http_json(
        server=server,
        token=token,
        method="POST",
        path="/api/commands",
        payload={
            "issued_by": "browser-cli",
            "timeout_ms": timeout_ms,
            "target": target,
            "command": command,
        },
    )
    if not response.get("ok"):
        raise RuntimeError(str(response))

    command_id = str(response.get("command_id", "")).strip()
    if not command_id:
        raise RuntimeError("Hub did not return command_id")

    return _wait_command(server, token, command_id, timeout_sec=wait_sec, interval_sec=max(poll_interval, 0.1))


def _print_browser_summary(
    *,
    action: str,
    client: dict[str, Any],
    command: dict[str, Any],
    raw: bool,
    output_path: str | None = None,
) -> None:
    success_statuses = {"completed"}
    if raw:
        _print_json(command)
        return

    client_id = str(client.get("client_id", ""))
    result = _extract_command_result(command, client_id)
    data = result.get("data")
    if action == "screenshot" and isinstance(data, dict) and "imageDataUrl" in data:
        data = {
            "tabId": data.get("tabId"),
            "imageDataUrl": "<omitted; use --output to save PNG>",
        }
    payload: dict[str, Any] = {
        "ok": command.get("status") in success_statuses,
        "action": action,
        "client_id": client_id,
        "status": command.get("status"),
        "data": data,
        "error": result.get("error"),
    }
    if output_path:
        payload["output"] = output_path
    _print_json(payload)


def cmd_browser(args: argparse.Namespace) -> int:
    try:
        server, token = _extract_runtime(args)

        if args.browser_action == "clients":
            _print_json({"ok": True, "clients": _get_clients(server, token)})
            return 0

        clients = _get_clients(server, token)

        if args.browser_action == "status":
            selected = _pick_client(clients, args.client_id)
            _print_json(
                {
                    "ok": True,
                    "client": selected,
                    "clients": clients,
                }
            )
            return 0

        if args.browser_action == "tabs":
            selected = _pick_client(clients, args.client_id)
            _print_json(
                {
                    "ok": True,
                    "client_id": selected.get("client_id"),
                    "tabs": selected.get("tabs", []),
                }
            )
            return 0

        client = _pick_client(clients, args.client_id)
        target = _browser_target(args, str(client.get("client_id", "")).strip())

        action = args.browser_action
        command: dict[str, Any]
        output_path: str | None = None

        if action == "x11-click":
            command_record = _x11_click_fallback(
                server=server,
                token=token,
                client=client,
                target=target,
                x_ratio=args.x_ratio,
                y_ratio=args.y_ratio,
                button=args.button,
                wait_sec=args.wait,
            )
            if not command_record:
                raise RuntimeError("X11 click fallback is unavailable for the selected browser tab/window.")
            _print_browser_summary(
                action=action,
                client=client,
                command=command_record,
                raw=args.raw,
            )
            return 0

        if action == "open":
            command = {"type": "navigate", "url": args.url}
        elif action == "new-tab":
            command = {"type": "new_tab", "url": args.url, "active": not args.background}
        elif action == "click":
            command = {"type": "click", "selector": args.selector}
        elif action == "click-text":
            command = {
                "type": "click_text",
                "text": args.text,
                "root_selector": args.root_selector,
                "near_last_context": args.near_last_context,
            }
        elif action == "fill":
            command = {"type": "fill", "selector": args.selector, "value": args.value}
        elif action == "focus":
            command = {"type": "focus", "selector": args.selector}
        elif action == "wait":
            command = {
                "type": "wait_selector",
                "selector": args.selector,
                "timeout_ms": args.command_timeout_ms,
                "visible_only": args.visible_only,
            }
        elif action == "text":
            command = {"type": "extract_text", "selector": args.selector}
        elif action == "html":
            command = {"type": "get_html", "selector": args.selector}
        elif action == "attr":
            command = {"type": "get_attribute", "selector": args.selector, "attribute": args.attribute}
        elif action == "page-url":
            command = {"type": "get_page_url"}
        elif action == "back":
            command = {"type": "back"}
        elif action == "forward":
            command = {"type": "forward"}
        elif action == "reload":
            command = {"type": "reload", "ignore_cache": args.ignore_cache}
        elif action == "activate":
            command = {"type": "activate_tab"}
        elif action == "close-tab":
            command = {"type": "close_tab"}
        elif action == "scroll":
            command = {"type": "scroll", "selector": args.selector, "x": args.x, "y": args.y}
        elif action == "scroll-by":
            command = {"type": "scroll_by", "selector": args.selector, "delta_x": args.dx, "delta_y": args.dy}
        elif action == "press":
            command = {
                "type": "press_key",
                "selector": args.selector,
                "key": args.key,
                "ctrl": args.ctrl,
                "alt": args.alt,
                "shift": args.shift,
                "meta": args.meta,
            }
        elif action == "js":
            command = {"type": "run_script", "script": args.script}
            if args.script_args:
                command["args"] = json.loads(args.script_args)
        elif action == "screenshot":
            command = {"type": "screenshot"}
        else:
            raise ValueError(f"Unsupported browser action: {action}")

        command_record = _browser_send_command(
            server=server,
            token=token,
            client_id=str(client.get("client_id", "")).strip(),
            target=target,
            command=compact(command),
            timeout_ms=args.timeout_ms,
            wait_sec=args.wait,
            poll_interval=args.poll_interval,
        )
        command_record = _maybe_apply_browser_tab_fallback(
            action=action,
            server=server,
            token=token,
            client=client,
            target=target,
            command=compact(command),
            timeout_ms=args.timeout_ms,
            wait_sec=args.wait,
            poll_interval=args.poll_interval,
            command_record=command_record,
        )

        if action == "screenshot" and args.output:
            result = _extract_command_result(command_record, str(client.get("client_id", "")).strip())
            data = result.get("data") if isinstance(result, dict) else None
            if isinstance(data, dict) and isinstance(data.get("imageDataUrl"), str):
                output_path = _write_data_url_to_file(data["imageDataUrl"], args.output)

        _print_browser_summary(
            action=action,
            client=client,
            command=command_record,
            raw=args.raw,
            output_path=output_path,
        )
        return 0 if command_record.get("status") == "completed" else 1
    except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


def cmd_serve(args: argparse.Namespace) -> int:
    token = args.token or os.getenv(DEFAULT_TOKEN_ENV, "") or DEFAULT_QUICKSTART_TOKEN

    config = HubConfig(
        host=args.host,
        port=args.port,
        token=token,
        state_file=Path(args.state_file).expanduser(),
    )
    run_server(config)
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    server = _norm_server(args.server or DEFAULT_SERVER)
    try:
        response = _http_json(server=server, token="health", method="GET", path="/health")
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    _print_json(response)
    return 0


def cmd_state(args: argparse.Namespace) -> int:
    try:
        server, token = _extract_runtime(args)
        response = _http_json(server=server, token=token, method="GET", path="/api/state")
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    _print_json(response)
    return 0


def cmd_clients(args: argparse.Namespace) -> int:
    try:
        server, token = _extract_runtime(args)
        response = _http_json(server=server, token=token, method="GET", path="/api/clients")
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    _print_json(response)
    return 0


def _build_command_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.payload_file:
        payload = _load_json_file(args.payload_file)
        if "issued_by" not in payload:
            payload["issued_by"] = "cli"
        return payload

    if not args.type:
        raise ValueError("--type is required when --payload-file is not provided")

    command: dict[str, Any] = compact(
        {
            "type": args.type,
            "selector": args.selector,
            "value": args.value,
            "url": args.url,
            "text": args.text,
            "script": args.script,
            "attribute": args.attribute,
            "x": args.x,
            "y": args.y,
            "timeout_ms": args.command_timeout_ms,
        }
    )

    if args.script_args:
        command["args"] = json.loads(args.script_args)

    target: dict[str, Any] = compact(
        {
            "client_id": args.client_id,
            "tab_id": args.tab_id,
            "url_pattern": args.url_pattern,
            "active": args.active,
        }
    )

    if args.client_ids:
        target["client_ids"] = [value.strip() for value in args.client_ids.split(",") if value.strip()]
    if args.broadcast:
        target["broadcast"] = True

    payload = {
        "issued_by": "cli",
        "timeout_ms": args.timeout_ms,
        "target": target,
        "command": command,
    }
    return payload


def cmd_send(args: argparse.Namespace) -> int:
    try:
        server, token = _extract_runtime(args)
        payload = _build_command_payload(args)
        response = _http_json(server=server, token=token, method="POST", path="/api/commands", payload=payload)
    except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if not response.get("ok"):
        _print_json(response)
        return 1

    command_id = response.get("command_id")
    print(f"command_id={command_id}")
    print(f"status={response.get('status')}")
    print(f"targets={','.join(response.get('target_client_ids', []))}")

    if args.wait > 0 and command_id:
        command = _wait_command(server, token, command_id, timeout_sec=args.wait, interval_sec=max(args.poll_interval, 0.1))
        print("\nfinal_command_state:")
        _print_json(command)
    return 0


def cmd_wait(args: argparse.Namespace) -> int:
    try:
        server, token = _extract_runtime(args)
        command = _wait_command(
            server,
            token,
            args.command_id,
            timeout_sec=args.timeout,
            interval_sec=max(args.poll_interval, 0.1),
        )
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    _print_json(command)
    status = command.get("status")
    return 0 if status in TERMINAL_COMMAND_STATUSES else 1


def cmd_cancel(args: argparse.Namespace) -> int:
    try:
        server, token = _extract_runtime(args)
        response = _http_json(
            server=server,
            token=token,
            method="POST",
            path=f"/api/commands/{args.command_id}/cancel",
            payload={"reason": args.reason},
        )
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    _print_json(response)
    return 0 if response.get("ok") else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sitectl",
        description="Local site control hub CLI",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    def add_runtime_options(cmd: argparse.ArgumentParser) -> None:
        cmd.add_argument("--server", default=DEFAULT_SERVER, help=f"Hub URL (default: {DEFAULT_SERVER})")
        cmd.add_argument(
            "--token",
            default="",
            help=(
                f"Access token (fallback env: {DEFAULT_TOKEN_ENV}; "
                f"default quick mode: {DEFAULT_QUICKSTART_TOKEN})"
            ),
        )

    serve = sub.add_parser("serve", help="Run local API server")
    add_runtime_options(serve)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", default=8765, type=int)
    serve.add_argument(
        "--state-file",
        default=str(Path.home() / ".site-control-kit" / "state.json"),
        help="Path to persistent state file",
    )
    serve.set_defaults(func=cmd_serve)

    health = sub.add_parser("health", help="Check hub health endpoint")
    add_runtime_options(health)
    health.set_defaults(func=cmd_health)

    state = sub.add_parser("state", help="Print full hub state")
    add_runtime_options(state)
    state.set_defaults(func=cmd_state)

    clients = sub.add_parser("clients", help="List connected browser clients")
    add_runtime_options(clients)
    clients.set_defaults(func=cmd_clients)

    send = sub.add_parser("send", help="Send command to browser extension client(s)")
    add_runtime_options(send)
    send.add_argument("--payload-file", help="JSON file with full request payload")
    send.add_argument("--type", help="Command type (navigate/click/fill/extract_text/get_html/screenshot/wait_selector/scroll/run_script)")

    send.add_argument("--client-id", help="Target one client ID")
    send.add_argument("--client-ids", help="Comma-separated list of client IDs")
    send.add_argument("--broadcast", action="store_true", help="Send to all known clients")
    send.add_argument("--tab-id", type=int, help="Explicit browser tab id")
    send.add_argument("--url-pattern", help="Pick a tab where URL contains this text")
    send.add_argument(
        "--active",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Prefer active tab when tab_id/url_pattern not set",
    )

    send.add_argument("--selector", help="CSS selector")
    send.add_argument("--value", help="Input value")
    send.add_argument("--url", help="Navigation URL")
    send.add_argument("--text", help="Optional free text")
    send.add_argument("--script", help="JavaScript body for run_script")
    send.add_argument("--script-args", help="JSON args for run_script")
    send.add_argument("--attribute", help="DOM attribute name")
    send.add_argument("--x", type=int, help="Numeric x parameter")
    send.add_argument("--y", type=int, help="Numeric y parameter")
    send.add_argument("--command-timeout-ms", type=int, default=10000, help="Command-level timeout in extension")

    send.add_argument("--timeout-ms", type=int, default=20000, help="Hub queue timeout for command")
    send.add_argument("--wait", type=int, default=0, help="Wait up to N seconds for terminal command state")
    send.add_argument("--poll-interval", type=float, default=1.0, help="Polling interval for --wait")
    send.set_defaults(func=cmd_send)

    wait = sub.add_parser("wait", help="Wait for a command to finish")
    add_runtime_options(wait)
    wait.add_argument("command_id")
    wait.add_argument("--timeout", type=int, default=60)
    wait.add_argument("--poll-interval", type=float, default=1.0)
    wait.set_defaults(func=cmd_wait)

    cancel = sub.add_parser("cancel", help="Cancel a command")
    add_runtime_options(cancel)
    cancel.add_argument("command_id")
    cancel.add_argument("--reason", default="manual cancel")
    cancel.set_defaults(func=cmd_cancel)

    browser = sub.add_parser("browser", help="Simple browser control wrapper")
    add_runtime_options(browser)
    browser.add_argument("--client-id", help="Target one browser client; by default the freshest client is used")
    browser.add_argument("--tab-id", type=int, help="Explicit browser tab id")
    browser.add_argument("--url-pattern", help="Target tab where URL contains this text")
    browser.add_argument(
        "--active",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Prefer active tab when tab_id/url_pattern are not set",
    )
    browser.add_argument("--timeout-ms", type=int, default=20000, help="Hub queue timeout")
    browser.add_argument("--command-timeout-ms", type=int, default=10000, help="Command timeout in the browser")
    browser.add_argument("--wait", type=int, default=20, help="Wait up to N seconds for a result")
    browser.add_argument("--poll-interval", type=float, default=0.5, help="Polling interval while waiting")
    browser.add_argument("--raw", action="store_true", help="Print full raw command state")
    browser_sub = browser.add_subparsers(dest="browser_action", required=True)

    browser_status = browser_sub.add_parser("status", help="Show selected client and current hub-visible state")
    browser_status.set_defaults(func=cmd_browser)

    browser_clients = browser_sub.add_parser("clients", help="List connected browser clients")
    browser_clients.set_defaults(func=cmd_browser)

    browser_tabs = browser_sub.add_parser("tabs", help="List tabs for the selected client")
    browser_tabs.set_defaults(func=cmd_browser)

    browser_open = browser_sub.add_parser("open", help="Open URL in the selected tab")
    browser_open.add_argument("url")
    browser_open.set_defaults(func=cmd_browser)

    browser_new_tab = browser_sub.add_parser("new-tab", help="Create a new browser tab")
    browser_new_tab.add_argument("url")
    browser_new_tab.add_argument("--background", action="store_true", help="Create the tab without focusing it")
    browser_new_tab.set_defaults(func=cmd_browser)

    browser_click = browser_sub.add_parser("click", help="Click element by CSS selector")
    browser_click.add_argument("selector")
    browser_click.set_defaults(func=cmd_browser)

    browser_click_text = browser_sub.add_parser("click-text", help="Click visible element by text")
    browser_click_text.add_argument("text")
    browser_click_text.add_argument("--root-selector", default="", help="Limit search to a subtree")
    browser_click_text.add_argument("--near-last-context", action="store_true", help="Prefer matches near last context click")
    browser_click_text.set_defaults(func=cmd_browser)

    browser_fill = browser_sub.add_parser("fill", help="Fill input by selector")
    browser_fill.add_argument("selector")
    browser_fill.add_argument("value")
    browser_fill.set_defaults(func=cmd_browser)

    browser_focus = browser_sub.add_parser("focus", help="Focus element by selector")
    browser_focus.add_argument("selector")
    browser_focus.set_defaults(func=cmd_browser)

    browser_wait = browser_sub.add_parser("wait", help="Wait for selector")
    browser_wait.add_argument("selector")
    browser_wait.add_argument("--visible-only", action="store_true")
    browser_wait.set_defaults(func=cmd_browser)

    browser_text = browser_sub.add_parser("text", help="Extract text from selector or full page")
    browser_text.add_argument("selector", nargs="?")
    browser_text.set_defaults(func=cmd_browser)

    browser_html = browser_sub.add_parser("html", help="Extract HTML from selector or full page")
    browser_html.add_argument("selector", nargs="?")
    browser_html.set_defaults(func=cmd_browser)

    browser_attr = browser_sub.add_parser("attr", help="Get attribute from selector")
    browser_attr.add_argument("selector")
    browser_attr.add_argument("attribute")
    browser_attr.set_defaults(func=cmd_browser)

    browser_page_url = browser_sub.add_parser("page-url", help="Return current page URL")
    browser_page_url.set_defaults(func=cmd_browser)

    browser_back = browser_sub.add_parser("back", help="Go back in history")
    browser_back.set_defaults(func=cmd_browser)

    browser_forward = browser_sub.add_parser("forward", help="Go forward in history")
    browser_forward.set_defaults(func=cmd_browser)

    browser_reload = browser_sub.add_parser("reload", help="Reload the selected tab")
    browser_reload.add_argument("--ignore-cache", action="store_true")
    browser_reload.set_defaults(func=cmd_browser)

    browser_activate = browser_sub.add_parser("activate", help="Activate the selected tab")
    browser_activate.set_defaults(func=cmd_browser)

    browser_close = browser_sub.add_parser("close-tab", help="Close the selected tab")
    browser_close.set_defaults(func=cmd_browser)

    browser_x11_click = browser_sub.add_parser("x11-click", help="Click inside the browser window using X11 coordinates")
    browser_x11_click.add_argument("--x-ratio", type=float, required=True, help="Horizontal position within window (0..1)")
    browser_x11_click.add_argument("--y-ratio", type=float, required=True, help="Vertical position within window (0..1)")
    browser_x11_click.add_argument("--button", type=int, default=1, help="Mouse button number (default: 1)")
    browser_x11_click.set_defaults(func=cmd_browser)

    browser_scroll = browser_sub.add_parser("scroll", help="Scroll to selector or coordinates")
    browser_scroll.add_argument("--selector")
    browser_scroll.add_argument("--x", type=int)
    browser_scroll.add_argument("--y", type=int)
    browser_scroll.set_defaults(func=cmd_browser)

    browser_scroll_by = browser_sub.add_parser("scroll-by", help="Scroll by delta")
    browser_scroll_by.add_argument("--selector")
    browser_scroll_by.add_argument("--dx", type=int, default=0)
    browser_scroll_by.add_argument("--dy", type=int, default=0)
    browser_scroll_by.set_defaults(func=cmd_browser)

    browser_press = browser_sub.add_parser("press", help="Press a keyboard key")
    browser_press.add_argument("key")
    browser_press.add_argument("--selector")
    browser_press.add_argument("--ctrl", action="store_true")
    browser_press.add_argument("--alt", action="store_true")
    browser_press.add_argument("--shift", action="store_true")
    browser_press.add_argument("--meta", action="store_true")
    browser_press.set_defaults(func=cmd_browser)

    browser_js = browser_sub.add_parser("js", help="Run JavaScript in the page context")
    browser_js.add_argument("script")
    browser_js.add_argument("--script-args", help="JSON args for run_script")
    browser_js.set_defaults(func=cmd_browser)

    browser_screenshot = browser_sub.add_parser("screenshot", help="Capture screenshot of the visible tab")
    browser_screenshot.add_argument("--output", help="Write PNG to a file")
    browser_screenshot.set_defaults(func=cmd_browser)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
