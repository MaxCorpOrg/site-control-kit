from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .store import ControlStore

MAX_LONG_POLL_WAIT_MS = 25_000
LONG_POLL_SWEEP_INTERVAL_SECONDS = 1.0


@dataclass(frozen=True, slots=True)
class CommandWaitResult:
    command: dict[str, Any] | None
    mode: str
    wait_ms: int
    waited_ms: int
    timed_out: bool


class CommandService(Protocol):
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
    ) -> dict[str, Any]: ...

    def next_command(self, client_id: str, *, wait_ms: int = 0) -> CommandWaitResult: ...

    def get_command(self, command_id: str) -> dict[str, Any] | None: ...

    def acknowledge_delivery(
        self,
        *,
        command_id: str,
        client_id: str,
        delivery_id: str,
        lease_token: str,
    ) -> dict[str, Any]: ...

    def update_delivery_status(
        self,
        *,
        command_id: str,
        client_id: str,
        delivery_id: str,
        lease_token: str,
        status: str,
        reason: str = "client_status_update",
    ) -> dict[str, Any]: ...

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
    ) -> dict[str, Any] | None: ...

    def cancel_command(self, command_id: str) -> dict[str, Any] | None: ...


class ClientService(Protocol):
    def register_client(
        self,
        *,
        client_id: str,
        tabs: list[dict[str, Any]] | None,
        meta: dict[str, Any] | None,
        user_agent: str | None,
        extension_version: str | None,
    ) -> dict[str, Any]: ...

    def list_clients(self) -> list[dict[str, Any]]: ...


class SessionService(Protocol):
    def create_session(
        self,
        *,
        owner_id: str,
        client_id: str | None = None,
        ttl_seconds: int = 300,
        policy: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]: ...

    def get_session(self, session_id: str) -> dict[str, Any] | None: ...

    def list_sessions(self) -> list[dict[str, Any]]: ...

    def heartbeat_session(self, session_id: str) -> dict[str, Any]: ...

    def close_session(
        self,
        session_id: str,
        *,
        reason: str = "closed_by_owner",
    ) -> dict[str, Any]: ...

    def acquire_tab_lock(
        self,
        *,
        session_id: str,
        client_id: str,
        tab_id: int,
        lock_mode: str,
    ) -> dict[str, Any]: ...

    def release_tab_lock(
        self,
        *,
        session_id: str,
        client_id: str,
        tab_id: int,
    ) -> bool: ...


class StateService(Protocol):
    def snapshot(self) -> dict[str, Any]: ...

    def backup(self, destination: Path | None = None) -> Path: ...

    def journal_tail(self, limit: int = 100) -> list[dict[str, Any]]: ...


