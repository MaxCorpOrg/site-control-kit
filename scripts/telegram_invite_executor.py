#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
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
