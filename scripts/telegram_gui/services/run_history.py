from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from ..models import RunRecord, SessionResumeState


class RunHistoryService:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.runs_dir = workspace_root / "runs"
        self.state_dir = workspace_root / "state"
        self.index_path = self.runs_dir / "index.jsonl"
        self.last_session_path = self.state_dir / "last_session.json"
        self.pinned_chats_path = self.state_dir / "pinned_chats.json"

    def ensure(self) -> None:
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def run_dir(self, run_id: str) -> Path:
        self.ensure()
        return self.runs_dir / run_id

    def run_summary_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "summary.json"

    def run_artifacts_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "artifacts.json"

    def run_events_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "events.jsonl"

    def append_run(self, record: RunRecord) -> None:
        self.ensure()
        with self.index_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_json(), ensure_ascii=False) + "\n")

    def write_run_summary(self, record: RunRecord) -> Path:
        path = self.run_summary_path(record.run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record.to_json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def write_run_artifacts(self, record: RunRecord) -> Path:
        path = self.run_artifacts_path(record.run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record.artifacts.to_json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def list_recent(self, *, limit: int = 20) -> list[RunRecord]:
        self.ensure()
        if not self.index_path.exists():
            return []
        rows: list[RunRecord] = []
        for line in self.index_path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(RunRecord.from_json(payload))
        return list(reversed(rows[-max(limit, 1) :]))

    def save_last_session(self, session: SessionResumeState) -> None:
        self.ensure()
        self.last_session_path.write_text(
            json.dumps(session.to_json(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def load_last_session(self) -> SessionResumeState | None:
        self.ensure()
        if not self.last_session_path.exists():
            return None
        try:
            payload = json.loads(self.last_session_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        return SessionResumeState.from_json(payload)

    def load_pinned_chats(self) -> list[dict[str, str]]:
        self.ensure()
        if not self.pinned_chats_path.exists():
            return []
        try:
            payload = json.loads(self.pinned_chats_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        rows = payload.get("pinned_chats") if isinstance(payload, dict) else []
        return [row for row in rows if isinstance(row, dict)]

    def save_pinned_chats(self, rows: list[dict[str, str]]) -> None:
        self.ensure()
        self.pinned_chats_path.write_text(
            json.dumps({"pinned_chats": rows}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
