from __future__ import annotations

from typing import Any

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
) -> dict[str, Any]:
    """Build and validate the stable locator envelope used by agent commands."""

    choices = [
        ("css", selector),
        ("ref", ref),
        ("role", role),
        ("text", text),
        ("label", label),
        ("placeholder", placeholder),
        ("test_id", test_id),
    ]
    selected = [(strategy, str(value).strip()) for strategy, value in choices if value is not None and str(value).strip()]
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
    )


def agent_api_schema() -> dict[str, Any]:
    """Return a machine-readable, versioned contract for browser-agent clients."""

    locator = {
        "strategy": list(LOCATOR_STRATEGIES),
        "value": "string",
        "name": "optional accessible name; valid with strategy=role",
        "exact": "boolean; default false",
        "nth": "optional zero-based index",
        "root_selector": "optional CSS root",
    }
    return {
        "schema_version": "1.0",
        "transport": {
            "enqueue": "POST /api/commands",
            "command_state": "GET /api/commands/{command_id}",
            "clients": "GET /api/clients",
            "authentication": "X-Access-Token or Authorization: Bearer",
        },
        "target": {
            "client_id": "required for safe single-client agent calls",
            "tab_id": "preferred stable tab target",
            "url_pattern": "optional substring fallback",
            "active": "fallback to active tab; default true",
        },
        "locator": locator,
        "wait_states": list(WAIT_STATES),
        "commands": {
            "snapshot": {
                "type": "snapshot",
                "root_selector": "optional CSS root",
                "limit": "1..1000; default 200",
                "include_hidden": "boolean; default false",
            },
            "smart_click": {
                "type": "smart_click",
                "locator": locator,
                "timeout_ms": "browser-side wait timeout",
            },
            "set_editable_text": {
                "type": "set_editable_text",
                "locator": locator,
                "value": "string",
                "timeout_ms": "browser-side wait timeout",
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
            "stable_refs": "page-lifetime refs returned by snapshot; detached refs are healed only when unique",
            "shadow_dom": "open shadow roots",
            "iframes": "top frame only in schema version 1.0",
        },
    }
