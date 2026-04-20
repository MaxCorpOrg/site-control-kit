from __future__ import annotations

import importlib.util
import tempfile
import unittest
from http.client import RemoteDisconnected
from pathlib import Path
from unittest import mock


def _load_export_module():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "scripts" / "export_telegram_members_non_pii.py"
    spec = importlib.util.spec_from_file_location("telegram_export_script", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TelegramExportParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = _load_export_module()

    def test_parse_chat_members_colored_name_block(self) -> None:
        html = (
            '<div class="colored-name name floating-part" data-peer-id="123">'
            '<span class="peer-title with-icons bubble-name-first">'
            '<span class="peer-title-inner">Alice</span>'
            "</span>"
            '<span class="bubble-name-rank">admin</span>'
            "</div></div>"
        )
        members = self.mod._parse_chat_members(html)
        self.assertEqual(len(members), 1)
        self.assertEqual(members[0]["peer_id"], "123")
        self.assertEqual(members[0]["name"], "Alice")
        self.assertEqual(members[0]["role"], "admin")

    def test_parse_chat_members_peer_title_block(self) -> None:
        html = (
            '<span class="peer-title bubble-name-first with-icons" data-peer-id="456">'
            '<span class="peer-title-inner">Bob</span>'
            "</span>"
        )
        members = self.mod._parse_chat_members(html)
        self.assertEqual(len(members), 1)
        self.assertEqual(members[0]["peer_id"], "456")
        self.assertEqual(members[0]["name"], "Bob")

    def test_parse_chat_members_skips_negative_peer_id(self) -> None:
        html = '<span class="peer-title bubble-name-first" data-peer-id="-1288116010">Chat</span>'
        members = self.mod._parse_chat_members(html)
        self.assertEqual(members, [])

    def test_parse_chat_members_includes_avatar_only_group(self) -> None:
        html = (
            '<div class="avatar avatar-like bubbles-group-avatar user-avatar" data-peer-id="789">AB</div>'
            '<div data-mid="1" data-timestamp="1776505277" class="bubble hide-name is-in"></div>'
        )
        members = self.mod._parse_chat_members(html)
        self.assertEqual(len(members), 1)
        self.assertEqual(members[0]["peer_id"], "789")
        self.assertEqual(members[0]["name"], "AB")

    def test_parse_chat_members_merges_avatar_only_with_named_sender(self) -> None:
        html = (
            '<div class="avatar avatar-like bubbles-group-avatar user-avatar" data-peer-id="789">AB</div>'
            '<div data-mid="1" data-timestamp="1776505277" class="bubble hide-name is-in"></div>'
            '<div class="colored-name name floating-part" data-peer-id="789">'
            '<span class="peer-title with-icons bubble-name-first">'
            '<span class="peer-title-inner">Alice Brown</span>'
            "</span>"
            "</div>"
        )
        members = self.mod._parse_chat_members(html)
        self.assertEqual(len(members), 1)
        self.assertEqual(members[0]["peer_id"], "789")
        self.assertEqual(members[0]["name"], "Alice Brown")

    def test_assign_username_if_unique_rejects_duplicate_owner(self) -> None:
        members = {
            "111": {"peer_id": "111", "name": "Alice", "username": "@alice_111", "status": "—", "role": "—"},
            "222": {"peer_id": "222", "name": "Bob", "username": "—", "status": "—", "role": "—"},
        }
        username_to_peer = self.mod._seed_username_to_peer(list(members.values()))

        assigned, existing_peer, reason = self.mod._assign_username_if_unique(
            members_by_peer=members,
            username_to_peer=username_to_peer,
            peer_id="222",
            username="@alice_111",
        )

        self.assertFalse(assigned)
        self.assertEqual(existing_peer, "111")
        self.assertEqual(reason, "runtime_duplicate")
        self.assertEqual(members["222"]["username"], "—")

    def test_assign_username_if_unique_sets_username_for_new_peer(self) -> None:
        members = {
            "111": {"peer_id": "111", "name": "Alice", "username": "—", "status": "—", "role": "—"},
        }
        username_to_peer = self.mod._seed_username_to_peer(list(members.values()))

        assigned, existing_peer, reason = self.mod._assign_username_if_unique(
            members_by_peer=members,
            username_to_peer=username_to_peer,
            peer_id="111",
            username="@Alice_111",
        )

        self.assertTrue(assigned)
        self.assertIsNone(existing_peer)
        self.assertIsNone(reason)
        self.assertEqual(members["111"]["username"], "@Alice_111")

    def test_assign_username_if_unique_rejects_historical_peer_username_change(self) -> None:
        members = {
            "111": {"peer_id": "111", "name": "Alice", "username": "—", "status": "—", "role": "—"},
        }

        assigned, existing_peer, reason = self.mod._assign_username_if_unique(
            members_by_peer=members,
            username_to_peer={},
            peer_id="111",
            username="@alice_new",
            historical_peer_to_username={"111": "@alice_old"},
        )

        self.assertFalse(assigned)
        self.assertEqual(existing_peer, "@alice_old")
        self.assertEqual(reason, "historical_peer_username")
        self.assertEqual(members["111"]["username"], "—")

    def test_assign_username_if_unique_rejects_historical_username_owner_change(self) -> None:
        members = {
            "222": {"peer_id": "222", "name": "Bob", "username": "—", "status": "—", "role": "—"},
        }

        assigned, existing_peer, reason = self.mod._assign_username_if_unique(
            members_by_peer=members,
            username_to_peer={},
            peer_id="222",
            username="@alice_old",
            historical_username_to_peer={"@alice_old": "111"},
        )

        self.assertFalse(assigned)
        self.assertEqual(existing_peer, "111")
        self.assertEqual(reason, "historical_username_owner")
        self.assertEqual(members["222"]["username"], "—")

    def test_backfill_usernames_from_history_restores_known_peer_username(self) -> None:
        members = [
            {"peer_id": "111", "name": "Alice", "username": "—", "status": "—", "role": "—"},
            {"peer_id": "222", "name": "Bob", "username": "—", "status": "—", "role": "—"},
        ]

        updated, conflicts = self.mod._backfill_usernames_from_history(
            members=members,
            historical_username_to_peer={"@alice_old": "111"},
            historical_peer_to_username={"111": "@alice_old"},
        )

        self.assertEqual(updated, 1)
        self.assertEqual(conflicts, 0)
        self.assertEqual(members[0]["username"], "@alice_old")
        self.assertEqual(members[1]["username"], "—")

    def test_backfill_usernames_from_history_skips_runtime_duplicate(self) -> None:
        members = [
            {"peer_id": "111", "name": "Alice", "username": "@alice_old", "status": "—", "role": "—"},
            {"peer_id": "222", "name": "Bob", "username": "—", "status": "—", "role": "—"},
        ]

        updated, conflicts = self.mod._backfill_usernames_from_history(
            members=members,
            historical_username_to_peer={"@alice_old": "222"},
            historical_peer_to_username={"222": "@alice_old"},
        )

        self.assertEqual(updated, 0)
        self.assertEqual(conflicts, 1)
        self.assertEqual(members[1]["username"], "—")

    def test_sanitize_member_usernames_for_output_clears_duplicate_username(self) -> None:
        members = [
            {"peer_id": "111", "name": "Alice", "username": "@alice_old", "status": "—", "role": "—"},
            {"peer_id": "222", "name": "Bob", "username": "@alice_old", "status": "—", "role": "—"},
        ]

        restored, cleared = self.mod._sanitize_member_usernames_for_output(
            members=members,
            historical_username_to_peer={"@alice_old": "111"},
            historical_peer_to_username={"111": "@alice_old"},
        )

        self.assertEqual(restored, 0)
        self.assertEqual(cleared, 1)
        self.assertEqual(members[0]["username"], "@alice_old")
        self.assertEqual(members[1]["username"], "—")

    def test_sanitize_member_usernames_for_output_restores_historical_peer_username(self) -> None:
        members = [
            {"peer_id": "111", "name": "Alice", "username": "@wrong_name", "status": "—", "role": "—"},
        ]

        restored, cleared = self.mod._sanitize_member_usernames_for_output(
            members=members,
            historical_username_to_peer={"@alice_old": "111"},
            historical_peer_to_username={"111": "@alice_old"},
        )

        self.assertEqual(restored, 1)
        self.assertEqual(cleared, 0)
        self.assertEqual(members[0]["username"], "@alice_old")

    def test_url_matches_expected_dialog_by_exact_fragment(self) -> None:
        matched = self.mod._url_matches_expected_dialog(
            "https://web.telegram.org/k/#-2465948544",
            "https://web.telegram.org/a/#-2465948544",
        )
        self.assertTrue(matched)

    def test_url_matches_expected_dialog_rejects_other_fragment(self) -> None:
        matched = self.mod._url_matches_expected_dialog(
            "https://web.telegram.org/k/#-2465948544",
            "https://web.telegram.org/k/#@NoogasV",
        )
        self.assertFalse(matched)

    def test_parse_wmctrl_windows_reads_geometry_and_title(self) -> None:
        windows = self.mod._parse_wmctrl_windows(
            "0x02800264  2 328  128  2396 1536 GIGA Telegram Web - Google Chrome\n"
        )
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0]["window_id"], "0x02800264")
        self.assertEqual(windows[0]["x"], 328)
        self.assertEqual(windows[0]["width"], 2396)
        self.assertEqual(windows[0]["title"], "Telegram Web - Google Chrome")

    def test_pick_telegram_x11_window_prefers_chrome_title(self) -> None:
        picked = self.mod._pick_telegram_x11_window(
            [
                {"window_id": "0x1", "title": "Telegram Web - Chromium"},
                {"window_id": "0x2", "title": "Telegram Web - Google Chrome"},
            ]
        )
        self.assertIsNotNone(picked)
        self.assertEqual(picked["window_id"], "0x2")

    def test_http_json_wraps_remote_disconnect_as_runtime_error(self) -> None:
        original_urlopen = self.mod.urlopen

        def _boom(*args, **kwargs):
            raise RemoteDisconnected("Remote end closed connection without response")

        self.mod.urlopen = _boom
        try:
            with self.assertRaises(RuntimeError) as ctx:
                self.mod._http_json("http://127.0.0.1:8765", "token", "GET", "/api/clients")
        finally:
            self.mod.urlopen = original_urlopen

        self.assertIn("Network error: Remote end closed connection without response", str(ctx.exception))

    def test_find_tab_prefers_active_exact_dialog_match(self) -> None:
        client_id, tab_id = self.mod._find_tab(
            clients=[
                {
                    "client_id": "client-1",
                    "tabs": [
                        {
                            "id": 101,
                            "active": False,
                            "url": "https://web.telegram.org/k/#-2465948544",
                        },
                        {
                            "id": 202,
                            "active": True,
                            "url": "https://web.telegram.org/k/#-2465948544",
                        },
                    ],
                }
            ],
            client_id=None,
            tab_id=None,
            url_pattern="https://web.telegram.org/k/#-2465948544",
        )

        self.assertEqual(client_id, "client-1")
        self.assertEqual(tab_id, 202)

    def test_get_chat_anchor_peer_id_reads_visible_avatar_attribute(self) -> None:
        with mock.patch.object(
            self.mod,
            "_send_command_result",
            return_value={"ok": True, "data": {"value": "1621138520"}},
        ):
            peer_id = self.mod._get_chat_anchor_peer_id("server", "token", "client", 7)

        self.assertEqual(peer_id, "1621138520")

    def test_open_chat_peer_context_menu_prefers_anchor_route_when_peer_matches(self) -> None:
        calls: list[str] = []

        def _fake_send_command_result(**kwargs):
            selector = str(kwargs.get("command", {}).get("selector") or "")
            calls.append(selector)
            return {"ok": True}

        with mock.patch.object(self.mod, "_get_chat_anchor_peer_id", return_value="123"):
            with mock.patch.object(self.mod, "_send_command_result", side_effect=_fake_send_command_result):
                opened, route = self.mod._open_chat_peer_context_menu("server", "token", "client", 7, "123")

        self.assertTrue(opened)
        self.assertEqual(route, "anchor")
        self.assertEqual(calls[0], self.mod.CHAT_ANCHOR_CONTEXT_SELECTORS[0])

    def test_open_chat_peer_context_menu_falls_back_to_peer_route_when_anchor_differs(self) -> None:
        calls: list[str] = []

        def _fake_send_command_result(**kwargs):
            selector = str(kwargs.get("command", {}).get("selector") or "")
            calls.append(selector)
            if selector == '.bubbles .bubbles-group-avatar.user-avatar[data-peer-id="456"] .avatar-photo':
                return {"ok": True}
            return {"ok": False}

        with mock.patch.object(self.mod, "_get_chat_anchor_peer_id", return_value="123"):
            with mock.patch.object(self.mod, "_send_command_result", side_effect=_fake_send_command_result):
                opened, route = self.mod._open_chat_peer_context_menu("server", "token", "client", 7, "456")

        self.assertTrue(opened)
        self.assertEqual(route, "peer")
        self.assertEqual(calls[0], '.bubbles .bubble[data-peer-id="456"] .bubble-content-wrapper')

    def test_normalize_username_from_mention_markup_reads_hash_link(self) -> None:
        username = self.mod._normalize_username_from_mention_markup(
            '<a class="mention" href="https://web.telegram.org/k/#@Alice_111">@Alice_111</a>'
        )

        self.assertEqual(username, "@Alice_111")

    def test_read_username_from_composer_falls_back_to_html_markup(self) -> None:
        responses = iter(
            [
                {"ok": True, "data": {"text": ""}},
                {"ok": True, "data": {"html": '<a data-plain-text="@Alice_111">@Alice</a>'}},
            ]
        )

        with mock.patch.object(self.mod, "_send_command_result", side_effect=lambda **kwargs: next(responses)):
            username = self.mod._read_username_from_composer("server", "token", "client", 7)

        self.assertEqual(username, "@Alice_111")

    def test_try_username_via_mention_action_uses_body_fallback_click(self) -> None:
        click_roots: list[str] = []
        command_types: list[str] = []

        def _fake_send_command_result(**kwargs):
            command = kwargs.get("command") or {}
            command_type = command.get("type")
            command_types.append(str(command_type))
            if command_type == "wait_selector":
                return {"ok": True}
            if command_type == "click_menu_text":
                return {"ok": False}
            if command_type == "click_text":
                click_roots.append(str(command.get("root_selector") or ""))
                if str(command.get("root_selector") or "") == "body":
                    return {"ok": True}
                return {"ok": False}
            return {"ok": True}

        with mock.patch.object(self.mod, "_clear_composer_text") as clear_mock:
            with mock.patch.object(self.mod, "_open_chat_peer_context_menu", return_value=(True, "peer")):
                with mock.patch.object(self.mod, "_read_username_from_composer", return_value="@Alice_111"):
                    with mock.patch.object(self.mod, "_send_command_result", side_effect=_fake_send_command_result):
                        username = self.mod._try_username_via_mention_action(
                            "server", "token", "client", 7, "111"
                        )

        self.assertEqual(username, "@Alice_111")
        self.assertIn("click_menu_text", command_types)
        self.assertIn("body", click_roots)
        self.assertGreaterEqual(clear_mock.call_count, 2)

    def test_try_username_via_mention_action_prefers_click_menu_text(self) -> None:
        command_types: list[str] = []

        def _fake_send_command_result(**kwargs):
            command = kwargs.get("command") or {}
            command_type = str(command.get("type") or "")
            command_types.append(command_type)
            if command_type == "wait_selector":
                return {"ok": True}
            if command_type == "click_menu_text":
                return {"ok": True}
            if command_type == "click_text":
                return {"ok": False}
            return {"ok": True}

        with mock.patch.object(self.mod, "_clear_composer_text"):
            with mock.patch.object(self.mod, "_open_chat_peer_context_menu", return_value=(True, "peer")):
                with mock.patch.object(self.mod, "_read_username_from_composer", return_value="@Alice_111"):
                    with mock.patch.object(self.mod, "_send_command_result", side_effect=_fake_send_command_result):
                        username = self.mod._try_username_via_mention_action(
                            "server", "token", "client", 7, "111"
                        )

        self.assertEqual(username, "@Alice_111")
        self.assertIn("click_menu_text", command_types)
        self.assertNotIn("click_text", command_types)

    def test_try_username_via_mention_action_skips_click_menu_text_when_runtime_lacks_it(self) -> None:
        command_types: list[str] = []

        def _fake_send_command_result(**kwargs):
            command = kwargs.get("command") or {}
            command_type = str(command.get("type") or "")
            command_types.append(command_type)
            if command_type == "wait_selector":
                return {"ok": True}
            if command_type == "click_text":
                return {"ok": True}
            return {"ok": True}

        with mock.patch.object(self.mod, "_clear_composer_text"):
            with mock.patch.object(self.mod, "_open_chat_peer_context_menu", return_value=(True, "peer")):
                with mock.patch.object(self.mod, "_read_username_from_composer", return_value="@Alice_111"):
                    with mock.patch.object(self.mod, "_send_command_result", side_effect=_fake_send_command_result):
                        username = self.mod._try_username_via_mention_action(
                            "server",
                            "token",
                            "client",
                            7,
                            "111",
                            supports_click_menu_text=False,
                        )

        self.assertEqual(username, "@Alice_111")
        self.assertNotIn("click_menu_text", command_types)
        self.assertIn("click_text", command_types)

    def test_extract_bridge_capabilities_reads_background_and_content_lists(self) -> None:
        background, content = self.mod._extract_bridge_capabilities(
            {
                "meta": {
                    "capabilities": {
                        "background_commands": ["open_tab", "activate_tab"],
                        "content_commands": ["click", "click_menu_text"],
                    }
                }
            }
        )

        self.assertEqual(background, {"open_tab", "activate_tab"})
        self.assertEqual(content, {"click", "click_menu_text"})

    def test_extract_bridge_capabilities_returns_empty_sets_for_missing_meta(self) -> None:
        background, content = self.mod._extract_bridge_capabilities({"client_id": "client-a"})

        self.assertEqual(background, set())
        self.assertEqual(content, set())

    def test_should_run_chat_deep_step_runs_immediately_without_discovery_target(self) -> None:
        should_run = self.mod._should_run_chat_deep_step(
            step=2,
            members_count=8,
            min_members_target=0,
            mode="mention",
            chat_target_peer_id="",
            chat_target_name="",
        )

        self.assertTrue(should_run)

    def test_should_run_chat_deep_step_defers_url_mode_during_discovery(self) -> None:
        should_run = self.mod._should_run_chat_deep_step(
            step=3,
            members_count=12,
            min_members_target=50,
            mode="url",
            chat_target_peer_id="",
            chat_target_name="",
        )

        self.assertFalse(should_run)

    def test_should_run_chat_deep_step_allows_periodic_mention_during_discovery(self) -> None:
        interval = int(self.mod.CHAT_DISCOVERY_MENTION_DEEP_INTERVAL)

        should_skip = self.mod._should_run_chat_deep_step(
            step=1,
            members_count=12,
            min_members_target=50,
            mode="mention",
            chat_target_peer_id="",
            chat_target_name="",
        )
        should_run = self.mod._should_run_chat_deep_step(
            step=interval,
            members_count=12,
            min_members_target=50,
            mode="mention",
            chat_target_peer_id="",
            chat_target_name="",
        )

        self.assertFalse(should_skip)
        self.assertTrue(should_run)

    def test_should_run_chat_deep_step_does_not_defer_targeted_probe(self) -> None:
        should_run = self.mod._should_run_chat_deep_step(
            step=4,
            members_count=12,
            min_members_target=50,
            mode="mention",
            chat_target_peer_id="123",
            chat_target_name="",
        )

        self.assertTrue(should_run)

    def test_should_run_chat_deep_step_defers_known_view_during_discovery(self) -> None:
        should_run = self.mod._should_run_chat_deep_step(
            step=0,
            members_count=12,
            min_members_target=50,
            mode="mention",
            chat_target_peer_id="",
            chat_target_name="",
            known_view_signature=True,
        )

        self.assertFalse(should_run)

    def test_should_run_chat_deep_step_runs_mention_when_discovery_stalled(self) -> None:
        should_run = self.mod._should_run_chat_deep_step(
            step=1,
            members_count=12,
            min_members_target=50,
            mode="mention",
            chat_target_peer_id="",
            chat_target_name="",
            known_view_signature=True,
            discovery_stall_steps=int(self.mod.CHAT_DISCOVERY_MENTION_STALL_TRIGGER),
        )

        self.assertTrue(should_run)

    def test_extract_chat_view_signature_uses_top_mid_peer_and_timestamp(self) -> None:
        html = (
            '<div class="avatar avatar-like bubbles-group-avatar user-avatar" data-peer-id="789">AB</div>'
            '<div data-mid="101" data-timestamp="1776505277" class="bubble hide-name is-in"></div>'
            '<div class="avatar avatar-like bubbles-group-avatar user-avatar" data-peer-id="456">CD</div>'
            '<div data-mid="102" data-timestamp="1776505278" class="bubble hide-name is-in"></div>'
        )

        signature = self.mod._extract_chat_view_signature(html)

        self.assertEqual(signature, "mid=101,102|peer=789,456|ts=1776505277,1776505278")

    def test_extract_chat_view_signature_returns_empty_for_empty_html(self) -> None:
        self.assertEqual(self.mod._extract_chat_view_signature(""), "")

    def test_discovery_state_roundtrip_preserves_signatures_and_peers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "discovery_state.json"
            self.mod._save_discovery_state(
                path,
                {
                    "seen_view_signatures": ["mid=1|peer=2|ts=3"],
                    "seen_peer_ids": ["111", "222"],
                },
            )

            payload = self.mod._load_discovery_state(path)

        self.assertEqual(payload["seen_view_signatures"], ["mid=1|peer=2|ts=3"])
        self.assertEqual(payload["seen_peer_ids"], ["111", "222"])

    def test_build_export_stats_payload_counts_usernames_and_keeps_chat_stats(self) -> None:
        payload = self.mod._build_export_stats_payload(
            status="completed",
            group_url="https://web.telegram.org/k/#-2465948544",
            source="chat",
            source_label="chat",
            out_path=Path("/tmp/out.md"),
            members=[
                {"peer_id": "1", "name": "Alice", "username": "@alice_1", "status": "—", "role": "—"},
                {"peer_id": "2", "name": "Bob", "username": "—", "status": "—", "role": "—"},
            ],
            chat_stats={"unique_members": 2, "scroll_steps_done": 7, "jump_scrolls_done": 1},
            info_stats={"unique_members": 0},
            deep_usernames=True,
            max_members=50,
            deep_attempted_total=3,
            deep_updated_total=1,
            history_backfilled_total=2,
            output_usernames_restored_total=1,
            output_usernames_cleared_total=2,
        )

        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["members_total"], 2)
        self.assertEqual(payload["members_with_username"], 1)
        self.assertEqual(payload["members_without_username"], 1)
        self.assertEqual(payload["deep_attempted_total"], 3)
        self.assertEqual(payload["deep_updated_total"], 1)
        self.assertEqual(payload["history_backfilled_total"], 2)
        self.assertEqual(payload["output_usernames_restored_total"], 1)
        self.assertEqual(payload["output_usernames_cleared_total"], 2)
        self.assertEqual(payload["chat_stats"]["scroll_steps_done"], 7)
        self.assertEqual(payload["chat_stats"]["jump_scrolls_done"], 1)

    def test_load_discovery_state_returns_empty_payload_for_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = self.mod._load_discovery_state(Path(tmpdir) / "missing.json")

        self.assertEqual(payload["seen_view_signatures"], [])
        self.assertEqual(payload["seen_peer_ids"], [])

    def test_scroll_chat_up_requires_actual_wheel_movement(self) -> None:
        responses = iter(
            [
                {
                    "ok": True,
                    "data": {
                        "beforeTop": 0,
                        "afterTop": 0,
                        "scrollHeight": 3479,
                        "clientHeight": 513,
                        "moved": False,
                    },
                },
                {
                    "ok": True,
                    "data": {
                        "beforeTop": 0,
                        "afterTop": 0,
                        "moved": False,
                    },
                },
                {
                    "ok": True,
                    "data": {
                        "beforeTop": 0,
                        "afterTop": 0,
                        "scrollHeight": 3479,
                    },
                },
                {"ok": False},
                {"ok": False},
                {"ok": False},
                {"ok": False},
            ]
        )

        with mock.patch.object(self.mod, "_send_command_result", side_effect=lambda **kwargs: next(responses)):
            with mock.patch.object(self.mod, "_x11_wheel_scroll_telegram", return_value=False):
                with mock.patch.object(self.mod.time, "sleep", return_value=None):
                    moved = self.mod._scroll_chat_up("server", "token", "client", 1, 5)

        self.assertFalse(moved)

    def test_scroll_chat_up_accepts_wheel_height_growth(self) -> None:
        responses = iter(
            [
                {
                    "ok": True,
                    "data": {
                        "beforeTop": 0,
                        "afterTop": 0,
                        "scrollHeight": 3479,
                        "clientHeight": 513,
                        "moved": False,
                    },
                },
                {
                    "ok": True,
                    "data": {
                        "beforeTop": 0,
                        "afterTop": 0,
                        "moved": False,
                    },
                },
                {
                    "ok": True,
                    "data": {
                        "beforeTop": 0,
                        "afterTop": 0,
                        "scrollHeight": 4200,
                    },
                },
            ]
        )

        with mock.patch.object(self.mod, "_send_command_result", side_effect=lambda **kwargs: next(responses)):
            with mock.patch.object(self.mod, "_x11_wheel_scroll_telegram", return_value=False):
                with mock.patch.object(self.mod.time, "sleep", return_value=None):
                    moved = self.mod._scroll_chat_up("server", "token", "client", 1, 5)

        self.assertTrue(moved)

    def test_scroll_chat_up_jump_accepts_direct_position_change(self) -> None:
        responses = iter(
            [
                {
                    "ok": True,
                    "data": {
                        "beforeTop": 0,
                        "scrollHeight": 3479,
                    },
                },
                {
                    "ok": True,
                    "data": {
                        "beforeTop": 0,
                        "afterTop": 800,
                        "moved": True,
                    },
                },
            ]
        )

        with mock.patch.object(self.mod, "_send_command_result", side_effect=lambda **kwargs: next(responses)):
            with mock.patch.object(self.mod.time, "sleep", return_value=None):
                moved = self.mod._scroll_chat_up_jump("server", "token", "client", 1, 5)

        self.assertTrue(moved)

    def test_scroll_chat_up_jump_accepts_probe_height_change(self) -> None:
        responses = iter(
            [
                {
                    "ok": True,
                    "data": {
                        "beforeTop": 0,
                        "scrollHeight": 3479,
                    },
                },
                {
                    "ok": True,
                    "data": {
                        "beforeTop": 0,
                        "afterTop": 0,
                        "moved": False,
                    },
                },
                {
                    "ok": True,
                    "data": {
                        "beforeTop": 0,
                        "afterTop": 0,
                        "moved": False,
                    },
                },
                {
                    "ok": True,
                    "data": {
                        "beforeTop": 0,
                        "scrollHeight": 4200,
                    },
                },
            ]
        )

        with mock.patch.object(self.mod, "_send_command_result", side_effect=lambda **kwargs: next(responses)):
            with mock.patch.object(self.mod.time, "sleep", return_value=None):
                moved = self.mod._scroll_chat_up_jump("server", "token", "client", 1, 5)

        self.assertTrue(moved)

    def test_enrich_usernames_deep_chat_mention_mode_falls_back_to_url_probe(self) -> None:
        members = [
            {"peer_id": "111", "name": "Alice", "username": "—", "status": "—", "role": "—"},
        ]
        all_members = [dict(item) for item in members]

        with mock.patch.object(self.mod.time, "time", side_effect=[0.0, 0.0, 0.0, 0.1, 0.2]):
            with mock.patch.object(self.mod.time, "sleep", return_value=None):
                with mock.patch.object(self.mod, "_return_to_group_dialog_reliable", return_value=True):
                    with mock.patch.object(
                        self.mod,
                        "_get_tab_url",
                        return_value="https://web.telegram.org/k/#-2465948544",
                    ):
                        with mock.patch.object(self.mod, "_try_username_via_mention_action", return_value="—"):
                            with mock.patch.object(self.mod, "_open_peer_dialog_from_group_chat", return_value=True):
                                with mock.patch.object(
                                    self.mod,
                                    "_poll_username_from_tab_url",
                                    return_value=("@alice_111", "https://web.telegram.org/k/#@alice_111"),
                                ):
                                    attempted, updated, opened, opened_peer_ids = self.mod._enrich_usernames_deep_chat(
                                        server="server",
                                        token="token",
                                        client_id="client",
                                        tab_id=7,
                                        timeout_sec=5,
                                        members=members,
                                        all_members=all_members,
                                        group_url="https://web.telegram.org/k/#-2465948544",
                                        max_runtime_sec=3.0,
                                        mode="mention",
                                    )

        self.assertEqual(attempted, 1)
        self.assertEqual(updated, 1)
        self.assertEqual(opened, 1)
        self.assertEqual(opened_peer_ids, ["111"])
        self.assertEqual(members[0]["username"], "@alice_111")

    def test_enrich_usernames_deep_chat_mention_mode_skips_url_probe_after_mention_success(self) -> None:
        members = [
            {"peer_id": "111", "name": "Alice", "username": "—", "status": "—", "role": "—"},
        ]
        all_members = [dict(item) for item in members]

        with mock.patch.object(self.mod.time, "time", side_effect=[0.0, 0.0, 0.0, 0.1]):
            with mock.patch.object(self.mod.time, "sleep", return_value=None):
                with mock.patch.object(self.mod, "_return_to_group_dialog_reliable", return_value=True):
                    with mock.patch.object(
                        self.mod,
                        "_get_tab_url",
                        return_value="https://web.telegram.org/k/#-2465948544",
                    ):
                        with mock.patch.object(self.mod, "_try_username_via_mention_action", return_value="@alice_111"):
                            with mock.patch.object(self.mod, "_open_peer_dialog_from_group_chat") as open_peer_mock:
                                attempted, updated, opened, opened_peer_ids = self.mod._enrich_usernames_deep_chat(
                                    server="server",
                                    token="token",
                                    client_id="client",
                                    tab_id=7,
                                    timeout_sec=5,
                                    members=members,
                                    all_members=all_members,
                                    group_url="https://web.telegram.org/k/#-2465948544",
                                    max_runtime_sec=3.0,
                                    mode="mention",
                                )

        self.assertEqual(attempted, 1)
        self.assertEqual(updated, 1)
        self.assertEqual(opened, 0)
        self.assertEqual(opened_peer_ids, ["111"])
        self.assertEqual(members[0]["username"], "@alice_111")
        open_peer_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
