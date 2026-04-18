#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple

USERNAME_RE = re.compile(r"@[A-Za-z0-9_]{5,32}")
HISTORY_FILE = "identity_history.json"
REVIEW_FILE = "review.txt"
CONFLICTS_FILE = "conflicts.json"


class MemberRecord(NamedTuple):
    peer_id: str
    name: str
    username: str


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


def history_path(directory: Path) -> Path:
    return directory / HISTORY_FILE


def review_path(directory: Path) -> Path:
    return directory / REVIEW_FILE


def conflicts_path(directory: Path) -> Path:
    return directory / CONFLICTS_FILE


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_history(directory: Path) -> dict[str, Any]:
    path = history_path(directory)
    if not path.exists():
        return {
            "version": 1,
            "updated_at": "",
            "username_to_peer": {},
            "peer_to_username": {},
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "version": 1,
            "updated_at": "",
            "username_to_peer": {},
            "peer_to_username": {},
        }
    if not isinstance(payload, dict):
        payload = {}
    username_to_peer = payload.get("username_to_peer")
    peer_to_username = payload.get("peer_to_username")
    return {
        "version": 1,
        "updated_at": str(payload.get("updated_at") or ""),
        "username_to_peer": username_to_peer if isinstance(username_to_peer, dict) else {},
        "peer_to_username": peer_to_username if isinstance(peer_to_username, dict) else {},
    }


