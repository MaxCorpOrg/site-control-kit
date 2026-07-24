from __future__ import annotations

from typing import Any

from .protocol import AGENT_API_VERSION, HUB_PROTOCOL_VERSION, RETRY_POLICIES

LOCATOR_STRATEGIES = (
    "css",
    "ref",
    "role",
    "text",
    "label",
    "placeholder",
    "test_id",
)

WAIT_STATES = (
    "attached",
    "detached",
    "visible",
    "hidden",
    "enabled",
    "editable",
    "stable",
    "actionable",
    "text",
    "value",
)

FRAME_STRATEGIES = (
    "frame_id",
    "url",
    "name",
    "css",
)


def build_locator(
    *,
    selector: str | None = None,
    ref: str | None = None,
    role: str | None = None,
    name: str | None = None,
    text: str | None = None,
    label: str | None = None,
    placeholder: str | None = None,
    test_id: str | None = None,
    exact: bool = False,
    nth: int | None = None,
    root_selector: str | None = None,
    frame_id: int | None = None,
) -> dict[str, Any]:
    choices = [
        ("css", selector),
        ("ref", ref),
        ("role", role),
        ("text", text),
        ("label", label),
        ("placeholder", placeholder),
        ("test_id", test_id),
    ]
    selected = [
        (strategy, str(value).strip())
        for strategy, value in choices
        if value is not None and str(value).strip()
    ]
    if len(selected) != 1:
        raise ValueError(
            "Exactly one locator is required: --selector, --ref, --role, --text, "
            "--label, --placeholder, or --test-id"
        )
    strategy, value = selected[0]
    if name and strategy != "role":
        raise ValueError("--name can only be used with --role")
    if nth is not None and nth < 0:
        raise ValueError("--nth must be zero or greater")
    if frame_id is not None and frame_id < 0:
        raise ValueError("--frame-id must be zero or greater")

    locator: dict[str, Any] = {
        "strategy": strategy,
        "value": value,
        "exact": bool(exact),
    }
    if strategy == "role" and name:
        locator["name"] = str(name)
    if nth is not None:
        locator["nth"] = int(nth)
    if root_selector:
        locator["root_selector"] = str(root_selector)
    if frame_id is not None:
        locator["frame_id"] = int(frame_id)
    return locator


def build_locator_from_args(args: Any) -> dict[str, Any]:
    return build_locator(
        selector=getattr(args, "selector", None),
        ref=getattr(args, "ref", None),
        role=getattr(args, "role", None),
        name=getattr(args, "name", None),
        text=getattr(args, "locator_text", None),
        label=getattr(args, "label", None),
        placeholder=getattr(args, "placeholder", None),
        test_id=getattr(args, "test_id", None),
        exact=bool(getattr(args, "exact", False)),
        nth=getattr(args, "nth", None),
        root_selector=getattr(args, "root_selector", None),
        frame_id=getattr(args, "frame_id", None),
    )


def agent_api_schema() -> dict[str, Any]:
    locator = {
        "strategy": list(LOCATOR_STRATEGIES),
        "value": "string",
        "name": "optional accessible name; valid with strategy=role",
        "exact": "boolean; default false",
        "nth": "optional zero-based index; never selected implicitly",
        "root_selector": "optional CSS root",
        "frame_id": "optional browser frame identifier",
    }
    return {
        "schema_version": AGENT_API_VERSION,
        "protocol_version": HUB_PROTOCOL_VERSION,
        "transport": {
            "enqueue": "POST /api/commands",
            "lease": "GET /api/commands/next?client_id=...",
            "acknowledge": "POST /api/commands/{command_id}/ack",
            "running": "POST /api/commands/{command_id}/status",
            "result": "POST /api/commands/{command_id}/result",
            "command_state": "GET /api/commands/{command_id}",
            "clients": "GET /api/clients",
            "authentication": "X-Access-Token or Authorization: Bearer; URL tokens are forbidden",
        },
        "delivery": {
            "states": [
                "queued",
                "leased",
                "acknowledged",
                "running",
                "completed",
                "failed",
                "cancelled",
                "expired",
                "dead_letter",
            ],
            "identifiers": ["command_id", "delivery_id", "lease_token", "idempotency_key"],
            "retry_policies": sorted(RETRY_POLICIES),
        },
        "sessions": {
            "create": "POST /api/sessions",
            "heartbeat": "POST /api/sessions/{session_id}/heartbeat",
            "lock": "POST /api/sessions/{session_id}/locks",
            "release": "POST /api/sessions/{session_id}/locks/release",
            "lock_modes": ["exclusive", "shared_read", "operator_override"],
        },
        "target": {
            "client_id": "required for safe session calls",
            "tab_id": "required for session calls",
            "url_pattern": "legacy substring fallback",
            "active": "legacy active-tab fallback",
        },
        "frames": {
            "strategies": list(FRAME_STRATEGIES),
            "snapshot_field": "frame_id",
            "cross_origin": "supported when extension host permissions allow the frame URL",
            "closed_shadow_dom": "not available through DOM commands; CDP is a separate opt-in path",
        },
        "locator": locator,
        "wait_states": list(WAIT_STATES),
        "commands": {
            "snapshot": {
                "type": "snapshot",
                "root_selector": "optional CSS root",
                "limit": "1..1000 per frame; default 200",
                "include_hidden": "boolean; default false",
                "include_frames": "boolean; default true",
            },
            "smart_click": {
                "type": "smart_click",
                "locator": locator,
                "timeout_ms": "browser-side wait timeout",
                "proof": "optional postcondition object",
            },
            "set_editable_text": {
                "type": "set_editable_text",
                "locator": locator,
                "value": "string",
                "timeout_ms": "browser-side wait timeout",
                "proof": "optional postcondition object",
            },
            "wait_for": {
                "type": "wait_for",
                "locator": locator,
                "state": list(WAIT_STATES),
                "expected_text": "required when state=text",
                "expected_value": "required when state=value",
                "timeout_ms": "browser-side wait timeout",
            },
        },
        "compatibility": {
            "legacy_css_commands": True,
            "stable_refs": "frame-scoped refs; detached refs are healed only when unique",
            "shadow_dom": "open shadow roots",
            "iframes": "top-level and nested extension-accessible frames",
        },
    }
