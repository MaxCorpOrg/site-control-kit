#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_VERSION = 1
DEFAULT_OUTPUT_ROOT = Path.home() / "telegram_invite_jobs"
DEFAULT_SELECTABLE_STATUSES = ("new",)
ALLOWED_STATUSES = (
    "new",
    "checked",
    "invite_link_created",
    "sent",
    "requested",
    "approved",
    "joined",
    "skipped",
    "failed",
)
USERNAME_RE = re.compile(r"^@?[A-Za-z0-9_]{5,32}$")


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def chat_slug_from_chat_url(chat_url: str) -> str:
    fragment = str(chat_url or "").split("#", 1)[1] if "#" in str(chat_url or "") else str(chat_url or "")
    fragment = fragment or "chat"
    return re.sub(r"[^A-Za-z0-9._-]", "_", fragment)


def job_dir_for(chat_url: str, output_root: Path) -> Path:
    return output_root / f"chat_{chat_slug_from_chat_url(chat_url)}"


def normalize_username(value: str) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if not USERNAME_RE.fullmatch(raw):
        return None
    username = raw if raw.startswith("@") else f"@{raw}"
    return username.lower()


def parse_consent(value: Any) -> bool:
    normalized = str(value or "").strip().lower()
    return normalized in {"1", "true", "yes", "y", "да", "ok"}


