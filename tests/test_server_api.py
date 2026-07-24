from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from webcontrol.config import HubConfig
from webcontrol.server import HubHTTPServer
from webcontrol.store import ControlStore


class ServerApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.state_file = Path(self.tmp.name) / "state.json"
        self.config = HubConfig(
            host="127.0.0.1", port=0, token="test-token", state_file=self.state_file
        )
        self.store = ControlStore(self.state_file)
        self.server = HubHTTPServer(self.config.host, self.config.port, self.config, self.store)
        self.port = self.server.server_port
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
        )
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.tmp.cleanup()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def _request(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: dict | None = None,
        token: str | None = "test-token",
        extra_headers: dict[str, str] | None = None,
    ) -> tuple[int, dict]:
        headers = {"Accept": "application/json"}
        if token is not None:
            headers["X-Access-Token"] = token
        headers.update(extra_headers or {})
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(f"{self.base_url}{path}", data=body, method=method, headers=headers)
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def _heartbeat(self, client_id: str) -> None:
        status, payload = self._request(
            "/api/clients/heartbeat",
            method="POST",
            payload={
                "client_id": client_id,
                "extension_version": "0.1.0",
                "user_agent": "test-agent",
                "tabs": [
                    {
                        "id": 1,
                        "windowId": 1,
                        "active": True,
                        "title": client_id,
                        "url": "https://example.com",
                    }
                ],
                "meta": {"extension": "site-control-bridge"},
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])

    def test_health_does_not_require_auth(self) -> None:
        status, payload = self._request("/health", token=None)
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["service"], "site-control-hub")

    def test_token_in_url_or_body_is_rejected(self) -> None:
        status, payload = self._request("/api/clients?token=test-token", token=None)
        self.assertEqual(status, 400)
        self.assertEqual(payload["error_code"], "token_in_url_forbidden")

        status, payload = self._request(
            "/api/clients/heartbeat",
            method="POST",
            payload={"token": "test-token", "client_id": "c1"},
            token=None,
        )
        self.assertEqual(status, 400)
        self.assertEqual(payload["error_code"], "token_in_body_forbidden")

    def test_disallowed_origin_is_rejected_and_bearer_auth_works(self) -> None:
        status, payload = self._request(
            "/api/clients",
            extra_headers={"Origin": "https://untrusted.example"},
        )
        self.assertEqual(status, 403)
        self.assertEqual(payload["error_code"], "origin_denied")

        status, payload = self._request(
            "/api/clients",
            token=None,
            extra_headers={"Authorization": "Bearer test-token"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])

    def test_agent_schema_reports_protocol_and_extension_contract(self) -> None:
        status, payload = self._request("/api/agent/schema")
        self.assertEqual(status, 200)
        self.assertEqual(payload["schema"]["protocol_version"], "2.1")
        self.assertIn("smart_click", payload["schema"]["commands"])
        self.assertIn("stable_refs", payload["schema"]["compatibility"])

    def test_heartbeat_and_clients_endpoint_show_online_client(self) -> None:
        self._heartbeat("c1")

        status, payload = self._request("/api/clients")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["clients"]), 1)
        self.assertEqual(payload["clients"][0]["client_id"], "c1")
        self.assertTrue(payload["clients"][0]["is_online"])

    def test_telegram_webhook_collects_message_from_identity(self) -> None:
        status, payload = self._request(
            "/api/telegram/webhook",
            method="POST",
            payload={
                "update_id": 1,
                "message": {
                    "message_id": 10,
                    "from": {"id": 123456, "username": "alice"},
                    "text": "/start",
                },
            },
        )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["source"], "message.from")
        self.assertEqual(payload["telegram_user"]["telegram_id"], 123456)
        self.assertEqual(payload["telegram_user"]["username"], "@alice")

    def test_telegram_webhook_upserts_callback_from_username_change(self) -> None:
        self._request(
            "/api/telegram/webhook",
            method="POST",
            payload={"message": {"from": {"id": 123456, "username": "old_name"}}},
        )

        status, payload = self._request(
            "/api/telegram/webhook",
            method="POST",
            payload={
                "callback_query": {
                    "id": "callback-1",
                    "from": {"id": 123456, "username": "new_name"},
                    "data": "next",
                },
            },
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["source"], "callback_query.from")
        self.assertTrue(payload["telegram_user"]["changed"])
        self.assertEqual(payload["telegram_user"]["username"], "@new_name")

        status, state_payload = self._request("/api/state")
        self.assertEqual(status, 200)
        user = state_payload["state"]["telegram_users"]["123456"]
        self.assertEqual(user["telegram_id"], 123456)
        self.assertEqual(user["username"], "@new_name")

    def test_single_online_client_is_auto_targeted_through_api(self) -> None:
        self._heartbeat("c1")

        status, payload = self._request(
            "/api/commands",
            method="POST",
            payload={
                "issued_by": "test",
                "timeout_ms": 5000,
                "command": {"type": "extract_text", "selector": "body"},
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "queued")
        self.assertEqual(payload["target_client_ids"], ["c1"])
        self.assertIsNone(payload["error"])

        command_id = payload["command_id"]

        status, payload = self._request("/api/commands/next?client_id=c1")
        self.assertEqual(status, 200)
        self.assertEqual(payload["command"]["id"], command_id)

        status, payload = self._request(
            f"/api/commands/{command_id}/result",
            method="POST",
            payload={
                "client_id": "c1",
                "ok": True,
                "status": "completed",
                "data": {"text": "ok"},
                "error": None,
                "logs": ["done"],
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["command"]["status"], "completed")

    def test_long_poll_wakes_when_command_is_enqueued(self) -> None:
        self._heartbeat("c1")
        response: list[tuple[int, dict]] = []
        started = time.monotonic()
        waiter = threading.Thread(
            target=lambda: response.append(
                self._request("/api/commands/next?client_id=c1&wait_ms=2000")
            )
        )
        waiter.start()
        time.sleep(0.05)

        status, payload = self._request(
            "/api/commands",
            method="POST",
            payload={
                "issued_by": "test",
                "timeout_ms": 5000,
                "target": {"client_id": "c1"},
                "command": {"type": "extract_text", "selector": "body"},
            },
        )
        self.assertEqual(status, 200)

        waiter.join(timeout=1)
        self.assertFalse(waiter.is_alive())
        self.assertEqual(response[0][0], 200)
        self.assertEqual(response[0][1]["command"]["id"], payload["command_id"])
        self.assertEqual(response[0][1]["poll"]["mode"], "long_poll")
        self.assertFalse(response[0][1]["poll"]["timed_out"])
        self.assertLess((time.monotonic() - started) * 1000, 500)

    def test_long_poll_rejects_invalid_wait(self) -> None:
        self._heartbeat("c1")

        status, payload = self._request("/api/commands/next?client_id=c1&wait_ms=not-a-number")

        self.assertEqual(status, 400)
        self.assertEqual(payload["error_code"], "invalid_wait_ms")

    def test_command_is_rejected_when_multiple_online_clients_and_no_target(self) -> None:
        self._heartbeat("c1")
        self._heartbeat("c2")

        status, payload = self._request(
            "/api/commands",
            method="POST",
            payload={
                "issued_by": "test",
                "timeout_ms": 5000,
                "command": {"type": "extract_text", "selector": "body"},
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "rejected")
        self.assertEqual(payload["target_client_ids"], [])
        self.assertIn("Multiple online browser clients", payload["error"])

    def test_unknown_client_id_is_rejected_immediately(self) -> None:
        self._heartbeat("c1")

        status, payload = self._request(
            "/api/commands",
            method="POST",
            payload={
                "issued_by": "test",
                "timeout_ms": 5000,
                "target": {"client_id": "missing"},
                "command": {"type": "click", "selector": "button"},
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "rejected")
        self.assertEqual(payload["target_client_ids"], [])
        self.assertEqual(payload["error"], "Target client not found: missing")


if __name__ == "__main__":
    unittest.main()
