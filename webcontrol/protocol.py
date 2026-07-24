from __future__ import annotations

import hashlib
import json
from typing import Any

HUB_PROTOCOL_VERSION = "2.1"
AGENT_API_VERSION = "1.1"
STORAGE_SCHEMA_VERSION = 2

DELIVERY_STATES = {
    "queued",
    "leased",
    "acknowledged",
    "running",
    "completed",
    "failed",
    "cancelled",
    "expired",
    "dead_letter",
}
TERMINAL_DELIVERY_STATES = {
    "completed",
    "failed",
    "cancelled",
    "expired",
    "dead_letter",
}
TERMINAL_COMMAND_STATES = {
    "completed",
    "failed",
    "partial",
    "cancelled",
    "expired",
    "dead_letter",
    "rejected",
}

RETRY_POLICIES = {
    "never_retry",
    "retry_if_not_started",
    "retry_with_verification",
    "safe_retry",
}

READ_ONLY_COMMANDS = {
    "extract_text",
    "get_html",
    "get_attribute",
    "get_page_url",
    "snapshot",
    "wait_for",
    "wait_selector",
    "screenshot",
}

INPUT_COMMANDS = {
    "clear_editable",
    "fill",
    "focus",
    "press_key",
    "set_editable_text",
}

FILE_UPLOAD_COMMANDS = {
    "set_file_input_files",
    "upload_file",
}

DANGEROUS_COMMANDS = {
    "click",
    "click_menu_text",
    "click_text",
    "close_tab",
    "context_click",
    "new_tab",
    "run_script",
    "smart_click",
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def payload_fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def command_type(command: dict[str, Any]) -> str:
    return str(command.get("type") or "").strip()


def command_is_read_only(command: dict[str, Any]) -> bool:
    return command_type(command) in READ_ONLY_COMMANDS


def command_is_mutating(command: dict[str, Any]) -> bool:
    return not command_is_read_only(command)


def default_retry_policy(command: dict[str, Any]) -> str:
    if command_is_read_only(command):
        return "safe_retry"
    if command_type(command) in INPUT_COMMANDS:
        return "retry_if_not_started"
    return "never_retry"


def normalize_retry_policy(command: dict[str, Any], requested: Any = None) -> str:
    policy = str(requested or default_retry_policy(command)).strip()
    if policy not in RETRY_POLICIES:
        allowed = ", ".join(sorted(RETRY_POLICIES))
        raise ValueError(f"Unknown retry policy {policy!r}; expected one of: {allowed}")
    return policy


def command_requires_confirmation(command: dict[str, Any]) -> bool:
    if bool(command.get("requires_confirmation")):
        return True
    action = str(command.get("dangerous_action") or "").strip()
    return bool(action)
