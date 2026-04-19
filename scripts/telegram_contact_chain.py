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


def write_chain_summary(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run multiple short Telegram contact collection passes with pauses and shared discovery state."
    )
    parser.add_argument("group_url", help="Telegram group URL")
    parser.add_argument("output_root", nargs="?", default=str(Path.home() / "telegram_contact_batches"))
    parser.add_argument("--runs", type=int, default=max(int(os.environ.get("TELEGRAM_CHAIN_RUNS", "5") or "5"), 1))
    parser.add_argument(
        "--interval-sec",
        type=float,
        default=max(float(os.environ.get("TELEGRAM_CHAIN_INTERVAL_SEC", "20") or "20"), 0.0),
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
    return parser


def main() -> int:
    args = build_parser().parse_args()

    output_root = Path(args.output_root).expanduser()
    chat_dir = chat_dir_for(args.group_url, output_root)
    chain_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    chain_dir = chat_dir / "chains" / chain_id
    chain_summary_path = chain_dir / "chain.json"
    chain_log_path = chain_dir / "chain.log"
    chain_dir.mkdir(parents=True, exist_ok=True)

    attempts: list[dict[str, Any]] = []
    idle_runs = 0
    chain_status = "completed"

    with chain_log_path.open("w", encoding="utf-8") as log_fh:
        for attempt_index in range(1, max(int(args.runs), 1) + 1):
            started_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            print(f"INFO: chain run {attempt_index}/{args.runs} started", flush=True)
            log_fh.write(f"[{started_at}] run {attempt_index}/{args.runs} started\n")
            log_fh.flush()

            completed = subprocess.run(
                ["bash", str(COLLECT_SCRIPT), args.group_url, str(output_root)],
                cwd=str(ROOT_DIR),
                check=False,
            )

            run_json_path = latest_run_json(chat_dir)
            run_payload = load_run_payload(run_json_path)
            new_usernames = int(run_payload.get("new_usernames", 0) or 0)
            run_status = str(run_payload.get("status") or ("completed" if completed.returncode == 0 else "failed"))

            if run_status == "completed" and new_usernames <= 0:
                idle_runs += 1
            elif run_status == "completed":
                idle_runs = 0

            attempts.append(
                {
                    "attempt": attempt_index,
                    "started_at": started_at,
                    "exit_code": int(completed.returncode),
                    "run_json": str(run_json_path) if run_json_path else "",
                    "run_status": run_status,
                    "new_usernames": new_usernames,
                    "batch_path": str(run_payload.get("batch_path") or ""),
                    "idle_runs": idle_runs,
                }
            )
            log_fh.write(
                f"[{datetime.now(timezone.utc).replace(microsecond=0).isoformat()}] "
                f"run {attempt_index} exit={completed.returncode} status={run_status} new={new_usernames} idle={idle_runs}\n"
            )
            log_fh.flush()

            if completed.returncode != 0 and not args.continue_on_nonzero:
                chain_status = "stopped_on_error"
                break
            if should_stop_after_idle(idle_runs, int(args.stop_after_idle)):
                chain_status = "stopped_on_idle"
                break
            if attempt_index >= int(args.runs):
                break
            if float(args.interval_sec) > 0:
                print(f"INFO: sleeping {args.interval_sec:.1f}s before next chain run", flush=True)
                time.sleep(float(args.interval_sec))

    summary = {
        "status": chain_status,
        "group_url": args.group_url,
        "output_root": str(output_root),
        "chat_dir": str(chat_dir),
        "chain_dir": str(chain_dir),
        "chain_log": str(chain_log_path),
        "runs_requested": int(args.runs),
        "interval_sec": float(args.interval_sec),
        "stop_after_idle": int(args.stop_after_idle),
        "attempts": attempts,
    }
    write_chain_summary(chain_summary_path, summary)
    print(f"INFO: chain summary saved to {chain_summary_path}", flush=True)
    return 0 if chain_status in {"completed", "stopped_on_idle"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
