from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


def _load_module():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "scripts" / "telegram_invite_manager.py"
    spec = importlib.util.spec_from_file_location("telegram_invite_manager", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TelegramInviteManagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = _load_module()

    def test_normalize_username(self) -> None:
        self.assertEqual(self.mod.normalize_username("Alice_123"), "@alice_123")
        self.assertEqual(self.mod.normalize_username("@Bob_123"), "@bob_123")
        self.assertIsNone(self.mod.normalize_username("bad name"))
        self.assertIsNone(self.mod.normalize_username("abc"))

    def _call_silent(self, func, namespace) -> int:
        with contextlib.redirect_stdout(io.StringIO()):
            return func(namespace)

    def test_prepare_users_imports_consent_and_skips_duplicates(self) -> None:
        users, stats = self.mod.prepare_users(
            [
                {"username": "@Alice_123", "consent": "yes", "display_name": "Alice"},
                {"username": "bob_12345", "consent": "no", "display_name": "Bob"},
                {"username": "@Alice_123", "consent": "yes"},
                {"username": "not valid username", "consent": "yes"},
            ],
            "2026-04-23T12:00:00Z",
        )
        self.assertEqual(stats["rows_total"], 4)
        self.assertEqual(stats["imported"], 2)
        self.assertEqual(stats["duplicates"], 1)
        self.assertEqual(stats["invalid_username"], 1)
        self.assertEqual(users[0]["status"], "new")
        self.assertEqual(users[1]["status"], "skipped")
        self.assertFalse(users[1]["consent"])
        self.assertEqual(users[1]["history"][0]["reason"], "init_no_consent")

    def test_init_creates_state_file_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            input_path = tmp / "users.csv"
            input_path.write_text(
                "username,display_name,note,consent,source\n"
                "@alice_123,Alice,test,yes,manual\n"
                "@bob_12345,Bob,test,no,manual\n",
                encoding="utf-8",
            )
            job_dir = tmp / "job"
            rc = self._call_silent(
                self.mod.command_init,
                Namespace(
                    chat_url="https://web.telegram.org/k/#-2465948544",
                    input=str(input_path),
                    output_root=str(tmp / "out"),
                    job_dir=str(job_dir),
                ),
            )
            self.assertEqual(rc, 0)
            state = json.loads((job_dir / "invite_state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["chat_slug"], "-2465948544")
            self.assertEqual(len(state["users"]), 2)
            self.assertEqual(state["users"][0]["username"], "@alice_123")

    def test_select_candidates_only_consented_default_new(self) -> None:
        payload = {
            "users": [
                {"username": "@auser1", "consent": True, "status": "new", "attempts": 0},
                {"username": "@buser2", "consent": True, "status": "checked", "attempts": 0},
                {"username": "@cuser3", "consent": False, "status": "new", "attempts": 0},
            ]
        }
        selected = self.mod.select_candidates(payload, 5)
        self.assertEqual([row["username"] for row in selected], ["@auser1"])
        selected_checked = self.mod.select_candidates(payload, 5, ["checked"])
        self.assertEqual([row["username"] for row in selected_checked], ["@buser2"])

    def test_run_dry_run_writes_artifacts_without_state_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            job_dir = tmp / "job"
            payload = {
                "version": 1,
                "chat_url": "https://web.telegram.org/k/#-2465948544",
                "chat_slug": "-2465948544",
                "created_at": "2026-04-23T12:00:00Z",
                "updated_at": "2026-04-23T12:00:00Z",
                "source_file": str(tmp / "users.csv"),
                "users": [
                    {"username": "@alice_123", "consent": True, "status": "new", "attempts": 0, "last_attempt_at": "", "history": [], "display_name": "", "note": "", "source": "manual"},
                    {"username": "@bob_12345", "consent": True, "status": "new", "attempts": 0, "last_attempt_at": "", "history": [], "display_name": "", "note": "", "source": "manual"},
                ],
            }
            self.mod.save_state(job_dir, payload)
            rc = self._call_silent(
                self.mod.command_run,
                Namespace(
                    job_dir=str(job_dir),
                    limit=1,
                    statuses=["new"],
                    to_status="checked",
                    dry_run=True,
                ),
            )
            self.assertEqual(rc, 0)
            state = self.mod.load_state(job_dir)
            self.assertEqual(state["users"][0]["status"], "new")
            runs = sorted((job_dir / "runs").glob("*/invite_run.json"))
            self.assertEqual(len(runs), 1)
            run_payload = json.loads(runs[0].read_text(encoding="utf-8"))
            self.assertTrue(run_payload["dry_run"])
            self.assertEqual(run_payload["processed"], 1)
            self.assertEqual(run_payload["updated"], 0)

    def test_run_updates_state_when_not_dry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            job_dir = tmp / "job"
            payload = {
                "version": 1,
                "chat_url": "https://web.telegram.org/k/#-2465948544",
                "chat_slug": "-2465948544",
                "created_at": "2026-04-23T12:00:00Z",
                "updated_at": "2026-04-23T12:00:00Z",
                "source_file": str(tmp / "users.csv"),
                "users": [
                    {"username": "@alice_123", "consent": True, "status": "new", "attempts": 0, "last_attempt_at": "", "history": [], "display_name": "", "note": "", "source": "manual"},
                ],
            }
            self.mod.save_state(job_dir, payload)
            rc = self._call_silent(
                self.mod.command_run,
                Namespace(
                    job_dir=str(job_dir),
                    limit=1,
                    statuses=["new"],
                    to_status="checked",
                    dry_run=False,
                ),
            )
            self.assertEqual(rc, 0)
            state = self.mod.load_state(job_dir)
            self.assertEqual(state["users"][0]["status"], "checked")
            self.assertEqual(state["users"][0]["attempts"], 1)
            self.assertEqual(state["users"][0]["history"][0]["to_status"], "checked")

    def test_mark_updates_specific_user(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            job_dir = tmp / "job"
            payload = {
                "version": 1,
                "chat_url": "https://web.telegram.org/k/#-2465948544",
                "chat_slug": "-2465948544",
                "created_at": "2026-04-23T12:00:00Z",
                "updated_at": "2026-04-23T12:00:00Z",
                "source_file": str(tmp / "users.csv"),
                "users": [
                    {"username": "@alice_123", "consent": True, "status": "new", "attempts": 0, "last_attempt_at": "", "history": [], "display_name": "", "note": "", "source": "manual"},
                ],
            }
            self.mod.save_state(job_dir, payload)
            rc = self._call_silent(
                self.mod.command_mark,
                Namespace(
                    job_dir=str(job_dir),
                    username=["alice_123"],
                    status="sent",
                    reason="manual_send",
                ),
            )
            self.assertEqual(rc, 0)
            state = self.mod.load_state(job_dir)
            self.assertEqual(state["users"][0]["status"], "sent")
            self.assertEqual(state["users"][0]["history"][0]["reason"], "manual_send")

    def test_add_user_adds_one_consented_user(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            job_dir = tmp / "job"
            payload = {
                "version": 1,
                "chat_url": "https://web.telegram.org/k/#-2465948544",
                "chat_slug": "-2465948544",
                "created_at": "2026-04-23T12:00:00Z",
                "updated_at": "2026-04-23T12:00:00Z",
                "source_file": str(tmp / "users.csv"),
                "users": [],
            }
            self.mod.save_state(job_dir, payload)
            rc = self._call_silent(
                self.mod.command_add_user,
                Namespace(
                    job_dir=str(job_dir),
                    chat_url=None,
                    username="Alice_123",
                    display_name="Alice",
                    note="one user test",
                    source="manual",
                    consent="yes",
                    update=False,
                ),
            )
            self.assertEqual(rc, 0)
            state = self.mod.load_state(job_dir)
            self.assertEqual(len(state["users"]), 1)
            self.assertEqual(state["users"][0]["username"], "@alice_123")
            self.assertEqual(state["users"][0]["status"], "new")
            self.assertEqual(state["users"][0]["history"][0]["reason"], "manual_add_user")

    def test_add_user_requires_explicit_consent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            job_dir = tmp / "job"
            payload = {
                "version": 1,
                "chat_url": "https://web.telegram.org/k/#-2465948544",
                "chat_slug": "-2465948544",
                "created_at": "2026-04-23T12:00:00Z",
                "updated_at": "2026-04-23T12:00:00Z",
                "source_file": str(tmp / "users.csv"),
                "users": [],
            }
            self.mod.save_state(job_dir, payload)
            with self.assertRaises(ValueError):
                self.mod.command_add_user(
                    Namespace(
                        job_dir=str(job_dir),
                        chat_url=None,
                        username="Alice_123",
                        display_name="Alice",
                        note="one user test",
                        source="manual",
                        consent="no",
                        update=False,
                    )
                )

    def test_add_user_existing_without_update_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            job_dir = tmp / "job"
            payload = {
                "version": 1,
                "chat_url": "https://web.telegram.org/k/#-2465948544",
                "chat_slug": "-2465948544",
                "created_at": "2026-04-23T12:00:00Z",
                "updated_at": "2026-04-23T12:00:00Z",
                "source_file": str(tmp / "users.csv"),
                "users": [
                    {"username": "@alice_123", "consent": True, "status": "new", "attempts": 0, "last_attempt_at": "", "history": [], "display_name": "Alice", "note": "", "source": "manual"},
                ],
            }
            self.mod.save_state(job_dir, payload)
            rc = self._call_silent(
                self.mod.command_add_user,
                Namespace(
                    job_dir=str(job_dir),
                    chat_url=None,
                    username="@alice_123",
                    display_name="Alice Changed",
                    note="changed",
                    source="manual",
                    consent="yes",
                    update=False,
                ),
            )
            self.assertEqual(rc, 0)
            state = self.mod.load_state(job_dir)
            self.assertEqual(len(state["users"]), 1)
            self.assertEqual(state["users"][0]["display_name"], "Alice")

    def test_add_user_can_create_one_user_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            job_dir = Path(tmpdir) / "job"
            rc = self._call_silent(
                self.mod.command_add_user,
                Namespace(
                    job_dir=str(job_dir),
                    chat_url="https://web.telegram.org/k/#-2465948544",
                    username="Alice_123",
                    display_name="Alice",
                    note="created from add-user",
                    source="manual",
                    consent="yes",
                    update=False,
                ),
            )
            self.assertEqual(rc, 0)
            state = self.mod.load_state(job_dir)
            self.assertEqual(state["chat_slug"], "-2465948544")
            self.assertEqual(state["source_file"], "manual:add-user")
            self.assertEqual(state["users"][0]["username"], "@alice_123")
            self.assertEqual(state["import_stats"]["imported"], 1)


if __name__ == "__main__":
    unittest.main()
