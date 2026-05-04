from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from .jobs import DEFAULT_TELEGRAM_STATE_ROOT, now_utc


DEFAULT_AGENT_STATE_PATH = DEFAULT_TELEGRAM_STATE_ROOT / "agent" / "agent_state.json"


def default_agent_state() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "current_priority": "Воспроизвести и закрыть live баг Совместного режима в Telegram control center.",
        "active_risks": [
            "GUI Combined Mode ещё может расходиться с panel-harness.",
            "Orchestration add/session/combined всё ещё слишком привязана к gui.py.",
            "Linux live-path сильнее остальных ОС; Windows/macOS пока требуют adapter-first layering.",
        ],
        "default_decisions": {
            "agent_model": "runbook_plus_orchestration",
            "platform_support": "tiered",
            "first_major_stage_after_bugfix": "workflow_engine_and_job_store",
            "session_runner_runtime": "standalone_repo_contract",
            "persistent_state_root": str(DEFAULT_TELEGRAM_STATE_ROOT),
        },
        "last_verified_artifacts": {
            "project_status": "/home/max/site-control-kit/docs/PROJECT_STATUS_RU.md",
            "supertool_roadmap": "/home/max/site-control-kit/docs/TELEGRAM_SUPERTOOL_ROADMAP_RU.md",
            "next_chat_prompt": "/home/max/site-control-kit/tools/telegram/NEXT_CHAT_AGENT_PROMPT_RU.md",
        },
        "next_recommended_step": "Снять live лог Combined Mode в реальной панели, затем выносить workflow/job engine из gui.py.",
        "updated_at": "",
    }


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(path.parent)) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temp_path = Path(handle.name)
    temp_path.replace(path)
    return path


def load_agent_state(path: str | Path = DEFAULT_AGENT_STATE_PATH) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve()
    payload = _load_json(resolved)
    state = default_agent_state()
    state.update({key: value for key, value in payload.items() if key in state})
    return state


def save_agent_state(payload: dict[str, Any], path: str | Path = DEFAULT_AGENT_STATE_PATH) -> Path:
    resolved = Path(path).expanduser().resolve()
    state = default_agent_state()
    state.update({key: value for key, value in payload.items() if key in state})
    state["updated_at"] = now_utc()
    return _atomic_write_json(resolved, state)


def ensure_agent_state(path: str | Path = DEFAULT_AGENT_STATE_PATH) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        save_agent_state(default_agent_state(), resolved)
    return resolved
