from __future__ import annotations

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


@dataclass(frozen=True)
class CommandSpec:
    argv: list[str]
    cwd: Path


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
    input_path: str | Path,
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
) -> CommandSpec:
    prepared_input = prepare_invite_input_file(input_path, temp_dir)
    resolved_job_dir = Path(job_dir).expanduser().resolve()
    argv = [
        "python3",
        str(DEFAULT_INVITE_EXECUTOR_SCRIPT),
        "desktop-add-contact-batch",
        "--job-dir",
        str(resolved_job_dir),
        "--input",
        str(prepared_input),
        "--chat-url",
        contact_add_chat_url(profile_name=profile_name, account_username=account_username),
        "--portable-profile-name",
        str(profile_name or "").strip(),
        "--portable-profile-dir",
        str(Path(portable_profile_dir).expanduser().resolve()),
        "--output-root",
        str(Path(output_root).expanduser().resolve()),
    ]
    if account_username:
        argv.extend(["--account-username", str(account_username).strip()])
    if account_label:
        argv.extend(["--account-label", str(account_label).strip()])
    if limit > 0:
        argv.extend(["--limit", str(int(limit))])
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


def session_message_targets(config_path: str | Path) -> list[dict[str, Any]]:
    payload = load_session_config_payload(config_path)
    message_policy = payload.get("message_policy")
    if not isinstance(message_policy, dict):
        return []
    raw_targets = message_policy.get("message_targets")
    if not isinstance(raw_targets, list):
        return []
    return [dict(item) for item in raw_targets if isinstance(item, dict)]


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
    portable_profile_dir: str = "",
    auto_send: bool = False,
) -> Path:
    if not message_targets:
        raise ValueError("at least one message target is required")
    payload = load_session_config_payload(base_config_path)
    payload["portable_profile_dir"] = portable_profile_dir or str(
        payload.get("portable_profile_dir") or ""
    )
    message_policy = payload.get("message_policy")
    if not isinstance(message_policy, dict):
        message_policy = {}
        payload["message_policy"] = message_policy

    kinds = {str(item.get("kind") or "contact").strip().lower() for item in message_targets}
    target_mode = "rotating_all" if "group" in kinds else "rotating_contacts"
    message_policy["message_targets"] = message_targets
    message_policy["target_mode"] = target_mode
    message_policy["auto_send"] = bool(auto_send)

    resolved_output = Path(output_path).expanduser().resolve()
    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    resolved_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return resolved_output


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
) -> dict[str, Any]:
    spec = session_run_command(
        config_path=config_path,
        state_file=state_file,
        runs_dir=runs_dir,
        auto_send=auto_send,
        launch_if_needed=launch_if_needed,
    )
    return run_json_command(spec.argv, cwd=spec.cwd)


def session_run_command(
    *,
    config_path: str | Path,
    state_file: str | Path = DEFAULT_SESSION_STATE_FILE,
    runs_dir: str | Path = DEFAULT_SESSION_RUNS_DIR,
    auto_send: bool = False,
    launch_if_needed: bool = True,
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
    return CommandSpec(argv=argv, cwd=DEFAULT_SESSION_REPO)
