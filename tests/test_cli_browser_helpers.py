from __future__ import annotations

import unittest

from webcontrol.cli import _extract_command_result, _pick_client


class BrowserCliHelperTests(unittest.TestCase):
    def test_pick_client_by_requested_id(self) -> None:
        clients = [
            {"client_id": "client-a", "last_seen": "2026-03-31T10:00:00+00:00"},
            {"client_id": "client-b", "last_seen": "2026-03-31T11:00:00+00:00"},
        ]
        selected = _pick_client(clients, "client-a")
        self.assertEqual(selected["client_id"], "client-a")

    def test_pick_client_uses_freshest_when_not_specified(self) -> None:
        clients = [
            {"client_id": "client-a", "last_seen": "2026-03-31T10:00:00+00:00"},
            {"client_id": "client-b", "last_seen": "2026-03-31T11:00:00+00:00"},
        ]
        selected = _pick_client(clients)
        self.assertEqual(selected["client_id"], "client-b")

    def test_pick_client_uses_freshest_online_when_required(self) -> None:
        clients = [
            {"client_id": "client-a", "last_seen": "2026-03-31T12:00:00+00:00", "is_online": False},
            {"client_id": "client-b", "last_seen": "2026-03-31T11:00:00+00:00", "is_online": True},
        ]
        selected = _pick_client(clients, require_online=True)
        self.assertEqual(selected["client_id"], "client-b")

    def test_pick_client_rejects_offline_requested_client_when_online_required(self) -> None:
        clients = [
            {"client_id": "client-a", "last_seen": "2026-03-31T12:00:00+00:00", "is_online": False},
        ]
        with self.assertRaisesRegex(RuntimeError, "offline"):
            _pick_client(clients, "client-a", require_online=True)

    def test_extract_command_result_for_selected_client(self) -> None:
        command = {
            "deliveries": {
                "client-a": {"result": {"ok": True, "data": {"text": "hello"}}},
                "client-b": {"result": {"ok": False, "error": {"message": "boom"}}},
            }
        }
        result = _extract_command_result(command, "client-a")
        self.assertEqual(result["data"]["text"], "hello")


if __name__ == "__main__":
    unittest.main()
