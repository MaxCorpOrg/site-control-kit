from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from webcontrol.runtime_logging import RuntimeEventLogger, append_jsonl, build_event_payload


@dataclass(frozen=True, slots=True)
class GuiRunArtifactPaths:
    run_dir: Path
    events_path: Path
    summary_path: Path
    artifacts_path: Path


class GuiRunLogger:
    def __init__(self, workspace_root: Path, runtime_logger: RuntimeEventLogger | None = None):
        self.workspace_root = workspace_root
        self.runtime_logger = runtime_logger
        self.runs_root = workspace_root / "runs"

    def paths_for(self, run_id: str) -> GuiRunArtifactPaths:
        run_dir = self.runs_root / run_id
        return GuiRunArtifactPaths(
            run_dir=run_dir,
            events_path=run_dir / "events.jsonl",
            summary_path=run_dir / "summary.json",
            artifacts_path=run_dir / "artifacts.json",
        )

    def append_run_event(
        self,
        run_id: str,
        *,
        event: str,
        profile: str = "",
        chat_ref: str = "",
        chat_title: str = "",
        status: str = "",
        message: str = "",
        level: str = "info",
        details: dict[str, Any] | None = None,
    ) -> Path:
        paths = self.paths_for(run_id)
        payload = build_event_payload(
            component="telegram_gui",
            event=event,
            level=level,
            run_id=run_id,
            profile=profile,
            chat_ref=chat_ref,
            chat_title=chat_title,
            status=status,
            message=message,
            details=details,
        )
        append_jsonl(paths.events_path, payload)
        if self.runtime_logger is not None:
            self.runtime_logger.log_event(
                component="telegram_gui",
                event=event,
                level=level,
                run_id=run_id,
                profile=profile,
                chat_ref=chat_ref,
                chat_title=chat_title,
                status=status,
                message=message,
                details=details,
            )
        return paths.events_path

    def write_summary(self, run_id: str, payload: dict[str, Any]) -> Path:
        paths = self.paths_for(run_id)
        paths.run_dir.mkdir(parents=True, exist_ok=True)
        paths.summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return paths.summary_path

    def write_artifacts(self, run_id: str, payload: dict[str, Any]) -> Path:
        paths = self.paths_for(run_id)
        paths.run_dir.mkdir(parents=True, exist_ok=True)
        paths.artifacts_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return paths.artifacts_path


def tail_text_file(path: Path | None, *, max_lines: int = 40) -> str:
    if path is None or not path.exists():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    if max_lines <= 0:
        return ""
    return "\n".join(lines[-max_lines:])
