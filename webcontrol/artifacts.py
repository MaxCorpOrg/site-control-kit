from __future__ import annotations

import base64
import json
import re
import threading
from pathlib import Path
from typing import Any

from .utils import dump_json, now_utc_iso

SENSITIVE_KEY_PARTS = {
    "access_token",
    "authorization",
    "cookie",
    "password",
    "proxy_password",
    "refresh_token",
    "secret",
    "token",
}
CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}")


def redact(value: Any, *, secrets: list[str] | None = None) -> Any:
    explicit = [item for item in (secrets or []) if item]
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).lower()
            if any(part in normalized for part in SENSITIVE_KEY_PARTS):
                cleaned[key] = "[СКРЫТО]"
            else:
                cleaned[key] = redact(item, secrets=explicit)
        return cleaned
    if isinstance(value, list):
        return [redact(item, secrets=explicit) for item in value]
    if isinstance(value, tuple):
        return [redact(item, secrets=explicit) for item in value]
    if not isinstance(value, str):
        return value
    result = BEARER_RE.sub("Bearer [СКРЫТО]", value)
    result = CARD_RE.sub("[СКРЫТО:КАРТА]", result)
    for secret in explicit:
        result = result.replace(secret, "[СКРЫТО]")
    return result


class ArtifactManager:
    def __init__(self, root: Path):
        self.root = root.expanduser()
        self._lock = threading.RLock()

    def session_dir(self, session_id: str) -> Path:
        return self.root / _safe_name(session_id)

    def create_session(self, session: dict[str, Any]) -> Path:
        directory = self.session_dir(str(session["session_id"]))
        directory.mkdir(parents=True, exist_ok=True)
        dump_json(directory / "session.json", redact(session, secrets=session.get("secrets")))
        for name in (
            "commands.jsonl",
            "events.jsonl",
            "console.jsonl",
            "network.jsonl",
            "errors.jsonl",
        ):
            (directory / name).touch(exist_ok=True)
        return directory

    def append(
        self,
        session_id: str,
        stream: str,
        payload: dict[str, Any],
        *,
        secrets: list[str] | None = None,
    ) -> Path:
        allowed = {"commands", "events", "console", "network", "errors"}
        if stream not in allowed:
            raise ValueError(f"Unknown artifact stream: {stream}")
        directory = self.session_dir(session_id)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{stream}.jsonl"
        record = {
            "recorded_at": now_utc_iso(),
            **redact(payload, secrets=secrets),
        }
        line = json.dumps(record, ensure_ascii=False, sort_keys=True)
        with self._lock:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
                handle.flush()
        return path

    def save_failure_bundle(
        self,
        session_id: str,
        command_id: str,
        payload: dict[str, Any],
        *,
        secrets: list[str] | None = None,
    ) -> dict[str, str]:
        directory = self.session_dir(session_id) / "errors" / _safe_name(command_id)
        directory.mkdir(parents=True, exist_ok=True)
        cleaned = redact(payload, secrets=secrets)
        screenshot = cleaned.pop("screenshot_data_url", None) if isinstance(cleaned, dict) else None
        snapshot = cleaned.pop("semantic_snapshot", None) if isinstance(cleaned, dict) else None
        paths: dict[str, str] = {}
        dump_json(directory / "diagnostics.json", cleaned)
        paths["diagnostics"] = str(directory / "diagnostics.json")
        if snapshot is not None:
            dump_json(directory / "semantic_snapshot.json", snapshot)
            paths["semantic_snapshot"] = str(directory / "semantic_snapshot.json")
        if isinstance(screenshot, str) and screenshot.startswith("data:image/png;base64,"):
            encoded = screenshot.split(",", 1)[1]
            try:
                image = base64.b64decode(encoded, validate=True)
            except (ValueError, TypeError):
                image = b""
            if image:
                screenshot_path = directory / "screenshot.png"
                screenshot_path.write_bytes(image)
                paths["screenshot"] = str(screenshot_path)
        return paths


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    return cleaned[:160] or "unknown"
