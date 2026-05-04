from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .jobs import DEFAULT_TELEGRAM_STATE_ROOT


DEFAULT_WORKFLOW_STATE_ROOT = DEFAULT_TELEGRAM_STATE_ROOT / "panel_state"
LEGACY_PANEL_STATE_ROOT = Path("/tmp/telegram-control-center")


def _safe_slug(value: str, fallback: str) -> str:
    slug = "".join(char if char.isalnum() or char in "._-" else "_" for char in str(value or "").strip())
    slug = slug.strip("._-")
    return slug or fallback


def combined_flow_state_path(
    *,
    profile_name: str,
    profile_dir: str | Path,
    state_root: str | Path = DEFAULT_WORKFLOW_STATE_ROOT,
) -> Path:
    profile_slug = _safe_slug(profile_name, "profile")
    dir_name = Path(profile_dir).expanduser().resolve().name if str(profile_dir or "").strip() else "portable"
    dir_slug = _safe_slug(dir_name, "portable")
    return Path(state_root).expanduser().resolve() / "combined_flows" / f"{profile_slug}__{dir_slug}.json"


def migrate_legacy_combined_state(
    *,
    profile_name: str,
    profile_dir: str | Path,
    new_state_root: str | Path = DEFAULT_WORKFLOW_STATE_ROOT,
    legacy_state_root: str | Path = LEGACY_PANEL_STATE_ROOT,
) -> dict[str, Any] | None:
    target_path = combined_flow_state_path(
        profile_name=profile_name,
        profile_dir=profile_dir,
        state_root=new_state_root,
    )
    if target_path.exists():
        try:
            payload = json.loads(target_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    legacy_path = combined_flow_state_path(
        profile_name=profile_name,
        profile_dir=profile_dir,
        state_root=legacy_state_root,
    )
    if not legacy_path.exists():
        return None
    try:
        payload = json.loads(legacy_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload
