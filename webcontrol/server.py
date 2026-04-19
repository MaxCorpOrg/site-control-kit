from __future__ import annotations

import json
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from .config import HubConfig
from .store import ControlStore

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

    def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Access-Token")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

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

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Access-Token")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/health":
            self._send_json(HTTPStatus.OK, {"ok": True, "service": "site-control-hub", "version": "0.1"})
            return

        query_token = query.get("token", [None])[0]
        header_token = self._extract_header_token()
        token = header_token or query_token

        if not self._require_auth(token):
            return

        if path == "/api/state":
            self._send_json(HTTPStatus.OK, {"ok": True, "state": self.hub.store.snapshot()})
            return

        if path == "/api/clients":
            self._send_json(HTTPStatus.OK, {"ok": True, "clients": self.hub.store.list_clients()})
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

        self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        payload = self._read_json_body()

        token = payload.get("token") or self._extract_header_token()
        if not self._require_auth(token):
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

            timeout_ms = int(payload.get("timeout_ms", 20000))
            timeout_ms = max(1000, min(timeout_ms, 30 * 60 * 1000))

            issued_by = str(payload.get("issued_by", "api"))

            record = self.hub.store.enqueue_command(
                command=command,
                target=target,
                timeout_ms=timeout_ms,
                issued_by=issued_by,
            )
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "command_id": record["id"],
                    "status": record["status"],
                    "target_client_ids": record.get("target_client_ids", []),
                },
            )
            return

        if path.startswith("/api/commands/"):
            chunks = [chunk for chunk in path.split("/") if chunk]
            if len(chunks) == 4 and chunks[3] == "result":
                command_id = chunks[2]
                client_id = str(payload.get("client_id", "")).strip()
                if not client_id:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "client_id is required"})
                    return

                command = self.hub.store.submit_result(
                    command_id=command_id,
                    client_id=client_id,
                    ok=bool(payload.get("ok", False)),
                    status=payload.get("status"),
                    data=payload.get("data"),
                    error=payload.get("error"),
                    logs=payload.get("logs"),
                )
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


def run_server(config: HubConfig) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    store = ControlStore(config.state_file)
    server = HubHTTPServer(config.host, config.port, config, store)
    LOGGER.info("Server started on %s", config.base_url)
    LOGGER.info("State file: %s", config.state_file)

    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        LOGGER.info("Interrupted, shutting down")
    finally:
        server.shutdown()
        server.server_close()
        LOGGER.info("Stopped")
