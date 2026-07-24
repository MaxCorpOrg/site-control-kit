from __future__ import annotations

import secrets
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .artifacts import ArtifactManager
from .protocol import (
    DANGEROUS_COMMANDS,
    DELIVERY_STATES,
    HUB_PROTOCOL_VERSION,
    INPUT_COMMANDS,
    STORAGE_SCHEMA_VERSION,
    TERMINAL_COMMAND_STATES,
    TERMINAL_DELIVERY_STATES,
    command_is_mutating,
    command_is_read_only,
    command_requires_confirmation,
    command_type,
    normalize_retry_policy,
    payload_fingerprint,
)
from .state_backend import SQLiteStateBackend
from .utils import now_utc_iso

TERMINAL_DELIVERY_STATUSES = TERMINAL_DELIVERY_STATES
TERMINAL_COMMAND_STATUSES = TERMINAL_COMMAND_STATES
CLIENT_ONLINE_WINDOW_SECONDS = 30
MAX_PERSISTED_TERMINAL_COMMANDS = 200
DEFAULT_LEASE_DURATION_MS = 60_000
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_SESSION_TTL_SECONDS = 300
MAX_SESSION_TTL_SECONDS = 24 * 60 * 60


class StoreValidationError(ValueError):
    error_code = "validation_error"


class IdempotencyConflictError(StoreValidationError):
    error_code = "idempotency_conflict"


class ResultValidationError(StoreValidationError):
    error_code = "invalid_result"


class ResultConflictError(ResultValidationError):
    error_code = "result_conflict"


class StaleLeaseError(ResultValidationError):
    error_code = "stale_lease"


class SessionConflictError(StoreValidationError):
    error_code = "session_conflict"


class SessionPolicyError(StoreValidationError):
    error_code = "session_policy_denied"


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        parsed = datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _iso_after(*, milliseconds: int = 0, seconds: int = 0) -> str:
    return (
        datetime.now(timezone.utc) + timedelta(milliseconds=milliseconds, seconds=seconds)
    ).isoformat()


def _tab_lock_key(client_id: str, tab_id: int) -> str:
    return f"{client_id}:{tab_id}"


