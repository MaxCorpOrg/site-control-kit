from __future__ import annotations

import json
import tempfile
import threading
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
        self.config = HubConfig(host="127.0.0.1", port=0, token="test-token", state_file=self.state_file)
        self.store = ControlStore(self.state_file)
        self.server = HubHTTPServer(self.config.host, self.config.port, self.config, self.store)
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
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
    ) -> tuple[int, dict]:
        headers = {"Accept": "application/json"}
        if token is not None:
            headers["X-Access-Token"] = token
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
                "tabs": [{"id": 1, "windowId": 1, "active": True, "title": client_id, "url": "https://example.com"}],
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

    def test_heartbeat_and_clients_endpoint_show_online_client(self) -> None:
        self._heartbeat("c1")

        status, payload = self._request("/api/clients")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["clients"]), 1)
        self.assertEqual(payload["clients"][0]["client_id"], "c1")
        self.assertTrue(payload["clients"][0]["is_online"])

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
        self.assertEqual(payload["status"], "pending")
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
