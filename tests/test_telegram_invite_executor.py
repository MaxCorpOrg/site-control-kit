from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


def _load_module(module_name: str, relative_path: str):
    root = Path(__file__).resolve().parents[1]
    module_path = root / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TelegramInviteExecutorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manager = _load_module("telegram_invite_manager", "scripts/telegram_invite_manager.py")
        cls.executor = _load_module("telegram_invite_executor", "scripts/telegram_invite_executor.py")

    def _call_json(self, func, namespace) -> tuple[int, dict]:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            rc = func(namespace)
        return rc, json.loads(buffer.getvalue())

    def _seed_state(self, job_dir: Path) -> None:
        payload = {
            "version": 1,
            "chat_url": "https://web.telegram.org/k/#-2465948544",
            "chat_slug": "-2465948544",
            "created_at": "2026-04-23T12:00:00Z",
            "updated_at": "2026-04-23T12:00:00Z",
            "source_file": str(job_dir / "users.csv"),
            "users": [
                {
                    "username": "@alice_123",
                    "display_name": "Alice",
                    "consent": True,
                    "status": "checked",
                    "attempts": 0,
                    "last_attempt_at": "",
                    "history": [],
                    "note": "warm lead",
                    "source": "manual",
                },
                {
                    "username": "@bob_12345",
                    "display_name": "Bob",
                    "consent": True,
                    "status": "checked",
                    "attempts": 0,
                    "last_attempt_at": "",
                    "history": [],
                    "note": "",
                    "source": "crm",
                },
                {
                    "username": "@charlie_1",
                    "display_name": "Charlie",
                    "consent": False,
                    "status": "skipped",
                    "attempts": 0,
                    "last_attempt_at": "",
                    "history": [],
                    "note": "",
                    "source": "manual",
                },
            ],
        }
        self.manager.save_state(job_dir, payload)

    def test_configure_persists_execution_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            job_dir = Path(tmpdir) / "job"
            self._seed_state(job_dir)
            rc, payload = self._call_json(
                self.executor.command_configure,
                Namespace(
                    job_dir=str(job_dir),
                    invite_link="https://t.me/+safeLink",
                    message_template="Привет, {display_name}: {invite_link}",
                    note="operator flow",
                    requires_approval=True,
                    client_id="client-123",
                    tab_id=0,
                    url_pattern="web.telegram.org/k/#-2465948544",
                    active=True,
                ),
            )
            self.assertEqual(rc, 0)
            execution = payload["execution"]
            self.assertEqual(execution["invite_link"], "https://t.me/+safeLink")
            self.assertTrue(execution["requires_approval"])
            self.assertEqual(execution["browser_target"]["client_id"], "client-123")

            state = self.manager.load_state(job_dir)
            self.assertEqual(state["execution"]["note"], "operator flow")

    def test_plan_creates_execution_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            job_dir = Path(tmpdir) / "job"
            self._seed_state(job_dir)
            rc, payload = self._call_json(
                self.executor.command_plan,
                Namespace(
                    job_dir=str(job_dir),
                    limit=1,
                    statuses=["checked"],
                    invite_link="https://t.me/+safeLink",
                    message_template="Привет! {invite_link}",
                    note=None,
                    requires_approval=True,
                    reserve=False,
                ),
            )
            self.assertEqual(rc, 0)
            self.assertEqual(payload["selected_users"], 1)
            self.assertEqual(payload["users"][0]["action"], "share_invite_link")
            self.assertIn("message_text", payload["users"][0])
            run_dir = Path(payload["run_dir"])
            self.assertTrue((run_dir / "execution_plan.json").exists())
            state = self.manager.load_state(job_dir)
            self.assertEqual(state["users"][0]["status"], "checked")

    def test_plan_reserve_updates_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            job_dir = Path(tmpdir) / "job"
            self._seed_state(job_dir)
            rc, payload = self._call_json(
                self.executor.command_plan,
                Namespace(
                    job_dir=str(job_dir),
                    limit=1,
                    statuses=["checked"],
                    invite_link="https://t.me/+safeLink",
                    message_template=None,
                    note=None,
                    requires_approval=True,
                    reserve=True,
                ),
            )
            self.assertEqual(rc, 0)
            self.assertEqual(payload["reserved"], 1)
            state = self.manager.load_state(job_dir)
            self.assertEqual(state["users"][0]["status"], "invite_link_created")
            self.assertEqual(state["users"][0]["history"][0]["reason"], "execution_plan_created")

    def test_open_chat_dry_run_builds_browser_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            job_dir = Path(tmpdir) / "job"
            self._seed_state(job_dir)
            self._call_json(
                self.executor.command_configure,
                Namespace(
                    job_dir=str(job_dir),
                    invite_link=None,
                    message_template=None,
                    note=None,
                    requires_approval=None,
                    client_id="client-xyz",
                    tab_id=None,
                    url_pattern="web.telegram.org/k/#-2465948544",
                    active=True,
                )
            )
            rc, payload = self._call_json(
                self.executor.command_open_chat,
                Namespace(
                    job_dir=str(job_dir),
                    client_id=None,
                    tab_id=None,
                    url_pattern=None,
                    active=None,
                    dry_run=True,
                ),
            )
            self.assertEqual(rc, 0)
            self.assertEqual(payload["command"][:4], ["python3", "-m", "webcontrol", "browser"])
            self.assertIn("--client-id", payload["command"])
            self.assertIn("activate", payload["command"])

    def test_record_updates_state_and_writes_execution_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            job_dir = Path(tmpdir) / "job"
            self._seed_state(job_dir)
            rc, payload = self._call_json(
                self.executor.command_record,
                Namespace(
                    job_dir=str(job_dir),
                    username=["alice_123"],
                    status="sent",
                    reason="manual_link_sent",
                    execution_id="20260423T120000Z",
                ),
            )
            self.assertEqual(rc, 0)
            self.assertEqual(payload["updated"][0]["to_status"], "sent")
            self.assertTrue((Path(payload["run_dir"]) / "execution_record.json").exists())
            state = self.manager.load_state(job_dir)
            self.assertEqual(state["users"][0]["status"], "sent")

    def test_report_lists_latest_execution_plans(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            job_dir = Path(tmpdir) / "job"
            self._seed_state(job_dir)
            self._call_json(
                self.executor.command_plan,
                Namespace(
                    job_dir=str(job_dir),
                    limit=1,
                    statuses=["checked"],
                    invite_link="https://t.me/+safeLink",
                    message_template=None,
                    note=None,
                    requires_approval=True,
                    reserve=False,
                )
            )
            rc, payload = self._call_json(
                self.executor.command_report,
                Namespace(
                    job_dir=str(job_dir),
                    limit=2,
                ),
            )
            self.assertEqual(rc, 0)
            self.assertTrue(payload["latest_execution_plans"])
            self.assertEqual(payload["next_execution_batch"][0]["action"], "prepare_invite_link")


if __name__ == "__main__":
    unittest.main()
