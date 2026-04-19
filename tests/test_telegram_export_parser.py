from __future__ import annotations

import importlib.util
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
        self.assertEqual(calls[0], '.bubbles .bubbles-group-avatar.user-avatar[data-peer-id="456"] .avatar-photo')

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


if __name__ == "__main__":
    unittest.main()
