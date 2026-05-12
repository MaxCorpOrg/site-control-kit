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
        "current_priority": "После закрытого historical backfill/provenance dry-run tranche продолжать deeper thinning gui.py / telegram_gui_helpers.py и docs as product; historical --apply делать только по явному операторскому решению.",
        "active_risks": [
            "AK5 на этой Wayland-машине теперь воспроизводимо поднимается через x11 backend (`QT_QPA_PLATFORM=xcb`), но attach gating остаётся строгим: live-safe только при `exact_window` или `title_match`, а preference `display_backend = x11` нельзя терять.",
            "Historical invite/session/combined backfill теперь имеет единый dry-run/report CLI, но живой `--apply` намеренно не запускался и остаётся отдельным операторским решением.",
            "AK3 live invite path на project-local профиле теперь уже подтверждён до 70 contact_added / 1416 new / 0 failed, но следующий реальный риск снова operational: выбирать controlled tranche и не уходить в длинный rollout без pause-point и живого лога.",
            "Session/combined readback уже invite-grade на уровне workspace snapshot и GUI; дальше не повторять этот tranche, а точечно утоньшать GUI/helpers и нормализовать docs.",
            "gui.py стал тоньше, но часть formatting/open-policy и readback/UI-связывания всё ещё полезно дальше выносить поверх jobs.py/workflows.py, чтобы GUI оставался чистым thin client.",
            "Session-runner code намеренно остаётся external repo; mutable data уже переведены в runtime/telegram/session, но этот boundary нужно держать явным и не размазывать бизнес-логику между репозиториями.",
            "Operator entry docs уже добавлены, но templates, examples и часть historical handoff всё ещё требуют дальнейшей нормализации под canonical runtime/telegram.",
            "Project-local AK3 иногда может приходить в состояние running_without_window после старого orphaned процесса; безопасный способ восстановления уже подтверждён как relaunch профиля, а не ослабление attach gating.",
            "Wayland-сессия у оператора усложняет attach-диагностику для новых portable-профилей: X11/AT-SPI сами по себе могут не подтвердить окно, даже когда приложение живо в desktop session.",
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
            "ak5_profile_dir": "/home/max/site-control-kit/runtime/telegram/profiles/TelegramPortable-AK5",
            "ak5_launch_log": "/home/max/site-control-kit/runtime/telegram/profiles/TelegramPortable-AK5/portable-launch.log",
            "ak5_telegram_log": "/home/max/site-control-kit/runtime/telegram/profiles/TelegramPortable-AK5/TelegramForcePortable/log.txt",
            "ak5_wayland_recovery_bundle": "/tmp/telegram-ak5-wayland-recovery-J72H7a",
            "ak5_status_after_launch": "/tmp/telegram-ak5-wayland-recovery-J72H7a/status-after-launch.json",
            "ak5_profile_health_after_launch": "/tmp/telegram-ak5-wayland-recovery-J72H7a/profile-health-after-launch.json",
            "session_combined_py_compile": "python3 -m py_compile tool_platform/gui.py tool_platform/telegram_gui_helpers.py tool_platform/jobs.py tool_platform/workflows.py tool_platform/agent_state.py scripts/telegram_portable.py tests/test_tool_platform.py",
            "session_combined_readback_tests": "PYTHONPATH=\"$PWD\" python3 -m unittest tests.test_tool_platform",
            "session_combined_full_tests": "PYTHONPATH=\"$PWD\" python3 -m unittest discover -s tests -p 'test_*.py'",
            "session_combined_diff_check": "git diff --check",
            "session_combined_panel_smoke": "timeout 10s ./tools/telegram/platform/bin/tool-platform-panel",
            "historical_backfill_dry_run": "./tools/telegram/platform/bin/tool-platform repair-historical-artifacts --profile-name AK --profile-dir /home/max/TelegramPortableAK",
            "historical_backfill_tests": "PYTHONPATH=\"$PWD\" python3 -m unittest tests.test_tool_platform",
            "historical_backfill_full_tests": "PYTHONPATH=\"$PWD\" python3 -m unittest discover -s tests -p 'test_*.py'",
            "ak3_controlled10_result": "/tmp/telegram-ak3-controlled10-rrH2bx/result.json",
            "ak3_pathfix_smoke_result": "/tmp/telegram-ak3-pathfix-smoke-te3fk5ga/result.json",
            "ak3_post_refactor_smoke_result": "/tmp/telegram-ak3-post-refactor-smoke-vqh2kbgb/result.json",
            "ak3_product_grade_smoke_result": "/tmp/telegram-ak3-product-grade-smoke-1o3xssvd/result.json",
        },
        "next_recommended_step": "После закрытого historical dry-run/report tranche продолжить deeper thinning gui.py / telegram_gui_helpers.py и docs as product; `repair-historical-artifacts --apply` запускать только по явному решению оператора после повторного preview.",
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
