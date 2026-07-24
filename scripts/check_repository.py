#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PREFIXES = (
    ".site-control-kit/",
    "artifacts/",
    "runtime/",
    "var/",
    "chrome-profile/",
    "browser-profile/",
)
FORBIDDEN_BINARY_SUFFIXES = {
    ".7z",
    ".bin",
    ".deb",
    ".dmg",
    ".exe",
    ".msi",
    ".rar",
    ".tar",
    ".tgz",
    ".whl",
    ".zip",
}
SECRET_PATTERNS = (
    ("закрытый ключ", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    (
        "токен GitHub",
        re.compile(r"\b(?:gh[opusr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b"),
    ),
    ("ключ AWS", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("токен Slack", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
)
PRIVATE_PATH_RE = re.compile(r"/home/(?!user(?:/|$)|max(?:/site-control-kit)?(?:/|$))[^/\s`]+/")
PUBLIC_IP_RE = re.compile(
    r"\b(?!(?:127|10|0)\.)(?!(?:192\.168|169\.254)\.)(?!172\.(?:1[6-9]|2\d|3[01])\.)"
    r"(?:\d{1,3}\.){3}\d{1,3}\b"
)


def git_lines(*args: str) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def selected_files(base: str | None) -> list[Path]:
    if base:
        try:
            names = git_lines("diff", "--name-only", "--diff-filter=ACMR", f"{base}...HEAD")
        except subprocess.CalledProcessError:
            names = git_lines("ls-files")
    else:
        names = git_lines("ls-files")
    return [ROOT / name for name in names if (ROOT / name).is_file()]


def scan(path: Path) -> list[dict[str, str | int]]:
    relative = path.relative_to(ROOT).as_posix()
    findings: list[dict[str, str | int]] = []
    if relative.startswith(FORBIDDEN_PREFIXES):
        findings.append({"file": relative, "kind": "runtime_path", "line": 0})
    if path.suffix.lower() in FORBIDDEN_BINARY_SUFFIXES:
        findings.append({"file": relative, "kind": "binary_extension", "line": 0})
    if path.stat().st_size > 2 * 1024 * 1024:
        findings.append({"file": relative, "kind": "oversized_file", "line": 0})
    raw = path.read_bytes()
    if b"\0" in raw[:8192]:
        findings.append({"file": relative, "kind": "binary_content", "line": 0})
        return findings
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        findings.append({"file": relative, "kind": "non_utf8_text", "line": 0})
        return findings
    for line_number, line in enumerate(text.splitlines(), start=1):
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(line):
                findings.append({"file": relative, "kind": label, "line": line_number})
        if path.suffix.lower() == ".md":
            if PRIVATE_PATH_RE.search(line):
                findings.append(
                    {"file": relative, "kind": "private_absolute_path", "line": line_number}
                )
            ip_match = PUBLIC_IP_RE.search(line)
            if ip_match and not ip_match.group(0).startswith(
                ("192.0.2.", "198.51.100.", "203.0.113.")
            ):
                findings.append(
                    {"file": relative, "kind": "public_ip_in_docs", "line": line_number}
                )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Проверка репозитория перед слиянием")
    parser.add_argument("--base", help="Базовая ветка или SHA; без неё проверяются все файлы")
    parser.add_argument("--report", help="Куда записать JSON-отчёт")
    args = parser.parse_args(argv)
    findings = [finding for path in selected_files(args.base) for finding in scan(path)]
    report = {
        "checked_files": len(selected_files(args.base)),
        "findings": findings,
        "ok": not findings,
    }
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
    print(f"Проверка репозитория пройдена: {report['checked_files']} файлов.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
