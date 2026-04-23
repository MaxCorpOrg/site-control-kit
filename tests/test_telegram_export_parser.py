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

    def test_parse_chat_members_sender_group_current_tg_web(self) -> None:
        html = (
            '<div id="message-group-208227" class="sender-group-container Tk8btfOT">'
            '<div class="UPrRM3Ks opacity-transition fast shown open">'
            '<div class="Avatar jdvqXfYh size-small peer-color-5 interactive" data-peer-id="891274018" style="--_size: 34px;">'
            '<div class="inner"><img class="Avatar__media avatar-media opacity-transition slow shown open" alt="Bulka"></div>'
            "</div></div>"
            '<div id="message-208227" class="Message message-list-item first-in-group allow-selection last-in-group has-reply shown open">'
            '<div class="message-content-wrapper can-select-text"><div class="message-content peer-color-5 text has-subheader">'
            '<div class="content-inner with-subheader">'
            '<div class="message-title" dir="ltr">'
            '<span class="message-title-name-container interactive" dir="ltr">'
            '<span class="forward-title-container"></span>'
            '<span class="message-title-name"><span class="sender-title">Bulka</span></span>'
            "</span>"
            '<div class="title-spacer"></div>'
            '<span class="message-title-meta"><div class="admin-title-badge">Модератор</div></span>'
            "</div>"
            '<div class="message-subheader">'
            '<div class="message-title"><span class="embedded-sender-wrapper"><span class="embedded-sender">Walter</span></span></div>'
            "</div>"
            "</div></div></div></div>"
        )
        members = self.mod._parse_chat_members(html)
        self.assertEqual(len(members), 1)
        self.assertEqual(members[0]["peer_id"], "891274018")
        self.assertEqual(members[0]["name"], "Bulka")
        self.assertEqual(members[0]["role"], "Модератор")

    def test_parse_members_current_right_column_members_list(self) -> None:
        html = (
            '<div id="RightColumn">'
            '<div class="Profile">'
            '<div class="content members-list">'
            '<div class="ListItem chat-item-clickable contact-list-item scroll-item small-icon">'
            '<div class="ListItem-button" role="button" tabindex="0">'
            '<div class="ChatInfo">'
            '<div class="Avatar size-medium peer-color-5" id="peer-story891274018" data-peer-id="891274018">'
            '<div class="inner"><img class="Avatar__media avatar-media" alt="Bulka"></div>'
            "</div>"
            '<div class="info">'
            '<div class="info-name-title">'
            '<div class="title QljEeKI5"><h3 dir="auto" role="button" class="fullName AS54Cntu">Bulka</h3></div>'
            '<div class="hJUqHi4B jNZTCgu2 peer-color-3">Модератор</div>'
            "</div>"
            '<span class="status"><span class="user-status" dir="auto">last seen recently</span></span>'
            "</div>"
            "</div>"
            "</div>"
            "</div>"
            '<div class="SquareTabList no-scrollbar"></div>'
            "</div>"
            "</div>"
        )
        members = self.mod._parse_members(html)
        self.assertEqual(len(members), 1)
        self.assertEqual(members[0]["peer_id"], "891274018")
        self.assertEqual(members[0]["name"], "Bulka")
        self.assertEqual(members[0]["role"], "Модератор")
        self.assertEqual(members[0]["status"], "last seen recently")

    def test_detect_info_members_view_kind_preview(self) -> None:
        html = (
            '<div id="RightColumn">'
            '<div class="Profile custom-scroll">'
            '<div class="profile-info"></div>'
            '<div class="ChatExtra"></div>'
            '<div class="shared-media">'
            '<div class="content members-list"></div>'
            "</div>"
            '<div class="SquareTabList no-scrollbar"></div>'
            '<h3 class="title">Group Info</h3>'
            "</div>"
            "</div>"
        )
        self.assertEqual(self.mod._detect_info_members_view_kind(html), "preview")

    def test_detect_info_members_view_kind_list(self) -> None:
        html = (
            '<div id="RightColumn">'
            '<div class="MembersPanel">'
            '<div class="content members-list"></div>'
            "</div>"
            "</div>"
        )
        self.assertEqual(self.mod._detect_info_members_view_kind(html), "list")

    def test_extract_username_from_current_profile_row(self) -> None:
        html = (
            '<div id="RightColumn">'
            '<div class="Profile">'
            '<div class="ChatExtra">'
            '<div class="ListItem has-ripple narrow multiline">'
            '<div class="ListItem-button" role="button" tabindex="0">'
            '<i class="icon icon-mention ListItem-main-icon" aria-hidden="true"></i>'
            '<div class="multiline-item"><span class="title">@Bychkov_AA</span><span class="subtitle">Username</span></div>'
            "</div>"
            "</div>"
            '<div class="ListItem sfYp5akl allow-selection narrow multiline is-static">'
            '<div class="ListItem-button"><i class="icon icon-info ListItem-main-icon" aria-hidden="true"></i>'
            '<div class="multiline-item"><span class="title word-break allow-selection">'
            'see <a href="https://t.me/nadopingchat">t.me/nadopingchat</a>'
            "</span><span class=\"subtitle\">Bio</span></div>"
            "</div>"
            "</div>"
            "</div>"
            "</div>"
            "</div>"
        )
        username = self.mod._extract_username_from_profile_html(html)
        self.assertEqual(username, "@Bychkov_AA")

    def test_extract_username_from_profile_ignores_bio_tme_links(self) -> None:
        html = (
            '<div id="RightColumn">'
            '<div class="Profile">'
            '<div class="ChatExtra">'
            '<div class="ListItem sfYp5akl allow-selection narrow multiline is-static">'
            '<div class="ListItem-button"><i class="icon icon-info ListItem-main-icon" aria-hidden="true"></i>'
            '<div class="multiline-item"><span class="title word-break allow-selection">'
            'channel <a href="https://t.me/nadopingchat">t.me/nadopingchat</a>'
            "</span><span class=\"subtitle\">Bio</span></div>"
            "</div>"
            "</div>"
            "</div>"
            "</div>"
            "</div>"
        )
        username = self.mod._extract_username_from_profile_html(html)
        self.assertEqual(username, "—")

    def test_chat_peer_anchor_selectors_include_current_tg_web_avatar(self) -> None:
        selectors = self.mod._chat_peer_anchor_selectors("1291639730")
        self.assertIn('.sender-group-container .Avatar.interactive[data-peer-id="1291639730"]', selectors)
        self.assertIn('.sender-group-container .Avatar[data-peer-id="1291639730"]', selectors)
        self.assertIn('.MessageList .Avatar[data-peer-id="1291639730"]', selectors)
        self.assertIn('.bubbles .bubbles-group-avatar.user-avatar[data-peer-id="1291639730"]', selectors)

    def test_build_parser_defaults_to_both(self) -> None:
        parser = self.mod.build_parser()
        args = parser.parse_args([])
        self.assertEqual(args.source, "both")


if __name__ == "__main__":
    unittest.main()
