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
CLIENT_ONLINE_WINDOW_SECONDS = 30
MAX_PERSISTED_TERMINAL_COMMANDS = 40


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        parsed = datetime.fromisoformat(ts)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class ControlStore:
    """Thread-safe storage for clients, command queues, and command results."""

    def __init__(self, state_file: Path):
        self.state_file = state_file
        self._lock = threading.RLock()
        self._state = self._load_state()
        with self._lock:
            if self._prune_terminal_commands():
                self._save()

    def _load_state(self) -> dict[str, Any]:
        state = load_json(self.state_file, default={})
        if not isinstance(state, dict):
            state = {}
        state.setdefault("version", 1)
        state.setdefault("created_at", now_utc_iso())
        state.setdefault("clients", {})
        state.setdefault("commands", {})
        state.setdefault("queues", {})
        state.setdefault("telegram_users", {})
        return state

    def _save(self) -> None:
        self._prune_terminal_commands()
        dump_json(self.state_file, self._state)

    @staticmethod
    def _command_sort_key(command: dict[str, Any]) -> tuple[str, str, str]:
        return (
            str(command.get("last_update") or command.get("created_at") or ""),
            str(command.get("created_at") or ""),
            str(command.get("id") or ""),
        )

    def _prune_terminal_commands(self) -> bool:
        commands = self._state.setdefault("commands", {})
        if not isinstance(commands, dict):
            self._state["commands"] = {}
            commands = self._state["commands"]

        keep_ids: set[str] = set()
        terminal_commands: list[tuple[tuple[str, str, str], str]] = []
        for command_id, command in commands.items():
            status = str((command or {}).get("status") or "")
            if status in TERMINAL_COMMAND_STATUSES:
                terminal_commands.append((self._command_sort_key(command), command_id))
                continue
            keep_ids.add(command_id)

        terminal_commands.sort(key=lambda item: item[0], reverse=True)
        keep_ids.update(command_id for _, command_id in terminal_commands[:MAX_PERSISTED_TERMINAL_COMMANDS])

        changed = False
        for command_id in list(commands):
            if command_id in keep_ids:
                continue
            del commands[command_id]
            changed = True

        queues = self._state.setdefault("queues", {})
        if not isinstance(queues, dict):
            self._state["queues"] = {}
            queues = self._state["queues"]
            changed = True
        for client_id, queue in list(queues.items()):
            if not isinstance(queue, list):
                queues[client_id] = []
                changed = True
                continue
            filtered_queue = [command_id for command_id in queue if command_id in commands]
            if filtered_queue != queue:
                queues[client_id] = filtered_queue
                changed = True
        return changed

    def _client_is_online(self, client: dict[str, Any], *, now: datetime | None = None) -> bool:
        last_seen = _parse_iso(str(client.get("last_seen", "")).strip())
        if not last_seen:
            return False
        current = now or datetime.now(timezone.utc)
        return last_seen >= current - timedelta(seconds=CLIENT_ONLINE_WINDOW_SECONDS)

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
            changed = False
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
                changed = True
            else:
                client["last_seen"] = now
                if tabs is not None and client.get("tabs") != tabs:
                    client["tabs"] = tabs
                    changed = True
                if meta:
                    merged_meta = {**client.get("meta", {}), **meta}
                    if client.get("meta") != merged_meta:
                        client["meta"] = merged_meta
                        changed = True
                if user_agent and client.get("user_agent") != user_agent:
                    client["user_agent"] = user_agent
                    changed = True
                if extension_version and client.get("extension_version") != extension_version:
                    client["extension_version"] = extension_version
                    changed = True

            self._state["queues"].setdefault(client_id, [])
            if changed:
                self._save()
            return {**client, "is_online": True}

    def list_clients(self) -> list[dict[str, Any]]:
        with self._lock:
            now = datetime.now(timezone.utc)
            clients = [{**client, "is_online": self._client_is_online(client, now=now)} for client in self._state["clients"].values()]
            clients.sort(key=lambda c: c.get("last_seen", ""), reverse=True)
            return clients

    def _resolve_target_clients(self, target: dict[str, Any]) -> tuple[list[str], str | None]:
        client_id = target.get("client_id")
        if client_id:
            normalized = str(client_id).strip()
            if normalized in self._state["clients"]:
                return [normalized], None
            return [], f"Target client not found: {normalized}"

        client_ids = target.get("client_ids")
        if isinstance(client_ids, list) and client_ids:
            known = sorted({str(x).strip() for x in client_ids if str(x).strip() in self._state["clients"]})
            if known:
                return known, None
            return [], "No known target clients matched client_ids"

        if target.get("broadcast"):
            known_clients = sorted(self._state["clients"].keys())
            if known_clients:
                return known_clients, None
            return [], "No browser clients are registered for broadcast"

        now = datetime.now(timezone.utc)
        online_clients = sorted(
            client_id
            for client_id, client in self._state["clients"].items()
            if self._client_is_online(client, now=now)
        )
        if len(online_clients) == 1:
            return online_clients, None
        if not online_clients:
            return [], "No online browser clients available"
        return [], "Multiple online browser clients available; specify client_id/client_ids or broadcast"

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
            target_clients, rejection_reason = self._resolve_target_clients(target)

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
                "rejection_reason": rejection_reason,
            }
            self._state["commands"][command_id] = record
            self._save()
            return record

    def _is_expired(self, command: dict[str, Any]) -> bool:
        expires_at = _parse_iso(command.get("expires_at"))
        if not expires_at:
            return False
        return datetime.now(timezone.utc) > expires_at

    def _refresh_command_status(self, command: dict[str, Any]) -> bool:
        deliveries = command.get("deliveries", {})
        statuses = [item.get("status", "pending") for item in deliveries.values()]
        changed = False
        if not statuses:
            if command.get("status") != "rejected":
                command["status"] = "rejected"
                changed = True
            if changed:
                command["last_update"] = now_utc_iso()
            return changed

        if self._is_expired(command) and any(s not in TERMINAL_DELIVERY_STATUSES for s in statuses):
            for delivery in deliveries.values():
                if delivery.get("status") not in TERMINAL_DELIVERY_STATUSES:
                    delivery["status"] = "expired"
                    delivery["updated_at"] = now_utc_iso()
                    changed = True
            statuses = [item.get("status", "pending") for item in deliveries.values()]

        if all(s == "completed" for s in statuses):
            next_status = "completed"
        elif all(s == "failed" for s in statuses):
            next_status = "failed"
        elif all(s in TERMINAL_DELIVERY_STATUSES for s in statuses):
            if all(s == "cancelled" for s in statuses):
                next_status = "cancelled"
            elif all(s == "expired" for s in statuses):
                next_status = "expired"
            else:
                next_status = "partial"
        elif any(s == "dispatched" for s in statuses):
            next_status = "in_progress"
        else:
            next_status = "pending"

        if command.get("status") != next_status:
            command["status"] = next_status
            changed = True
        if changed:
            command["last_update"] = now_utc_iso()
        return changed

    def pop_next_command(self, client_id: str) -> dict[str, Any] | None:
        with self._lock:
            queue = self._state["queues"].setdefault(client_id, [])
            commands = self._state["commands"]
            changed = False

            while queue:
                command_id = queue.pop(0)
                changed = True
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

            if changed:
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
            changed = self._refresh_command_status(command)
            if changed:
                self._save()
            return command

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            # Refresh statuses on read so clients receive up-to-date state.
            changed = False
            for command in self._state["commands"].values():
                changed = self._refresh_command_status(command) or changed

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
                "telegram_users": dict(sorted(self._state.get("telegram_users", {}).items())),
                "queue_sizes": queues,
                "commands": summary_commands,
            }
            if changed:
                self._save()
            return payload

    def upsert_telegram_user(self, *, telegram_id: Any, username: str | None) -> dict[str, Any]:
        telegram_id_text = str(telegram_id).strip()
        if not telegram_id_text:
            raise ValueError("telegram_id is required")

        normalized_username = None
        if username is not None:
            username_text = str(username).strip()
            if username_text:
                normalized_username = username_text if username_text.startswith("@") else f"@{username_text}"

        with self._lock:
            users = self._state.setdefault("telegram_users", {})
            now = now_utc_iso()
            existing = users.get(telegram_id_text)
            if not existing:
                record = {
                    "telegram_id": telegram_id,
                    "username": normalized_username,
                    "created_at": now,
                    "updated_at": now,
                }
                users[telegram_id_text] = record
                self._save()
                return {**record, "changed": True}

            changed = False
            if existing.get("telegram_id") != telegram_id:
                existing["telegram_id"] = telegram_id
                changed = True
            if existing.get("username") != normalized_username:
                existing["username"] = normalized_username
                changed = True
            if changed:
                existing["updated_at"] = now
                self._save()
            return {**existing, "changed": changed}
