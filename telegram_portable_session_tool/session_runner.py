from __future__ import annotations

import ast
import json
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .config import load_config
from .models import MessageDraft, SessionPlan, ToolConfig
from .planner import build_session_plan, default_state
from .portable_bridge import PortableBridge
from .sync_sources import build_message_target_candidates, resolve_targets


INPUT_SOURCES_SCHEMA = "org.gnome.desktop.input-sources"
INPUT_SOURCES_KEY = "sources"
INPUT_SOURCES_CURRENT_KEY = "current"
RUSSIAN_KEY_MAP = {
    "й": "q",
    "ц": "w",
    "у": "e",
    "к": "r",
    "е": "t",
    "н": "y",
    "г": "u",
    "ш": "i",
    "щ": "o",
    "з": "p",
    "х": "bracketleft",
    "ъ": "bracketright",
    "ф": "a",
    "ы": "s",
    "в": "d",
    "а": "f",
    "п": "g",
    "р": "h",
    "о": "j",
    "л": "k",
    "д": "l",
    "ж": "semicolon",
    "э": "apostrophe",
    "я": "z",
    "ч": "x",
    "с": "c",
    "м": "v",
    "и": "b",
    "т": "n",
    "ь": "m",
    "б": "comma",
    "ю": "period",
    "ё": "grave",
}
RUSSIAN_PUNCTUATION_MAP = {
    " ": "space",
    "\n": "Return",
    "!": "Shift_L+1",
    "\"": "Shift_L+2",
    "№": "Shift_L+3",
    ";": "Shift_L+4",
    "%": "Shift_L+5",
    ":": "Shift_L+6",
    "?": "Shift_L+7",
    "*": "Shift_L+8",
    "(": "Shift_L+9",
    ")": "Shift_L+0",
    "-": "minus",
    "_": "Shift_L+minus",
    "+": "Shift_L+equal",
    "=": "equal",
    ".": "slash",
    ",": "Shift_L+slash",
}


def load_state(path: Path) -> dict:
    if not path.exists():
        return default_state()
    payload = json.loads(path.read_text(encoding="utf-8"))
    state = default_state()
    if isinstance(payload, dict):
        state.update(payload)
    return state


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def default_send_confirmation(message: MessageDraft) -> bool:
    answer = input(f"Отправить сообщение #{message.index}: {message.text!r}? Введите YES: ").strip()
    return answer == "YES"


def ensure_running(bridge: PortableBridge, launch_if_needed: bool) -> dict:
    status = bridge.status()
    if status.get("running"):
        return status
    if not launch_if_needed:
        raise RuntimeError("Portable Telegram is not running; use --launch-if-needed")
    bridge.launch()
    return bridge.status()


