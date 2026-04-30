#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

DEFAULT_WORKSPACE_ROOT = Path.home() / ".site-control-kit" / "telegram_workspace"
LEGACY_USERS_ROOT = Path.home() / ".site-control-kit" / "telegram_users"
LEGACY_REGISTRY_PATH = LEGACY_USERS_ROOT / "registry.json"


def _workspace_paths(root: Path) -> dict[str, Path]:
    return {
        "root": root,
        "registry_dir": root / "registry",
        "registry_file": root / "registry" / "users.json",
        "profiles_dir": root / "profiles",
        "default_profile_dir": root / "profiles" / "default",
        "cache_unpacked_dir": root / "cache" / "unpacked_profiles",
        "accounts_dir": root / "accounts",
        "readme_file": root / "README.txt",
    }


def _empty_registry() -> dict[str, Any]:
    return {"default_user": "", "users": []}


def _write_if_missing(path: Path, content: str) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _ensure_slot(slot_dir: Path, slot_index: int) -> None:
    profile_dir = slot_dir / "profile"
    imports_dir = slot_dir / "imports"
    keys_dir = slot_dir / "keys"

    profile_dir.mkdir(parents=True, exist_ok=True)
    imports_dir.mkdir(parents=True, exist_ok=True)
    keys_dir.mkdir(parents=True, exist_ok=True)

    _write_if_missing(
        slot_dir / "README.txt",
        "\n".join(
            [
                f"Telegram slot {slot_index}",
                "",
                "Куда класть данные:",
                "- profile/: профиль браузера с Telegram (можно копировать tdata/Default и т.д.)",
                "- imports/: zip-архивы portable-профиля (GUI покажет auto-слоты)",
                "- keys/api_token.txt: SITECTL token для этого пользователя",
                "- keys/api_id.txt: Telegram API ID (опционально)",
                "- keys/api_hash.txt: Telegram API Hash (опционально)",
                "",
                "Рекомендация: используйте один слот = один Telegram пользователь.",
                "",
            ]
        ),
    )
    _write_if_missing(keys_dir / "api_token.txt", "")
    _write_if_missing(keys_dir / "api_id.txt", "")
    _write_if_missing(keys_dir / "api_hash.txt", "")


