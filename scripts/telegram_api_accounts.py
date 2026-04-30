#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_REGISTRY_PATH = Path.home() / ".site-control-kit" / "telegram_workspace" / "registry" / "api_accounts.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _empty_registry() -> dict[str, Any]:
    return {"default_account": "", "accounts": []}


def _normalize_account_payload(
    *,
    name: str,
    token: str,
    client_id: str = "",
    updated_at: str | None = None,
) -> dict[str, str]:
    account_name = str(name or "").strip()
    if not account_name:
        raise ValueError("account name is required")
    access_token = str(token or "").strip()
    if not access_token:
        raise ValueError("account token is required")
    return {
        "name": account_name,
        "token": access_token,
        "client_id": str(client_id or "").strip(),
        "updated_at": str(updated_at or _now_iso()),
    }


def load_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _empty_registry()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_registry()
    if not isinstance(payload, dict):
        return _empty_registry()
    accounts_payload = payload.get("accounts")
    rows: list[dict[str, str]] = []
    if isinstance(accounts_payload, list):
        for item in accounts_payload:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            token = str(item.get("token") or "").strip()
            if not name or not token:
                continue
            rows.append(
                _normalize_account_payload(
                    name=name,
                    token=token,
                    client_id=str(item.get("client_id") or "").strip(),
                    updated_at=str(item.get("updated_at") or "").strip() or None,
                )
            )
    default_account = str(payload.get("default_account") or "").strip()
    if default_account and all(row["name"] != default_account for row in rows):
        default_account = rows[0]["name"] if rows else ""
    return {"default_account": default_account, "accounts": rows}


def save_registry(path: Path, registry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def list_accounts(registry: dict[str, Any]) -> list[dict[str, str]]:
    accounts = registry.get("accounts")
    if not isinstance(accounts, list):
        return []
    rows = [row for row in accounts if isinstance(row, dict)]
    rows.sort(key=lambda row: str(row.get("name") or "").lower())
    return rows


def token_mask(value: str) -> str:
    token = str(value or "")
    if len(token) <= 8:
        return "*" * len(token) if token else ""
    return f"{token[:4]}...{token[-4:]}"


def add_or_update_account(
    registry: dict[str, Any],
    *,
    name: str,
    token: str,
    client_id: str = "",
    set_default: bool = False,
) -> dict[str, Any]:
    payload = _normalize_account_payload(name=name, token=token, client_id=client_id)
    rows = list_accounts(registry)
    updated = False
    for row in rows:
        if row["name"] == payload["name"]:
            row.update(payload)
            updated = True
            break
    if not updated:
        rows.append(payload)
        rows.sort(key=lambda row: row["name"].lower())
    default_account = str(registry.get("default_account") or "").strip()
    if set_default or not default_account:
        default_account = payload["name"]
    return {"default_account": default_account, "accounts": rows}


def remove_account(registry: dict[str, Any], *, name: str) -> dict[str, Any]:
    target_name = str(name or "").strip()
    if not target_name:
        raise ValueError("account name is required")
    rows = [row for row in list_accounts(registry) if row["name"] != target_name]
    default_account = str(registry.get("default_account") or "").strip()
    if default_account == target_name:
        default_account = rows[0]["name"] if rows else ""
    return {"default_account": default_account, "accounts": rows}


def set_default_account(registry: dict[str, Any], *, name: str) -> dict[str, Any]:
    target_name = str(name or "").strip()
    if not target_name:
        raise ValueError("account name is required")
    rows = list_accounts(registry)
    if all(row["name"] != target_name for row in rows):
        raise ValueError(f"account not found: {target_name}")
    return {"default_account": target_name, "accounts": rows}


def resolve_account(registry: dict[str, Any], name: str | None = None) -> dict[str, str]:
    target_name = str(name or "").strip()
    rows = list_accounts(registry)
    if not rows:
        return {}
    if not target_name:
        target_name = str(registry.get("default_account") or "").strip()
    if target_name:
        for row in rows:
            if row["name"] == target_name:
                return row
    return rows[0]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Telegram API account registry helper.")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH), help="Path to registry JSON file.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List configured API accounts.")
    list_parser.add_argument("--format", choices=("json", "tsv"), default="tsv")

    add_parser = subparsers.add_parser("add", help="Add or update an API account.")
    add_parser.add_argument("--name", required=True)
    add_parser.add_argument("--token", required=True)
    add_parser.add_argument("--client-id", default="")
    add_parser.add_argument("--set-default", action="store_true")

    remove_parser = subparsers.add_parser("remove", help="Remove an API account.")
    remove_parser.add_argument("--name", required=True)

    default_parser = subparsers.add_parser("set-default", help="Set default API account.")
    default_parser.add_argument("--name", required=True)

    resolve_parser = subparsers.add_parser("resolve", help="Resolve account by name or default.")
    resolve_parser.add_argument("--name", default="")
    resolve_parser.add_argument("--format", choices=("json", "tsv"), default="tsv")
    return parser


def _print_account_tsv(account: dict[str, str], default_name: str) -> None:
    is_default = "1" if str(account.get("name") or "") == default_name else "0"
    print(
        "\t".join(
            [
                is_default,
                str(account.get("name") or ""),
                str(account.get("client_id") or ""),
                token_mask(str(account.get("token") or "")),
                str(account.get("updated_at") or ""),
            ]
        )
    )


def main() -> int:
    args = build_parser().parse_args()
    path = Path(args.registry).expanduser()
    registry = load_registry(path)

    if args.command == "list":
        rows = list_accounts(registry)
        if args.format == "json":
            payload = {
                "default_account": str(registry.get("default_account") or ""),
                "accounts": rows,
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        default_name = str(registry.get("default_account") or "")
        for row in rows:
            _print_account_tsv(row, default_name)
        return 0

    if args.command == "add":
        next_registry = add_or_update_account(
            registry,
            name=args.name,
            token=args.token,
            client_id=args.client_id,
            set_default=bool(args.set_default),
        )
        save_registry(path, next_registry)
        return 0

    if args.command == "remove":
        next_registry = remove_account(registry, name=args.name)
        save_registry(path, next_registry)
        return 0

    if args.command == "set-default":
        next_registry = set_default_account(registry, name=args.name)
        save_registry(path, next_registry)
        return 0

    if args.command == "resolve":
        account = resolve_account(registry, name=args.name)
        if args.format == "json":
            print(json.dumps(account, ensure_ascii=False, indent=2))
            return 0
        print(str(account.get("name") or ""))
        print(str(account.get("token") or ""))
        print(str(account.get("client_id") or ""))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