def load_input_rows(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            return [dict(row) for row in reader]
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            users = payload.get("users")
            if isinstance(users, list):
                return [dict(row) for row in users if isinstance(row, dict)]
        if isinstance(payload, list):
            return [dict(row) for row in payload if isinstance(row, dict)]
    raise ValueError(f"unsupported input format: {path}")


def build_user_record(row: dict[str, Any], imported_at: str) -> tuple[dict[str, Any] | None, str | None]:
    username = normalize_username(row.get("username", ""))
    if not username:
        return None, "invalid_username"
    consent = parse_consent(row.get("consent"))
    note = str(row.get("note") or "").strip()
    source = str(row.get("source") or "").strip()
    display_name = str(row.get("display_name") or "").strip()
    status = "new" if consent else "skipped"
    history = []
    if not consent:
        history.append(
            {
                "at": imported_at,
                "from_status": "",
                "to_status": "skipped",
                "reason": "init_no_consent",
            }
        )
    return (
        {
            "username": username,
            "display_name": display_name,
            "consent": bool(consent),
            "status": status,
            "last_attempt_at": "",
            "attempts": 0,
            "note": note,
            "source": source,
            "history": history,
        },
        None,
    )


def prepare_users(rows: list[dict[str, Any]], imported_at: str) -> tuple[list[dict[str, Any]], dict[str, int]]:
    users: list[dict[str, Any]] = []
    stats = {
        "rows_total": len(rows),
        "imported": 0,
        "duplicates": 0,
        "invalid_username": 0,
        "consent_yes": 0,
        "consent_no": 0,
    }
    seen: set[str] = set()
    for row in rows:
        record, error = build_user_record(row, imported_at)
        if error:
            stats[error] = stats.get(error, 0) + 1
            continue
        assert record is not None
        username = record["username"]
        if username in seen:
            stats["duplicates"] += 1
            continue
        seen.add(username)
        stats["imported"] += 1
        if record["consent"]:
            stats["consent_yes"] += 1
        else:
            stats["consent_no"] += 1
        users.append(record)
    return users, stats


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def state_path_for(job_dir: Path) -> Path:
    return job_dir / "invite_state.json"


def load_state(job_dir: Path) -> dict[str, Any]:
    path = state_path_for(job_dir)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid state payload: {path}")
    if not isinstance(payload.get("users"), list):
        raise ValueError(f"state missing users list: {path}")
    return payload


def save_state(job_dir: Path, payload: dict[str, Any]) -> None:
    payload = dict(payload)
    payload["updated_at"] = now_utc()
    atomic_write_json(state_path_for(job_dir), payload)


def ensure_valid_status(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized not in ALLOWED_STATUSES:
        raise ValueError(f"unsupported status: {status}")
    return normalized


def summarize_state(payload: dict[str, Any]) -> dict[str, Any]:
    users = [row for row in payload.get("users") or [] if isinstance(row, dict)]
    counts = Counter(str(row.get("status") or "") for row in users)
    return {
        "chat_url": str(payload.get("chat_url") or ""),
        "chat_slug": str(payload.get("chat_slug") or ""),
        "source_file": str(payload.get("source_file") or ""),
        "total_users": len(users),
        "consent_yes": sum(1 for row in users if bool(row.get("consent"))),
        "consent_no": sum(1 for row in users if not bool(row.get("consent"))),
        "counts": dict(sorted(counts.items())),
    }


def select_candidates(payload: dict[str, Any], limit: int, statuses: list[str] | tuple[str, ...] | None = None) -> list[dict[str, Any]]:
    allowed = tuple(ensure_valid_status(item) for item in (statuses or DEFAULT_SELECTABLE_STATUSES))
    candidates = [
        row
        for row in payload.get("users") or []
        if isinstance(row, dict) and bool(row.get("consent")) and str(row.get("status") or "") in allowed
    ]
    candidates.sort(key=lambda row: (int(row.get("attempts", 0) or 0), str(row.get("username") or "")))
    return candidates[: max(int(limit), 0)]


def append_history(user: dict[str, Any], from_status: str, to_status: str, reason: str, at: str) -> None:
    history = user.get("history")
    if not isinstance(history, list):
        history = []
        user["history"] = history
    history.append(
        {
            "at": at,
            "from_status": from_status,
            "to_status": to_status,
            "reason": reason,
        }
    )


def write_run_artifacts(job_dir: Path, run_payload: dict[str, Any], log_lines: list[str]) -> Path:
    run_id = str(run_payload.get("run_id") or now_utc().replace(":", "").replace("-", ""))
    runs_dir = job_dir / "runs" / run_id
    runs_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(runs_dir / "invite_run.json", run_payload)
    (runs_dir / "invite.log").write_text("\n".join(log_lines) + ("\n" if log_lines else ""), encoding="utf-8")
    return runs_dir


def command_init(args: argparse.Namespace) -> int:
    input_path = Path(args.input).expanduser().resolve()
    output_root = Path(args.output_root).expanduser()
    imported_at = now_utc()
    rows = load_input_rows(input_path)
    users, import_stats = prepare_users(rows, imported_at)
    job_dir = Path(args.job_dir).expanduser() if args.job_dir else job_dir_for(args.chat_url, output_root)
    job_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "version": STATE_VERSION,
        "chat_url": args.chat_url,
        "chat_slug": chat_slug_from_chat_url(args.chat_url),
        "created_at": imported_at,
        "updated_at": imported_at,
        "source_file": str(input_path),
        "users": users,
        "import_stats": import_stats,
    }
    save_state(job_dir, state)
    summary = summarize_state(state)
    summary.update({"job_dir": str(job_dir), "state_path": str(state_path_for(job_dir)), "import_stats": import_stats})
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def command_status(args: argparse.Namespace) -> int:
    payload = load_state(Path(args.job_dir).expanduser())
    summary = summarize_state(payload)
    summary["job_dir"] = str(Path(args.job_dir).expanduser())
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def command_next(args: argparse.Namespace) -> int:
    payload = load_state(Path(args.job_dir).expanduser())
    candidates = select_candidates(payload, args.limit, args.statuses)
    response = {
        "job_dir": str(Path(args.job_dir).expanduser()),
        "limit": int(args.limit),
        "selected": len(candidates),
        "users": candidates,
    }
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0


def command_run(args: argparse.Namespace) -> int:
    job_dir = Path(args.job_dir).expanduser()
    payload = load_state(job_dir)
    candidates = select_candidates(payload, args.limit, args.statuses)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    selected_statuses = [ensure_valid_status(item) for item in (args.statuses or DEFAULT_SELECTABLE_STATUSES)]
    target_status = ensure_valid_status(args.to_status)
    at = now_utc()
    results = []
    log_lines = [
        f"INFO: invite run started run_id={run_id}",
        f"INFO: selected {len(candidates)} users from statuses={','.join(selected_statuses)} target={target_status} dry_run={int(bool(args.dry_run))}",
    ]
    users_by_username = {
        str(row.get("username") or ""): row
        for row in payload.get("users") or []
        if isinstance(row, dict)
    }
    for candidate in candidates:
        username = str(candidate.get("username") or "")
        current = users_by_username[username]
        from_status = str(current.get("status") or "")
        reason = "dry_run_selected" if args.dry_run else "batch_progress"
        result = {
            "username": username,
            "from_status": from_status,
            "to_status": target_status,
            "reason": reason,
        }
        results.append(result)
        log_lines.append(f"INFO: {username} {from_status} -> {target_status} ({reason})")
        if args.dry_run:
            continue
        current["status"] = target_status
        current["last_attempt_at"] = at
        current["attempts"] = int(current.get("attempts", 0) or 0) + 1
        append_history(current, from_status, target_status, reason, at)

    if not args.dry_run:
        save_state(job_dir, payload)

    run_payload = {
        "status": "completed",
        "job_dir": str(job_dir),
        "run_id": run_id,
        "limit": int(args.limit),
        "dry_run": bool(args.dry_run),
        "selected_users": len(candidates),
        "processed": len(results),
        "updated": 0 if args.dry_run else len(results),
        "from_statuses": selected_statuses,
        "target_status": target_status,
        "results": results,
    }
    run_dir = write_run_artifacts(job_dir, run_payload, log_lines)
    run_payload["run_dir"] = str(run_dir)
    print(json.dumps(run_payload, ensure_ascii=False, indent=2))
    return 0


def command_mark(args: argparse.Namespace) -> int:
    job_dir = Path(args.job_dir).expanduser()
    payload = load_state(job_dir)
    target_status = ensure_valid_status(args.status)
    requested = [normalize_username(value) for value in args.username]
    requested = [value for value in requested if value]
    users_by_username = {
        str(row.get("username") or ""): row
        for row in payload.get("users") or []
        if isinstance(row, dict)
    }
    at = now_utc()
    updated = []
    missing = []
    for username in requested:
        current = users_by_username.get(username)
        if current is None:
            missing.append(username)
            continue
        from_status = str(current.get("status") or "")
        current["status"] = target_status
        current["last_attempt_at"] = at
        current["attempts"] = int(current.get("attempts", 0) or 0) + 1
        append_history(current, from_status, target_status, args.reason, at)
        updated.append({"username": username, "from_status": from_status, "to_status": target_status})
    save_state(job_dir, payload)
    print(
        json.dumps(
            {
                "job_dir": str(job_dir),
                "updated": updated,
                "missing": missing,
                "reason": args.reason,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def command_report(args: argparse.Namespace) -> int:
    job_dir = Path(args.job_dir).expanduser()
    payload = load_state(job_dir)
    summary = summarize_state(payload)
    runs_dir = job_dir / "runs"
    latest_runs = []
    if runs_dir.exists():
        for path in sorted(runs_dir.glob("*/invite_run.json"))[-5:]:
            try:
                run_payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            latest_runs.append(
                {
                    "run_id": str(run_payload.get("run_id") or ""),
                    "status": str(run_payload.get("status") or ""),
                    "dry_run": bool(run_payload.get("dry_run")),
                    "processed": int(run_payload.get("processed", 0) or 0),
                    "updated": int(run_payload.get("updated", 0) or 0),
                    "path": str(path),
                }
            )
    summary["job_dir"] = str(job_dir)
    summary["latest_runs"] = latest_runs
    summary["next_default_batch"] = select_candidates(payload, args.limit, DEFAULT_SELECTABLE_STATUSES)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Telegram Invite Manager: safe stateful manager for consent-based invite workflows.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create a new invite job from CSV or JSON input.")
    init_parser.add_argument("--chat-url", required=True)
    init_parser.add_argument("--input", required=True)
    init_parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    init_parser.add_argument("--job-dir")
    init_parser.set_defaults(func=command_init)

    status_parser = subparsers.add_parser("status", help="Show aggregate job status.")
    status_parser.add_argument("--job-dir", required=True)
    status_parser.set_defaults(func=command_status)

    next_parser = subparsers.add_parser("next", help="Return next consented users for processing.")
    next_parser.add_argument("--job-dir", required=True)
    next_parser.add_argument("--limit", type=int, default=3)
    next_parser.add_argument("--statuses", nargs="*", default=list(DEFAULT_SELECTABLE_STATUSES))
    next_parser.set_defaults(func=command_next)

    run_parser = subparsers.add_parser("run", help="Process next batch and write run artifacts.")
    run_parser.add_argument("--job-dir", required=True)
    run_parser.add_argument("--limit", type=int, default=3)
    run_parser.add_argument("--statuses", nargs="*", default=list(DEFAULT_SELECTABLE_STATUSES))
    run_parser.add_argument("--to-status", default="checked")
    run_parser.add_argument("--dry-run", action="store_true")
    run_parser.set_defaults(func=command_run)

    mark_parser = subparsers.add_parser("mark", help="Set an explicit status for one or more usernames.")
    mark_parser.add_argument("--job-dir", required=True)
    mark_parser.add_argument("--username", action="append", required=True)
    mark_parser.add_argument("--status", required=True)
    mark_parser.add_argument("--reason", default="manual_mark")
    mark_parser.set_defaults(func=command_mark)

    report_parser = subparsers.add_parser("report", help="Show job summary and recent runs.")
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