def _timestamp_run_id(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    return f"{current.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _contains_cyrillic(text: str) -> bool:
    return any("а" <= char.lower() <= "я" or char.lower() == "ё" for char in str(text or ""))


def _run_gsettings(*args: str) -> str:
    completed = subprocess.run(["gsettings", *args], check=True, capture_output=True, text=True)
    return str(completed.stdout or "").strip()


def _get_input_sources() -> list[tuple[str, str]]:
    raw = _run_gsettings("get", INPUT_SOURCES_SCHEMA, INPUT_SOURCES_KEY)
    parsed = ast.literal_eval(raw)
    if not isinstance(parsed, list):
        return []
    sources: list[tuple[str, str]] = []
    for item in parsed:
        if not isinstance(item, tuple) or len(item) != 2:
            continue
        source_type = str(item[0]).strip()
        layout = str(item[1]).strip()
        if source_type and layout:
            sources.append((source_type, layout))
    return sources


def _get_current_input_source() -> int | None:
    raw = _run_gsettings("get", INPUT_SOURCES_SCHEMA, INPUT_SOURCES_CURRENT_KEY)
    parts = raw.split()
    if not parts:
        return None
    try:
        return int(parts[-1])
    except ValueError:
        return None


def _set_current_input_source(index: int) -> None:
    _run_gsettings("set", INPUT_SOURCES_SCHEMA, INPUT_SOURCES_CURRENT_KEY, str(int(index)))


def _preferred_input_source_index(
    text: str,
    *,
    get_input_sources_fn: Callable[[], list[tuple[str, str]]],
) -> int | None:
    desired_layout = "ru" if _contains_cyrillic(text) else "us"
    for index, item in enumerate(get_input_sources_fn()):
        if len(item) != 2:
            continue
        if str(item[1]).strip() == desired_layout:
            return index
    return None


def _russian_text_to_key_sequences(text: str) -> list[str]:
    sequences: list[str] = []
    for char in str(text or ""):
        lower = char.lower()
        if lower in RUSSIAN_KEY_MAP:
            key = RUSSIAN_KEY_MAP[lower]
            if char != lower:
                sequences.append(f"Shift_L+{key}")
            else:
                sequences.append(key)
            continue
        if char in RUSSIAN_PUNCTUATION_MAP:
            sequences.append(RUSSIAN_PUNCTUATION_MAP[char])
            continue
        if "0" <= char <= "9":
            sequences.append(char)
            continue
        raise ValueError(f"unsupported character for Russian X11 typing: {char!r}")
    return sequences


def _draft_message_text(
    *,
    bridge: PortableBridge,
    config: ToolConfig,
    text: str,
    sleep_fn: Callable[[float], None],
    get_input_source_fn: Callable[[], int | None],
    set_input_source_fn: Callable[[int], None],
    get_input_sources_fn: Callable[[], list[tuple[str, str]]],
) -> tuple[dict, dict, int | None]:
    focus_result = bridge.window_click(
        x_ratio=float(config.session.message_input_x_ratio),
        y_ratio=float(config.session.message_input_y_ratio),
        coordinate_space="window_geometry",
    )
    if config.session.message_focus_delay_seconds > 0:
        sleep_fn(float(config.session.message_focus_delay_seconds))

    clear_result = bridge.press_keys("Control_L+a", "BackSpace")
    previous_input_source = get_input_source_fn()
    target_input_source = _preferred_input_source_index(text, get_input_sources_fn=get_input_sources_fn)
    if target_input_source is not None and target_input_source != previous_input_source:
        set_input_source_fn(target_input_source)
        sleep_fn(0.15)

    if _contains_cyrillic(text):
        sequences = _russian_text_to_key_sequences(text)
        raw_type_result = bridge.press_keys(*sequences)
        text_mode = "x11_keys_ru"
    else:
        raw_type_result = bridge.type_text(text, press_enter=False)
        text_mode = "x11_keys_us"

    type_result = dict(raw_type_result)
    type_result["text_mode"] = text_mode
    type_result["clear_result"] = clear_result
    type_result["input_source_before"] = previous_input_source
    type_result["input_source_target"] = target_input_source
    return focus_result, type_result, previous_input_source


def _is_stop_requested(stop_requested: Callable[[], bool] | None) -> bool:
    return bool(stop_requested is not None and stop_requested())


def _sleep_interruptibly(
    duration_seconds: float,
    *,
    sleep_fn: Callable[[float], None],
    stop_requested: Callable[[], bool] | None,
    step_seconds: float = 0.2,
) -> bool:
    remaining = max(0.0, float(duration_seconds))
    if remaining <= 0:
        return not _is_stop_requested(stop_requested)
    while remaining > 0:
        if _is_stop_requested(stop_requested):
            return False
        interval = min(step_seconds, remaining)
        sleep_fn(interval)
        remaining = max(0.0, remaining - interval)
    return not _is_stop_requested(stop_requested)


def _click_send_button(bridge: PortableBridge, config: ToolConfig) -> dict:
    attempts: list[dict] = []
    try:
        accessibility_result = bridge.accessibility_click(
            query="Отправить",
            role="push button",
            match_mode="exact",
            visible_only=True,
            state_filters=("showing",),
            pick="rightmost",
        )
        attempts.append({"method": "accessibility_click", "result": accessibility_result})
        return {
            "status": "completed",
            "send_strategy": "send_button",
            "button_method": "accessibility_click",
            "attempts": attempts,
        }
    except Exception as exc:
        attempts.append({"method": "accessibility_click", "error": str(exc)})

    ratio_result = bridge.window_click(
        x_ratio=float(config.session.message_send_button_x_ratio),
        y_ratio=float(config.session.message_send_button_y_ratio),
        coordinate_space="window_geometry",
    )
    attempts.append({"method": "window_click", "result": ratio_result})
    return {
        "status": "completed",
        "send_strategy": "send_button",
        "button_method": "window_click",
        "attempts": attempts,
    }


def _send_via_double_return(bridge: PortableBridge) -> dict:
    payload = dict(bridge.press_keys("Return", "Return"))
    payload["send_strategy"] = "double_return"
    payload["attempts"] = [{"method": "double_return", "result": dict(payload)}]
    return payload


def _send_drafted_message(bridge: PortableBridge, config: ToolConfig) -> dict:
    strategy = str(config.session.message_send_strategy or "send_button_then_return")
    if strategy == "double_return":
        return _send_via_double_return(bridge)
    if strategy == "send_button":
        return _click_send_button(bridge, config)
    if strategy == "return_then_button":
        primary = _send_via_double_return(bridge)
        fallback = _click_send_button(bridge, config)
        return {
            "status": "completed",
            "send_strategy": "return_then_button",
            "primary_method": "double_return",
            "fallback_method": fallback.get("button_method"),
            "attempts": list(primary.get("attempts", [])) + list(fallback.get("attempts", [])),
        }

    primary = _click_send_button(bridge, config)
    fallback = _send_via_double_return(bridge)
    return {
        "status": "completed",
        "send_strategy": "send_button_then_return",
        "primary_method": primary.get("button_method"),
        "fallback_method": "double_return",
        "attempts": list(primary.get("attempts", [])) + list(fallback.get("attempts", [])),
    }


def run_session(
    *,
    config: ToolConfig,
    state_path: Path,
    runs_dir: Path,
    execute: bool,
    launch_if_needed: bool,
    confirm_send: bool,
    auto_send: bool,
    seed: str | None = None,
    approval_callback: Callable[[MessageDraft], bool] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    now: datetime | None = None,
    bridge: PortableBridge | None = None,
    get_input_source_fn: Callable[[], int | None] = _get_current_input_source,
    set_input_source_fn: Callable[[int], None] = _set_current_input_source,
    get_input_sources_fn: Callable[[], list[tuple[str, str]]] = _get_input_sources,
    stop_requested: Callable[[], bool] | None = None,
) -> dict:
    state = load_state(state_path)
    plan = build_session_plan(config, state, now=now, seed=seed)
    run_id = _timestamp_run_id(now)
    run_dir = runs_dir / run_id
    _write_json(run_dir / "plan.json", plan.to_dict())

    report = {
        "run_id": run_id,
        "execute": bool(execute),
        "confirm_send": bool(confirm_send),
        "auto_send": bool(auto_send),
        "plan": plan.to_dict(),
        "visits": [],
        "messages": [],
        "sent_count": 0,
    }

    if not execute:
        report["status"] = "dry_run"
        _write_json(run_dir / "run.json", report)
        return report

    resolved_bridge = bridge or PortableBridge(
        site_control_kit_root=Path(config.site_control_kit_root),
        profile_dir=Path(config.portable_profile_dir),
        python_bin=config.python_bin,
    )
    status = ensure_running(resolved_bridge, launch_if_needed)
    report["portable_status"] = status

    stopped_early = False
    message_errors = 0

    for visit in plan.visits:
        if _is_stop_requested(stop_requested):
            stopped_early = True
            break
        if visit.action == "sidebar_click":
            open_result = resolved_bridge.window_click(
                x_ratio=float(visit.x_ratio if visit.x_ratio is not None else 0.14),
                y_ratio=float(visit.y_ratio if visit.y_ratio is not None else 0.5),
                coordinate_space="window_geometry",
            )
        else:
            open_result = resolved_bridge.open_uri(visit.uri)
        report["visits"].append(
            {
                "target_id": visit.target_id,
                "label": visit.label,
                "kind": visit.kind,
                "action": visit.action,
                "uri": visit.uri,
                "x_ratio": visit.x_ratio,
                "y_ratio": visit.y_ratio,
                "view_seconds": visit.view_seconds,
                "open_result": open_result,
            }
        )
        if visit.view_seconds > 0:
            if not _sleep_interruptibly(
                float(visit.view_seconds),
                sleep_fn=sleep_fn,
                stop_requested=stop_requested,
            ):
                stopped_early = True
                break

    approve = approval_callback or default_send_confirmation
    for draft in plan.message_drafts:
        if stopped_early or _is_stop_requested(stop_requested):
            stopped_early = True
            break
        open_target = resolved_bridge.open_uri(plan.message_target_uri)
        if config.session.message_open_delay_seconds > 0:
            if not _sleep_interruptibly(
                float(config.session.message_open_delay_seconds),
                sleep_fn=sleep_fn,
                stop_requested=stop_requested,
            ):
                stopped_early = True
                break
        previous_input_source: int | None = None
        message_report = {
            "index": draft.index,
            "text": draft.text,
            "open_result": open_target,
            "sent": False,
        }
        try:
            focus_result, type_result, previous_input_source = _draft_message_text(
                bridge=resolved_bridge,
                config=config,
                text=draft.text,
                sleep_fn=sleep_fn,
                get_input_source_fn=get_input_source_fn,
                set_input_source_fn=set_input_source_fn,
                get_input_sources_fn=get_input_sources_fn,
            )
            message_report["focus_result"] = focus_result
            message_report["draft_result"] = type_result
            if auto_send:
                if config.session.message_send_delay_seconds > 0:
                    if not _sleep_interruptibly(
                        float(config.session.message_send_delay_seconds),
                        sleep_fn=sleep_fn,
                        stop_requested=stop_requested,
                    ):
                        stopped_early = True
                        message_report["send_mode"] = "interrupted_before_send"
                    else:
                        send_result = _send_drafted_message(resolved_bridge, config)
                        message_report["sent"] = True
                        message_report["send_result"] = send_result
                        message_report["send_mode"] = "auto"
            elif confirm_send and approve(draft):
                if config.session.message_send_delay_seconds > 0:
                    if not _sleep_interruptibly(
                        float(config.session.message_send_delay_seconds),
                        sleep_fn=sleep_fn,
                        stop_requested=stop_requested,
                    ):
                        stopped_early = True
                        message_report["send_mode"] = "interrupted_before_send"
                    else:
                        send_result = _send_drafted_message(resolved_bridge, config)
                        message_report["sent"] = True
                        message_report["send_result"] = send_result
                        message_report["send_mode"] = "confirm"
            else:
                message_report["send_mode"] = "draft_only"
        except Exception as exc:
            message_errors += 1
            message_report["error"] = str(exc)
            if "send_mode" not in message_report:
                message_report["send_mode"] = "failed"
        finally:
            report["messages"].append(message_report)
            if previous_input_source is not None:
                set_input_source_fn(previous_input_source)
        if not stopped_early:
            if not _sleep_interruptibly(1.0, sleep_fn=sleep_fn, stop_requested=stop_requested):
                stopped_early = True

    processed_messages = len(report["messages"])
    sent_count = sum(1 for item in report["messages"] if item.get("sent"))
    report["sent_count"] = sent_count

    state["message_cursor"] = int(state.get("message_cursor", 0)) + processed_messages
    state["messages_sent_total"] = int(state.get("messages_sent_total", 0)) + sent_count
    if processed_messages and config.message_policy.target_mode != "fixed" and plan.message_target_username:
        state["message_target_cursor"] = int(state.get("message_target_cursor", 0)) + 1
    state.setdefault("history", []).append(
        {
            "run_id": run_id,
            "seed": plan.seed,
            "draft_count": processed_messages,
            "sent_count": sent_count,
            "visit_count": len(report["visits"]),
            "status": "stopped" if stopped_early else ("completed_with_errors" if message_errors else "completed"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )
    state["history"] = state["history"][-50:]
    save_state(state_path, state)

    if stopped_early:
        report["status"] = "stopped"
    elif message_errors:
        report["status"] = "completed_with_errors"
    else:
        report["status"] = "completed"
    _write_json(run_dir / "run.json", report)
    return report


def run_session_continuous(
    *,
    config: ToolConfig,
    state_path: Path,
    runs_dir: Path,
    execute: bool,
    launch_if_needed: bool,
    confirm_send: bool,
    auto_send: bool,
    seed: str | None = None,
    approval_callback: Callable[[MessageDraft], bool] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    bridge: PortableBridge | None = None,
    get_input_source_fn: Callable[[], int | None] = _get_current_input_source,
    set_input_source_fn: Callable[[int], None] = _set_current_input_source,
    get_input_sources_fn: Callable[[], list[tuple[str, str]]] = _get_input_sources,
    stop_requested: Callable[[], bool] | None = None,
    cycle_limit: int = 0,
) -> dict:
    started_at = datetime.now(timezone.utc)
    completed_cycles = 0
    cycle_summaries: list[dict] = []
    last_run: dict | None = None

    while True:
        if _is_stop_requested(stop_requested):
            break
        if cycle_limit > 0 and completed_cycles >= cycle_limit:
            break
        payload = run_session(
            config=config,
            state_path=state_path,
            runs_dir=runs_dir,
            execute=execute,
            launch_if_needed=launch_if_needed,
            confirm_send=confirm_send,
            auto_send=auto_send,
            seed=seed,
            approval_callback=approval_callback,
            sleep_fn=sleep_fn,
            bridge=bridge,
            get_input_source_fn=get_input_source_fn,
            set_input_source_fn=set_input_source_fn,
            get_input_sources_fn=get_input_sources_fn,
            stop_requested=stop_requested,
        )
        last_run = payload
        completed_cycles += 1
        cycle_summaries.append(
            {
                "run_id": payload.get("run_id"),
                "status": payload.get("status"),
                "visit_count": len(payload.get("visits", [])),
                "draft_count": len(payload.get("messages", [])),
                "sent_count": int(payload.get("sent_count", 0)),
            }
        )
        if str(payload.get("status") or "").strip().lower() == "stopped":
            break
        if _is_stop_requested(stop_requested):
            break

    finished_at = datetime.now(timezone.utc)
    return {
        "status": "stopped" if _is_stop_requested(stop_requested) else "completed",
        "continuous": True,
        "cycle_count": completed_cycles,
        "elapsed_seconds": round((finished_at - started_at).total_seconds(), 1),
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "cycles": cycle_summaries[-50:],
        "run": last_run or {},
        "state": load_state(state_path),
    }


def plan_session(*, config_path: Path, state_path: Path, seed: str | None = None, now: datetime | None = None) -> dict:
    config = load_config(config_path)
    state = load_state(state_path)
    return build_session_plan(config, state, now=now, seed=seed).to_dict()


def sync_preview(*, config_path: Path) -> dict:
    config = load_config(config_path)
    resolved = resolve_targets(config)
    message_candidates = build_message_target_candidates(config, resolved)
    return {
        "groups": [item.to_dict() for item in resolved.groups],
        "contacts": [item.to_dict() for item in resolved.contacts],
        "message_targets": [item.to_dict() for item in message_candidates],
        "reports": [item.to_dict() for item in resolved.reports],
    }
