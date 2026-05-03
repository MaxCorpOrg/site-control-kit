from __future__ import annotations

from collections import Counter
import csv
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_INVITE_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "telegram_invite_manager.py"
DEFAULT_INVITE_EXECUTOR_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "telegram_invite_executor.py"
DEFAULT_INVITE_OUTPUT_ROOT = Path.home() / "telegram_invite_jobs"
DEFAULT_SESSION_REPO = Path("/home/max/telegram-portable-session-tool")
DEFAULT_SESSION_CONFIG = DEFAULT_SESSION_REPO / "examples" / "session.example.json"
DEFAULT_SESSION_STATE_FILE = DEFAULT_SESSION_REPO / ".state" / "session_state.json"
DEFAULT_SESSION_RUNS_DIR = DEFAULT_SESSION_REPO / "runs"
USERNAME_RE = re.compile(r"^@?[A-Za-z0-9_]{5,32}$")
CONTACT_PENDING_STATUSES = {"new", "checked"}
CONTACT_SUCCESS_STATUSES = {"contact_added"}
CONTACT_ERROR_STATUSES = {"failed"}


@dataclass(frozen=True)
class CommandSpec:
    argv: list[str]
    cwd: Path


def _load_json_file(path: str | Path) -> Any:
    return json.loads(Path(path).expanduser().resolve().read_text(encoding="utf-8"))


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_json_payload(stdout: str) -> dict[str, Any]:
    payload = json.loads(stdout)
    if not isinstance(payload, dict):
        raise RuntimeError("command returned unexpected JSON payload")
    return payload


