#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from telegram_profiles import (  # noqa: E402
    DEFAULT_PROFILE,
    available_profiles,
    build_profile_env,
    resolve_chain_interval,
    resolve_profile,
    resolve_profile_name,
)


ROOT_DIR = Path(__file__).resolve().parents[1]
COLLECT_SCRIPT = ROOT_DIR / "scripts" / "collect_new_telegram_contacts.sh"


def chat_slug_from_group_url(group_url: str) -> str:
    fragment = str(group_url or "").split("#", 1)[1] if "#" in str(group_url or "") else str(group_url or "")
    fragment = fragment or "chat"
    return re.sub(r"[^A-Za-z0-9._-]", "_", fragment)


def chat_dir_for(group_url: str, output_root: Path) -> Path:
    return output_root / f"chat_{chat_slug_from_group_url(group_url)}"


def latest_run_json(chat_dir: Path) -> Path | None:
    runs_dir = chat_dir / "runs"
    if not runs_dir.exists():
        return None
    candidates = sorted(runs_dir.glob("*/run.json"))
    return candidates[-1] if candidates else None


def load_run_payload(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def should_stop_after_idle(idle_runs: int, stop_after_idle: int) -> bool:
    return stop_after_idle > 0 and idle_runs >= stop_after_idle


def should_stop_after_no_growth(no_growth_runs: int, stop_after_no_growth: int) -> bool:
    return stop_after_no_growth > 0 and no_growth_runs >= stop_after_no_growth


def reached_chain_target(current_value: int, target_value: int) -> bool:
    return target_value > 0 and current_value >= target_value


def is_productive_deep_yield(run_payload: dict[str, Any]) -> bool:
    if not isinstance(run_payload, dict):
        return False
    return bool(int(run_payload.get("chat_deep_yield_stop", 0) or 0)) and int(run_payload.get("deep_updated_total", 0) or 0) > 0


def should_skip_interval_after_run(run_payload: dict[str, Any], skip_on_productive_yield: bool) -> bool:
    if not skip_on_productive_yield:
        return False
    return is_productive_deep_yield(run_payload)


def resolve_interval_sec(explicit_value: float | None, profile_name: str) -> float:
    if explicit_value is not None:
        return max(float(explicit_value), 0.0)
    env_value = os.environ.get("TELEGRAM_CHAIN_INTERVAL_SEC", "").strip()
    if env_value:
        try:
            return max(float(env_value), 0.0)
        except ValueError:
            pass
    return resolve_chain_interval(profile_name)


def build_collect_env(profile_name: str) -> dict[str, str]:
    env = os.environ.copy()
    for key, value in build_profile_env(profile_name).items():
        env.setdefault(str(key), str(value))
    env["TELEGRAM_CHAIN_PROFILE"] = resolve_profile_name(profile_name)
    env.setdefault("CHAT_PROFILE", resolve_profile_name(profile_name))
    return env


def write_chain_summary(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run multiple short Telegram contact collection passes with pauses and shared discovery state."
    )
    parser.add_argument("group_url", help="Telegram group URL")
    parser.add_argument("output_root", nargs="?", default=str(Path.home() / "telegram_contact_batches"))
    parser.add_argument(
        "--profile",
        choices=available_profiles(),
        default=str(os.environ.get("TELEGRAM_CHAIN_PROFILE", DEFAULT_PROFILE) or DEFAULT_PROFILE).strip().lower(),
        help="Preset chain profile for collect-script env and default interval.",
    )
    parser.add_argument("--runs", type=int, default=max(int(os.environ.get("TELEGRAM_CHAIN_RUNS", "5") or "5"), 1))
    parser.add_argument(
        "--interval-sec",
        type=float,
        default=None,
    )
    parser.add_argument(
        "--stop-after-idle",
        type=int,
        default=max(int(os.environ.get("TELEGRAM_CHAIN_STOP_AFTER_IDLE", "2") or "2"), 0),
        help="Stop after N consecutive runs without new usernames (0 = disabled).",
    )
    parser.add_argument(
        "--continue-on-nonzero",
        action="store_true",
        help="Continue the chain even if one run exits non-zero.",
    )
    parser.add_argument(
        "--target-unique-members",
        type=int,
        default=max(int(os.environ.get("TELEGRAM_CHAIN_TARGET_UNIQUE_MEMBERS", "0") or "0"), 0),
        help="Stop once run.json reaches at least this many unique members (0 = disabled).",
    )
    parser.add_argument(
        "--target-safe-count",
        type=int,
        default=max(int(os.environ.get("TELEGRAM_CHAIN_TARGET_SAFE_COUNT", "0") or "0"), 0),
        help="Stop once run.json reaches at least this many safe usernames (0 = disabled).",
    )
    parser.add_argument(
        "--stop-after-no-growth",
        type=int,
        default=max(int(os.environ.get("TELEGRAM_CHAIN_STOP_AFTER_NO_GROWTH", "0") or "0"), 0),
        help="Stop after N completed runs without improving unique_members or safe_count (0 = disabled).",
    )
    parser.add_argument(
        "--skip-interval-on-productive-yield",
        action=argparse.BooleanOptionalAction,
        default=os.environ.get("TELEGRAM_CHAIN_SKIP_INTERVAL_ON_PRODUCTIVE_YIELD", "1").strip().lower() not in {"0", "false", "no"},
        help="Skip the sleep interval after runs that stopped on productive deep-yield.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    profile_name = resolve_profile_name(args.profile)
    interval_sec = resolve_interval_sec(args.interval_sec, profile_name)
    collect_env = build_collect_env(profile_name)
    output_root = Path(args.output_root).expanduser()
    chat_dir = chat_dir_for(args.group_url, output_root)
    chain_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    chain_dir = chat_dir / "chains" / chain_id
    chain_summary_path = chain_dir / "chain.json"
    chain_log_path = chain_dir / "chain.log"
    chain_dir.mkdir(parents=True, exist_ok=True)

    attempts: list[dict[str, Any]] = []
    idle_runs = 0
    no_growth_runs = 0
    best_unique_members = 0
    best_safe_count = 0
    productive_yield_runs = 0
    chain_status = "completed"

    with chain_log_path.open("w", encoding="utf-8") as log_fh:
        for attempt_index in range(1, max(int(args.runs), 1) + 1):
            started_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            print(f"INFO: chain run {attempt_index}/{args.runs} started (profile={profile_name})", flush=True)
            log_fh.write(f"[{started_at}] run {attempt_index}/{args.runs} started profile={profile_name}\n")
            log_fh.flush()

            completed = subprocess.run(
                ["bash", str(COLLECT_SCRIPT), args.group_url, str(output_root)],
                cwd=str(ROOT_DIR),
                check=False,
                env=collect_env,
            )

            run_json_path = latest_run_json(chat_dir)
            run_payload = load_run_payload(run_json_path)
            new_usernames = int(run_payload.get("new_usernames", 0) or 0)
            unique_members = int(run_payload.get("unique_members", 0) or 0)
            safe_count = int(run_payload.get("safe_count", 0) or 0)
            members_with_username = int(run_payload.get("members_with_username", 0) or 0)
            chat_deep_priority_rounds = int(run_payload.get("chat_deep_priority_rounds", 0) or 0)
            chat_deep_yield_stop = int(run_payload.get("chat_deep_yield_stop", 0) or 0)
            run_status = str(run_payload.get("status") or ("completed" if completed.returncode == 0 else "failed"))
            unique_progress = False
            safe_progress = False
            productive_yield = run_status == "completed" and is_productive_deep_yield(run_payload)

            if productive_yield:
                productive_yield_runs += 1

            if run_status == "completed" and new_usernames <= 0:
                idle_runs += 1
            elif run_status == "completed":
                idle_runs = 0

            if run_status == "completed":
                unique_progress = unique_members > best_unique_members
                safe_progress = safe_count > best_safe_count
                if unique_progress:
                    best_unique_members = unique_members
                if safe_progress:
                    best_safe_count = safe_count
                if unique_progress or safe_progress:
                    no_growth_runs = 0
                else:
                    no_growth_runs += 1

            attempts.append(
                {
                    "attempt": attempt_index,
                    "profile": profile_name,
                    "started_at": started_at,
                    "exit_code": int(completed.returncode),
                    "run_json": str(run_json_path) if run_json_path else "",
                    "run_status": run_status,
                    "new_usernames": new_usernames,
                    "unique_members": unique_members,
                    "safe_count": safe_count,
                    "members_with_username": members_with_username,
                    "chat_deep_priority_rounds": chat_deep_priority_rounds,
                    "chat_deep_yield_stop": chat_deep_yield_stop,
                    "productive_yield": productive_yield,
                    "unique_progress": unique_progress,
                    "safe_progress": safe_progress,
                    "batch_path": str(run_payload.get("batch_path") or ""),
                    "idle_runs": idle_runs,
                    "no_growth_runs": no_growth_runs,
                    "best_unique_members": best_unique_members,
                    "best_safe_count": best_safe_count,
                }
            )
            log_fh.write(
                f"[{datetime.now(timezone.utc).replace(microsecond=0).isoformat()}] "
                f"run {attempt_index} exit={completed.returncode} status={run_status} new={new_usernames} "
                f"unique={unique_members} safe={safe_count} idle={idle_runs} no_growth={no_growth_runs} "
                f"deep_yield={int(productive_yield)}\n"
            )
            log_fh.flush()

            if completed.returncode != 0 and not args.continue_on_nonzero:
                chain_status = "stopped_on_error"
                break
            if reached_chain_target(unique_members, int(args.target_unique_members)):
                chain_status = "target_unique_members_reached"
                break
            if reached_chain_target(safe_count, int(args.target_safe_count)):
                chain_status = "target_safe_count_reached"
                break
            if should_stop_after_idle(idle_runs, int(args.stop_after_idle)):
                chain_status = "stopped_on_idle"
                break
            if should_stop_after_no_growth(no_growth_runs, int(args.stop_after_no_growth)):
                chain_status = "stopped_on_no_growth"
                break
            if attempt_index >= int(args.runs):
                break
            if should_skip_interval_after_run(run_payload, bool(args.skip_interval_on_productive_yield)):
                print("INFO: skip sleep after productive deep-yield run", flush=True)
                log_fh.write(
                    f"[{datetime.now(timezone.utc).replace(microsecond=0).isoformat()}] "
                    f"run {attempt_index} skip_sleep=productive_deep_yield\n"
                )
                log_fh.flush()
                continue
            if interval_sec > 0:
                print(f"INFO: sleeping {interval_sec:.1f}s before next chain run", flush=True)
                time.sleep(interval_sec)

    summary = {
        "status": chain_status,
        "profile": profile_name,
        "group_url": args.group_url,
        "output_root": str(output_root),
        "chat_dir": str(chat_dir),
        "chain_dir": str(chain_dir),
        "chain_log": str(chain_log_path),
        "runs_requested": int(args.runs),
        "interval_sec": float(interval_sec),
        "stop_after_idle": int(args.stop_after_idle),
        "stop_after_no_growth": int(args.stop_after_no_growth),
        "target_unique_members": int(args.target_unique_members),
        "target_safe_count": int(args.target_safe_count),
        "skip_interval_on_productive_yield": bool(args.skip_interval_on_productive_yield),
        "productive_yield_runs": productive_yield_runs,
        "collect_env_overrides": dict(resolve_profile(profile_name).get("env") or {}),
        "best_unique_members": best_unique_members,
        "best_safe_count": best_safe_count,
        "attempts": attempts,
    }
    write_chain_summary(chain_summary_path, summary)
    print(f"INFO: chain summary saved to {chain_summary_path}", flush=True)
    return 0 if chain_status in {"completed", "stopped_on_idle", "stopped_on_no_growth", "target_unique_members_reached", "target_safe_count_reached"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