class StoreCommandService:
    """Командный сервис с совместимым ожиданием поверх ControlStore."""

    def __init__(self, store: ControlStore):
        self.store = store
        self._available = threading.Condition()

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
        with self._available:
            record = self.store.enqueue_command(
                command=command,
                target=target,
                timeout_ms=timeout_ms,
                issued_by=issued_by,
                idempotency_key=idempotency_key,
                retry_policy=retry_policy,
                lease_duration_ms=lease_duration_ms,
                max_attempts=max_attempts,
                session_id=session_id,
                confirmation=confirmation,
            )
            if record.get("status") == "queued":
                self._available.notify_all()
            return record

    def next_command(self, client_id: str, *, wait_ms: int = 0) -> CommandWaitResult:
        safe_wait_ms = max(0, min(int(wait_ms), MAX_LONG_POLL_WAIT_MS))
        mode = "long_poll" if safe_wait_ms else "immediate"
        started = time.monotonic()
        deadline = started + safe_wait_ms / 1000

        with self._available:
            while True:
                command = self.store.pop_next_command(client_id)
                if command is not None:
                    return self._wait_result(
                        command=command,
                        mode=mode,
                        wait_ms=safe_wait_ms,
                        started=started,
                        timed_out=False,
                    )
                remaining = deadline - time.monotonic()
                if safe_wait_ms == 0 or remaining <= 0:
                    return self._wait_result(
                        command=None,
                        mode=mode,
                        wait_ms=safe_wait_ms,
                        started=started,
                        timed_out=safe_wait_ms > 0,
                    )
                self._available.wait(timeout=min(remaining, LONG_POLL_SWEEP_INTERVAL_SECONDS))

    @staticmethod
    def _wait_result(
        *,
        command: dict[str, Any] | None,
        mode: str,
        wait_ms: int,
        started: float,
        timed_out: bool,
    ) -> CommandWaitResult:
        return CommandWaitResult(
            command=command,
            mode=mode,
            wait_ms=wait_ms,
            waited_ms=max(0, round((time.monotonic() - started) * 1000)),
            timed_out=timed_out,
        )

    def get_command(self, command_id: str) -> dict[str, Any] | None:
        return self.store.get_command(command_id)

    def acknowledge_delivery(
        self,
        *,
        command_id: str,
        client_id: str,
        delivery_id: str,
        lease_token: str,
    ) -> dict[str, Any]:
        return self.store.acknowledge_delivery(
            command_id=command_id,
            client_id=client_id,
            delivery_id=delivery_id,
            lease_token=lease_token,
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
        return self.store.update_delivery_status(
            command_id=command_id,
            client_id=client_id,
            delivery_id=delivery_id,
            lease_token=lease_token,
            status=status,
            reason=reason,
        )

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
        return self.store.submit_result(
            command_id=command_id,
            client_id=client_id,
            ok=ok,
            status=status,
            data=data,
            error=error,
            logs=logs,
            delivery_id=delivery_id,
            lease_token=lease_token,
            result_id=result_id,
            finished_at=finished_at,
            diagnostics=diagnostics,
        )

    def cancel_command(self, command_id: str) -> dict[str, Any] | None:
        return self.store.cancel_command(command_id)


class StoreClientService:
    def __init__(self, store: ControlStore):
        self.store = store

    def register_client(
        self,
        *,
        client_id: str,
        tabs: list[dict[str, Any]] | None,
        meta: dict[str, Any] | None,
        user_agent: str | None,
        extension_version: str | None,
    ) -> dict[str, Any]:
        return self.store.register_client(
            client_id=client_id,
            tabs=tabs,
            meta=meta,
            user_agent=user_agent,
            extension_version=extension_version,
        )

    def list_clients(self) -> list[dict[str, Any]]:
        return self.store.list_clients()


class StoreSessionService:
    def __init__(self, store: ControlStore):
        self.store = store

    def create_session(
        self,
        *,
        owner_id: str,
        client_id: str | None = None,
        ttl_seconds: int = 300,
        policy: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        return self.store.create_session(
            owner_id=owner_id,
            client_id=client_id,
            ttl_seconds=ttl_seconds,
            policy=policy,
            session_id=session_id,
        )

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        return self.store.get_session(session_id)

    def list_sessions(self) -> list[dict[str, Any]]:
        return self.store.list_sessions()

    def heartbeat_session(self, session_id: str) -> dict[str, Any]:
        return self.store.heartbeat_session(session_id)

    def close_session(
        self,
        session_id: str,
        *,
        reason: str = "closed_by_owner",
    ) -> dict[str, Any]:
        return self.store.close_session(session_id, reason=reason)

    def acquire_tab_lock(
        self,
        *,
        session_id: str,
        client_id: str,
        tab_id: int,
        lock_mode: str,
    ) -> dict[str, Any]:
        return self.store.acquire_tab_lock(
            session_id=session_id,
            client_id=client_id,
            tab_id=tab_id,
            lock_mode=lock_mode,
        )

    def release_tab_lock(
        self,
        *,
        session_id: str,
        client_id: str,
        tab_id: int,
    ) -> bool:
        return self.store.release_tab_lock(
            session_id=session_id,
            client_id=client_id,
            tab_id=tab_id,
        )


class StoreStateService:
    def __init__(self, store: ControlStore):
        self.store = store

    def snapshot(self) -> dict[str, Any]:
        return self.store.snapshot()

    def backup(self, destination: Path | None = None) -> Path:
        return self.store.backup(destination)

    def journal_tail(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.store.journal_tail(limit)


@dataclass(slots=True)
class HubServices:
    commands: CommandService
    clients: ClientService
    sessions: SessionService
    state: StateService

    @classmethod
    def from_store(cls, store: ControlStore) -> HubServices:
        return cls(
            commands=StoreCommandService(store),
            clients=StoreClientService(store),
            sessions=StoreSessionService(store),
            state=StoreStateService(store),
        )
