#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def markdown_files(base: str | None) -> list[Path]:
    if base:
        result = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=ACMR", f"{base}...HEAD"],
            cwd=ROOT,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        )
        names = result.stdout.splitlines()
    else:
        result = subprocess.run(
            ["git", "ls-files", "*.md"],
            cwd=ROOT,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        )
        names = result.stdout.splitlines()
    return [ROOT / name for name in names if name.endswith(".md") and (ROOT / name).is_file()]


def check_links(path: Path) -> list[dict[str, str | int]]:
    findings = []
    text = path.read_text(encoding="utf-8")
    for line_number, line in enumerate(text.splitlines(), start=1):
        for raw_target in LINK_RE.findall(line):
            target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
            if not target or target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            file_target = unquote(target.split("#", 1)[0])
            if not file_target:
                continue
            resolved = (path.parent / file_target).resolve()
            try:
                resolved.relative_to(ROOT)
            except ValueError:
                findings.append(
                    {
                        "file": path.relative_to(ROOT).as_posix(),
                        "line": line_number,
                        "kind": "link_outside_repository",
                        "target": target,
                    }
                )
                continue
            if not resolved.exists():
                findings.append(
                    {
                        "file": path.relative_to(ROOT).as_posix(),
                        "line": line_number,
                        "kind": "broken_link",
                        "target": target,
                    }
                )
    return findings


def check_versions() -> list[dict[str, str | int]]:
    manifest = json.loads((ROOT / "extension" / "manifest.json").read_text(encoding="utf-8"))
    version = str(manifest["version"])
    api_path = ROOT / "docs" / "API.md"
    if not api_path.exists():
        return []
    api = api_path.read_text(encoding="utf-8")
    marker = f"Версия расширения: `{version}`"
    if marker not in api:
        return [
            {
                "file": "docs/API.md",
                "line": 0,
                "kind": "extension_version_mismatch",
                "target": marker,
            }
        ]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Проверка ссылок и версий документации")
    parser.add_argument("--base")
    parser.add_argument("--report")
    args = parser.parse_args(argv)
    files = markdown_files(args.base)
    findings = [finding for path in files for finding in check_links(path)]
    findings.extend(check_versions())
    report = {"checked_files": len(files), "findings": findings, "ok": not findings}
    if args.report:
        destination = Path(args.report)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    if findings:
        print(json.dumps(report, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    print(f"Документация проверена: {len(files)} файлов.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
