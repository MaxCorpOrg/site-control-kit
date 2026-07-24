from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path

from webcontrol.services import HubServices, StoreCommandService
from webcontrol.store import ControlStore


class StoreCommandServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ControlStore(Path(self.tmp.name) / "state.json")
        self.store.register_client(
            client_id="browser-1",
            tabs=[{"id": 7, "url": "https://example.com", "active": True}],
            meta={},
            user_agent="test",
            extension_version="0.3.0",
        )
        self.service = StoreCommandService(self.store)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _enqueue(self) -> dict:
        return self.service.enqueue_command(
            command={"type": "extract_text", "selector": "body"},
            target={"client_id": "browser-1", "tab_id": 7},
            timeout_ms=10_000,
            issued_by="test",
        )

    def test_long_poll_wakes_immediately_after_enqueue(self) -> None:
        result: list = []
        started = time.monotonic()
        waiter = threading.Thread(
            target=lambda: result.append(self.service.next_command("browser-1", wait_ms=2_000))
        )
        waiter.start()
        time.sleep(0.05)

        command = self._enqueue()
        waiter.join(timeout=1)

        self.assertFalse(waiter.is_alive())
        self.assertEqual(result[0].command["id"], command["id"])
        self.assertEqual(result[0].mode, "long_poll")
        self.assertFalse(result[0].timed_out)
        self.assertLess((time.monotonic() - started) * 1000, 500)

    def test_long_poll_returns_timeout_metadata(self) -> None:
        result = self.service.next_command("browser-1", wait_ms=60)

        self.assertIsNone(result.command)
        self.assertEqual(result.mode, "long_poll")
        self.assertTrue(result.timed_out)
        self.assertGreaterEqual(result.waited_ms, 40)

    def test_immediate_mode_keeps_old_store_behavior(self) -> None:
        result = self.service.next_command("browser-1")

        self.assertIsNone(result.command)
        self.assertEqual(result.mode, "immediate")
        self.assertFalse(result.timed_out)

    def test_hub_services_keep_one_shared_store(self) -> None:
        services = HubServices.from_store(self.store)

        self.assertIs(services.commands.store, self.store)
        self.assertIs(services.clients.store, self.store)
        self.assertIs(services.sessions.store, self.store)
        self.assertIs(services.state.store, self.store)


if __name__ == "__main__":
    unittest.main()
