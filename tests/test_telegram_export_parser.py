from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


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


if __name__ == "__main__":
    unittest.main()