def ensure_workspace(root: Path, slots: int) -> dict[str, Any]:
    paths = _workspace_paths(root)
    for key in (
        "root",
        "registry_dir",
        "profiles_dir",
        "default_profile_dir",
        "cache_unpacked_dir",
        "accounts_dir",
    ):
        paths[key].mkdir(parents=True, exist_ok=True)

    _write_if_missing(
        paths["readme_file"],
        "\n".join(
            [
                "Telegram Workspace (site-control-kit)",
                "",
                "Единая папка для всех данных GUI-экспорта @username.",
                "",
                "Структура:",
                "- registry/users.json: реестр пользователей GUI",
                "- profiles/default: профиль по умолчанию",
                "- cache/unpacked_profiles: кэш распаковки zip-профилей",
                "- accounts/1..10: слоты пользователей (profile/imports/keys)",
                "",
                "Как использовать slots:",
                "1) Кладите tdata/профиль в accounts/N/profile",
                "2) Или zip в accounts/N/imports",
                "3) Ключи храните в accounts/N/keys",
                "",
            ]
        ),
    )

    if not paths["registry_file"].exists():
        if LEGACY_REGISTRY_PATH.exists():
            paths["registry_file"].write_text(LEGACY_REGISTRY_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            paths["registry_file"].write_text(json.dumps(_empty_registry(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for index in range(1, max(slots, 1) + 1):
        _ensure_slot(paths["accounts_dir"] / str(index), index)

    return {
        "workspace_root": str(paths["root"]),
        "registry_file": str(paths["registry_file"]),
        "default_profile_dir": str(paths["default_profile_dir"]),
        "cache_unpacked_dir": str(paths["cache_unpacked_dir"]),
        "accounts_dir": str(paths["accounts_dir"]),
        "slots": max(slots, 1),
    }


def _directory_has_payload(path: Path) -> bool:
    if not path.exists() or not path.is_dir():
        return False
    try:
        next(path.iterdir())
    except StopIteration:
        return False
    return True


def list_profiles(root: Path) -> list[tuple[str, str]]:
    paths = _workspace_paths(root)
    rows: list[tuple[str, str]] = []
    if _directory_has_payload(paths["default_profile_dir"]):
        rows.append(("auto-default", str(paths["default_profile_dir"])))

    accounts_dir = paths["accounts_dir"]
    if accounts_dir.exists():
        for slot_dir in sorted((item for item in accounts_dir.iterdir() if item.is_dir()), key=lambda p: p.name):
            slot_name = slot_dir.name
            profile_dir = slot_dir / "profile"
            imports_dir = slot_dir / "imports"
            if _directory_has_payload(profile_dir):
                rows.append((f"auto-slot-{slot_name}-profile", str(profile_dir)))
            if imports_dir.is_dir():
                for archive in sorted(imports_dir.glob("*.zip"), key=lambda p: p.name.lower()):
                    rows.append((f"auto-slot-{slot_name}-zip-{archive.stem}", str(archive)))

    # Legacy fallback for compatibility with previous layout
    legacy_profiles_dir = LEGACY_USERS_ROOT / "profiles"
    if legacy_profiles_dir.exists():
        for item in sorted(legacy_profiles_dir.iterdir(), key=lambda p: p.name.lower()):
            if item.is_dir():
                rows.append((f"auto-legacy-{item.name}", str(item)))
            elif item.is_file() and item.suffix.lower() == ".zip":
                rows.append((f"auto-legacy-{item.stem}", str(item)))

    deduped: list[tuple[str, str]] = []
    seen: set[str] = set()
    for name, value in rows:
        key = f"{name}\t{value}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append((name, value))
    return deduped


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Telegram workspace layout helper.")
    parser.add_argument("--root", default=str(DEFAULT_WORKSPACE_ROOT), help="Workspace root path.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    ensure_parser = subparsers.add_parser("ensure", help="Ensure workspace directories exist.")
    ensure_parser.add_argument("--slots", type=int, default=10, help="How many numeric user slots to create.")
    ensure_parser.add_argument("--format", choices=("json", "tsv"), default="json")

    profiles_parser = subparsers.add_parser("list-profiles", help="List auto-detected profile sources.")
    profiles_parser.add_argument("--format", choices=("tsv", "json"), default="tsv")

    migrate_parser = subparsers.add_parser("migrate-legacy", help="Copy a legacy profile into a slot profile directory.")
    migrate_parser.add_argument("--source", required=True, help="Legacy folder path (e.g. TG_CONTACT).")
    migrate_parser.add_argument("--slot", type=int, required=True, help="Target slot number.")
    migrate_parser.add_argument("--replace", action="store_true", help="Replace target slot profile directory.")

    return parser


def migrate_legacy(root: Path, source: Path, slot: int, replace: bool) -> dict[str, str]:
    if slot < 1:
        raise ValueError("slot must be >= 1")
    if not source.exists() or not source.is_dir():
        raise ValueError("source directory not found")

    ensure_workspace(root, slots=max(slot, 10))
    target = _workspace_paths(root)["accounts_dir"] / str(slot) / "profile"

    if target.exists() and any(target.iterdir()):
        if not replace:
            raise ValueError(f"slot profile is not empty: {target}")
        shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)

    for item in source.iterdir():
        src = item
        dst = target / item.name
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)

    return {"source": str(source), "target": str(target), "slot": str(slot)}


def main() -> int:
    args = build_parser().parse_args()
    root = Path(args.root).expanduser()

    if args.command == "ensure":
        payload = ensure_workspace(root, slots=max(int(args.slots), 1))
        if args.format == "tsv":
            for key in sorted(payload):
                print(f"{key}\t{payload[key]}")
            return 0
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if args.command == "list-profiles":
        rows = list_profiles(root)
        if args.format == "json":
            print(json.dumps([{"name": name, "path": path} for name, path in rows], ensure_ascii=False, indent=2))
            return 0
        for name, path in rows:
            print(f"{name}\t{path}")
        return 0

    if args.command == "migrate-legacy":
        payload = migrate_legacy(
            root=root,
            source=Path(args.source).expanduser(),
            slot=int(args.slot),
            replace=bool(args.replace),
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
