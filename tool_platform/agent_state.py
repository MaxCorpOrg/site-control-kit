from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from .jobs import now_utc
from .telegram_runtime import LEGACY_STATE_ROOT, agent_state_path, preferred_read_path, state_root


DEFAULT_AGENT_STATE_PATH = agent_state_path()
LEGACY_AGENT_STATE_PATH = LEGACY_STATE_ROOT / "agent" / "agent_state.json"


def default_agent_state() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "current_priority": "После product-grade AK3 smoke и live apply для repair-invite-artifacts доводить session/combined parity до invite-grade, продолжать deeper thinning gui.py / telegram_gui_helpers.py и затем закрывать historical backfill + docs as product.",
        "active_risks": [
            "AK3 live invite path на project-local профиле теперь уже подтверждён до 70 contact_added / 1416 new / 0 failed, но следующий реальный риск снова operational: выбирать controlled tranche и не уходить в длинный rollout без pause-point и живого лога.",
            "Historical invite jobs на AK3 уже canonicalized через explicit repair, но session/combined historical continuity и provenance всё ещё нужно довести до такого же product-grade уровня.",
            "gui.py стал тоньше, но часть formatting/open-policy и readback/UI-связывания всё ещё полезно дальше выносить поверх jobs.py/workflows.py, чтобы GUI оставался чистым thin client.",
            "Session-runner code намеренно остаётся external repo; mutable data уже переведены в runtime/telegram/session, но этот boundary нужно держать явным и не размазывать бизнес-логику между репозиториями.",
            "Operator entry docs уже добавлены, но templates, examples и часть historical handoff всё ещё требуют дальнейшей нормализации под canonical runtime/telegram.",
            "Project-local AK3 иногда может приходить в состояние running_without_window после старого orphaned процесса; безопасный способ восстановления уже подтверждён как relaunch профиля, а не ослабление attach gating.",
            "Linux live-path сильнее остальных ОС; Windows/macOS пока требуют adapter-first layering.",
        ],
        "default_decisions": {
            "agent_model": "runbook_plus_orchestration",
            "platform_support": "tiered",
            "first_major_stage_after_bugfix": "workflow_engine_and_job_store",
            "session_runner_runtime": "standalone_repo_contract",
            "persistent_state_root": str(state_root()),
        },
        "last_verified_artifacts": {
            "project_status": "/home/max/site-control-kit/docs/PROJECT_STATUS_RU.md",
            "supertool_roadmap": "/home/max/site-control-kit/docs/TELEGRAM_SUPERTOOL_ROADMAP_RU.md",
            "next_chat_prompt": "/home/max/site-control-kit/tools/telegram/NEXT_CHAT_AGENT_PROMPT_RU.md",
            "operator_entry": "/home/max/site-control-kit/docs/TELEGRAM_CONTROL_CENTER_OPERATOR_RU.md",
            "maintainer_runbook": "/home/max/site-control-kit/docs/TELEGRAM_CONTROL_CENTER_RUNBOOK_RU.md",
            "runtime_checkpoint": "/home/max/site-control-kit/runtime/telegram/state/agent/workspace_checkpoint.json",
            "ak3_controlled10_result": "/tmp/telegram-ak3-controlled10-rrH2bx/result.json",
            "ak3_pathfix_smoke_result": "/tmp/telegram-ak3-pathfix-smoke-te3fk5ga/result.json",
            "ak3_post_refactor_smoke_result": "/tmp/telegram-ak3-post-refactor-smoke-vqh2kbgb/result.json",
            "ak3_product_grade_smoke_result": "/tmp/telegram-ak3-product-grade-smoke-1o3xssvd/result.json",
        },
        "next_recommended_step": "Сначала довести session/combined progress + recoverability до invite-grade на canonical runtime/telegram, затем продолжить deeper thinning gui.py / telegram_gui_helpers.py и после этого закрыть historical backfill и docs as product.",
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
    read_path = resolved
    if resolved == DEFAULT_AGENT_STATE_PATH:
        read_path = preferred_read_path(resolved, LEGACY_AGENT_STATE_PATH)
    payload = _load_json(read_path)
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
