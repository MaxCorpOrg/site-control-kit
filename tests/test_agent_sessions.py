from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from webcontrol.store import (
    ControlStore,
    SessionConflictError,
    SessionPolicyError,
)


class AgentSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = ControlStore(
            self.root / "state.json",
            artifacts_root=self.root / "artifacts",
        )
        self.store.register_client(
            client_id="c1",
            tabs=[
                {
                    "id": 11,
                    "windowId": 1,
                    "url": "https://example.com/app",
                    "title": "App",
                    "active": True,
                }
            ],
            meta={},
            user_agent="test",
            extension_version="0.2.0",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _session(self, owner: str, **policy):
        return self.store.create_session(
            owner_id=owner,
            client_id="c1",
            ttl_seconds=300,
            policy={
                "allowed_domains": ["example.com"],
                "require_dangerous_confirmation": True,
                "secrets": ["very-private-value"],
                **policy,
            },
        )

    def test_two_agents_cannot_exclusively_lock_one_tab(self) -> None:
        first = self._session("agent-a")
        second = self._session("agent-b")
        self.store.acquire_tab_lock(
            session_id=first["session_id"],
            client_id="c1",
            tab_id=11,
            lock_mode="exclusive",
        )
        with self.assertRaises(SessionConflictError):
            self.store.acquire_tab_lock(
                session_id=second["session_id"],
                client_id="c1",
                tab_id=11,
                lock_mode="exclusive",
            )

    def test_shared_read_lock_rejects_mutating_command(self) -> None:
        session = self._session("reader")
        self.store.acquire_tab_lock(
            session_id=session["session_id"],
            client_id="c1",
            tab_id=11,
            lock_mode="shared_read",
        )
        with self.assertRaises(SessionConflictError):
            self.store.enqueue_command(
                command={"type": "fill", "selector": "#name", "value": "A"},
                target={"client_id": "c1", "tab_id": 11},
                timeout_ms=10_000,
                issued_by="test",
                session_id=session["session_id"],
            )

    def test_dangerous_command_needs_confirmation_and_correct_url(self) -> None:
        session = self._session("writer")
        self.store.acquire_tab_lock(
            session_id=session["session_id"],
            client_id="c1",
            tab_id=11,
        )
        command = {
            "type": "smart_click",
            "locator": {"strategy": "role", "value": "button", "name": "Save"},
            "preconditions": {"expected_url": "https://example.com/app"},
        }
        with self.assertRaises(SessionPolicyError):
            self.store.enqueue_command(
                command=command,
                target={"client_id": "c1", "tab_id": 11},
                timeout_ms=10_000,
                issued_by="test",
                session_id=session["session_id"],
            )
        accepted = self.store.enqueue_command(
            command=command,
            target={"client_id": "c1", "tab_id": 11},
            timeout_ms=10_000,
            issued_by="test",
            session_id=session["session_id"],
            confirmation={"confirmed": True},
        )
        self.assertEqual(accepted["status"], "queued")

    def test_session_timeout_releases_lock_and_stops_commands(self) -> None:
        session = self._session("writer", require_dangerous_confirmation=False)
        self.store.acquire_tab_lock(
            session_id=session["session_id"],
            client_id="c1",
            tab_id=11,
        )
        command = self.store.enqueue_command(
            command={"type": "extract_text", "selector": "body"},
            target={"client_id": "c1", "tab_id": 11},
            timeout_ms=10_000,
            issued_by="test",
            session_id=session["session_id"],
        )
        session["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        current = self.store.get_session(session["session_id"])
        self.assertEqual(current["status"], "expired")
        self.assertEqual(self.store._state["tab_locks"], {})
        self.assertEqual(self.store.get_command(command["id"])["status"], "dead_letter")

    def test_failure_artifacts_mask_secrets(self) -> None:
        session = self._session("writer", require_dangerous_confirmation=False)
        self.store.acquire_tab_lock(
            session_id=session["session_id"],
            client_id="c1",
            tab_id=11,
        )
        command = self.store.enqueue_command(
            command={"type": "extract_text", "selector": "body"},
            target={"client_id": "c1", "tab_id": 11},
            timeout_ms=10_000,
            issued_by="test",
            session_id=session["session_id"],
        )
        envelope = self.store.pop_next_command("c1")
        result = self.store.submit_result(
            command_id=command["id"],
            client_id="c1",
            delivery_id=envelope["delivery_id"],
            lease_token=envelope["lease_token"],
            result_id="failure",
            ok=False,
            status="failed",
            data=None,
            error={"message": "failed with very-private-value", "password": "p@ss"},
            logs=[],
            diagnostics={
                "url": "https://example.com/app",
                "authorization": "Bearer abcdefghijk",
                "card": "4111 1111 1111 1111",
                "semantic_snapshot": {"text": "very-private-value"},
            },
        )
        paths = result["deliveries"]["c1"]["failure_artifacts"]
        diagnostics = Path(paths["diagnostics"]).read_text(encoding="utf-8")
        snapshot = Path(paths["semantic_snapshot"]).read_text(encoding="utf-8")
        self.assertNotIn("very-private-value", diagnostics)
        self.assertNotIn("very-private-value", snapshot)
        self.assertNotIn("4111 1111 1111 1111", diagnostics)
        self.assertNotIn("abcdefghijk", diagnostics)
        parsed = json.loads(diagnostics)
        self.assertEqual(parsed["authorization"], "[СКРЫТО]")


if __name__ == "__main__":
    unittest.main()
