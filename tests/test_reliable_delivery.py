from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from webcontrol.store import (
    ControlStore,
    IdempotencyConflictError,
    ResultConflictError,
    StaleLeaseError,
)


class ReliableDeliveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ControlStore(
            Path(self.tmp.name) / "state.json",
            lease_duration_ms=1_000,
            max_attempts=3,
        )
        self.store.register_client(
            client_id="browser-1",
            tabs=[
                {
                    "id": 7,
                    "windowId": 1,
                    "url": "https://example.com/form",
                    "title": "Example",
                    "active": True,
                }
            ],
            meta={},
            user_agent="test",
            extension_version="0.2.0",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _enqueue(self, command: dict, **kwargs):
        return self.store.enqueue_command(
            command=command,
            target={"client_id": "browser-1", "tab_id": 7},
            timeout_ms=30_000,
            issued_by="test",
            **kwargs,
        )

    def _expire(self, command_id: str) -> None:
        delivery = self.store._state["commands"][command_id]["deliveries"]["browser-1"]
        delivery["lease_expires_at"] = (
            datetime.now(timezone.utc) - timedelta(seconds=1)
        ).isoformat()

    def test_safe_command_is_reissued_and_stale_result_is_rejected(self) -> None:
        record = self._enqueue({"type": "extract_text", "selector": "body"})
        first = self.store.pop_next_command("browser-1")
        self.assertEqual(first["attempt_number"], 1)

        self._expire(record["id"])
        second = self.store.pop_next_command("browser-1")

        self.assertIsNotNone(second)
        self.assertEqual(second["attempt_number"], 2)
        self.assertNotEqual(first["delivery_id"], second["delivery_id"])
        with self.assertRaises(StaleLeaseError):
            self.store.submit_result(
                command_id=record["id"],
                client_id="browser-1",
                delivery_id=first["delivery_id"],
                lease_token=first["lease_token"],
                result_id="old-result",
                ok=True,
                status="completed",
                data={"text": "stale"},
                error=None,
                logs=[],
            )

        completed = self.store.submit_result(
            command_id=record["id"],
            client_id="browser-1",
            delivery_id=second["delivery_id"],
            lease_token=second["lease_token"],
            result_id="current-result",
            ok=True,
            status="completed",
            data={"text": "fresh"},
            error=None,
            logs=[],
        )
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(
            completed["deliveries"]["browser-1"]["result"]["data"]["text"],
            "fresh",
        )

    def test_dangerous_running_command_is_not_executed_twice(self) -> None:
        record = self._enqueue(
            {"type": "smart_click", "locator": {"strategy": "role", "value": "button"}},
            retry_policy="retry_if_not_started",
        )
        envelope = self.store.pop_next_command("browser-1")
        self.store.acknowledge_delivery(
            command_id=record["id"],
            client_id="browser-1",
            delivery_id=envelope["delivery_id"],
            lease_token=envelope["lease_token"],
        )
        self.store.update_delivery_status(
            command_id=record["id"],
            client_id="browser-1",
            delivery_id=envelope["delivery_id"],
            lease_token=envelope["lease_token"],
            status="running",
        )

        self._expire(record["id"])
        self.assertIsNone(self.store.pop_next_command("browser-1"))
        current = self.store.get_command(record["id"])
        self.assertEqual(current["status"], "dead_letter")
        self.assertEqual(current["deliveries"]["browser-1"]["attempt_number"], 1)

    def test_acknowledged_but_not_started_command_can_be_reissued(self) -> None:
        record = self._enqueue(
            {"type": "set_editable_text", "locator": {"strategy": "css", "value": "#name"}},
            retry_policy="retry_if_not_started",
        )
        first = self.store.pop_next_command("browser-1")
        self.store.acknowledge_delivery(
            command_id=record["id"],
            client_id="browser-1",
            delivery_id=first["delivery_id"],
            lease_token=first["lease_token"],
        )
        self._expire(record["id"])
        second = self.store.pop_next_command("browser-1")
        self.assertEqual(second["attempt_number"], 2)

    def test_same_result_is_idempotent_and_different_result_conflicts(self) -> None:
        record = self._enqueue({"type": "extract_text", "selector": "body"})
        envelope = self.store.pop_next_command("browser-1")
        common = {
            "command_id": record["id"],
            "client_id": "browser-1",
            "delivery_id": envelope["delivery_id"],
            "lease_token": envelope["lease_token"],
            "ok": True,
            "status": "completed",
            "data": {"text": "same"},
            "error": None,
            "logs": ["done"],
            "finished_at": "2026-07-24T10:00:00+00:00",
        }
        self.store.submit_result(result_id="r1", **common)
        repeated = self.store.submit_result(result_id="r2", **common)
        self.assertEqual(
            repeated["deliveries"]["browser-1"]["duplicate_result_count"],
            1,
        )
        with self.assertRaises(ResultConflictError):
            self.store.submit_result(
                result_id="r3",
                **{**common, "data": {"text": "different"}},
            )

    def test_idempotency_key_reuses_only_identical_command(self) -> None:
        first = self._enqueue(
            {"type": "extract_text", "selector": "body"},
            idempotency_key="read-home",
        )
        second = self._enqueue(
            {"type": "extract_text", "selector": "body"},
            idempotency_key="read-home",
        )
        self.assertEqual(first["id"], second["id"])
        self.assertTrue(second["idempotency_reused"])
        with self.assertRaises(IdempotencyConflictError):
            self._enqueue(
                {"type": "extract_text", "selector": "main"},
                idempotency_key="read-home",
            )

    def test_sqlite_backup_and_journal_are_available(self) -> None:
        self._enqueue({"type": "extract_text", "selector": "body"})
        backup = self.store.backup()
        self.assertTrue(backup.exists())
        self.assertEqual(backup.suffix, ".sqlite3")
        events = self.store.journal_tail(20)
        self.assertTrue(any(item["event_type"] == "command_enqueued" for item in events))


if __name__ == "__main__":
    unittest.main()
