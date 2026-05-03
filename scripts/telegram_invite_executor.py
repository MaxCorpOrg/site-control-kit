#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import html
import io
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    from scripts.telegram_invite_manager import (
        DEFAULT_SELECTABLE_STATUSES,
        append_history,
        atomic_write_json,
        build_user_record,
        chat_slug_from_chat_url,
        consent_label,
        ensure_valid_status,
        load_input_rows,
        load_state,
        normalize_username,
        now_utc,
        parse_consent,
        prepare_users,
        save_state,
        select_candidates,
        summarize_state,
        state_path_for,
        write_run_artifacts,
    )
except ImportError:
    from telegram_invite_manager import (  # type: ignore
        DEFAULT_SELECTABLE_STATUSES,
        append_history,
        atomic_write_json,
        build_user_record,
        chat_slug_from_chat_url,
        consent_label,
        ensure_valid_status,
        load_input_rows,
        load_state,
        normalize_username,
        now_utc,
        parse_consent,
        prepare_users,
        save_state,
        select_candidates,
        summarize_state,
        state_path_for,
        write_run_artifacts,
    )


DEFAULT_MESSAGE_TEMPLATE = "Привет! Вот ссылка для вступления в чат: {invite_link}"
DEFAULT_EXECUTION_STATUSES = ("checked",)
DEFAULT_CONTACT_BATCH_STATUSES = ("new", "checked", "failed")
MEMBER_COUNT_RE = re.compile(r"(?P<count>\d[\d\s,.]*)\s+members?\b", re.IGNORECASE)
DESKTOP_ADD_CONTACT_X_RATIO = 0.3364
DESKTOP_ADD_CONTACT_Y_RATIO = 0.5417
DESKTOP_DONE_CONTACT_X_RATIO = 0.5785
DESKTOP_DONE_CONTACT_Y_RATIO = 0.7956
DESKTOP_ADD_CONTACT_BUTTON_TERMS = ("ДОБАВИТЬ КОНТАКТ", "Добавить контакт", "ADD TO CONTACTS", "Add to contacts")
DESKTOP_ADD_TO_CONTACTS_CHAT_TERMS = ("В КОНТАКТЫ", "TO CONTACTS")
DESKTOP_DONE_BUTTON_TERMS = ("Готово", "Done")
DESKTOP_FIRST_NAME_TERMS = ("Имя", "First name")
DESKTOP_LAST_NAME_TERMS = ("Фамилия", "Last name")
DESKTOP_CONTACT_EDIT_TERMS = ("ИЗМЕНИТЬ КОНТАКТ", "Изменить контакт", "EDIT CONTACT", "Edit contact")
DESKTOP_CONTACT_DELETE_TERMS = ("УДАЛИТЬ КОНТАКТ", "Удалить контакт", "DELETE CONTACT", "Delete contact")
CONTACT_VERIFY_ADD_TERMS = (*DESKTOP_ADD_CONTACT_BUTTON_TERMS, *DESKTOP_ADD_TO_CONTACTS_CHAT_TERMS)
CONTACT_VERIFY_SUCCESS_TERMS = (*DESKTOP_CONTACT_EDIT_TERMS, *DESKTOP_CONTACT_DELETE_TERMS)
CONTACT_ADD_SUCCESS_OUTCOMES = ("contact_added_verified", "contact_already_present")
ADD_MEMBERS_OPEN_SELECTORS = (
    "#column-right .profile-container.can-add-members button.btn-circle.btn-corner",
    "#column-right .profile-container.can-add-members button.btn-circle",
    ".profile-container.can-add-members button.btn-circle.btn-corner",
)
ADD_MEMBERS_SEARCH_SELECTOR = ".add-members-container .selector-search-input"
ADD_MEMBERS_CONFIRM_SELECTOR = ".add-members-container > .sidebar-content > button.btn-circle.btn-corner"
ADD_MEMBERS_POPUP_ADD_SELECTOR = ".popup-add-members .popup-buttons button:nth-child(1)"
ADD_MEMBERS_CLOSE_SELECTOR = ".add-members-container .sidebar-close-button"
MEMBERS_TAB_MARKERS = (
    'search-super-tab-container search-super-container-members tabs-tab active',
    'search-super-tab-container search-super-container-members tabs-tab',
)
MEMBERS_TAB_STOP_MARKERS = (
    'search-super-tab-container search-super-container-media',
    'search-super-tab-container search-super-container-gifts',
    'search-super-tab-container search-super-container-saved',
    'search-super-tab-container search-super-container-files',
    'search-super-tab-container search-super-container-links',
    'search-super-tab-container search-super-container-music',
    'search-super-tab-container search-super-container-voice',
    'search-super-tab-container search-super-container-groups',
    'search-super-tab-container search-super-container-similar',
)
PUBLIC_TELEGRAM_HANDLE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")


def _execution_runs_dir(job_dir: Path) -> Path:
    return job_dir / "executions"


def _execution_state(payload: dict[str, Any]) -> dict[str, Any]:
    execution = payload.get("execution")
    if not isinstance(execution, dict):
        execution = {}
        payload["execution"] = execution
    browser_target = execution.get("browser_target")
    if not isinstance(browser_target, dict):
        browser_target = {}
        execution["browser_target"] = browser_target
    portable_actor = execution.get("portable_actor")
    if not isinstance(portable_actor, dict):
        portable_actor = {}
        execution["portable_actor"] = portable_actor
    return execution


def _bool_flag(value: bool | None, *, default: bool) -> bool:
    if value is None:
        return bool(default)
    return bool(value)


def _nonempty(value: Any) -> str:
    return str(value or "").strip()


def _normalize_space(value: Any) -> str:
    return " ".join(str(value or "").split())


def _merge_execution_config(
    payload: dict[str, Any],
    *,
    invite_link: str | None = None,
    message_template: str | None = None,
    note: str | None = None,
    requires_approval: bool | None = None,
    client_id: str | None = None,
    tab_id: int | None = None,
    url_pattern: str | None = None,
    active: bool | None = None,
    portable_profile_name: str | None = None,
    portable_profile_dir: str | None = None,
    account_username: str | None = None,
    account_label: str | None = None,
) -> dict[str, Any]:
    execution = _execution_state(payload)
    browser_target = execution["browser_target"]
    portable_actor = execution["portable_actor"]

    if invite_link is not None:
        execution["invite_link"] = _nonempty(invite_link)
    if message_template is not None:
        execution["message_template"] = _nonempty(message_template)
    if note is not None:
        execution["note"] = _nonempty(note)
    if requires_approval is not None:
        execution["requires_approval"] = bool(requires_approval)
    if client_id is not None:
        browser_target["client_id"] = _nonempty(client_id)
    if tab_id is not None:
        browser_target["tab_id"] = int(tab_id)
    if url_pattern is not None:
        browser_target["url_pattern"] = _nonempty(url_pattern)
    if active is not None:
        browser_target["active"] = bool(active)
    if portable_profile_name is not None:
        portable_actor["profile_name"] = _nonempty(portable_profile_name)
    if portable_profile_dir is not None:
        portable_actor["profile_dir"] = _nonempty(portable_profile_dir)
    if account_username is not None:
        portable_actor["account_username"] = _nonempty(account_username)
    if account_label is not None:
        portable_actor["account_label"] = _nonempty(account_label)
    return execution


def _resolved_execution_config(
    payload: dict[str, Any],
    *,
    invite_link: str | None = None,
    message_template: str | None = None,
    note: str | None = None,
    requires_approval: bool | None = None,
    client_id: str | None = None,
    tab_id: int | None = None,
    url_pattern: str | None = None,
    active: bool | None = None,
    portable_profile_name: str | None = None,
    portable_profile_dir: str | None = None,
    account_username: str | None = None,
    account_label: str | None = None,
) -> dict[str, Any]:
    execution = dict(_execution_state(payload))
    browser_target = dict(execution.get("browser_target") or {})
    execution["browser_target"] = browser_target
    portable_actor = dict(execution.get("portable_actor") or {})
    execution["portable_actor"] = portable_actor

    if invite_link is not None:
        execution["invite_link"] = _nonempty(invite_link)
    execution.setdefault("invite_link", "")

    if message_template is not None:
        execution["message_template"] = _nonempty(message_template)
    execution.setdefault("message_template", DEFAULT_MESSAGE_TEMPLATE)

    if note is not None:
        execution["note"] = _nonempty(note)
    execution.setdefault("note", "")

    execution["requires_approval"] = _bool_flag(
        requires_approval,
        default=bool(execution.get("requires_approval", True)),
    )

    if client_id is not None:
        browser_target["client_id"] = _nonempty(client_id)
    browser_target.setdefault("client_id", "")

    if tab_id is not None:
        browser_target["tab_id"] = int(tab_id)
    browser_target.setdefault("tab_id", 0)

    if url_pattern is not None:
        browser_target["url_pattern"] = _nonempty(url_pattern)
    browser_target.setdefault("url_pattern", "")

    if active is not None:
        browser_target["active"] = bool(active)
    browser_target["active"] = _bool_flag(browser_target.get("active"), default=True)

    if portable_profile_name is not None:
        portable_actor["profile_name"] = _nonempty(portable_profile_name)
    portable_actor.setdefault("profile_name", "")

    if portable_profile_dir is not None:
        portable_actor["profile_dir"] = _nonempty(portable_profile_dir)
    portable_actor.setdefault("profile_dir", "")

    if account_username is not None:
        portable_actor["account_username"] = _nonempty(account_username)
    portable_actor.setdefault("account_username", "")

    if account_label is not None:
        portable_actor["account_label"] = _nonempty(account_label)
    portable_actor.setdefault("account_label", "")
    return execution


def _format_message(template: str, user: dict[str, Any], invite_link: str, chat_url: str) -> str:
    return str(template).format(
        username=str(user.get("username") or ""),
        display_name=str(user.get("display_name") or "").strip() or str(user.get("username") or ""),
        invite_link=invite_link,
        chat_url=chat_url,
        note=str(user.get("note") or "").strip(),
        source=str(user.get("source") or "").strip(),
    )


def _plan_users(
    payload: dict[str, Any],
    *,
    limit: int,
    statuses: list[str] | tuple[str, ...],
    execution: dict[str, Any],
) -> list[dict[str, Any]]:
    selected = select_candidates(payload, limit, statuses)
    return [_plan_row_for_user(row, execution=execution, chat_url=_nonempty(payload.get("chat_url"))) for row in selected]


def _plan_row_for_user(row: dict[str, Any], *, execution: dict[str, Any], chat_url: str) -> dict[str, Any]:
    invite_link = _nonempty(execution.get("invite_link"))
    message_template = _nonempty(execution.get("message_template")) or DEFAULT_MESSAGE_TEMPLATE
    requires_approval = bool(execution.get("requires_approval", True))
    action = "share_invite_link" if invite_link else "prepare_invite_link"
    plan_row = {
        "username": str(row.get("username") or ""),
        "display_name": str(row.get("display_name") or ""),
        "note": str(row.get("note") or ""),
        "source": str(row.get("source") or ""),
        "from_status": str(row.get("status") or ""),
        "action": action,
        "invite_link": invite_link,
        "requires_approval": requires_approval,
    }
    if invite_link:
        plan_row["message_text"] = _format_message(message_template, row, invite_link, chat_url)
    return plan_row


def _write_execution_artifacts(job_dir: Path, execution_id: str, payload: dict[str, Any], log_lines: list[str]) -> Path:
    run_dir = _execution_runs_dir(job_dir) / execution_id
    run_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(run_dir / "execution_plan.json", payload)
    (run_dir / "execution.log").write_text("\n".join(log_lines) + ("\n" if log_lines else ""), encoding="utf-8")
    return run_dir


def _write_execution_record(job_dir: Path, execution_id: str, payload: dict[str, Any], log_lines: list[str]) -> Path:
    run_dir = _execution_runs_dir(job_dir) / execution_id
    run_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(run_dir / "execution_record.json", payload)
    (run_dir / "execution_record.log").write_text("\n".join(log_lines) + ("\n" if log_lines else ""), encoding="utf-8")
    return run_dir