def save_history(directory: Path, history: dict[str, Any]) -> None:
    history = {
        "version": 1,
        "updated_at": utc_now_iso(),
        "username_to_peer": dict(sorted((history.get("username_to_peer") or {}).items())),
        "peer_to_username": dict(sorted((history.get("peer_to_username") or {}).items())),
    }
    history_path(directory).write_text(
        json.dumps(history, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _split_markdown_cells(line: str) -> list[str]:
    row = line.strip()
    if not row.startswith("|") or not row.endswith("|"):
        return []
    row = row[1:-1]
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in row:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "|":
            cells.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    cells.append("".join(current).strip())
    return cells


def load_member_records_from_markdown(path: Path) -> list[MemberRecord]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    rows: list[MemberRecord] = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = _split_markdown_cells(line)
        if len(cells) != 6:
            continue
        if cells[0] in {"#", "---"}:
            continue
        username = normalize_username(cells[2])
        peer_id = str(cells[5] or "").strip()
        if not username or not peer_id or peer_id == "—":
            continue
        rows.append(
            MemberRecord(
                peer_id=peer_id,
                name=str(cells[1] or "").strip(),
                username=username,
            )
        )
    return rows


def evaluate_identity_records(
    records: list[MemberRecord],
    history: dict[str, Any],
) -> tuple[list[str], list[dict[str, str]], dict[str, Any]]:
    username_to_peer = {
        str(key): str(value)
        for key, value in (history.get("username_to_peer") or {}).items()
        if key and value
    }
    peer_to_username = {
        str(key): str(value)
        for key, value in (history.get("peer_to_username") or {}).items()
        if key and value
    }
    current_username_to_peer: dict[str, str] = {}
    current_peer_to_username: dict[str, str] = {}
    safe_usernames: list[str] = []
    conflicts: list[dict[str, str]] = []

    for record in records:
        username = normalize_username(record.username)
        peer_id = str(record.peer_id or "").strip()
        if not username or not peer_id:
            continue

        current_peer_for_username = current_username_to_peer.get(username)
        if current_peer_for_username and current_peer_for_username != peer_id:
            conflicts.append(
                {
                    "reason": "duplicate_username_in_current_export",
                    "username": username,
                    "peer_id": peer_id,
                    "previous_peer_id": current_peer_for_username,
                    "name": record.name,
                }
            )
            continue

        current_username_for_peer = current_peer_to_username.get(peer_id)
        if current_username_for_peer and current_username_for_peer != username:
            conflicts.append(
                {
                    "reason": "duplicate_peer_in_current_export",
                    "username": username,
                    "peer_id": peer_id,
                    "previous_username": current_username_for_peer,
                    "name": record.name,
                }
            )
            continue

        historical_peer = username_to_peer.get(username)
        if historical_peer and historical_peer != peer_id:
            conflicts.append(
                {
                    "reason": "username_changed_owner",
                    "username": username,
                    "peer_id": peer_id,
                    "previous_peer_id": historical_peer,
                    "name": record.name,
                }
            )
            continue

        historical_username = peer_to_username.get(peer_id)
        if historical_username and historical_username != username:
            conflicts.append(
                {
                    "reason": "peer_changed_username",
                    "username": username,
                    "peer_id": peer_id,
                    "previous_username": historical_username,
                    "name": record.name,
                }
            )
            continue

        current_username_to_peer[username] = peer_id
        current_peer_to_username[peer_id] = username
        safe_usernames.append(username)

    next_history = {
        "version": 1,
        "updated_at": utc_now_iso(),
        "username_to_peer": {**username_to_peer, **current_username_to_peer},
        "peer_to_username": {**peer_to_username, **current_peer_to_username},
    }
    return safe_usernames, conflicts, next_history


def write_review_files(directory: Path, conflicts: list[dict[str, str]]) -> tuple[Path, Path] | tuple[None, None]:
    review_txt = review_path(directory)
    conflicts_json = conflicts_path(directory)
    if not conflicts:
        review_txt.unlink(missing_ok=True)
        conflicts_json.unlink(missing_ok=True)
        return None, None

    ts = utc_now_iso()
    review_lines = [
        "Telegram username review",
        "",
        f"Updated at: {ts}",
        f"Conflicts: {len(conflicts)}",
        "",
    ]
    for index, item in enumerate(conflicts, start=1):
        review_lines.append(
            f"{index}. {item.get('reason', 'conflict')}: "
            f"{item.get('username', '')} -> peer {item.get('peer_id', '')}"
        )
        if item.get("name"):
            review_lines.append(f"   name: {item['name']}")
        if item.get("previous_peer_id"):
            review_lines.append(f"   previous peer: {item['previous_peer_id']}")
        if item.get("previous_username"):
            review_lines.append(f"   previous username: {item['previous_username']}")
    review_lines.append("")

    review_txt.write_text("\n".join(review_lines), encoding="utf-8")
    payload = {
        "updated_at": ts,
        "count": len(conflicts),
        "conflicts": conflicts,
    }
    conflicts_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return review_txt, conflicts_json


def save_new_batch(
    source: Path,
    directory: Path,
    full_md: Path | None = None,
) -> tuple[int, Path | None, int, Path | None]:
    directory.mkdir(parents=True, exist_ok=True)
    usernames = load_usernames(source)
    review_file: Path | None = None
    review_count = 0

    if full_md is not None and full_md.exists():
        history = load_history(directory)
        records = load_member_records_from_markdown(full_md)
        safe_usernames, conflicts, next_history = evaluate_identity_records(records, history)
        if safe_usernames:
            allowed = set(safe_usernames)
            usernames = [item for item in usernames if item in allowed]
        else:
            usernames = []
        review_count = len(conflicts)
        review_txt, _ = write_review_files(directory, conflicts)
        review_file = review_txt
        save_history(directory, next_history)

    new_rows = filter_new_usernames(usernames, known_usernames(directory))
    if not new_rows:
        return 0, None, review_count, review_file

    batch_path = directory / f"{next_batch_number(directory)}.txt"
    batch_path.write_text("\n".join(new_rows) + "\n", encoding="utf-8")
    return len(new_rows), batch_path, review_count, review_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Save only new Telegram usernames into numbered batch files."
    )
    parser.add_argument("--source", required=True, help="Text file with full exported @username list")
    parser.add_argument("--directory", required=True, help="Directory with numbered batch files")
    parser.add_argument("--full-md", help="Full markdown export used for identity safety checks")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    count, batch_path, review_count, review_file = save_new_batch(
        Path(args.source).expanduser(),
        Path(args.directory).expanduser(),
        Path(args.full_md).expanduser() if args.full_md else None,
    )
    print(f"created={1 if batch_path else 0}")
    print(f"count={count}")
    print(f"path={batch_path if batch_path else ''}")
    print(f"review_count={review_count}")
    print(f"review_path={review_file if review_file else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
