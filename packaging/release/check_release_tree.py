from __future__ import annotations

import argparse
import re
from pathlib import Path


FORBIDDEN_PATH_PARTS = {".codex", "TG_APP", "telegram_ak", "runtime", ".git", "__pycache__"}
SECRET_PATTERNS = [
    re.compile(r"BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY"),
    re.compile(r"(?i)(api[_-]?key|bot[_-]?token|auth[_-]?token|password|secret)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}"),
]


def _is_text_file(path: Path) -> bool:
    try:
        path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False
    except OSError:
        return False
    return True


def _allowed_dev_path(path: Path) -> bool:
    parts = set(path.parts)
    if path.suffix.lower() in {".md", ".txt"}:
        return True
    return bool({"docs", "README.md", "BROWSER_QUICKSTART.md", "examples", "agent_pack"} & parts)


def scan_tree(root: Path) -> list[str]:
    errors: list[str] = []
    root = root.expanduser().resolve()
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if any(part in FORBIDDEN_PATH_PARTS for part in relative.parts):
            errors.append(f"forbidden path included: {relative}")
            continue
        if not path.is_file() or not _is_text_file(path):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "/home/max/" in text and not _allowed_dev_path(relative):
            errors.append(f"developer absolute path in runtime file: {relative}")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                errors.append(f"possible secret in {relative}: {pattern.pattern}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan release tree for private runtime data and obvious secrets.")
    parser.add_argument("root")
    args = parser.parse_args()
    errors = scan_tree(Path(args.root))
    if errors:
        for error in errors:
            print(error)
        return 1
    print("release tree scan ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
