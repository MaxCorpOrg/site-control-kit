from __future__ import annotations

import argparse
import json
import signal
from pathlib import Path

from .config import load_config, write_sample_config
from .session_runner import load_state, plan_session, run_session, run_session_continuous, sync_preview


_STOP_REQUESTED = False


def _request_stop(_signum: int, _frame: object) -> None:
    global _STOP_REQUESTED
    _STOP_REQUESTED = True


def _stop_requested() -> bool:
    return _STOP_REQUESTED


def _run_with_stop_handlers(callback):
    global _STOP_REQUESTED
    _STOP_REQUESTED = False
    previous_handlers: list[tuple[int, object]] = []
    for signum in (signal.SIGTERM, signal.SIGINT):
        try:
            previous_handlers.append((signum, signal.getsignal(signum)))
            signal.signal(signum, _request_stop)
        except Exception:
            continue
    try:
        return callback()
    finally:
        for signum, handler in previous_handlers:
            try:
                signal.signal(signum, handler)
            except Exception:
                continue


def _print(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def command_sample_config(args: argparse.Namespace) -> int:
    path = write_sample_config(Path(args.output))
    _print({"status": "written", "output": str(path)})
    return 0


def command_plan_session(args: argparse.Namespace) -> int:
    payload = plan_session(
        config_path=Path(args.config),
        state_path=Path(args.state_file),
        seed=args.seed or None,
    )
    _print({"status": "planned", "plan": payload})
    return 0


def command_show_state(args: argparse.Namespace) -> int:
    payload = load_state(Path(args.state_file))
    _print({"status": "ok", "state": payload})
    return 0


def command_sync_preview(args: argparse.Namespace) -> int:
    payload = sync_preview(config_path=Path(args.config))
    _print({"status": "ok", "sync": payload})
    return 0


def command_run_session(args: argparse.Namespace) -> int:
    config = load_config(Path(args.config))
    runs_dir = Path(args.runs_dir) if args.runs_dir else Path.cwd() / "runs"
    confirm_send = bool(args.confirm_send)
    auto_send = bool(args.auto_send) or (bool(config.message_policy.auto_send) and not confirm_send)
    def _execute() -> dict:
        try:
            if args.continuous:
                return run_session_continuous(
                    config=config,
                    state_path=Path(args.state_file),
                    runs_dir=runs_dir,
                    execute=bool(args.execute),
                    launch_if_needed=bool(args.launch_if_needed),
                    confirm_send=confirm_send,
                    auto_send=auto_send,
                    seed=args.seed or None,
                    stop_requested=_stop_requested,
                )
            return run_session(
                config=config,
                state_path=Path(args.state_file),
                runs_dir=runs_dir,
                execute=bool(args.execute),
                launch_if_needed=bool(args.launch_if_needed),
                confirm_send=confirm_send,
                auto_send=auto_send,
                seed=args.seed or None,
                stop_requested=_stop_requested,
            )
        except Exception as exc:
            if _stop_requested():
                return {
                    "status": "stopped",
                    "continuous": bool(args.continuous),
                    "error": str(exc),
                }
            raise

    payload = _run_with_stop_handlers(_execute)
    _print(payload)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Allowlist-only Telegram Desktop portable session tool.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sample_parser = subparsers.add_parser("sample-config", help="Write a sample session config.")
    sample_parser.add_argument("--output", required=True)
    sample_parser.set_defaults(func=command_sample_config)

    plan_parser = subparsers.add_parser("plan-session", help="Build a session plan without executing it.")
    plan_parser.add_argument("--config", required=True)
    plan_parser.add_argument("--state-file", required=True)
    plan_parser.add_argument("--seed", default="")
    plan_parser.set_defaults(func=command_plan_session)

    sync_parser = subparsers.add_parser("sync-preview", help="Show targets resolved from manual config and sync sources.")
    sync_parser.add_argument("--config", required=True)
    sync_parser.set_defaults(func=command_sync_preview)

    run_parser = subparsers.add_parser("run-session", help="Execute a session plan.")
    run_parser.add_argument("--config", required=True)
    run_parser.add_argument("--state-file", required=True)
    run_parser.add_argument("--runs-dir", default="")
    run_parser.add_argument("--seed", default="")
    run_parser.add_argument("--execute", action="store_true")
    run_parser.add_argument("--launch-if-needed", action="store_true")
    run_parser.add_argument("--continuous", action="store_true")
    send_mode_group = run_parser.add_mutually_exclusive_group()
    send_mode_group.add_argument("--confirm-send", action="store_true")
    send_mode_group.add_argument("--auto-send", action="store_true")
    run_parser.set_defaults(func=command_run_session)

    state_parser = subparsers.add_parser("show-state", help="Show the current state file.")
    state_parser.add_argument("--state-file", required=True)
    state_parser.set_defaults(func=command_show_state)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
