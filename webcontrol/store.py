from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .utils import dump_json, now_utc_iso, load_json

TERMINAL_DELIVERY_STATUSES = {"completed", "failed", "cancelled", "expired"}
TERMINAL_COMMAND_STATUSES = {
    "completed",
    "failed",
    "partial",
    "cancelled",
    "expired",
    "rejected",
}


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


class ControlStore:
    """Thread-safe storage for clients, command queues, and command results."""

    def __init__(self, state_file: Path):
        self.state_file = state_file
        self._lock = threading.RLock()
        self._state = self._load_state()

    def _load_state(self) -> dict[str, Any]:
        state = load_json(self.state_file, default={})
        if not isinstance(state, dict):
            state = {}
        state.setdefault("version", 1)
        state.setdefault("created_at", now_utc_iso())
        state.setdefault("clients", {})
        state.setdefault("commands", {})
        state.setdefault("queues", {})
        return state

    def _save(self) -> None:
        dump_json(self.state_file, self._state)

    def register_client(
        self,
        *,
        client_id: str,
        tabs: list[dict[str, Any]] | None,
        meta: dict[str, Any] | None,
        user_agent: str | None,
        extension_version: str | None,
    ) -> dict[str, Any]:
        with self._lock:
            clients = self._state["clients"]
            client = clients.get(client_id)
            now = now_utc_iso()
            if not client:
                client = {
                    "client_id": client_id,
                    "created_at": now,
                    "last_seen": now,
                    "tabs": tabs or [],
                    "meta": meta or {},
                    "user_agent": user_agent,
                    "extension_version": extension_version,
                }
                clients[client_id] = client
            else:
                client["last_seen"] = now
                if tabs is not None:
                    client["tabs"] = tabs
                if meta:
                    client["meta"] = {**client.get("meta", {}), **meta}
                if user_agent:
                    client["user_agent"] = user_agent
                if extension_version:
                    client["extension_version"] = extension_version

            self._state["queues"].setdefault(client_id, [])
            self._save()
            return client

    def list_clients(self) -> list[dict[str, Any]]:
        with self._lock:
            clients = list(self._state["clients"].values())
            clients.sort(key=lambda c: c.get("last_seen", ""), reverse=True)
            return clients

    def _resolve_target_clients(self, target: dict[str, Any]) -> list[str]:
        client_id = target.get("client_id")
        if client_id:
            return [str(client_id)]

        client_ids = target.get("client_ids")
        if isinstance(client_ids, list) and client_ids:
            return sorted({str(x) for x in client_ids if x})

        if target.get("broadcast"):
            return sorted(self._state["clients"].keys())

        return sorted(self._state["clients"].keys())

    def enqueue_command(
        self,
        *,
        command: dict[str, Any],
        target: dict[str, Any] | None,
        timeout_ms: int,
        issued_by: str,
    ) -> dict[str, Any]:
        with self._lock:
            target = target or {}
            now = datetime.now(timezone.utc)
            command_id = str(uuid.uuid4())
            target_clients = self._resolve_target_clients(target)

            deliveries: dict[str, Any] = {}
            for client_id in target_clients:
                deliveries[client_id] = {
                    "status": "pending",
                    "updated_at": now_utc_iso(),
                    "result": None,
                }
                self._state["queues"].setdefault(client_id, []).append(command_id)

            record = {
                "id": command_id,
                "created_at": now_utc_iso(),
                "expires_at": (now + timedelta(milliseconds=timeout_ms)).isoformat(),
                "status": "pending" if target_clients else "rejected",
                "issued_by": issued_by,
                "target": target,
                "target_client_ids": target_clients,
                "timeout_ms": timeout_ms,
                "command": command,
                "deliveries": deliveries,
                "last_update": now_utc_iso(),
            }
            self._state["commands"][command_id] = record
            self._save()
            return record

    def _is_expired(self, command: dict[str, Any]) -> bool:
        expires_at = _parse_iso(command.get("expires_at"))
        if not expires_at:
            return False
        return datetime.now(timezone.utc) > expires_at

    def _refresh_command_status(self, command: dict[str, Any]) -> None:
        deliveries = command.get("deliveries", {})
        statuses = [item.get("status", "pending") for item in deliveries.values()]
        if not statuses:
            command["status"] = "rejected"
            command["last_update"] = now_utc_iso()
            return

        if self._is_expired(command) and any(s not in TERMINAL_DELIVERY_STATUSES for s in statuses):
            for delivery in deliveries.values():
                if delivery.get("status") not in TERMINAL_DELIVERY_STATUSES:
                    delivery["status"] = "expired"
                    delivery["updated_at"] = now_utc_iso()
            statuses = [item.get("status", "pending") for item in deliveries.values()]

        if all(s == "completed" for s in statuses):
            command["status"] = "completed"
        elif all(s == "failed" for s in statuses):
            command["status"] = "failed"
        elif all(s in TERMINAL_DELIVERY_STATUSES for s in statuses):
            if all(s == "cancelled" for s in statuses):
                command["status"] = "cancelled"
            elif all(s == "expired" for s in statuses):
                command["status"] = "expired"
            else:
                command["status"] = "partial"
        elif any(s == "dispatched" for s in statuses):
            command["status"] = "in_progress"
        else:
            command["status"] = "pending"

        command["last_update"] = now_utc_iso()

    def pop_next_command(self, client_id: str) -> dict[str, Any] | None:
        with self._lock:
            queue = self._state["queues"].setdefault(client_id, [])
            commands = self._state["commands"]

            while queue:
                command_id = queue.pop(0)
                command = commands.get(command_id)
                if not command:
                    continue

                delivery = command.get("deliveries", {}).get(client_id)
                if not delivery:
                    continue

                self._refresh_command_status(command)
                if command["status"] in TERMINAL_COMMAND_STATUSES:
                    continue

                if delivery.get("status") in TERMINAL_DELIVERY_STATUSES:
                    continue

                delivery["status"] = "dispatched"
                delivery["updated_at"] = now_utc_iso()
                delivery["dispatched_at"] = now_utc_iso()
                self._refresh_command_status(command)
                self._save()

                return {
                    "id": command["id"],
                    "created_at": command["created_at"],
                    "timeout_ms": command.get("timeout_ms", 0),
                    "target": command.get("target", {}),
                    "command": command.get("command", {}),
                }

            self._save()
            return None

    def submit_result(
        self,
        *,
        command_id: str,
        client_id: str,
        ok: bool,
        status: str | None,
        data: Any,
        error: Any,
        logs: list[str] | None,
    ) -> dict[str, Any] | None:
        with self._lock:
            command = self._state["commands"].get(command_id)
            if not command:
                return None

            deliveries = command.setdefault("deliveries", {})
            delivery = deliveries.setdefault(
                client_id,
                {"status": "pending", "updated_at": now_utc_iso(), "result": None},
            )

            delivery["status"] = status or ("completed" if ok else "failed")
            delivery["updated_at"] = now_utc_iso()
            delivery["result"] = {
                "ok": bool(ok),
                "status": delivery["status"],
                "data": data,
                "error": error,
                "logs": logs or [],
                "finished_at": now_utc_iso(),
            }

            self._refresh_command_status(command)
            self._save()
            return command

    def cancel_command(self, command_id: str) -> dict[str, Any] | None:
        with self._lock:
            command = self._state["commands"].get(command_id)
            if not command:
                return None

            for delivery in command.get("deliveries", {}).values():
                if delivery.get("status") not in TERMINAL_DELIVERY_STATUSES:
                    delivery["status"] = "cancelled"
                    delivery["updated_at"] = now_utc_iso()

            self._refresh_command_status(command)
            self._save()
            return command

    def get_command(self, command_id: str) -> dict[str, Any] | None:
        with self._lock:
            command = self._state["commands"].get(command_id)
            if not command:
                return None
            self._refresh_command_status(command)
            self._save()
            return command

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            # Refresh statuses on read so clients receive up-to-date state.
            for command in self._state["commands"].values():
                self._refresh_command_status(command)

            commands = list(self._state["commands"].values())
            commands.sort(key=lambda c: c.get("created_at", ""), reverse=True)
            summary_commands = commands[:100]

            queues = {key: len(value) for key, value in self._state["queues"].items()}
            clients = self.list_clients()

            payload = {
                "version": self._state.get("version", 1),
                "created_at": self._state.get("created_at"),
                "now": now_utc_iso(),
                "clients": clients,
                "queue_sizes": queues,
                "commands": summary_commands,
            }
            self._save()
            return payload
