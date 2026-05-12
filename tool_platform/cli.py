from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from typing import Any

from .agent_state import ensure_agent_state, load_agent_state
from .catalog import (
    DEFAULT_REGISTRY_PATH,
    ToolAction,
    ToolCatalog,
    ToolManifest,
    catalog_to_dict,
    find_action,
    find_tool,
    load_catalog,
    tool_platform_support,
)
from .jobs import get_job, list_jobs, repair_historical_artifacts, repair_invite_artifacts, repair_session_artifacts
from .locks import list_profile_locks
from .platform_adapters import (
    current_platform_id,
    platform_capabilities,
    platform_capability_warnings,
    platform_doctor_report,
)
from .workflows import artifacts_workflow, profile_health, resume_workflow, stop_workflow_job


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
    subparsers.add_parser("doctor", help="Show current platform doctor report for the Telegram control layer.")
    subparsers.add_parser("capabilities", help="Show current platform capabilities snapshot.")
    subparsers.add_parser("show-agent-state", help="Show persistent machine-readable agent state.")
    list_jobs_parser = subparsers.add_parser("list-jobs", help="Show recent unified Telegram jobs.")
    list_jobs_parser.add_argument("--profile-name")
    list_jobs_parser.add_argument("--profile-dir")
    list_jobs_parser.add_argument("--workflow-kind")
    list_jobs_parser.add_argument("--status")
    list_jobs_parser.add_argument("--limit", type=int, default=20)

    show_job = subparsers.add_parser("show-job", help="Show one unified Telegram job by id.")
    show_job.add_argument("--job-id", required=True)

    show_artifacts = subparsers.add_parser("show-artifacts", help="Show aggregated artifact index for one job.")
    show_artifacts.add_argument("--job-id", required=True)

    repair_session = subparsers.add_parser(
        "repair-session-artifacts",
        help="Preview or backfill legacy session artifact_paths in the unified Telegram job index.",
    )
    repair_session.add_argument("--job-id")
    repair_session.add_argument("--profile-name")
    repair_session.add_argument("--profile-dir")
    repair_session.add_argument("--apply", action="store_true")

    repair_invite = subparsers.add_parser(
        "repair-invite-artifacts",
        help="Preview or backfill legacy invite/combined invite artifact_paths in the unified Telegram job index.",
    )
    repair_invite.add_argument("--job-id")
    repair_invite.add_argument("--profile-name")
    repair_invite.add_argument("--profile-dir")
    repair_invite.add_argument("--apply", action="store_true")

    repair_historical = subparsers.add_parser(
        "repair-historical-artifacts",
        help="Preview or backfill legacy invite/session/combined artifact_paths in the unified Telegram job index.",
    )
    repair_historical.add_argument("--job-id")
    repair_historical.add_argument("--profile-name")
    repair_historical.add_argument("--profile-dir")
    repair_historical.add_argument("--apply", action="store_true")

    stop_job = subparsers.add_parser("stop-job", help="Mark one unified Telegram workflow job as stopped.")
    stop_job.add_argument("--job-id", required=True)
    stop_job.add_argument("--summary", default="Остановлено оператором")

    resume_job = subparsers.add_parser("resume-job", help="Resolve the next command for one unified Telegram workflow job.")
    resume_job.add_argument("--job-id", required=True)

    profile_health = subparsers.add_parser("profile-health", help="Show current workspace and health for one Telegram profile.")
    profile_health.add_argument("--profile-name", required=True)
    profile_health.add_argument("--profile-dir", required=True)

    subparsers.add_parser("list-locks", help="Show active Telegram profile locks.")

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
    if tool.supported_platforms:
        lines.append(f"supported_platforms: {', '.join(tool.supported_platforms)}")
    if tool.required_capabilities:
        lines.append(f"required_capabilities: {', '.join(tool.required_capabilities)}")
    if tool.degraded_modes:
        lines.append("degraded_modes:")
        for platform_id, detail in sorted(tool.degraded_modes.items()):
            lines.append(f"  - {platform_id}: {detail}")
    support = tool_platform_support(tool)
    lines.append(
        "current_platform_support: "
        + ("supported" if support["supported"] else "not_supported")
        + f" ({support['platform_id']})"
    )
    if support["missing_capabilities"]:
        lines.append(f"missing_capabilities: {', '.join(support['missing_capabilities'])}")
    if support["degraded_mode"]:
        lines.append(f"degraded_mode_now: {support['degraded_mode']}")
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
        support = tool_platform_support(tool)
        support_label = "supported" if support["supported"] else "not_supported"
        print(
            "\t".join(
                [
                    tool.tool_id,
                    tool.display_name,
                    tool.kind,
                    standalone,
                    tool.source_label,
                    support_label,
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


def _cmd_doctor(catalog: ToolCatalog) -> int:
    report = platform_doctor_report()
    report["current_platform_id"] = current_platform_id()
    report["tools"] = {
        tool.tool_id: tool_platform_support(tool, report["current_platform_id"])
        for tool in catalog.tools
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def _cmd_capabilities(catalog: ToolCatalog) -> int:
    payload = {
        "platform_id": current_platform_id(),
        "capabilities": platform_capabilities(),
        "warnings": platform_capability_warnings(),
        "tools": {
            tool.tool_id: tool_platform_support(tool)
            for tool in catalog.tools
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _cmd_show_agent_state() -> int:
    ensure_agent_state()
    print(json.dumps(load_agent_state(), ensure_ascii=False, indent=2))
    return 0


def _cmd_list_jobs(
    *,
    profile_name: str | None = None,
    profile_dir: str | None = None,
    workflow_kind: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> int:
    print(
        json.dumps(
            {
                "jobs": list_jobs(
                    profile_name=profile_name,
                    profile_dir=profile_dir,
                    workflow_kind=workflow_kind,
                    status=status,
                    limit=limit,
                )
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _cmd_show_job(job_id: str) -> int:
    payload = get_job(job_id)
    if payload is None:
        print(json.dumps({"status": "missing", "job_id": job_id}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _cmd_show_artifacts(job_id: str) -> int:
    try:
        payload = artifacts_workflow(job_id)
    except KeyError:
        print(json.dumps({"status": "missing", "job_id": job_id}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _cmd_repair_session_artifacts(
    *,
    job_id: str | None,
    profile_name: str | None,
    profile_dir: str | None,
    apply: bool,
) -> int:
    payload = repair_session_artifacts(
        job_id=job_id,
        profile_name=profile_name,
        profile_dir=profile_dir,
        apply=apply,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _cmd_repair_invite_artifacts(
    *,
    job_id: str | None,
    profile_name: str | None,
    profile_dir: str | None,
    apply: bool,
) -> int:
    payload = repair_invite_artifacts(
        job_id=job_id,
        profile_name=profile_name,
        profile_dir=profile_dir,
        apply=apply,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _cmd_repair_historical_artifacts(
    *,
    job_id: str | None,
    profile_name: str | None,
    profile_dir: str | None,
    apply: bool,
) -> int:
    payload = repair_historical_artifacts(
        job_id=job_id,
        profile_name=profile_name,
        profile_dir=profile_dir,
        apply=apply,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _cmd_stop_job(job_id: str, summary: str) -> int:
    try:
        payload = stop_workflow_job(job_id, summary=summary)
    except KeyError:
        print(json.dumps({"status": "missing", "job_id": job_id}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _cmd_resume_job(job_id: str) -> int:
    try:
        payload = resume_workflow(job_id)
    except KeyError:
        print(json.dumps({"status": "missing", "job_id": job_id}, ensure_ascii=False, indent=2))
        return 1
    command = payload.get("command")
    step = payload.get("step") if isinstance(payload.get("step"), dict) else {}
    serializable = dict(payload)
    if command is not None:
        serializable["command"] = {
            "argv": list(command.argv),
            "cwd": str(command.cwd),
        }
    if step:
        serializable["step"] = step
    print(json.dumps(serializable, ensure_ascii=False, indent=2))
    return 0


def _cmd_profile_health(profile_name_value: str, profile_dir_value: str) -> int:
    print(
        json.dumps(
            profile_health(profile_name=profile_name_value, profile_dir=profile_dir_value),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _cmd_list_locks() -> int:
    print(json.dumps({"locks": list_profile_locks()}, ensure_ascii=False, indent=2))
    return 0


def _cmd_run_action(catalog: ToolCatalog, tool_id: str, action_id: str, dry_run: bool) -> int:
    tool = find_tool(catalog, tool_id)
    support = tool_platform_support(tool)
    if not support["supported"]:
        print(
            json.dumps(
                {
                    "status": "unsupported",
                    "tool_id": tool.tool_id,
                    "platform_id": support["platform_id"],
                    "missing_capabilities": support["missing_capabilities"],
                    "degraded_mode": support["degraded_mode"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
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
    if args.command == "doctor":
        return _cmd_doctor(catalog)
    if args.command == "capabilities":
        return _cmd_capabilities(catalog)
    if args.command == "show-agent-state":
        return _cmd_show_agent_state()
    if args.command == "list-jobs":
        return _cmd_list_jobs(
            profile_name=args.profile_name,
            profile_dir=args.profile_dir,
            workflow_kind=args.workflow_kind,
            status=args.status,
            limit=args.limit,
        )
    if args.command == "show-job":
        return _cmd_show_job(args.job_id)
    if args.command == "show-artifacts":
        return _cmd_show_artifacts(args.job_id)
    if args.command == "repair-session-artifacts":
        return _cmd_repair_session_artifacts(
            job_id=args.job_id,
            profile_name=args.profile_name,
            profile_dir=args.profile_dir,
            apply=bool(args.apply),
        )
    if args.command == "repair-invite-artifacts":
        return _cmd_repair_invite_artifacts(
            job_id=args.job_id,
            profile_name=args.profile_name,
            profile_dir=args.profile_dir,
            apply=bool(args.apply),
        )
    if args.command == "repair-historical-artifacts":
        return _cmd_repair_historical_artifacts(
            job_id=args.job_id,
            profile_name=args.profile_name,
            profile_dir=args.profile_dir,
            apply=bool(args.apply),
        )
    if args.command == "stop-job":
        return _cmd_stop_job(args.job_id, args.summary)
    if args.command == "resume-job":
        return _cmd_resume_job(args.job_id)
    if args.command == "profile-health":
        return _cmd_profile_health(args.profile_name, args.profile_dir)
    if args.command == "list-locks":
        return _cmd_list_locks()
    if args.command == "run-action":
        return _cmd_run_action(catalog, args.tool_id, args.action_id, args.dry_run)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
