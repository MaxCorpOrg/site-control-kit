#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
PROJECT_VERSION_RE = re.compile(
    r"^\[project\]\s*$.*?^version\s*=\s*[\"']([^\"']+)[\"']",
    re.MULTILINE | re.DOTALL,
)

REQUIRED_DOCUMENTS = (
    "README.md",
    "USER_GUIDE_RU.md",
    "START_HERE_AGENT_RU.md",
    "docs/ARCHITECTURE.md",
    "docs/API.md",
    "docs/SECURITY.md",
    "docs/TROUBLESHOOTING.md",
    "docs/PROJECT_STATUS_RU.md",
    "docs/ROADMAP_RU.md",
    "docs/TERMS_RU.md",
)

# Это папки, где агент самостоятельно меняет исходники, проверки, настройки
# или нормативную документацию. Generated/runtime-папки сюда не входят.
WORKING_DIRECTORIES = (
    ".github",
    ".github/workflows",
    "config",
    "docs",
    "docs/adr",
    "docs/agent_handoff_ru",
    "docs/checkpoints",
    "docs/reports",
    "docs/research",
    "examples",
    "extension",
    "packaging",
    "packaging/linux",
    "resources",
    "resources/branding",
    "resources/icons",
    "scripts",
    "scripts/telegram_gui",
    "scripts/telegram_gui/adapters",
    "scripts/telegram_gui/services",
    "scripts/telegram_gui/ui",
    "tests",
    "tests/js",
    "webcontrol",
)

CLI_DOCUMENTS = (
    "README.md",
    "USER_GUIDE_RU.md",
    "START_HERE_AGENT_RU.md",
    "BROWSER_QUICKSTART.md",
    "docs/AI_MAINTAINER_GUIDE.md",
    "docs/INSTALL_OTHER_DEVICES_RU.md",
    "docs/PROJECT_WORKFLOW_RU.md",
    "docs/SERVER_BROWSER_ACCESS.md",
    "docs/TROUBLESHOOTING.md",
    "docs/WINDOWS_SMOKE_HANDOFF_RU.md",
    "docs/agent_handoff_ru/05_STATE_AND_ARTIFACTS.md",
    "docs/agent_handoff_ru/06_AGENT_WORKFLOW_AND_OPERATIONS.md",
)

REQUIRED_ROOT_COMMANDS = {
    "serve",
    "runtime-env",
    "health",
    "state",
    "clients",
    "send",
    "wait",
    "cancel",
    "session",
    "storage",
    "browser",
}
REQUIRED_BROWSER_COMMANDS = {
    "status",
    "clients",
    "tabs",
    "schema",
    "open",
    "new-tab",
    "snapshot",
    "smart-click",
    "set-text",
    "wait-for",
    "screenshot",
}

NUMERIC_OPTIONS = {
    "--tab-id",
    "--frame-id",
    "--timeout",
    "--timeout-ms",
    "--command-timeout-ms",
    "--ttl-seconds",
    "--limit",
    "--wait",
}


def finding(
    file: str,
    kind: str,
    *,
    line: int = 0,
    target: str = "",
) -> dict[str, str | int]:
    return {"file": file, "line": line, "kind": kind, "target": target}


