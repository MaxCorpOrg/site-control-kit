from __future__ import annotations

import json
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from webcontrol.store import ControlStore


class ControlStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.state_file = Path(self.tmp.name) / "state.json"
        self.store = ControlStore(self.state_file)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_single_client_command_lifecycle(self) -> None:
        self.store.register_client(
            client_id="c1",
            tabs=[{"id": 1, "url": "https://example.com", "active": True}],
            meta={},
            user_agent="test",
            extension_version="0.1",
        )

        record = self.store.enqueue_command(
            command={"type": "extract_text", "selector": "body"},
            target={"client_id": "c1"},
            timeout_ms=5000,
            issued_by="test",
        )
        self.assertEqual(record["status"], "pending")

        envelope = self.store.pop_next_command("c1")
        self.assertIsNotNone(envelope)
        self.assertEqual(envelope["command"]["type"], "extract_text")

        updated = self.store.submit_result(
            command_id=record["id"],
            client_id="c1",
            ok=True,
            status="completed",
            data={"text": "ok"},
            error=None,
            logs=[],
        )
        self.assertIsNotNone(updated)
        self.assertEqual(updated["status"], "completed")

    def test_multi_client_partial_status(self) -> None:
        for cid in ("c1", "c2"):
            self.store.register_client(
                client_id=cid,
                tabs=[],
                meta={},
                user_agent="ua",
                extension_version="0.1",
            )

        record = self.store.enqueue_command(
            command={"type": "click", "selector": "button"},
            target={"client_ids": ["c1", "c2"]},
            timeout_ms=5000,
            issued_by="test",
        )

        self.store.pop_next_command("c1")
        self.store.pop_next_command("c2")

        self.store.submit_result(
            command_id=record["id"],
            client_id="c1",
            ok=True,
            status="completed",
            data={},
            error=None,
            logs=[],
        )
        final = self.store.submit_result(
            command_id=record["id"],
            client_id="c2",
            ok=False,
            status="failed",
            data=None,
            error={"message": "boom"},
            logs=[],
        )
        self.assertEqual(final["status"], "partial")

    def test_command_expiration(self) -> None:
        self.store.register_client(
            client_id="c1",
            tabs=[],
            meta={},
            user_agent="ua",
            extension_version="0.1",
        )
        record = self.store.enqueue_command(
            command={"type": "wait_selector", "selector": "#x"},
            target={"client_id": "c1"},
            timeout_ms=1000,
            issued_by="test",
        )
        time.sleep(1.1)
        cmd = self.store.get_command(record["id"])
        self.assertIn(cmd["status"], {"expired", "pending", "in_progress", "partial"})

    def test_implicit_target_uses_single_online_client(self) -> None:
        self.store.register_client(
            client_id="c1",
            tabs=[],
            meta={},
            user_agent="ua",
            extension_version="0.1",
        )

        record = self.store.enqueue_command(
            command={"type": "extract_text", "selector": "body"},
            target={},
            timeout_ms=5000,
            issued_by="test",
        )

        self.assertEqual(record["status"], "pending")
        self.assertEqual(record["target_client_ids"], ["c1"])
        self.assertIsNone(record["rejection_reason"])

    def test_implicit_target_rejected_when_multiple_online_clients_exist(self) -> None:
        for cid in ("c1", "c2"):
            self.store.register_client(
                client_id=cid,
                tabs=[],
                meta={},
                user_agent="ua",
                extension_version="0.1",
            )

        record = self.store.enqueue_command(
            command={"type": "extract_text", "selector": "body"},
            target={},
            timeout_ms=5000,
            issued_by="test",
        )

        self.assertEqual(record["status"], "rejected")
        self.assertEqual(record["target_client_ids"], [])
        self.assertIn("Multiple online browser clients", record["rejection_reason"])

    def test_unknown_explicit_client_is_rejected_immediately(self) -> None:
        self.store.register_client(
            client_id="c1",
            tabs=[],
            meta={},
            user_agent="ua",
            extension_version="0.1",
        )

        record = self.store.enqueue_command(
            command={"type": "click", "selector": "button"},
            target={"client_id": "missing"},
            timeout_ms=5000,
            issued_by="test",
        )

        self.assertEqual(record["status"], "rejected")
        self.assertEqual(record["target_client_ids"], [])
        self.assertEqual(record["rejection_reason"], "Target client not found: missing")

    def test_list_clients_marks_stale_client_offline(self) -> None:
        self.store.register_client(
            client_id="c1",
            tabs=[],
            meta={},
            user_agent="ua",
            extension_version="0.1",
        )
        self.store._state["clients"]["c1"]["last_seen"] = (
            datetime.now(timezone.utc) - timedelta(minutes=5)
        ).isoformat()

        clients = self.store.list_clients()
        self.assertEqual(len(clients), 1)
        self.assertFalse(clients[0]["is_online"])

    def test_upsert_telegram_user_updates_username(self) -> None:
        created = self.store.upsert_telegram_user(telegram_id=123456, username="@old_name")
        updated = self.store.upsert_telegram_user(telegram_id=123456, username="@new_name")

        self.assertTrue(created["changed"])
        self.assertTrue(updated["changed"])
        self.assertEqual(updated["telegram_id"], 123456)
        self.assertEqual(updated["username"], "@new_name")

        payload = json.loads(self.state_file.read_text(encoding="utf-8"))
        self.assertEqual(payload["telegram_users"]["123456"]["username"], "@new_name")

    def test_upsert_telegram_user_clears_missing_username(self) -> None:
        self.store.upsert_telegram_user(telegram_id=123456, username="@old_name")
        updated = self.store.upsert_telegram_user(telegram_id=123456, username=None)

        self.assertTrue(updated["changed"])
        self.assertIsNone(updated["username"])

    def test_get_command_does_not_save_when_status_is_unchanged(self) -> None:
        self.store.register_client(
            client_id="c1",
            tabs=[],
            meta={},
            user_agent="ua",
            extension_version="0.1",
        )
        record = self.store.enqueue_command(
            command={"type": "extract_text", "selector": "body"},
            target={"client_id": "c1"},
            timeout_ms=5000,
            issued_by="test",
        )

        with mock.patch.object(self.store, "_save") as save_mock:
            command = self.store.get_command(record["id"])

        self.assertIsNotNone(command)
        self.assertEqual(command["status"], "pending")
        save_mock.assert_not_called()

    def test_get_command_saves_when_status_changes_due_to_expiration(self) -> None:
        self.store.register_client(
            client_id="c1",
            tabs=[],
            meta={},
            user_agent="ua",
            extension_version="0.1",
        )
        record = self.store.enqueue_command(
            command={"type": "wait_selector", "selector": "#x"},
            target={"client_id": "c1"},
            timeout_ms=1000,
            issued_by="test",
        )
        time.sleep(1.1)

        with mock.patch.object(self.store, "_save") as save_mock:
            command = self.store.get_command(record["id"])

        self.assertIsNotNone(command)
        self.assertEqual(command["status"], "expired")
        save_mock.assert_called_once()

    def test_register_client_does_not_save_on_heartbeat_only_refresh(self) -> None:
        self.store.register_client(
            client_id="c1",
            tabs=[{"id": 1, "url": "https://example.com", "active": True}],
            meta={"extension": "site-control-bridge"},
            user_agent="ua",
            extension_version="0.1",
        )

        with mock.patch.object(self.store, "_save") as save_mock:
            self.store.register_client(
                client_id="c1",
                tabs=[{"id": 1, "url": "https://example.com", "active": True}],
                meta={"extension": "site-control-bridge"},
                user_agent="ua",
                extension_version="0.1",
            )

        save_mock.assert_not_called()

    def test_pop_next_command_does_not_save_when_queue_is_empty(self) -> None:
        self.store.register_client(
            client_id="c1",
            tabs=[],
            meta={},
            user_agent="ua",
            extension_version="0.1",
        )

        with mock.patch.object(self.store, "_save") as save_mock:
            envelope = self.store.pop_next_command("c1")

        self.assertIsNone(envelope)
        save_mock.assert_not_called()

    def test_snapshot_does_not_save_when_statuses_are_unchanged(self) -> None:
        self.store.register_client(
            client_id="c1",
            tabs=[],
            meta={},
            user_agent="ua",
            extension_version="0.1",
        )
        self.store.enqueue_command(
            command={"type": "extract_text", "selector": "body"},
            target={"client_id": "c1"},
            timeout_ms=5000,
            issued_by="test",
        )

        with mock.patch.object(self.store, "_save") as save_mock:
            payload = self.store.snapshot()

        self.assertIn("clients", payload)
        save_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
