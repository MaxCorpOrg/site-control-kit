from __future__ import annotations

import json
import logging
import os
from fnmatch import fnmatch
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .browser_agent import agent_api_schema
from .config import HubConfig
from .runtime_logging import RuntimeEventLogger
from .settings import load_runtime_settings
from .store import (
    ControlStore,
    IdempotencyConflictError,
    ResultConflictError,
    ResultValidationError,
    SessionConflictError,
    SessionPolicyError,
    StaleLeaseError,
    StoreValidationError,
)

LOGGER = logging.getLogger("webcontrol.server")


class HubHTTPServer(ThreadingHTTPServer):
    def __init__(self, host: str, port: int, config: HubConfig, store: ControlStore):
        super().__init__((host, port), HubRequestHandler)
        self.config = config
        self.store = store


class HubRequestHandler(BaseHTTPRequestHandler):
    server_version = "SiteControlHub/0.1"

    @property
    def hub(self) -> HubHTTPServer:
        return self.server  # type: ignore[return-value]

    def log_message(self, fmt: str, *args: Any) -> None:
        LOGGER.info("%s - %s", self.client_address[0], fmt % args)

    def _allowed_origin(self) -> str | None:
        origin = str(self.headers.get("Origin") or "").strip()
        if not origin:
            return None
        if any(fnmatch(origin, pattern) for pattern in self.hub.config.allowed_origins):
            return origin
        return ""

    def _send_cors_headers(self) -> None:
        allowed = self._allowed_origin()
        if allowed:
            self.send_header("Access-Control-Allow-Origin", allowed)
            self.send_header("Vary", "Origin")
            self.send_header(
                "Access-Control-Allow-Headers",
                "Content-Type, Authorization, X-Access-Token",
            )
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors_headers()
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            LOGGER.info("%s - response connection closed by client", self.client_address[0])

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}
        if isinstance(payload, dict):
            return payload
        return {}

    def _extract_header_token(self) -> str | None:
        token = self.headers.get("X-Access-Token")
        if token:
            return token.strip()

        auth = self.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
        return None

    def _authorized(self, token: str | None) -> bool:
        expected = self.hub.config.token
        return bool(token) and token == expected

    def _require_auth(self, token: str | None) -> bool:
        if self._authorized(token):
            return True
        self._send_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "unauthorized"})
        return False

    def _send_store_error(self, exc: StoreValidationError) -> None:
        if isinstance(
            exc,
            (
                IdempotencyConflictError,
                ResultConflictError,
                SessionConflictError,
                SessionPolicyError,
                StaleLeaseError,
            ),
        ):
            status = HTTPStatus.CONFLICT
        elif isinstance(exc, ResultValidationError) and "not found" in str(exc):
            status = HTTPStatus.NOT_FOUND
        else:
            status = HTTPStatus.BAD_REQUEST
        self._send_json(
            status,
            {
                "ok": False,
                "error": str(exc),
                "error_code": exc.error_code,
            },
        )

    def _extract_telegram_from_user(self, payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
        for source_key in ("message", "callback_query"):
            source = payload.get(source_key)
            if not isinstance(source, dict):
                continue
            from_user = source.get("from")
            if isinstance(from_user, dict):
                return from_user, f"{source_key}.from"

        from_user = payload.get("from")
        if isinstance(from_user, dict):
            return from_user, "from"
        return None, None

    def do_OPTIONS(self) -> None:  # noqa: N802
        if self._allowed_origin() == "":
            self._send_json(
                HTTPStatus.FORBIDDEN,
                {"ok": False, "error": "origin is not allowed", "error_code": "origin_denied"},
            )
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if self._allowed_origin() == "":
            self._send_json(
                HTTPStatus.FORBIDDEN,
                {"ok": False, "error": "origin is not allowed", "error_code": "origin_denied"},
            )
            return
        if path == "/health":
            self._send_json(HTTPStatus.OK, {"ok": True, "service": "site-control-hub", "version": "0.1"})
            return

        if "token" in query:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {
                    "ok": False,
                    "error": "tokens in URL are forbidden; use an HTTP header",
                    "error_code": "token_in_url_forbidden",
                },
            )
            return
        if not self._require_auth(self._extract_header_token()):
            return

        if path == "/api/state":
            self._send_json(HTTPStatus.OK, {"ok": True, "state": self.hub.store.snapshot()})
            return

        if path == "/api/clients":
            self._send_json(HTTPStatus.OK, {"ok": True, "clients": self.hub.store.list_clients()})
            return

        if path == "/api/agent/schema":
            self._send_json(HTTPStatus.OK, {"ok": True, "schema": agent_api_schema()})
            return

        if path == "/api/sessions":
            self._send_json(
                HTTPStatus.OK,
                {"ok": True, "sessions": self.hub.store.list_sessions()},
            )
            return

        if path == "/api/storage/journal":
            limit_raw = query.get("limit", ["100"])[0]
            try:
                limit = int(limit_raw)
            except ValueError:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"ok": False, "error": "limit must be an integer"},
                )
                return
            self._send_json(
                HTTPStatus.OK,
                {"ok": True, "events": self.hub.store.journal_tail(limit)},
            )
            return

        if path == "/api/commands/next":
            client_id = query.get("client_id", [""])[0].strip()
            if not client_id:
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "client_id is required"})
                return
            command = self.hub.store.pop_next_command(client_id)
            self._send_json(HTTPStatus.OK, {"ok": True, "command": command})
            return

        if path.startswith("/api/commands/"):
            chunks = [chunk for chunk in path.split("/") if chunk]
            if len(chunks) == 3:
                command_id = chunks[2]
                command = self.hub.store.get_command(command_id)
                if not command:
                    self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "command not found"})
                    return
                self._send_json(HTTPStatus.OK, {"ok": True, "command": command})
                return

        if path.startswith("/api/sessions/"):
            chunks = [chunk for chunk in path.split("/") if chunk]
            if len(chunks) == 3:
                session = self.hub.store.get_session(chunks[2])
                if not session:
                    self._send_json(
                        HTTPStatus.NOT_FOUND,
                        {"ok": False, "error": "session not found"},
                    )
                    return
                self._send_json(HTTPStatus.OK, {"ok": True, "session": session})
                return

        self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        payload = self._read_json_body()

        if self._allowed_origin() == "":
            self._send_json(
                HTTPStatus.FORBIDDEN,
                {"ok": False, "error": "origin is not allowed", "error_code": "origin_denied"},
            )
            return
        if "token" in payload:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {
                    "ok": False,
                    "error": "tokens in request bodies are forbidden; use an HTTP header",
                    "error_code": "token_in_body_forbidden",
                },
            )
            return
        if not self._require_auth(self._extract_header_token()):
            return

        if path == "/api/clients/heartbeat":
            client_id = str(payload.get("client_id", "")).strip()
            if not client_id:
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "client_id is required"})
                return

            tabs = payload.get("tabs")
            if not isinstance(tabs, list):
                tabs = []

            meta = payload.get("meta")
            if not isinstance(meta, dict):
                meta = {}

            client = self.hub.store.register_client(
                client_id=client_id,
                tabs=tabs,
                meta=meta,
                user_agent=payload.get("user_agent"),
                extension_version=payload.get("extension_version"),
            )
            self._send_json(HTTPStatus.OK, {"ok": True, "client": client})
            return

        if path == "/api/sessions":
            policy = payload.get("policy")
            if not isinstance(policy, dict):
                policy = {}
            try:
                session = self.hub.store.create_session(
                    owner_id=str(payload.get("owner_id") or ""),
                    client_id=str(payload.get("client_id") or "") or None,
                    ttl_seconds=int(payload.get("ttl_seconds", 300)),
                    policy=policy,
                    session_id=str(payload.get("session_id") or "") or None,
                )
            except (StoreValidationError, ValueError) as exc:
                if isinstance(exc, StoreValidationError):
                    self._send_store_error(exc)
                else:
                    self._send_json(
                        HTTPStatus.BAD_REQUEST,
                        {"ok": False, "error": str(exc), "error_code": "validation_error"},
                    )
                return
            self._send_json(HTTPStatus.CREATED, {"ok": True, "session": session})
            return

        if path == "/api/storage/backup":
            destination_raw = str(payload.get("destination") or "").strip()
            destination = Path(destination_raw).expanduser() if destination_raw else None
            backup = self.hub.store.backup(destination)
            self._send_json(
                HTTPStatus.OK,
                {"ok": True, "backup_file": str(backup)},
            )
            return

        if path.startswith("/api/sessions/"):
            chunks = [chunk for chunk in path.split("/") if chunk]
            if len(chunks) >= 4:
                session_id = chunks[2]
                try:
                    if len(chunks) == 4 and chunks[3] == "heartbeat":
                        session = self.hub.store.heartbeat_session(session_id)
                        self._send_json(HTTPStatus.OK, {"ok": True, "session": session})
                        return
                    if len(chunks) == 4 and chunks[3] == "close":
                        session = self.hub.store.close_session(
                            session_id,
                            reason=str(payload.get("reason") or "closed_by_owner"),
                        )
                        self._send_json(HTTPStatus.OK, {"ok": True, "session": session})
                        return
                    if len(chunks) == 4 and chunks[3] == "locks":
                        lock = self.hub.store.acquire_tab_lock(
                            session_id=session_id,
                            client_id=str(payload.get("client_id") or ""),
                            tab_id=int(payload.get("tab_id")),
                            lock_mode=str(payload.get("lock_mode") or "exclusive"),
                        )
                        self._send_json(HTTPStatus.OK, {"ok": True, "lock": lock})
                        return
                    if len(chunks) == 5 and chunks[3:] == ["locks", "release"]:
                        released = self.hub.store.release_tab_lock(
                            session_id=session_id,
                            client_id=str(payload.get("client_id") or ""),
                            tab_id=int(payload.get("tab_id")),
                        )
                        self._send_json(HTTPStatus.OK, {"ok": True, "released": released})
                        return
                except (StoreValidationError, ValueError, TypeError) as exc:
                    if isinstance(exc, StoreValidationError):
                        self._send_store_error(exc)
                    else:
                        self._send_json(
                            HTTPStatus.BAD_REQUEST,
                            {"ok": False, "error": str(exc), "error_code": "validation_error"},
                        )
                    return

        if path == "/api/telegram/webhook":
            from_user, source = self._extract_telegram_from_user(payload)
            if not from_user or from_user.get("id") is None:
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "telegram from.id is required"})
                return

            username_raw = str(from_user.get("username", "")).strip()
            username = f"@{username_raw}" if username_raw else None
            user = self.hub.store.upsert_telegram_user(
                telegram_id=from_user.get("id"),
                username=username,
            )
            LOGGER.info(
                "telegram user upsert source=%s telegram_id=%s username=%s changed=%s",
                source,
                user.get("telegram_id"),
                user.get("username"),
                user.get("changed"),
            )
            self._send_json(HTTPStatus.OK, {"ok": True, "telegram_user": user, "source": source})
            return

        if path == "/api/commands":
            command = payload.get("command")
            if not isinstance(command, dict):
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "command must be an object"})
                return
            if not command.get("type"):
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "command.type is required"})
                return

            target = payload.get("target")
            if not isinstance(target, dict):
                target = {}

            try:
                timeout_ms = int(payload.get("timeout_ms", 20000))
            except (TypeError, ValueError):
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"ok": False, "error": "timeout_ms must be an integer"},
                )
                return
            timeout_ms = max(1000, min(timeout_ms, 30 * 60 * 1000))

            issued_by = str(payload.get("issued_by", "api"))

            confirmation = payload.get("confirmation")
            if not isinstance(confirmation, dict):
                confirmation = {}
            try:
                record = self.hub.store.enqueue_command(
                    command=command,
                    target=target,
                    timeout_ms=timeout_ms,
                    issued_by=issued_by,
                    idempotency_key=payload.get("idempotency_key"),
                    retry_policy=payload.get("retry_policy"),
                    lease_duration_ms=payload.get("lease_duration_ms"),
                    max_attempts=payload.get("max_attempts"),
                    session_id=str(payload.get("session_id") or "") or None,
                    confirmation=confirmation,
                )
            except (StoreValidationError, ValueError, TypeError) as exc:
                if isinstance(exc, StoreValidationError):
                    self._send_store_error(exc)
                else:
                    self._send_json(
                        HTTPStatus.BAD_REQUEST,
                        {"ok": False, "error": str(exc), "error_code": "validation_error"},
                    )
                return
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "command_id": record["id"],
                    "status": record["status"],
                    "target_client_ids": record.get("target_client_ids", []),
                    "error": record.get("rejection_reason"),
                    "retry_policy": record.get("retry_policy"),
                    "idempotency_key": record.get("idempotency_key"),
                    "idempotency_reused": bool(record.get("idempotency_reused")),
                },
            )
            return

        if path.startswith("/api/commands/"):
            chunks = [chunk for chunk in path.split("/") if chunk]
            if len(chunks) == 4 and chunks[3] == "ack":
                command_id = chunks[2]
                try:
                    command = self.hub.store.acknowledge_delivery(
                        command_id=command_id,
                        client_id=str(payload.get("client_id") or ""),
                        delivery_id=str(payload.get("delivery_id") or ""),
                        lease_token=str(payload.get("lease_token") or ""),
                    )
                except StoreValidationError as exc:
                    self._send_store_error(exc)
                    return
                self._send_json(HTTPStatus.OK, {"ok": True, "command": command})
                return

            if len(chunks) == 4 and chunks[3] == "status":
                command_id = chunks[2]
                try:
                    command = self.hub.store.update_delivery_status(
                        command_id=command_id,
                        client_id=str(payload.get("client_id") or ""),
                        delivery_id=str(payload.get("delivery_id") or ""),
                        lease_token=str(payload.get("lease_token") or ""),
                        status=str(payload.get("status") or ""),
                        reason=str(payload.get("reason") or "client_status_update"),
                    )
                except StoreValidationError as exc:
                    self._send_store_error(exc)
                    return
                self._send_json(HTTPStatus.OK, {"ok": True, "command": command})
                return

            if len(chunks) == 4 and chunks[3] == "result":
                command_id = chunks[2]
                client_id = str(payload.get("client_id", "")).strip()
                if not client_id:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "client_id is required"})
                    return

                diagnostics = payload.get("diagnostics")
                if not isinstance(diagnostics, dict):
                    diagnostics = {}
                try:
                    command = self.hub.store.submit_result(
                        command_id=command_id,
                        client_id=client_id,
                        ok=bool(payload.get("ok", False)),
                        status=payload.get("status"),
                        data=payload.get("data"),
                        error=payload.get("error"),
                        logs=payload.get("logs"),
                        delivery_id=payload.get("delivery_id"),
                        lease_token=payload.get("lease_token"),
                        result_id=payload.get("result_id"),
                        finished_at=payload.get("finished_at"),
                        diagnostics=diagnostics,
                    )
                except StoreValidationError as exc:
                    self._send_store_error(exc)
                    return
                if not command:
                    self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "command not found"})
                    return
                self._send_json(HTTPStatus.OK, {"ok": True, "command": command})
                return

            if len(chunks) == 4 and chunks[3] == "cancel":
                command_id = chunks[2]
                command = self.hub.store.cancel_command(command_id)
                if not command:
                    self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "command not found"})
                    return
                self._send_json(HTTPStatus.OK, {"ok": True, "command": command})
                return

        self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})