def _git_paths(*args: str) -> list[str]:
    result = subprocess.run(
        ["git", *args, "-z"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    return [
        item.decode("utf-8", errors="strict")
        for item in result.stdout.split(b"\0")
        if item
    ]


def markdown_files(base: str | None) -> list[Path]:
    names: set[str] = set()
    if base:
        try:
            names.update(
                _git_paths(
                    "diff",
                    "--name-only",
                    "--diff-filter=ACMR",
                    f"{base}...HEAD",
                )
            )
        except subprocess.CalledProcessError:
            names.update(_git_paths("ls-files", "*.md"))
        names.update(_git_paths("diff", "--name-only", "--diff-filter=ACMR"))
        names.update(
            _git_paths("diff", "--cached", "--name-only", "--diff-filter=ACMR")
        )
    else:
        names.update(_git_paths("ls-files", "*.md"))
    names.update(_git_paths("ls-files", "--others", "--exclude-standard", "*.md"))
    return [
        ROOT / name
        for name in sorted(names)
        if name.endswith(".md") and (ROOT / name).is_file()
    ]


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
                    finding(
                        path.relative_to(ROOT).as_posix(),
                        "link_outside_repository",
                        line=line_number,
                        target=target,
                    )
                )
                continue
            if not resolved.exists():
                findings.append(
                    finding(
                        path.relative_to(ROOT).as_posix(),
                        "broken_link",
                        line=line_number,
                        target=target,
                    )
                )
    return findings


def check_required_documents() -> list[dict[str, str | int]]:
    return [
        finding(path, "missing_required_document", target=path)
        for path in REQUIRED_DOCUMENTS
        if not (ROOT / path).is_file()
    ]


def check_agent_instructions() -> list[dict[str, str | int]]:
    findings: list[dict[str, str | int]] = []
    paths = [Path(".")] + [Path(item) for item in WORKING_DIRECTORIES]
    seen_contents: dict[str, str] = {}
    for directory in paths:
        if directory != Path(".") and not (ROOT / directory).is_dir():
            findings.append(
                finding(
                    directory.as_posix(),
                    "missing_working_directory",
                    target=directory.as_posix(),
                )
            )
            continue
        instruction = ROOT / directory / "AGENTS.md"
        relative = instruction.relative_to(ROOT).as_posix()
        if not instruction.is_file():
            findings.append(
                finding(relative, "missing_agent_instruction", target=relative)
            )
            continue
        text = instruction.read_text(encoding="utf-8")
        lowered = text.lower()
        required_meanings = {
            "purpose": ("назначен", "цель"),
            "checks": ("провер",),
            "limitations": ("огранич", "запрещ", "не "),
            "errors": ("ошиб",),
        }
        for label, markers in required_meanings.items():
            if not any(marker in lowered for marker in markers):
                findings.append(
                    finding(
                        relative,
                        "incomplete_agent_instruction",
                        target=label,
                    )
                )
        normalized = re.sub(r"\s+", " ", lowered).strip()
        duplicate = seen_contents.get(normalized)
        if duplicate:
            findings.append(
                finding(
                    relative,
                    "duplicate_agent_instruction",
                    target=duplicate,
                )
            )
        else:
            seen_contents[normalized] = relative
    return findings


def check_versions() -> list[dict[str, str | int]]:
    from webcontrol.protocol import (
        AGENT_API_VERSION,
        HUB_PROTOCOL_VERSION,
        STORAGE_SCHEMA_VERSION,
    )

    manifest = json.loads(
        (ROOT / "extension" / "manifest.json").read_text(encoding="utf-8")
    )
    project_text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    project_match = PROJECT_VERSION_RE.search(project_text)
    project_version = project_match.group(1) if project_match else ""
    api_path = ROOT / "docs" / "API.md"
    if not api_path.exists():
        return []
    api = api_path.read_text(encoding="utf-8")
    markers = {
        "protocol_version_mismatch": f"Версия протокола: `{HUB_PROTOCOL_VERSION}`",
        "agent_api_version_mismatch": f"Версия агентного API: `{AGENT_API_VERSION}`",
        "extension_version_mismatch": (
            f"Версия расширения: `{manifest['version']}`"
        ),
        "cli_version_mismatch": f"Версия CLI: `{project_version}`",
        "storage_schema_version_mismatch": (
            f"Версия схемы хранилища: `{STORAGE_SCHEMA_VERSION}`"
        ),
    }
    return [
        finding("docs/API.md", kind, target=marker)
        for kind, marker in markers.items()
        if marker not in api
    ]


def _subcommand_names(parser: argparse.ArgumentParser) -> set[str]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return set(action.choices)
    return set()


def check_required_cli_commands() -> list[dict[str, str | int]]:
    from webcontrol.cli import build_parser

    parser = build_parser()
    root_commands = _subcommand_names(parser)
    browser_parser = next(
        action.choices["browser"]
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    browser_commands = _subcommand_names(browser_parser)
    findings = [
        finding(
            "webcontrol/cli.py",
            "missing_required_cli_command",
            target=command,
        )
        for command in sorted(REQUIRED_ROOT_COMMANDS - root_commands)
    ]
    findings.extend(
        finding(
            "webcontrol/cli.py",
            "missing_required_browser_command",
            target=command,
        )
        for command in sorted(REQUIRED_BROWSER_COMMANDS - browser_commands)
    )
    return findings


def _cli_args_from_line(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith(("#", "$")):
        return None
    if any(marker in stripped for marker in ("&&", "||", "| ", "$(")):
        return None
    try:
        tokens = shlex.split(stripped)
    except ValueError:
        return None
    while tokens and "=" in tokens[0] and not tokens[0].startswith("-"):
        tokens.pop(0)
    if not tokens:
        return None
    if tokens[0] == "sitectl":
        args = tokens[1:]
    elif "-m" in tokens:
        module_index = tokens.index("-m")
        if module_index + 1 >= len(tokens) or tokens[module_index + 1] != "webcontrol":
            return None
        args = tokens[module_index + 2 :]
    else:
        return None
    normalized: list[str] = []
    for token in args:
        if token.startswith("<") and token.endswith(">"):
            previous = normalized[-1] if normalized else ""
            normalized.append("1" if previous in NUMERIC_OPTIONS else "значение")
        else:
            normalized.append(token)
    return normalized


def check_documented_cli_syntax() -> list[dict[str, str | int]]:
    from webcontrol.cli import build_parser

    parser = build_parser()
    findings: list[dict[str, str | int]] = []
    for relative in CLI_DOCUMENTS:
        path = ROOT / relative
        if not path.is_file():
            continue
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            args = _cli_args_from_line(line)
            if args is None:
                continue
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
                io.StringIO()
            ):
                try:
                    parser.parse_args(args)
                except SystemExit as exc:
                    if exc.code == 0:
                        continue
                    findings.append(
                        finding(
                            relative,
                            "stale_or_invalid_cli_command",
                            line=line_number,
                            target=line.strip(),
                        )
                    )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Проверка ссылок, инструкций, команд и версий документации"
    )
    parser.add_argument("--base")
    parser.add_argument("--report")
    args = parser.parse_args(argv)

    files = markdown_files(args.base)
    findings = [item for path in files for item in check_links(path)]
    findings.extend(check_required_documents())
    findings.extend(check_agent_instructions())
    findings.extend(check_versions())
    findings.extend(check_required_cli_commands())
    findings.extend(check_documented_cli_syntax())

    report = {
        "checked_files": len(files),
        "checked_agent_directories": len(WORKING_DIRECTORIES) + 1,
        "checked_cli_documents": len(CLI_DOCUMENTS),
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
    print(
        "Документация проверена: "
        f"{len(files)} файлов, {len(WORKING_DIRECTORIES) + 1} папок агентов, "
        f"{len(CLI_DOCUMENTS)} файлов с командами."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
