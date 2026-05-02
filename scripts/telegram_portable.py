#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import time
import warnings
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

DEFAULT_TELEGRAM_LINUX_URL = "https://telegram.org/dl/desktop/linux"
DEFAULT_OUTPUT_ROOT = Path.home()
DEFAULT_RUNTIME_CACHE_DIR = Path.home() / ".cache" / "site-control-kit" / "telegram-portable-runtime"
PROFILE_PREFIX = "TelegramPortable-"
LEGACY_PROFILE_PREFIX_RE = re.compile(r"^TelegramPortable[-_]?", re.I)
LOG_EVENT_RE = re.compile(r"^\[(?P<timestamp>[^\]]+)\]\s+(?P<kind>[^:]+):\s*(?P<message>.*)$")


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def sanitize_profile_name(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("profile name is required")
    raw = LEGACY_PROFILE_PREFIX_RE.sub("", raw)
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip("-._")
    if not normalized:
        raise ValueError(f"unable to derive safe profile name from: {value}")
    return normalized[:80]


def profile_dir_for(output_root: Path, profile_name: str) -> Path:
    safe_name = sanitize_profile_name(profile_name)
    return output_root.expanduser().resolve() / f"{PROFILE_PREFIX}{safe_name}"


def _metadata_path(target_dir: Path) -> Path:
    return target_dir / "portable-profile.json"


def _telegram_log_path(target_dir: Path) -> Path:
    return target_dir / "TelegramForcePortable" / "log.txt"


def _profile_dir_from_args(args: argparse.Namespace) -> Path:
    profile_dir = getattr(args, "profile_dir", None)
    if profile_dir:
        return Path(str(profile_dir)).expanduser().resolve()
    profile_name = getattr(args, "profile_name", None)
    if not profile_name:
        raise ValueError("pass --profile-name or --profile-dir")
    return profile_dir_for(Path(args.output_root), str(profile_name))


def _profile_name_from_dir(target_dir: Path) -> str:
    return sanitize_profile_name(target_dir.name)


def _validated_member_destination(root_dir: Path, member_name: str) -> Path:
    destination = (root_dir / member_name).resolve()
    root_resolved = root_dir.resolve()
    if os.path.commonpath([str(root_resolved), str(destination)]) != str(root_resolved):
        raise ValueError(f"archive contains unsafe path: {member_name}")
    return destination


def _zip_member_is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0o170000
    return mode == stat.S_IFLNK


def safe_extract_zip(archive_path: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive_path) as zf:
        members = zf.infolist()
        if not members:
            raise ValueError(f"zip archive is empty: {archive_path}")
        for member in members:
            name = member.filename
            if not name:
                continue
            if Path(name).is_absolute():
                raise ValueError(f"zip archive contains absolute path: {name}")
            if _zip_member_is_symlink(member):
                raise ValueError(f"zip archive contains unsupported symlink entry: {name}")
            _validated_member_destination(destination, name)
        zf.extractall(destination)


def safe_extract_tar(archive_path: Path, destination: Path) -> None:
    with tarfile.open(archive_path, mode="r:*") as tf:
        members = tf.getmembers()
        if not members:
            raise ValueError(f"tar archive is empty: {archive_path}")
        for member in members:
            if member.issym() or member.islnk():
                raise ValueError(f"tar archive contains unsupported link entry: {member.name}")
            _validated_member_destination(destination, member.name)
        tf.extractall(destination, filter="data")


def discover_tdata_dir(extracted_root: Path) -> Path:
    if (extracted_root / "key_datas").is_file():
        return extracted_root

    candidates: list[tuple[int, int, str, Path]] = []
    for key_datas_path in extracted_root.rglob("key_datas"):
        if not key_datas_path.is_file():
            continue
        parent = key_datas_path.parent
        try:
            depth = len(parent.relative_to(extracted_root).parts)
        except ValueError:
            continue
        named_tdata = 0 if parent.name == "tdata" else 1
        candidates.append((named_tdata, depth, str(parent), parent))

    if not candidates:
        raise ValueError(f"tdata directory with key_datas was not found in zip: {extracted_root}")

    candidates.sort()
    return candidates[0][3]


def discover_runtime_dir(extracted_root: Path) -> Path:
    direct = extracted_root / "Telegram"
    if direct.is_dir() and (direct / "Telegram").is_file():
        return direct

    candidates: list[tuple[int, str, Path]] = []
    for binary_path in extracted_root.rglob("Telegram"):
        if not binary_path.is_file():
            continue
        parent = binary_path.parent
        try:
            depth = len(parent.relative_to(extracted_root).parts)
        except ValueError:
            continue
        candidates.append((depth, str(parent), parent))

    if not candidates:
        raise ValueError(f"Telegram runtime directory was not found in archive: {extracted_root}")

    candidates.sort()
    return candidates[0][2]


def clear_directory_contents(directory: Path) -> None:
    if not directory.exists():
        return
    for child in directory.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()


def copy_tree_contents(source_dir: Path, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    for child in source_dir.iterdir():
        destination = target_dir / child.name
        if child.is_dir() and not child.is_symlink():
            shutil.copytree(child, destination)
        else:
            shutil.copy2(child, destination)


def ensure_executable(path: Path) -> None:
    if not path.exists():
        return
    current_mode = path.stat().st_mode
    path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": "site-control-kit telegram portable helper"})
    with urlopen(request, timeout=300) as response, destination.open("wb") as fh:
        shutil.copyfileobj(response, fh)


def ensure_runtime_cache(
    *,
    runtime_cache_dir: Path,
    runtime_archive: str | None,
    download_url: str,
    refresh_runtime: bool,
) -> dict[str, Any]:
    runtime_cache_dir = runtime_cache_dir.expanduser().resolve()
    cached_binary = runtime_cache_dir / "Telegram"
    if cached_binary.is_file() and not refresh_runtime:
        return {
            "runtime_dir": str(runtime_cache_dir),
            "source": "cache",
        }

    archive_source = "download"
    with tempfile.TemporaryDirectory(prefix="telegram-portable-runtime.") as tmpdir:
        temp_root = Path(tmpdir)
        archive_path = temp_root / "telegram-runtime.tar.xz"
        if runtime_archive:
            source_path = Path(runtime_archive).expanduser().resolve()
            if not source_path.is_file():
                raise FileNotFoundError(f"runtime archive not found: {source_path}")
            shutil.copy2(source_path, archive_path)
            archive_source = "archive"
        else:
            download_file(download_url, archive_path)

        extracted_root = temp_root / "runtime"
        extracted_root.mkdir(parents=True, exist_ok=True)
        safe_extract_tar(archive_path, extracted_root)
        runtime_source_dir = discover_runtime_dir(extracted_root)

        runtime_cache_dir.mkdir(parents=True, exist_ok=True)
        clear_directory_contents(runtime_cache_dir)
        copy_tree_contents(runtime_source_dir, runtime_cache_dir)
        ensure_executable(runtime_cache_dir / "Telegram")
        ensure_executable(runtime_cache_dir / "Updater")

    return {
        "runtime_dir": str(runtime_cache_dir),
        "source": archive_source,
    }


def _read_proc_cmdline_args(pid: str) -> list[str]:
    cmdline_path = Path("/proc") / pid / "cmdline"
    try:
        raw = cmdline_path.read_bytes()
    except OSError:
        return []
    return [part.decode("utf-8", errors="ignore") for part in raw.split(b"\0") if part]


def find_running_pids(binary_path: Path) -> list[int]:
    binary_path = binary_path.expanduser().resolve()
    proc_root = Path("/proc")
    if not proc_root.exists():
        return []

    pids: list[int] = []
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        pid = entry.name
        exe_path = entry / "exe"
        try:
            if exe_path.exists() and exe_path.resolve() == binary_path:
                pids.append(int(pid))
                continue
        except OSError:
            pass

        cmdline_args = _read_proc_cmdline_args(pid)
        if any(arg == str(binary_path) for arg in cmdline_args):
            pids.append(int(pid))
    return sorted(set(pids))


def write_profile_metadata(target_dir: Path, payload: dict[str, Any]) -> Path:
    metadata_path = _metadata_path(target_dir)
    metadata_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return metadata_path


def read_profile_metadata(target_dir: Path) -> dict[str, Any]:
    metadata_path = _metadata_path(target_dir)
    if not metadata_path.is_file():
        return {}
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _wmctrl_windows_by_pid() -> dict[int, list[dict[str, Any]]]:
    try:
        proc = subprocess.run(["wmctrl", "-l", "-G", "-p"], check=False, capture_output=True, text=True)
    except OSError:
        return {}
    if proc.returncode != 0:
        return {}

    windows_by_pid: dict[int, list[dict[str, Any]]] = {}
    for raw_line in str(proc.stdout or "").splitlines():
        parts = raw_line.split(None, 8)
        if len(parts) < 9:
            continue
        window_id, desktop, pid_raw, x_raw, y_raw, width_raw, height_raw, host, title = parts
        try:
            pid = int(pid_raw)
        except ValueError:
            continue
        try:
            desktop_id = int(desktop)
        except ValueError:
            desktop_id = -1
        try:
            x = int(x_raw)
            y = int(y_raw)
            width = int(width_raw)
            height = int(height_raw)
        except ValueError:
            x = 0
            y = 0
            width = 0
            height = 0
        windows_by_pid.setdefault(pid, []).append(
            {
                "window_id": window_id,
                "desktop": desktop_id,
                "pid": pid,
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "host": host,
                "title": title,
            }
        )
    return windows_by_pid


def profile_status(target_dir: Path) -> dict[str, Any]:
    target_dir = target_dir.expanduser().resolve()
    binary_path = target_dir / "Telegram"
    pids = find_running_pids(binary_path)
    windows_by_pid = _wmctrl_windows_by_pid()
    windows = [window for pid in pids for window in windows_by_pid.get(pid, [])]
    metadata = read_profile_metadata(target_dir)
    try:
        profile_name = str(metadata.get("profile_name") or "").strip() or _profile_name_from_dir(target_dir)
    except ValueError:
        profile_name = target_dir.name
    return {
        "status": "completed",
        "profile_name": profile_name,
        "profile_dir": str(target_dir),
        "binary_path": str(binary_path),
        "portable_dir": str(target_dir / "TelegramForcePortable"),
        "tdata_dir": str(target_dir / "TelegramForcePortable" / "tdata"),
        "metadata_path": str(_metadata_path(target_dir)),
        "metadata_exists": bool(_metadata_path(target_dir).is_file()),
        "account": metadata.get("account") if isinstance(metadata.get("account"), dict) else {},
        "running": bool(pids),
        "pids": pids,
        "windows": windows,
        "log_path": str(target_dir / "portable-launch.log"),
        "telegram_log_path": str(_telegram_log_path(target_dir)),
    }


def diagnose_telegram_log(target_dir: Path, *, tail_lines: int = 200, max_events: int = 20) -> dict[str, Any]:
    target_dir = target_dir.expanduser().resolve()
    log_path = _telegram_log_path(target_dir)
    if not log_path.is_file():
        return {
            "status": "missing",
            "profile_dir": str(target_dir),
            "telegram_log_path": str(log_path),
            "tail_lines": int(tail_lines),
            "alerts": [],
            "recent_events": [],
        }

    lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    recent_lines = lines[-max(int(tail_lines), 1) :]
    recent_events: list[dict[str, str]] = []
    counts: dict[str, int] = {}
    alert_keys: set[str] = set()
    working_dir_seen = False

    for raw_line in recent_lines:
        if "Working dir:" in raw_line:
            working_dir_seen = True
        match = LOG_EVENT_RE.match(raw_line.strip())
        if not match:
            continue
        kind = str(match.group("kind") or "").strip()
        message = str(match.group("message") or "").strip()
        if "Error" not in kind and "RPC" not in kind:
            continue
        counts[kind] = counts.get(kind, 0) + 1
        if "PEER_FLOOD" in message:
            alert_keys.add("peer_flood")
        if "PEER_ID_INVALID" in message:
            alert_keys.add("peer_id_invalid")
        if "FLOOD_WAIT" in message:
            alert_keys.add("flood_wait")
        recent_events.append(
            {
                "timestamp": str(match.group("timestamp") or "").strip(),
                "kind": kind,
                "message": message,
            }
        )

    alerts = []
    if "peer_flood" in alert_keys:
        alerts.append(
            {
                "code": "PEER_FLOOD",
                "severity": "high",
                "meaning": "Telegram is currently rejecting peer actions from this account; stop repeated add/invite attempts.",
            }
        )
    if "peer_id_invalid" in alert_keys:
        alerts.append(
            {
                "code": "PEER_ID_INVALID",
                "severity": "medium",
                "meaning": "Telegram received an invalid or unresolved peer; username resolution or target selection failed.",
            }
        )
    if "flood_wait" in alert_keys:
        alerts.append(
            {
                "code": "FLOOD_WAIT",
                "severity": "high",
                "meaning": "Telegram requested a cooldown window; defer further RPC-style actions.",
            }
        )

    return {
        "status": "completed",
        "profile_dir": str(target_dir),
        "telegram_log_path": str(log_path),
        "tail_lines": int(tail_lines),
        "working_dir_seen": bool(working_dir_seen),
        "event_counts": counts,
        "alerts": alerts,
        "recent_events": recent_events[-max(int(max_events), 1) :],
    }


def discover_profile_dirs(output_root: Path) -> list[Path]:
    output_root = output_root.expanduser().resolve()
    if not output_root.is_dir():
        return []
    candidates: list[Path] = []
    for child in output_root.glob("TelegramPortable*"):
        if not child.is_dir():
            continue
        if (child / "Telegram").is_file() or (child / "TelegramForcePortable").is_dir():
            candidates.append(child.resolve())
    return sorted(candidates, key=lambda path: path.name.lower())


def adopt_profile(
    *,
    profile_dir: Path,
    profile_name: str | None,
    account_username: str | None,
    account_label: str | None,
) -> dict[str, Any]:
    target_dir = profile_dir.expanduser().resolve()
    binary_path = target_dir / "Telegram"
    tdata_dir = target_dir / "TelegramForcePortable" / "tdata"
    if not binary_path.is_file():
        raise FileNotFoundError(f"Telegram binary not found: {binary_path}")
    if not (tdata_dir / "key_datas").is_file():
        raise FileNotFoundError(f"Telegram portable tdata not found: {tdata_dir}")

    safe_profile_name = sanitize_profile_name(profile_name or target_dir.name)
    metadata = read_profile_metadata(target_dir)
    metadata.update(
        {
            "status": "adopted",
            "adopted_at": now_utc(),
            "profile_name": safe_profile_name,
            "profile_dir": str(target_dir),
            "binary_path": str(binary_path),
            "portable_dir": str(target_dir / "TelegramForcePortable"),
            "tdata_dir": str(tdata_dir),
        }
    )
    account: dict[str, Any] = {}
    if account_username:
        account["username"] = str(account_username).strip()
    if account_label:
        account["label"] = str(account_label).strip()
    if account:
        metadata["account"] = account
    metadata_path = write_profile_metadata(target_dir, metadata)
    status = profile_status(target_dir)
    status.update({"adopted": True, "metadata_path": str(metadata_path)})
    return status


def launch_portable(target_dir: Path) -> dict[str, Any]:
    binary_path = target_dir / "Telegram"
    if not binary_path.is_file():
        raise FileNotFoundError(f"Telegram binary not found: {binary_path}")

    log_path = target_dir / "portable-launch.log"
    existing_pids = find_running_pids(binary_path)
    if existing_pids:
        return {
            "status": "already_running",
            "pids": existing_pids,
            "log_path": str(log_path),
        }

    with log_path.open("ab") as log_fh:
        process = subprocess.Popen(
            [str(binary_path)],
            cwd=str(target_dir),
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    return {
        "status": "started",
        "pid": int(process.pid),
        "log_path": str(log_path),
    }


def open_portable_uri(target_dir: Path, uri: str, *, dry_run: bool = False) -> dict[str, Any]:
    target_dir = target_dir.expanduser().resolve()
    binary_path = target_dir / "Telegram"
    if not binary_path.is_file():
        raise FileNotFoundError(f"Telegram binary not found: {binary_path}")
    uri = str(uri or "").strip()
    if not uri:
        raise ValueError("uri is required")
    command = [str(binary_path), uri]
    if dry_run:
        return {"status": "dry_run", "command": command, "cwd": str(target_dir)}
    with (target_dir / "portable-launch.log").open("ab") as log_fh:
        process = subprocess.Popen(
            command,
            cwd=str(target_dir),
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    return {"status": "opened", "pid": int(process.pid), "command": command}


def _focus_x11_window(window_id: str) -> bool:
    if not window_id or sys_platform_is_not_linux():
        return False
    try:
        subprocess.run(["wmctrl", "-ia", window_id], check=False)
    except OSError:
        return False
    time.sleep(0.18)
    return True


def sys_platform_is_not_linux() -> bool:
    import sys

    return sys.platform != "linux" or not os.environ.get("DISPLAY")


def _send_x11_key_sequence(window_id: str, sequences: list[list[str]]) -> bool:
    if not window_id or sys_platform_is_not_linux():
        return False
    try:
        from Xlib import X, XK, display  # type: ignore
        from Xlib.ext import xtest  # type: ignore
    except Exception:
        return False
    try:
        _focus_x11_window(window_id)
        d = display.Display()

        def _press(name: str, pressed: bool) -> None:
            keysym = XK.string_to_keysym(name)
            if keysym == 0:
                raise RuntimeError(f"Unknown X11 key: {name}")
            keycode = d.keysym_to_keycode(keysym)
            if keycode == 0:
                raise RuntimeError(f"Unable to map X11 key: {name}")
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
            time.sleep(0.02)
        return True
    except Exception:
        return False


def _read_x11_clipboard_text() -> str | None:
    if sys_platform_is_not_linux():
        return None
    try:
        import gi  # type: ignore

        gi.require_version("Gtk", "3.0")
        gi.require_version("Gdk", "3.0")
        from gi.repository import Gdk, Gtk  # type: ignore
    except Exception:
        return None
    try:
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        value = clipboard.wait_for_text()
        return str(value) if value is not None else None
    except Exception:
        return None


def _write_x11_clipboard_text(text: str) -> bool:
    if sys_platform_is_not_linux():
        return False
    try:
        import gi  # type: ignore

        gi.require_version("Gtk", "3.0")
        gi.require_version("Gdk", "3.0")
        from gi.repository import Gdk, Gtk  # type: ignore
    except Exception:
        return False
    try:
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(str(text), -1)
        clipboard.store()
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        return True
    except Exception:
        return False


def _paste_x11_text(
    window_id: str,
    text: str,
    *,
    clear_first: bool = False,
    press_enter: bool = False,
) -> bool:
    previous_clipboard = _read_x11_clipboard_text()
    if not _write_x11_clipboard_text(text):
        return False
    sequences: list[list[str]] = []
    if clear_first:
        sequences.extend([["Control_L", "a"], ["BackSpace"]])
    sequences.append(["Control_L", "v"])
    # Collapse any selection left by clipboard paste so the next click hits the action button,
    # not just the active text field.
    sequences.append(["End"])
    if press_enter:
        sequences.append(["Return"])
    try:
        return _send_x11_key_sequence(window_id, sequences)
    finally:
        if previous_clipboard is not None:
            _write_x11_clipboard_text(previous_clipboard)

    try:
        _focus_x11_window(window_id)
        d = display.Display()

        def _press(name: str, pressed: bool) -> None:
            keysym = XK.string_to_keysym(name)
            if keysym == 0:
                raise RuntimeError(f"Unknown X11 key: {name}")
            keycode = d.keysym_to_keycode(keysym)
            if keycode == 0:
                raise RuntimeError(f"Unable to map X11 key: {name}")
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
            time.sleep(0.02)
        return True
    except Exception:
        return False


def _x11_click_point(x: int, y: int, *, button: int = 1) -> bool:
    if sys_platform_is_not_linux():
        return False
    try:
        from Xlib import X, display  # type: ignore
        from Xlib.ext import xtest  # type: ignore
    except Exception:
        return False

    try:
        d = display.Display()
        xtest.fake_input(d, X.MotionNotify, x=int(x), y=int(y))
        d.sync()
        time.sleep(0.05)
        xtest.fake_input(d, X.ButtonPress, int(button))
        xtest.fake_input(d, X.ButtonRelease, int(button))
        d.sync()
        return True
    except Exception:
        return False


def _window_click_point(window: dict[str, Any], *, x_ratio: float, y_ratio: float) -> tuple[int, int] | None:
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
    return (
        x + max(1, min(int(width * xr), width - 2)),
        y + max(1, min(int(height * yr), height - 2)),
    )


def _resolved_window(status: dict[str, Any], window_id: str = "") -> dict[str, Any]:
    windows = status.get("windows") if isinstance(status.get("windows"), list) else []
    for item in windows:
        if not isinstance(item, dict):
            continue
        if window_id and str(item.get("window_id") or "") == str(window_id):
            return item
    for item in windows:
        if not isinstance(item, dict):
            continue
        if int(item.get("width", 0) or 0) > 0 and int(item.get("height", 0) or 0) > 0:
            return item
    return windows[0] if windows and isinstance(windows[0], dict) else {}


ASCII_KEY_MAP: dict[str, list[str]] = {
    " ": ["space"],
    "\n": ["Return"],
    ".": ["period"],
    ",": ["comma"],
    "-": ["minus"],
    "_": ["Shift_L", "minus"],
    "/": ["slash"],
    "?": ["Shift_L", "slash"],
    ":": ["Shift_L", "semicolon"],
    ";": ["semicolon"],
    "=": ["equal"],
    "+": ["Shift_L", "equal"],
    "&": ["Shift_L", "7"],
    "@": ["Shift_L", "2"],
    "#": ["Shift_L", "3"],
    "%": ["Shift_L", "5"],
    "(": ["Shift_L", "9"],
    ")": ["Shift_L", "0"],
}


def _ascii_text_to_key_sequences(text: str) -> list[list[str]]:
    sequences: list[list[str]] = []
    for char in str(text or ""):
        if char in ASCII_KEY_MAP:
            sequences.append(ASCII_KEY_MAP[char])
            continue
        if "a" <= char <= "z" or "0" <= char <= "9":
            sequences.append([char])
            continue
        if "A" <= char <= "Z":
            sequences.append(["Shift_L", char.lower()])
            continue
        raise ValueError(f"unsupported non-ASCII or unmapped character for X11 typing: {char!r}")
    return sequences


def _parse_x11_chords(items: list[str]) -> list[list[str]]:
    sequences: list[list[str]] = []
    for raw_item in items:
        item = str(raw_item or "").strip()
        if not item:
            continue
        parts = [chunk.strip() for chunk in item.split("+") if str(chunk).strip()]
        if not parts:
            continue
        sequences.append(parts)
    if not sequences:
        raise ValueError("at least one --sequence value is required")
    return sequences


def _contains_non_ascii(text: str) -> bool:
    return any(ord(char) > 127 for char in str(text or ""))


def type_portable_text(target_dir: Path, text: str, *, window_id: str = "", press_enter: bool = False, dry_run: bool = False) -> dict[str, Any]:
    status = profile_status(target_dir)
    windows = status.get("windows") if isinstance(status.get("windows"), list) else []
    resolved_window_id = window_id or (str(windows[0].get("window_id") or "") if windows and isinstance(windows[0], dict) else "")
    if not resolved_window_id:
        raise RuntimeError(f"no X11 window found for portable profile: {target_dir}")
    if dry_run:
        try:
            dry_run_sequences = _ascii_text_to_key_sequences(text)
            if press_enter:
                dry_run_sequences.append(["Return"])
            sequence_count = len(dry_run_sequences)
        except ValueError:
            sequence_count = 1 + (1 if press_enter else 0)
        return {
            "status": "dry_run",
            "window_id": resolved_window_id,
            "text_length": len(text),
            "press_enter": bool(press_enter),
            "sequence_count": sequence_count,
        }
    try:
        sequences = _ascii_text_to_key_sequences(text)
        if press_enter:
            sequences.append(["Return"])
        if not _send_x11_key_sequence(resolved_window_id, sequences):
            raise RuntimeError(f"failed to type text into Telegram window: {resolved_window_id}")
        input_method = "x11_keys"
        sequence_count = len(sequences)
    except ValueError:
        if not _paste_x11_text(resolved_window_id, text, press_enter=press_enter):
            raise RuntimeError(f"failed to paste text into Telegram window: {resolved_window_id}")
        input_method = "x11_clipboard"
        sequence_count = 1 + (1 if press_enter else 0)
    return {
        "status": "typed",
        "window_id": resolved_window_id,
        "text_length": len(text),
        "press_enter": bool(press_enter),
        "sequence_count": sequence_count,
        "input_method": input_method,
    }


def press_portable_keys(
    target_dir: Path,
    sequences: list[list[str]],
    *,
    window_id: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    status = profile_status(target_dir)
    windows = status.get("windows") if isinstance(status.get("windows"), list) else []
    resolved_window_id = window_id or (str(windows[0].get("window_id") or "") if windows and isinstance(windows[0], dict) else "")
    if not resolved_window_id:
        raise RuntimeError(f"no X11 window found for portable profile: {target_dir}")
    normalized_sequences = [list(sequence) for sequence in sequences if sequence]
    if not normalized_sequences:
        raise ValueError("at least one key sequence is required")
    if dry_run:
        return {
            "status": "dry_run",
            "window_id": resolved_window_id,
            "sequence_count": len(normalized_sequences),
            "sequences": normalized_sequences,
        }
    if not _send_x11_key_sequence(resolved_window_id, normalized_sequences):
        raise RuntimeError(f"failed to send key sequence into Telegram window: {resolved_window_id}")
    return {
        "status": "pressed",
        "window_id": resolved_window_id,
        "sequence_count": len(normalized_sequences),
        "sequences": normalized_sequences,
    }


def click_portable_window(
    target_dir: Path,
    *,
    x_ratio: float,
    y_ratio: float,
    window_id: str = "",
    button: int = 1,
    coordinate_space: str = "auto",
    dry_run: bool = False,
) -> dict[str, Any]:
    status = profile_status(target_dir)
    window = _resolved_window(status, window_id=window_id)
    resolved_window_id = str(window.get("window_id") or "")
    if not resolved_window_id:
        raise RuntimeError(f"no X11 window found for portable profile: {target_dir}")
    point = None
    requested_coordinate_space = str(coordinate_space or "auto").strip() or "auto"
    if requested_coordinate_space not in {"auto", "window_geometry", "accessible_window"}:
        raise ValueError(f"unsupported coordinate space: {requested_coordinate_space}")
    coordinate_space = "window_geometry"
    if requested_coordinate_space in {"auto", "accessible_window"}:
        try:
            _, _, _, accessible_window_extents = _pick_accessible_window(target_dir)
            point = _window_click_point(accessible_window_extents, x_ratio=float(x_ratio), y_ratio=float(y_ratio))
            if point is not None:
                coordinate_space = "accessible_window"
        except Exception:
            point = None
        if point is None and requested_coordinate_space == "accessible_window":
            raise RuntimeError(f"accessible window geometry is unavailable for portable profile: {resolved_window_id}")
    if point is None:
        point = _window_click_point(window, x_ratio=float(x_ratio), y_ratio=float(y_ratio))
        coordinate_space = "window_geometry"
    if point is None:
        raise RuntimeError(f"window geometry is unavailable for portable profile: {resolved_window_id}")
    x, y = point
    if dry_run:
        return {
            "status": "dry_run",
            "window_id": resolved_window_id,
            "x": x,
            "y": y,
            "button": int(button),
            "x_ratio": float(x_ratio),
            "y_ratio": float(y_ratio),
            "coordinate_space": coordinate_space,
        }
    _focus_x11_window(resolved_window_id)
    if not _x11_click_point(x, y, button=int(button)):
        raise RuntimeError(f"failed to click Telegram window: {resolved_window_id}")
    return {
        "status": "clicked",
        "window_id": resolved_window_id,
        "x": x,
        "y": y,
        "button": int(button),
        "x_ratio": float(x_ratio),
        "y_ratio": float(y_ratio),
        "coordinate_space": coordinate_space,
    }


def capture_portable_window_screenshot(
    target_dir: Path,
    *,
    output_path: Path,
    window_id: str = "",
) -> dict[str, Any]:
    status = profile_status(target_dir)
    window = _resolved_window(status, window_id=window_id)
    resolved_window_id = str(window.get("window_id") or "")
    if not resolved_window_id:
        raise RuntimeError(f"no X11 window found for portable profile: {target_dir}")
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if sys_platform_is_not_linux():
        raise RuntimeError("window-screenshot requires Linux with DISPLAY")
    try:
        from PIL import Image  # type: ignore
        from Xlib import X, display  # type: ignore
    except Exception as exc:
        raise RuntimeError("window-screenshot requires python3-xlib and Pillow") from exc

    try:
        d = display.Display()
        x_window = d.create_resource_object("window", int(resolved_window_id, 16))
        geometry = x_window.get_geometry()
        raw = x_window.get_image(0, 0, int(geometry.width), int(geometry.height), X.ZPixmap, 0xFFFFFFFF)
        if raw is None or not getattr(raw, "data", b""):
            raise RuntimeError(f"unable to capture X11 window image: {resolved_window_id}")
        image = None
        for raw_mode in ("BGRX", "RGBX"):
            try:
                image = Image.frombytes("RGB", (int(geometry.width), int(geometry.height)), raw.data, "raw", raw_mode)
                break
            except Exception:
                image = None
        if image is None:
            raise RuntimeError(f"unsupported X11 raw image format for window: {resolved_window_id}")
        image.save(output_path)
    except Exception as exc:
        raise RuntimeError(f"failed to capture X11 window screenshot: {resolved_window_id}") from exc

    return {
        "status": "completed",
        "window_id": resolved_window_id,
        "output_path": str(output_path),
        "width": int(window.get("width", 0) or 0),
        "height": int(window.get("height", 0) or 0),
    }


def _import_atspi():
    try:
        import gi  # type: ignore

        gi.require_version("Atspi", "2.0")
        from gi.repository import Atspi  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("AT-SPI is unavailable; install python3-gi and gir1.2-atspi-2.0 or run under a desktop session") from exc
    return Atspi


def _normalize_accessible_window_name(value: str) -> str:
    text = str(value or "")
    for marker in ("\u200e", "\u200f", "\u2066", "\u2067", "\u2068", "\u2069"):
        text = text.replace(marker, "")
    return " ".join(text.split()).strip()


def _pick_accessible_window(target_dir: Path) -> tuple[Any, Any, dict[str, Any], dict[str, int]]:
    Atspi = _import_atspi()
    desktop = Atspi.get_desktop(0)
    apps: list[Any] = []
    for index in range(desktop.get_child_count()):
        candidate = desktop.get_child_at_index(index)
        if candidate is None:
            continue
        name = str(candidate.get_name() or "")
        if name in {"TelegramDesktop", "Telegram"} and candidate.get_child_count() > 0:
            apps.append(candidate)
    if not apps:
        raise RuntimeError("AT-SPI cannot find a running TelegramDesktop application")

    status = profile_status(target_dir)
    preferred_windows = [item for item in status.get("windows") or [] if isinstance(item, dict)]
    preferred_titles = [
        _normalize_accessible_window_name(str(item.get("title") or ""))
        for item in preferred_windows
        if str(item.get("title") or "").strip()
    ]
    accessible_windows: list[Any] = []
    for app in apps:
        app_windows = [app.get_child_at_index(index) for index in range(app.get_child_count())]
        app_windows = [item for item in app_windows if item is not None]
        for candidate in app_windows:
            accessible_windows.append(candidate)
            normalized_name = _normalize_accessible_window_name(str(candidate.get_name() or ""))
            for title in preferred_titles:
                if title and (normalized_name == title or title in normalized_name or normalized_name in title):
                    return Atspi, candidate, status, _extents_payload(candidate.get_extents(Atspi.CoordType.SCREEN))

    if not accessible_windows:
        raise RuntimeError("AT-SPI Telegram application has no accessible windows")

    for candidate in accessible_windows:
        if str(candidate.get_name() or "").strip().lower() != "media viewer":
            return Atspi, candidate, status, _extents_payload(candidate.get_extents(Atspi.CoordType.SCREEN))
    fallback = accessible_windows[0]
    return Atspi, fallback, status, _extents_payload(fallback.get_extents(Atspi.CoordType.SCREEN))


def _extents_payload(extents: Any) -> dict[str, int]:
    return {
        "x": int(getattr(extents, "x", 0) or 0),
        "y": int(getattr(extents, "y", 0) or 0),
        "width": int(getattr(extents, "width", 0) or 0),
        "height": int(getattr(extents, "height", 0) or 0),
    }


def _resolved_accessible_extents(
    extents: dict[str, int],
    *,
    accessible_window_extents: dict[str, int],
    window_geometry: dict[str, Any],
) -> dict[str, int]:
    raw_x = int(extents.get("x", 0) or 0)
    raw_y = int(extents.get("y", 0) or 0)
    raw_width = int(extents.get("width", 0) or 0)
    raw_height = int(extents.get("height", 0) or 0)

    root_x = int(accessible_window_extents.get("x", 0) or 0)
    root_y = int(accessible_window_extents.get("y", 0) or 0)
    root_width = int(accessible_window_extents.get("width", 0) or 0)
    root_height = int(accessible_window_extents.get("height", 0) or 0)

    window_x = int(window_geometry.get("x", 0) or 0)
    window_y = int(window_geometry.get("y", 0) or 0)
    window_width = int(window_geometry.get("width", 0) or 0)
    window_height = int(window_geometry.get("height", 0) or 0)

    scale_x = (float(window_width) / float(root_width)) if root_width > 0 and window_width > 0 else 1.0
    scale_y = (float(window_height) / float(root_height)) if root_height > 0 and window_height > 0 else 1.0

    return {
        "x": int(round((raw_x - root_x) * scale_x + window_x)),
        "y": int(round((raw_y - root_y) * scale_y + window_y)),
        "width": int(round(raw_width * scale_x)),
        "height": int(round(raw_height * scale_y)),
    }


def _relative_extents(extents: dict[str, int], *, window_geometry: dict[str, Any]) -> dict[str, int]:
    window_x = int(window_geometry.get("x", 0) or 0)
    window_y = int(window_geometry.get("y", 0) or 0)
    return {
        "x": int(extents.get("x", 0) or 0) - window_x,
        "y": int(extents.get("y", 0) or 0) - window_y,
        "width": int(extents.get("width", 0) or 0),
        "height": int(extents.get("height", 0) or 0),
    }


def _accessible_state_names(node: Any) -> list[str]:
    try:
        state_set = node.get_state_set()
        if state_set is None:
            return []
        states = state_set.get_states() or []
    except Exception:
        return []
    names: list[str] = []
    for state in states:
        nick = str(getattr(state, "value_nick", "") or "").strip().lower()
        if nick:
            names.append(nick)
            continue
        value_name = str(getattr(state, "value_name", "") or "").strip().lower()
        if value_name.startswith("atspi_state_"):
            value_name = value_name.removeprefix("atspi_state_")
        if value_name:
            names.append(value_name)
    return sorted(set(names))


def _accessible_action_names(node: Any) -> list[str]:
    try:
        action_count = int(node.get_n_actions() or 0)
    except Exception:
        return []
    names: list[str] = []
    for index in range(max(action_count, 0)):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            try:
                name = str(node.get_action_name(index) or "").strip()
            except Exception:
                name = ""
        if name:
            names.append(name)
    return names


def _walk_accessible_nodes(
    node: Any,
    Atspi: Any,
    *,
    accessible_window_extents: dict[str, int],
    window_geometry: dict[str, Any],
    path: list[int] | None = None,
    ancestors: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    current_path = list(path or [])
    current_ancestors = list(ancestors or [])
    extents = _extents_payload(node.get_extents(Atspi.CoordType.SCREEN))
    resolved_extents = _resolved_accessible_extents(
        extents,
        accessible_window_extents=accessible_window_extents,
        window_geometry=window_geometry,
    )
    relative_extents = _relative_extents(resolved_extents, window_geometry=window_geometry)
    window_width = int(window_geometry.get("width", 0) or 0)
    window_height = int(window_geometry.get("height", 0) or 0)
    state_names = _accessible_state_names(node)
    action_names = _accessible_action_names(node)
    payload = {
        "path": current_path,
        "path_text": "/" + "/".join(str(item) for item in current_path),
        "role": str(node.get_role_name() or ""),
        "name": str(node.get_name() or ""),
        "child_count": int(node.get_child_count() or 0),
        "interfaces": list(node.get_interfaces() or []),
        "states": state_names,
        "focused": "focused" in state_names,
        "showing": "showing" in state_names,
        "action_count": len(action_names),
        "action_names": action_names,
        "extents": extents,
        "resolved_extents": resolved_extents,
        "relative_extents": relative_extents,
        "relative_x_ratio": (float(relative_extents["x"]) / float(window_width)) if window_width > 0 else 0.0,
        "relative_y_ratio": (float(relative_extents["y"]) / float(window_height)) if window_height > 0 else 0.0,
        "visible": bool(extents["width"] > 0 and extents["height"] > 0),
        "ancestors": current_ancestors,
    }
    results = [payload]
    next_ancestors = [
        *current_ancestors,
        {
            "path": current_path,
            "path_text": payload["path_text"],
            "role": payload["role"],
            "name": payload["name"],
            "child_count": payload["child_count"],
            "extents": extents,
            "resolved_extents": resolved_extents,
        },
    ]
    for index in range(node.get_child_count()):
        child = node.get_child_at_index(index)
        if child is None:
            continue
        results.extend(
            _walk_accessible_nodes(
                child,
                Atspi,
                accessible_window_extents=accessible_window_extents,
                window_geometry=window_geometry,
                path=[*current_path, index],
                ancestors=next_ancestors,
            )
        )
    return results


def _node_matches_query(
    node: dict[str, Any],
    *,
    query: str,
    role: str,
    match_mode: str,
    visible_only: bool,
    state_filters: list[str] | None = None,
) -> bool:
    active_states = {str(item or "").strip().lower() for item in (node.get("states") or [])}
    if visible_only and not bool(node.get("visible")):
        return False
    if visible_only and "showing" not in active_states and not bool(node.get("showing")):
        return False
    for required_state in state_filters or []:
        if str(required_state or "").strip().lower() not in active_states:
            return False
    node_role = str(node.get("role") or "")
    if role and node_role != role:
        return False
    if not query:
        return True
    query_norm = query.casefold()
    haystack = " ".join([node_role, str(node.get("name") or "")]).casefold()
    if match_mode == "exact":
        return query_norm == str(node.get("name") or "").casefold()
    return query_norm in haystack


def _pick_accessible_matches(matches: list[dict[str, Any]], *, pick: str) -> list[dict[str, Any]]:
    def _extents(item: dict[str, Any]) -> dict[str, int]:
        return item.get("resolved_extents") if isinstance(item.get("resolved_extents"), dict) else item.get("extents", {})

    def _best_priority(item: dict[str, Any]) -> tuple[int, int, int, int, int, int]:
        states = {str(state or "").strip().lower() for state in (item.get("states") or [])}
        interfaces = {str(name or "").strip() for name in (item.get("interfaces") or [])}
        extents = _extents(item)
        return (
            0 if bool(item.get("visible")) else 1,
            0 if "editable" in states or "EditableText" in interfaces else 1,
            0 if "focusable" in states else 1,
            int(extents.get("y", 0)),
            int(extents.get("x", 0)),
            -len(item.get("path") or []),
        )

    if pick == "first":
        return list(matches)
    if pick == "rightmost":
        return sorted(matches, key=lambda item: (int(_extents(item).get("x", 0)), int(_extents(item).get("y", 0))), reverse=True)
    if pick == "leftmost":
        return sorted(matches, key=lambda item: (int(_extents(item).get("x", 0)), int(_extents(item).get("y", 0))))
    if pick == "bottommost":
        return sorted(matches, key=lambda item: (int(_extents(item).get("y", 0)), int(_extents(item).get("x", 0))), reverse=True)
    if pick == "topmost":
        return sorted(matches, key=lambda item: (int(_extents(item).get("y", 0)), int(_extents(item).get("x", 0))))
    return sorted(matches, key=_best_priority)


def list_accessible_nodes(
    target_dir: Path,
    *,
    query: str = "",
    role: str = "",
    match_mode: str = "contains",
    visible_only: bool = False,
    max_results: int = 50,
    pick: str = "best",
    state_filters: list[str] | None = None,
) -> dict[str, Any]:
    Atspi, window, status, accessible_window_extents = _pick_accessible_window(target_dir)
    window_geometry = _resolved_window(status)
    normalized_state_filters = [
        str(item or "").strip().lower()
        for item in (state_filters or [])
        if str(item or "").strip()
    ]
    all_nodes = _walk_accessible_nodes(
        window,
        Atspi,
        accessible_window_extents=accessible_window_extents,
        window_geometry=window_geometry,
    )
    matches = [
        node
        for node in all_nodes
        if _node_matches_query(
            node,
            query=str(query or "").strip(),
            role=str(role or "").strip(),
            match_mode=str(match_mode or "contains").strip() or "contains",
            visible_only=bool(visible_only),
            state_filters=normalized_state_filters,
        )
    ]
    ordered = _pick_accessible_matches(matches, pick=str(pick or "best"))
    return {
        "status": "completed",
        "profile_dir": str(target_dir.expanduser().resolve()),
        "window_name": str(window.get_name() or ""),
        "window_geometry": window_geometry,
        "accessible_window_extents": accessible_window_extents,
        "query": str(query or ""),
        "role": str(role or ""),
        "match_mode": str(match_mode or "contains"),
        "visible_only": bool(visible_only),
        "state_filters": normalized_state_filters,
        "pick": str(pick or "best"),
        "match_count": len(matches),
        "matches": ordered[: max(int(max_results), 1)],
    }


def _accessible_click_point(node: dict[str, Any]) -> dict[str, Any] | None:
    extents = node.get("resolved_extents") if isinstance(node.get("resolved_extents"), dict) else {}
    if not extents:
        extents = node.get("extents") if isinstance(node.get("extents"), dict) else {}
    width = int(extents.get("width", 0) or 0)
    height = int(extents.get("height", 0) or 0)
    if width > 0 and height > 0:
        return {
            "mode": "direct_extents",
            "x": int(extents.get("x", 0) or 0) + width // 2,
            "y": int(extents.get("y", 0) or 0) + height // 2,
        }
    path = list(node.get("path") or [])
    for ancestor in reversed(list(node.get("ancestors") or [])):
        if not isinstance(ancestor, dict):
            continue
        ancestor_extents = (
            ancestor.get("resolved_extents")
            if isinstance(ancestor.get("resolved_extents"), dict)
            else {}
        )
        if not ancestor_extents and isinstance(ancestor.get("extents"), dict):
            ancestor_extents = ancestor.get("extents")
        ancestor_width = int(ancestor_extents.get("width", 0) or 0)
        ancestor_height = int(ancestor_extents.get("height", 0) or 0)
        ancestor_path = list(ancestor.get("path") or [])
        child_count = int(ancestor.get("child_count", 0) or 0)
        if ancestor_width <= 0 or ancestor_height <= 0 or child_count < 2:
            continue
        if len(path) <= len(ancestor_path):
            continue
        branch_index = int(path[len(ancestor_path)])
        if branch_index < 0 or branch_index >= child_count:
            continue
        return {
            "mode": "ancestor_segment",
            "x": int(ancestor_extents.get("x", 0) or 0) + int(((branch_index + 0.5) / child_count) * ancestor_width),
            "y": int(ancestor_extents.get("y", 0) or 0) + ancestor_height // 2,
            "ancestor_path": ancestor.get("path_text"),
            "branch_index": branch_index,
            "segments": child_count,
        }
    return None


def _resolve_accessible_node_by_path(window: Any, path: list[int]) -> Any:
    node = window
    for raw_index in path:
        index = int(raw_index)
        node = node.get_child_at_index(index)
        if node is None:
            raise RuntimeError(f"failed to resolve accessible child at index {index} for path {path!r}")
    return node


def _find_accessible_match(
    target_dir: Path,
    *,
    query: str,
    role: str = "",
    match_mode: str = "contains",
    visible_only: bool = False,
    pick: str = "best",
    index: int = 0,
    state_filters: list[str] | None = None,
) -> dict[str, Any]:
    Atspi, window, status, accessible_window_extents = _pick_accessible_window(target_dir)
    window_geometry = _resolved_window(status)
    normalized_state_filters = [
        str(item or "").strip().lower()
        for item in (state_filters or [])
        if str(item or "").strip()
    ]
    all_nodes = _walk_accessible_nodes(
        window,
        Atspi,
        accessible_window_extents=accessible_window_extents,
        window_geometry=window_geometry,
    )
    matches = [
        node
        for node in all_nodes
        if _node_matches_query(
            node,
            query=str(query or "").strip(),
            role=str(role or "").strip(),
            match_mode=str(match_mode or "contains").strip() or "contains",
            visible_only=bool(visible_only),
            state_filters=normalized_state_filters,
        )
    ]
    ordered = _pick_accessible_matches(matches, pick=str(pick or "best"))
    if int(index) < 0 or int(index) >= len(ordered):
        raise RuntimeError(f"accessible node not found for query={query!r} role={role!r} index={index}")
    chosen = ordered[int(index)]
    actual_node = _resolve_accessible_node_by_path(window, list(chosen.get("path") or []))
    return {
        "Atspi": Atspi,
        "window": window,
        "status": status,
        "window_geometry": window_geometry,
        "accessible_window_extents": accessible_window_extents,
        "matches": ordered,
        "chosen": chosen,
        "node": actual_node,
    }


def _focus_accessible_node(node: Any) -> bool:
    try:
        if bool(node.grab_focus()):
            return True
    except Exception:
        pass
    try:
        action_count = int(node.get_n_actions() or 0)
    except Exception:
        action_count = 0
    for action_index in range(max(action_count, 0)):
        try:
            action_name = str(node.get_action_name(action_index) or "").strip().casefold()
        except Exception:
            action_name = ""
        if action_name != "setfocus":
            continue
        try:
            if bool(node.do_action(action_index)):
                return True
        except Exception:
            continue
    return False


def _set_accessible_text_value(node: Any, text: str) -> bool:
    for method_name, args in (
        ("set_text_contents", (text,)),
        ("delete_text", (0, -1)),
    ):
        if not hasattr(node, method_name):
            continue
        try:
            result = getattr(node, method_name)(*args)
            if method_name == "set_text_contents":
                return bool(result)
        except Exception:
            if method_name == "set_text_contents":
                continue
    if hasattr(node, "insert_text"):
        try:
            return bool(node.insert_text(0, text, len(text)))
        except Exception:
            return False
    return False


def click_accessible_node(
    target_dir: Path,
    *,
    query: str,
    role: str = "",
    match_mode: str = "contains",
    visible_only: bool = False,
    pick: str = "best",
    index: int = 0,
    button: int = 1,
    dry_run: bool = False,
    state_filters: list[str] | None = None,
) -> dict[str, Any]:
    resolved = _find_accessible_match(
        target_dir,
        query=query,
        role=role,
        match_mode=match_mode,
        visible_only=visible_only,
        pick=pick,
        index=index,
        state_filters=state_filters,
    )
    chosen = resolved["chosen"]
    point = _accessible_click_point(chosen)
    if point is None:
        raise RuntimeError(f"accessible node has no clickable point for query={query!r}")
    x = int(point["x"])
    y = int(point["y"])
    if dry_run:
        return {
            "status": "dry_run",
            "query": query,
            "role": role,
            "match_mode": match_mode,
            "pick": pick,
            "index": int(index),
            "button": int(button),
            "node": chosen,
            "click_point": point,
        }
    status = resolved["status"]
    window = _resolved_window(status)
    resolved_window_id = str(window.get("window_id") or "")
    if resolved_window_id:
        _focus_x11_window(resolved_window_id)
    if not _x11_click_point(x, y, button=int(button)):
        raise RuntimeError(f"failed to click accessible point for query={query!r}")
    return {
        "status": "clicked",
        "query": query,
        "role": role,
        "match_mode": match_mode,
        "pick": pick,
        "index": int(index),
        "button": int(button),
        "node": chosen,
        "click_point": point,
        "window_id": resolved_window_id,
    }


def type_into_accessible_node(
    target_dir: Path,
    *,
    query: str,
    text: str,
    role: str = "",
    match_mode: str = "contains",
    visible_only: bool = False,
    pick: str = "best",
    index: int = 0,
    clear_first: bool = False,
    press_enter: bool = False,
    dry_run: bool = False,
    state_filters: list[str] | None = None,
) -> dict[str, Any]:
    resolved = _find_accessible_match(
        target_dir,
        query=query,
        role=role,
        match_mode=match_mode,
        visible_only=visible_only,
        pick=pick,
        index=index,
        state_filters=state_filters,
    )
    chosen = resolved["chosen"]
    node = resolved["node"]
    point = _accessible_click_point(chosen)
    if point is None:
        raise RuntimeError(f"accessible node has no clickable point for query={query!r}")
    status = resolved["status"]
    window = _resolved_window(status)
    window_id = str(window.get("window_id") or "")
    pre_sequences: list[list[str]] = []
    if clear_first:
        pre_sequences.extend([["Control_L", "a"], ["BackSpace"]])
    if dry_run:
        return {
            "status": "dry_run",
            "query": query,
            "role": role,
            "pick": pick,
            "index": int(index),
            "node": chosen,
            "click_point": point,
            "clear_first": bool(clear_first),
            "press_enter": bool(press_enter),
            "sequence_count": len(pre_sequences) + 1 + (1 if press_enter else 0),
            "window_id": window_id,
        }
    direct_text_ok = False
    try:
        _focus_accessible_node(node)
        direct_text_ok = _set_accessible_text_value(node, text)
    except Exception:
        direct_text_ok = False
    if direct_text_ok and _contains_non_ascii(text):
        verification = list_accessible_nodes(
            target_dir,
            query=text,
            role=role or "text",
            match_mode="exact",
            visible_only=visible_only,
            max_results=10,
            pick="best",
            state_filters=state_filters or [],
        )
        direct_text_ok = bool(verification.get("match_count"))
    if direct_text_ok:
        if press_enter and not _send_x11_key_sequence(window_id, [["Return"]]):
            raise RuntimeError(f"failed to confirm accessible text entry for query={query!r}")
        return {
            "status": "typed",
            "query": query,
            "role": role,
            "pick": pick,
            "index": int(index),
            "node": chosen,
            "click_point": point,
            "clear_first": bool(clear_first),
            "press_enter": bool(press_enter),
            "sequence_count": 1 if not press_enter else 2,
            "window_id": window_id,
            "text_length": len(text),
            "input_method": "accessible_text",
        }
    click_payload = click_accessible_node(
        target_dir,
        query=query,
        role=role,
        match_mode=match_mode,
        visible_only=visible_only,
        pick=pick,
        index=index,
        dry_run=False,
        state_filters=state_filters,
    )
    input_method = "x11_keys"
    try:
        text_sequences = _ascii_text_to_key_sequences(text)
        if press_enter:
            text_sequences.append(["Return"])
        all_sequences = [*pre_sequences, *text_sequences]
        if not _send_x11_key_sequence(window_id, all_sequences):
            raise RuntimeError(f"failed to type into accessible node for query={query!r}")
        sequence_count = len(all_sequences)
    except ValueError:
        if not _paste_x11_text(window_id, text, clear_first=clear_first, press_enter=press_enter):
            raise RuntimeError(f"failed to paste into accessible node for query={query!r}")
        input_method = "x11_clipboard"
        sequence_count = len(pre_sequences) + 1 + (1 if press_enter else 0)
    return {
        "status": "typed",
        "query": query,
        "role": role,
        "pick": pick,
        "index": int(index),
        "click": click_payload,
        "clear_first": bool(clear_first),
        "press_enter": bool(press_enter),
        "sequence_count": sequence_count,
        "window_id": window_id,
        "text_length": len(text),
        "input_method": input_method,
    }


def import_zip(
    *,
    zip_path: Path,
    profile_name: str,
    output_root: Path,
    runtime_cache_dir: Path,
    runtime_archive: str | None,
    download_url: str,
    refresh_runtime: bool,
    launch_after_import: bool,
) -> dict[str, Any]:
    zip_path = zip_path.expanduser().resolve()
    if not zip_path.is_file():
        raise FileNotFoundError(f"zip archive not found: {zip_path}")

    safe_profile_name = sanitize_profile_name(profile_name)
    target_dir = profile_dir_for(output_root, safe_profile_name)
    target_existed = target_dir.exists()
    if target_existed:
        running_pids = find_running_pids(target_dir / "Telegram")
        if running_pids:
            raise RuntimeError(
                f"profile {safe_profile_name} is already running via {target_dir}; close it before replacing the tdata"
            )

    runtime_info = ensure_runtime_cache(
        runtime_cache_dir=runtime_cache_dir,
        runtime_archive=runtime_archive,
        download_url=download_url,
        refresh_runtime=refresh_runtime,
    )

    with tempfile.TemporaryDirectory(prefix="telegram-portable-import.") as tmpdir:
        temp_root = Path(tmpdir)
        extracted_zip_root = temp_root / "zip"
        extracted_zip_root.mkdir(parents=True, exist_ok=True)
        safe_extract_zip(zip_path, extracted_zip_root)
        tdata_source_dir = discover_tdata_dir(extracted_zip_root)

        target_dir.mkdir(parents=True, exist_ok=True)
        clear_directory_contents(target_dir)
        copy_tree_contents(Path(runtime_info["runtime_dir"]), target_dir)
        ensure_executable(target_dir / "Telegram")
        ensure_executable(target_dir / "Updater")

        portable_root = target_dir / "TelegramForcePortable"
        portable_root.mkdir(parents=True, exist_ok=True)
        shutil.copytree(tdata_source_dir, portable_root / "tdata")

    metadata = {
        "status": "completed",
        "imported_at": now_utc(),
        "profile_name": safe_profile_name,
        "profile_dir": str(target_dir),
        "binary_path": str(target_dir / "Telegram"),
        "portable_dir": str(target_dir / "TelegramForcePortable"),
        "tdata_dir": str(target_dir / "TelegramForcePortable" / "tdata"),
        "source_zip": str(zip_path),
        "runtime": {
            "cache_dir": str(Path(runtime_info["runtime_dir"])),
            "source": str(runtime_info["source"]),
        },
    }
    metadata_path = write_profile_metadata(target_dir, metadata)

    launch_result = {"status": "not_requested"}
    if launch_after_import:
        launch_result = launch_portable(target_dir)

    return {
        "status": "completed",
        "mode": "updated" if target_existed else "created",
        "profile_name": safe_profile_name,
        "profile_dir": str(target_dir),
        "binary_path": str(target_dir / "Telegram"),
        "portable_dir": str(target_dir / "TelegramForcePortable"),
        "tdata_dir": str(target_dir / "TelegramForcePortable" / "tdata"),
        "source_zip": str(zip_path),
        "metadata_path": str(metadata_path),
        "runtime": metadata["runtime"],
        "launch": launch_result,
    }


def command_import_zip(args: argparse.Namespace) -> int:
    profile_name = args.profile_name or Path(args.zip).stem
    payload = import_zip(
        zip_path=Path(args.zip),
        profile_name=profile_name,
        output_root=Path(args.output_root),
        runtime_cache_dir=Path(args.runtime_cache_dir),
        runtime_archive=args.runtime_archive,
        download_url=args.download_url,
        refresh_runtime=bool(args.refresh_runtime),
        launch_after_import=bool(args.launch),
    )
    _print_json(payload)
    return 0


def command_launch(args: argparse.Namespace) -> int:
    target_dir = _profile_dir_from_args(args)
    payload = {
        "status": "completed",
        "profile_name": sanitize_profile_name(args.profile_name or target_dir.name),
        "profile_dir": str(target_dir),
        "binary_path": str(target_dir / "Telegram"),
        "launch": launch_portable(target_dir),
    }
    _print_json(payload)
    return 0


def command_open_uri(args: argparse.Namespace) -> int:
    target_dir = _profile_dir_from_args(args)
    _print_json(open_portable_uri(target_dir, args.uri, dry_run=bool(args.dry_run)))
    return 0


def command_type_text(args: argparse.Namespace) -> int:
    target_dir = _profile_dir_from_args(args)
    _print_json(
        type_portable_text(
            target_dir,
            args.text,
            window_id=args.window_id or "",
            press_enter=bool(args.press_enter),
            dry_run=bool(args.dry_run),
        )
    )
    return 0


def command_press_keys(args: argparse.Namespace) -> int:
    target_dir = _profile_dir_from_args(args)
    _print_json(
        press_portable_keys(
            target_dir,
            _parse_x11_chords(list(args.sequence or [])),
            window_id=args.window_id or "",
            dry_run=bool(args.dry_run),
        )
    )
    return 0


def command_window_click(args: argparse.Namespace) -> int:
    target_dir = _profile_dir_from_args(args)
    _print_json(
        click_portable_window(
            target_dir,
            x_ratio=float(args.x_ratio),
            y_ratio=float(args.y_ratio),
            window_id=args.window_id or "",
            button=int(args.button),
            coordinate_space=str(args.coordinate_space or "auto"),
            dry_run=bool(args.dry_run),
        )
    )
    return 0


def command_window_screenshot(args: argparse.Namespace) -> int:
    target_dir = _profile_dir_from_args(args)
    _print_json(
        capture_portable_window_screenshot(
            target_dir,
            output_path=Path(args.output),
            window_id=args.window_id or "",
        )
    )
    return 0


def command_status(args: argparse.Namespace) -> int:
    _print_json(profile_status(_profile_dir_from_args(args)))
    return 0


def command_log_diagnose(args: argparse.Namespace) -> int:
    target_dir = _profile_dir_from_args(args)
    _print_json(
        diagnose_telegram_log(
            target_dir,
            tail_lines=int(args.tail_lines),
            max_events=int(args.max_events),
        )
    )
    return 0


def command_list(args: argparse.Namespace) -> int:
    profiles = [profile_status(path) for path in discover_profile_dirs(Path(args.output_root))]
    _print_json(
        {
            "status": "completed",
            "output_root": str(Path(args.output_root).expanduser().resolve()),
            "profiles": profiles,
        }
    )
    return 0


def command_adopt(args: argparse.Namespace) -> int:
    payload = adopt_profile(
        profile_dir=Path(args.profile_dir),
        profile_name=args.profile_name,
        account_username=args.account_username,
        account_label=args.account_label,
    )
    _print_json(payload)
    return 0


def command_accessibility_dump(args: argparse.Namespace) -> int:
    target_dir = _profile_dir_from_args(args)
    _print_json(
        list_accessible_nodes(
            target_dir,
            query=args.query or "",
            role=args.role or "",
            match_mode=args.match_mode or "contains",
            visible_only=bool(args.visible_only),
            max_results=int(args.max_results),
            pick=args.pick or "best",
            state_filters=list(args.state or []),
        )
    )
    return 0


def command_accessibility_click(args: argparse.Namespace) -> int:
    target_dir = _profile_dir_from_args(args)
    _print_json(
        click_accessible_node(
            target_dir,
            query=args.query,
            role=args.role or "",
            match_mode=args.match_mode or "contains",
            visible_only=bool(args.visible_only),
            pick=args.pick or "best",
            index=int(args.index),
            button=int(args.button),
            dry_run=bool(args.dry_run),
            state_filters=list(args.state or []),
        )
    )
    return 0


def command_accessibility_type_text(args: argparse.Namespace) -> int:
    target_dir = _profile_dir_from_args(args)
    _print_json(
        type_into_accessible_node(
            target_dir,
            query=args.query,
            text=args.text,
            role=args.role or "",
            match_mode=args.match_mode or "contains",
            visible_only=bool(args.visible_only),
            pick=args.pick or "best",
            index=int(args.index),
            clear_first=bool(args.clear_first),
            press_enter=bool(args.press_enter),
            dry_run=bool(args.dry_run),
            state_filters=list(args.state or []),
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Telegram Desktop portable helper for Linux profiles backed by TelegramForcePortable."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    import_parser = subparsers.add_parser(
        "import-zip",
        help="Import a tdata zip into a dedicated Linux Telegram portable profile and optionally launch it.",
    )
    import_parser.add_argument("--zip", required=True, help="Path to the zip archive that contains tdata.")
    import_parser.add_argument("--profile-name", help="Readable profile suffix. Defaults to the zip filename stem.")
    import_parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    import_parser.add_argument("--runtime-cache-dir", default=str(DEFAULT_RUNTIME_CACHE_DIR))
    import_parser.add_argument("--runtime-archive", help="Optional local Telegram Desktop archive (.tar.xz/.tar.gz) for offline setup.")
    import_parser.add_argument("--download-url", default=DEFAULT_TELEGRAM_LINUX_URL)
    import_parser.add_argument("--refresh-runtime", action="store_true", help="Re-download or re-import the runtime into the cache.")
    import_parser.add_argument("--launch", action="store_true", help="Launch the imported portable profile after extracting it.")
    import_parser.set_defaults(func=command_import_zip)

    launch_parser = subparsers.add_parser("launch", help="Launch an existing Telegram portable profile.")
    launch_parser.add_argument("--profile-name")
    launch_parser.add_argument("--profile-dir", help="Explicit portable profile directory. Useful for adopted legacy profiles.")
    launch_parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    launch_parser.set_defaults(func=command_launch)

    status_parser = subparsers.add_parser("status", help="Show status for a Telegram portable profile.")
    status_parser.add_argument("--profile-name")
    status_parser.add_argument("--profile-dir", help="Explicit portable profile directory. Useful for adopted legacy profiles.")
    status_parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    status_parser.set_defaults(func=command_status)

    log_parser = subparsers.add_parser(
        "log-diagnose",
        help="Parse recent Telegram Desktop portable log entries and surface RPC/App errors like PEER_FLOOD.",
    )
    log_parser.add_argument("--profile-name")
    log_parser.add_argument("--profile-dir", help="Explicit portable profile directory. Useful for adopted legacy profiles.")
    log_parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    log_parser.add_argument("--tail-lines", type=int, default=200)
    log_parser.add_argument("--max-events", type=int, default=20)
    log_parser.set_defaults(func=command_log_diagnose)

    list_parser = subparsers.add_parser("list", help="List Telegram portable profiles under an output root.")
    list_parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    list_parser.set_defaults(func=command_list)

    adopt_parser = subparsers.add_parser("adopt", help="Register an existing Telegram portable directory without re-importing tdata.")
    adopt_parser.add_argument("--profile-dir", required=True)
    adopt_parser.add_argument("--profile-name")
    adopt_parser.add_argument("--account-username")
    adopt_parser.add_argument("--account-label")
    adopt_parser.set_defaults(func=command_adopt)

    open_uri_parser = subparsers.add_parser("open-uri", help="Open a Telegram URI through a portable Telegram Desktop profile.")
    open_uri_parser.add_argument("--profile-name")
    open_uri_parser.add_argument("--profile-dir", help="Explicit portable profile directory.")
    open_uri_parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    open_uri_parser.add_argument("--uri", required=True)
    open_uri_parser.add_argument("--dry-run", action="store_true")
    open_uri_parser.set_defaults(func=command_open_uri)

    type_text_parser = subparsers.add_parser("type-text", help="Type ASCII text into the portable Telegram Desktop window.")
    type_text_parser.add_argument("--profile-name")
    type_text_parser.add_argument("--profile-dir", help="Explicit portable profile directory.")
    type_text_parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    type_text_parser.add_argument("--window-id")
    type_text_parser.add_argument("--text", required=True)
    type_text_parser.add_argument("--press-enter", action="store_true")
    type_text_parser.add_argument("--dry-run", action="store_true")
    type_text_parser.set_defaults(func=command_type_text)

    press_keys_parser = subparsers.add_parser(
        "press-keys",
        help="Send one or more X11 key chords to the portable Telegram Desktop window.",
    )
    press_keys_parser.add_argument("--profile-name")
    press_keys_parser.add_argument("--profile-dir", help="Explicit portable profile directory.")
    press_keys_parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    press_keys_parser.add_argument("--window-id")
    press_keys_parser.add_argument(
        "--sequence",
        action="append",
        default=[],
        help="Repeatable key chord like Control_L+f or Return. Use multiple --sequence flags for sequential presses.",
    )
    press_keys_parser.add_argument("--dry-run", action="store_true")
    press_keys_parser.set_defaults(func=command_press_keys)

    window_click_parser = subparsers.add_parser(
        "window-click",
        help="Click inside the portable Telegram window by relative X/Y ratios.",
    )
    window_click_parser.add_argument("--profile-name")
    window_click_parser.add_argument("--profile-dir", help="Explicit portable profile directory.")
    window_click_parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    window_click_parser.add_argument("--window-id")
    window_click_parser.add_argument("--x-ratio", type=float, required=True)
    window_click_parser.add_argument("--y-ratio", type=float, required=True)
    window_click_parser.add_argument("--button", type=int, default=1)
    window_click_parser.add_argument(
        "--coordinate-space",
        choices=("auto", "window_geometry", "accessible_window"),
        default="auto",
        help="Choose whether the click ratios are relative to the real X11 window or the AT-SPI accessible window.",
    )
    window_click_parser.add_argument("--dry-run", action="store_true")
    window_click_parser.set_defaults(func=command_window_click)

    window_screenshot_parser = subparsers.add_parser(
        "window-screenshot",
        help="Capture a PNG screenshot of the portable Telegram Desktop X11 window.",
    )
    window_screenshot_parser.add_argument("--profile-name")
    window_screenshot_parser.add_argument("--profile-dir", help="Explicit portable profile directory.")
    window_screenshot_parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    window_screenshot_parser.add_argument("--window-id")
    window_screenshot_parser.add_argument("--output", required=True)
    window_screenshot_parser.set_defaults(func=command_window_screenshot)

    accessibility_dump_parser = subparsers.add_parser(
        "accessibility-dump",
        help="List AT-SPI accessible Telegram Desktop nodes for the portable profile.",
    )
    accessibility_dump_parser.add_argument("--profile-name")
    accessibility_dump_parser.add_argument("--profile-dir", help="Explicit portable profile directory.")
    accessibility_dump_parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    accessibility_dump_parser.add_argument("--query", default="")
    accessibility_dump_parser.add_argument("--role", default="")
    accessibility_dump_parser.add_argument("--match-mode", choices=("contains", "exact"), default="contains")
    accessibility_dump_parser.add_argument("--visible-only", action="store_true")
    accessibility_dump_parser.add_argument(
        "--state",
        action="append",
        default=[],
        help="Repeatable AT-SPI state filter like focused, showing, visible, editable.",
    )
    accessibility_dump_parser.add_argument("--pick", choices=("best", "first", "rightmost", "leftmost", "topmost", "bottommost"), default="best")
    accessibility_dump_parser.add_argument("--max-results", type=int, default=50)
    accessibility_dump_parser.set_defaults(func=command_accessibility_dump)

    accessibility_click_parser = subparsers.add_parser(
        "accessibility-click",
        help="Click a Telegram Desktop accessible node found through AT-SPI.",
    )
    accessibility_click_parser.add_argument("--profile-name")
    accessibility_click_parser.add_argument("--profile-dir", help="Explicit portable profile directory.")
    accessibility_click_parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    accessibility_click_parser.add_argument("--query", required=True)
    accessibility_click_parser.add_argument("--role", default="")
    accessibility_click_parser.add_argument("--match-mode", choices=("contains", "exact"), default="contains")
    accessibility_click_parser.add_argument("--visible-only", action="store_true")
    accessibility_click_parser.add_argument(
        "--state",
        action="append",
        default=[],
        help="Repeatable AT-SPI state filter like focused, showing, visible, editable.",
    )
    accessibility_click_parser.add_argument("--pick", choices=("best", "first", "rightmost", "leftmost", "topmost", "bottommost"), default="best")
    accessibility_click_parser.add_argument("--index", type=int, default=0)
    accessibility_click_parser.add_argument("--button", type=int, default=1)
    accessibility_click_parser.add_argument("--dry-run", action="store_true")
    accessibility_click_parser.set_defaults(func=command_accessibility_click)

    accessibility_type_parser = subparsers.add_parser(
        "accessibility-type-text",
        help="Focus an accessible Telegram Desktop node and type ASCII text into it.",
    )
    accessibility_type_parser.add_argument("--profile-name")
    accessibility_type_parser.add_argument("--profile-dir", help="Explicit portable profile directory.")
    accessibility_type_parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    accessibility_type_parser.add_argument("--query", required=True)
    accessibility_type_parser.add_argument("--role", default="")
    accessibility_type_parser.add_argument("--match-mode", choices=("contains", "exact"), default="contains")
    accessibility_type_parser.add_argument("--visible-only", action="store_true")
    accessibility_type_parser.add_argument(
        "--state",
        action="append",
        default=[],
        help="Repeatable AT-SPI state filter like focused, showing, visible, editable.",
    )
    accessibility_type_parser.add_argument("--pick", choices=("best", "first", "rightmost", "leftmost", "topmost", "bottommost"), default="best")
    accessibility_type_parser.add_argument("--index", type=int, default=0)
    accessibility_type_parser.add_argument("--text", required=True)
    accessibility_type_parser.add_argument("--clear-first", action="store_true")
    accessibility_type_parser.add_argument("--press-enter", action="store_true")
    accessibility_type_parser.add_argument("--dry-run", action="store_true")
    accessibility_type_parser.set_defaults(func=command_accessibility_type_text)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