def run_server(config: HubConfig, *, log_path: str | None = None) -> None:
    settings = load_runtime_settings(mutate=True)
    runtime_logger = RuntimeEventLogger(
        events_path=settings.runtime_events_log_file,
        errors_path=settings.runtime_errors_log_file,
    )
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_path:
        file_path = Path(log_path).expanduser()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(file_path, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=handlers,
        force=True,
    )
    store = ControlStore(
        config.state_file,
        lease_duration_ms=config.lease_duration_ms,
        max_attempts=config.max_attempts,
        artifacts_root=config.artifacts_root,
    )
    server = HubHTTPServer(config.host, config.port, config, store)
    LOGGER.info("Server started on %s", config.base_url)
    LOGGER.info("State file: %s", config.state_file)
    if log_path:
        LOGGER.info("Hub log: %s", log_path)
    runtime_logger.log_event(
        component="hub",
        event="server_started",
        status="running",
        message=f"Hub started on {config.base_url}",
        details={
            "host": config.host,
            "port": config.port,
            "state_file": str(config.state_file),
            "log_path": str(log_path or ""),
            "pid": os.getpid(),
        },
    )

    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        LOGGER.info("Interrupted, shutting down")
        runtime_logger.log_event(
            component="hub",
            event="server_interrupted",
            status="stopping",
            message="Hub interrupted by KeyboardInterrupt",
            details={"pid": os.getpid()},
        )
    except Exception as exc:
        runtime_logger.log_exception(
            component="hub",
            event="server_crashed",
            exc=exc,
            message="Hub crashed",
            details={
                "host": config.host,
                "port": config.port,
                "state_file": str(config.state_file),
            },
        )
        raise
    finally:
        server.shutdown()
        server.server_close()
        LOGGER.info("Stopped")
        runtime_logger.log_event(
            component="hub",
            event="server_stopped",
            status="stopped",
            message="Hub stopped",
            details={"pid": os.getpid()},
        )
