from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from typing import Any

from .catalog import (
    DEFAULT_REGISTRY_PATH,
    ToolAction,
    ToolCatalog,
    ToolManifest,
    catalog_to_dict,
    find_action,
    find_tool,
    load_catalog,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tool-platform",
        description="Registry-driven Telegram control layer for embedded and standalone workflows.",
    )
    parser.add_argument(
        "--registry",
        default=str(DEFAULT_REGISTRY_PATH),
        help="Path to tool registry JSON.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-tools", help="List registered tools.")

    show_tool = subparsers.add_parser("show-tool", help="Show one tool entry.")
    show_tool.add_argument("--tool-id", required=True)

    subparsers.add_parser("validate-registry", help="Validate the registry and manifests.")
    subparsers.add_parser("dump-catalog", help="Dump fully resolved catalog as JSON.")

    run_action = subparsers.add_parser("run-action", help="Run or preview one registered action.")
    run_action.add_argument("--tool-id", required=True)
    run_action.add_argument("--action-id", required=True)
    run_action.add_argument("--dry-run", action="store_true")
    return parser


def _format_tool_lines(tool: ToolManifest) -> list[str]:
    lines = [
        f"{tool.display_name} [{tool.tool_id}]",
        f"kind: {tool.kind}",
        f"standalone: {str(tool.standalone).lower()}",
        f"source: {tool.source_label}",
        f"root_dir: {tool.root_dir}",
        f"manifest: {tool.manifest_path}",
    ]
    if tool.description:
        lines.append(f"description: {tool.description}")
    if tool.capabilities:
        lines.append(f"capabilities: {', '.join(tool.capabilities)}")
    if tool.tags:
        lines.append(f"tags: {', '.join(tool.tags)}")
    if tool.docs:
        lines.append("docs:")
        for doc in tool.docs:
            lines.append(f"  - {doc.label}: {doc.path}")
    if tool.actions:
        lines.append("actions:")
        for action in tool.actions:
            command = shlex.join(action.argv)
            lines.append(f"  - {action.action_id}: {action.label}")
            if action.description:
                lines.append(f"    {action.description}")
            lines.append(f"    cwd: {action.workdir}")
            lines.append(f"    cmd: {command}")
    if tool.artifacts:
        lines.append("artifacts:")
        for key, value in tool.artifacts.items():
            lines.append(f"  - {key}: {value}")
    return lines


def execute_action(action: ToolAction, dry_run: bool = False) -> dict[str, Any]:
    command = shlex.join(action.argv)
    result: dict[str, Any] = {
        "action_id": action.action_id,
        "command": command,
        "workdir": str(action.workdir),
        "capture_output": action.capture_output,
    }
    if dry_run:
        result["status"] = "dry_run"
        return result
    if action.capture_output:
        completed = subprocess.run(
            action.argv,
            cwd=action.workdir,
            check=False,
            capture_output=True,
            text=True,
        )
        result.update(
            {
                "status": "completed",
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
        )
        return result
    process = subprocess.Popen(action.argv, cwd=action.workdir)
    result.update({"status": "spawned", "pid": process.pid})
    return result


def _cmd_list_tools(catalog: ToolCatalog) -> int:
    for tool in catalog.tools:
        standalone = "standalone" if tool.standalone else "embedded"
        print(
            "\t".join(
                [
                    tool.tool_id,
                    tool.display_name,
                    tool.kind,
                    standalone,
                    tool.source_label,
                ]
            )
        )
    return 0


def _cmd_show_tool(catalog: ToolCatalog, tool_id: str) -> int:
    print("\n".join(_format_tool_lines(find_tool(catalog, tool_id))))
    return 0


def _cmd_validate_registry(catalog: ToolCatalog) -> int:
    print(
        f"Registry OK: {catalog.platform_name} ({len(catalog.tools)} tools) "
        f"[{catalog.registry_path}]"
    )
    return 0


def _cmd_dump_catalog(catalog: ToolCatalog) -> int:
    print(json.dumps(catalog_to_dict(catalog), ensure_ascii=False, indent=2))
    return 0


def _cmd_run_action(catalog: ToolCatalog, tool_id: str, action_id: str, dry_run: bool) -> int:
    tool = find_tool(catalog, tool_id)
    result = execute_action(find_action(tool, action_id), dry_run=dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("returncode", 0) == 0 else int(result["returncode"])


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    catalog = load_catalog(args.registry)
    if args.command == "list-tools":
        return _cmd_list_tools(catalog)
    if args.command == "show-tool":
        return _cmd_show_tool(catalog, args.tool_id)
    if args.command == "validate-registry":
        return _cmd_validate_registry(catalog)
    if args.command == "dump-catalog":
        return _cmd_dump_catalog(catalog)
    if args.command == "run-action":
        return _cmd_run_action(catalog, args.tool_id, args.action_id, args.dry_run)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
