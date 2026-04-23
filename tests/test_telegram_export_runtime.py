from __future__ import annotations

import importlib.util
import itertools
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def _load_export_module():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "scripts" / "export_telegram_members_non_pii.py"
    spec = importlib.util.spec_from_file_location("telegram_export_runtime", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TelegramExportRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = _load_export_module()

    def test_collect_members_from_chat_auto_extends_while_new_people_appear(self) -> None:
        member1 = {"peer_id": "1", "name": "One", "username": "—", "status": "из чата", "role": "—"}
        member2 = {"peer_id": "2", "name": "Two", "username": "—", "status": "из чата", "role": "—"}
        member3 = {"peer_id": "3", "name": "Three", "username": "—", "status": "из чата", "role": "—"}
        parse_sequence = [
            [member1],
            [member1, member2],
            [member2, member3],
            [member3],
            [member3],
        ]

        with (
            patch.object(self.mod, "_send_get_html", side_effect=["h0", "h1", "h2", "h3", "h4"]),
            patch.object(self.mod, "_parse_chat_members", side_effect=parse_sequence),
            patch.object(self.mod, "_scroll_chat_up", return_value=True) as mock_scroll,
        ):
            members, stats = self.mod._collect_members_from_chat(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=1,
                timeout_sec=5,
                scroll_steps=1,
                group_url="https://web.telegram.org/a/#-1002465948544",
                deep_usernames=False,
                chat_deep_limit=0,
                max_runtime_sec=120,
                auto_extra_steps=4,
            )

        self.assertEqual(len(members), 3)
        self.assertEqual(stats["unique_members"], 3)
        self.assertEqual(stats["scroll_steps_done"], 4)
        self.assertEqual(stats["auto_extra_steps"], 3)
        self.assertEqual(mock_scroll.call_count, 4)

    def test_collect_members_from_chat_caps_deep_step_runtime_budget(self) -> None:
        member1 = {"peer_id": "1", "name": "One", "username": "—", "status": "из чата", "role": "—"}
        deep_budgets: list[float] = []

        def fake_deep_chat(**kwargs):
            deep_budgets.append(float(kwargs["max_runtime_sec"]))
            return 1, 0, 0, []

        with (
            patch.object(self.mod, "CHAT_DEEP_STEP_MAX_SEC", 7.0),
            patch.object(self.mod, "_send_get_html", return_value=""),
            patch.object(self.mod, "_parse_chat_members", return_value=[member1]),
            patch.object(self.mod, "_enrich_usernames_deep_chat", side_effect=fake_deep_chat),
            patch.object(self.mod, "_scroll_chat_up", return_value=False),
        ):
            members, stats = self.mod._collect_members_from_chat(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=1,
                timeout_sec=5,
                scroll_steps=0,
                group_url="https://web.telegram.org/a/#-1002465948544",
                deep_usernames=True,
                chat_deep_limit=3,
                max_runtime_sec=120,
                chat_deep_mode="mention",
            )

        self.assertEqual(len(members), 1)
        self.assertEqual(stats["deep_attempted"], 1)
        self.assertEqual(deep_budgets, [7.0])

    def test_archive_export_copy_writes_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            output_path = tmp_path / "result.md"
            output_path.write_text("# sample\n", encoding="utf-8")
            username_rows = self.mod._collect_username_rows(
                [
                    {"peer_id": "1", "name": "One", "username": "@one_user", "status": "из чата", "role": "—"},
                    {"peer_id": "2", "name": "Two", "username": "—", "status": "из чата", "role": "—"},
                ]
            )
            sidecars = self.mod._write_username_sidecars(
                output_path,
                username_rows,
                "https://web.telegram.org/a/#-1002465948544",
                "both(info-preview+chat)",
            )

            archive_paths = self.mod._archive_export_copy(
                archive_dir=tmp_path / "archive",
                output_path=output_path,
                group_url="https://web.telegram.org/a/#-1002465948544",
                source_mode="both(info-preview+chat)",
                members=[{"peer_id": "1", "name": "One", "username": "—", "status": "из чата", "role": "—"}],
                sidecar_paths=sidecars,
            )

            archive_path = archive_paths["markdown"]
            self.assertTrue(archive_path.exists())
            self.assertEqual(archive_path.read_text(encoding="utf-8"), "# sample\n")
            self.assertTrue(archive_paths["usernames_txt"].exists())
            self.assertTrue(archive_paths["usernames_json"].exists())
            index_path = tmp_path / "archive" / "INDEX.md"
            self.assertTrue(index_path.exists())
            index_text = index_path.read_text(encoding="utf-8")
            self.assertIn("https://web.telegram.org/a/#-1002465948544", index_text)
            self.assertIn(str(output_path), index_text)
            self.assertIn(str(archive_path), index_text)
            self.assertIn(str(sidecars["usernames_txt"]), index_text)
            self.assertIn(str(archive_paths["usernames_txt"]), index_text)
            self.assertIn(str(sidecars["usernames_json"]), index_text)
            self.assertIn(str(archive_paths["usernames_json"]), index_text)

    def test_write_username_sidecars_dedupes_usernames_and_writes_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            output_path = tmp_path / "export.md"
            username_rows = self.mod._collect_username_rows(
                [
                    {"peer_id": "1", "name": "Alice", "username": "@alice_1", "status": "из чата", "role": "—"},
                    {"peer_id": "2", "name": "Alice Clone", "username": "@Alice_1", "status": "из чата", "role": "—"},
                    {"peer_id": "3", "name": "Bob", "username": "@bob_2", "status": "из чата", "role": "admin"},
                    {"peer_id": "4", "name": "No Username", "username": "—", "status": "из чата", "role": "—"},
                ]
            )

            sidecars = self.mod._write_username_sidecars(
                output_path,
                username_rows,
                "https://web.telegram.org/a/#-1002465948544",
                "chat",
            )

            txt_body = sidecars["usernames_txt"].read_text(encoding="utf-8")
            self.assertEqual(txt_body, "@alice_1\n@bob_2\n")

            payload = json.loads(sidecars["usernames_json"].read_text(encoding="utf-8"))
            self.assertEqual(payload["group_url"], "https://web.telegram.org/a/#-1002465948544")
            self.assertEqual(payload["source_mode"], "chat")
            self.assertEqual(payload["count"], 2)
            self.assertEqual(payload["usernames"], ["@alice_1", "@bob_2"])
            self.assertEqual(payload["rows"][0]["peer_id"], "1")
            self.assertEqual(payload["rows"][1]["role"], "admin")

    def test_send_command_result_waits_for_late_result_after_terminal_without_payload(self) -> None:
        http_responses = [
            {"ok": True, "command_id": "cmd-1"},
            {
                "command": {
                    "status": "expired",
                    "deliveries": {
                        "client-1": {
                            "status": "expired",
                            "result": None,
                        }
                    },
                }
            },
            {
                "command": {
                    "status": "completed",
                    "deliveries": {
                        "client-1": {
                            "status": "completed",
                            "result": {
                                "ok": True,
                                "status": "completed",
                                "data": {"tabId": 123},
                                "error": None,
                                "logs": [],
                            },
                        }
                    },
                }
            },
        ]

        with (
            patch.object(self.mod, "_http_json_retry", side_effect=http_responses),
            patch.object(self.mod.time, "time", side_effect=itertools.count()),
            patch.object(self.mod.time, "sleep", return_value=None),
        ):
            result = self.mod._send_command_result(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=1,
                timeout_sec=5,
                command={"type": "get_html", "selector": "body"},
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["tabId"], 123)

    def test_send_command_result_returns_informative_failure_when_terminal_without_payload_persists(self) -> None:
        http_responses = [
            {"ok": True, "command_id": "cmd-2"},
            {
                "command": {
                    "status": "expired",
                    "deliveries": {
                        "client-1": {
                            "status": "expired",
                            "result": None,
                        }
                    },
                }
            },
            {
                "command": {
                    "status": "expired",
                    "deliveries": {
                        "client-1": {
                            "status": "expired",
                            "result": None,
                        }
                    },
                }
            },
        ]

        with (
            patch.object(self.mod, "_http_json_retry", side_effect=http_responses),
            patch.object(self.mod.time, "time", side_effect=[0.0, 1.0, 200.0, 201.0]),
            patch.object(self.mod.time, "sleep", return_value=None),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                self.mod._send_command_result(
                    server="http://127.0.0.1:8765",
                    token="token",
                    client_id="client-1",
                    tab_id=1,
                    timeout_sec=5,
                    command={"type": "get_html", "selector": "body"},
                )

        self.assertIn("finished without result", str(ctx.exception))
        self.assertIn("command_status=expired", str(ctx.exception))
        self.assertIn("delivery_status=expired", str(ctx.exception))

    def test_try_username_via_mention_action_bails_out_on_delivery_failure(self) -> None:
        def fake_send_command_result(**kwargs):
            command_type = kwargs["command"]["type"]
            if command_type == "context_click":
                return {"ok": True}
            if command_type == "wait_selector":
                return {"ok": True}
            if command_type == "extract_text":
                return {"ok": False, "error": {"message": "Element not found for selector: .MessageContextMenu_items"}}
            if command_type == "click_menu_text":
                return {
                    "ok": False,
                    "error": {
                        "message": "command click_menu_text finished without result (command_status=expired, delivery_status=expired)"
                    },
                }
            raise AssertionError(f"Unexpected command type: {command_type}")

        with (
            patch.object(self.mod, "_clear_composer_text", return_value=None),
            patch.object(self.mod, "_send_command_result", side_effect=fake_send_command_result) as mock_send,
        ):
            username, outcome = self.mod._try_username_via_mention_action(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=1,
                peer_id="42",
                supports_click_menu_text=True,
            )

        self.assertEqual(username, "—")
        self.assertEqual(outcome, "delivery_failure")
        self.assertEqual(mock_send.call_count, 4)

    def test_try_username_via_mention_action_short_circuits_when_menu_has_no_mention(self) -> None:
        def fake_send_command_result(**kwargs):
            command_type = kwargs["command"]["type"]
            if command_type == "context_click":
                return {"ok": True}
            if command_type == "wait_selector":
                return {"ok": True}
            if command_type == "extract_text":
                return {"ok": True, "data": {"text": "Reply\nCopy Text\nForward\nSelect\nReport"}}
            raise AssertionError(f"Unexpected command type: {command_type}")

        with (
            patch.object(self.mod, "_clear_composer_text", return_value=None),
            patch.object(self.mod, "_send_command_result", side_effect=fake_send_command_result) as mock_send,
        ):
            username, outcome = self.mod._try_username_via_mention_action(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=1,
                peer_id="42",
                supports_click_menu_text=True,
            )

        self.assertEqual(username, "—")
        self.assertEqual(outcome, "menu_missing")
        self.assertEqual(mock_send.call_count, 3)

    def test_enrich_usernames_deep_chat_uses_helper_fallback_in_mention_mode(self) -> None:
        with (
            patch.object(self.mod, "_return_to_group_dialog_reliable", return_value=True),
            patch.object(self.mod, "_get_tab_url", return_value="https://web.telegram.org/a/#-1002465948544"),
            patch.object(self.mod, "_try_username_via_mention_action", return_value=("—", "delivery_failure")),
            patch.object(self.mod, "_read_username_via_helper_tab", return_value=("@alice_42", True)) as mock_helper,
            patch.object(self.mod, "_close_helper_session_best_effort", return_value=None),
        ):
            attempted, updated, opened, opened_peer_ids = self.mod._enrich_usernames_deep_chat(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=1,
                timeout_sec=5,
                members=[{"peer_id": "42", "name": "Alice", "username": "—", "status": "из чата", "role": "—"}],
                group_url="https://web.telegram.org/a/#-1002465948544",
                max_runtime_sec=12,
                mode="mention",
                supports_click_menu_text=True,
            )

        self.assertEqual(attempted, 1)
        self.assertEqual(updated, 1)
        self.assertEqual(opened, 1)
        self.assertEqual(opened_peer_ids, ["42"])
        self.assertEqual(mock_helper.call_count, 1)

    def test_enrich_usernames_deep_chat_switches_remaining_peers_to_helper_only_after_menu_missing(self) -> None:
        members = [
            {"peer_id": "42", "name": "Alice", "username": "—", "status": "из чата", "role": "—"},
            {"peer_id": "43", "name": "Bob", "username": "—", "status": "из чата", "role": "—"},
        ]

        helper_calls: list[dict[str, object]] = []

        def fake_helper(**kwargs):
            helper_calls.append(kwargs)
            peer_id = kwargs["peer_id"]
            if peer_id == "42":
                return "@alice_42", True
            if peer_id == "43":
                return "@bob_43", True
            raise AssertionError(f"Unexpected peer_id: {peer_id}")

        with (
            patch.object(self.mod, "_return_to_group_dialog_reliable", return_value=True) as mock_return,
            patch.object(self.mod, "_get_tab_url", return_value="https://web.telegram.org/a/#-1002465948544"),
            patch.object(
                self.mod,
                "_try_username_via_mention_action",
                side_effect=[("—", "menu_missing")],
            ) as mock_mention,
            patch.object(self.mod, "_read_username_via_helper_tab", side_effect=fake_helper),
            patch.object(self.mod, "_close_helper_session_best_effort", return_value=None),
        ):
            attempted, updated, opened, opened_peer_ids = self.mod._enrich_usernames_deep_chat(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=1,
                timeout_sec=5,
                members=members,
                group_url="https://web.telegram.org/a/#-1002465948544",
                max_runtime_sec=12,
                mode="mention",
                supports_click_menu_text=True,
            )

        self.assertEqual(attempted, 2)
        self.assertEqual(updated, 2)
        self.assertEqual(opened, 2)
        self.assertEqual(opened_peer_ids, ["42", "43"])
        self.assertEqual(mock_mention.call_count, 1)
        self.assertEqual(mock_return.call_count, 1)
        self.assertEqual(helper_calls[0]["restore_base_tab"], False)
        self.assertEqual(helper_calls[1]["restore_base_tab"], False)
        self.assertEqual(members[0]["username"], "@alice_42")
        self.assertEqual(members[1]["username"], "@bob_43")

    def test_client_supports_content_command_detects_click_menu_text(self) -> None:
        clients = [
            {
                "client_id": "client-1",
                "meta": {
                    "capabilities": {
                        "content_commands": ["click_menu_text", "click_text"],
                    }
                },
            }
        ]

        self.assertTrue(self.mod._client_supports_content_command(clients, "client-1", "click_menu_text"))
        self.assertFalse(self.mod._client_supports_content_command(clients, "client-1", "run_script"))
        self.assertFalse(self.mod._client_supports_content_command(clients, "missing", "click_menu_text"))

    def test_sanitize_output_keeps_fresh_live_username_when_history_is_stale(self) -> None:
        members = [
            {
                "peer_id": "555101371",
                "name": "Teimur",
                "username": "@Teimur_92",
                "status": "из чата",
                "role": "—",
            }
        ]

        restored, cleared = self.mod._sanitize_member_usernames_for_output(
            members=members,
            historical_username_to_peer={"@abuzayd06": "555101371"},
            historical_peer_to_username={"555101371": "@abuzayd06"},
        )

        self.assertEqual(restored, 0)
        self.assertEqual(cleared, 0)
        self.assertEqual(members[0]["username"], "@Teimur_92")

    def test_sanitize_output_restores_historical_username_when_live_value_conflicts(self) -> None:
        members = [
            {
                "peer_id": "555101371",
                "name": "Teimur",
                "username": "@shared_name",
                "status": "из чата",
                "role": "—",
            }
        ]

        restored, cleared = self.mod._sanitize_member_usernames_for_output(
            members=members,
            historical_username_to_peer={
                "@shared_name": "999",
                "@abuzayd06": "555101371",
            },
            historical_peer_to_username={"555101371": "@abuzayd06"},
        )

        self.assertEqual(restored, 1)
        self.assertEqual(cleared, 0)
        self.assertEqual(members[0]["username"], "@abuzayd06")


if __name__ == "__main__":
    unittest.main()
