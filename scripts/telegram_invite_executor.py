#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.telegram_invite_manager import (
        DEFAULT_SELECTABLE_STATUSES,
        append_history,
        atomic_write_json,
        ensure_valid_status,
        load_state,
        normalize_username,
        now_utc,
        save_state,
        select_candidates,
        summarize_state,
    )
except ImportError:
    from telegram_invite_manager import (  # type: ignore
        DEFAULT_SELECTABLE_STATUSES,
        append_history,
        atomic_write_json,
        ensure_valid_status,
        load_state,
        normalize_username,
        now_utc,
        save_state,
        select_candidates,
        summarize_state,
    )


DEFAULT_MESSAGE_TEMPLATE = "Привет! Вот ссылка для вступления в чат: {invite_link}"
DEFAULT_EXECUTION_STATUSES = ("checked",)
MEMBER_COUNT_RE = re.compile(r"(?P<count>\d[\d\s,.]*)\s+members?\b", re.IGNORECASE)
ADD_MEMBERS_OPEN_SELECTORS = (
    "#column-right .profile-container.can-add-members button.btn-circle.btn-corner",
    "#column-right .profile-container.can-add-members button.btn-circle",
    ".profile-container.can-add-members button.btn-circle.btn-corner",
)
ADD_MEMBERS_SEARCH_SELECTOR = ".add-members-container .selector-search-input"
ADD_MEMBERS_CONFIRM_SELECTOR = ".add-members-container > .sidebar-content > button.btn-circle.btn-corner"
ADD_MEMBERS_POPUP_ADD_SELECTOR = ".popup-add-members .popup-buttons button:nth-child(1)"
ADD_MEMBERS_CLOSE_SELECTOR = ".add-members-container .sidebar-close-button"


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
    return execution


def _bool_flag(value: bool | None, *, default: bool) -> bool:
    if value is None:
        return bool(default)
    return bool(value)


def _nonempty(value: Any) -> str:
    return str(value or "").strip()


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
) -> dict[str, Any]:
    execution = _execution_state(payload)
    browser_target = execution["browser_target"]

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
) -> dict[str, Any]:
    execution = dict(_execution_state(payload))
    browser_target = dict(execution.get("browser_target") or {})
    execution["browser_target"] = browser_target

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
    invite_link = _nonempty(execution.get("invite_link"))
    message_template = _nonempty(execution.get("message_template")) or DEFAULT_MESSAGE_TEMPLATE
    chat_url = _nonempty(payload.get("chat_url"))
    requires_approval = bool(execution.get("requires_approval", True))
    action = "share_invite_link" if invite_link else "prepare_invite_link"
    planned = []
    for row in selected:
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
        planned.append(plan_row)
    return planned


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
    command.extend(["new-tab", chat_url])
    return command


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
            "Не отправляйте ссылку пользователям без consent=yes в invite_state.json.",
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

    page_url_result = run_step("page_url", _browser_action_command(browser_target, "page-url"))
    text_result = run_step("read_text", _browser_action_command(browser_target, "text", "body"))
    html_result = run_step("read_html", _browser_action_command(browser_target, "html", "body"), required=False)

    page_url = _browser_payload_text(page_url_result, "url")
    body_text = _browser_payload_text(text_result, "text")
    body_html = _browser_payload_text(html_result, "html")
    member_count, member_count_text = _extract_member_count(body_text)
    response = {
        "status": "completed",
        "job_dir": str(job_dir),
        "chat_url": str(payload.get("chat_url") or ""),
        "page_url": page_url,
        "member_count": member_count,
        "member_count_text": member_count_text,
        "add_members_visible": ("Add Members" in body_text) or ("can-add-members" in body_html),
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
    log_lines = [
        f"INFO: add-contact started execution_id={execution_id}",
        f"INFO: username={username} search_query={search_query}",
        f"INFO: confirm_add={int(bool(args.confirm_add))} record_result={int(bool(args.record_result))}",
    ]
    steps: list[dict[str, Any]] = []
    selected_candidate: dict[str, str] | None = None
    outcome = "dry_run" if args.dry_run else "started"
    record_update: dict[str, str] | None = None

    def run_step(label: str, command: list[str], *, required: bool = True) -> dict[str, Any]:
        if args.dry_run:
            result = {"label": label, "command": command, "dry_run": True, "returncode": 0, "stdout_json": {}}
        else:
            result = {"label": label, **_run_browser_json(repo_root, command)}
        steps.append(result)
        if required and int(result.get("returncode", 1) or 0) != 0:
            raise RuntimeError(f"{label} failed: {result.get('stderr') or result.get('stdout')}")
        return result

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
                    outcome = "confirmed_unverified"
                    if args.record_result:
                        record_update = _record_user_status(
                            job_dir,
                            payload,
                            user,
                            status="requested",
                            reason="live_add_members_confirmed_unverified",
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
    summary["job_dir"] = str(job_dir)
    summary["execution"] = _resolved_execution_config(payload)
    summary["latest_execution_plans"] = executions
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
        help="When final Add was clicked and no visible error was detected, move user to requested.",
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
