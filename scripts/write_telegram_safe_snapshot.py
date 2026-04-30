#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
from typing import Any


def _load_batches_module(script_dir: Path):
    module_path = script_dir / "telegram_contact_batches.py"
    spec = importlib.util.spec_from_file_location("telegram_contact_batches", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load helper module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build safe Telegram username snapshot from a raw markdown export.",
    )
    parser.add_argument(
        "--source-md",
        required=True,
        help="Path to raw markdown export (*.md) with Telegram members table.",
    )
    parser.add_argument(
        "--directory",
        required=True,
        help="Target directory for safe outputs/history/review files.",
    )
    return parser


def _print_result(*, safe_count: int, safe_md: Path, safe_txt: Path, review_count: int, review_path: Path | None, conflicts_path: Path | None) -> None:
    print(f"safe_count={safe_count}")
    print(f"safe_md={safe_md}")
    print(f"safe_txt={safe_txt}")
    print(f"review_count={review_count}")
    print(f"review_path={review_path if review_path else ''}")
    print(f"conflicts_path={conflicts_path if conflicts_path else ''}")


def main() -> int:
    args = build_parser().parse_args()
    source_md = Path(args.source_md).expanduser()
    target_dir = Path(args.directory).expanduser()
    target_dir.mkdir(parents=True, exist_ok=True)

    if not source_md.exists():
        raise FileNotFoundError(f"source markdown not found: {source_md}")

    module = _load_batches_module(Path(__file__).resolve().parent)

    rows = module.load_markdown_member_rows(source_md)
    records = [
        module.MemberRecord(peer_id=row.peer_id, name=row.name, username=row.username)
        for row in rows
    ]
    history: dict[str, Any] = module.load_history(target_dir)
    safe_usernames, conflicts, next_history = module.evaluate_identity_records(records, history)
    safe_md, safe_txt, safe_count = module.write_safe_outputs(target_dir, rows, safe_usernames)
    review_txt, conflicts_json = module.write_review_files(target_dir, conflicts)
    module.save_history(target_dir, next_history)

    _print_result(
        safe_count=int(safe_count),
        safe_md=safe_md,
        safe_txt=safe_txt,
        review_count=len(conflicts),
        review_path=review_txt,
        conflicts_path=conflicts_json,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