def run_json_command(argv: list[str], *, cwd: str | Path | None = None) -> dict[str, Any]:
    completed = subprocess.run(
        argv,
        cwd=str(cwd) if cwd is not None else None,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(detail or f"command failed with code {completed.returncode}")
    return parse_json_payload(completed.stdout)


def chat_slug_from_chat_url(chat_url: str) -> str:
    fragment = str(chat_url or "").split("#", 1)[1] if "#" in str(chat_url or "") else str(chat_url or "")
    fragment = fragment or "chat"
    return re.sub(r"[^A-Za-z0-9._-]", "_", fragment)


def default_invite_job_dir(chat_url: str, output_root: str | Path = DEFAULT_INVITE_OUTPUT_ROOT) -> Path:
    return Path(output_root).expanduser().resolve() / f"chat_{chat_slug_from_chat_url(chat_url)}"


def _safe_slug(value: str, fallback: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]", "_", str(value or "").strip())
    slug = slug.strip("._-")
    return slug or fallback


def default_contact_add_job_dir(
    *,
    profile_name: str,
    input_path: str | Path,
    output_root: str | Path = DEFAULT_INVITE_OUTPUT_ROOT,
) -> Path:
    input_stem = Path(input_path).expanduser().resolve().stem if str(input_path or "").strip() else "list"
    profile_slug = _safe_slug(profile_name, "profile")
    input_slug = _safe_slug(input_stem, "list")
    return Path(output_root).expanduser().resolve() / f"contact_add__{profile_slug}__{input_slug}"


def contact_add_chat_url(*, profile_name: str, account_username: str = "") -> str:
    identity = _safe_slug(account_username or profile_name, "profile")
    return f"contacts://{identity}"


def parse_plaintext_usernames(text: str) -> list[str]:
    usernames: list[str] = []
    seen: set[str] = set()
    for raw_line in str(text or "").splitlines():
        candidate = raw_line.strip()
        if not candidate or candidate.startswith("#"):
            continue
        if not USERNAME_RE.fullmatch(candidate):
            raise ValueError(f"invalid username in txt list: {candidate}")
        normalized = candidate if candidate.startswith("@") else f"@{candidate}"
        normalized = normalized.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        usernames.append(normalized)
    return usernames


def preview_invite_input_file(source_path: str | Path) -> dict[str, Any]:
    path = Path(source_path).expanduser().resolve()
    suffix = path.suffix.lower()
    unique_usernames: list[str] = []
    seen: set[str] = set()
    duplicates = 0
    invalid_entries: list[str] = []
    rows_total = 0

    def _register_username(raw_value: Any) -> None:
        nonlocal duplicates, rows_total
        rows_total += 1
        candidate = str(raw_value or "").strip()
        if not candidate or candidate.startswith("#"):
            return
        if not USERNAME_RE.fullmatch(candidate):
            invalid_entries.append(candidate)
            return
        normalized = candidate if candidate.startswith("@") else f"@{candidate}"
        normalized = normalized.lower()
        if normalized in seen:
            duplicates += 1
            return
        seen.add(normalized)
        unique_usernames.append(normalized)

    if suffix == ".txt":
        for line in path.read_text(encoding="utf-8").splitlines():
            _register_username(line)
    elif suffix == ".csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                _register_username((row or {}).get("username"))
    elif suffix == ".json":
        payload = _load_json_file(path)
        if isinstance(payload, dict):
            raw_items = payload.get("users")
        else:
            raw_items = payload
        if not isinstance(raw_items, list):
            raise ValueError("json input must contain a list or object with users[]")
        for item in raw_items:
            if isinstance(item, dict):
                _register_username(item.get("username"))
    else:
        raise ValueError("supported invite input formats: .txt, .csv, .json")

    return {
        "status": "ready",
        "path": str(path),
        "format": suffix.lstrip(".") or "unknown",
        "rows_total": rows_total,
        "unique_usernames": len(unique_usernames),
        "duplicates": duplicates,
        "invalid_count": len(invalid_entries),
        "invalid_entries": invalid_entries[:10],
        "usernames": unique_usernames[:20],
    }


def _iter_contact_batch_runs(job_dir: str | Path, *, history_limit: int) -> list[dict[str, Any]]:
    executions_dir = Path(job_dir).expanduser().resolve() / "executions"
    if not executions_dir.exists():
        return []
    history: list[dict[str, Any]] = []
    for path in sorted(executions_dir.glob("*/batch_contact_add.json"))[-history_limit:]:
        try:
            payload = _load_json_file(path)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        history.append(
            {
                "execution_id": str(payload.get("execution_id") or path.parent.name),
                "status": str(payload.get("status") or ""),
                "added_count": _safe_int(payload.get("added_count")),
                "failed_count": _safe_int(payload.get("failed_count")),
                "remaining_candidates": _safe_int(payload.get("remaining_candidates")),
                "selected_users": _safe_int(payload.get("selected_users")),
                "run_dir": str(payload.get("run_dir") or path.parent),
                "path": str(path),
            }
        )
    return history


def contact_job_snapshot(
    job_dir: str | Path,
    *,
    queue_limit: int = 12,
    history_limit: int = 8,
) -> dict[str, Any]:
    resolved_job_dir = Path(job_dir).expanduser().resolve()
    state_path = resolved_job_dir / "invite_state.json"
    if not state_path.exists():
        return {
            "status": "missing",
            "job_dir": str(resolved_job_dir),
            "state_path": str(state_path),
        }

    payload = _load_json_file(state_path)
    if not isinstance(payload, dict):
        raise ValueError("invite_state.json must contain an object")
    users = [row for row in payload.get("users") or [] if isinstance(row, dict)]
    counts = Counter(str(row.get("status") or "") for row in users)
    pending_users = [str(row.get("username") or "") for row in users if str(row.get("status") or "") in CONTACT_PENDING_STATUSES]
    added_users = [str(row.get("username") or "") for row in users if str(row.get("status") or "") in CONTACT_SUCCESS_STATUSES]
    failed_rows = [row for row in users if str(row.get("status") or "") in CONTACT_ERROR_STATUSES]
    failed_users = [str(row.get("username") or "") for row in failed_rows]
    failed_details = [
        {
            "username": str(row.get("username") or ""),
            "attempts": _safe_int(row.get("attempts")),
            "last_attempt_at": str(row.get("last_attempt_at") or ""),
            "last_reason": str((row.get("history") or [{}])[-1].get("reason") or "")
            if isinstance(row.get("history"), list) and row.get("history")
            else "",
        }
        for row in failed_rows[:queue_limit]
    ]
    latest_runs = _iter_contact_batch_runs(resolved_job_dir, history_limit=history_limit)
    latest_errors: list[dict[str, Any]] = []
    if latest_runs:
        latest_run_path = Path(latest_runs[-1]["path"])
        try:
            latest_payload = _load_json_file(latest_run_path)
        except (OSError, json.JSONDecodeError):
            latest_payload = {}
        if isinstance(latest_payload, dict):
            for item in latest_payload.get("results") or []:
                if not isinstance(item, dict):
                    continue
                if str(item.get("status") or "").strip().lower() == "failed" or str(item.get("returncode") or "") not in {"", "0"}:
                    latest_errors.append(
                        {
                            "username": str(item.get("username") or ""),
                            "error": str(item.get("error") or ""),
                            "outcome": str(item.get("outcome") or ""),
                            "run_dir": str(item.get("run_dir") or ""),
                        }
                    )
            latest_errors = latest_errors[:queue_limit]

    return {
        "status": "ready",
        "job_dir": str(resolved_job_dir),
        "state_path": str(state_path),
        "chat_url": str(payload.get("chat_url") or ""),
        "source_file": str(payload.get("source_file") or ""),
        "updated_at": str(payload.get("updated_at") or ""),
        "total_users": len(users),
        "counts": dict(sorted(counts.items())),
        "pending_total": len(pending_users),
        "added_total": len(added_users),
        "failed_total": len(failed_users),
        "pending_usernames": pending_users[:queue_limit],
        "added_usernames": added_users[-queue_limit:],
        "failed_usernames": failed_users[:queue_limit],
        "failed_details": failed_details,
        "latest_runs": latest_runs,
        "latest_errors": latest_errors,
    }


def prepare_invite_input_file(source_path: str | Path, temp_dir: str | Path) -> Path:
    path = Path(source_path).expanduser().resolve()
    if path.suffix.lower() in {".csv", ".json"}:
        return path
    if path.suffix.lower() != ".txt":
        raise ValueError("supported invite input formats: .txt, .csv, .json")

    usernames = parse_plaintext_usernames(path.read_text(encoding="utf-8"))
    output_path = Path(temp_dir).expanduser().resolve() / f"{path.stem}.invite-import.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["username", "consent", "source"])
        writer.writeheader()
        for username in usernames:
            writer.writerow(
                {
                    "username": username,
                    "consent": "yes",
                    "source": "panel_txt_import",
                }
            )
    return output_path


def invite_manager_init(
    *,
    chat_url: str,
    input_path: str | Path,
    job_dir: str | Path | None = None,
    output_root: str | Path = DEFAULT_INVITE_OUTPUT_ROOT,
    temp_dir: str | Path = "/tmp/telegram-control-center",
) -> dict[str, Any]:
    spec = invite_manager_init_command(
        chat_url=chat_url,
        input_path=input_path,
        job_dir=job_dir,
        output_root=output_root,
        temp_dir=temp_dir,
    )
    return run_json_command(spec.argv, cwd=spec.cwd)


def invite_manager_init_command(
    *,
    chat_url: str,
    input_path: str | Path,
    job_dir: str | Path | None = None,
    output_root: str | Path = DEFAULT_INVITE_OUTPUT_ROOT,
    temp_dir: str | Path = "/tmp/telegram-control-center",
) -> CommandSpec:
    prepared_input = prepare_invite_input_file(input_path, temp_dir)
    argv = [
        "python3",
        str(DEFAULT_INVITE_SCRIPT),
        "init",
        "--chat-url",
        chat_url,
        "--input",
        str(prepared_input),
        "--output-root",
        str(Path(output_root).expanduser().resolve()),
    ]
    if job_dir:
        argv.extend(["--job-dir", str(Path(job_dir).expanduser().resolve())])
    return CommandSpec(argv=argv, cwd=DEFAULT_INVITE_SCRIPT.parent.parent)


def invite_manager_status(job_dir: str | Path) -> dict[str, Any]:
    spec = invite_manager_status_command(job_dir)
    return run_json_command(spec.argv, cwd=spec.cwd)


def invite_manager_status_command(job_dir: str | Path) -> CommandSpec:
    return CommandSpec(
        argv=[
            "python3",
            str(DEFAULT_INVITE_SCRIPT),
            "status",
            "--job-dir",
            str(Path(job_dir).expanduser().resolve()),
        ],
        cwd=DEFAULT_INVITE_SCRIPT.parent.parent,
    )


def invite_manager_next(job_dir: str | Path, *, limit: int = 10) -> dict[str, Any]:
    spec = invite_manager_next_command(job_dir, limit=limit)
    return run_json_command(spec.argv, cwd=spec.cwd)


def invite_manager_next_command(job_dir: str | Path, *, limit: int = 10) -> CommandSpec:
    return CommandSpec(
        argv=[
            "python3",
            str(DEFAULT_INVITE_SCRIPT),
            "next",
            "--job-dir",
            str(Path(job_dir).expanduser().resolve()),
            "--limit",
            str(max(int(limit), 1)),
        ],
        cwd=DEFAULT_INVITE_SCRIPT.parent.parent,
    )


def contact_add_batch_command(
    *,
    input_path: str | Path | None,
    job_dir: str | Path,
    profile_name: str,
    portable_profile_dir: str | Path,
    account_username: str = "",
    account_label: str = "",
    limit: int = 0,
    output_root: str | Path = DEFAULT_INVITE_OUTPUT_ROOT,
    temp_dir: str | Path = "/tmp/telegram-control-center",
    launch_if_needed: bool = True,
    confirm_add: bool = True,
    dry_run: bool = False,
    statuses: list[str] | tuple[str, ...] | None = None,
) -> CommandSpec:
    resolved_job_dir = Path(job_dir).expanduser().resolve()
    argv = [
        "python3",
        str(DEFAULT_INVITE_EXECUTOR_SCRIPT),
        "desktop-add-contact-batch",
        "--job-dir",
        str(resolved_job_dir),
        "--chat-url",
        contact_add_chat_url(profile_name=profile_name, account_username=account_username),
        "--portable-profile-name",
        str(profile_name or "").strip(),
        "--portable-profile-dir",
        str(Path(portable_profile_dir).expanduser().resolve()),
        "--output-root",
        str(Path(output_root).expanduser().resolve()),
    ]
    if input_path is not None and str(input_path).strip():
        prepared_input = prepare_invite_input_file(input_path, temp_dir)
        argv.extend(["--input", str(prepared_input)])
    if account_username:
        argv.extend(["--account-username", str(account_username).strip()])
    if account_label:
        argv.extend(["--account-label", str(account_label).strip()])
    if limit > 0:
        argv.extend(["--limit", str(int(limit))])
    if statuses:
        argv.extend(["--statuses", *[str(item).strip() for item in statuses if str(item).strip()]])
    if launch_if_needed:
        argv.append("--launch-if-needed")
    if confirm_add:
        argv.append("--confirm-add")
    if dry_run:
        argv.append("--dry-run")
    return CommandSpec(argv=argv, cwd=DEFAULT_INVITE_EXECUTOR_SCRIPT.parent.parent)


def load_session_config_payload(config_path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(config_path).expanduser().resolve().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("session config must contain a JSON object")
    return payload


def _as_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _as_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def session_message_targets(config_path: str | Path) -> list[dict[str, Any]]:
    payload = load_session_config_payload(config_path)
    message_policy = payload.get("message_policy")
    if not isinstance(message_policy, dict):
        return []
    raw_targets = message_policy.get("message_targets")
    if not isinstance(raw_targets, list):
        return []
    return [dict(item) for item in raw_targets if isinstance(item, dict)]


def session_config_defaults(config_path: str | Path) -> dict[str, Any]:
    payload = load_session_config_payload(config_path)
    session = payload.get("session")
    if not isinstance(session, dict):
        session = {}
    message_policy = payload.get("message_policy")
    if not isinstance(message_policy, dict):
        message_policy = {}
    raw_targets = message_policy.get("message_targets")
    raw_templates = message_policy.get("templates")
    return {
        "message_targets": [dict(item) for item in raw_targets if isinstance(item, dict)] if isinstance(raw_targets, list) else [],
        "templates": [str(item).strip() for item in raw_templates if str(item).strip()] if isinstance(raw_templates, list) else [],
        "auto_send": _as_bool(message_policy.get("auto_send"), default=False),
        "drafts_per_run": _as_int(message_policy.get("drafts_per_run"), default=1),
        "total_message_limit": _as_int(message_policy.get("total_message_limit"), default=0),
        "random_walk_visits_per_run": _as_int(session.get("random_walk_visits_per_run"), default=6),
        "view_min_seconds": _as_int(session.get("view_min_seconds"), default=3),
        "view_max_seconds": _as_int(session.get("view_max_seconds"), default=6),
    }


def format_session_target_label(item: dict[str, Any]) -> str:
    handle = str(item.get("handle") or "").strip()
    label = str(item.get("label") or "").strip() or handle
    kind = str(item.get("kind") or "contact").strip().lower()
    kind_label = "группа" if kind == "group" else "контакт"
    return f"{label} · {handle} · {kind_label}"


def build_session_runtime_config(
    *,
    base_config_path: str | Path,
    output_path: str | Path,
    message_targets: list[dict[str, Any]],
    message_templates: list[str],
    drafts_per_run: int,
    total_message_limit: int,
    portable_profile_dir: str = "",
    auto_send: bool = False,
    session_overrides: dict[str, Any] | None = None,
) -> Path:
    payload = load_session_config_payload(base_config_path)
    payload["portable_profile_dir"] = portable_profile_dir or str(
        payload.get("portable_profile_dir") or ""
    )
    session = payload.get("session")
    if not isinstance(session, dict):
        session = {}
        payload["session"] = session
    message_policy = payload.get("message_policy")
    if not isinstance(message_policy, dict):
        message_policy = {}
        payload["message_policy"] = message_policy

    message_policy["message_targets"] = message_targets
    message_policy["target_username"] = ""
    kinds = {str(item.get("kind") or "contact").strip().lower() for item in message_targets}
    message_policy["target_mode"] = "rotating_all" if "group" in kinds else "rotating_contacts"
    message_policy["templates"] = [str(item).strip() for item in message_templates if str(item).strip()]
    message_policy["drafts_per_run"] = max(0, int(drafts_per_run))
    message_policy["total_message_limit"] = max(0, int(total_message_limit))
    message_policy["auto_send"] = bool(auto_send)
    if isinstance(session_overrides, dict):
        for key, value in session_overrides.items():
            session[key] = value

    resolved_output = Path(output_path).expanduser().resolve()
    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    resolved_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return resolved_output


def session_history_snapshot(
    *,
    state_file: str | Path = DEFAULT_SESSION_STATE_FILE,
    runs_dir: str | Path = DEFAULT_SESSION_RUNS_DIR,
    limit: int = 8,
) -> dict[str, Any]:
    resolved_state = Path(state_file).expanduser().resolve()
    resolved_runs = Path(runs_dir).expanduser().resolve()
    state_payload: dict[str, Any] = {}
    if resolved_state.exists():
        raw_state = _load_json_file(resolved_state)
        if isinstance(raw_state, dict):
            state_payload = raw_state

    history = state_payload.get("history") if isinstance(state_payload.get("history"), list) else []
    latest_runs: list[dict[str, Any]] = []
    if resolved_runs.exists():
        for path in sorted(resolved_runs.glob("*/run.json"))[-limit:]:
            try:
                run_payload = _load_json_file(path)
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(run_payload, dict):
                continue
            messages = run_payload.get("messages") if isinstance(run_payload.get("messages"), list) else []
            sent_count = _safe_int(run_payload.get("sent_count"))
            unsent_messages = [
                {
                    "index": _safe_int(item.get("index")),
                    "text": str(item.get("text") or ""),
                    "sent": bool(item.get("sent")),
                    "send_mode": str(item.get("send_mode") or ""),
                }
                for item in messages
                if isinstance(item, dict) and not bool(item.get("sent"))
            ]
            latest_runs.append(
                {
                    "run_id": str(run_payload.get("run_id") or path.parent.name),
                    "status": str(run_payload.get("status") or ""),
                    "visit_count": len(run_payload.get("visits") or []),
                    "message_count": len(messages),
                    "sent_count": sent_count,
                    "message_target_username": str(
                        ((run_payload.get("plan") or {}) if isinstance(run_payload.get("plan"), dict) else {}).get("message_target_username")
                        or ""
                    ),
                    "run_dir": str(path.parent),
                    "path": str(path),
                    "unsent_messages": unsent_messages[:5],
                }
            )

    last_run = latest_runs[-1] if latest_runs else {}
    return {
        "status": "ready" if resolved_state.exists() or resolved_runs.exists() else "missing",
        "state_file": str(resolved_state),
        "runs_dir": str(resolved_runs),
        "messages_sent_total": _safe_int(state_payload.get("messages_sent_total")),
        "message_cursor": _safe_int(state_payload.get("message_cursor")),
        "message_target_cursor": _safe_int(state_payload.get("message_target_cursor")),
        "history": history[-limit:],
        "latest_runs": latest_runs,
        "last_run": last_run,
    }


def session_plan(
    *,
    config_path: str | Path,
    state_file: str | Path = DEFAULT_SESSION_STATE_FILE,
) -> dict[str, Any]:
    spec = session_plan_command(config_path=config_path, state_file=state_file)
    return run_json_command(spec.argv, cwd=spec.cwd)


def session_plan_command(
    *,
    config_path: str | Path,
    state_file: str | Path = DEFAULT_SESSION_STATE_FILE,
) -> CommandSpec:
    return CommandSpec(
        argv=[
            "python3",
            "-m",
            "telegram_portable_session_tool.cli",
            "plan-session",
            "--config",
            str(Path(config_path).expanduser().resolve()),
            "--state-file",
            str(Path(state_file).expanduser().resolve()),
        ],
        cwd=DEFAULT_SESSION_REPO,
    )


def session_run(
    *,
    config_path: str | Path,
    state_file: str | Path = DEFAULT_SESSION_STATE_FILE,
    runs_dir: str | Path = DEFAULT_SESSION_RUNS_DIR,
    auto_send: bool = False,
    launch_if_needed: bool = True,
    continuous: bool = False,
) -> dict[str, Any]:
    spec = session_run_command(
        config_path=config_path,
        state_file=state_file,
        runs_dir=runs_dir,
        auto_send=auto_send,
        launch_if_needed=launch_if_needed,
        continuous=continuous,
    )
    return run_json_command(spec.argv, cwd=spec.cwd)


def session_run_command(
    *,
    config_path: str | Path,
    state_file: str | Path = DEFAULT_SESSION_STATE_FILE,
    runs_dir: str | Path = DEFAULT_SESSION_RUNS_DIR,
    auto_send: bool = False,
    launch_if_needed: bool = True,
    continuous: bool = False,
) -> CommandSpec:
    argv = [
        "python3",
        "-m",
        "telegram_portable_session_tool.cli",
        "run-session",
        "--config",
        str(Path(config_path).expanduser().resolve()),
        "--state-file",
        str(Path(state_file).expanduser().resolve()),
        "--runs-dir",
        str(Path(runs_dir).expanduser().resolve()),
        "--execute",
    ]
    if launch_if_needed:
        argv.append("--launch-if-needed")
    if auto_send:
        argv.append("--auto-send")
    if continuous:
        argv.append("--continuous")
    return CommandSpec(argv=argv, cwd=DEFAULT_SESSION_REPO)
