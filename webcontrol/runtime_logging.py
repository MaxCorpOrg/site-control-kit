from __future__ import annotations

import json
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_event_payload(
    *,
    component: str,
    event: str,
    level: str = "info",
    run_id: str = "",
    profile: str = "",
    chat_ref: str = "",
    chat_title: str = "",
    status: str = "",
    message: str = "",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "ts": utc_timestamp(),
        "level": level,
        "component": component,
        "event": event,
        "run_id": run_id,
        "profile": profile,
        "chat_ref": chat_ref,
        "chat_title": chat_title,
        "status": status,
        "message": message,
        "details": details or {},
    }


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


class RuntimeEventLogger:
    def __init__(self, *, events_path: Path, errors_path: Path):
        self.events_path = events_path
        self.errors_path = errors_path

    def log_event(
        self,
        *,
        component: str,
        event: str,
        level: str = "info",
        run_id: str = "",
        profile: str = "",
        chat_ref: str = "",
        chat_title: str = "",
        status: str = "",
        message: str = "",
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = build_event_payload(
            component=component,
            event=event,
            level=level,
            run_id=run_id,
            profile=profile,
            chat_ref=chat_ref,
            chat_title=chat_title,
            status=status,
            message=message,
            details=details,
        )
        append_jsonl(self.events_path, payload)
        if level.lower() in {"error", "critical"}:
            append_jsonl(self.errors_path, payload)
        return payload

    def log_exception(
        self,
        *,
        component: str,
        event: str,
        exc: BaseException,
        run_id: str = "",
        profile: str = "",
        chat_ref: str = "",
        chat_title: str = "",
        status: str = "failed",
        message: str = "",
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload_details = dict(details or {})
        payload_details.setdefault("error_type", exc.__class__.__name__)
        payload_details.setdefault("traceback", "".join(traceback.format_exception(exc)).strip())
        return self.log_event(
            component=component,
            event=event,
            level="error",
            run_id=run_id,
            profile=profile,
            chat_ref=chat_ref,
            chat_title=chat_title,
            status=status,
            message=message or str(exc),
            details=payload_details,
        )
