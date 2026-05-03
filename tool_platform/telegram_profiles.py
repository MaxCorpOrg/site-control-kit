from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path
from typing import Any


DEFAULT_OUTPUT_ROOT = Path.home()
PORTABLE_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "telegram_portable.py"


def _run_json_command(argv: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        argv,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        command = shlex.join(argv)
        raise RuntimeError(f"command failed ({completed.returncode}): {command}\n{detail}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        command = shlex.join(argv)
        raise RuntimeError(f"command returned invalid JSON: {command}") from exc
    if not isinstance(payload, dict):
        command = shlex.join(argv)
        raise RuntimeError(f"command returned unexpected payload: {command}")
    return payload


def _portable_command(*parts: str) -> list[str]:
    return ["python3", str(PORTABLE_SCRIPT_PATH), *parts]


def format_profile_label(profile: dict[str, Any]) -> str:
    account = profile.get("account") if isinstance(profile.get("account"), dict) else {}
    primary = (
        str(account.get("label") or "").strip()
        or str(account.get("username") or "").strip()
        or str(profile.get("profile_name") or "").strip()
        or str(profile.get("profile_dir") or "").strip()
    )
    profile_name = str(profile.get("profile_name") or "").strip()
    if profile_name and profile_name != primary:
        primary = f"{primary} ({profile_name})"
    status = "запущен" if profile.get("running") else "остановлен"
    return f"{primary} [{status}]"


def list_portable_profiles(output_root: str | Path = DEFAULT_OUTPUT_ROOT) -> list[dict[str, Any]]:
    payload = _run_json_command(
        _portable_command("list", "--output-root", str(Path(output_root).expanduser().resolve()))
    )
    raw_profiles = payload.get("profiles")
    if not isinstance(raw_profiles, list):
        raise RuntimeError("portable helper returned invalid profiles list")
    profiles = [item for item in raw_profiles if isinstance(item, dict)]
    return sorted(
        profiles,
        key=lambda item: (
            0 if item.get("running") else 1,
            format_profile_label(item).lower(),
        ),
    )


def get_profile_status(profile_dir: str | Path) -> dict[str, Any]:
    return _run_json_command(
        _portable_command("status", "--profile-dir", str(Path(profile_dir).expanduser().resolve()))
    )


def launch_profile(profile_dir: str | Path) -> dict[str, Any]:
    return _run_json_command(
        _portable_command("launch", "--profile-dir", str(Path(profile_dir).expanduser().resolve()))
    )


def import_tdata_profile(
    *,
    zip_path: str | Path,
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
    profile_name: str = "",
    account_username: str = "",
    account_label: str = "",
    launch: bool = True,
) -> dict[str, Any]:
    argv = _portable_command(
        "import-zip",
        "--zip",
        str(Path(zip_path).expanduser().resolve()),
        "--output-root",
        str(Path(output_root).expanduser().resolve()),
    )
    if profile_name.strip():
        argv.extend(["--profile-name", profile_name.strip()])
    if account_username.strip():
        argv.extend(["--account-username", account_username.strip()])
    if account_label.strip():
        argv.extend(["--account-label", account_label.strip()])
    if launch:
        argv.append("--launch")
    return _run_json_command(argv)


def adopt_existing_profile(
    *,
    profile_dir: str | Path,
    profile_name: str = "",
    account_username: str = "",
    account_label: str = "",
) -> dict[str, Any]:
    argv = _portable_command(
        "adopt",
        "--profile-dir",
        str(Path(profile_dir).expanduser().resolve()),
    )
    if profile_name.strip():
        argv.extend(["--profile-name", profile_name.strip()])
    if account_username.strip():
        argv.extend(["--account-username", account_username.strip()])
    if account_label.strip():
        argv.extend(["--account-label", account_label.strip()])
    return _run_json_command(argv)
