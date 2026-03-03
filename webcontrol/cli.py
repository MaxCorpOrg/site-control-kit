from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import HubConfig
from .server import run_server
from .store import TERMINAL_COMMAND_STATUSES
from .utils import compact

DEFAULT_SERVER = "http://127.0.0.1:8765"
DEFAULT_TOKEN_ENV = "SITECTL_TOKEN"
DEFAULT_QUICKSTART_TOKEN = "local-bridge-quickstart-2026"


def _norm_server(url: str) -> str:
    return url.rstrip("/")


def _http_json(
    *,
    server: str,
    token: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    endpoint = f"{_norm_server(server)}{path}"
    body = None
    headers = {
        "Accept": "application/json",
        "X-Access-Token": token,
    }
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = Request(endpoint, data=body, method=method, headers=headers)
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            if not raw:
                return {"ok": True}
            return json.loads(raw)
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
        raise RuntimeError(f"HTTP {exc.code}: {raw or exc.reason}") from exc
    except URLError as exc:
        raise RuntimeError(f"Network error: {exc.reason}") from exc


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _load_json_file(path: str) -> dict[str, Any]:
    content = Path(path).read_text(encoding="utf-8")
    payload = json.loads(content)
    if not isinstance(payload, dict):
        raise ValueError("JSON payload must be an object")
    return payload


def _wait_command(server: str, token: str, command_id: str, timeout_sec: int, interval_sec: float) -> dict[str, Any]:
    deadline = time.time() + timeout_sec
    while True:
        response = _http_json(server=server, token=token, method="GET", path=f"/api/commands/{command_id}")
        command = response.get("command") or {}
        status = command.get("status")
        if status in TERMINAL_COMMAND_STATUSES:
            return command
        if time.time() >= deadline:
            return command
        time.sleep(interval_sec)


def _extract_runtime(args: argparse.Namespace) -> tuple[str, str]:
    token = args.token or os.getenv(DEFAULT_TOKEN_ENV, "") or DEFAULT_QUICKSTART_TOKEN
    server = _norm_server(args.server or DEFAULT_SERVER)
    return server, token


def cmd_serve(args: argparse.Namespace) -> int:
    token = args.token or os.getenv(DEFAULT_TOKEN_ENV, "") or DEFAULT_QUICKSTART_TOKEN

    config = HubConfig(
        host=args.host,
        port=args.port,
        token=token,
        state_file=Path(args.state_file).expanduser(),
    )
    run_server(config)
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    server = _norm_server(args.server or DEFAULT_SERVER)
    try:
        response = _http_json(server=server, token="health", method="GET", path="/health")
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    _print_json(response)
    return 0


def cmd_state(args: argparse.Namespace) -> int:
    try:
        server, token = _extract_runtime(args)
        response = _http_json(server=server, token=token, method="GET", path="/api/state")
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    _print_json(response)
    return 0


def cmd_clients(args: argparse.Namespace) -> int:
    try:
        server, token = _extract_runtime(args)
        response = _http_json(server=server, token=token, method="GET", path="/api/clients")
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    _print_json(response)
    return 0


def _build_command_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.payload_file:
        payload = _load_json_file(args.payload_file)
        if "issued_by" not in payload:
            payload["issued_by"] = "cli"
        return payload

    if not args.type:
        raise ValueError("--type is required when --payload-file is not provided")

    command: dict[str, Any] = compact(
        {
            "type": args.type,
            "selector": args.selector,
            "value": args.value,
            "url": args.url,
            "text": args.text,
            "script": args.script,
            "attribute": args.attribute,
            "x": args.x,
            "y": args.y,
            "timeout_ms": args.command_timeout_ms,
        }
    )

    if args.script_args:
        command["args"] = json.loads(args.script_args)

    target: dict[str, Any] = compact(
        {
            "client_id": args.client_id,
            "tab_id": args.tab_id,
            "url_pattern": args.url_pattern,
            "active": args.active,
        }
    )

    if args.client_ids:
        target["client_ids"] = [value.strip() for value in args.client_ids.split(",") if value.strip()]
    if args.broadcast:
        target["broadcast"] = True

    payload = {
        "issued_by": "cli",
        "timeout_ms": args.timeout_ms,
        "target": target,
        "command": command,
    }
    return payload


def cmd_send(args: argparse.Namespace) -> int:
    try:
        server, token = _extract_runtime(args)
        payload = _build_command_payload(args)
        response = _http_json(server=server, token=token, method="POST", path="/api/commands", payload=payload)
    except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if not response.get("ok"):
        _print_json(response)
        return 1

    command_id = response.get("command_id")
    print(f"command_id={command_id}")
    print(f"status={response.get('status')}")
    print(f"targets={','.join(response.get('target_client_ids', []))}")

    if args.wait > 0 and command_id:
        command = _wait_command(server, token, command_id, timeout_sec=args.wait, interval_sec=max(args.poll_interval, 0.1))
        print("\nfinal_command_state:")
        _print_json(command)
    return 0


def cmd_wait(args: argparse.Namespace) -> int:
    try:
        server, token = _extract_runtime(args)
        command = _wait_command(
            server,
            token,
            args.command_id,
            timeout_sec=args.timeout,
            interval_sec=max(args.poll_interval, 0.1),
        )
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    _print_json(command)
    status = command.get("status")
    return 0 if status in TERMINAL_COMMAND_STATUSES else 1


def cmd_cancel(args: argparse.Namespace) -> int:
    try:
        server, token = _extract_runtime(args)
        response = _http_json(
            server=server,
            token=token,
            method="POST",
            path=f"/api/commands/{args.command_id}/cancel",
            payload={"reason": args.reason},
        )
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    _print_json(response)
    return 0 if response.get("ok") else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sitectl",
        description="Local site control hub CLI",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    def add_runtime_options(cmd: argparse.ArgumentParser) -> None:
        cmd.add_argument("--server", default=DEFAULT_SERVER, help=f"Hub URL (default: {DEFAULT_SERVER})")
        cmd.add_argument(
            "--token",
            default="",
            help=(
                f"Access token (fallback env: {DEFAULT_TOKEN_ENV}; "
                f"default quick mode: {DEFAULT_QUICKSTART_TOKEN})"
            ),
        )

    serve = sub.add_parser("serve", help="Run local API server")
    add_runtime_options(serve)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", default=8765, type=int)
    serve.add_argument(
        "--state-file",
        default=str(Path.home() / ".site-control-kit" / "state.json"),
        help="Path to persistent state file",
    )
    serve.set_defaults(func=cmd_serve)

    health = sub.add_parser("health", help="Check hub health endpoint")
    add_runtime_options(health)
    health.set_defaults(func=cmd_health)

    state = sub.add_parser("state", help="Print full hub state")
    add_runtime_options(state)
    state.set_defaults(func=cmd_state)

    clients = sub.add_parser("clients", help="List connected browser clients")
    add_runtime_options(clients)
    clients.set_defaults(func=cmd_clients)

    send = sub.add_parser("send", help="Send command to browser extension client(s)")
    add_runtime_options(send)
    send.add_argument("--payload-file", help="JSON file with full request payload")
    send.add_argument("--type", help="Command type (navigate/click/fill/extract_text/get_html/screenshot/wait_selector/scroll/run_script)")

    send.add_argument("--client-id", help="Target one client ID")
    send.add_argument("--client-ids", help="Comma-separated list of client IDs")
    send.add_argument("--broadcast", action="store_true", help="Send to all known clients")
    send.add_argument("--tab-id", type=int, help="Explicit browser tab id")
    send.add_argument("--url-pattern", help="Pick a tab where URL contains this text")
    send.add_argument(
        "--active",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Prefer active tab when tab_id/url_pattern not set",
    )

    send.add_argument("--selector", help="CSS selector")
    send.add_argument("--value", help="Input value")
    send.add_argument("--url", help="Navigation URL")
    send.add_argument("--text", help="Optional free text")
    send.add_argument("--script", help="JavaScript body for run_script")
    send.add_argument("--script-args", help="JSON args for run_script")
    send.add_argument("--attribute", help="DOM attribute name")
    send.add_argument("--x", type=int, help="Numeric x parameter")
    send.add_argument("--y", type=int, help="Numeric y parameter")
    send.add_argument("--command-timeout-ms", type=int, default=10000, help="Command-level timeout in extension")

    send.add_argument("--timeout-ms", type=int, default=20000, help="Hub queue timeout for command")
    send.add_argument("--wait", type=int, default=0, help="Wait up to N seconds for terminal command state")
    send.add_argument("--poll-interval", type=float, default=1.0, help="Polling interval for --wait")
    send.set_defaults(func=cmd_send)

    wait = sub.add_parser("wait", help="Wait for a command to finish")
    add_runtime_options(wait)
    wait.add_argument("command_id")
    wait.add_argument("--timeout", type=int, default=60)
    wait.add_argument("--poll-interval", type=float, default=1.0)
    wait.set_defaults(func=cmd_wait)

    cancel = sub.add_parser("cancel", help="Cancel a command")
    add_runtime_options(cancel)
    cancel.add_argument("command_id")
    cancel.add_argument("--reason", default="manual cancel")
    cancel.set_defaults(func=cmd_cancel)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
