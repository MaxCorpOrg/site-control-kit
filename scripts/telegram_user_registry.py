#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_REGISTRY_PATH = Path.home() / ".site-control-kit" / "telegram_workspace" / "registry" / "users.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _empty_registry() -> dict[str, Any]:
    return {"default_user": "", "users": []}


def _normalize_user_payload(
    *,
    name: str,
    token: str,
    profile: str = "",
    updated_at: str | None = None,
) -> dict[str, str]:
    user_name = str(name or "").strip()
    if not user_name:
        raise ValueError("user name is required")
    api_token = str(token or "").strip()
    if not api_token:
        raise ValueError("api token is required")
    return {
        "name": user_name,
        "token": api_token,
        "profile": str(profile or "").strip(),
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

    rows: list[dict[str, str]] = []
    users_payload = payload.get("users")
    if isinstance(users_payload, list):
        for item in users_payload:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            token = str(item.get("token") or "").strip()
            if not name or not token:
                continue
            rows.append(
                _normalize_user_payload(
                    name=name,
                    token=token,
                    profile=str(item.get("profile") or "").strip(),
                    updated_at=str(item.get("updated_at") or "").strip() or None,
                )
            )

    default_user = str(payload.get("default_user") or "").strip()
    if default_user and all(row["name"] != default_user for row in rows):
        default_user = rows[0]["name"] if rows else ""
    return {"default_user": default_user, "users": rows}


def save_registry(path: Path, registry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def list_users(registry: dict[str, Any]) -> list[dict[str, str]]:
    rows = registry.get("users")
    if not isinstance(rows, list):
        return []
    prepared = [row for row in rows if isinstance(row, dict)]
    prepared.sort(key=lambda row: str(row.get("name") or "").lower())
    return prepared


def token_mask(value: str) -> str:
    token = str(value or "")
    if len(token) <= 8:
        return "*" * len(token) if token else ""
    return f"{token[:4]}...{token[-4:]}"


def add_or_update_user(
    registry: dict[str, Any],
    *,
    name: str,
    token: str,
    profile: str = "",
    set_default: bool = False,
) -> dict[str, Any]:
    payload = _normalize_user_payload(name=name, token=token, profile=profile)
    rows = list_users(registry)
    updated = False
    for row in rows:
        if row["name"] == payload["name"]:
            row.update(payload)
            updated = True
            break
    if not updated:
        rows.append(payload)
        rows.sort(key=lambda row: row["name"].lower())
    default_user = str(registry.get("default_user") or "").strip()
    if set_default or not default_user:
        default_user = payload["name"]
    return {"default_user": default_user, "users": rows}


def set_default_user(registry: dict[str, Any], *, name: str) -> dict[str, Any]:
    target = str(name or "").strip()
    if not target:
        raise ValueError("user name is required")
    rows = list_users(registry)
    if all(row["name"] != target for row in rows):
        raise ValueError(f"user not found: {target}")
    return {"default_user": target, "users": rows}


def remove_user(registry: dict[str, Any], *, name: str) -> dict[str, Any]:
    target = str(name or "").strip()
    if not target:
        raise ValueError("user name is required")
    rows = [row for row in list_users(registry) if row["name"] != target]
    default_user = str(registry.get("default_user") or "").strip()
    if default_user == target:
        default_user = rows[0]["name"] if rows else ""
    return {"default_user": default_user, "users": rows}


def resolve_user(registry: dict[str, Any], name: str | None = None) -> dict[str, str]:
    target = str(name or "").strip()
    rows = list_users(registry)
    if not rows:
        return {}
    if not target:
        target = str(registry.get("default_user") or "").strip()
    if target:
        for row in rows:
            if row["name"] == target:
                return row
    return rows[0]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Telegram users registry helper.")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH), help="Path to users registry JSON.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List users.")
    list_parser.add_argument("--format", choices=("json", "tsv"), default="tsv")

    add_parser = subparsers.add_parser("add", help="Add or update user.")
    add_parser.add_argument("--name", required=True)
    add_parser.add_argument("--token", required=True)
    add_parser.add_argument("--profile", default="")
    add_parser.add_argument("--set-default", action="store_true")

    remove_parser = subparsers.add_parser("remove", help="Remove user.")
    remove_parser.add_argument("--name", required=True)

    default_parser = subparsers.add_parser("set-default", help="Set default user.")
    default_parser.add_argument("--name", required=True)

    resolve_parser = subparsers.add_parser("resolve", help="Resolve user by name or default.")
    resolve_parser.add_argument("--name", default="")
    resolve_parser.add_argument("--format", choices=("json", "tsv"), default="tsv")
    return parser


def _print_user_tsv(user: dict[str, str], default_name: str) -> None:
    is_default = "1" if str(user.get("name") or "") == default_name else "0"
    print(
        "\t".join(
            [
                is_default,
                str(user.get("name") or ""),
                str(user.get("profile") or ""),
                token_mask(str(user.get("token") or "")),
                str(user.get("updated_at") or ""),
            ]
        )
    )


def main() -> int:
    args = build_parser().parse_args()
    path = Path(args.registry).expanduser()
    registry = load_registry(path)

    if args.command == "list":
        users = list_users(registry)
        if args.format == "json":
            print(json.dumps({"default_user": registry.get("default_user") or "", "users": users}, ensure_ascii=False, indent=2))
            return 0
        default_name = str(registry.get("default_user") or "")
        for user in users:
            _print_user_tsv(user, default_name)
        return 0

    if args.command == "add":
        next_registry = add_or_update_user(
            registry,
            name=args.name,
            token=args.token,
            profile=args.profile,
            set_default=bool(args.set_default),
        )
        save_registry(path, next_registry)
        return 0

    if args.command == "set-default":
        next_registry = set_default_user(registry, name=args.name)
        save_registry(path, next_registry)
        return 0

    if args.command == "remove":
        next_registry = remove_user(registry, name=args.name)
        save_registry(path, next_registry)
        return 0

    if args.command == "resolve":
        user = resolve_user(registry, name=args.name)
        if args.format == "json":
            print(json.dumps(user, ensure_ascii=False, indent=2))
            return 0
        print(str(user.get("name") or ""))
        print(str(user.get("token") or ""))
        print(str(user.get("profile") or ""))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
