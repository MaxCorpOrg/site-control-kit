from __future__ import annotations

import json
from pathlib import Path

from .models import MessagePolicy, SessionSettings, SyncSource, Target, ToolConfig


def _parse_bool(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"unsupported boolean value: {value}")


def _parse_allowed_actions(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple, set, frozenset)):
        items = value
    else:
        items = str(value).split(",")
    normalized = [str(item).strip() for item in items if str(item).strip()]
    return tuple(dict.fromkeys(normalized))


def _load_targets(
    raw_items: list[dict],
    *,
    kind: str | None = None,
    default_source: str = "manual",
    default_allowed_actions: tuple[str, ...] = (),
) -> list[Target]:
    targets: list[Target] = []
    for index, item in enumerate(raw_items, start=1):
        resolved_kind = str(item.get("kind") or kind or "contact").strip().lower()
        if resolved_kind not in {"group", "contact"}:
            raise ValueError(f"unsupported target kind: {resolved_kind}")
        handle = str(item["handle"])
        target_id = str(item.get("target_id") or f"{resolved_kind}_{index}")
        label = str(item.get("label") or handle)
        allowed_actions = _parse_allowed_actions(item.get("allowed_actions")) or default_allowed_actions
        targets.append(
            Target(
                target_id=target_id,
                label=label,
                handle=handle,
                kind=resolved_kind,  # type: ignore[arg-type]
                source=str(item.get("source") or default_source),
                allowed_actions=allowed_actions,
                consent_confirmed=_parse_bool(item.get("consent_confirmed"), default=True),
            )
        )
    return targets


def sample_config_payload() -> dict:
    return {
        "version": 1,
        "tool_name": "Telegram Portable Session Tool",
        "site_control_kit_root": "",
        "portable_profile_dir": "",
        "python_bin": "python3",
        "session": {
            "max_group_views_per_run": 3,
            "max_contact_views_per_run": 3,
            "view_min_seconds": 3,
            "view_max_seconds": 6,
            "visit_mode": "current_profile_sidebar",
            "random_walk_visits_per_run": 6,
            "sidebar_x_ratio": 0.14,
            "sidebar_y_min_ratio": 0.18,
            "sidebar_y_max_ratio": 0.82,
            "message_input_x_ratio": 0.55,
            "message_input_y_ratio": 0.975,
            "message_open_delay_seconds": 1.0,
            "message_focus_delay_seconds": 0.4,
            "message_send_delay_seconds": 0.2,
            "message_send_button_x_ratio": 0.962,
            "message_send_button_y_ratio": 0.94,
            "message_send_strategy": "send_button_then_return",
        },
        "message_policy": {
            "target_mode": "rotating_contacts",
            "drafts_per_run": 2,
            "auto_send": False,
            "total_message_limit": 0,
            "templates": [
                "Позвоню?",
                "Ты где?",
                "Добрый день!",
                "Хорошего дня!",
            ],
            "message_targets": [
                {
                    "target_id": "example_contact",
                    "label": "Example Contact",
                    "handle": "@example_contact",
                    "kind": "contact",
                }
            ],
        },
        "sync_sources": [],
        "groups": [],
        "contacts": [],
    }


def write_sample_config(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sample_config_payload(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_config(path: Path) -> ToolConfig:
    payload = json.loads(path.read_text(encoding="utf-8"))
    groups = _load_targets(payload.get("groups", []), kind="group")
    contacts = _load_targets(payload.get("contacts", []), kind="contact")
    session_raw = payload.get("session", {})
    message_raw = payload.get("message_policy", {})
    sync_raw = payload.get("sync_sources", [])
    target_username = str(message_raw.get("target_username") or "").strip()
    target_mode = str(message_raw.get("target_mode") or "").strip() or ("fixed" if target_username else "rotating_contacts")
    return ToolConfig(
        version=int(payload.get("version", 1)),
        tool_name=str(payload.get("tool_name") or "Telegram Portable Session Tool"),
        site_control_kit_root=str(payload["site_control_kit_root"]),
        portable_profile_dir=str(payload["portable_profile_dir"]),
        python_bin=str(payload.get("python_bin") or "python3"),
        session=SessionSettings(
            max_group_views_per_run=int(session_raw.get("max_group_views_per_run", 3)),
            max_contact_views_per_run=int(session_raw.get("max_contact_views_per_run", 3)),
            view_min_seconds=int(session_raw.get("view_min_seconds", 3)),
            view_max_seconds=int(session_raw.get("view_max_seconds", 6)),
            visit_mode=str(session_raw.get("visit_mode") or "explicit_targets"),  # type: ignore[arg-type]
            random_walk_visits_per_run=int(session_raw.get("random_walk_visits_per_run", 6)),
            sidebar_x_ratio=float(session_raw.get("sidebar_x_ratio", 0.14)),
            sidebar_y_min_ratio=float(session_raw.get("sidebar_y_min_ratio", 0.18)),
            sidebar_y_max_ratio=float(session_raw.get("sidebar_y_max_ratio", 0.82)),
            message_input_x_ratio=float(session_raw.get("message_input_x_ratio", 0.55)),
            message_input_y_ratio=float(session_raw.get("message_input_y_ratio", 0.975)),
            message_open_delay_seconds=float(session_raw.get("message_open_delay_seconds", 1.0)),
            message_focus_delay_seconds=float(session_raw.get("message_focus_delay_seconds", 0.4)),
            message_send_delay_seconds=float(session_raw.get("message_send_delay_seconds", 0.2)),
            message_send_button_x_ratio=float(session_raw.get("message_send_button_x_ratio", 0.962)),
            message_send_button_y_ratio=float(session_raw.get("message_send_button_y_ratio", 0.94)),
            message_send_strategy=str(session_raw.get("message_send_strategy") or "send_button_then_return"),  # type: ignore[arg-type]
        ),
        message_policy=MessagePolicy(
            target_username=target_username,
            target_mode=target_mode,  # type: ignore[arg-type]
            drafts_per_run=int(message_raw.get("drafts_per_run", 2)),
            auto_send=_parse_bool(message_raw.get("auto_send"), default=False),
            total_message_limit=int(message_raw.get("total_message_limit", 0)),
            templates=[str(item) for item in message_raw.get("templates", []) if str(item).strip()],
            message_targets=_load_targets(
                message_raw.get("message_targets", []),
                default_source="message_policy",
                default_allowed_actions=("send_message",),
            ),
        ),
        sync_sources=[
            SyncSource(
                source_type=str(item["source_type"]),  # type: ignore[arg-type]
                path=str(item["path"]),
                enabled=_parse_bool(item.get("enabled"), default=True),
                include_groups=_parse_bool(item.get("include_groups"), default=True),
                include_contacts=_parse_bool(item.get("include_contacts"), default=True),
            )
            for item in sync_raw
        ],
        groups=groups,
        contacts=contacts,
    )
