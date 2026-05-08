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

    def _dialog_window(self) -> dict:
        return {
            "x": 328,
            "y": 128,
            "width": 2396,
            "height": 1536,
        }

    def _dialog_ancestors(self) -> list[dict]:
        return [
            {
                "role": "dialog",
                "resolved_extents": {
                    "x": 1162,
                    "y": 498,
                    "width": 728,
                    "height": 832,
                },
            }
        ]

    def _profile_add_match(self) -> dict:
        return {
            "name": "ДОБАВИТЬ КОНТАКТ",
            "role": "push button",
            "relative_x_ratio": 0.3364,
            "relative_y_ratio": 0.4688,
            "relative_extents": {
                "x": 806,
                "y": 720,
                "width": 784,
                "height": 76,
            },
            "resolved_extents": {
                "x": 1134,
                "y": 848,
                "width": 784,
                "height": 76,
            },
            "ancestors": [],
        }

    def _dialog_first_name_match(self) -> dict:
        return {
            "name": "Имя",
            "role": "text",
            "relative_x_ratio": 0.3639,
            "relative_y_ratio": 0.4180,
            "relative_extents": {
                "x": 872,
                "y": 642,
                "width": 652,
                "height": 46,
            },
            "resolved_extents": {
                "x": 1200,
                "y": 770,
                "width": 652,
                "height": 46,
            },
            "ancestors": self._dialog_ancestors(),
        }

    def _dialog_done_match(self) -> dict:
        return {
            "name": "Готово",
            "role": "push button",
            "relative_x_ratio": 0.5785,
            "relative_y_ratio": 0.7956,
            "relative_extents": {
                "x": 1386,
                "y": 1222,
                "width": 156,
                "height": 68,
            },
            "resolved_extents": {
                "x": 1714,
                "y": 1350,
                "width": 156,
                "height": 68,
            },
            "ancestors": self._dialog_ancestors(),
        }

    def test_portable_derive_dialog_submit_ratio_uses_dialog_geometry(self) -> None:
        ratio = self.executor._portable_derive_dialog_submit_ratio(
            {"match": self._dialog_first_name_match()},
            self._dialog_window(),
        )
        self.assertEqual(ratio, {"x_ratio": 0.5576, "y_ratio": 0.7611})

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
                    portable_profile_name="AK",
                    portable_profile_dir="/home/max/TelegramPortableAK",
                    account_username="@M_a_g_g_i_e",
                    account_label="Maggie",
                ),
            )
            self.assertEqual(rc, 0)
            execution = payload["execution"]
            self.assertEqual(execution["invite_link"], "https://t.me/+safeLink")
            self.assertTrue(execution["requires_approval"])
            self.assertEqual(execution["browser_target"]["client_id"], "client-123")
            self.assertEqual(execution["portable_actor"]["profile_name"], "AK")
            self.assertEqual(execution["portable_actor"]["profile_dir"], "/home/max/TelegramPortableAK")
            self.assertEqual(execution["portable_actor"]["account_username"], "@M_a_g_g_i_e")

            state = self.manager.load_state(job_dir)
            self.assertEqual(state["execution"]["note"], "operator flow")
            self.assertEqual(state["execution"]["portable_actor"]["account_label"], "Maggie")

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

    def test_open_chat_dry_run_normalizes_public_t_me_chat_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            job_dir = Path(tmpdir) / "job"
            self._seed_state(job_dir)
            state = self.manager.load_state(job_dir)
            state["chat_url"] = "https://t.me/Zhirotop_shop"
            state["chat_slug"] = "Zhirotop_shop"
            self.manager.save_state(job_dir, state)
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
            self.assertEqual(
                payload["command"],
                ["python3", "-m", "webcontrol", "browser", "new-tab", "https://web.telegram.org/k/#@Zhirotop_shop"],
            )

    def test_ensure_portable_reads_configured_actor(self) -> None:
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
                    client_id=None,
                    tab_id=None,
                    url_pattern=None,
                    active=None,
                    portable_profile_name="AK",
                    portable_profile_dir="/home/max/TelegramPortableAK",
                    account_username="@M_a_g_g_i_e",
                    account_label="Maggie",
                ),
            )

            def fake_run(_repo_root, command):
                payload = {
                    "status": "completed",
                    "running": True,
                    "pids": [10413],
                    "windows": [{"window_id": "0x0460002e", "title": "Жиротоп Shop"}],
                }
                return {
                    "command": command,
                    "returncode": 0,
                    "stdout": json.dumps(payload),
                    "stderr": "",
                    "stdout_json": payload,
                }

            with mock.patch.object(self.executor, "_run_portable_json", side_effect=fake_run):
                rc, payload = self._call_json(
                    self.executor.command_ensure_portable,
                    Namespace(
                        job_dir=str(job_dir),
                        portable_profile_name=None,
                        portable_profile_dir=None,
                        account_username=None,
                        account_label=None,
                        launch_if_needed=False,
                    ),
                )
            self.assertEqual(rc, 0)
            self.assertTrue(payload["running"])
            self.assertEqual(payload["account_username"], "@M_a_g_g_i_e")
            self.assertIn("--profile-dir", payload["status_result"]["command"])
            self.assertEqual(payload["pids"], [10413])

    def test_prepare_next_reserves_checked_user_after_portable_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            job_dir = Path(tmpdir) / "job"
            self._seed_state(job_dir)
            self._call_json(
                self.executor.command_configure,
                Namespace(
                    job_dir=str(job_dir),
                    invite_link="https://t.me/+safeLink",
                    message_template="Привет! {invite_link}",
                    note=None,
                    requires_approval=False,
                    client_id=None,
                    tab_id=None,
                    url_pattern=None,
                    active=None,
                    portable_profile_name="AK",
                    portable_profile_dir="/home/max/TelegramPortableAK",
                    account_username="@M_a_g_g_i_e",
                    account_label="@M_a_g_g_i_e",
                ),
            )

            def fake_portable(_repo_root, command):
                payload = {"status": "completed", "running": True, "pids": [10413], "windows": [{"window_id": "0x1"}]}
                return {"command": command, "returncode": 0, "stdout": json.dumps(payload), "stderr": "", "stdout_json": payload}

            with mock.patch.object(self.executor, "_run_portable_json", side_effect=fake_portable):
                rc, payload = self._call_json(
                    self.executor.command_prepare_next,
                    Namespace(
                        job_dir=str(job_dir),
                        username=None,
                        consent="",
                        display_name="",
                        note="",
                        source="prepare-next",
                        statuses=["checked", "new"],
                        execution_id="20260426T090000Z",
                        launch_if_needed=False,
                        reserve=True,
                        dry_run=False,
                    ),
                )
            self.assertEqual(rc, 0)
            self.assertEqual(payload["selected_user"]["username"], "@alice_123")
            self.assertEqual(payload["reserved"], 1)
            self.assertTrue((Path(payload["execution_run_dir"]) / "execution_plan.json").exists())
            state = self.manager.load_state(job_dir)
            self.assertEqual(state["users"][0]["status"], "invite_link_created")

    def test_prepare_next_adds_new_user_checks_and_reserves(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            job_dir = Path(tmpdir) / "job"
            self._seed_state(job_dir)
            state = self.manager.load_state(job_dir)
            for row in state["users"]:
                if row["status"] == "checked":
                    row["status"] = "requested"
            self.manager.save_state(job_dir, state)
            self._call_json(
                self.executor.command_configure,
                Namespace(
                    job_dir=str(job_dir),
                    invite_link="https://t.me/+safeLink",
                    message_template=None,
                    note=None,
                    requires_approval=False,
                    client_id=None,
                    tab_id=None,
                    url_pattern=None,
                    active=None,
                    portable_profile_name="AK",
                    portable_profile_dir="/home/max/TelegramPortableAK",
                    account_username="@M_a_g_g_i_e",
                    account_label="@M_a_g_g_i_e",
                ),
            )

            def fake_portable(_repo_root, command):
                payload = {"status": "completed", "running": True, "pids": [10413], "windows": []}
                return {"command": command, "returncode": 0, "stdout": json.dumps(payload), "stderr": "", "stdout_json": payload}

            with mock.patch.object(self.executor, "_run_portable_json", side_effect=fake_portable):
                rc, payload = self._call_json(
                    self.executor.command_prepare_next,
                    Namespace(
                        job_dir=str(job_dir),
                        username="@fresh_user",
                        consent="yes",
                        display_name="Fresh",
                        note="consented",
                        source="manual",
                        statuses=["checked", "new"],
                        execution_id="20260426T090100Z",
                        launch_if_needed=False,
                        reserve=True,
                        dry_run=False,
                    ),
                )
            self.assertEqual(rc, 0)
            self.assertEqual(payload["selected_user"]["username"], "@fresh_user")
            self.assertTrue((Path(payload["manager_run_dir"]) / "invite_run.json").exists())
            state = self.manager.load_state(job_dir)
            created = next(row for row in state["users"] if row["username"] == "@fresh_user")
            self.assertEqual(created["status"], "invite_link_created")

    def test_desktop_send_link_dry_run_builds_portable_steps_without_state_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            job_dir = Path(tmpdir) / "job"
            self._seed_state(job_dir)
            self._call_json(
                self.executor.command_configure,
                Namespace(
                    job_dir=str(job_dir),
                    invite_link="https://t.me/Zhirotop_shop",
                    message_template=None,
                    note=None,
                    requires_approval=True,
                    client_id=None,
                    tab_id=None,
                    url_pattern=None,
                    active=None,
                    portable_profile_name="AK",
                    portable_profile_dir="/home/max/TelegramPortableAK",
                    account_username="@M_a_g_g_i_e",
                    account_label="@M_a_g_g_i_e",
                ),
            )
            calls: list[list[str]] = []

            def fake_portable(_repo_root, command):
                calls.append(list(command))
                if "status" in command:
                    payload = {
                        "status": "completed",
                        "running": True,
                        "pids": [10413],
                        "windows": [{"window_id": "0x0460002e"}],
                    }
                elif "open-uri" in command:
                    payload = {"status": "dry_run", "command": command}
                else:
                    payload = {"status": "dry_run", "text_length": len("https://t.me/Zhirotop_shop")}
                return {"command": command, "returncode": 0, "stdout": json.dumps(payload), "stderr": "", "stdout_json": payload}

            with mock.patch.object(self.executor, "_run_portable_json", side_effect=fake_portable):
                rc, payload = self._call_json(
                    self.executor.command_desktop_send_link,
                    Namespace(
                        job_dir=str(job_dir),
                        username="@alice_123",
                        invite_link=None,
                        message=None,
                        statuses=["checked"],
                        execution_id="20260426T100000Z",
                        window_id="",
                        open_wait=0,
                        launch_if_needed=False,
                        confirm_send=False,
                        record_result=True,
                        dry_run=True,
                    ),
                )
            self.assertEqual(rc, 0)
            self.assertEqual(payload["outcome"], "prepared")
            self.assertIsNone(payload["record_update"])
            self.assertIn("--dry-run", calls[1])
            self.assertIn("--dry-run", calls[2])
            self.assertNotIn("--press-enter", calls[2])
            self.assertEqual(payload["uri"], "tg://resolve?domain=alice_123")
            self.assertTrue((Path(payload["run_dir"]) / "execution_record.json").exists())
            state = self.manager.load_state(job_dir)
            self.assertEqual(state["users"][0]["status"], "checked")

    def test_desktop_send_link_confirm_records_sent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            job_dir = Path(tmpdir) / "job"
            self._seed_state(job_dir)
            state = self.manager.load_state(job_dir)
            state["users"][0]["status"] = "invite_link_created"
            self.manager.save_state(job_dir, state)
            self._call_json(
                self.executor.command_configure,
                Namespace(
                    job_dir=str(job_dir),
                    invite_link="https://t.me/Zhirotop_shop",
                    message_template=None,
                    note=None,
                    requires_approval=True,
                    client_id=None,
                    tab_id=None,
                    url_pattern=None,
                    active=None,
                    portable_profile_name="AK",
                    portable_profile_dir="/home/max/TelegramPortableAK",
                    account_username="@M_a_g_g_i_e",
                    account_label="@M_a_g_g_i_e",
                ),
            )
            calls: list[list[str]] = []

            def fake_portable(_repo_root, command):
                calls.append(list(command))
                if "status" in command:
                    payload = {
                        "status": "completed",
                        "running": True,
                        "pids": [10413],
                        "windows": [{"window_id": "0x0460002e"}],
                    }
                elif "open-uri" in command:
                    payload = {"status": "opened", "pid": 10499, "command": command}
                else:
                    payload = {"status": "typed", "press_enter": True, "sequence_count": 27}
                return {"command": command, "returncode": 0, "stdout": json.dumps(payload), "stderr": "", "stdout_json": payload}

            with mock.patch.object(self.executor, "_run_portable_json", side_effect=fake_portable), mock.patch.object(
                self.executor.time, "sleep"
            ):
                rc, payload = self._call_json(
                    self.executor.command_desktop_send_link,
                    Namespace(
                        job_dir=str(job_dir),
                        username="@alice_123",
                        invite_link=None,
                        message=None,
                        statuses=["invite_link_created"],
                        execution_id="20260426T100100Z",
                        window_id="0x0460002e",
                        open_wait=0,
                        launch_if_needed=False,
                        confirm_send=True,
                        record_result=True,
                        dry_run=False,
                    ),
                )
            self.assertEqual(rc, 0)
            self.assertEqual(payload["outcome"], "sent")
            self.assertEqual(payload["target_status"], "sent")
            self.assertIn("--press-enter", calls[2])
            self.assertNotIn("--dry-run", calls[2])
            state = self.manager.load_state(job_dir)
            self.assertEqual(state["users"][0]["status"], "sent")

    def test_telegram_public_chat_uri_uses_tg_resolve_for_public_handle(self) -> None:
        self.assertEqual(
            self.executor._telegram_public_chat_uri("https://t.me/Zhirotop_shop"),
            "tg://resolve?domain=Zhirotop_shop",
        )
        self.assertEqual(self.executor._telegram_public_chat_uri("https://t.me/+privateInvite"), "")

    def test_desktop_open_add_members_dry_run_builds_portable_ui_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            job_dir = Path(tmpdir) / "job"
            self._seed_state(job_dir)
            state = self.manager.load_state(job_dir)
            state["chat_url"] = "https://t.me/Zhirotop_shop"
            state["users"][0]["status"] = "checked"
            self.manager.save_state(job_dir, state)
            self._call_json(
                self.executor.command_configure,
                Namespace(
                    job_dir=str(job_dir),
                    invite_link=None,
                    message_template=None,
                    note=None,
                    requires_approval=True,
                    client_id=None,
                    tab_id=None,
                    url_pattern=None,
                    active=None,
                    portable_profile_name="AK",
                    portable_profile_dir="/home/max/TelegramPortableAK",
                    account_username="@M_a_g_g_i_e",
                    account_label="@M_a_g_g_i_e",
                ),
            )
            calls: list[list[str]] = []

            def fake_portable(_repo_root, command):
                calls.append(list(command))
                if "status" in command:
                    payload = {"status": "completed", "running": True, "pids": [10413], "windows": [{"window_id": "0x0460002e"}]}
                elif "log-diagnose" in command:
                    payload = {"status": "completed", "alerts": []}
                elif "accessibility-dump" in command:
                    payload = {
                        "status": "completed",
                        "matches": [
                            {
                                "name": "Search",
                                "role": "text",
                                "visible": True,
                                "extents": {"x": 2200, "y": 320, "width": 240, "height": 36},
                                "resolved_extents": {"x": 2200, "y": 320, "width": 240, "height": 36},
                                "relative_x_ratio": 0.7,
                            }
                        ],
                    }
                else:
                    payload = {"status": "dry_run", "command": command}
                return {"command": command, "returncode": 0, "stdout": json.dumps(payload), "stderr": "", "stdout_json": payload}

            with mock.patch.object(self.executor, "_run_portable_json", side_effect=fake_portable):
                rc, payload = self._call_json(
                    self.executor.command_desktop_open_add_members,
                    Namespace(
                        job_dir=str(job_dir),
                        username="@alice_123",
                        search_query=None,
                        group_uri=None,
                        execution_id="20260426T120000Z",
                        open_wait=0,
                        panel_wait=0,
                        search_wait=0,
                        min_search_x=0,
                        min_search_ratio=0.55,
                        launch_if_needed=False,
                        allow_alerts=False,
                        type_search=True,
                        clear_search=False,
                        press_enter_after_search=False,
                        dry_run=True,
                    ),
                )
            self.assertEqual(rc, 0)
            self.assertEqual(payload["outcome"], "search_typed")
            self.assertEqual(payload["group_uri"], "tg://resolve?domain=Zhirotop_shop")
            self.assertTrue(any("open-uri" in command for command in calls))
            self.assertGreaterEqual(sum(1 for command in calls if "accessibility-click" in command), 2)
            self.assertTrue(any("accessibility-dump" in command for command in calls))
            self.assertTrue(any("accessibility-type-text" in command for command in calls))
            self.assertTrue((Path(payload["run_dir"]) / "execution_record.json").exists())

    def test_desktop_add_contact_profile_dry_run_builds_portable_steps(self) -> None:
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
                    requires_approval=True,
                    client_id=None,
                    tab_id=None,
                    url_pattern=None,
                    active=None,
                    portable_profile_name="AK2",
                    portable_profile_dir="/home/max/TelegramPortable-AK2",
                    account_username="@S_e_r_a_p_h_i_na",
                    account_label="@S_e_r_a_p_h_i_na",
                ),
            )
            calls: list[list[str]] = []

            def fake_portable(_repo_root, command):
                calls.append(list(command))
                if "status" in command:
                    payload = {"status": "completed", "running": True, "pids": [38744], "windows": [{"window_id": "0x04c0002e"}]}
                elif "log-diagnose" in command:
                    payload = {"status": "completed", "alerts": []}
                else:
                    payload = {"status": "dry_run", "command": command}
                return {"command": command, "returncode": 0, "stdout": json.dumps(payload), "stderr": "", "stdout_json": payload}

            with mock.patch.object(self.executor, "_run_portable_json", side_effect=fake_portable):
                rc, payload = self._call_json(
                    self.executor.command_desktop_add_contact_profile,
                    Namespace(
                        job_dir=str(job_dir),
                        username="@alice_123",
                        execution_id="20260427T130000Z",
                        open_wait=0,
                        after_add_wait=0,
                        after_done_wait=0,
                        verify_wait=0,
                        add_click_x_ratio=0.394,
                        add_click_y_ratio=0.397,
                        done_click_x_ratio=0.565,
                        done_click_y_ratio=0.715,
                        done_click_repeat=1,
                        last_name_text="",
                        press_enter_after_last_name=False,
                        launch_if_needed=False,
                        verify_profile_reopen=True,
                        confirm_add=True,
                        dry_run=True,
                    ),
                )

            self.assertEqual(rc, 0)
            self.assertEqual(payload["outcome"], "dry_run")
            self.assertTrue(any("open-uri" in command for command in calls))
            self.assertGreaterEqual(sum(1 for command in calls if "window-click" in command), 2)
            self.assertTrue(any("--dry-run" in command for command in calls if "open-uri" in command))
            self.assertTrue((Path(payload["run_dir"]) / "execution_record.json").exists())

    def test_desktop_add_contact_profile_live_writes_screenshots(self) -> None:
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
                    requires_approval=True,
                    client_id=None,
                    tab_id=None,
                    url_pattern=None,
                    active=None,
                    portable_profile_name="AK2",
                    portable_profile_dir="/home/max/TelegramPortable-AK2",
                    account_username="@S_e_r_a_p_h_i_na",
                    account_label="@S_e_r_a_p_h_i_na",
                ),
            )

            state = {"dialog_open": False, "verified": False}

            def fake_portable(_repo_root, command):
                if "status" in command:
                    payload = {
                        "status": "completed",
                        "running": True,
                        "pids": [38744],
                        "windows": [{"window_id": "0x04c0002e", **self._dialog_window()}],
                    }
                elif "log-diagnose" in command:
                    payload = {"status": "completed", "alerts": []}
                elif "accessibility-dump" in command:
                    query = command[command.index("--query") + 1]
                    if query == "@alice_123":
                        payload = {"status": "completed", "matches": [{"name": "@alice_123", "role": "label"}]}
                    elif query in self.executor.DESKTOP_ADD_CONTACT_BUTTON_TERMS or query in self.executor.DESKTOP_ADD_TO_CONTACTS_CHAT_TERMS:
                        matches = [] if state["verified"] or state["dialog_open"] else [self._profile_add_match()]
                        payload = {"status": "completed", "matches": matches}
                    elif query in self.executor.DESKTOP_FIRST_NAME_TERMS:
                        matches = [self._dialog_first_name_match()] if state["dialog_open"] else []
                        payload = {"status": "completed", "matches": matches}
                    elif query in self.executor.DESKTOP_DONE_BUTTON_TERMS:
                        matches = [self._dialog_done_match()] if state["dialog_open"] else []
                        payload = {"status": "completed", "matches": matches}
                    elif query in self.executor.DESKTOP_CONTACT_DELETE_TERMS:
                        matches = [{"name": "Удалить контакт", "role": "push button"}] if state["verified"] else []
                        payload = {"status": "completed", "matches": matches}
                    else:
                        payload = {"status": "completed", "matches": []}
                elif "window-click" in command:
                    x_ratio = float(command[command.index("--x-ratio") + 1])
                    y_ratio = float(command[command.index("--y-ratio") + 1])
                    if abs(x_ratio - 0.3364) < 0.01 and abs(y_ratio - 0.4688) < 0.02:
                        state["dialog_open"] = True
                    elif state["dialog_open"]:
                        state["dialog_open"] = False
                        state["verified"] = True
                    payload = {"status": "completed"}
                elif "window-screenshot" in command:
                    output_path = command[command.index("--output") + 1]
                    payload = {"status": "completed", "output_path": output_path, "window_id": "0x04c0002e"}
                else:
                    payload = {"status": "completed"}
                return {"command": command, "returncode": 0, "stdout": json.dumps(payload), "stderr": "", "stdout_json": payload}

            with mock.patch.object(self.executor, "_run_portable_json", side_effect=fake_portable):
                rc, payload = self._call_json(
                    self.executor.command_desktop_add_contact_profile,
                    Namespace(
                        job_dir=str(job_dir),
                        username="@alice_123",
                        execution_id="20260427T130500Z",
                        open_wait=0,
                        after_add_wait=0,
                        after_done_wait=0,
                        verify_wait=0,
                        add_click_x_ratio=0.3364,
                        add_click_y_ratio=0.5417,
                        done_click_x_ratio=0.5785,
                        done_click_y_ratio=0.7956,
                        done_click_repeat=1,
                        last_name_text="",
                        press_enter_after_last_name=False,
                        launch_if_needed=False,
                        verify_profile_reopen=True,
                        confirm_add=True,
                        dry_run=False,
                    ),
                )

            self.assertEqual(rc, 0)
            self.assertEqual(payload["outcome"], "contact_added_verified")
            self.assertTrue(payload["verification"]["success_visible"])
            self.assertFalse(payload["verification"]["add_visible"])
            self.assertTrue(any(step.get("label") == "dialog_submit_click" for step in payload["steps"]))
            self.assertTrue(payload["screenshots"]["profile_before"].endswith("desktop_add_contact_profile_before.png"))
            self.assertTrue(payload["screenshots"]["profile_after_actions"].endswith("desktop_add_contact_profile_after_actions.png"))
            self.assertTrue(payload["screenshots"]["profile_verify"].endswith("desktop_add_contact_profile_verify.png"))
            self.assertTrue((Path(payload["run_dir"]) / "execution_record.json").exists())

    def test_desktop_add_contact_profile_treats_existing_contact_as_success(self) -> None:
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
                    requires_approval=True,
                    client_id=None,
                    tab_id=None,
                    url_pattern=None,
                    active=None,
                    portable_profile_name="AK2",
                    portable_profile_dir="/home/max/TelegramPortable-AK2",
                    account_username="@S_e_r_a_p_h_i_na",
                    account_label="@S_e_r_a_p_h_i_na",
                ),
            )

            def fake_portable(_repo_root, command):
                if "status" in command:
                    payload = {
                        "status": "completed",
                        "running": True,
                        "pids": [38744],
                        "windows": [{"window_id": "0x04c0002e", **self._dialog_window()}],
                    }
                elif "log-diagnose" in command:
                    payload = {"status": "completed", "alerts": []}
                elif "accessibility-dump" in command:
                    query = command[command.index("--query") + 1]
                    if query == "@alice_123":
                        payload = {"status": "completed", "matches": [{"name": "@alice_123", "role": "label"}]}
                    elif query in self.executor.DESKTOP_ADD_CONTACT_BUTTON_TERMS or query in self.executor.DESKTOP_ADD_TO_CONTACTS_CHAT_TERMS:
                        payload = {"status": "completed", "matches": []}
                    elif query in self.executor.DESKTOP_CONTACT_DELETE_TERMS:
                        payload = {"status": "completed", "matches": [{"name": "Удалить контакт", "role": "push button"}]}
                    else:
                        payload = {"status": "completed", "matches": []}
                elif "window-screenshot" in command:
                    output_path = command[command.index("--output") + 1]
                    payload = {"status": "completed", "output_path": output_path, "window_id": "0x04c0002e"}
                else:
                    payload = {"status": "completed"}
                return {"command": command, "returncode": 0, "stdout": json.dumps(payload), "stderr": "", "stdout_json": payload}

            with mock.patch.object(self.executor, "_run_portable_json", side_effect=fake_portable):
                rc, payload = self._call_json(
                    self.executor.command_desktop_add_contact_profile,
                    Namespace(
                        job_dir=str(job_dir),
                        username="@alice_123",
                        execution_id="20260503T170100Z",
                        open_wait=0,
                        after_add_wait=0,
                        after_done_wait=0,
                        verify_wait=0,
                        add_click_x_ratio=0.3364,
                        add_click_y_ratio=0.5417,
                        done_click_x_ratio=0.5785,
                        done_click_y_ratio=0.7956,
                        done_click_repeat=1,
                        last_name_text="",
                        press_enter_after_last_name=False,
                        launch_if_needed=False,
                        verify_profile_reopen=True,
                        confirm_add=True,
                        dry_run=False,
                    ),
                )

            self.assertEqual(rc, 0)
            self.assertEqual(payload["status"], "completed")
            self.assertEqual(payload["outcome"], "contact_already_present")
            self.assertTrue(payload["verification"]["success_visible"])
            self.assertFalse(payload["verification"]["add_visible"])
            self.assertFalse(any(step.get("label") == "dialog_submit_click" for step in payload["steps"]))
            self.assertTrue(any(step.get("label") == "precheck_contact_verification" for step in payload["steps"]))

    def test_desktop_add_contact_profile_retries_when_first_verify_still_shows_add_contact(self) -> None:
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
                    requires_approval=True,
                    client_id=None,
                    tab_id=None,
                    url_pattern=None,
                    active=None,
                    portable_profile_name="AK3",
                    portable_profile_dir="/home/max/TelegramPortable-AK3",
                    account_username="",
                    account_label="AK3",
                ),
            )

            state = {"dialog_open": False, "verified": False, "submit_count": 0}

            def fake_portable(_repo_root, command):
                if "status" in command:
                    payload = {
                        "status": "completed",
                        "running": True,
                        "pids": [19374],
                        "windows": [{"window_id": "0x04c0002e", **self._dialog_window()}],
                    }
                elif "log-diagnose" in command:
                    payload = {"status": "completed", "alerts": []}
                elif "accessibility-dump" in command:
                    query = command[command.index("--query") + 1]
                    if query == "@alice_123":
                        payload = {"status": "completed", "matches": [{"name": "@alice_123", "role": "label"}]}
                    elif query in self.executor.DESKTOP_ADD_CONTACT_BUTTON_TERMS or query in self.executor.DESKTOP_ADD_TO_CONTACTS_CHAT_TERMS:
                        matches = [] if state["verified"] or state["dialog_open"] else [self._profile_add_match()]
                        payload = {"status": "completed", "matches": matches}
                    elif query in self.executor.DESKTOP_FIRST_NAME_TERMS:
                        matches = [self._dialog_first_name_match()] if state["dialog_open"] else []
                        payload = {"status": "completed", "matches": matches}
                    elif query in self.executor.DESKTOP_DONE_BUTTON_TERMS:
                        matches = [self._dialog_done_match()] if state["dialog_open"] else []
                        payload = {"status": "completed", "matches": matches}
                    elif query in self.executor.DESKTOP_CONTACT_DELETE_TERMS:
                        matches = [{"name": "Удалить контакт", "role": "push button"}] if state["verified"] else []
                        payload = {"status": "completed", "matches": matches}
                    else:
                        payload = {"status": "completed", "matches": []}
                elif "window-click" in command:
                    x_ratio = float(command[command.index("--x-ratio") + 1])
                    y_ratio = float(command[command.index("--y-ratio") + 1])
                    if abs(x_ratio - 0.3364) < 0.01 and abs(y_ratio - 0.4688) < 0.02:
                        state["dialog_open"] = True
                    elif state["dialog_open"]:
                        state["dialog_open"] = False
                        state["submit_count"] += 1
                        if state["submit_count"] >= 2:
                            state["verified"] = True
                    payload = {"status": "completed"}
                elif "window-screenshot" in command:
                    output_path = command[command.index("--output") + 1]
                    payload = {"status": "completed", "output_path": output_path, "window_id": "0x04c0002e"}
                else:
                    payload = {"status": "completed"}
                return {"command": command, "returncode": 0, "stdout": json.dumps(payload), "stderr": "", "stdout_json": payload}

            with mock.patch.object(self.executor, "_run_portable_json", side_effect=fake_portable), mock.patch.object(
                self.executor.time, "sleep"
            ):
                rc, payload = self._call_json(
                    self.executor.command_desktop_add_contact_profile,
                    Namespace(
                        job_dir=str(job_dir),
                        username="@alice_123",
                        execution_id="20260507T160000Z",
                        open_wait=0,
                        after_add_wait=0,
                        after_done_wait=0,
                        verify_wait=0,
                        add_click_x_ratio=0.3364,
                        add_click_y_ratio=0.5417,
                        done_click_x_ratio=0.5785,
                        done_click_y_ratio=0.7956,
                        done_click_repeat=1,
                        last_name_text="",
                        press_enter_after_last_name=False,
                        launch_if_needed=False,
                        verify_profile_reopen=True,
                        confirm_add=True,
                        dry_run=False,
                    ),
                )

            self.assertEqual(rc, 0)
            self.assertEqual(payload["status"], "completed")
            self.assertEqual(payload["outcome"], "contact_added_verified")
            self.assertEqual(payload["verification"]["stage"], "verify_reopen_retry")
            self.assertTrue(payload["verification"]["success_visible"])
            self.assertFalse(payload["verification"]["add_visible"])
            self.assertTrue(any(step.get("label") == "verify_reopen_retry_requested" for step in payload["steps"]))
            self.assertTrue(any(step.get("label") == "recovery_dialog_submit_click" for step in payload["steps"]))
            self.assertIn("profile_after_retry_actions", payload["screenshots"])
            self.assertIn("profile_verify_retry", payload["screenshots"])

    def test_desktop_add_contact_batch_initializes_job_and_marks_contact_added(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            job_dir = root / "job"
            input_path = root / "users.csv"
            input_path.write_text(
                "username,consent,source\n@alice_123,yes,panel\n",
                encoding="utf-8",
            )

            state = {"dialog_open": False, "verified": False}

            def fake_portable(_repo_root, command):
                if "status" in command:
                    payload = {
                        "status": "completed",
                        "running": True,
                        "pids": [38744],
                        "windows": [{"window_id": "0x04c0002e", **self._dialog_window()}],
                    }
                elif "log-diagnose" in command:
                    payload = {"status": "completed", "alerts": []}
                elif "accessibility-dump" in command:
                    query = command[command.index("--query") + 1]
                    if query == "@alice_123":
                        payload = {"status": "completed", "matches": [{"name": "@alice_123", "role": "label"}]}
                    elif query in self.executor.DESKTOP_ADD_CONTACT_BUTTON_TERMS or query in self.executor.DESKTOP_ADD_TO_CONTACTS_CHAT_TERMS:
                        matches = [] if state["verified"] or state["dialog_open"] else [self._profile_add_match()]
                        payload = {"status": "completed", "matches": matches}
                    elif query in self.executor.DESKTOP_FIRST_NAME_TERMS:
                        matches = [self._dialog_first_name_match()] if state["dialog_open"] else []
                        payload = {"status": "completed", "matches": matches}
                    elif query in self.executor.DESKTOP_DONE_BUTTON_TERMS:
                        matches = [self._dialog_done_match()] if state["dialog_open"] else []
                        payload = {"status": "completed", "matches": matches}
                    elif query in self.executor.DESKTOP_CONTACT_DELETE_TERMS:
                        matches = [{"name": "Удалить контакт", "role": "push button"}] if state["verified"] else []
                        payload = {"status": "completed", "matches": matches}
                    else:
                        payload = {"status": "completed", "matches": []}
                elif "window-click" in command:
                    x_ratio = float(command[command.index("--x-ratio") + 1])
                    y_ratio = float(command[command.index("--y-ratio") + 1])
                    if abs(x_ratio - 0.3364) < 0.01 and abs(y_ratio - 0.4688) < 0.02:
                        state["dialog_open"] = True
                    elif state["dialog_open"]:
                        state["dialog_open"] = False
                        state["verified"] = True
                    payload = {"status": "completed"}
                elif "window-screenshot" in command:
                    output_path = command[command.index("--output") + 1]
                    payload = {"status": "completed", "output_path": output_path, "window_id": "0x04c0002e"}
                else:
                    payload = {"status": "completed"}
                return {"command": command, "returncode": 0, "stdout": json.dumps(payload), "stderr": "", "stdout_json": payload}

            with mock.patch.object(self.executor, "_run_portable_json", side_effect=fake_portable), mock.patch.object(
                self.executor.time, "sleep"
            ), mock.patch.object(
                self.executor.time,
                "monotonic",
                side_effect=[100.0, 100.0, 130.0, 160.0, 220.0, 220.0],
            ):
                rc, payload = self._call_json(
                    self.executor.command_desktop_add_contact_batch,
                    Namespace(
                        job_dir=str(job_dir),
                        input=str(input_path),
                        chat_url="contacts://AK",
                        output_root="",
                        portable_profile_name="AK",
                        portable_profile_dir="/home/max/TelegramPortableAK",
                        account_username="@M_a_g_g_i_e",
                        account_label="@M_a_g_g_i_e",
                        limit=0,
                        statuses=["new", "checked", "failed"],
                        execution_id="20260503T101500Z",
                        open_wait=0,
                        after_add_wait=0,
                        after_done_wait=0,
                        verify_wait=0,
                        add_click_x_ratio=0.3364,
                        add_click_y_ratio=0.5417,
                        done_click_x_ratio=0.5785,
                        done_click_y_ratio=0.7956,
                        done_click_repeat=1,
                        last_name_text="",
                        press_enter_after_last_name=False,
                        launch_if_needed=False,
                        verify_profile_reopen=True,
                        confirm_add=True,
                        dry_run=False,
                    ),
                )

            self.assertEqual(rc, 0)
            self.assertTrue(payload["initialized_from_input"])
            self.assertEqual(payload["selected_users"], 1)
            self.assertEqual(payload["processed_count"], 1)
            self.assertEqual(payload["added_count"], 1)
            self.assertEqual(payload["failed_count"], 0)
            self.assertEqual(payload["elapsed_seconds"], 120)
            self.assertEqual(payload["rate_per_minute"], 0.5)
            self.assertTrue(payload["started_at"])
            self.assertTrue(payload["completed_at"])
            self.assertTrue(payload["progress_json"].endswith("batch_progress.json"))
            self.assertTrue(payload["batch_json"].endswith("batch_contact_add.json"))
            self.assertTrue(payload["artifact_paths"]["progress_json"].endswith("batch_progress.json"))
            progress_payload = json.loads(Path(payload["progress_json"]).read_text(encoding="utf-8"))
            self.assertEqual(progress_payload["status"], "completed")
            self.assertEqual(progress_payload["processed_count"], 1)
            self.assertEqual(progress_payload["remaining_in_run"], 0)
            self.assertTrue((Path(payload["run_dir"]) / "batch_contact_add.json").exists())
            state = self.manager.load_state(job_dir)
            self.assertEqual(state["users"][0]["status"], "contact_added")

    def test_desktop_add_contact_batch_marks_failed_when_verify_still_shows_add_contact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            job_dir = root / "job"
            input_path = root / "users.csv"
            input_path.write_text(
                "username,consent,source\n@alice_123,yes,panel\n",
                encoding="utf-8",
            )

            def fake_portable(_repo_root, command):
                if "status" in command:
                    payload = {
                        "status": "completed",
                        "running": True,
                        "pids": [38744],
                        "windows": [{"window_id": "0x04c0002e", **self._dialog_window()}],
                    }
                elif "log-diagnose" in command:
                    payload = {"status": "completed", "alerts": []}
                elif "accessibility-dump" in command:
                    query = command[command.index("--query") + 1]
                    if query == "@alice_123":
                        payload = {"status": "completed", "matches": [{"name": "@alice_123", "role": "label"}]}
                    elif query in self.executor.DESKTOP_ADD_CONTACT_BUTTON_TERMS or query in self.executor.DESKTOP_ADD_TO_CONTACTS_CHAT_TERMS:
                        payload = {"status": "completed", "matches": [self._profile_add_match()]}
                    elif query in self.executor.DESKTOP_FIRST_NAME_TERMS:
                        payload = {"status": "completed", "matches": [self._dialog_first_name_match()]}
                    elif query in self.executor.DESKTOP_DONE_BUTTON_TERMS:
                        payload = {"status": "completed", "matches": [self._dialog_done_match()]}
                    else:
                        payload = {"status": "completed", "matches": []}
                elif "window-screenshot" in command:
                    output_path = command[command.index("--output") + 1]
                    payload = {"status": "completed", "output_path": output_path, "window_id": "0x04c0002e"}
                else:
                    payload = {"status": "completed"}
                return {"command": command, "returncode": 0, "stdout": json.dumps(payload), "stderr": "", "stdout_json": payload}

            with mock.patch.object(self.executor, "_run_portable_json", side_effect=fake_portable), mock.patch.object(
                self.executor.time, "sleep"
            ):
                rc, payload = self._call_json(
                    self.executor.command_desktop_add_contact_batch,
                    Namespace(
                        job_dir=str(job_dir),
                        input=str(input_path),
                        chat_url="contacts://AK",
                        output_root="",
                        portable_profile_name="AK",
                        portable_profile_dir="/home/max/TelegramPortableAK",
                        account_username="@M_a_g_g_i_e",
                        account_label="@M_a_g_g_i_e",
                        limit=0,
                        statuses=["new", "checked", "failed"],
                        execution_id="20260503T101700Z",
                        open_wait=0,
                        after_add_wait=0,
                        after_done_wait=0,
                        verify_wait=0,
                        add_click_x_ratio=0.3364,
                        add_click_y_ratio=0.5417,
                        done_click_x_ratio=0.5785,
                        done_click_y_ratio=0.7956,
                        done_click_repeat=1,
                        last_name_text="",
                        press_enter_after_last_name=False,
                        launch_if_needed=False,
                        verify_profile_reopen=True,
                        confirm_add=True,
                        dry_run=False,
                    ),
                )

            self.assertEqual(rc, 0)
            self.assertEqual(payload["added_count"], 0)
            self.assertEqual(payload["failed_count"], 1)
            self.assertEqual(payload["results"][0]["outcome"], "contact_not_added")
            state = self.manager.load_state(job_dir)
            self.assertEqual(state["users"][0]["status"], "failed")

    def test_desktop_add_contact_batch_marks_existing_contact_as_contact_added(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            job_dir = root / "job"
            input_path = root / "users.csv"
            input_path.write_text(
                "username,consent,source\n@alice_123,yes,panel\n",
                encoding="utf-8",
            )

            def fake_portable(_repo_root, command):
                if "status" in command:
                    payload = {
                        "status": "completed",
                        "running": True,
                        "pids": [38744],
                        "windows": [{"window_id": "0x04c0002e", **self._dialog_window()}],
                    }
                elif "log-diagnose" in command:
                    payload = {"status": "completed", "alerts": []}
                elif "accessibility-dump" in command:
                    query = command[command.index("--query") + 1]
                    if query == "@alice_123":
                        payload = {"status": "completed", "matches": [{"name": "@alice_123", "role": "label"}]}
                    elif query in self.executor.DESKTOP_ADD_CONTACT_BUTTON_TERMS or query in self.executor.DESKTOP_ADD_TO_CONTACTS_CHAT_TERMS:
                        payload = {"status": "completed", "matches": []}
                    elif query in self.executor.DESKTOP_CONTACT_DELETE_TERMS:
                        payload = {"status": "completed", "matches": [{"name": "Удалить контакт", "role": "push button"}]}
                    else:
                        payload = {"status": "completed", "matches": []}
                elif "window-screenshot" in command:
                    output_path = command[command.index("--output") + 1]
                    payload = {"status": "completed", "output_path": output_path, "window_id": "0x04c0002e"}
                else:
                    payload = {"status": "completed"}
                return {"command": command, "returncode": 0, "stdout": json.dumps(payload), "stderr": "", "stdout_json": payload}

            with mock.patch.object(self.executor, "_run_portable_json", side_effect=fake_portable), mock.patch.object(
                self.executor.time, "sleep"
            ):
                rc, payload = self._call_json(
                    self.executor.command_desktop_add_contact_batch,
                    Namespace(
                        job_dir=str(job_dir),
                        input=str(input_path),
                        chat_url="contacts://AK",
                        output_root="",
                        portable_profile_name="AK",
                        portable_profile_dir="/home/max/TelegramPortableAK",
                        account_username="@M_a_g_g_i_e",
                        account_label="@M_a_g_g_i_e",
                        limit=0,
                        statuses=["new", "checked", "failed"],
                        execution_id="20260503T170300Z",
                        open_wait=0,
                        after_add_wait=0,
                        after_done_wait=0,
                        verify_wait=0,
                        add_click_x_ratio=0.3364,
                        add_click_y_ratio=0.5417,
                        done_click_x_ratio=0.5785,
                        done_click_y_ratio=0.7956,
                        done_click_repeat=1,
                        last_name_text="",
                        press_enter_after_last_name=False,
                        launch_if_needed=False,
                        verify_profile_reopen=True,
                        confirm_add=True,
                        dry_run=False,
                    ),
                )

            self.assertEqual(rc, 0)
            self.assertEqual(payload["added_count"], 1)
            self.assertEqual(payload["already_present_count"], 1)
            self.assertEqual(payload["failed_count"], 0)
            self.assertEqual(payload["results"][0]["outcome"], "contact_already_present")
            state = self.manager.load_state(job_dir)
            self.assertEqual(state["users"][0]["status"], "contact_added")

    def test_extract_member_count(self) -> None:
        count, count_text = self.executor._extract_member_count("Жиротоп Shop\n2 440 members, 153 online")
        self.assertEqual(count, 2440)
        self.assertEqual(count_text, "2 440 members")

    def test_preferred_chat_url_normalizes_public_t_me_handle(self) -> None:
        self.assertEqual(
            self.executor._preferred_chat_url("https://t.me/Zhirotop_shop"),
            "https://web.telegram.org/k/#@Zhirotop_shop",
        )
        self.assertEqual(
            self.executor._preferred_chat_url("https://t.me/+privateInvite"),
            "https://t.me/+privateInvite",
        )

    def test_inspect_chat_dry_run_builds_read_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            job_dir = Path(tmpdir) / "job"
            self._seed_state(job_dir)
            rc, payload = self._call_json(
                self.executor.command_inspect_chat,
                Namespace(
                    job_dir=str(job_dir),
                    client_id=None,
                    tab_id=123,
                    url_pattern=None,
                    skip_open=True,
                    active=None,
                    dry_run=True,
                ),
            )
            self.assertEqual(rc, 0)
            self.assertIsNone(payload["member_count"])
            self.assertEqual(
                [step["label"] for step in payload["steps"]],
                ["page_url", "read_text", "read_html"],
            )

    def test_inspect_chat_parses_visible_member_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            job_dir = Path(tmpdir) / "job"
            self._seed_state(job_dir)

            def fake_run(_repo_root, command):
                action = command[-2] if command[-1] == "body" else command[-1]
                if action == "page-url":
                    payload = {"ok": True, "data": {"url": "https://web.telegram.org/k/#@Zhirotop_shop"}}
                elif action == "text":
                    payload = {"ok": True, "data": {"text": "Жиротоп Shop\n2 440 members, 153 online\nAdd Members"}}
                else:
                    payload = {
                        "ok": True,
                        "data": {
                            "html": """
                            <div class="profile-container can-add-members"></div>
                            <div id="column-right">
                              <div class="search-super-tabs-container tabs-container">
                                <div class="search-super-tab-container search-super-container-members tabs-tab active">
                                  <div class="search-super-content-container search-super-content-members">
                                    <a class="row no-wrap row-with-padding row-clickable hover-effect rp chatlist-chat chatlist-chat-abitbigger" data-peer-id="1410391920">
                                      <span class="peer-title" dir="auto">Oleg S</span>
                                    </a>
                                  </div>
                                </div>
                                <div class="search-super-tab-container search-super-container-media tabs-tab"></div>
                              </div>
                            </div>
                            """,
                        },
                    }
                return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload), stderr="")

            with mock.patch.object(self.executor, "_run_browser_command", side_effect=fake_run):
                rc, payload = self._call_json(
                    self.executor.command_inspect_chat,
                    Namespace(
                        job_dir=str(job_dir),
                        client_id=None,
                        tab_id=123,
                        url_pattern=None,
                        skip_open=True,
                        active=None,
                        dry_run=False,
                    ),
                )
            self.assertEqual(rc, 0)
            self.assertEqual(payload["member_count"], 2440)
            self.assertEqual(payload["member_count_text"], "2 440 members")
            self.assertTrue(payload["add_members_visible"])
            self.assertEqual(payload["visible_member_count"], 1)
            self.assertEqual(payload["visible_member_peers"], [{"peer_id": "1410391920", "title": "Oleg S"}])
            self.assertEqual(payload["page_url"], "https://web.telegram.org/k/#@Zhirotop_shop")

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

    def test_parse_visible_member_peers(self) -> None:
        html_payload = """
        <div id="column-right">
          <div class="search-super-tabs-container tabs-container" data-animation="tabs">
            <div class="search-super-tab-container search-super-container-members tabs-tab active">
              <div class="search-super-content-container search-super-content-members">
                <a class="row no-wrap row-with-padding row-clickable hover-effect rp chatlist-chat chatlist-chat-abitbigger" data-peer-id="1410391920">
                  <span class="peer-title" dir="auto">Oleg S</span>
                </a>
                <a class="row no-wrap row-with-padding row-clickable hover-effect rp chatlist-chat chatlist-chat-abitbigger" data-peer-id="1404471788">
                  <span class="peer-title" dir="auto">Камаз</span>
                </a>
              </div>
            </div>
            <div class="search-super-tab-container search-super-container-media tabs-tab"></div>
          </div>
        </div>
        """
        peers = self.executor._parse_visible_member_peers(html_payload)
        self.assertEqual(
            peers,
            [
                {"peer_id": "1410391920", "title": "Oleg S"},
                {"peer_id": "1404471788", "title": "Камаз"},
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
                    verify_membership=None,
                    verify_wait=0,
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
                    verify_membership=True,
                    verify_wait=0,
                    active=None,
                    dry_run=False,
                ),
            )
            self.assertEqual(rc, 0)
            self.assertEqual(payload["outcome"], "confirmed_unverified")
            self.assertEqual(payload["selected_candidate"]["peer_id"], "1404471788")
            self.assertEqual(payload["verification"]["reason"], "member_count_unchanged")
            state = self.manager.load_state(job_dir)
            self.assertEqual(state["users"][0]["status"], "requested")

    def test_add_contact_confirm_records_joined_when_member_list_shows_selected_peer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            job_dir = Path(tmpdir) / "job"
            self._seed_state(job_dir)
            html_calls = 0
            text_calls = 0

            def fake_run(_repo_root, command):
                nonlocal html_calls, text_calls
                action = command[-2] if command[-1] == "body" else command[-1]
                if action == "html":
                    html_calls += 1
                    if html_calls == 1:
                        payload = {
                            "ok": True,
                            "data": {
                                "html": """
                                <div id="column-right">
                                  <div class="search-super-tabs-container tabs-container">
                                    <div class="search-super-tab-container search-super-container-members tabs-tab active">
                                      <div class="search-super-content-container search-super-content-members">
                                        <a class="row no-wrap row-with-padding row-clickable hover-effect rp chatlist-chat chatlist-chat-abitbigger" data-peer-id="500">
                                          <span class="peer-title" dir="auto">Existing Member</span>
                                        </a>
                                      </div>
                                    </div>
                                    <div class="search-super-tab-container search-super-container-media tabs-tab"></div>
                                  </div>
                                </div>
                                """,
                            },
                        }
                    elif html_calls == 2:
                        payload = {
                            "ok": True,
                            "data": {
                                "html": """
                                <div class="tabs-tab sidebar-slider-item add-members-container active">
                                  <a class="row chatlist-chat row-clickable" data-peer-id="1404471788">
                                    <span class="peer-title" dir="auto">Alice</span>
                                  </a>
                                </div>
                                """,
                            },
                        }
                    else:
                        payload = {
                            "ok": True,
                            "data": {
                                "html": """
                                <div id="column-right">
                                  <div class="search-super-tabs-container tabs-container">
                                    <div class="search-super-tab-container search-super-container-members tabs-tab active">
                                      <div class="search-super-content-container search-super-content-members">
                                        <a class="row no-wrap row-with-padding row-clickable hover-effect rp chatlist-chat chatlist-chat-abitbigger" data-peer-id="500">
                                          <span class="peer-title" dir="auto">Existing Member</span>
                                        </a>
                                        <a class="row no-wrap row-with-padding row-clickable hover-effect rp chatlist-chat chatlist-chat-abitbigger" data-peer-id="1404471788">
                                          <span class="peer-title" dir="auto">Alice</span>
                                        </a>
                                      </div>
                                    </div>
                                    <div class="search-super-tab-container search-super-container-media tabs-tab"></div>
                                  </div>
                                </div>
                                """,
                            },
                        }
                elif action == "text":
                    text_calls += 1
                    payload = {"ok": True, "data": {"text": "2 440 members"}}
                elif action == "page-url":
                    payload = {"ok": True, "data": {"url": "https://web.telegram.org/k/#@Zhirotop_shop"}}
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
                        execution_id="20260425T080150Z",
                        search_wait=0,
                        confirm_wait=0,
                        result_wait=0,
                        skip_open=True,
                        allow_first_result=False,
                        confirm_add=True,
                        record_result=True,
                        verify_membership=True,
                        verify_wait=0,
                        active=None,
                        dry_run=False,
                    ),
                )
            self.assertEqual(rc, 0)
            self.assertEqual(payload["outcome"], "joined_confirmed")
            self.assertEqual(payload["target_status"], "joined")
            self.assertEqual(payload["verification"]["reason"], "member_list_peer_visible")
            self.assertEqual(payload["verification"]["confirmed_signal"], "member_list_visible_peer")
            state = self.manager.load_state(job_dir)
            self.assertEqual(state["users"][0]["status"], "joined")

    def test_add_contact_confirm_records_joined_when_member_count_grows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            job_dir = Path(tmpdir) / "job"
            self._seed_state(job_dir)
            html_calls = 0
            text_calls = 0

            def fake_run(_repo_root, command):
                nonlocal html_calls, text_calls
                action = command[-2] if command[-1] == "body" else command[-1]
                if action == "html":
                    html_calls += 1
                    if html_calls == 1:
                        payload = {"ok": True, "data": {"html": '<div class="profile-container can-add-members"></div>'}}
                    elif html_calls == 2:
                        payload = {
                            "ok": True,
                            "data": {
                                "html": """
                                <div class="tabs-tab sidebar-slider-item add-members-container active">
                                  <a class="row chatlist-chat row-clickable" data-peer-id="1404471788">
                                    <span class="peer-title" dir="auto">Alice</span>
                                  </a>
                                </div>
                                """,
                            },
                        }
                    elif html_calls == 3:
                        payload = {"ok": True, "data": {"html": '<div class="chat-body"></div>'}}
                    else:
                        payload = {"ok": True, "data": {"html": '<div class="profile-container can-add-members"></div>'}}
                elif action == "text":
                    text_calls += 1
                    count_text = "2 440 members" if text_calls == 1 else "2 441 members"
                    payload = {"ok": True, "data": {"text": count_text}}
                elif action == "page-url":
                    payload = {"ok": True, "data": {"url": "https://web.telegram.org/k/#@Zhirotop_shop"}}
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
                        execution_id="20260425T080200Z",
                        search_wait=0,
                        confirm_wait=0,
                        result_wait=0,
                        skip_open=True,
                        allow_first_result=False,
                        confirm_add=True,
                        record_result=True,
                        verify_membership=True,
                        verify_wait=0,
                        active=None,
                        dry_run=False,
                    ),
                )
            self.assertEqual(rc, 0)
            self.assertEqual(payload["outcome"], "joined_confirmed")
            self.assertTrue(payload["verification"]["joined_confirmed"])
            self.assertEqual(payload["verification"]["reason"], "member_count_increased")
            self.assertEqual(payload["verification"]["confirmed_signal"], "member_count_delta")
            state = self.manager.load_state(job_dir)
            self.assertEqual(state["users"][0]["status"], "joined")

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
            self.assertEqual(payload["latest_execution_records"], [])
            self.assertEqual(payload["next_execution_batch"][0]["action"], "prepare_invite_link")


if __name__ == "__main__":
    unittest.main()
