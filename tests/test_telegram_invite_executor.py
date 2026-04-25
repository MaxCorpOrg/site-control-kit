from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock


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

    def test_parse_add_members_candidates(self) -> None:
        html_payload = """
        <div class="tabs-tab sidebar-slider-item add-members-container active">
          <a class="row chatlist-chat row-clickable" data-peer-id="1404471788">
            <span class="peer-title" dir="auto">Камаз</span>
          </a>
          <a class="row chatlist-chat row-clickable" data-peer-id="1281184986">
            <span class="peer-title" dir="auto">25 GPoint</span>
          </a>
        </div>
        """
        candidates = self.executor._parse_add_members_candidates(html_payload)
        self.assertEqual(
            candidates,
            [
                {"peer_id": "1404471788", "title": "Камаз"},
                {"peer_id": "1281184986", "title": "25 GPoint"},
            ],
        )

    def test_add_contact_dry_run_builds_safe_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            job_dir = Path(tmpdir) / "job"
            self._seed_state(job_dir)
            rc, payload = self._call_json(
                self.executor.command_add_contact,
                Namespace(
                    job_dir=str(job_dir),
                    username="@alice_123",
                    search_query=None,
                    client_id=None,
                    tab_id=123,
                    url_pattern=None,
                    execution_id="20260425T080000Z",
                    search_wait=0,
                    confirm_wait=0,
                    result_wait=0,
                    skip_open=True,
                    allow_first_result=False,
                    confirm_add=False,
                    record_result=False,
                    active=None,
                    dry_run=True,
                ),
            )
            self.assertEqual(rc, 0)
            self.assertEqual(payload["outcome"], "dry_run")
            self.assertEqual(payload["username"], "@alice_123")
            self.assertFalse(any(step.get("label") == "confirm_add" for step in payload["steps"]))
            self.assertTrue((Path(payload["run_dir"]) / "execution_record.json").exists())

    def test_add_contact_confirm_records_requested_when_no_visible_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            job_dir = Path(tmpdir) / "job"
            self._seed_state(job_dir)
            html_payload = """
            <div class="tabs-tab sidebar-slider-item add-members-container active">
              <a class="row chatlist-chat row-clickable" data-peer-id="1404471788">
                <span class="peer-title" dir="auto">Alice</span>
              </a>
            </div>
            """

            def fake_run(_repo_root, command):
                action = command[-2] if command[-1] == "body" else command[-1]
                if action == "html":
                    payload = {"ok": True, "data": {"html": html_payload}}
                elif action == "text":
                    payload = {"ok": True, "data": {"text": "2 440 members"}}
                else:
                    payload = {"ok": True, "data": {"clicked": True}}
                return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload), stderr="")

            with mock.patch.object(self.executor, "_run_browser_command", side_effect=fake_run):
                rc, payload = self._call_json(
                    self.executor.command_add_contact,
                    Namespace(
                        job_dir=str(job_dir),
                        username="@alice_123",
                        search_query=None,
                        client_id=None,
                        tab_id=123,
                        url_pattern=None,
                        execution_id="20260425T080100Z",
                        search_wait=0,
                        confirm_wait=0,
                        result_wait=0,
                        skip_open=True,
                        allow_first_result=False,
                        confirm_add=True,
                        record_result=True,
                        active=None,
                        dry_run=False,
                    ),
                )
            self.assertEqual(rc, 0)
            self.assertEqual(payload["outcome"], "confirmed_unverified")
            self.assertEqual(payload["selected_candidate"]["peer_id"], "1404471788")
            state = self.manager.load_state(job_dir)
            self.assertEqual(state["users"][0]["status"], "requested")

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