class ControlStore:
    """Потокобезопасное состояние хаба поверх SQLite WAL и JSON-зеркала."""

    def __init__(
        self,
        state_file: Path,
        *,
        lease_duration_ms: int = DEFAULT_LEASE_DURATION_MS,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        artifacts_root: Path | None = None,
    ):
        self.state_file = state_file
        self.lease_duration_ms = max(1_000, min(int(lease_duration_ms), 10 * 60 * 1000))
        self.max_attempts = max(1, min(int(max_attempts), 100))
        self._lock = threading.RLock()
        self._backend = SQLiteStateBackend(state_file)
        self._artifacts = ArtifactManager(artifacts_root or state_file.parent / "artifacts")
        self._state = self._load_state()
        with self._lock:
            changed = self._normalize_state()
            changed = self._sweep_expired() or changed
            changed = self._prune_terminal_commands() or changed
            if changed:
                self._save(event_type="state_normalized")

    def _default_state(self) -> dict[str, Any]:
        return {
            "version": STORAGE_SCHEMA_VERSION,
            "protocol_version": HUB_PROTOCOL_VERSION,
            "created_at": now_utc_iso(),
            "clients": {},
            "commands": {},
            "queues": {},
            "telegram_users": {},
            "sessions": {},
            "tab_locks": {},
            "idempotency_index": {},
        }

    def _load_state(self) -> dict[str, Any]:
        state = self._backend.load(self._default_state())
        if not isinstance(state, dict):
            state = self._default_state()
        state.pop("storage", None)
        return state

    def _normalize_state(self) -> bool:
        changed = False
        defaults = self._default_state()
        for key, value in defaults.items():
            if key not in self._state:
                self._state[key] = value
                changed = True
        if self._state.get("version") != STORAGE_SCHEMA_VERSION:
            self._state["version"] = STORAGE_SCHEMA_VERSION
            changed = True
        if self._state.get("protocol_version") != HUB_PROTOCOL_VERSION:
            self._state["protocol_version"] = HUB_PROTOCOL_VERSION
            changed = True

        commands = self._state.get("commands")
        if not isinstance(commands, dict):
            self._state["commands"] = {}
            commands = self._state["commands"]
            changed = True
        queues = self._state.get("queues")
        if not isinstance(queues, dict):
            self._state["queues"] = {}
            changed = True
        for client_id in self._state.get("clients", {}):
            self._state["queues"].setdefault(client_id, [])

        for command in commands.values():
            if not isinstance(command, dict):
                continue
            legacy_status = str(command.get("status") or "queued")
            if legacy_status == "pending":
                command["status"] = "queued"
                changed = True
            elif legacy_status == "in_progress":
                command["status"] = "running"
                changed = True
            command.setdefault("protocol_version", "1.0")
            command.setdefault("retry_policy", normalize_retry_policy(command.get("command", {})))
            command.setdefault("max_attempts", self.max_attempts)
            command.setdefault("lease_duration_ms", self.lease_duration_ms)
            command.setdefault("idempotency_key", None)
            command.setdefault("session_id", None)
            command.setdefault("transitions", [])
            for client_id, delivery in command.get("deliveries", {}).items():
                if not isinstance(delivery, dict):
                    continue
                delivery_status = str(delivery.get("status") or "queued")
                replacements = {"pending": "queued", "dispatched": "leased"}
                if delivery_status in replacements:
                    delivery["status"] = replacements[delivery_status]
                    changed = True
                delivery.setdefault("client_id", client_id)
                delivery.setdefault("delivery_id", None)
                delivery.setdefault("lease_token", None)
                delivery.setdefault("lease_expires_at", None)
                delivery.setdefault("attempt_number", 0)
                delivery.setdefault("transitions", [])
                delivery.setdefault("attempts", [])
        return changed

    def _save(
        self,
        *,
        event_type: str = "state_saved",
        entity_id: str | None = None,
        event_payload: dict[str, Any] | None = None,
    ) -> None:
        self._prune_terminal_commands()
        self._backend.save(
            self._state,
            event_type=event_type,
            entity_id=entity_id,
            event_payload=event_payload,
        )

    @staticmethod
    def _command_sort_key(command: dict[str, Any]) -> tuple[str, str, str]:
        return (
            str(command.get("last_update") or command.get("created_at") or ""),
            str(command.get("created_at") or ""),
            str(command.get("id") or ""),
        )

    def _prune_terminal_commands(self) -> bool:
        commands = self._state.setdefault("commands", {})
        keep_ids: set[str] = set()
        terminal: list[tuple[tuple[str, str, str], str]] = []
        for command_id, command in commands.items():
            if str((command or {}).get("status") or "") in TERMINAL_COMMAND_STATES:
                terminal.append((self._command_sort_key(command), command_id))
            else:
                keep_ids.add(command_id)
        terminal.sort(key=lambda item: item[0], reverse=True)
        keep_ids.update(command_id for _, command_id in terminal[:MAX_PERSISTED_TERMINAL_COMMANDS])

        changed = False
        for command_id in list(commands):
            if command_id in keep_ids:
                continue
            idempotency_key = commands[command_id].get("idempotency_key")
            if (
                idempotency_key
                and self._state["idempotency_index"].get(idempotency_key) == command_id
            ):
                del self._state["idempotency_index"][idempotency_key]
            del commands[command_id]
            changed = True
        for client_id, queue in list(self._state.setdefault("queues", {}).items()):
            if not isinstance(queue, list):
                self._state["queues"][client_id] = []
                changed = True
                continue
            filtered = [
                command_id
                for command_id in queue
                if command_id in commands
                and commands[command_id].get("status") not in TERMINAL_COMMAND_STATES
            ]
            if filtered != queue:
                self._state["queues"][client_id] = filtered
                changed = True
        return changed

    def _client_is_online(
        self,
        client: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> bool:
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
            changed = self._sweep_expired()
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
                self._save(
                    event_type="client_heartbeat",
                    entity_id=client_id,
                    event_payload={"tab_count": len(tabs or [])},
                )
            return {**client, "is_online": True}

    def list_clients(self) -> list[dict[str, Any]]:
        with self._lock:
            now = datetime.now(timezone.utc)
            clients = [
                {**client, "is_online": self._client_is_online(client, now=now)}
                for client in self._state["clients"].values()
            ]
            clients.sort(key=lambda item: item.get("last_seen", ""), reverse=True)
            return clients

    def _resolve_target_clients(
        self,
        target: dict[str, Any],
    ) -> tuple[list[str], str | None]:
        client_id = target.get("client_id")
        if client_id:
            normalized = str(client_id).strip()
            if normalized in self._state["clients"]:
                return [normalized], None
            return [], f"Target client not found: {normalized}"
        client_ids = target.get("client_ids")
        if isinstance(client_ids, list) and client_ids:
            known = sorted(
                {
                    str(item).strip()
                    for item in client_ids
                    if str(item).strip() in self._state["clients"]
                }
            )
            if known:
                return known, None
            return [], "No known target clients matched client_ids"
        if target.get("broadcast"):
            known_clients = sorted(self._state["clients"])
            if known_clients:
                return known_clients, None
            return [], "No browser clients are registered for broadcast"
        now = datetime.now(timezone.utc)
        online = sorted(
            client_id
            for client_id, client in self._state["clients"].items()
            if self._client_is_online(client, now=now)
        )
        if len(online) == 1:
            return online, None
        if not online:
            return [], "No online browser clients available"
        return (
            [],
            "Multiple online browser clients available; specify client_id/client_ids or broadcast",
        )

    def _idempotency_signature(
        self,
        *,
        command: dict[str, Any],
        target: dict[str, Any],
        session_id: str | None,
    ) -> str:
        return payload_fingerprint(
            {
                "command": command,
                "target": target,
                "session_id": session_id,
            }
        )

    def enqueue_command(
        self,
        *,
        command: dict[str, Any],
        target: dict[str, Any] | None,
        timeout_ms: int,
        issued_by: str,
        idempotency_key: str | None = None,
        retry_policy: str | None = None,
        lease_duration_ms: int | None = None,
        max_attempts: int | None = None,
        session_id: str | None = None,
        confirmation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._sweep_expired()
            target = target or {}
            normalized_key = str(idempotency_key or "").strip() or None
            signature = self._idempotency_signature(
                command=command,
                target=target,
                session_id=session_id,
            )
            if normalized_key:
                existing_id = self._state["idempotency_index"].get(normalized_key)
                existing = self._state["commands"].get(existing_id)
                if existing:
                    if existing.get("idempotency_signature") != signature:
                        raise IdempotencyConflictError(
                            f"Idempotency key {normalized_key!r} is already used for another command"
                        )
                    return {**existing, "idempotency_reused": True}

            policy = normalize_retry_policy(command, retry_policy)
            safe_lease_ms = max(
                1_000,
                min(int(lease_duration_ms or self.lease_duration_ms), 10 * 60 * 1000),
            )
            safe_max_attempts = max(
                1,
                min(int(max_attempts or self.max_attempts), 100),
            )
            target_clients, rejection_reason = self._resolve_target_clients(target)
            if session_id:
                self._validate_session_command(
                    session_id=session_id,
                    command=command,
                    target=target,
                    target_clients=target_clients,
                    confirmation=confirmation or {},
                )

            now = datetime.now(timezone.utc)
            command_id = str(uuid.uuid4())
            deliveries: dict[str, Any] = {}
            for client_id in target_clients:
                delivery: dict[str, Any] = {
                    "client_id": client_id,
                    "status": "queued",
                    "updated_at": now_utc_iso(),
                    "result": None,
                    "delivery_id": None,
                    "lease_token": None,
                    "lease_expires_at": None,
                    "attempt_number": 0,
                    "attempts": [],
                    "transitions": [],
                }
                self._append_delivery_transition(
                    delivery,
                    "queued",
                    client_id=client_id,
                    reason="command_enqueued",
                )
                deliveries[client_id] = delivery
                self._queue_once(client_id, command_id)

            record: dict[str, Any] = {
                "id": command_id,
                "command_id": command_id,
                "protocol_version": HUB_PROTOCOL_VERSION,
                "created_at": now_utc_iso(),
                "expires_at": (now + timedelta(milliseconds=timeout_ms)).isoformat(),
                "status": "queued" if target_clients else "rejected",
                "issued_by": issued_by,
                "target": target,
                "target_client_ids": target_clients,
                "timeout_ms": timeout_ms,
                "lease_duration_ms": safe_lease_ms,
                "max_attempts": safe_max_attempts,
                "retry_policy": policy,
                "idempotency_key": normalized_key,
                "idempotency_signature": signature,
                "session_id": session_id,
                "command": command,
                "deliveries": deliveries,
                "transitions": [],
                "last_update": now_utc_iso(),
                "rejection_reason": rejection_reason,
            }
            self._append_command_transition(
                record,
                record["status"],
                reason=rejection_reason or "command_enqueued",
            )
            self._state["commands"][command_id] = record
            if normalized_key:
                self._state["idempotency_index"][normalized_key] = command_id
            self._save(
                event_type="command_enqueued",
                entity_id=command_id,
                event_payload={
                    "retry_policy": policy,
                    "session_id": session_id,
                    "target_client_ids": target_clients,
                },
            )
            self._write_session_command_event(record, "enqueued")
            return record

    def _queue_once(self, client_id: str, command_id: str) -> None:
        queue = self._state["queues"].setdefault(client_id, [])
        if command_id not in queue:
            queue.append(command_id)

    def _append_delivery_transition(
        self,
        delivery: dict[str, Any],
        status: str,
        *,
        client_id: str,
        reason: str,
        delivery_id: str | None = None,
        attempt_number: int | None = None,
    ) -> None:
        if status not in DELIVERY_STATES:
            raise StoreValidationError(f"Unknown delivery state: {status}")
        now = now_utc_iso()
        delivery["status"] = status
        delivery["updated_at"] = now
        delivery.setdefault("transitions", []).append(
            {
                "status": status,
                "at": now,
                "client_id": client_id,
                "delivery_id": delivery_id or delivery.get("delivery_id"),
                "attempt_number": attempt_number
                if attempt_number is not None
                else delivery.get("attempt_number", 0),
                "reason": reason,
                "protocol_version": HUB_PROTOCOL_VERSION,
            }
        )

    def _append_command_transition(
        self,
        command: dict[str, Any],
        status: str,
        *,
        reason: str,
    ) -> None:
        now = now_utc_iso()
        command["status"] = status
        command["last_update"] = now
        command.setdefault("transitions", []).append(
            {
                "status": status,
                "at": now,
                "reason": reason,
                "protocol_version": HUB_PROTOCOL_VERSION,
            }
        )

    def _is_expired(self, command: dict[str, Any]) -> bool:
        expires_at = _parse_iso(command.get("expires_at"))
        return bool(expires_at and datetime.now(timezone.utc) > expires_at)

    def _refresh_command_status(self, command: dict[str, Any]) -> bool:
        deliveries = command.get("deliveries", {})
        statuses = [str(item.get("status") or "queued") for item in deliveries.values()]
        if not statuses:
            next_status = "rejected"
        elif all(status == "completed" for status in statuses):
            next_status = "completed"
        elif all(status == "failed" for status in statuses):
            next_status = "failed"
        elif all(status == "cancelled" for status in statuses):
            next_status = "cancelled"
        elif all(status == "expired" for status in statuses):
            next_status = "expired"
        elif all(status == "dead_letter" for status in statuses):
            next_status = "dead_letter"
        elif all(status in TERMINAL_DELIVERY_STATES for status in statuses):
            next_status = "partial"
        elif any(status == "running" for status in statuses):
            next_status = "running"
        elif any(status == "acknowledged" for status in statuses):
            next_status = "acknowledged"
        elif any(status == "leased" for status in statuses):
            next_status = "leased"
        else:
            next_status = "queued"
        if command.get("status") == next_status:
            return False
        self._append_command_transition(command, next_status, reason="delivery_aggregate_changed")
        return True

    def _sweep_expired(self) -> bool:
        now = datetime.now(timezone.utc)
        changed = self._expire_sessions(now)
        for command in self._state.get("commands", {}).values():
            if command.get("status") in TERMINAL_COMMAND_STATES:
                continue
            if self._is_expired(command):
                for client_id, delivery in command.get("deliveries", {}).items():
                    if delivery.get("status") in TERMINAL_DELIVERY_STATES:
                        continue
                    self._append_delivery_transition(
                        delivery,
                        "expired",
                        client_id=client_id,
                        reason="command_deadline_expired",
                    )
                    self._clear_lease(delivery)
                    changed = True
                changed = self._refresh_command_status(command) or changed
                continue
            for client_id, delivery in command.get("deliveries", {}).items():
                if delivery.get("status") not in {"leased", "acknowledged", "running"}:
                    continue
                lease_expires = _parse_iso(delivery.get("lease_expires_at"))
                if lease_expires and now > lease_expires:
                    self._handle_lease_expiration(command, client_id, delivery)
                    changed = True
            changed = self._refresh_command_status(command) or changed
        return changed

    def _handle_lease_expiration(
        self,
        command: dict[str, Any],
        client_id: str,
        delivery: dict[str, Any],
    ) -> None:
        previous_status = str(delivery.get("status") or "")
        attempt = int(delivery.get("attempt_number") or 0)
        policy = str(command.get("retry_policy") or "never_retry")
        can_retry = attempt < int(command.get("max_attempts") or self.max_attempts)
        if policy == "never_retry":
            can_retry = False
        elif policy == "retry_if_not_started" and previous_status == "running":
            can_retry = False
        elif policy == "retry_with_verification":
            verification = command.get("verification")
            can_retry = bool(
                can_retry
                and isinstance(verification, dict)
                and verification.get("not_started") is True
            )

        self._append_delivery_transition(
            delivery,
            "expired",
            client_id=client_id,
            reason="lease_expired",
        )
        delivery.setdefault("attempts", []).append(
            {
                "delivery_id": delivery.get("delivery_id"),
                "attempt_number": attempt,
                "leased_at": delivery.get("leased_at"),
                "lease_expires_at": delivery.get("lease_expires_at"),
                "last_status": previous_status,
                "finished_at": now_utc_iso(),
                "outcome": "lease_expired",
            }
        )
        self._clear_lease(delivery)
        if can_retry:
            self._append_delivery_transition(
                delivery,
                "queued",
                client_id=client_id,
                reason=f"retry_allowed:{policy}",
            )
            self._queue_once(client_id, command["id"])
        else:
            self._append_delivery_transition(
                delivery,
                "dead_letter",
                client_id=client_id,
                reason=f"retry_denied:{policy}",
            )

    @staticmethod
    def _clear_lease(delivery: dict[str, Any]) -> None:
        delivery["delivery_id"] = None
        delivery["lease_token"] = None
        delivery["lease_expires_at"] = None

    def pop_next_command(self, client_id: str) -> dict[str, Any] | None:
        with self._lock:
            changed = self._sweep_expired()
            queue = self._state["queues"].setdefault(client_id, [])
            commands = self._state["commands"]
            while queue:
                command_id = queue.pop(0)
                changed = True
                command = commands.get(command_id)
                if not command or command.get("status") in TERMINAL_COMMAND_STATES:
                    continue
                delivery = command.get("deliveries", {}).get(client_id)
                if not delivery or delivery.get("status") != "queued":
                    continue
                attempt = int(delivery.get("attempt_number") or 0) + 1
                if attempt > int(command.get("max_attempts") or self.max_attempts):
                    self._append_delivery_transition(
                        delivery,
                        "dead_letter",
                        client_id=client_id,
                        reason="max_attempts_exceeded",
                        attempt_number=attempt,
                    )
                    self._refresh_command_status(command)
                    continue
                delivery_id = str(uuid.uuid4())
                lease_token = secrets.token_urlsafe(32)
                lease_duration_ms = int(command.get("lease_duration_ms") or self.lease_duration_ms)
                delivery["delivery_id"] = delivery_id
                delivery["lease_token"] = lease_token
                delivery["leased_at"] = now_utc_iso()
                delivery["lease_expires_at"] = _iso_after(milliseconds=lease_duration_ms)
                delivery["attempt_number"] = attempt
                self._append_delivery_transition(
                    delivery,
                    "leased",
                    client_id=client_id,
                    reason="dispatched_to_client",
                    delivery_id=delivery_id,
                    attempt_number=attempt,
                )
                self._refresh_command_status(command)
                self._save(
                    event_type="command_leased",
                    entity_id=command_id,
                    event_payload={
                        "client_id": client_id,
                        "delivery_id": delivery_id,
                        "attempt_number": attempt,
                    },
                )
                self._write_session_command_event(command, "leased")
                session = self._state["sessions"].get(command.get("session_id"))
                policy = (session or {}).get("policy", {})
                return {
                    "id": command["id"],
                    "command_id": command["id"],
                    "delivery_id": delivery_id,
                    "lease_token": lease_token,
                    "lease_expires_at": delivery["lease_expires_at"],
                    "attempt_number": attempt,
                    "protocol_version": HUB_PROTOCOL_VERSION,
                    "created_at": command["created_at"],
                    "timeout_ms": command.get("timeout_ms", 0),
                    "retry_policy": command.get("retry_policy"),
                    "idempotency_key": command.get("idempotency_key"),
                    "session_id": command.get("session_id"),
                    "capture": {
                        "capture_screenshots": bool(policy.get("capture_screenshots", False)),
                        "capture_console": bool(policy.get("capture_console", False)),
                        "capture_network": bool(policy.get("capture_network", False)),
                        "allow_cdp": bool(policy.get("allow_cdp", False)),
                    },
                    "target": command.get("target", {}),
                    "command": command.get("command", {}),
                }
            if changed:
                self._save(event_type="queue_swept", entity_id=client_id)
            return None

    def acknowledge_delivery(
        self,
        *,
        command_id: str,
        client_id: str,
        delivery_id: str,
        lease_token: str,
    ) -> dict[str, Any]:
        return self.update_delivery_status(
            command_id=command_id,
            client_id=client_id,
            delivery_id=delivery_id,
            lease_token=lease_token,
            status="acknowledged",
            reason="client_acknowledged",
        )

    def update_delivery_status(
        self,
        *,
        command_id: str,
        client_id: str,
        delivery_id: str,
        lease_token: str,
        status: str,
        reason: str = "client_status_update",
    ) -> dict[str, Any]:
        if status not in {"acknowledged", "running"}:
            raise StoreValidationError("Only acknowledged or running status updates are allowed")
        with self._lock:
            command, delivery = self._validate_active_lease(
                command_id=command_id,
                client_id=client_id,
                delivery_id=delivery_id,
                lease_token=lease_token,
            )
            current = str(delivery.get("status") or "")
            if current == status:
                return command
            allowed = {
                "acknowledged": {"leased", "acknowledged"},
                "running": {"leased", "acknowledged", "running"},
            }
            if current not in allowed[status]:
                raise ResultValidationError(f"Cannot move delivery from {current!r} to {status!r}")
            self._append_delivery_transition(
                delivery,
                status,
                client_id=client_id,
                reason=reason,
                delivery_id=delivery_id,
            )
            self._refresh_command_status(command)
            self._save(
                event_type=f"command_{status}",
                entity_id=command_id,
                event_payload={"client_id": client_id, "delivery_id": delivery_id},
            )
            self._write_session_command_event(command, status)
            return command

    def _validate_active_lease(
        self,
        *,
        command_id: str,
        client_id: str,
        delivery_id: str,
        lease_token: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        command = self._state["commands"].get(command_id)
        if not command:
            raise ResultValidationError("command not found")
        delivery = command.get("deliveries", {}).get(client_id)
        if not delivery:
            raise ResultValidationError("client is not a target of this command")
        if delivery.get("delivery_id") != delivery_id:
            raise StaleLeaseError("delivery_id does not match the current lease")
        if not secrets.compare_digest(
            str(delivery.get("lease_token") or ""), str(lease_token or "")
        ):
            raise StaleLeaseError("lease_token does not match the current lease")
        lease_expires = _parse_iso(delivery.get("lease_expires_at"))
        if lease_expires and datetime.now(timezone.utc) > lease_expires:
            self._handle_lease_expiration(command, client_id, delivery)
            self._refresh_command_status(command)
            self._save(
                event_type="stale_lease_rejected",
                entity_id=command_id,
                event_payload={"client_id": client_id, "delivery_id": delivery_id},
            )
            raise StaleLeaseError("lease has expired")
        return command, delivery

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
        delivery_id: str | None = None,
        lease_token: str | None = None,
        result_id: str | None = None,
        finished_at: str | None = None,
        diagnostics: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        with self._lock:
            command = self._state["commands"].get(command_id)
            if not command:
                return None
            delivery = command.get("deliveries", {}).get(client_id)
            if not delivery:
                raise ResultValidationError("client is not a target of this command")

            result_status = str(status or ("completed" if ok else "failed"))
            if result_status not in {"completed", "failed", "cancelled"}:
                raise ResultValidationError(f"Unsupported terminal result status: {result_status}")
            result_payload = {
                "ok": bool(ok),
                "status": result_status,
                "data": data,
                "error": error,
                "logs": logs or [],
                "finished_at": finished_at or now_utc_iso(),
                "diagnostics": diagnostics or {},
            }
            fingerprint = payload_fingerprint(
                {
                    "ok": result_payload["ok"],
                    "status": result_payload["status"],
                    "data": result_payload["data"],
                    "error": result_payload["error"],
                    "logs": result_payload["logs"],
                    "diagnostics": result_payload["diagnostics"],
                }
            )
            existing = delivery.get("result")
            if delivery.get("status") in TERMINAL_DELIVERY_STATES and existing:
                if existing.get("fingerprint") == fingerprint:
                    delivery["duplicate_result_count"] = (
                        int(delivery.get("duplicate_result_count") or 0) + 1
                    )
                    self._save(
                        event_type="duplicate_result_accepted",
                        entity_id=command_id,
                        event_payload={"client_id": client_id, "result_id": result_id},
                    )
                    return command
                conflict = {
                    "at": now_utc_iso(),
                    "client_id": client_id,
                    "result_id": result_id,
                    "fingerprint": fingerprint,
                }
                delivery.setdefault("result_conflicts", []).append(conflict)
                self._save(
                    event_type="result_conflict_rejected",
                    entity_id=command_id,
                    event_payload=conflict,
                )
                raise ResultConflictError("a different terminal result was already accepted")

            legacy_result = not delivery_id and not lease_token
            if legacy_result:
                delivery_id = str(delivery.get("delivery_id") or "")
                lease_token = str(delivery.get("lease_token") or "")
                if not delivery_id or not lease_token:
                    raise StaleLeaseError(
                        "result has no delivery identifiers and no active legacy lease"
                    )
            self._validate_active_lease(
                command_id=command_id,
                client_id=client_id,
                delivery_id=str(delivery_id),
                lease_token=str(lease_token),
            )
            received_at = now_utc_iso()
            delivery["result"] = {
                **result_payload,
                "result_id": result_id or str(uuid.uuid4()),
                "fingerprint": fingerprint,
                "received_at": received_at,
                "legacy_delivery_identifiers": legacy_result,
            }
            delivery.setdefault("attempts", []).append(
                {
                    "delivery_id": delivery_id,
                    "attempt_number": delivery.get("attempt_number"),
                    "leased_at": delivery.get("leased_at"),
                    "lease_expires_at": delivery.get("lease_expires_at"),
                    "finished_at": result_payload["finished_at"],
                    "received_at": received_at,
                    "outcome": result_status,
                }
            )
            self._append_delivery_transition(
                delivery,
                result_status,
                client_id=client_id,
                reason="result_accepted",
                delivery_id=str(delivery_id),
            )
            delivery["lease_token"] = None
            delivery["lease_expires_at"] = None
            self._refresh_command_status(command)
            self._save(
                event_type="command_result_accepted",
                entity_id=command_id,
                event_payload={
                    "client_id": client_id,
                    "delivery_id": delivery_id,
                    "status": result_status,
                    "legacy_delivery_identifiers": legacy_result,
                },
            )
            self._write_session_command_event(command, "result", result=delivery["result"])
            session_id = command.get("session_id")
            session = self._state["sessions"].get(session_id) if session_id else None
            if session:
                secrets_list = session.get("policy", {}).get("secrets")
                for item in (diagnostics or {}).get("console_tail", []):
                    if isinstance(item, dict):
                        self._artifacts.append(
                            session_id,
                            "console",
                            item,
                            secrets=secrets_list,
                        )
                for item in (diagnostics or {}).get("network_errors", []):
                    if isinstance(item, dict):
                        self._artifacts.append(
                            session_id,
                            "network",
                            item,
                            secrets=secrets_list,
                        )
            if not ok:
                self._write_failure_bundle(command, delivery, diagnostics or {})
            return command

    def cancel_command(self, command_id: str) -> dict[str, Any] | None:
        with self._lock:
            command = self._state["commands"].get(command_id)
            if not command:
                return None
            for client_id, delivery in command.get("deliveries", {}).items():
                if delivery.get("status") in TERMINAL_DELIVERY_STATES:
                    continue
                self._append_delivery_transition(
                    delivery,
                    "cancelled",
                    client_id=client_id,
                    reason="command_cancelled",
                )
                self._clear_lease(delivery)
            self._refresh_command_status(command)
            self._save(event_type="command_cancelled", entity_id=command_id)
            self._write_session_command_event(command, "cancelled")
            return command

    def get_command(self, command_id: str) -> dict[str, Any] | None:
        with self._lock:
            command = self._state["commands"].get(command_id)
            if not command:
                return None
            changed = self._sweep_expired()
            if changed:
                self._save(event_type="expiration_sweep", entity_id=command_id)
            return command

    def create_session(
        self,
        *,
        owner_id: str,
        client_id: str | None = None,
        ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS,
        policy: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            normalized_owner = str(owner_id or "").strip()
            if not normalized_owner:
                raise StoreValidationError("owner_id is required")
            normalized_client = str(client_id or "").strip() or None
            if normalized_client and normalized_client not in self._state["clients"]:
                raise StoreValidationError(f"Unknown browser client: {normalized_client}")
            normalized_policy = self._normalize_session_policy(policy or {})
            safe_ttl = max(
                5,
                min(
                    int(ttl_seconds),
                    int(normalized_policy["max_session_duration_seconds"]),
                    MAX_SESSION_TTL_SECONDS,
                ),
            )
            identifier = str(session_id or uuid.uuid4())
            if identifier in self._state["sessions"]:
                raise SessionConflictError(f"Session already exists: {identifier}")
            now = now_utc_iso()
            session = {
                "session_id": identifier,
                "owner_id": normalized_owner,
                "client_id": normalized_client,
                "tab_locks": [],
                "created_at": now,
                "last_activity_at": now,
                "last_heartbeat_at": now,
                "expires_at": _iso_after(seconds=safe_ttl),
                "ttl_seconds": safe_ttl,
                "artifact_dir": str(self._artifacts.session_dir(identifier)),
                "policy": normalized_policy,
                "status": "active",
                "events": [
                    {
                        "at": now,
                        "event": "session_created",
                        "reason": "api_request",
                    }
                ],
            }
            self._state["sessions"][identifier] = session
            self._artifacts.create_session(session)
            self._artifacts.append(identifier, "events", {"event": "session_created"})
            self._save(event_type="session_created", entity_id=identifier)
            return session

    @staticmethod
    def _normalize_session_policy(policy: dict[str, Any]) -> dict[str, Any]:
        normalized = {
            "allowed_domains": list(policy.get("allowed_domains") or []),
            "denied_domains": list(policy.get("denied_domains") or []),
            "read_only": bool(policy.get("read_only", False)),
            "allow_input": bool(policy.get("allow_input", True)),
            "allow_file_upload": bool(policy.get("allow_file_upload", False)),
            "allow_form_submit": bool(policy.get("allow_form_submit", False)),
            "allow_download": bool(policy.get("allow_download", False)),
            "allow_cdp": bool(policy.get("allow_cdp", False)),
            "max_tabs": max(1, int(policy.get("max_tabs", 10))),
            "max_session_duration_seconds": max(
                5,
                min(
                    int(policy.get("max_session_duration_seconds", MAX_SESSION_TTL_SECONDS)),
                    MAX_SESSION_TTL_SECONDS,
                ),
            ),
            "require_dangerous_confirmation": bool(
                policy.get("require_dangerous_confirmation", True)
            ),
            "capture_screenshots": bool(policy.get("capture_screenshots", True)),
            "capture_console": bool(policy.get("capture_console", False)),
            "capture_network": bool(policy.get("capture_network", False)),
            "capture_har": bool(policy.get("capture_har", False)),
            "capture_trace": bool(policy.get("capture_trace", False)),
            "capture_video": bool(policy.get("capture_video", False)),
            "secrets": [str(item) for item in policy.get("secrets", []) if str(item)],
        }
        if (
            normalized["capture_console"]
            or normalized["capture_network"]
            or normalized["capture_har"]
            or normalized["capture_trace"]
        ) and not normalized["allow_cdp"]:
            raise SessionPolicyError(
                "Console, network, HAR, and trace capture require allow_cdp=true"
            )
        return normalized

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            changed = self._sweep_expired()
            session = self._state["sessions"].get(session_id)
            if changed:
                self._save(event_type="session_expiration_sweep", entity_id=session_id)
            return session

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._lock:
            changed = self._sweep_expired()
            sessions = list(self._state["sessions"].values())
            sessions.sort(key=lambda item: item.get("created_at", ""), reverse=True)
            if changed:
                self._save(event_type="session_expiration_sweep")
            return sessions

    def heartbeat_session(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            self._sweep_expired()
            session = self._require_active_session(session_id)
            now = now_utc_iso()
            session["last_activity_at"] = now
            session["last_heartbeat_at"] = now
            session["expires_at"] = _iso_after(seconds=int(session["ttl_seconds"]))
            for key in list(session.get("tab_locks", [])):
                for lock in self._state["tab_locks"].get(key, []):
                    if lock.get("session_id") == session_id:
                        lock["last_heartbeat_at"] = now
                        lock["expires_at"] = session["expires_at"]
            self._save(event_type="session_heartbeat", entity_id=session_id)
            return session

    def close_session(self, session_id: str, *, reason: str = "closed_by_owner") -> dict[str, Any]:
        with self._lock:
            session = self._state["sessions"].get(session_id)
            if not session:
                raise StoreValidationError("session not found")
            if session.get("status") == "active":
                session["status"] = "closed"
                session["closed_at"] = now_utc_iso()
                session.setdefault("events", []).append(
                    {"at": now_utc_iso(), "event": "session_closed", "reason": reason}
                )
                self._release_all_session_locks(session_id)
                self._artifacts.append(
                    session_id,
                    "events",
                    {"event": "session_closed", "reason": reason},
                    secrets=session.get("policy", {}).get("secrets"),
                )
                self._save(event_type="session_closed", entity_id=session_id)
            return session

    def acquire_tab_lock(
        self,
        *,
        session_id: str,
        client_id: str,
        tab_id: int,
        lock_mode: str = "exclusive",
    ) -> dict[str, Any]:
        if lock_mode not in {"exclusive", "shared_read", "operator_override"}:
            raise StoreValidationError("Unknown tab lock mode")
        with self._lock:
            self._sweep_expired()
            session = self._require_active_session(session_id)
            if session.get("client_id") and session["client_id"] != client_id:
                raise SessionConflictError("Session belongs to another browser client")
            self._require_existing_tab(client_id, tab_id)
            key = _tab_lock_key(client_id, tab_id)
            existing = list(self._state["tab_locks"].get(key, []))
            own = next((item for item in existing if item.get("session_id") == session_id), None)
            if own:
                own["lock_mode"] = lock_mode
                own["last_heartbeat_at"] = now_utc_iso()
                own["expires_at"] = session["expires_at"]
                self._save(event_type="tab_lock_renewed", entity_id=key)
                return own

            if len(session.get("tab_locks", [])) >= int(
                session.get("policy", {}).get("max_tabs", 10)
            ):
                raise SessionPolicyError("Session reached the maximum number of locked tabs")

            if lock_mode == "operator_override":
                for item in existing:
                    previous = self._state["sessions"].get(item.get("session_id"))
                    if previous:
                        previous.setdefault("events", []).append(
                            {
                                "at": now_utc_iso(),
                                "event": "tab_lock_overridden",
                                "reason": f"operator_override:{session_id}",
                                "tab_id": tab_id,
                            }
                        )
                        if key in previous.get("tab_locks", []):
                            previous["tab_locks"].remove(key)
                existing = []
            elif lock_mode == "exclusive" and existing:
                raise SessionConflictError(f"Tab {tab_id} is already locked by another session")
            elif lock_mode == "shared_read" and any(
                item.get("lock_mode") in {"exclusive", "operator_override"} for item in existing
            ):
                raise SessionConflictError(f"Tab {tab_id} has an exclusive lock")
            elif lock_mode in {"exclusive", "operator_override"} and existing:
                raise SessionConflictError(f"Tab {tab_id} already has shared locks")

            now = now_utc_iso()
            lock = {
                "tab_id": int(tab_id),
                "client_id": client_id,
                "session_id": session_id,
                "owner_id": session["owner_id"],
                "lock_mode": lock_mode,
                "acquired_at": now,
                "expires_at": session["expires_at"],
                "last_heartbeat_at": now,
            }
            existing.append(lock)
            self._state["tab_locks"][key] = existing
            if key not in session["tab_locks"]:
                session["tab_locks"].append(key)
            if not session.get("client_id"):
                session["client_id"] = client_id
            self._artifacts.append(
                session_id,
                "events",
                {"event": "tab_lock_acquired", "lock": lock},
                secrets=session.get("policy", {}).get("secrets"),
            )
            self._save(event_type="tab_lock_acquired", entity_id=key)
            return lock

    def release_tab_lock(
        self,
        *,
        session_id: str,
        client_id: str,
        tab_id: int,
    ) -> bool:
        with self._lock:
            key = _tab_lock_key(client_id, tab_id)
            existing = self._state["tab_locks"].get(key, [])
            filtered = [item for item in existing if item.get("session_id") != session_id]
            if len(filtered) == len(existing):
                return False
            if filtered:
                self._state["tab_locks"][key] = filtered
            else:
                self._state["tab_locks"].pop(key, None)
            session = self._state["sessions"].get(session_id)
            if session and key in session.get("tab_locks", []):
                session["tab_locks"].remove(key)
            self._save(event_type="tab_lock_released", entity_id=key)
            return True

    def _require_active_session(self, session_id: str) -> dict[str, Any]:
        session = self._state["sessions"].get(session_id)
        if not session:
            raise StoreValidationError("session not found")
        if session.get("status") != "active":
            raise SessionConflictError(f"Session is not active: {session.get('status')}")
        return session

    def _require_existing_tab(self, client_id: str, tab_id: int) -> dict[str, Any]:
        client = self._state["clients"].get(client_id)
        if not client:
            raise StoreValidationError(f"Unknown browser client: {client_id}")
        for tab in client.get("tabs", []):
            if int(tab.get("id", -1)) == int(tab_id):
                return tab
        raise StoreValidationError(f"Tab {tab_id} does not exist on client {client_id}")

    def _validate_session_command(
        self,
        *,
        session_id: str,
        command: dict[str, Any],
        target: dict[str, Any],
        target_clients: list[str],
        confirmation: dict[str, Any],
    ) -> None:
        session = self._require_active_session(session_id)
        if len(target_clients) != 1:
            raise SessionPolicyError("Session commands must target exactly one client")
        client_id = target_clients[0]
        if session.get("client_id") and session["client_id"] != client_id:
            raise SessionConflictError("Command targets another browser client")
        tab_id = target.get("tab_id")
        if not isinstance(tab_id, int):
            raise SessionPolicyError("Session command requires an explicit tab_id")
        tab = self._require_existing_tab(client_id, tab_id)
        key = _tab_lock_key(client_id, tab_id)
        locks = self._state["tab_locks"].get(key, [])
        own_lock = next((item for item in locks if item.get("session_id") == session_id), None)
        if not own_lock:
            raise SessionConflictError("Session does not own a lock for the target tab")
        if command_is_mutating(command) and own_lock.get("lock_mode") == "shared_read":
            raise SessionConflictError("shared_read lock does not allow mutating commands")

        expected_url = str((command.get("preconditions") or {}).get("expected_url") or "").strip()
        if expected_url and str(tab.get("url") or "") != expected_url:
            raise SessionConflictError(
                f"Tab URL changed: expected {expected_url!r}, got {tab.get('url')!r}"
            )
        self._enforce_policy(
            session=session,
            command=command,
            tab=tab,
            confirmation=confirmation,
        )
        session["last_activity_at"] = now_utc_iso()

    def _enforce_policy(
        self,
        *,
        session: dict[str, Any],
        command: dict[str, Any],
        tab: dict[str, Any],
        confirmation: dict[str, Any],
    ) -> None:
        policy = session.get("policy", {})
        type_name = command_type(command)
        if policy.get("read_only") and not command_is_read_only(command):
            raise SessionPolicyError("Session policy allows read-only commands only")
        if type_name in INPUT_COMMANDS and not policy.get("allow_input"):
            raise SessionPolicyError("Session policy forbids text and keyboard input")
        if type_name in {"upload_file", "set_file_input_files"} and not policy.get(
            "allow_file_upload"
        ):
            raise SessionPolicyError("Session policy forbids file upload")
        needs_cdp = (
            type_name == "screenshot" or str(command.get("wait_until") or "") == "network_idle"
        )
        if needs_cdp and not policy.get("allow_cdp"):
            raise SessionPolicyError("Session policy forbids CDP")
        dangerous_action = str(command.get("dangerous_action") or "").lower()
        if dangerous_action in {"submit", "send_form"} and not policy.get("allow_form_submit"):
            raise SessionPolicyError("Session policy forbids form submission")
        if dangerous_action in {"download", "save_file"} and not policy.get("allow_download"):
            raise SessionPolicyError("Session policy forbids downloads")

        url = str(tab.get("url") or "")
        host = (urlparse(url).hostname or "").lower()
        denied = {str(item).lower() for item in policy.get("denied_domains", [])}
        allowed = {str(item).lower() for item in policy.get("allowed_domains", [])}
        if any(host == domain or host.endswith(f".{domain}") for domain in denied):
            raise SessionPolicyError(f"Domain is denied by session policy: {host}")
        if allowed and not any(host == domain or host.endswith(f".{domain}") for domain in allowed):
            raise SessionPolicyError(f"Domain is not allowed by session policy: {host}")

        dangerous = command_requires_confirmation(command) or type_name in DANGEROUS_COMMANDS
        if (
            dangerous
            and policy.get("require_dangerous_confirmation")
            and confirmation.get("confirmed") is not True
        ):
            raise SessionPolicyError("Dangerous command requires operator confirmation")

    def _expire_sessions(self, now: datetime) -> bool:
        changed = False
        for session_id, session in self._state.get("sessions", {}).items():
            if session.get("status") != "active":
                continue
            expires_at = _parse_iso(session.get("expires_at"))
            if not expires_at or now <= expires_at:
                continue
            session["status"] = "expired"
            session["expired_at"] = now_utc_iso()
            session.setdefault("events", []).append(
                {
                    "at": now_utc_iso(),
                    "event": "session_expired",
                    "reason": "heartbeat_timeout",
                }
            )
            self._release_all_session_locks(session_id)
            for command in self._state.get("commands", {}).values():
                if command.get("session_id") != session_id:
                    continue
                if command.get("status") in TERMINAL_COMMAND_STATES:
                    continue
                for client_id, delivery in command.get("deliveries", {}).items():
                    if delivery.get("status") in TERMINAL_DELIVERY_STATES:
                        continue
                    self._append_delivery_transition(
                        delivery,
                        "dead_letter",
                        client_id=client_id,
                        reason="session_heartbeat_expired",
                    )
                    self._clear_lease(delivery)
                self._refresh_command_status(command)
            self._artifacts.append(
                session_id,
                "events",
                {"event": "session_expired", "reason": "heartbeat_timeout"},
                secrets=session.get("policy", {}).get("secrets"),
            )
            changed = True
        return changed

    def _release_all_session_locks(self, session_id: str) -> None:
        session = self._state["sessions"].get(session_id)
        for key in list((session or {}).get("tab_locks", [])):
            locks = self._state["tab_locks"].get(key, [])
            remaining = [item for item in locks if item.get("session_id") != session_id]
            if remaining:
                self._state["tab_locks"][key] = remaining
            else:
                self._state["tab_locks"].pop(key, None)
        if session:
            session["tab_locks"] = []

    def _write_session_command_event(
        self,
        command: dict[str, Any],
        event: str,
        *,
        result: dict[str, Any] | None = None,
    ) -> None:
        session_id = command.get("session_id")
        if not session_id:
            return
        session = self._state["sessions"].get(session_id)
        if not session:
            return
        self._artifacts.append(
            session_id,
            "commands",
            {
                "event": event,
                "command_id": command.get("id"),
                "status": command.get("status"),
                "retry_policy": command.get("retry_policy"),
                "command": command.get("command"),
                "target": command.get("target"),
                "result": result,
            },
            secrets=session.get("policy", {}).get("secrets"),
        )

    def _write_failure_bundle(
        self,
        command: dict[str, Any],
        delivery: dict[str, Any],
        diagnostics: dict[str, Any],
    ) -> None:
        session_id = command.get("session_id")
        if not session_id:
            return
        session = self._state["sessions"].get(session_id)
        if not session:
            return
        payload = {
            "command_id": command.get("id"),
            "command": command.get("command"),
            "target": command.get("target"),
            "retry_policy": command.get("retry_policy"),
            "attempt_number": delivery.get("attempt_number"),
            "attempts": delivery.get("attempts"),
            "error": (delivery.get("result") or {}).get("error"),
            **diagnostics,
        }
        paths = self._artifacts.save_failure_bundle(
            session_id,
            str(command.get("id")),
            payload,
            secrets=session.get("policy", {}).get("secrets"),
        )
        delivery["failure_artifacts"] = paths
        self._artifacts.append(
            session_id,
            "errors",
            {"command_id": command.get("id"), "artifacts": paths, "error": payload.get("error")},
            secrets=session.get("policy", {}).get("secrets"),
        )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            changed = self._sweep_expired()
            commands = list(self._state["commands"].values())
            commands.sort(key=lambda item: item.get("created_at", ""), reverse=True)
            payload = {
                "version": self._state.get("version", STORAGE_SCHEMA_VERSION),
                "protocol_version": self._state.get("protocol_version"),
                "created_at": self._state.get("created_at"),
                "now": now_utc_iso(),
                "storage": {
                    "backend": "sqlite-wal",
                    "database_file": str(self._backend.database_file),
                    "schema_version": STORAGE_SCHEMA_VERSION,
                },
                "clients": self.list_clients(),
                "sessions": list(self._state.get("sessions", {}).values()),
                "tab_locks": self._state.get("tab_locks", {}),
                "telegram_users": dict(sorted(self._state.get("telegram_users", {}).items())),
                "queue_sizes": {key: len(value) for key, value in self._state["queues"].items()},
                "commands": commands[:200],
            }
            if changed:
                self._save(event_type="snapshot_expiration_sweep")
            return payload

    def backup(self, destination: Path | None = None) -> Path:
        with self._lock:
            self._save(event_type="backup_requested")
            return self._backend.backup(destination)

    def journal_tail(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            return self._backend.journal_tail(limit)

    def upsert_telegram_user(
        self,
        *,
        telegram_id: Any,
        username: str | None,
    ) -> dict[str, Any]:
        telegram_id_text = str(telegram_id).strip()
        if not telegram_id_text:
            raise ValueError("telegram_id is required")
        normalized_username = None
        if username is not None:
            username_text = str(username).strip()
            if username_text:
                normalized_username = (
                    username_text if username_text.startswith("@") else f"@{username_text}"
                )
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
                self._save(event_type="telegram_user_created", entity_id=telegram_id_text)
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
                self._save(event_type="telegram_user_updated", entity_id=telegram_id_text)
            return {**existing, "changed": changed}
