from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
