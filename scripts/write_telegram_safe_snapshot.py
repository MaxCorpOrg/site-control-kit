#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path


def _load_batches_module():
    module_path = Path(__file__).resolve().with_name("telegram_contact_batches.py")
    spec = importlib.util.spec_from_file_location("telegram_contact_batches_module", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load helper module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build safe Telegram snapshot files from one markdown export."
    )
    parser.add_argument("--source-md", required=True, help="Markdown export from Telegram exporter")
    parser.add_argument("--directory", required=True, help="Output directory for latest_safe.* and review files")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    module = _load_batches_module()
    source_md = Path(args.source_md).expanduser()
    output_dir = Path(args.directory).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    history = module.load_history(output_dir)
    rows = module.load_markdown_member_rows(source_md)
    records = module.load_member_records_from_markdown(source_md)
    safe_usernames, conflicts, next_history = module.evaluate_identity_records(records, history)

    safe_md, safe_txt, safe_count = module.write_safe_outputs(output_dir, rows, safe_usernames)
    review_txt, conflicts_json = module.write_review_files(output_dir, conflicts)
    module.save_history(output_dir, next_history)

    print(f"safe_count={safe_count}")
    print(f"safe_md={safe_md}")
    print(f"safe_txt={safe_txt}")
    print(f"review_count={len(conflicts)}")
    print(f"review_path={review_txt if review_txt else ''}")
    print(f"conflicts_path={conflicts_json if conflicts_json else ''}")
    print(f"history_path={module.history_path(output_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