def _execution_id_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _invoke_json_command(func: Any, namespace: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        rc = int(func(namespace))
    raw_output = buffer.getvalue().strip()
    if not raw_output:
        raise RuntimeError("command returned empty stdout")
    payload = json.loads(raw_output)
    if not isinstance(payload, dict):
        raise RuntimeError("command returned non-object JSON payload")
    return rc, payload


def _init_job_state_from_input(
    *,
    job_dir: Path,
    input_path: Path,
    chat_url: str,
) -> dict[str, Any]:
    imported_at = now_utc()
    rows = load_input_rows(input_path)
    users, import_stats = prepare_users(rows, imported_at)
    state = {
        "version": 1,
        "chat_url": chat_url,
        "chat_slug": chat_slug_from_chat_url(chat_url),
        "created_at": imported_at,
        "updated_at": imported_at,
        "source_file": str(input_path),
        "users": users,
        "import_stats": import_stats,
    }
    job_dir.mkdir(parents=True, exist_ok=True)
    save_state(job_dir, state)
    return state


def _write_contact_batch_artifacts(
    job_dir: Path,
    execution_id: str,
    payload: dict[str, Any],
    log_lines: list[str],
) -> Path:
    run_dir = _execution_runs_dir(job_dir) / execution_id
    run_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(run_dir / "batch_contact_add.json", payload)
    (run_dir / "batch_contact_add.log").write_text(
        "\n".join(log_lines) + ("\n" if log_lines else ""),
        encoding="utf-8",
    )
    return run_dir


def _portable_visible_match_count(result: dict[str, Any]) -> int:
    stdout_json = result.get("stdout_json")
    if not isinstance(stdout_json, dict):
        return 0
    matches = stdout_json.get("matches")
    if not isinstance(matches, list):
        return 0
    return sum(1 for row in matches if isinstance(row, dict))


def _portable_contact_verify_summary(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    add_visible = False
    success_visible = False
    visible_terms: list[str] = []
    term_counts: dict[str, int] = {}
    for term in CONTACT_VERIFY_ADD_TERMS:
        result = results.get(term) or {}
        count = _portable_visible_match_count(result)
        term_counts[term] = count
        if count > 0:
            add_visible = True
            visible_terms.append(term)
    for term in CONTACT_VERIFY_SUCCESS_TERMS:
        result = results.get(term) or {}
        count = _portable_visible_match_count(result)
        term_counts[term] = count
        if count > 0:
            success_visible = True
            visible_terms.append(term)
    if success_visible:
        outcome = "contact_added_verified"
    elif add_visible:
        outcome = "contact_not_added"
    else:
        outcome = "contact_add_unverified"
    return {
        "outcome": outcome,
        "add_visible": add_visible,
        "success_visible": success_visible,
        "term_counts": term_counts,
        "visible_terms": visible_terms,
    }


def _is_contact_add_success_outcome(value: Any) -> bool:
    return str(value or "").strip() in CONTACT_ADD_SUCCESS_OUTCOMES


def _browser_command(
    repo_root: Path,
    *,
    chat_url: str,
    browser_target: dict[str, Any],
) -> list[str]:
    command = ["python3", "-m", "webcontrol", "browser"]
    client_id = _nonempty(browser_target.get("client_id"))
    if client_id:
        command.extend(["--client-id", client_id])

    tab_id = int(browser_target.get("tab_id", 0) or 0)
    url_pattern = _nonempty(browser_target.get("url_pattern"))
    if tab_id > 0:
        command.extend(["--tab-id", str(tab_id), "activate"])
        return command
    if url_pattern:
        command.extend(["--url-pattern", url_pattern, "activate"])
        return command
    command.extend(["new-tab", _preferred_chat_url(chat_url)])
    return command


def _preferred_chat_url(chat_url: str) -> str:
    value = _nonempty(chat_url)
    if not value:
        return ""
    parsed = urlparse(value)
    host = (parsed.netloc or "").lower()
    if host not in {"t.me", "telegram.me", "www.t.me", "www.telegram.me"}:
        return value
    path = str(parsed.path or "").strip("/")
    if not path or "/" in path:
        return value
    handle = path.lstrip("@")
    if not PUBLIC_TELEGRAM_HANDLE_RE.fullmatch(handle):
        return value
    return f"https://web.telegram.org/k/#@{handle}"


def _run_browser_command(repo_root: Path, command: list[str]) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo_root)
    return subprocess.run(
        command,
        cwd=str(repo_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def _browser_target_args(browser_target: dict[str, Any]) -> list[str]:
    args: list[str] = []
    client_id = _nonempty(browser_target.get("client_id"))
    if client_id:
        args.extend(["--client-id", client_id])

    tab_id = int(browser_target.get("tab_id", 0) or 0)
    if tab_id > 0:
        args.extend(["--tab-id", str(tab_id)])
        return args

    url_pattern = _nonempty(browser_target.get("url_pattern"))
    if url_pattern:
        args.extend(["--url-pattern", url_pattern])
    return args


def _browser_action_command(browser_target: dict[str, Any], action: str, *action_args: str) -> list[str]:
    return ["python3", "-m", "webcontrol", "browser", *_browser_target_args(browser_target), action, *action_args]


def _run_browser_json(repo_root: Path, command: list[str]) -> dict[str, Any]:
    proc = _run_browser_command(repo_root, command)
    payload: dict[str, Any] = {
        "command": command,
        "returncode": int(proc.returncode),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "stdout_json": {},
    }
    try:
        payload["stdout_json"] = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        payload["stdout_json"] = {}
    return payload


def _portable_actor_args(actor: dict[str, Any]) -> list[str]:
    profile_dir = _nonempty(actor.get("profile_dir"))
    if profile_dir:
        return ["--profile-dir", profile_dir]
    profile_name = _nonempty(actor.get("profile_name"))
    if profile_name:
        return ["--profile-name", profile_name]
    return []


def _portable_command(repo_root: Path, actor: dict[str, Any], action: str) -> list[str]:
    actor_args = _portable_actor_args(actor)
    if not actor_args:
        raise ValueError("portable actor requires profile_name or profile_dir")
    return ["python3", str(repo_root / "scripts" / "telegram_portable.py"), action, *actor_args]


def _portable_action_command(repo_root: Path, actor: dict[str, Any], action: str, *action_args: str) -> list[str]:
    return [*_portable_command(repo_root, actor, action), *action_args]


def _run_portable_json(repo_root: Path, command: list[str]) -> dict[str, Any]:
    proc = subprocess.run(
        command,
        cwd=str(repo_root),
        check=False,
        capture_output=True,
        text=True,
    )
    payload: dict[str, Any] = {
        "command": command,
        "returncode": int(proc.returncode),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "stdout_json": {},
    }
    try:
        payload["stdout_json"] = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        payload["stdout_json"] = {}
    return payload


def _telegram_public_chat_uri(chat_url: str) -> str:
    value = _nonempty(chat_url)
    if not value:
        return ""
    parsed = urlparse(value)
    host = (parsed.netloc or "").lower()
    if host not in {"t.me", "telegram.me", "www.t.me", "www.telegram.me"}:
        return ""
    path = str(parsed.path or "").strip("/")
    if not path or "/" in path:
        return ""
    handle = path.lstrip("@")
    if not PUBLIC_TELEGRAM_HANDLE_RE.fullmatch(handle):
        return ""
    return f"tg://resolve?domain={handle}"


def _browser_payload_text(payload: dict[str, Any], key: str) -> str:
    stdout_json = payload.get("stdout_json")
    if not isinstance(stdout_json, dict):
        return ""
    data = stdout_json.get("data")
    if not isinstance(data, dict):
        return ""
    return str(data.get(key) or "")


def _extract_member_count(text: str) -> tuple[int | None, str]:
    match = MEMBER_COUNT_RE.search(str(text or ""))
    if not match:
        return None, ""
    count_text = " ".join(str(match.group("count") or "").split())
    digits = re.sub(r"\D", "", count_text)
    if not digits:
        return None, ""
    return int(digits), f"{count_text} members"


def _chat_snapshot_summary(
    *,
    page_url: str = "",
    member_count: int | None = None,
    member_count_text: str = "",
    add_members_visible: bool = False,
    visible_member_peers: list[dict[str, str]] | None = None,
    error: str = "",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "page_url": page_url,
        "member_count": member_count,
        "member_count_text": member_count_text,
        "add_members_visible": bool(add_members_visible),
        "visible_member_peers": list(visible_member_peers or []),
        "visible_member_count": len(visible_member_peers or []),
    }
    if error:
        payload["error"] = error
    return payload


def _portable_accessible_matches(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    stdout_json = payload.get("stdout_json") if isinstance(payload.get("stdout_json"), dict) else {}
    matches = stdout_json.get("matches")
    if not isinstance(matches, list):
        return []
    return [row for row in matches if isinstance(row, dict)]


def _portable_find_accessible_match_in_results(
    results: dict[str, dict[str, Any]] | None,
    terms: tuple[str, ...] | list[str],
) -> dict[str, Any] | None:
    if not isinstance(results, dict):
        return None
    for term in terms:
        payload = results.get(str(term))
        matches = _portable_accessible_matches(payload)
        if matches:
            return {
                "term": str(term),
                "result": payload,
                "match": matches[0],
            }
    return None


def _portable_resolve_accessible_node_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    stdout_json = payload.get("stdout_json") if isinstance(payload.get("stdout_json"), dict) else {}
    node = stdout_json.get("node")
    if isinstance(node, dict):
        return node
    click_payload = stdout_json.get("click") if isinstance(stdout_json.get("click"), dict) else {}
    click_node = click_payload.get("node")
    if isinstance(click_node, dict):
        return click_node
    match = payload.get("match")
    if isinstance(match, dict):
        return match
    return None


def _portable_match_origin_ratio(match: dict[str, Any]) -> dict[str, float] | None:
    try:
        x_ratio = float(match.get("relative_x_ratio"))
        y_ratio = float(match.get("relative_y_ratio"))
    except (TypeError, ValueError):
        return None
    return {
        "x_ratio": round(min(max(x_ratio, 0.0), 1.0), 4),
        "y_ratio": round(min(max(y_ratio, 0.0), 1.0), 4),
    }


def _portable_derive_accessible_click_ratio(
    match: dict[str, Any],
    window: dict[str, Any],
    *,
    x_anchor: float = 0.18,
    y_anchor: float = 0.45,
) -> dict[str, float] | None:
    extents = match.get("relative_extents") if isinstance(match.get("relative_extents"), dict) else {}
    try:
        rel_x = int(extents.get("x", 0) or 0)
        rel_y = int(extents.get("y", 0) or 0)
        width = int(extents.get("width", 0) or 0)
        height = int(extents.get("height", 0) or 0)
        window_width = int(window.get("width", 0) or 0)
        window_height = int(window.get("height", 0) or 0)
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0 or window_width <= 1 or window_height <= 1:
        return None
    x_inset = min(max(int(round(width * float(x_anchor))), 18), max(width - 4, 1))
    y_inset = min(max(int(round(height * float(y_anchor))), 10), max(height - 4, 1))
    click_x = rel_x + x_inset
    click_y = rel_y + y_inset
    return {
        "x_ratio": round(min(max(float(click_x) / float(window_width), 0.0), 1.0), 4),
        "y_ratio": round(min(max(float(click_y) / float(window_height), 0.0), 1.0), 4),
    }


def _portable_derive_dialog_submit_ratio(
    payload: dict[str, Any] | None,
    window: dict[str, Any],
    *,
    x_anchor: float = 0.69,
    y_anchor: float = 0.96,
) -> dict[str, float] | None:
    node = _portable_resolve_accessible_node_payload(payload)
    if not isinstance(node, dict):
        return None
    dialog_extents: dict[str, Any] | None = None
    for ancestor in reversed(node.get("ancestors") or []):
        if not isinstance(ancestor, dict):
            continue
        if str(ancestor.get("role") or "") != "dialog":
            continue
        extents = ancestor.get("resolved_extents") if isinstance(ancestor.get("resolved_extents"), dict) else {}
        if int(extents.get("width", 0) or 0) > 0 and int(extents.get("height", 0) or 0) > 0:
            dialog_extents = extents
            break
    if dialog_extents is None:
        return None
    try:
        dialog_x = int(dialog_extents.get("x", 0) or 0)
        dialog_y = int(dialog_extents.get("y", 0) or 0)
        dialog_width = int(dialog_extents.get("width", 0) or 0)
        dialog_height = int(dialog_extents.get("height", 0) or 0)
        window_x = int(window.get("x", 0) or 0)
        window_y = int(window.get("y", 0) or 0)
        window_width = int(window.get("width", 0) or 0)
        window_height = int(window.get("height", 0) or 0)
    except (TypeError, ValueError):
        return None
    if dialog_width <= 0 or dialog_height <= 0 or window_width <= 1 or window_height <= 1:
        return None
    rel_x = dialog_x - window_x
    rel_y = dialog_y - window_y
    max_x = rel_x + dialog_width - 4
    max_y = rel_y + dialog_height - 4
    if max_x <= rel_x or max_y <= rel_y:
        return None
    click_x = min(max(int(round(rel_x + dialog_width * float(x_anchor))), rel_x + 4), max_x)
    click_y = min(max(int(round(rel_y + dialog_height * float(y_anchor))), rel_y + 4), max_y)
    return {
        "x_ratio": round(min(max(float(click_x) / float(window_width), 0.0), 1.0), 4),
        "y_ratio": round(min(max(float(click_y) / float(window_height), 0.0), 1.0), 4),
    }


def _snapshot_log_line(label: str, snapshot: dict[str, Any] | None) -> str:
    if not isinstance(snapshot, dict):
        return f"INFO: {label} snapshot missing"
    error = _nonempty(snapshot.get("error"))
    if error:
        return f"WARN: {label} snapshot failed error={error}"
    member_count = snapshot.get("member_count")
    member_count_text = _nonempty(snapshot.get("member_count_text"))
    page_url = _nonempty(snapshot.get("page_url"))
    add_members_visible = int(bool(snapshot.get("add_members_visible")))
    visible_member_count = int(snapshot.get("visible_member_count", 0) or 0)
    return (
        f"INFO: {label} member_count={member_count!r} "
        f"member_count_text={member_count_text!r} "
        f"add_members_visible={add_members_visible} "
        f"visible_member_count={visible_member_count} "
        f"page_url={page_url!r}"
    )


def _member_section_html(html_payload: str) -> str:
    scope = str(html_payload or "")
    column_right = scope.find('id="column-right"')
    if column_right >= 0:
        scope = scope[column_right:]
    for marker in MEMBERS_TAB_MARKERS:
        start = scope.find(marker)
        if start < 0:
            continue
        section = scope[start:]
        end_candidates = [section.find(stop_marker) for stop_marker in MEMBERS_TAB_STOP_MARKERS]
        end_candidates = [value for value in end_candidates if value > 0]
        if end_candidates:
            return section[: min(end_candidates)]
        return section
    return ""


def _parse_visible_member_peers(html_payload: str) -> list[dict[str, str]]:
    section = _member_section_html(html_payload)
    if not section:
        return []
    peers: list[dict[str, str]] = []
    seen: set[str] = set()
    row_pattern = re.compile(
        r'<a\b(?=[^>]*\bdata-peer-id="(?P<peer_id>\d+)")[^>]*\bclass="(?P<class>[^"]*\bchatlist-chat[^"]*)"[^>]*>(?P<body>.*?)</a>',
        re.DOTALL,
    )
    title_pattern = re.compile(r'<span\b(?=[^>]*\bclass="[^"]*\bpeer-title\b[^"]*")[^>]*>(?P<title>.*?)</span>', re.DOTALL)
    for match in row_pattern.finditer(section):
        peer_id = match.group("peer_id")
        if peer_id in seen:
            continue
        title_match = title_pattern.search(match.group("body"))
        title = _strip_tags(title_match.group("title")) if title_match else ""
        if not title:
            continue
        seen.add(peer_id)
        peers.append({"peer_id": peer_id, "title": title})
    return peers


def _snapshot_member_peer_ids(snapshot: dict[str, Any] | None) -> set[str]:
    if not isinstance(snapshot, dict):
        return set()
    peers = snapshot.get("visible_member_peers")
    if not isinstance(peers, list):
        return set()
    result: set[str] = set()
    for row in peers:
        if not isinstance(row, dict):
            continue
        peer_id = _nonempty(row.get("peer_id"))
        if peer_id:
            result.add(peer_id)
    return result


def _read_chat_snapshot(run_step, browser_target: dict[str, Any], *, label_prefix: str = "") -> dict[str, Any]:
    page_url_result = run_step(f"{label_prefix}page_url", _browser_action_command(browser_target, "page-url"))
    text_result = run_step(f"{label_prefix}read_text", _browser_action_command(browser_target, "text", "body"))
    html_result = run_step(f"{label_prefix}read_html", _browser_action_command(browser_target, "html", "body"), required=False)

    page_url = _browser_payload_text(page_url_result, "url")
    body_text = _browser_payload_text(text_result, "text")
    body_html = _browser_payload_text(html_result, "html")
    member_count, member_count_text = _extract_member_count(body_text)
    visible_member_peers = _parse_visible_member_peers(body_html)
    return _chat_snapshot_summary(
        page_url=page_url,
        member_count=member_count,
        member_count_text=member_count_text,
        add_members_visible=("Add Members" in body_text) or ("can-add-members" in body_html),
        visible_member_peers=visible_member_peers,
    )


def _build_membership_verification(
    selected_candidate: dict[str, str] | None,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    after_wait: dict[str, Any] | None,
) -> dict[str, Any]:
    selected_peer_id = _nonempty(selected_candidate.get("peer_id")) if isinstance(selected_candidate, dict) else ""
    verification = {
        "signals_checked": ["member_list_visible_peer", "member_count_delta"],
        "joined_confirmed": False,
        "target_status": "requested",
        "reason": "member_count_not_checked",
        "confirmed_phase": "",
        "confirmed_signal": "",
        "confirmed_delta": 0,
        "selected_peer_id": selected_peer_id,
        "before_member_list_has_peer": False,
        "after_member_list_has_peer": False,
        "after_wait_member_list_has_peer": False,
        "before": before,
        "after": after,
        "after_wait": after_wait,
    }

    before_member_ids = _snapshot_member_peer_ids(before)
    if selected_peer_id:
        verification["before_member_list_has_peer"] = selected_peer_id in before_member_ids

    observed: list[tuple[str, dict[str, Any]]] = []
    for phase, snapshot in (("after", after), ("after_wait", after_wait)):
        if isinstance(snapshot, dict):
            observed.append((phase, snapshot))

    if not observed:
        verification["reason"] = "member_count_after_missing"
        return verification

    for phase, snapshot in observed:
        current_member_ids = _snapshot_member_peer_ids(snapshot)
        if phase == "after":
            verification["after_member_list_has_peer"] = selected_peer_id in current_member_ids if selected_peer_id else False
        elif phase == "after_wait":
            verification["after_wait_member_list_has_peer"] = selected_peer_id in current_member_ids if selected_peer_id else False
        if selected_peer_id and selected_peer_id in current_member_ids and selected_peer_id not in before_member_ids:
            verification["joined_confirmed"] = True
            verification["target_status"] = "joined"
            verification["reason"] = "member_list_peer_visible"
            verification["confirmed_phase"] = phase
            verification["confirmed_signal"] = "member_list_visible_peer"
            return verification

    baseline = before.get("member_count") if isinstance(before, dict) else None
    if baseline is None:
        verification["reason"] = "member_count_before_missing"
        return verification

    saw_unreadable = False
    for phase, snapshot in observed:
        current = snapshot.get("member_count")
        if current is None:
            saw_unreadable = True
            continue
        if int(current) > int(baseline):
            verification["joined_confirmed"] = True
            verification["target_status"] = "joined"
            verification["reason"] = "member_count_increased"
            verification["confirmed_phase"] = phase
            verification["confirmed_signal"] = "member_count_delta"
            verification["confirmed_delta"] = int(current) - int(baseline)
            return verification

    verification["reason"] = "member_count_after_unreadable" if saw_unreadable else "member_count_unchanged"
    return verification


def _extract_tab_id(stdout_json: dict[str, Any]) -> int:
    data = stdout_json.get("data") if isinstance(stdout_json, dict) else None
    if not isinstance(data, dict):
        return 0
    for key in ("tabId", "tab_id"):
        try:
            value = int(data.get(key, 0) or 0)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return value
    tab = data.get("tab")
    if isinstance(tab, dict):
        try:
            value = int(tab.get("id", 0) or 0)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return value
    try:
        value = int(data.get("id", 0) or 0)
    except (TypeError, ValueError):
        value = 0
    return value if value > 0 else 0


def _strip_tags(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", value)).strip()


def _parse_add_members_candidates(html_payload: str) -> list[dict[str, str]]:
    marker = "add-members-container active"
    start = html_payload.find(marker)
    scoped = html_payload[start:] if start >= 0 else html_payload
    candidates: list[dict[str, str]] = []
    seen: set[str] = set()
    row_pattern = re.compile(
        r'<a\b(?=[^>]*\bdata-peer-id="(?P<peer_id>\d+)")[^>]*\bclass="(?P<class>[^"]*\bchatlist-chat[^"]*)"[^>]*>(?P<body>.*?)</a>',
        re.DOTALL,
    )
    title_pattern = re.compile(r'<span\b(?=[^>]*\bclass="[^"]*\bpeer-title\b[^"]*")[^>]*>(?P<title>.*?)</span>', re.DOTALL)
    for match in row_pattern.finditer(scoped):
        peer_id = match.group("peer_id")
        if peer_id in seen:
            continue
        title_match = title_pattern.search(match.group("body"))
        title = _strip_tags(title_match.group("title")) if title_match else ""
        if not title:
            continue
        seen.add(peer_id)
        candidates.append({"peer_id": peer_id, "title": title})
    return candidates


def _find_state_user(payload: dict[str, Any], username: str) -> dict[str, Any] | None:
    normalized = normalize_username(username)
    for row in payload.get("users") or []:
        if isinstance(row, dict) and str(row.get("username") or "") == normalized:
            return row
    return None


def _record_user_status(
    job_dir: Path,
    payload: dict[str, Any],
    user: dict[str, Any],
    *,
    status: str,
    reason: str,
) -> dict[str, str]:
    target_status = ensure_valid_status(status)
    at = now_utc()
    from_status = str(user.get("status") or "")
    user["status"] = target_status
    user["last_attempt_at"] = at
    user["attempts"] = int(user.get("attempts", 0) or 0) + 1
    append_history(user, from_status, target_status, reason, at)
    save_state(job_dir, payload)
    return {"username": str(user.get("username") or ""), "from_status": from_status, "to_status": target_status}


def command_configure(args: argparse.Namespace) -> int:
    job_dir = Path(args.job_dir).expanduser()
    payload = load_state(job_dir)
    execution = _merge_execution_config(
        payload,
        invite_link=args.invite_link,
        message_template=args.message_template,
        note=args.note,
        requires_approval=args.requires_approval,
        client_id=args.client_id,
        tab_id=args.tab_id,
        url_pattern=args.url_pattern,
        active=args.active,
        portable_profile_name=getattr(args, "portable_profile_name", None),
        portable_profile_dir=getattr(args, "portable_profile_dir", None),
        account_username=getattr(args, "account_username", None),
        account_label=getattr(args, "account_label", None),
    )
    save_state(job_dir, payload)
    print(
        json.dumps(
            {
                "job_dir": str(job_dir),
                "execution": _resolved_execution_config(payload),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def command_plan(args: argparse.Namespace) -> int:
    job_dir = Path(args.job_dir).expanduser()
    payload = load_state(job_dir)
    execution = _resolved_execution_config(
        payload,
        invite_link=args.invite_link,
        message_template=args.message_template,
        note=args.note,
        requires_approval=args.requires_approval,
    )
    if args.reserve and not _nonempty(execution.get("invite_link")):
        raise ValueError("reserve requires invite_link to be configured or passed explicitly")

    selected_statuses = [ensure_valid_status(item) for item in (args.statuses or DEFAULT_EXECUTION_STATUSES)]
    planned_users = _plan_users(payload, limit=args.limit, statuses=selected_statuses, execution=execution)
    execution_id = _execution_id_now()
    at = now_utc()
    log_lines = [
        f"INFO: execution plan started execution_id={execution_id}",
        f"INFO: selected {len(planned_users)} users from statuses={','.join(selected_statuses)} reserve={int(bool(args.reserve))}",
    ]
    reserved = 0
    if args.reserve and planned_users:
        users_by_username = {
            str(row.get("username") or ""): row
            for row in payload.get("users") or []
            if isinstance(row, dict)
        }
        for row in planned_users:
            username = row["username"]
            current = users_by_username[username]
            from_status = str(current.get("status") or "")
            current["status"] = "invite_link_created"
            current["last_attempt_at"] = at
            current["attempts"] = int(current.get("attempts", 0) or 0) + 1
            append_history(current, from_status, "invite_link_created", "execution_plan_created", at)
            row["reserved_to_status"] = "invite_link_created"
            reserved += 1
            log_lines.append(f"INFO: reserved {username} {from_status} -> invite_link_created")
        save_state(job_dir, payload)

    run_payload = {
        "status": "completed",
        "job_dir": str(job_dir),
        "execution_id": execution_id,
        "selected_users": len(planned_users),
        "reserved": reserved,
        "from_statuses": selected_statuses,
        "execution": execution,
        "users": planned_users,
        "operator_checklist": [
            "Проверьте, что invite link актуален и ведёт в нужный чат.",
            "Если execution привязан к portable_actor, сначала выполните ensure-portable и проверьте account/window.",
            "Не отправляйте ссылку пользователям без consent=yes в invite_state.json.",
            "Перед live add снимите inspect-chat или используйте add-contact с автопроверкой before/after.",
            "Не ставьте joined без подтверждения роста счётчика или другого отдельного сигнала вступления.",
            "После фактической отправки обновите статус через telegram_invite_executor.py record.",
        ],
    }
    run_dir = _write_execution_artifacts(job_dir, execution_id, run_payload, log_lines)
    run_payload["run_dir"] = str(run_dir)
    print(json.dumps(run_payload, ensure_ascii=False, indent=2))
    return 0


def command_open_chat(args: argparse.Namespace) -> int:
    job_dir = Path(args.job_dir).expanduser()
    payload = load_state(job_dir)
    repo_root = Path(__file__).resolve().parents[1]
    execution = _resolved_execution_config(
        payload,
        client_id=args.client_id,
        tab_id=args.tab_id,
        url_pattern=args.url_pattern,
        active=args.active,
    )
    command = _browser_command(
        repo_root,
        chat_url=str(payload.get("chat_url") or ""),
        browser_target=execution.get("browser_target") or {},
    )
    response: dict[str, Any] = {
        "job_dir": str(job_dir),
        "chat_url": str(payload.get("chat_url") or ""),
        "command": command,
        "dry_run": bool(args.dry_run),
    }
    if args.dry_run:
        print(json.dumps(response, ensure_ascii=False, indent=2))
        return 0

    proc = _run_browser_command(repo_root, command)
    response["returncode"] = int(proc.returncode)
    response["stdout"] = proc.stdout
    response["stderr"] = proc.stderr
    try:
        response["stdout_json"] = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        response["stdout_json"] = {}
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0 if proc.returncode == 0 else int(proc.returncode)


def command_ensure_portable(args: argparse.Namespace) -> int:
    job_dir = Path(args.job_dir).expanduser()
    payload = load_state(job_dir)
    repo_root = Path(__file__).resolve().parents[1]
    execution = _resolved_execution_config(
        payload,
        portable_profile_name=args.portable_profile_name,
        portable_profile_dir=args.portable_profile_dir,
        account_username=args.account_username,
        account_label=args.account_label,
    )
    actor = execution.get("portable_actor") or {}
    status_command = _portable_command(repo_root, actor, "status")
    status_result = _run_portable_json(repo_root, status_command)
    status_payload = status_result.get("stdout_json") if isinstance(status_result.get("stdout_json"), dict) else {}

    launch_result: dict[str, Any] | None = None
    if int(status_result.get("returncode", 1) or 0) == 0 and not bool(status_payload.get("running")) and args.launch_if_needed:
        launch_command = _portable_command(repo_root, actor, "launch")
        launch_result = _run_portable_json(repo_root, launch_command)
        status_result = _run_portable_json(repo_root, status_command)
        status_payload = status_result.get("stdout_json") if isinstance(status_result.get("stdout_json"), dict) else {}

    response = {
        "status": "completed" if int(status_result.get("returncode", 1) or 0) == 0 else "failed",
        "job_dir": str(job_dir),
        "chat_url": str(payload.get("chat_url") or ""),
        "portable_actor": actor,
        "account_username": _nonempty(actor.get("account_username")),
        "status_result": status_result,
        "launch_result": launch_result,
        "running": bool(status_payload.get("running")),
        "pids": status_payload.get("pids") if isinstance(status_payload.get("pids"), list) else [],
        "windows": status_payload.get("windows") if isinstance(status_payload.get("windows"), list) else [],
    }
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0 if response["status"] == "completed" else 1


def _ensure_portable_actor_ready(
    *,
    repo_root: Path,
    actor: dict[str, Any],
    launch_if_needed: bool,
) -> dict[str, Any]:
    status_command = _portable_command(repo_root, actor, "status")
    status_result = _run_portable_json(repo_root, status_command)
    status_payload = status_result.get("stdout_json") if isinstance(status_result.get("stdout_json"), dict) else {}

    launch_result: dict[str, Any] | None = None
    if int(status_result.get("returncode", 1) or 0) == 0 and not bool(status_payload.get("running")) and launch_if_needed:
        launch_command = _portable_command(repo_root, actor, "launch")
        launch_result = _run_portable_json(repo_root, launch_command)
        status_result = _run_portable_json(repo_root, status_command)
        status_payload = status_result.get("stdout_json") if isinstance(status_result.get("stdout_json"), dict) else {}

    return {
        "status_result": status_result,
        "launch_result": launch_result,
        "running": bool(status_payload.get("running")),
        "pids": status_payload.get("pids") if isinstance(status_payload.get("pids"), list) else [],
        "windows": status_payload.get("windows") if isinstance(status_payload.get("windows"), list) else [],
    }


def _ensure_user_for_prepare_next(
    payload: dict[str, Any],
    *,
    username: str,
    consent: str,
    display_name: str,
    note: str,
    source: str,
    dry_run: bool,
) -> dict[str, Any] | None:
    normalized = normalize_username(username)
    if not normalized:
        return None
    users = payload.get("users")
    if not isinstance(users, list):
        raise ValueError("state missing users list")
    existing = next((row for row in users if isinstance(row, dict) and str(row.get("username") or "") == normalized), None)
    if existing is not None:
        if not bool(existing.get("consent")):
            if not parse_consent(consent):
                raise ValueError(f"user has no consent=yes in invite_state.json: {normalized}")
            if not dry_run:
                at = now_utc()
                from_status = str(existing.get("status") or "")
                existing["consent"] = True
                existing["status"] = "new" if from_status == "skipped" else from_status
                append_history(existing, from_status, str(existing.get("status") or ""), "prepare_next_consent_update", at)
        return existing

    if not parse_consent(consent):
        raise ValueError("prepare-next can add a new user only with explicit --consent yes")
    at = now_utc()
    record, error = build_user_record(
        {
            "username": normalized,
            "display_name": display_name or normalized,
            "note": note,
            "consent": consent_label(True),
            "source": source or "prepare-next",
        },
        at,
    )
    if error or record is None:
        raise ValueError(error or f"unable to build user record for {normalized}")
    append_history(record, "", "new", "prepare_next_add_user", at)
    if not dry_run:
        users.append(record)
        import_stats = payload.get("import_stats")
        if isinstance(import_stats, dict):
            import_stats["rows_total"] = int(import_stats.get("rows_total", 0) or 0) + 1
            import_stats["imported"] = int(import_stats.get("imported", 0) or 0) + 1
            import_stats["consent_yes"] = int(import_stats.get("consent_yes", 0) or 0) + 1
    return record


def _select_prepare_next_user(
    payload: dict[str, Any],
    *,
    username: str | None,
    statuses: list[str],
) -> dict[str, Any] | None:
    if username:
        normalized = normalize_username(username)
        if not normalized:
            raise ValueError(f"invalid username: {username}")
        user = _find_state_user(payload, normalized)
        if user is None:
            return None
        if not bool(user.get("consent")):
            raise ValueError(f"user has no consent=yes in invite_state.json: {normalized}")
        if str(user.get("status") or "") not in set(statuses):
            raise ValueError(f"user {normalized} is not in selectable status: {str(user.get('status') or '')}")
        return user

    for status in statuses:
        candidates = select_candidates(payload, 1, [status])
        if candidates:
            return candidates[0]
    return None


def _write_prepare_next_manager_artifact(
    *,
    job_dir: Path,
    execution_id: str,
    username: str,
    from_status: str,
    to_status: str,
    dry_run: bool,
) -> str:
    run_payload = {
        "status": "completed",
        "job_dir": str(job_dir),
        "run_id": execution_id,
        "limit": 1,
        "dry_run": bool(dry_run),
        "selected_users": 1,
        "processed": 1,
        "updated": 0 if dry_run else 1,
        "from_statuses": [from_status],
        "target_status": to_status,
        "results": [
            {
                "username": username,
                "from_status": from_status,
                "to_status": to_status,
                "reason": "prepare_next_checked",
            }
        ],
    }
    run_dir = write_run_artifacts(job_dir, run_payload, [f"INFO: {username} {from_status} -> {to_status} (prepare_next_checked)"])
    return str(run_dir)


def command_prepare_next(args: argparse.Namespace) -> int:
    job_dir = Path(args.job_dir).expanduser()
    payload = load_state(job_dir)
    repo_root = Path(__file__).resolve().parents[1]
    execution = _resolved_execution_config(payload)
    actor = execution.get("portable_actor") or {}
    if not _portable_actor_args(actor):
        raise ValueError("prepare-next requires portable_actor in execution config; run configure with --portable-profile-name/dir")

    portable = _ensure_portable_actor_ready(
        repo_root=repo_root,
        actor=actor,
        launch_if_needed=bool(args.launch_if_needed),
    )
    if int(portable["status_result"].get("returncode", 1) or 0) != 0:
        raise RuntimeError(portable["status_result"].get("stderr") or portable["status_result"].get("stdout") or "portable status failed")
    if not portable["running"]:
        raise RuntimeError("portable actor is not running; rerun with --launch-if-needed or start Telegram Desktop portable")

    requested_username = normalize_username(args.username) if args.username else None
    if args.username:
        _ensure_user_for_prepare_next(
            payload,
            username=args.username,
            consent=args.consent,
            display_name=args.display_name,
            note=args.note,
            source=args.source,
            dry_run=bool(args.dry_run),
        )

    statuses = [ensure_valid_status(item) for item in (args.statuses or ["checked", "new"])]
    selected_user = _select_prepare_next_user(payload, username=requested_username, statuses=statuses)
    if selected_user is None:
        response = {
            "status": "no_candidates",
            "job_dir": str(job_dir),
            "chat_url": str(payload.get("chat_url") or ""),
            "portable_actor": actor,
            "portable": portable,
            "from_statuses": statuses,
            "next_action": "add a consented username, then rerun prepare-next",
        }
        print(json.dumps(response, ensure_ascii=False, indent=2))
        return 0

    execution_id = args.execution_id or _execution_id_now()
    at = now_utc()
    username = str(selected_user.get("username") or "")
    original_status = str(selected_user.get("status") or "")
    manager_run_dir = ""
    if original_status == "new":
        if not args.dry_run:
            selected_user["status"] = "checked"
            selected_user["last_attempt_at"] = at
            selected_user["attempts"] = int(selected_user.get("attempts", 0) or 0) + 1
            append_history(selected_user, "new", "checked", "prepare_next_checked", at)
            save_state(job_dir, payload)
        manager_run_dir = _write_prepare_next_manager_artifact(
            job_dir=job_dir,
            execution_id=execution_id,
            username=username,
            from_status="new",
            to_status="checked",
            dry_run=bool(args.dry_run),
        )

    current_status = "checked" if original_status == "new" else original_status
    selected_user_for_plan = dict(selected_user)
    selected_user_for_plan["status"] = current_status
    plan_row = _plan_row_for_user(selected_user_for_plan, execution=execution, chat_url=_nonempty(payload.get("chat_url")))

    reserved = 0
    record_user = _find_state_user(payload, username)
    if args.reserve:
        if not _nonempty(execution.get("invite_link")):
            raise ValueError("prepare-next --reserve requires invite_link to be configured")
        if not args.dry_run and record_user is not None:
            from_status = str(record_user.get("status") or "")
            record_user["status"] = "invite_link_created"
            record_user["last_attempt_at"] = at
            record_user["attempts"] = int(record_user.get("attempts", 0) or 0) + 1
            append_history(record_user, from_status, "invite_link_created", "prepare_next_execution_plan_created", at)
            save_state(job_dir, payload)
            plan_row["reserved_to_status"] = "invite_link_created"
            reserved = 1
        elif args.dry_run:
            plan_row["reserved_to_status"] = "invite_link_created"

    run_payload = {
        "status": "completed",
        "job_dir": str(job_dir),
        "execution_id": execution_id,
        "selected_users": 1,
        "reserved": reserved,
        "from_statuses": statuses,
        "execution": execution,
        "portable_actor": actor,
        "users": [plan_row],
        "operator_checklist": [
            "Portable actor уже проверен этой командой.",
            "Работать только с указанным username и consent=yes.",
            "После отправки invite link или Desktop-действия записать результат через record.",
            "Не ставить joined без отдельного подтверждения вступления.",
        ],
    }
    log_lines = [
        f"INFO: prepare-next started execution_id={execution_id}",
        f"INFO: portable actor running={int(bool(portable['running']))}",
        f"INFO: selected {username} from_status={original_status} reserve={int(bool(args.reserve))} dry_run={int(bool(args.dry_run))}",
    ]
    execution_run_dir = ""
    if not args.dry_run:
        execution_run_dir = str(_write_execution_artifacts(job_dir, execution_id, run_payload, log_lines))

    response = {
        "status": "completed",
        "job_dir": str(job_dir),
        "chat_url": str(payload.get("chat_url") or ""),
        "execution_id": execution_id,
        "dry_run": bool(args.dry_run),
        "portable_actor": actor,
        "portable": portable,
        "selected_user": plan_row,
        "manager_run_dir": manager_run_dir,
        "execution_run_dir": execution_run_dir,
        "reserved": reserved,
        "target_status": "invite_link_created" if args.reserve else current_status,
        "next_action": "send invite using Telegram Desktop portable actor, then record sent/requested/joined",
    }
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0


def command_desktop_send_link(args: argparse.Namespace) -> int:
    job_dir = Path(args.job_dir).expanduser()
    payload = load_state(job_dir)
    repo_root = Path(__file__).resolve().parents[1]
    username = normalize_username(args.username)
    if not username:
        raise ValueError("desktop-send-link requires a valid Telegram username")
    user = _find_state_user(payload, username)
    if user is None:
        raise ValueError(f"user is not present in invite_state.json: {username}")
    if not bool(user.get("consent")):
        raise ValueError(f"user has no consent=yes in invite_state.json: {username}")
    allowed_statuses = {ensure_valid_status(item) for item in (args.statuses or ["invite_link_created", "checked"])}
    user_status = str(user.get("status") or "")
    if user_status not in allowed_statuses:
        raise ValueError(f"user {username} has status {user_status!r}, expected one of {sorted(allowed_statuses)}")

    execution = _resolved_execution_config(payload)
    actor = execution.get("portable_actor") or {}
    if not _portable_actor_args(actor):
        raise ValueError("desktop-send-link requires portable_actor in execution config")
    invite_link = _nonempty(args.invite_link) or _nonempty(execution.get("invite_link"))
    if not invite_link:
        raise ValueError("desktop-send-link requires invite_link in execution config or --invite-link")
    message_text = _nonempty(args.message) or invite_link
    try:
        message_text.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("desktop-send-link currently supports only ASCII text; use an ASCII invite link or message") from exc

    portable = _ensure_portable_actor_ready(repo_root=repo_root, actor=actor, launch_if_needed=bool(args.launch_if_needed))
    if int(portable["status_result"].get("returncode", 1) or 0) != 0:
        raise RuntimeError(portable["status_result"].get("stderr") or portable["status_result"].get("stdout") or "portable status failed")
    if not portable["running"]:
        raise RuntimeError("portable actor is not running; rerun with --launch-if-needed or start Telegram Desktop portable")

    execution_id = args.execution_id or _execution_id_now()
    domain = username.lstrip("@")
    uri = f"tg://resolve?domain={domain}"
    steps: list[dict[str, Any]] = []
    open_command = _portable_action_command(repo_root, actor, "open-uri", "--uri", uri)
    if args.dry_run:
        open_command.append("--dry-run")
    open_result = _run_portable_json(repo_root, open_command)
    steps.append({"label": "open_user_chat", **open_result})
    if int(open_result.get("returncode", 1) or 0) != 0:
        raise RuntimeError(open_result.get("stderr") or open_result.get("stdout") or "open user chat failed")
    if not args.dry_run:
        time.sleep(max(float(args.open_wait), 0.0))

    type_command = _portable_action_command(repo_root, actor, "type-text", "--text", message_text)
    if args.window_id:
        type_command.extend(["--window-id", args.window_id])
    if args.confirm_send:
        type_command.append("--press-enter")
    if args.dry_run or not args.confirm_send:
        type_command.append("--dry-run")
    type_result = _run_portable_json(repo_root, type_command)
    steps.append({"label": "type_invite_link", **type_result})
    if int(type_result.get("returncode", 1) or 0) != 0:
        raise RuntimeError(type_result.get("stderr") or type_result.get("stdout") or "type invite link failed")

    record_update: dict[str, str] | None = None
    if args.record_result and args.confirm_send and not args.dry_run:
        record_update = _record_user_status(
            job_dir,
            payload,
            user,
            status="sent",
            reason="desktop_portable_invite_link_sent",
        )

    status = "sent" if args.confirm_send and not args.dry_run else "prepared"
    response = {
        "status": "completed",
        "outcome": status,
        "job_dir": str(job_dir),
        "chat_url": str(payload.get("chat_url") or ""),
        "execution_id": execution_id,
        "username": username,
        "portable_actor": actor,
        "portable": portable,
        "uri": uri,
        "message_text": message_text,
        "confirm_send": bool(args.confirm_send),
        "record_update": record_update,
        "target_status": record_update["to_status"] if isinstance(record_update, dict) else "",
        "steps": steps,
    }
    log_lines = [
        f"INFO: desktop-send-link started execution_id={execution_id}",
        f"INFO: username={username} confirm_send={int(bool(args.confirm_send))} record_result={int(bool(args.record_result))}",
    ]
    run_dir = _write_execution_record(job_dir, execution_id, response, log_lines)
    response["run_dir"] = str(run_dir)
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0


def command_desktop_open_add_members(args: argparse.Namespace) -> int:
    job_dir = Path(args.job_dir).expanduser()
    payload = load_state(job_dir)
    repo_root = Path(__file__).resolve().parents[1]
    username = normalize_username(args.username)
    if not username:
        raise ValueError("desktop-open-add-members requires a valid Telegram username")
    user = _find_state_user(payload, username)
    if user is None:
        raise ValueError(f"user is not present in invite_state.json: {username}")
    if not bool(user.get("consent")):
        raise ValueError(f"user has no consent=yes in invite_state.json: {username}")

    execution = _resolved_execution_config(payload)
    actor = execution.get("portable_actor") or {}
    if not _portable_actor_args(actor):
        raise ValueError("desktop-open-add-members requires portable_actor in execution config")

    portable = _ensure_portable_actor_ready(repo_root=repo_root, actor=actor, launch_if_needed=bool(args.launch_if_needed))
    if int(portable["status_result"].get("returncode", 1) or 0) != 0:
        raise RuntimeError(portable["status_result"].get("stderr") or portable["status_result"].get("stdout") or "portable status failed")
    if not portable["running"]:
        raise RuntimeError("portable actor is not running; rerun with --launch-if-needed or start Telegram Desktop portable")

    execution_id = args.execution_id or _execution_id_now()
    search_query = _nonempty(args.search_query) or username.lstrip("@")
    group_uri = _nonempty(args.group_uri) or _telegram_public_chat_uri(str(payload.get("chat_url") or ""))
    if not group_uri:
        raise ValueError("desktop-open-add-members requires --group-uri or a public t.me chat_url in invite_state.json")

    steps: list[dict[str, Any]] = []
    outcome = "started"
    chosen_search_field: dict[str, Any] | None = None

    def run_portable_step(label: str, command: list[str], *, required: bool = True) -> dict[str, Any]:
        result = {"label": label, **_run_portable_json(repo_root, command)}
        steps.append(result)
        if required and int(result.get("returncode", 1) or 0) != 0:
            raise RuntimeError(f"{label} failed: {result.get('stderr') or result.get('stdout')}")
        return result

    log_lines = [
        f"INFO: desktop-open-add-members started execution_id={execution_id}",
        f"INFO: username={username} search_query={search_query!r}",
        f"INFO: group_uri={group_uri!r}",
    ]

    try:
        preflight_command = _portable_action_command(repo_root, actor, "log-diagnose")
        preflight_result = run_portable_step("preflight_log", preflight_command, required=False)
        preflight_json = preflight_result.get("stdout_json") if isinstance(preflight_result.get("stdout_json"), dict) else {}
        alerts = preflight_json.get("alerts") if isinstance(preflight_json.get("alerts"), list) else []
        blocking_alerts = [
            item
            for item in alerts
            if isinstance(item, dict) and str(item.get("code") or "") in {"PEER_FLOOD", "FLOOD_WAIT"}
        ]
        if blocking_alerts:
            log_lines.append(f"WARN: blocking alerts before UI flow: {json.dumps(blocking_alerts, ensure_ascii=False)}")
            if not args.allow_alerts and not args.dry_run:
                raise RuntimeError("Telegram portable log shows PEER_FLOOD/FLOOD_WAIT; stop direct add flow or rerun with --allow-alerts")

        open_command = _portable_action_command(repo_root, actor, "open-uri", "--uri", group_uri)
        if args.dry_run:
            open_command.append("--dry-run")
        run_portable_step("open_group", open_command)
        if not args.dry_run:
            time.sleep(max(float(args.open_wait), 0.0))

        info_command = _portable_action_command(
            repo_root,
            actor,
            "accessibility-click",
            "--query",
            "Info",
            "--role",
            "push button",
            "--match-mode",
            "exact",
            "--visible-only",
            "--pick",
            "rightmost",
        )
        if args.dry_run:
            info_command.append("--dry-run")
        run_portable_step("open_info_panel", info_command)
        if not args.dry_run:
            time.sleep(max(float(args.panel_wait), 0.0))

        add_members_command = _portable_action_command(
            repo_root,
            actor,
            "accessibility-click",
            "--query",
            "Add members",
            "--role",
            "push button",
            "--match-mode",
            "exact",
            "--pick",
            "best",
        )
        if args.dry_run:
            add_members_command.append("--dry-run")
        run_portable_step("open_add_members_panel", add_members_command)
        if not args.dry_run:
            time.sleep(max(float(args.search_wait), 0.0))

        search_dump_command = _portable_action_command(
            repo_root,
            actor,
            "accessibility-dump",
            "--query",
            "Search",
            "--role",
            "text",
            "--visible-only",
            "--pick",
            "rightmost",
            "--max-results",
            "10",
        )
        search_dump = run_portable_step("dump_search_fields", search_dump_command)
        search_payload = search_dump.get("stdout_json") if isinstance(search_dump.get("stdout_json"), dict) else {}
        search_matches = search_payload.get("matches") if isinstance(search_payload.get("matches"), list) else []
        for row in search_matches:
            if not isinstance(row, dict):
                continue
            relative_x_ratio = float(row.get("relative_x_ratio", 0.0) or 0.0)
            resolved_extents = row.get("resolved_extents") if isinstance(row.get("resolved_extents"), dict) else {}
            resolved_x = int(resolved_extents.get("x", 0) or 0)
            if relative_x_ratio >= float(args.min_search_ratio) or (
                int(args.min_search_x) > 0 and resolved_x >= int(args.min_search_x)
            ):
                chosen_search_field = row
                break

        if args.type_search:
            if chosen_search_field is None:
                outcome = "search_field_not_found"
                raise RuntimeError(
                    "Add Members search field was not found in the right-side pane; aborting before typing"
                )
            type_command = _portable_action_command(
                repo_root,
                actor,
                "accessibility-type-text",
                "--query",
                "Search",
                "--role",
                "text",
                "--match-mode",
                "contains",
                "--visible-only",
                "--pick",
                "rightmost",
                "--text",
                search_query,
            )
            if args.clear_search:
                type_command.append("--clear-first")
            if args.press_enter_after_search:
                type_command.append("--press-enter")
            if args.dry_run:
                type_command.append("--dry-run")
            run_portable_step("type_member_search", type_command)
            outcome = "search_typed"
        else:
            outcome = "add_members_opened"
    except Exception as exc:  # noqa: BLE001
        if outcome == "started":
            outcome = "failed"
        log_lines.append(f"ERROR: {exc}")
        response = {
            "status": "failed",
            "outcome": outcome,
            "job_dir": str(job_dir),
            "execution_id": execution_id,
            "username": username,
            "group_uri": group_uri,
            "search_query": search_query,
            "portable_actor": actor,
            "portable": portable,
            "chosen_search_field": chosen_search_field,
            "error": str(exc),
            "steps": steps,
        }
        run_dir = _write_execution_record(job_dir, execution_id, response, log_lines)
        response["run_dir"] = str(run_dir)
        print(json.dumps(response, ensure_ascii=False, indent=2))
        return 0 if args.dry_run else 1

    response = {
        "status": "completed",
        "outcome": outcome,
        "job_dir": str(job_dir),
        "execution_id": execution_id,
        "username": username,
        "group_uri": group_uri,
        "search_query": search_query,
        "portable_actor": actor,
        "portable": portable,
        "chosen_search_field": chosen_search_field,
        "steps": steps,
    }
    run_dir = _write_execution_record(job_dir, execution_id, response, log_lines)
    response["run_dir"] = str(run_dir)
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0


def command_desktop_add_contact_profile(args: argparse.Namespace) -> int:
    job_dir = Path(args.job_dir).expanduser()
    payload = load_state(job_dir)
    repo_root = Path(__file__).resolve().parents[1]
    username = normalize_username(args.username)
    if not username:
        raise ValueError("desktop-add-contact-profile requires a valid Telegram username")
    user = _find_state_user(payload, username)
    if user is None:
        raise ValueError(f"user is not present in invite_state.json: {username}")
    if not bool(user.get("consent")):
        raise ValueError(f"user has no consent=yes in invite_state.json: {username}")

    execution = _resolved_execution_config(payload)
    actor = execution.get("portable_actor") or {}
    if not _portable_actor_args(actor):
        raise ValueError("desktop-add-contact-profile requires portable_actor in execution config")

    portable = _ensure_portable_actor_ready(repo_root=repo_root, actor=actor, launch_if_needed=bool(args.launch_if_needed))
    if int(portable["status_result"].get("returncode", 1) or 0) != 0:
        raise RuntimeError(portable["status_result"].get("stderr") or portable["status_result"].get("stdout") or "portable status failed")
    if not portable["running"]:
        raise RuntimeError("portable actor is not running; rerun with --launch-if-needed or start Telegram Desktop portable")

    execution_id = args.execution_id or _execution_id_now()
    execution_run_dir = _execution_runs_dir(job_dir) / execution_id
    execution_run_dir.mkdir(parents=True, exist_ok=True)
    uri = f"tg://resolve?domain={username.lstrip('@')}&profile"
    steps: list[dict[str, Any]] = []
    screenshots: dict[str, str] = {}
    outcome = "started"
    verification: dict[str, Any] | None = None
    preexisting_contact_detected = False

    def run_portable_step(label: str, command: list[str], *, required: bool = True) -> dict[str, Any]:
        result = {"label": label, **_run_portable_json(repo_root, command)}
        steps.append(result)
        if required and int(result.get("returncode", 1) or 0) != 0:
            raise RuntimeError(f"{label} failed: {result.get('stderr') or result.get('stdout')}")
        return result

    def capture_screenshot(label: str, filename: str) -> None:
        if args.dry_run:
            steps.append({"label": label, "dry_run": True, "skipped": True})
            screenshots[label] = ""
            return
        screenshot_path = execution_run_dir / filename
        result = run_portable_step(
            label,
            _portable_action_command(repo_root, actor, "window-screenshot", "--output", str(screenshot_path)),
            required=False,
        )
        payload_json = result.get("stdout_json") if isinstance(result.get("stdout_json"), dict) else {}
        screenshots[label] = str(payload_json.get("output_path") or screenshot_path)

    def dump_accessible_query(label: str, query: str) -> dict[str, Any]:
        dump_command = _portable_action_command(
            repo_root,
            actor,
            "accessibility-dump",
            "--query",
            query,
            "--visible-only",
            "--max-results",
            "20",
        )
        return run_portable_step(label, dump_command, required=False)

    def query_accessible(
        label: str,
        *,
        query: str,
        role: str = "",
        visible_only: bool = True,
        state_filters: tuple[str, ...] = ("showing",),
        max_results: int = 20,
    ) -> dict[str, Any]:
        command = _portable_action_command(repo_root, actor, "accessibility-dump", "--query", query)
        if role:
            command.extend(["--role", role])
        if visible_only:
            command.append("--visible-only")
        for state_name in state_filters:
            command.extend(["--state", str(state_name)])
        command.extend(["--max-results", str(max(int(max_results), 1))])
        return run_portable_step(label, command, required=False)

    def find_accessible_match(
        *,
        terms: tuple[str, ...] | list[str],
        role: str = "",
        visible_only: bool = True,
        state_filters: tuple[str, ...] = ("showing",),
        label_prefix: str = "find_accessible",
    ) -> dict[str, Any] | None:
        results: dict[str, dict[str, Any]] = {}
        for index, term in enumerate(terms, start=1):
            result = query_accessible(
                f"{label_prefix}_{index}",
                query=str(term),
                role=role,
                visible_only=visible_only,
                state_filters=state_filters,
            )
            results[str(term)] = result
        return _portable_find_accessible_match_in_results(results, terms)

    def click_window_ratio(label: str, *, x_ratio: float, y_ratio: float, required: bool = False) -> dict[str, Any]:
        command = _portable_action_command(
            repo_root,
            actor,
            "window-click",
            "--coordinate-space",
            "window_geometry",
            "--x-ratio",
            str(float(x_ratio)),
            "--y-ratio",
            str(float(y_ratio)),
        )
        if args.dry_run:
            command.append("--dry-run")
        return run_portable_step(label, command, required=required)

    def try_accessible_type(label_prefix: str, terms: tuple[str, ...] | list[str], text: str) -> dict[str, Any] | None:
        for index, term in enumerate(terms, start=1):
            for node_index in (0, 1):
                command = _portable_action_command(
                    repo_root,
                    actor,
                    "accessibility-type-text",
                    "--query",
                    str(term),
                    "--role",
                    "text",
                    "--visible-only",
                    "--state",
                    "showing",
                    "--index",
                    str(node_index),
                    "--text",
                    text,
                    "--clear-first",
                )
                if args.dry_run:
                    command.append("--dry-run")
                result = run_portable_step(f"{label_prefix}_{index}_{node_index}", command, required=False)
                if int(result.get("returncode", 1) or 0) == 0:
                    return result
        return None

    def find_add_contact_button() -> dict[str, Any] | None:
        return find_accessible_match(
            terms=(*DESKTOP_ADD_TO_CONTACTS_CHAT_TERMS, *DESKTOP_ADD_CONTACT_BUTTON_TERMS),
            role="push button",
            visible_only=True,
            label_prefix="find_add_contact_button",
        )

    def find_exact_username_label(target_username: str) -> dict[str, Any] | None:
        normalized_target = target_username if str(target_username or "").startswith("@") else f"@{target_username}"
        for role in ("label", "text"):
            match = find_accessible_match(
                terms=(normalized_target,),
                role=role,
                visible_only=True,
                label_prefix=f"find_exact_username_{role}",
            )
            if not match:
                continue
            match_name = _normalize_space(match["match"].get("name"))
            if match_name.casefold() == normalized_target.casefold():
                return match
        return None

    def probe_contact_verification(label_prefix: str) -> dict[str, Any]:
        verify_results = {
            term: dump_accessible_query(
                f"{label_prefix}:{term}",
                term,
            )
            for term in (*CONTACT_VERIFY_ADD_TERMS, *CONTACT_VERIFY_SUCCESS_TERMS)
        }
        return _portable_contact_verify_summary(verify_results)

    log_lines = [
        f"INFO: desktop-add-contact-profile started execution_id={execution_id}",
        f"INFO: username={username} uri={uri!r}",
        f"INFO: confirm_add={int(bool(args.confirm_add))} dry_run={int(bool(args.dry_run))}",
        f"INFO: add_click_ratio=({float(args.add_click_x_ratio):.4f},{float(args.add_click_y_ratio):.4f})",
        f"INFO: done_click_ratio=({float(args.done_click_x_ratio):.4f},{float(args.done_click_y_ratio):.4f}) repeat={int(args.done_click_repeat)}",
    ]

    try:
        preflight_command = _portable_action_command(repo_root, actor, "log-diagnose")
        run_portable_step("preflight_log", preflight_command, required=False)

        open_command = _portable_action_command(repo_root, actor, "open-uri", "--uri", uri)
        if args.dry_run:
            open_command.append("--dry-run")
        run_portable_step("open_user_profile", open_command)
        if not args.dry_run:
            time.sleep(max(float(args.open_wait), 0.0))

        capture_screenshot("profile_before", "desktop_add_contact_profile_before.png")

        if args.confirm_add:
            if args.dry_run:
                click_window_ratio(
                    "click_add_to_contacts",
                    x_ratio=float(args.add_click_x_ratio),
                    y_ratio=float(args.add_click_y_ratio),
                    required=False,
                )
                last_name_text = _nonempty(args.last_name_text)
                if last_name_text:
                    type_command = _portable_action_command(repo_root, actor, "type-text", "--text", last_name_text)
                    if bool(args.press_enter_after_last_name):
                        type_command.append("--press-enter")
                    type_command.append("--dry-run")
                    run_portable_step("type_last_name", type_command, required=False)
                done_repeat = max(int(args.done_click_repeat), 1)
                for index in range(done_repeat):
                    click_window_ratio(
                        f"click_done_{index + 1}",
                        x_ratio=float(args.done_click_x_ratio),
                        y_ratio=float(args.done_click_y_ratio),
                        required=False,
                    )
            else:
                window_geometry = portable["windows"][0] if portable.get("windows") else {}
                add_button_match = find_add_contact_button()
                username_match = find_exact_username_label(username)
                if add_button_match:
                    steps.append(
                        {
                            "label": "probe_add_contact_button",
                            "term": add_button_match["term"],
                            "match": add_button_match["match"],
                        }
                    )
                if username_match:
                    steps.append(
                        {
                            "label": "profile_username_exact_match",
                            "term": username_match["term"],
                            "match": username_match["match"],
                        }
                    )
                if add_button_match is None:
                    precheck_verification = probe_contact_verification("precheck_term")
                    precheck_verification["stage"] = "precheck"
                    steps.append(
                        {
                            "label": "precheck_contact_verification",
                            "verification": precheck_verification,
                        }
                    )
                    if bool(precheck_verification.get("success_visible")) and not bool(precheck_verification.get("add_visible")):
                        preexisting_contact_detected = True
                        verification = precheck_verification
                        log_lines.append(
                            "INFO: precheck detected existing contact "
                            f"visible_terms={json.dumps(precheck_verification.get('visible_terms') or [], ensure_ascii=False)}"
                        )
                    else:
                        outcome = "ui_add_button_not_found"
                        raise RuntimeError("Add to contacts button is not visible in the opened profile")
                if username_match is None:
                    outcome = "ui_profile_username_mismatch"
                    raise RuntimeError(f"Exact username label is not visible for {username}")

                if not preexisting_contact_detected:
                    add_click_ratio = (
                        _portable_match_origin_ratio(add_button_match["match"])
                        or _portable_derive_accessible_click_ratio(add_button_match["match"], window_geometry)
                        or {"x_ratio": float(args.add_click_x_ratio), "y_ratio": float(args.add_click_y_ratio)}
                    )
                    steps.append(
                        {
                            "label": "resolved_add_contact_click",
                            "x_ratio": add_click_ratio["x_ratio"],
                            "y_ratio": add_click_ratio["y_ratio"],
                        }
                    )
                    click_window_ratio(
                        "click_add_to_contacts",
                        x_ratio=float(add_click_ratio["x_ratio"]),
                        y_ratio=float(add_click_ratio["y_ratio"]),
                        required=False,
                    )
                    time.sleep(max(float(args.after_add_wait), 0.0))

                    post_add_first_name = find_accessible_match(
                        terms=DESKTOP_FIRST_NAME_TERMS,
                        role="text",
                        visible_only=True,
                        label_prefix="find_first_name",
                    )
                    post_add_done_button = find_accessible_match(
                        terms=DESKTOP_DONE_BUTTON_TERMS,
                        role="push button",
                        visible_only=True,
                        label_prefix="find_done_button",
                    )
                    post_add_button = find_add_contact_button()
                    dialog_detected = bool(post_add_first_name or post_add_done_button)
                    steps.append(
                        {
                            "label": "post_add_dialog_state",
                            "dialog_detected": dialog_detected,
                            "add_button_still_visible": bool(post_add_button),
                            "first_name_visible": bool(post_add_first_name),
                            "done_button_visible": bool(post_add_done_button),
                        }
                    )
                    if not dialog_detected and post_add_button is not None:
                        retry_click_ratio = (
                            _portable_match_origin_ratio(post_add_button["match"])
                            or _portable_derive_accessible_click_ratio(post_add_button["match"], window_geometry)
                        )
                        if retry_click_ratio:
                            steps.append(
                                {
                                    "label": "retry_add_contact_click",
                                    "x_ratio": retry_click_ratio["x_ratio"],
                                    "y_ratio": retry_click_ratio["y_ratio"],
                                }
                            )
                            click_window_ratio(
                                "retry_add_to_contacts",
                                x_ratio=float(retry_click_ratio["x_ratio"]),
                                y_ratio=float(retry_click_ratio["y_ratio"]),
                                required=False,
                            )
                            time.sleep(max(float(args.after_add_wait), 0.0))
                            post_add_first_name = find_accessible_match(
                                terms=DESKTOP_FIRST_NAME_TERMS,
                                role="text",
                                visible_only=True,
                                label_prefix="retry_find_first_name",
                            )
                            post_add_done_button = find_accessible_match(
                                terms=DESKTOP_DONE_BUTTON_TERMS,
                                role="push button",
                                visible_only=True,
                                label_prefix="retry_find_done_button",
                            )
                            dialog_detected = bool(post_add_first_name or post_add_done_button)
                    if not dialog_detected:
                        outcome = "ui_add_dialog_not_detected"
                        raise RuntimeError("Add contact dialog did not appear after clicking Add to contacts")

                    last_name_text = _nonempty(args.last_name_text)
                    last_name_result: dict[str, Any] | None = None
                    if last_name_text:
                        last_name_result = try_accessible_type("type_last_name_accessible", DESKTOP_LAST_NAME_TERMS, last_name_text)
                        if last_name_result is None:
                            type_command = _portable_action_command(repo_root, actor, "type-text", "--text", last_name_text)
                            if bool(args.press_enter_after_last_name):
                                type_command.append("--press-enter")
                            run_portable_step("type_last_name_fallback", type_command, required=False)
                        time.sleep(0.15)

                    dialog_submit_ratio = (
                        _portable_derive_dialog_submit_ratio(last_name_result, window_geometry)
                        or _portable_derive_dialog_submit_ratio(post_add_done_button, window_geometry)
                        or _portable_derive_dialog_submit_ratio(post_add_first_name, window_geometry)
                    )
                    if dialog_submit_ratio:
                        steps.append(
                            {
                                "label": "dialog_submit_click",
                                "x_ratio": dialog_submit_ratio["x_ratio"],
                                "y_ratio": dialog_submit_ratio["y_ratio"],
                            }
                        )
                        click_window_ratio(
                            "click_done_dialog_submit",
                            x_ratio=float(dialog_submit_ratio["x_ratio"]),
                            y_ratio=float(dialog_submit_ratio["y_ratio"]),
                            required=False,
                        )
                    elif post_add_done_button is not None:
                        done_click_ratio = (
                            _portable_match_origin_ratio(post_add_done_button["match"])
                            or _portable_derive_accessible_click_ratio(post_add_done_button["match"], window_geometry)
                            or {"x_ratio": float(args.done_click_x_ratio), "y_ratio": float(args.done_click_y_ratio)}
                        )
                        steps.append(
                            {
                                "label": "resolved_done_contact_click",
                                "x_ratio": done_click_ratio["x_ratio"],
                                "y_ratio": done_click_ratio["y_ratio"],
                            }
                        )
                        click_window_ratio(
                            "click_done_button",
                            x_ratio=float(done_click_ratio["x_ratio"]),
                            y_ratio=float(done_click_ratio["y_ratio"]),
                            required=False,
                        )
                    else:
                        done_repeat = max(int(args.done_click_repeat), 1)
                        for index in range(done_repeat):
                            click_window_ratio(
                                f"click_done_{index + 1}",
                                x_ratio=float(args.done_click_x_ratio),
                                y_ratio=float(args.done_click_y_ratio),
                                required=False,
                            )
                            time.sleep(0.12)
                    time.sleep(max(float(args.after_done_wait), 0.0))

        capture_screenshot("profile_after_actions", "desktop_add_contact_profile_after_actions.png")

        if bool(args.verify_profile_reopen):
            verify_open_command = _portable_action_command(repo_root, actor, "open-uri", "--uri", uri)
            if args.dry_run:
                verify_open_command.append("--dry-run")
            run_portable_step("reopen_profile_for_verify", verify_open_command)
            if not args.dry_run:
                time.sleep(max(float(args.verify_wait), 0.0))
            capture_screenshot("profile_verify", "desktop_add_contact_profile_verify.png")
            if not args.dry_run and args.confirm_add:
                verification = probe_contact_verification("verify_term")
                verification["stage"] = "verify_reopen"
                log_lines.append(
                    "INFO: verify outcome="
                    f"{verification['outcome']} add_visible={int(bool(verification['add_visible']))} "
                    f"success_visible={int(bool(verification['success_visible']))} "
                    f"term_counts={json.dumps(verification['term_counts'], ensure_ascii=False)}"
                )

        if args.dry_run:
            outcome = "dry_run"
        elif verification is not None:
            verification_outcome = str(verification.get("outcome") or "contact_add_unverified")
            if preexisting_contact_detected and verification_outcome == "contact_added_verified":
                outcome = "contact_already_present"
            else:
                outcome = verification_outcome
        elif args.confirm_add:
            outcome = "contact_submit_clicked"
        else:
            outcome = "profile_opened"
    except Exception as exc:  # noqa: BLE001
        if outcome == "started":
            outcome = "failed"
        log_lines.append(f"ERROR: {exc}")
        response = {
            "status": "failed",
            "outcome": outcome,
            "job_dir": str(job_dir),
            "execution_id": execution_id,
            "username": username,
            "uri": uri,
            "portable_actor": actor,
            "portable": portable,
            "screenshots": screenshots,
            "verification": verification,
            "error": str(exc),
            "steps": steps,
        }
        run_dir = _write_execution_record(job_dir, execution_id, response, log_lines)
        response["run_dir"] = str(run_dir)
        print(json.dumps(response, ensure_ascii=False, indent=2))
        return 0 if args.dry_run else 1

    status = "completed"
    return_code = 0
    if args.confirm_add and verification is not None and not _is_contact_add_success_outcome(outcome):
        status = "failed"
        return_code = 1

    response = {
        "status": status,
        "outcome": outcome,
        "job_dir": str(job_dir),
        "execution_id": execution_id,
        "username": username,
        "uri": uri,
        "portable_actor": actor,
        "portable": portable,
        "screenshots": screenshots,
        "verification": verification,
        "steps": steps,
    }
    run_dir = _write_execution_record(job_dir, execution_id, response, log_lines)
    response["run_dir"] = str(run_dir)
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return return_code


def command_desktop_add_contact_batch(args: argparse.Namespace) -> int:
    job_dir = Path(args.job_dir).expanduser()
    repo_root = Path(__file__).resolve().parents[1]
    input_path = Path(args.input).expanduser().resolve() if _nonempty(args.input) else None
    state_exists = state_path_for(job_dir).exists()
    if not state_exists:
        if input_path is None:
            raise ValueError("desktop-add-contact-batch requires --input when invite_state.json does not exist")
        if not input_path.exists():
            raise ValueError(f"input file does not exist: {input_path}")
        payload = _init_job_state_from_input(
            job_dir=job_dir,
            input_path=input_path,
            chat_url=_nonempty(args.chat_url) or f"contacts://{job_dir.name}",
        )
        initialized_from_input = True
    else:
        payload = load_state(job_dir)
        initialized_from_input = False

    _merge_execution_config(
        payload,
        portable_profile_name=getattr(args, "portable_profile_name", None),
        portable_profile_dir=getattr(args, "portable_profile_dir", None),
        account_username=getattr(args, "account_username", None),
        account_label=getattr(args, "account_label", None),
    )
    save_state(job_dir, payload)

    execution = _resolved_execution_config(payload)
    actor = execution.get("portable_actor") or {}
    if not _portable_actor_args(actor):
        raise ValueError("desktop-add-contact-batch requires portable_actor in execution config")

    portable = _ensure_portable_actor_ready(
        repo_root=repo_root,
        actor=actor,
        launch_if_needed=bool(args.launch_if_needed),
    )
    if int(portable["status_result"].get("returncode", 1) or 0) != 0:
        raise RuntimeError(
            portable["status_result"].get("stderr")
            or portable["status_result"].get("stdout")
            or "portable status failed"
        )
    if not portable["running"]:
        raise RuntimeError(
            "portable actor is not running; rerun with --launch-if-needed or start Telegram Desktop portable"
        )

    statuses = [ensure_valid_status(item) for item in (args.statuses or DEFAULT_CONTACT_BATCH_STATUSES)]
    limit = max(int(args.limit or 0), 0)
    selection_limit = limit if limit > 0 else 10_000
    candidates = select_candidates(payload, selection_limit, statuses)
    execution_id = args.execution_id or _execution_id_now()
    log_lines = [
        f"INFO: desktop-add-contact-batch started execution_id={execution_id}",
        f"INFO: job_dir={job_dir}",
        f"INFO: initialized_from_input={int(initialized_from_input)}",
        f"INFO: statuses={','.join(statuses)} limit={limit or 0} selected={len(candidates)}",
        f"INFO: confirm_add={int(bool(args.confirm_add))} dry_run={int(bool(args.dry_run))}",
    ]
    results: list[dict[str, Any]] = []
    added_count = 0
    already_present_count = 0
    failed_count = 0

    for index, row in enumerate(candidates, start=1):
        username = str(row.get("username") or "")
        user_execution_id = f"{execution_id}-{index:03d}-{username.lstrip('@')}"
        log_lines.append(f"INFO: processing {username} execution_id={user_execution_id}")
        namespace = argparse.Namespace(
            job_dir=str(job_dir),
            username=username,
            execution_id=user_execution_id,
            open_wait=float(args.open_wait),
            after_add_wait=float(args.after_add_wait),
            after_done_wait=float(args.after_done_wait),
            verify_wait=float(args.verify_wait),
            add_click_x_ratio=float(args.add_click_x_ratio),
            add_click_y_ratio=float(args.add_click_y_ratio),
            done_click_x_ratio=float(args.done_click_x_ratio),
            done_click_y_ratio=float(args.done_click_y_ratio),
            done_click_repeat=int(args.done_click_repeat),
            last_name_text=_nonempty(args.last_name_text),
            press_enter_after_last_name=bool(args.press_enter_after_last_name),
            launch_if_needed=False,
            verify_profile_reopen=bool(args.verify_profile_reopen),
            confirm_add=bool(args.confirm_add),
            dry_run=bool(args.dry_run),
        )
        try:
            user_rc, user_payload = _invoke_json_command(command_desktop_add_contact_profile, namespace)
            result: dict[str, Any] = {
                "username": username,
                "returncode": int(user_rc),
                "status": str(user_payload.get("status") or ""),
                "outcome": str(user_payload.get("outcome") or ""),
                "run_dir": str(user_payload.get("run_dir") or ""),
                "verification": user_payload.get("verification")
                if isinstance(user_payload.get("verification"), dict)
                else None,
            }
            successful_contact = _is_contact_add_success_outcome(user_payload.get("outcome"))
            if user_rc == 0 and str(user_payload.get("status") or "") == "completed" and successful_contact:
                if not args.dry_run and args.confirm_add:
                    state_payload = load_state(job_dir)
                    current_user = _find_state_user(state_payload, username)
                    if current_user is not None:
                        result["state_update"] = _record_user_status(
                            job_dir,
                            state_payload,
                            current_user,
                            status="contact_added",
                            reason=(
                                "desktop_contact_batch_already_present"
                                if str(user_payload.get("outcome") or "") == "contact_already_present"
                                else "desktop_contact_batch_added"
                            ),
                        )
                    added_count += 1
                    if str(user_payload.get("outcome") or "") == "contact_already_present":
                        already_present_count += 1
                else:
                    result["state_update"] = None
                log_lines.append(f"INFO: success {username} outcome={result['outcome']}")
            else:
                failed_count += 1
                result["error"] = str(
                    user_payload.get("error")
                    or (
                        "contact add was not verified after profile reopen"
                        if str(user_payload.get("outcome") or "") in {"contact_not_added", "contact_add_unverified"}
                        else f"command failed with code {user_rc}"
                    )
                )
                if not args.dry_run:
                    state_payload = load_state(job_dir)
                    current_user = _find_state_user(state_payload, username)
                    if current_user is not None:
                        result["state_update"] = _record_user_status(
                            job_dir,
                            state_payload,
                            current_user,
                            status="failed",
                            reason=(
                                "desktop_contact_batch_not_verified"
                                if str(user_payload.get("outcome") or "") in {"contact_not_added", "contact_add_unverified"}
                                else "desktop_contact_batch_failed"
                            ),
                        )
                log_lines.append(f"WARN: failed {username} error={result.get('error')!r}")
            results.append(result)
        except Exception as exc:  # noqa: BLE001
            failed_count += 1
            result = {
                "username": username,
                "returncode": 1,
                "status": "failed",
                "outcome": "failed",
                "error": str(exc),
            }
            if not args.dry_run:
                state_payload = load_state(job_dir)
                current_user = _find_state_user(state_payload, username)
                if current_user is not None:
                    result["state_update"] = _record_user_status(
                        job_dir,
                        state_payload,
                        current_user,
                        status="failed",
                        reason="desktop_contact_batch_failed",
                    )
            results.append(result)
            log_lines.append(f"ERROR: {username} {exc}")

    final_state = load_state(job_dir)
    summary = summarize_state(final_state)
    remaining_candidates = select_candidates(final_state, 10_000, statuses)
    response = {
        "status": "completed_with_errors" if failed_count else ("dry_run" if args.dry_run else "completed"),
        "job_dir": str(job_dir),
        "input_path": str(input_path) if input_path is not None else str(final_state.get("source_file") or ""),
        "initialized_from_input": bool(initialized_from_input),
        "execution_id": execution_id,
        "portable_actor": actor,
        "portable": portable,
        "selected_users": len(candidates),
        "added_count": added_count,
        "already_present_count": already_present_count,
        "failed_count": failed_count,
        "remaining_candidates": len(remaining_candidates),
        "remaining_usernames": [str(item.get("username") or "") for item in remaining_candidates[:20]],
        "summary": summary,
        "results": results,
    }
    run_dir = _write_contact_batch_artifacts(job_dir, execution_id, response, log_lines)
    response["run_dir"] = str(run_dir)
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0


def command_inspect_chat(args: argparse.Namespace) -> int:
    job_dir = Path(args.job_dir).expanduser()
    payload = load_state(job_dir)
    repo_root = Path(__file__).resolve().parents[1]
    execution = _resolved_execution_config(
        payload,
        client_id=args.client_id,
        tab_id=args.tab_id,
        url_pattern=args.url_pattern,
        active=args.active,
    )
    browser_target = execution.get("browser_target") or {}
    steps: list[dict[str, Any]] = []

    def run_step(label: str, command: list[str], *, required: bool = True) -> dict[str, Any]:
        if args.dry_run:
            result = {"label": label, "command": command, "dry_run": True, "returncode": 0, "stdout_json": {}}
        else:
            result = {"label": label, **_run_browser_json(repo_root, command)}
        steps.append(result)
        if required and int(result.get("returncode", 1) or 0) != 0:
            raise RuntimeError(f"{label} failed: {result.get('stderr') or result.get('stdout')}")
        return result

    if not args.skip_open:
        open_result = run_step(
            "open_or_activate_chat",
            _browser_command(
                repo_root,
                chat_url=str(payload.get("chat_url") or ""),
                browser_target=browser_target,
            ),
        )
        opened_tab_id = _extract_tab_id(open_result.get("stdout_json") or {})
        if opened_tab_id > 0:
            browser_target["tab_id"] = opened_tab_id

    snapshot = _read_chat_snapshot(run_step, browser_target)
    response = {
        "status": "completed",
        "job_dir": str(job_dir),
        "chat_url": str(payload.get("chat_url") or ""),
        "page_url": snapshot["page_url"],
        "member_count": snapshot["member_count"],
        "member_count_text": snapshot["member_count_text"],
        "add_members_visible": snapshot["add_members_visible"],
        "visible_member_count": snapshot["visible_member_count"],
        "visible_member_peers": snapshot["visible_member_peers"],
        "dry_run": bool(args.dry_run),
        "steps": steps,
    }
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0


def command_add_contact(args: argparse.Namespace) -> int:
    job_dir = Path(args.job_dir).expanduser()
    payload = load_state(job_dir)
    repo_root = Path(__file__).resolve().parents[1]
    username = normalize_username(args.username)
    if not username:
        raise ValueError("add-contact requires a valid Telegram username")

    user = _find_state_user(payload, username)
    if user is None:
        raise ValueError(f"user is not present in invite_state.json: {username}")
    if not bool(user.get("consent")):
        raise ValueError(f"user has no consent=yes in invite_state.json: {username}")

    execution = _resolved_execution_config(
        payload,
        client_id=args.client_id,
        tab_id=args.tab_id,
        url_pattern=args.url_pattern,
        active=args.active,
    )
    browser_target = execution.get("browser_target") or {}
    search_query = _nonempty(args.search_query) or username.lstrip("@")
    execution_id = args.execution_id or _execution_id_now()
    verify_membership = _bool_flag(
        getattr(args, "verify_membership", None),
        default=bool(args.confirm_add and not args.dry_run),
    )
    verify_wait = max(float(getattr(args, "verify_wait", 10.0) or 0.0), 0.0)
    log_lines = [
        f"INFO: add-contact started execution_id={execution_id}",
        f"INFO: username={username} search_query={search_query}",
        f"INFO: confirm_add={int(bool(args.confirm_add))} record_result={int(bool(args.record_result))}",
        f"INFO: verify_membership={int(bool(verify_membership))} verify_wait={verify_wait}",
    ]
    steps: list[dict[str, Any]] = []
    selected_candidate: dict[str, str] | None = None
    outcome = "dry_run" if args.dry_run else "started"
    record_update: dict[str, str] | None = None
    verification: dict[str, Any] | None = None

    def run_step(label: str, command: list[str], *, required: bool = True) -> dict[str, Any]:
        if args.dry_run:
            result = {"label": label, "command": command, "dry_run": True, "returncode": 0, "stdout_json": {}}
        else:
            result = {"label": label, **_run_browser_json(repo_root, command)}
        steps.append(result)
        if required and int(result.get("returncode", 1) or 0) != 0:
            raise RuntimeError(f"{label} failed: {result.get('stderr') or result.get('stdout')}")
        return result

    def capture_snapshot(label: str, *, required: bool) -> dict[str, Any]:
        try:
            snapshot = _read_chat_snapshot(run_step, browser_target, label_prefix=f"{label}:")
        except Exception as exc:  # noqa: BLE001
            if required:
                raise
            snapshot = _chat_snapshot_summary(error=str(exc))
        log_lines.append(_snapshot_log_line(label, snapshot))
        return snapshot

    try:
        if not args.skip_open:
            open_result = run_step(
                "open_or_activate_chat",
                _browser_command(
                    repo_root,
                    chat_url=str(payload.get("chat_url") or ""),
                    browser_target=browser_target,
                ),
            )
            opened_tab_id = _extract_tab_id(open_result.get("stdout_json") or {})
            if opened_tab_id > 0:
                browser_target["tab_id"] = opened_tab_id
                log_lines.append(f"INFO: using opened tab_id={opened_tab_id}")

        before_snapshot: dict[str, Any] | None = None
        after_snapshot: dict[str, Any] | None = None
        after_wait_snapshot: dict[str, Any] | None = None
        if verify_membership and args.confirm_add and not args.dry_run:
            before_snapshot = capture_snapshot("inspect_before", required=True)

        opened_add_members = False
        for selector in ADD_MEMBERS_OPEN_SELECTORS:
            result = run_step(
                f"open_add_members:{selector}",
                _browser_action_command(browser_target, "click", selector),
                required=False,
            )
            if int(result.get("returncode", 1) or 0) == 0:
                opened_add_members = True
                break
        if not args.dry_run and not opened_add_members:
            raise RuntimeError("cannot open Add Members panel; profile sidebar with can-add-members is not available")

        run_step("wait_add_members_search", _browser_action_command(browser_target, "wait", ADD_MEMBERS_SEARCH_SELECTOR))
        run_step("fill_add_members_search", _browser_action_command(browser_target, "fill", ADD_MEMBERS_SEARCH_SELECTOR, search_query))
        if not args.dry_run:
            time.sleep(max(float(args.search_wait), 0.0))

        html_result = run_step("read_add_members_html", _browser_action_command(browser_target, "html", "body"))
        html_payload = _browser_payload_text(html_result, "html")
        candidates = _parse_add_members_candidates(html_payload)
        log_lines.append(f"INFO: add-members candidates={json.dumps(candidates, ensure_ascii=False)}")
        if args.dry_run:
            outcome = "dry_run"
        else:
            if not candidates:
                outcome = "not_found"
                raise RuntimeError(f"Telegram Add Members search returned no candidates for {username}")
            if len(candidates) > 1 and not args.allow_first_result:
                outcome = "ambiguous"
                raise RuntimeError(
                    "Telegram Add Members search returned multiple candidates; rerun with --allow-first-result after manual check"
                )
            selected_candidate = candidates[0]
            run_step(
                "select_candidate",
                _browser_action_command(
                    browser_target,
                    "click",
                    f'.add-members-container .chatlist a.row[data-peer-id="{selected_candidate["peer_id"]}"]',
                ),
            )
            if not args.confirm_add:
                outcome = "confirmation_not_requested"
            else:
                run_step("open_add_confirmation", _browser_action_command(browser_target, "click", ADD_MEMBERS_CONFIRM_SELECTOR))
                if not args.dry_run:
                    time.sleep(max(float(args.confirm_wait), 0.0))
                run_step("confirm_add", _browser_action_command(browser_target, "click", ADD_MEMBERS_POPUP_ADD_SELECTOR))
                if not args.dry_run:
                    time.sleep(max(float(args.result_wait), 0.0))
                text_result = run_step("read_result_text", _browser_action_command(browser_target, "text", "body"), required=False)
                html_after_result = run_step("read_result_html", _browser_action_command(browser_target, "html", "body"), required=False)
                text_payload = _browser_payload_text(text_result, "text").lower()
                html_after = _browser_payload_text(html_after_result, "html")
                error_terms = ("privacy", "cannot", "too many", "sorry", "error", "ошибка", "нельзя", "limit")
                if any(term in text_payload for term in error_terms):
                    outcome = "telegram_error_visible"
                elif "popup-add-members active" in html_after:
                    outcome = "confirmation_still_open"
                else:
                    if verify_membership and not args.dry_run:
                        after_snapshot = capture_snapshot("inspect_after", required=False)
                        verification = _build_membership_verification(selected_candidate, before_snapshot, after_snapshot, None)
                        if not verification.get("joined_confirmed") and verify_wait > 0:
                            time.sleep(verify_wait)
                            after_wait_snapshot = capture_snapshot("inspect_after_wait", required=False)
                            verification = _build_membership_verification(
                                selected_candidate,
                                before_snapshot,
                                after_snapshot,
                                after_wait_snapshot,
                            )
                    outcome = "joined_confirmed" if verification and verification.get("joined_confirmed") else "confirmed_unverified"
                    if args.record_result:
                        target_status = "requested"
                        reason = "live_add_members_confirmed_unverified"
                        if verification and verification.get("joined_confirmed"):
                            target_status = "joined"
                            if verification.get("confirmed_signal") == "member_list_visible_peer":
                                reason = "live_add_members_member_list_confirmed"
                            else:
                                reason = "live_add_members_member_count_confirmed"
                        record_update = _record_user_status(
                            job_dir,
                            payload,
                            user,
                            status=target_status,
                            reason=reason,
                        )
    except Exception as exc:  # noqa: BLE001
        if outcome in {"started", "dry_run"}:
            outcome = "failed"
        log_lines.append(f"ERROR: {exc}")
        response = {
            "status": "failed",
            "outcome": outcome,
            "job_dir": str(job_dir),
            "execution_id": execution_id,
            "username": username,
            "search_query": search_query,
            "selected_candidate": selected_candidate,
            "record_update": record_update,
            "target_status": record_update["to_status"] if isinstance(record_update, dict) else "",
            "verification": verification,
            "error": str(exc),
            "steps": steps,
        }
        run_dir = _write_execution_record(job_dir, execution_id, response, log_lines)
        response["run_dir"] = str(run_dir)
        print(json.dumps(response, ensure_ascii=False, indent=2))
        return 0 if args.dry_run else 1

    status = "completed" if outcome not in {"failed", "telegram_error_visible", "confirmation_still_open"} else "failed"
    response = {
        "status": status,
        "outcome": outcome,
        "job_dir": str(job_dir),
        "execution_id": execution_id,
        "username": username,
        "search_query": search_query,
        "selected_candidate": selected_candidate,
        "record_update": record_update,
        "target_status": record_update["to_status"] if isinstance(record_update, dict) else "",
        "verification": verification,
        "steps": steps,
    }
    run_dir = _write_execution_record(job_dir, execution_id, response, log_lines)
    response["run_dir"] = str(run_dir)
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0 if status == "completed" else 1


def command_record(args: argparse.Namespace) -> int:
    job_dir = Path(args.job_dir).expanduser()
    payload = load_state(job_dir)
    target_status = ensure_valid_status(args.status)
    requested = [normalize_username(value) for value in args.username]
    requested = [value for value in requested if value]
    at = now_utc()
    users_by_username = {
        str(row.get("username") or ""): row
        for row in payload.get("users") or []
        if isinstance(row, dict)
    }
    updated = []
    missing = []
    log_lines = [
        f"INFO: execution record started execution_id={args.execution_id or ''}",
        f"INFO: target_status={target_status} reason={args.reason}",
    ]
    for username in requested:
        current = users_by_username.get(username)
        if current is None:
            missing.append(username)
            log_lines.append(f"WARN: missing user {username}")
            continue
        from_status = str(current.get("status") or "")
        current["status"] = target_status
        current["last_attempt_at"] = at
        current["attempts"] = int(current.get("attempts", 0) or 0) + 1
        append_history(current, from_status, target_status, args.reason, at)
        updated.append({"username": username, "from_status": from_status, "to_status": target_status})
        log_lines.append(f"INFO: {username} {from_status} -> {target_status} ({args.reason})")
    save_state(job_dir, payload)

    execution_id = args.execution_id or _execution_id_now()
    record_payload = {
        "status": "completed",
        "job_dir": str(job_dir),
        "execution_id": execution_id,
        "reason": args.reason,
        "updated": updated,
        "missing": missing,
        "target_status": target_status,
    }
    run_dir = _write_execution_record(job_dir, execution_id, record_payload, log_lines)
    record_payload["run_dir"] = str(run_dir)
    print(json.dumps(record_payload, ensure_ascii=False, indent=2))
    return 0


def command_report(args: argparse.Namespace) -> int:
    job_dir = Path(args.job_dir).expanduser()
    payload = load_state(job_dir)
    summary = summarize_state(payload)
    executions = []
    execution_records = []
    execution_root = _execution_runs_dir(job_dir)
    if execution_root.exists():
        for path in sorted(execution_root.glob("*/execution_plan.json"))[-5:]:
            try:
                execution_payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            executions.append(
                {
                    "execution_id": str(execution_payload.get("execution_id") or ""),
                    "selected_users": int(execution_payload.get("selected_users", 0) or 0),
                    "reserved": int(execution_payload.get("reserved", 0) or 0),
                    "path": str(path),
                }
            )
        for path in sorted(execution_root.glob("*/execution_record.json"))[-5:]:
            try:
                record_payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            verification = record_payload.get("verification")
            execution_records.append(
                {
                    "execution_id": str(record_payload.get("execution_id") or ""),
                    "status": str(record_payload.get("status") or ""),
                    "outcome": str(record_payload.get("outcome") or ""),
                    "target_status": str(record_payload.get("target_status") or ""),
                    "verification_reason": str(verification.get("reason") or "") if isinstance(verification, dict) else "",
                    "joined_confirmed": bool(verification.get("joined_confirmed")) if isinstance(verification, dict) else False,
                    "path": str(path),
                }
            )
    summary["job_dir"] = str(job_dir)
    summary["execution"] = _resolved_execution_config(payload)
    summary["latest_execution_plans"] = executions
    summary["latest_execution_records"] = execution_records
    summary["next_execution_batch"] = _plan_users(
        payload,
        limit=args.limit,
        statuses=DEFAULT_EXECUTION_STATUSES,
        execution=_resolved_execution_config(payload),
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _add_bool_choice(parser: argparse.ArgumentParser, name: str, *, dest: str, help_true: str, help_false: str) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument(name, dest=dest, action="store_true", help=help_true)
    group.add_argument(f"--no-{name[2:]}", dest=dest, action="store_false", help=help_false)
    parser.set_defaults(**{dest: None})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Telegram Invite Executor: safe site-control based execution layer for consent-based invite workflows."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    configure_parser = subparsers.add_parser("configure", help="Store invite link and browser target configuration in invite_state.json.")
    configure_parser.add_argument("--job-dir", required=True)
    configure_parser.add_argument("--invite-link")
    configure_parser.add_argument("--message-template")
    configure_parser.add_argument("--note")
    configure_parser.add_argument("--client-id")
    configure_parser.add_argument("--tab-id", type=int)
    configure_parser.add_argument("--url-pattern")
    configure_parser.add_argument("--portable-profile-name", help="Telegram Desktop portable profile name used as invite actor.")
    configure_parser.add_argument("--portable-profile-dir", help="Explicit Telegram Desktop portable profile dir used as invite actor.")
    configure_parser.add_argument("--account-username", help="Expected Telegram account username for the portable actor.")
    configure_parser.add_argument("--account-label", help="Human-readable Telegram account/window label for the portable actor.")
    _add_bool_choice(
        configure_parser,
        "--requires-approval",
        dest="requires_approval",
        help_true="Mark configured invite workflow as join-request based.",
        help_false="Mark configured invite workflow as direct join without approval.",
    )
    _add_bool_choice(
        configure_parser,
        "--active",
        dest="active",
        help_true="Prefer active tab when browser target is implicit.",
        help_false="Do not force active tab preference in browser target.",
    )
    configure_parser.set_defaults(func=command_configure)

    plan_parser = subparsers.add_parser("plan", help="Create operator-assisted execution plan for next checked users.")
    plan_parser.add_argument("--job-dir", required=True)
    plan_parser.add_argument("--limit", type=int, default=3)
    plan_parser.add_argument("--statuses", nargs="*", default=list(DEFAULT_EXECUTION_STATUSES))
    plan_parser.add_argument("--invite-link")
    plan_parser.add_argument("--message-template")
    plan_parser.add_argument("--note")
    _add_bool_choice(
        plan_parser,
        "--requires-approval",
        dest="requires_approval",
        help_true="Treat execution plan as join-request flow.",
        help_false="Treat execution plan as direct join link flow.",
    )
    plan_parser.add_argument("--reserve", action="store_true", help="Reserve selected users by moving them to invite_link_created.")
    plan_parser.set_defaults(func=command_plan)

    open_parser = subparsers.add_parser("open-chat", help="Open or activate target Telegram chat through site-control browser CLI.")
    open_parser.add_argument("--job-dir", required=True)
    open_parser.add_argument("--client-id")
    open_parser.add_argument("--tab-id", type=int)
    open_parser.add_argument("--url-pattern")
    _add_bool_choice(
        open_parser,
        "--active",
        dest="active",
        help_true="Prefer active tab when browser target is implicit.",
        help_false="Do not force active tab preference in browser target.",
    )
    open_parser.add_argument("--dry-run", action="store_true")
    open_parser.set_defaults(func=command_open_chat)

    ensure_portable_parser = subparsers.add_parser(
        "ensure-portable",
        help="Verify or launch the configured Telegram Desktop portable actor for this invite job.",
    )
    ensure_portable_parser.add_argument("--job-dir", required=True)
    ensure_portable_parser.add_argument("--portable-profile-name")
    ensure_portable_parser.add_argument("--portable-profile-dir")
    ensure_portable_parser.add_argument("--account-username")
    ensure_portable_parser.add_argument("--account-label")
    ensure_portable_parser.add_argument("--launch-if-needed", action="store_true")
    ensure_portable_parser.set_defaults(func=command_ensure_portable)

    prepare_next_parser = subparsers.add_parser(
        "prepare-next",
        help="One-command safe pipeline: ensure portable actor, select one consented user, check and reserve an execution plan.",
    )
    prepare_next_parser.add_argument("--job-dir", required=True)
    prepare_next_parser.add_argument("--username", help="Optional explicit username. If missing, the next checked/new consented user is selected.")
    prepare_next_parser.add_argument("--consent", default="", help="Must be yes when adding a new username through prepare-next.")
    prepare_next_parser.add_argument("--display-name", default="")
    prepare_next_parser.add_argument("--note", default="prepare-next")
    prepare_next_parser.add_argument("--source", default="prepare-next")
    prepare_next_parser.add_argument("--statuses", nargs="*", default=["checked", "new"])
    prepare_next_parser.add_argument("--execution-id")
    prepare_next_parser.add_argument("--launch-if-needed", action="store_true")
    reserve_group = prepare_next_parser.add_mutually_exclusive_group()
    reserve_group.add_argument("--reserve", dest="reserve", action="store_true", help="Move selected checked user to invite_link_created.")
    reserve_group.add_argument("--no-reserve", dest="reserve", action="store_false", help="Leave selected user in checked after planning.")
    prepare_next_parser.set_defaults(reserve=True)
    prepare_next_parser.add_argument("--dry-run", action="store_true")
    prepare_next_parser.set_defaults(func=command_prepare_next)

    desktop_send_parser = subparsers.add_parser(
        "desktop-send-link",
        help="Open one consented user's DM in Telegram Desktop portable and optionally send the configured invite link.",
    )
    desktop_send_parser.add_argument("--job-dir", required=True)
    desktop_send_parser.add_argument("--username", required=True)
    desktop_send_parser.add_argument("--invite-link", help="Override configured invite link. Defaults to execution.invite_link.")
    desktop_send_parser.add_argument("--message", help="ASCII message to type. Defaults to invite link only.")
    desktop_send_parser.add_argument("--statuses", nargs="*", default=["invite_link_created", "checked"])
    desktop_send_parser.add_argument("--execution-id")
    desktop_send_parser.add_argument("--window-id", help="Explicit X11 Telegram Desktop window id. Defaults to the portable actor window.")
    desktop_send_parser.add_argument("--open-wait", type=float, default=1.5)
    desktop_send_parser.add_argument("--launch-if-needed", action="store_true")
    desktop_send_parser.add_argument(
        "--confirm-send",
        action="store_true",
        help="Press Enter after typing. Without this flag the command only prepares/dry-runs the typing step.",
    )
    desktop_send_parser.add_argument(
        "--record-result",
        action="store_true",
        help="When --confirm-send succeeds, move the user to sent in invite_state.json.",
    )
    desktop_send_parser.add_argument("--dry-run", action="store_true")
    desktop_send_parser.set_defaults(func=command_desktop_send_link)

    desktop_open_add_parser = subparsers.add_parser(
        "desktop-open-add-members",
        help="Portable-only no-API UI path: open group info, try to open Add Members, and optionally type one username into the search field.",
    )
    desktop_open_add_parser.add_argument("--job-dir", required=True)
    desktop_open_add_parser.add_argument("--username", required=True)
    desktop_open_add_parser.add_argument("--search-query", help="Override Add Members search query; defaults to username without @.")
    desktop_open_add_parser.add_argument("--group-uri", help="Override group tg://resolve URI. Defaults to public t.me chat_url from invite_state.json.")
    desktop_open_add_parser.add_argument("--execution-id")
    desktop_open_add_parser.add_argument("--open-wait", type=float, default=1.8)
    desktop_open_add_parser.add_argument("--panel-wait", type=float, default=1.2)
    desktop_open_add_parser.add_argument("--search-wait", type=float, default=1.2)
    desktop_open_add_parser.add_argument("--min-search-x", type=int, default=0, help="Optional absolute X fallback for the Add Members search field.")
    desktop_open_add_parser.add_argument("--min-search-ratio", type=float, default=0.55, help="Expected left edge ratio for the right-side Add Members search field within the Telegram window.")
    desktop_open_add_parser.add_argument("--launch-if-needed", action="store_true")
    desktop_open_add_parser.add_argument("--allow-alerts", action="store_true")
    type_search_group = desktop_open_add_parser.add_mutually_exclusive_group()
    type_search_group.add_argument(
        "--type-search",
        dest="type_search",
        action="store_true",
        help="After opening Add Members, type the username into the right-side search field.",
    )
    type_search_group.add_argument(
        "--no-type-search",
        dest="type_search",
        action="store_false",
        help="Stop after opening Add Members and dumping search fields.",
    )
    desktop_open_add_parser.set_defaults(type_search=True)
    desktop_open_add_parser.add_argument("--clear-search", action="store_true")
    desktop_open_add_parser.add_argument("--press-enter-after-search", action="store_true")
    desktop_open_add_parser.add_argument("--dry-run", action="store_true")
    desktop_open_add_parser.set_defaults(func=command_desktop_open_add_members)

    desktop_add_contact_parser = subparsers.add_parser(
        "desktop-add-contact-profile",
        help="Portable no-API contact flow: open user profile, click Add to Contacts, and submit Done via configured click ratios.",
    )
    desktop_add_contact_parser.add_argument("--job-dir", required=True)
    desktop_add_contact_parser.add_argument("--username", required=True)
    desktop_add_contact_parser.add_argument("--execution-id")
    desktop_add_contact_parser.add_argument("--open-wait", type=float, default=1.2)
    desktop_add_contact_parser.add_argument("--after-add-wait", type=float, default=0.8)
    desktop_add_contact_parser.add_argument("--after-done-wait", type=float, default=0.8)
    desktop_add_contact_parser.add_argument("--verify-wait", type=float, default=1.2)
    desktop_add_contact_parser.add_argument("--add-click-x-ratio", type=float, default=DESKTOP_ADD_CONTACT_X_RATIO)
    desktop_add_contact_parser.add_argument("--add-click-y-ratio", type=float, default=DESKTOP_ADD_CONTACT_Y_RATIO)
    desktop_add_contact_parser.add_argument("--done-click-x-ratio", type=float, default=DESKTOP_DONE_CONTACT_X_RATIO)
    desktop_add_contact_parser.add_argument("--done-click-y-ratio", type=float, default=DESKTOP_DONE_CONTACT_Y_RATIO)
    desktop_add_contact_parser.add_argument("--done-click-repeat", type=int, default=1)
    desktop_add_contact_parser.add_argument(
        "--last-name-text",
        default="",
        help="Optional ASCII text to type into the New Contact last name field before Done click.",
    )
    desktop_add_contact_parser.add_argument("--press-enter-after-last-name", action="store_true")
    desktop_add_contact_parser.add_argument("--launch-if-needed", action="store_true")
    _add_bool_choice(
        desktop_add_contact_parser,
        "--verify-profile-reopen",
        dest="verify_profile_reopen",
        help_true="Re-open tg://resolve?...&profile after clicks and capture verify screenshot.",
        help_false="Skip profile reopen verification screenshot.",
    )
    desktop_add_contact_parser.add_argument(
        "--confirm-add",
        action="store_true",
        help="Actually click Add to Contacts and Done. Without this flag the command only opens profile and captures evidence.",
    )
    desktop_add_contact_parser.add_argument("--dry-run", action="store_true")
    desktop_add_contact_parser.set_defaults(func=command_desktop_add_contact_profile, verify_profile_reopen=True)

    desktop_add_contact_batch_parser = subparsers.add_parser(
        "desktop-add-contact-batch",
        help="Load consented usernames from a job/input file and add them into Telegram Desktop contacts one by one.",
    )
    desktop_add_contact_batch_parser.add_argument("--job-dir", required=True)
    desktop_add_contact_batch_parser.add_argument("--input", help="CSV/JSON input file. Required when invite_state.json does not exist yet.")
    desktop_add_contact_batch_parser.add_argument("--chat-url", default="", help="Service chat identifier used only when creating a new local job state from input.")
    desktop_add_contact_batch_parser.add_argument("--output-root", default="", help="Reserved for wrappers; batch command itself writes into --job-dir.")
    desktop_add_contact_batch_parser.add_argument("--portable-profile-name")
    desktop_add_contact_batch_parser.add_argument("--portable-profile-dir")
    desktop_add_contact_batch_parser.add_argument("--account-username")
    desktop_add_contact_batch_parser.add_argument("--account-label")
    desktop_add_contact_batch_parser.add_argument("--limit", type=int, default=0, help="0 means process all selectable usernames.")
    desktop_add_contact_batch_parser.add_argument("--statuses", nargs="*", default=list(DEFAULT_CONTACT_BATCH_STATUSES))
    desktop_add_contact_batch_parser.add_argument("--execution-id")
    desktop_add_contact_batch_parser.add_argument("--open-wait", type=float, default=1.2)
    desktop_add_contact_batch_parser.add_argument("--after-add-wait", type=float, default=0.8)
    desktop_add_contact_batch_parser.add_argument("--after-done-wait", type=float, default=0.8)
    desktop_add_contact_batch_parser.add_argument("--verify-wait", type=float, default=1.2)
    desktop_add_contact_batch_parser.add_argument("--add-click-x-ratio", type=float, default=DESKTOP_ADD_CONTACT_X_RATIO)
    desktop_add_contact_batch_parser.add_argument("--add-click-y-ratio", type=float, default=DESKTOP_ADD_CONTACT_Y_RATIO)
    desktop_add_contact_batch_parser.add_argument("--done-click-x-ratio", type=float, default=DESKTOP_DONE_CONTACT_X_RATIO)
    desktop_add_contact_batch_parser.add_argument("--done-click-y-ratio", type=float, default=DESKTOP_DONE_CONTACT_Y_RATIO)
    desktop_add_contact_batch_parser.add_argument("--done-click-repeat", type=int, default=1)
    desktop_add_contact_batch_parser.add_argument("--last-name-text", default="")
    desktop_add_contact_batch_parser.add_argument("--press-enter-after-last-name", action="store_true")
    desktop_add_contact_batch_parser.add_argument("--launch-if-needed", action="store_true")
    _add_bool_choice(
        desktop_add_contact_batch_parser,
        "--verify-profile-reopen",
        dest="verify_profile_reopen",
        help_true="Re-open the profile after each add and capture verify screenshots.",
        help_false="Skip verify reopen step for each contact.",
    )
    desktop_add_contact_batch_parser.add_argument(
        "--confirm-add",
        action="store_true",
        help="Actually click Add to Contacts and Done for every selected username.",
    )
    desktop_add_contact_batch_parser.add_argument("--dry-run", action="store_true")
    desktop_add_contact_batch_parser.set_defaults(func=command_desktop_add_contact_batch, verify_profile_reopen=True)

    inspect_parser = subparsers.add_parser(
        "inspect-chat",
        help="Read current Telegram chat view and extract visible member count from Telegram Web text.",
    )
    inspect_parser.add_argument("--job-dir", required=True)
    inspect_parser.add_argument("--client-id")
    inspect_parser.add_argument("--tab-id", type=int)
    inspect_parser.add_argument("--url-pattern")
    inspect_parser.add_argument("--skip-open", action="store_true", help="Assume target chat is already open on the selected tab.")
    _add_bool_choice(
        inspect_parser,
        "--active",
        dest="active",
        help_true="Prefer active tab when browser target is implicit.",
        help_false="Do not force active tab preference in browser target.",
    )
    inspect_parser.add_argument("--dry-run", action="store_true")
    inspect_parser.set_defaults(func=command_inspect_chat)

    add_contact_parser = subparsers.add_parser(
        "add-contact",
        help="Try to add exactly one consented contact through Telegram Web Add Members UI.",
    )
    add_contact_parser.add_argument("--job-dir", required=True)
    add_contact_parser.add_argument("--username", required=True)
    add_contact_parser.add_argument("--search-query", help="Override Add Members search query; default is username without @.")
    add_contact_parser.add_argument("--client-id")
    add_contact_parser.add_argument("--tab-id", type=int)
    add_contact_parser.add_argument("--url-pattern")
    add_contact_parser.add_argument("--execution-id")
    add_contact_parser.add_argument("--search-wait", type=float, default=3.0)
    add_contact_parser.add_argument("--confirm-wait", type=float, default=1.0)
    add_contact_parser.add_argument("--result-wait", type=float, default=5.0)
    add_contact_parser.add_argument("--skip-open", action="store_true", help="Assume target chat is already open on the selected tab.")
    add_contact_parser.add_argument(
        "--allow-first-result",
        action="store_true",
        help="Allow selecting the first search result when Telegram returns multiple candidates.",
    )
    add_contact_parser.add_argument(
        "--confirm-add",
        action="store_true",
        help="Click the final Telegram Add confirmation. Without this flag the command stops before the external add action.",
    )
    add_contact_parser.add_argument(
        "--record-result",
        action="store_true",
        help="When final Add was clicked and no visible error was detected, move user to requested or joined if verification confirms member-count growth.",
    )
    _add_bool_choice(
        add_contact_parser,
        "--verify-membership",
        dest="verify_membership",
        help_true="Capture inspect-chat style snapshots before/after live add and confirm joined only on a strong signal.",
        help_false="Skip automatic before/after membership verification and keep the older requested-only confirmation path.",
    )
    add_contact_parser.add_argument(
        "--verify-wait",
        type=float,
        default=10.0,
        help="Seconds to wait before a delayed after-check when member count did not grow immediately.",
    )
    _add_bool_choice(
        add_contact_parser,
        "--active",
        dest="active",
        help_true="Prefer active tab when browser target is implicit.",
        help_false="Do not force active tab preference in browser target.",
    )
    add_contact_parser.add_argument("--dry-run", action="store_true")
    add_contact_parser.set_defaults(func=command_add_contact)

    record_parser = subparsers.add_parser("record", help="Record execution result and update user statuses.")
    record_parser.add_argument("--job-dir", required=True)
    record_parser.add_argument("--username", action="append", required=True)
    record_parser.add_argument("--status", required=True)
    record_parser.add_argument("--reason", default="execution_record")
    record_parser.add_argument("--execution-id")
    record_parser.set_defaults(func=command_record)

    report_parser = subparsers.add_parser("report", help="Show execution config, recent plans and next batch preview.")
    report_parser.add_argument("--job-dir", required=True)
    report_parser.add_argument("--limit", type=int, default=5)
    report_parser.set_defaults(func=command_report)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
