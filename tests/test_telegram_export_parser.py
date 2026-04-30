from __future__ import annotations

import importlib.util
import json
import tempfile
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

    def test_parse_chat_members_ignores_message_mentions_for_author_username(self) -> None:
        html = (
            '<div id="message-group-208227" class="sender-group-container Tk8btfOT">'
            '<div class="Avatar jdvqXfYh size-small interactive" data-peer-id="1663660771">'
            '<div class="inner"><img class="Avatar__media avatar-media" alt="Ларионов Никита"></div>'
            "</div>"
            '<div id="message-208227" class="Message message-list-item shown open">'
            '<div class="message-content-wrapper can-select-text"><div class="message-content text has-subheader">'
            '<div class="message-title"><span class="message-title-name"><span class="sender-title">Ларионов Никита</span></span></div>'
            '<div class="text-content">привет @super_pavlik</div>'
            "</div></div></div>"
            "</div>"
        )

        members = self.mod._parse_chat_members(html)

        self.assertEqual(len(members), 1)
        self.assertEqual(members[0]["peer_id"], "1663660771")
        self.assertEqual(members[0]["username"], "—")

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

    def test_normalize_username_rejects_numeric_peer_id_shape(self) -> None:
        self.assertEqual(self.mod._normalize_username("Bychkov_AA"), "@Bychkov_AA")
        self.assertEqual(self.mod._normalize_username("@1291639730"), "—")
        self.assertEqual(self.mod._normalize_username("https://t.me/1291639730"), "—")

    def test_normalize_username_from_mention_input_accepts_raw_username(self) -> None:
        self.assertEqual(self.mod._normalize_username_from_mention_input("other_user"), "@other_user")
        self.assertEqual(self.mod._normalize_username_from_mention_input("1291639730"), "—")

    def test_collect_username_rows_excludes_bots_by_default(self) -> None:
        rows = self.mod._collect_username_rows(
            [
                {"peer_id": "1", "name": "Human", "username": "@human_user", "status": "online", "role": "—"},
                {"peer_id": "2", "name": "Alert Bot", "username": "@alerthelperbot", "status": "bot", "role": "—"},
            ]
        )
        self.assertEqual([row["username"] for row in rows], ["@human_user"])

    def test_collect_username_rows_can_include_bots(self) -> None:
        rows = self.mod._collect_username_rows(
            [
                {"peer_id": "1", "name": "Human", "username": "@human_user", "status": "online", "role": "—"},
                {"peer_id": "2", "name": "Alert Bot", "username": "@alerthelperbot", "status": "bot", "role": "—"},
            ],
            include_bots=True,
        )
        self.assertEqual([row["username"] for row in rows], ["@human_user", "@alerthelperbot"])

    def test_chat_peer_anchor_selectors_include_current_tg_web_avatar(self) -> None:
        selectors = self.mod._chat_peer_anchor_selectors("1291639730")
        self.assertIn('.sender-group-container .Avatar.interactive[data-peer-id="1291639730"]', selectors)
        self.assertIn('.sender-group-container .Avatar[data-peer-id="1291639730"]', selectors)
        self.assertIn('.MessageList .Avatar[data-peer-id="1291639730"]', selectors)
        self.assertIn('.bubbles .bubbles-group-avatar.user-avatar[data-peer-id="1291639730"]', selectors)

    def test_member_from_sticky_author_payload_normalizes_username(self) -> None:
        member = self.mod._member_from_sticky_author_payload(
            {
                "found": True,
                "peer_id": "8055002493",
                "name": "Sticky User",
                "role": "Модератор",
                "username": "t.me/sticky_user",
            }
        )

        self.assertEqual(member["peer_id"], "8055002493")
        self.assertEqual(member["name"], "Sticky User")
        self.assertEqual(member["role"], "Модератор")
        self.assertEqual(member["username"], "@sticky_user")

    def test_member_from_sticky_author_payload_rejects_negative_peer_id(self) -> None:
        member = self.mod._member_from_sticky_author_payload(
            {
                "found": True,
                "peer_id": "-1002465948544",
                "name": "Group",
            }
        )

        self.assertIsNone(member)

    def test_load_identity_history_prefers_newer_archive_state_over_stale_explicit_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive_dir = root / "archive"
            state_dir = archive_dir / "state"
            state_dir.mkdir(parents=True, exist_ok=True)
            history_path = root / "chat" / "identity_history.json"
            history_path.parent.mkdir(parents=True, exist_ok=True)

            history_path.write_text(
                json.dumps(
                    {
                        "updated_at": "2026-04-23T17:35:14+00:00",
                        "username_to_peer": {
                            "@super_pavlik": "1663660771",
                            "@legacy_user": "999",
                        },
                        "peer_to_username": {
                            "1663660771": "@super_pavlik",
                            "999": "@legacy_user",
                        },
                    }
                ),
                encoding="utf-8",
            )

            archive_history_path = state_dir / "1002465948544_identity_history.json"
            archive_history_path.write_text(
                json.dumps(
                    {
                        "updated_at": "2026-04-24T12:31:37+00:00",
                        "username_to_peer": {
                            "@super_pavlik": "1621138520",
                            "@alxkat": "306536305",
                        },
                        "peer_to_username": {
                            "1621138520": "@super_pavlik",
                            "306536305": "@alxkat",
                        },
                    }
                ),
                encoding="utf-8",
            )

            username_to_peer, peer_to_username = self.mod._load_identity_history(
                history_path,
                archive_dir=archive_dir,
                group_url="https://web.telegram.org/a/#-1002465948544",
            )

        self.assertEqual(username_to_peer["@super_pavlik"], "1621138520")
        self.assertEqual(peer_to_username["1621138520"], "@super_pavlik")
        self.assertEqual(username_to_peer["@alxkat"], "306536305")
        self.assertEqual(peer_to_username["306536305"], "@alxkat")
        self.assertEqual(username_to_peer["@legacy_user"], "999")
        self.assertEqual(peer_to_username["999"], "@legacy_user")
        self.assertNotIn("1663660771", peer_to_username)

    def test_load_discovery_state_preserves_peer_states(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "discovery_state.json"
            path.write_text(
                json.dumps(
                    {
                        "version": 2,
                        "updated_at": "2026-04-25T00:00:00+00:00",
                        "seen_view_signatures": ["42,43"],
                        "seen_peer_ids": ["42", "43"],
                        "peer_states": {
                            "42": {
                                "attempt_count": 3,
                                "success_count": 1,
                                "failure_count": 2,
                                "last_outcome": "helper_blank:delivery_failure",
                                "last_attempted_at": "2026-04-25T00:00:00+00:00",
                                "last_username": "@alice_42",
                                "cooldown_until": "2026-04-25T06:00:00+00:00",
                            }
                        },
                        "mention_candidate_states": {
                            "@alice_42": {
                                "attempt_count": 2,
                                "success_count": 0,
                                "failure_count": 2,
                                "last_outcome": "mention_non_target",
                                "last_attempted_at": "2026-04-25T00:00:00+00:00",
                                "last_peer_id": "999",
                                "cooldown_until": "2026-04-25T03:00:00+00:00",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            state = self.mod._load_discovery_state(path)

        self.assertEqual(state["version"], 2)
        self.assertEqual(state["seen_peer_ids"], ["42", "43"])
        self.assertEqual(state["seen_view_signatures"], ["42,43"])
        self.assertEqual(state["peer_states"]["42"]["attempt_count"], 3)
        self.assertEqual(state["peer_states"]["42"]["success_count"], 1)
        self.assertEqual(state["peer_states"]["42"]["failure_count"], 2)
        self.assertEqual(state["peer_states"]["42"]["last_username"], "@alice_42")
        self.assertEqual(state["peer_states"]["42"]["cooldown_until"], "2026-04-25T06:00:00+00:00")
        self.assertEqual(state["mention_candidate_states"]["@alice_42"]["attempt_count"], 2)
        self.assertEqual(state["mention_candidate_states"]["@alice_42"]["failure_count"], 2)
        self.assertEqual(state["mention_candidate_states"]["@alice_42"]["last_peer_id"], "999")

    def test_build_parser_defaults_to_both(self) -> None:
        parser = self.mod.build_parser()
        args = parser.parse_args([])
        self.assertEqual(args.source, "both")
        self.assertFalse(args.include_bots)


if __name__ == "__main__":
    unittest.main()
