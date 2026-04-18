#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

USERNAME_RE = re.compile(r"@[A-Za-z0-9_]{5,32}")


def normalize_username(value: str) -> str:
    match = USERNAME_RE.search(str(value or "").strip())
    return match.group(0).lower() if match else ""


def load_usernames(path: Path) -> list[str]:
    seen: set[str] = set()
    rows: list[str] = []
    text = path.read_text(encoding="utf-8", errors="ignore")
    for line in text.splitlines():
        username = normalize_username(line)
        if not username or username in seen:
            continue
        seen.add(username)
        rows.append(username)
    return rows


def numbered_batch_files(directory: Path) -> list[Path]:
    files: list[tuple[int, Path]] = []
    if not directory.exists():
        return []
    for path in directory.iterdir():
        if not path.is_file() or path.suffix.lower() != ".txt":
            continue
        stem = path.stem.strip()
        if not stem.isdigit():
            continue
        files.append((int(stem), path))
    files.sort(key=lambda item: item[0])
    return [path for _, path in files]


def known_usernames(directory: Path) -> set[str]:
    known: set[str] = set()
    for path in numbered_batch_files(directory):
        known.update(load_usernames(path))
    return known


def next_batch_number(directory: Path) -> int:
    files = numbered_batch_files(directory)
    if not files:
        return 1
    return max(int(path.stem) for path in files) + 1


def filter_new_usernames(usernames: list[str], known: set[str]) -> list[str]:
    new_rows: list[str] = []
    seen_now: set[str] = set()
    for username in usernames:
        normalized = normalize_username(username)
        if not normalized or normalized in known or normalized in seen_now:
            continue
        seen_now.add(normalized)
        new_rows.append(normalized)
    return new_rows


def save_new_batch(source: Path, directory: Path) -> tuple[int, Path | None]:
    directory.mkdir(parents=True, exist_ok=True)
    usernames = load_usernames(source)
    new_rows = filter_new_usernames(usernames, known_usernames(directory))
    if not new_rows:
        return 0, None

    batch_path = directory / f"{next_batch_number(directory)}.txt"
    batch_path.write_text("\n".join(new_rows) + "\n", encoding="utf-8")
    return len(new_rows), batch_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Save only new Telegram usernames into numbered batch files."
    )
    parser.add_argument("--source", required=True, help="Text file with full exported @username list")
    parser.add_argument("--directory", required=True, help="Directory with numbered batch files")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    count, batch_path = save_new_batch(Path(args.source).expanduser(), Path(args.directory).expanduser())
    print(f"created={1 if batch_path else 0}")
    print(f"count={count}")
    print(f"path={batch_path if batch_path else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
