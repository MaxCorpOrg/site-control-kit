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
            patch.object(self.mod, "_read_sticky_chat_author_member", return_value=None),
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

    def test_collect_members_from_chat_auto_stops_on_repeated_identical_view_before_minimum_steps(self) -> None:
        member = {"peer_id": "1", "name": "One", "username": "—", "status": "из чата", "role": "—"}
        parse_sequence = [[member]] * 10
        discovery_state = {
            "peer_states": {},
            "seen_peer_ids": [],
            "seen_view_signatures": [],
        }

        with (
            patch.object(self.mod, "CHAT_JUMP_SCROLL_TRIGGER_STALL", 2),
            patch.object(self.mod, "_send_get_html", side_effect=[f"h{i}" for i in range(10)]),
            patch.object(self.mod, "_parse_chat_members", side_effect=parse_sequence),
            patch.object(self.mod, "_read_sticky_chat_author_member", return_value=None),
            patch.object(self.mod, "_scroll_chat_up", return_value=True) as mock_scroll,
        ):
            members, stats = self.mod._collect_members_from_chat(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=1,
                timeout_sec=5,
                scroll_steps=8,
                group_url="https://web.telegram.org/a/#-1002465948544",
                deep_usernames=False,
                chat_deep_limit=0,
                max_runtime_sec=120,
                auto_extra_steps=0,
                discovery_state=discovery_state,
            )

        self.assertEqual(len(members), 1)
        self.assertEqual(stats["unique_members"], 1)
        self.assertEqual(stats["scroll_steps_done"], 3)
        self.assertEqual(stats["revisited_view_steps"], 3)
        self.assertEqual(stats["discovery_revisit_steps"], 3)
        self.assertEqual(stats["discovery_new_visible"], 1)
        self.assertEqual(stats["burst_scrolls_done"], 0)
        self.assertEqual(stats["jump_scrolls_done"], 0)
        self.assertEqual(mock_scroll.call_count, 3)

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
            patch.object(self.mod, "_read_sticky_chat_author_member", return_value=None),
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

    def test_collect_members_from_chat_backfills_history_before_deep(self) -> None:
        member = {
            "peer_id": "1291639730",
            "name": "Known",
            "username": "—",
            "status": "из чата",
            "role": "—",
        }

        with (
            patch.object(self.mod, "_send_get_html", return_value="h0"),
            patch.object(self.mod, "_parse_chat_members", return_value=[member]),
            patch.object(self.mod, "_read_sticky_chat_author_member", return_value=None),
            patch.object(self.mod, "_enrich_usernames_deep_chat", return_value=(0, 0, 0, [])) as mock_deep,
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
                chat_deep_limit=12,
                max_runtime_sec=60,
                historical_username_to_peer={"@bychkov_aa": "1291639730"},
                historical_peer_to_username={"1291639730": "@Bychkov_AA"},
            )

        mock_deep.assert_not_called()
        self.assertEqual(members[0]["username"], "@Bychkov_AA")
        self.assertEqual(stats["history_prefilled"], 1)
        self.assertEqual(stats["history_prefill_conflicts"], 0)
        self.assertEqual(stats["deep_attempted"], 0)

    def test_collect_members_from_chat_skips_bot_targets_in_deep(self) -> None:
        bot_member = {
            "peer_id": "444",
            "name": "Notify Bot",
            "username": "—",
            "status": "bot",
            "role": "—",
        }

        with (
            patch.object(self.mod, "_send_get_html", return_value="h0"),
            patch.object(self.mod, "_parse_chat_members", return_value=[bot_member]),
            patch.object(self.mod, "_read_sticky_chat_author_member", return_value=None),
            patch.object(self.mod, "_enrich_usernames_deep_chat", return_value=(1, 1, 1, ["444"])) as mock_deep,
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
                chat_deep_limit=12,
                max_runtime_sec=60,
            )

        mock_deep.assert_not_called()
        self.assertEqual(len(members), 1)
        self.assertEqual(stats["deep_attempted"], 0)

    def test_collect_members_from_chat_uses_sticky_author_mention_before_helper_deep(self) -> None:
        sticky_member = {
            "peer_id": "8055002493",
            "name": "Sticky User",
            "username": "—",
            "status": "из чата",
            "role": "—",
        }

        with (
            patch.object(self.mod, "_send_get_html", return_value="h0"),
            patch.object(self.mod, "_parse_chat_members", return_value=[]),
            patch.object(self.mod, "_read_sticky_chat_author_member", return_value=sticky_member),
            patch.object(self.mod, "_try_username_via_mention_action", return_value=("@sticky_user", "success")),
            patch.object(self.mod, "_enrich_usernames_deep_chat", return_value=(0, 0, 0, [])) as mock_deep,
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
                chat_deep_limit=12,
                max_runtime_sec=60,
            )

        mock_deep.assert_not_called()
        self.assertEqual(len(members), 1)
        self.assertEqual(members[0]["peer_id"], "8055002493")
        self.assertEqual(members[0]["username"], "@sticky_user")
        self.assertEqual(stats["sticky_authors_seen"], 1)
        self.assertEqual(stats["sticky_mention_attempted"], 1)
        self.assertEqual(stats["sticky_mention_updated"], 1)
        self.assertEqual(stats["deep_attempted"], 1)
        self.assertEqual(stats["deep_updated"], 1)

    def test_collect_members_from_chat_uses_sticky_helper_after_menu_missing(self) -> None:
        sticky_member = {
            "peer_id": "8055002493",
            "name": "Sticky User",
            "username": "—",
            "status": "из чата",
            "role": "—",
        }

        with (
            patch.object(self.mod, "_send_get_html", return_value="h0"),
            patch.object(self.mod, "_parse_chat_members", return_value=[]),
            patch.object(self.mod, "_read_sticky_chat_author_member", return_value=sticky_member),
            patch.object(self.mod, "_try_username_via_mention_action", return_value=("—", "menu_missing")),
            patch.object(self.mod, "_read_username_via_helper_tab", return_value=("@sticky_helper", True)) as mock_helper,
            patch.object(self.mod, "_enrich_usernames_deep_chat", return_value=(0, 0, 0, [])) as mock_deep,
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
                chat_deep_limit=12,
                max_runtime_sec=60,
            )

        mock_deep.assert_not_called()
        self.assertEqual(mock_helper.call_count, 1)
        self.assertEqual(mock_helper.call_args.kwargs["peer_id"], "8055002493")
        self.assertEqual(mock_helper.call_args.kwargs["expected_name"], "Sticky User")
        self.assertFalse(mock_helper.call_args.kwargs["restore_base_tab"])
        self.assertIsInstance(mock_helper.call_args.kwargs["helper_session"], dict)
        self.assertEqual(members[0]["username"], "@sticky_helper")
        self.assertEqual(stats["sticky_mention_attempted"], 1)
        self.assertEqual(stats["sticky_mention_updated"], 0)
        self.assertEqual(stats["sticky_helper_attempted"], 1)
        self.assertEqual(stats["sticky_helper_updated"], 1)
        self.assertEqual(stats["deep_attempted"], 2)
        self.assertEqual(stats["deep_updated"], 1)

    def test_collect_members_from_chat_skips_sticky_only_when_sticky_peer_is_in_discovery_cooldown(self) -> None:
        sticky_member = {
            "peer_id": "8055002493",
            "name": "Sticky User",
            "username": "—",
            "status": "из чата",
            "role": "—",
        }
        other_visible = {
            "peer_id": "42",
            "name": "Other Visible",
            "username": "—",
            "status": "из чата",
            "role": "—",
        }
        discovery_state = {
            "peer_states": {
                "8055002493": {
                    "cooldown_until": "2099-01-01T00:00:00+00:00",
                }
            },
            "seen_peer_ids": [],
            "seen_view_signatures": [],
        }

        with (
            patch.object(self.mod, "_send_get_html", return_value="h0"),
            patch.object(self.mod, "_parse_chat_members", return_value=[other_visible]),
            patch.object(self.mod, "_read_sticky_chat_author_member", return_value=sticky_member),
            patch.object(self.mod, "_enrich_usernames_deep_chat", return_value=(1, 1, 1, ["42"])) as mock_deep,
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
                chat_deep_limit=12,
                max_runtime_sec=60,
                discovery_state=discovery_state,
            )

        self.assertEqual({item["peer_id"] for item in members}, {"8055002493", "42"})
        self.assertEqual(stats["sticky_mention_attempted"], 0)
        self.assertEqual(mock_deep.call_count, 1)
        self.assertEqual(
            [item["peer_id"] for item in mock_deep.call_args.kwargs["members"]],
            ["42"],
        )
        self.assertEqual(set(discovery_state["seen_peer_ids"]), {"8055002493", "42"})

    def test_collect_members_from_chat_limits_deep_to_sticky_author_when_available(self) -> None:
        sticky_member = {
            "peer_id": "1621138520",
            "name": "Known Sticky",
            "username": "@super_pavlik",
            "status": "из чата",
            "role": "—",
        }
        other_visible = {
            "peer_id": "8055002493",
            "name": "Other Visible",
            "username": "—",
            "status": "из чата",
            "role": "—",
        }

        with (
            patch.object(self.mod, "_send_get_html", return_value="h0"),
            patch.object(self.mod, "_parse_chat_members", return_value=[other_visible]),
            patch.object(self.mod, "_read_sticky_chat_author_member", return_value=sticky_member),
            patch.object(self.mod, "_try_username_via_mention_action", return_value=("@other_user", "success")) as mock_mention,
            patch.object(self.mod, "_enrich_usernames_deep_chat", return_value=(1, 1, 1, ["8055002493"])) as mock_deep,
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
                chat_deep_limit=12,
                max_runtime_sec=60,
            )

        mock_mention.assert_not_called()
        mock_deep.assert_not_called()
        self.assertEqual({item["peer_id"] for item in members}, {"1621138520", "8055002493"})
        self.assertEqual(stats["sticky_authors_seen"], 1)
        self.assertEqual(stats["deep_attempted"], 0)
        self.assertEqual(stats["deep_updated"], 0)

    def test_enrich_chat_usernames_via_mentions_skips_cooled_candidates_and_records_zero_yield(self) -> None:
        members = [
            {"peer_id": "42", "name": "Target", "username": "—", "status": "из чата", "role": "—"},
        ]
        discovery_state = {
            "mention_candidate_states": {
                "@skip_user": {
                    "cooldown_until": "2099-01-01T00:00:00+00:00",
                }
            }
        }
        body_html = '<div>@skip_user and @other_user</div>'
        user_html = '<div class="chat-info"><span class="peer-title" data-peer-id="999"></span></div>'

        with (
            patch.object(self.mod, "_send_get_html_best_effort", side_effect=[body_html, user_html]),
            patch.object(self.mod, "_send_command_result", return_value={"ok": True}),
            patch.object(self.mod, "_wait_for_current_opened_identity", return_value=("", "")),
            patch.object(self.mod.time, "sleep", return_value=None),
        ):
            attempted, updated = self.mod._enrich_chat_usernames_via_mentions(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=1,
                timeout_sec=5,
                group_url="https://web.telegram.org/a/#-1002465948544",
                members=members,
                deep_limit=4,
                discovery_state=discovery_state,
            )

        self.assertEqual(attempted, 1)
        self.assertEqual(updated, 0)
        self.assertEqual(members[0]["username"], "—")
        self.assertEqual(discovery_state["mention_candidate_states"]["@other_user"]["failure_count"], 1)
        self.assertEqual(discovery_state["mention_candidate_states"]["@other_user"]["last_outcome"], "mention_non_target")
        self.assertEqual(discovery_state["mention_candidate_states"]["@other_user"]["last_peer_id"], "999")

    def test_enrich_chat_usernames_via_mentions_records_success_for_peer_and_candidate(self) -> None:
        members = [
            {"peer_id": "42", "name": "Target", "username": "—", "status": "из чата", "role": "—"},
        ]
        discovery_state = {}
        body_html = '<div>@target_user</div>'
        user_html = '<div class="chat-info"><span class="peer-title" data-peer-id="42"></span></div>'

        with (
            patch.object(self.mod, "_send_get_html_best_effort", side_effect=[body_html, user_html]),
            patch.object(self.mod, "_send_command_result", return_value={"ok": True}),
            patch.object(self.mod, "_wait_for_current_opened_identity", return_value=("", "")),
            patch.object(self.mod.time, "sleep", return_value=None),
        ):
            attempted, updated = self.mod._enrich_chat_usernames_via_mentions(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=1,
                timeout_sec=5,
                group_url="https://web.telegram.org/a/#-1002465948544",
                members=members,
                deep_limit=4,
                discovery_state=discovery_state,
            )

        self.assertEqual(attempted, 1)
        self.assertEqual(updated, 1)
        self.assertEqual(members[0]["username"], "@target_user")
        self.assertEqual(discovery_state["peer_states"]["42"]["last_outcome"], "mention_deep_success")
        self.assertEqual(discovery_state["mention_candidate_states"]["@target_user"]["last_outcome"], "mention_deep_success")
        self.assertEqual(discovery_state["mention_candidate_states"]["@target_user"]["last_peer_id"], "42")

    def test_enrich_chat_usernames_via_mentions_uses_waited_identity_peer_id_without_body_peer_markup(self) -> None:
        members = [
            {"peer_id": "42", "name": "Target", "username": "—", "status": "из чата", "role": "—"},
        ]
        discovery_state = {}
        body_html = '<div>@target_user</div>'

        with (
            patch.object(self.mod, "_send_get_html_best_effort", return_value=body_html),
            patch.object(self.mod, "_send_command_result", return_value={"ok": True}),
            patch.object(self.mod, "_wait_for_current_opened_identity", return_value=("42", "Target")),
            patch.object(self.mod.time, "sleep", return_value=None),
        ):
            attempted, updated = self.mod._enrich_chat_usernames_via_mentions(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=1,
                timeout_sec=5,
                group_url="https://web.telegram.org/a/#-1002465948544",
                members=members,
                deep_limit=4,
                discovery_state=discovery_state,
            )

        self.assertEqual(attempted, 1)
        self.assertEqual(updated, 1)
        self.assertEqual(members[0]["username"], "@target_user")
        self.assertEqual(discovery_state["peer_states"]["42"]["last_outcome"], "mention_deep_success")

    def test_enrich_chat_usernames_via_mentions_uses_unique_title_match_when_peer_id_missing(self) -> None:
        members = [
            {"peer_id": "42", "name": "Exact Target Name", "username": "—", "status": "из чата", "role": "—"},
        ]
        discovery_state = {}
        body_html = '<div>@target_user</div>'

        with (
            patch.object(self.mod, "_send_get_html_best_effort", return_value=body_html),
            patch.object(self.mod, "_send_command_result", return_value={"ok": True}),
            patch.object(self.mod, "_wait_for_current_opened_identity", return_value=("", "Exact Target Name")),
            patch.object(self.mod.time, "sleep", return_value=None),
        ):
            attempted, updated = self.mod._enrich_chat_usernames_via_mentions(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=1,
                timeout_sec=5,
                group_url="https://web.telegram.org/a/#-1002465948544",
                members=members,
                deep_limit=4,
                discovery_state=discovery_state,
            )

        self.assertEqual(attempted, 1)
        self.assertEqual(updated, 1)
        self.assertEqual(members[0]["username"], "@target_user")
        self.assertEqual(discovery_state["mention_candidate_states"]["@target_user"]["last_peer_id"], "42")

    def test_enrich_chat_usernames_via_mentions_respects_runtime_budget(self) -> None:
        members = [
            {"peer_id": "42", "name": "Target", "username": "—", "status": "из чата", "role": "—"},
        ]
        discovery_state = {}
        body_html = '<div>@other_user @target_user</div>'
        time_calls = {"count": 0}

        def fake_time() -> float:
            time_calls["count"] += 1
            return 0.0 if time_calls["count"] <= 5 else 1.1

        with (
            patch.object(self.mod, "_send_get_html_best_effort", return_value=body_html),
            patch.object(self.mod, "_send_command_result", return_value={"ok": True}),
            patch.object(self.mod, "_wait_for_current_opened_identity", return_value=("999", "Other")),
            patch.object(self.mod, "_is_specific_tg_dialog_url", return_value=False),
            patch.object(self.mod.time, "sleep", return_value=None),
            patch.object(self.mod.time, "time", side_effect=fake_time),
        ):
            attempted, updated = self.mod._enrich_chat_usernames_via_mentions(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=1,
                timeout_sec=5,
                group_url="https://web.telegram.org/a/#-1002465948544",
                members=members,
                deep_limit=4,
                discovery_state=discovery_state,
                max_runtime_sec=0.5,
            )

        self.assertEqual(attempted, 1)
        self.assertEqual(updated, 0)
        self.assertNotIn("@target_user", discovery_state.get("mention_candidate_states", {}))

    def test_enrich_chat_usernames_via_mentions_returns_zero_when_best_effort_body_is_empty(self) -> None:
        members = [
            {"peer_id": "42", "name": "Target", "username": "—", "status": "из чата", "role": "—"},
        ]

        with patch.object(self.mod, "_send_get_html_best_effort", return_value=""):
            attempted, updated = self.mod._enrich_chat_usernames_via_mentions(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=1,
                timeout_sec=5,
                group_url="https://web.telegram.org/a/#-1002465948544",
                members=members,
                deep_limit=4,
            )

        self.assertEqual((attempted, updated), (0, 0))

    def test_enrich_chat_usernames_via_mentions_respects_candidate_cap(self) -> None:
        members = [
            {"peer_id": "42", "name": "Target", "username": "—", "status": "из чата", "role": "—"},
        ]
        discovery_state = {}
        body_html = '<div>@other_user @target_user</div>'

        with (
            patch.object(self.mod, "CHAT_MENTION_DEEP_MAX_PER_STEP", 1),
            patch.object(self.mod, "_send_get_html_best_effort", return_value=body_html),
            patch.object(self.mod, "_send_command_result", return_value={"ok": True}),
            patch.object(self.mod, "_wait_for_current_opened_identity", return_value=("999", "Other")),
            patch.object(self.mod.time, "sleep", return_value=None),
        ):
            attempted, updated = self.mod._enrich_chat_usernames_via_mentions(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=1,
                timeout_sec=5,
                group_url="https://web.telegram.org/a/#-1002465948544",
                members=members,
                deep_limit=4,
                discovery_state=discovery_state,
            )

        self.assertEqual(attempted, 1)
        self.assertEqual(updated, 0)
        self.assertIn("@other_user", discovery_state.get("mention_candidate_states", {}))
        self.assertNotIn("@target_user", discovery_state.get("mention_candidate_states", {}))

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

    def test_default_identity_history_path_uses_archive_state_dir(self) -> None:
        archive_dir = Path("/tmp/telegram-archive")
        path = self.mod._default_identity_history_path(
            archive_dir,
            "https://web.telegram.org/a/#-1002465948544",
        )

        self.assertEqual(
            path,
            archive_dir / "state" / "1002465948544_identity_history.json",
        )

    def test_load_identity_history_bootstraps_from_archived_usernames_sidecars(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive_dir = Path(tmp)
            sidecar_path = archive_dir / "20260423_174823_chat_1002465948544_15_usernames_json.json"
            sidecar_payload = {
                "group_url": "https://web.telegram.org/k/#-1002465948544",
                "rows": [
                    {"peer_id": "1291639730", "username": "@bychkov_aa"},
                    {"peer_id": "891274018", "username": "@bulan04"},
                ],
            }
            sidecar_path.write_text(json.dumps(sidecar_payload), encoding="utf-8")

            other_sidecar_path = archive_dir / "20260423_174823_chat_other_usernames_json.json"
            other_sidecar_payload = {
                "group_url": "https://web.telegram.org/a/#-1000000000000",
                "rows": [
                    {"peer_id": "1", "username": "@ignored_user"},
                ],
            }
            other_sidecar_path.write_text(json.dumps(other_sidecar_payload), encoding="utf-8")

            username_to_peer, peer_to_username = self.mod._load_identity_history(
                archive_dir / "state" / "1002465948544_identity_history.json",
                archive_dir=archive_dir,
                group_url="https://web.telegram.org/a/#-1002465948544",
            )

        self.assertEqual(username_to_peer["@bychkov_aa"], "1291639730")
        self.assertEqual(username_to_peer["@bulan04"], "891274018")
        self.assertEqual(peer_to_username["1291639730"], "@bychkov_aa")
        self.assertNotIn("@ignored_user", username_to_peer)

    def test_save_identity_history_merges_members_and_replaces_stale_peer_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            history_path = Path(tmp) / "state" / "history.json"
            members = [
                {
                    "peer_id": "555101371",
                    "name": "Teimur",
                    "username": "@Teimur_92",
                    "status": "из чата",
                    "role": "—",
                },
                {
                    "peer_id": "891274018",
                    "name": "Bulka",
                    "username": "@bulan04",
                    "status": "из чата",
                    "role": "Модератор",
                },
            ]

            self.mod._save_identity_history(
                history_path,
                members=members,
                historical_username_to_peer={"@abuzayd06": "555101371", "@legacy_user": "999"},
                historical_peer_to_username={"555101371": "@abuzayd06", "999": "@legacy_user"},
            )

            payload = json.loads(history_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["peer_to_username"]["555101371"], "@Teimur_92")
        self.assertEqual(payload["peer_to_username"]["891274018"], "@bulan04")
        self.assertEqual(payload["username_to_peer"]["@teimur_92"], "555101371")
        self.assertEqual(payload["username_to_peer"]["@bulan04"], "891274018")
        self.assertNotIn("@abuzayd06", payload["username_to_peer"])
        self.assertEqual(payload["username_to_peer"]["@legacy_user"], "999")

    def test_load_identity_history_drops_numeric_username_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            history_path = Path(tmp) / "state" / "history.json"
            history_path.parent.mkdir(parents=True, exist_ok=True)
            history_path.write_text(
                json.dumps(
                    {
                        "username_to_peer": {
                            "@1291639730": "5137994780",
                            "@bychkov_aa": "1291639730",
                        },
                        "peer_to_username": {
                            "5137994780": "@1291639730",
                            "1291639730": "@bychkov_aa",
                        },
                    }
                ),
                encoding="utf-8",
            )

            username_to_peer, peer_to_username = self.mod._load_identity_history(history_path)

        self.assertNotIn("@1291639730", username_to_peer)
        self.assertNotIn("5137994780", peer_to_username)
        self.assertEqual(username_to_peer["@bychkov_aa"], "1291639730")
        self.assertEqual(peer_to_username["1291639730"], "@bychkov_aa")

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
            patch.object(
                self.mod,
                "_http_json_retry",
                side_effect=itertools.chain(http_responses, itertools.repeat(http_responses[-1])),
            ),
            patch.object(
                self.mod.time,
                "time",
                side_effect=itertools.chain([0.0, 1.0, 200.0, 201.0, 400.0, 401.0], itertools.repeat(401.0)),
            ),
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

    def test_send_command_result_uses_bounded_request_timeouts(self) -> None:
        request_timeouts: list[tuple[str, str, float | None]] = []

        def fake_http_json_retry(server, token, method, path, payload=None, retries=3, request_timeout_sec=None):
            request_timeouts.append((method, path, request_timeout_sec))
            if method == "POST":
                return {"ok": True, "command_id": "cmd-3"}
            return {
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
            }

        with patch.object(self.mod, "_http_json_retry", side_effect=fake_http_json_retry):
            result = self.mod._send_command_result(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=1,
                timeout_sec=5,
                command={"type": "get_html", "selector": "body"},
            )

        self.assertTrue(result["ok"])
        self.assertEqual(request_timeouts[0][:2], ("POST", "/api/commands"))
        self.assertLessEqual(float(request_timeouts[0][2]), 5.0)
        self.assertEqual(request_timeouts[1][:2], ("GET", "/api/commands/cmd-3"))
        self.assertLessEqual(float(request_timeouts[1][2]), 5.0)

    def test_send_command_result_retries_after_poll_transport_timeout(self) -> None:
        responses = iter(
            [
                {"ok": True, "command_id": "cmd-4"},
                RuntimeError("Network error: timed out"),
                {
                    "command": {
                        "status": "completed",
                        "deliveries": {
                            "client-1": {
                                "status": "completed",
                                "result": {
                                    "ok": True,
                                    "status": "completed",
                                    "data": {"tabId": 456},
                                    "error": None,
                                    "logs": [],
                                },
                            }
                        },
                    }
                },
            ]
        )

        def fake_http_json_retry(server, token, method, path, payload=None, retries=3, request_timeout_sec=None):
            response = next(responses)
            if isinstance(response, Exception):
                raise response
            return response

        with (
            patch.object(self.mod, "_http_json_retry", side_effect=fake_http_json_retry),
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
        self.assertEqual(result["data"]["tabId"], 456)

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

    def test_try_username_via_mention_action_treats_missing_visible_menu_item_as_menu_missing(self) -> None:
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
                    "error": {"message": "No visible menu item found by text"},
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
        self.assertEqual(outcome, "menu_missing")
        self.assertEqual(mock_send.call_count, 4)

    def test_try_username_via_mention_action_can_use_sticky_anchor_context(self) -> None:
        def fake_send_command_result(**kwargs):
            command_type = kwargs["command"]["type"]
            if command_type == "wait_selector":
                return {"ok": True}
            if command_type == "extract_text":
                return {"ok": True, "data": {"text": "Mention"}}
            if command_type == "click_menu_text":
                return {"ok": True}
            raise AssertionError(f"Unexpected command type: {command_type}")

        with (
            patch.object(self.mod, "_clear_composer_text", return_value=None),
            patch.object(self.mod, "_telegram_sticky_author_command", return_value={"context_clicked": True, "peer_id": "42"}) as mock_sticky,
            patch.object(self.mod, "_send_command_result", side_effect=fake_send_command_result),
            patch.object(self.mod, "_read_username_from_composer", return_value="@alice_42"),
        ):
            username, outcome = self.mod._try_username_via_mention_action(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=1,
                peer_id="42",
                supports_click_menu_text=True,
                use_sticky_anchor=True,
            )

        self.assertEqual(username, "@alice_42")
        self.assertEqual(outcome, "success")
        self.assertTrue(mock_sticky.call_args.kwargs["context_click"])
        self.assertEqual(mock_sticky.call_args.kwargs["expected_peer_id"], "42")

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
        self.assertEqual(mock_helper.call_args.kwargs["expected_name"], "Alice")

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
            runtime_hints: dict[str, object] = {}
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
                runtime_hints=runtime_hints,
            )

        self.assertEqual(attempted, 2)
        self.assertEqual(updated, 2)
        self.assertEqual(opened, 2)
        self.assertEqual(opened_peer_ids, ["42", "43"])
        self.assertEqual(mock_mention.call_count, 1)
        self.assertEqual(mock_return.call_count, 1)
        self.assertEqual(helper_calls[0]["expected_name"], "Alice")
        self.assertEqual(helper_calls[0]["restore_base_tab"], False)
        self.assertEqual(helper_calls[1]["expected_name"], "Bob")
        self.assertEqual(helper_calls[1]["restore_base_tab"], False)
        self.assertEqual(members[0]["username"], "@alice_42")
        self.assertEqual(members[1]["username"], "@bob_43")
        self.assertTrue(runtime_hints["mention_unavailable"])

    def test_enrich_usernames_deep_chat_can_start_helper_only_from_runtime_hint(self) -> None:
        members = [
            {"peer_id": "42", "name": "Alice", "username": "—", "status": "из чата", "role": "—"},
            {"peer_id": "43", "name": "Bob", "username": "—", "status": "из чата", "role": "—"},
        ]

        with (
            patch.object(self.mod, "_return_to_group_dialog_reliable", return_value=True) as mock_return,
            patch.object(self.mod, "_get_tab_url", return_value="https://web.telegram.org/a/#-1002465948544") as mock_url,
            patch.object(self.mod, "_try_username_via_mention_action", return_value=("—", "menu_missing")) as mock_mention,
            patch.object(self.mod, "_read_username_via_helper_tab", return_value=("@alice_42", True)) as mock_helper,
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
                helper_only_initial=True,
            )

        self.assertEqual(attempted, 2)
        self.assertEqual(updated, 1)
        self.assertEqual(opened, 2)
        self.assertEqual(opened_peer_ids, ["42", "43"])
        mock_return.assert_not_called()
        mock_url.assert_not_called()
        mock_mention.assert_not_called()
        self.assertEqual(mock_helper.call_count, 2)
        self.assertEqual(mock_helper.call_args_list[0].kwargs["expected_name"], "Alice")
        self.assertEqual(mock_helper.call_args_list[0].kwargs["restore_base_tab"], False)
        self.assertEqual(mock_helper.call_args_list[1].kwargs["expected_name"], "Bob")
        self.assertEqual(mock_helper.call_args_list[1].kwargs["restore_base_tab"], False)

    def test_enrich_usernames_deep_chat_records_helper_blank_in_discovery_state(self) -> None:
        discovery_state = {"peer_states": {}, "seen_peer_ids": [], "seen_view_signatures": []}

        with (
            patch.object(self.mod, "_return_to_group_dialog_reliable", return_value=True),
            patch.object(self.mod, "_get_tab_url", return_value="https://web.telegram.org/a/#-1002465948544"),
            patch.object(self.mod, "_try_username_via_mention_action", return_value=("—", "delivery_failure")),
            patch.object(self.mod, "_read_username_via_helper_tab", return_value=("—", True)),
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
                discovery_state=discovery_state,
            )

        self.assertEqual((attempted, updated, opened, opened_peer_ids), (1, 0, 1, ["42"]))
        self.assertEqual(discovery_state["peer_states"]["42"]["failure_count"], 1)
        self.assertEqual(
            discovery_state["peer_states"]["42"]["last_outcome"],
            "helper_blank:delivery_failure",
        )
        self.assertTrue(discovery_state["peer_states"]["42"]["cooldown_until"])

    def test_wait_for_helper_target_identity_rejects_stale_other_profile(self) -> None:
        header_html = (
            '<div class="MiddleHeader">'
            '<div class="Avatar" data-peer-id="555101371"></div>'
            '<h3 class="fullName">Тэймур Гусейнов</h3>'
            "</div>"
        )

        def fake_send_command_result(**kwargs):
            self.assertEqual(kwargs["command"]["type"], "get_html")
            return {"ok": True, "data": {"html": header_html}}

        with (
            patch.object(self.mod, "_send_command_result", side_effect=fake_send_command_result),
            patch.object(self.mod, "_read_dialog_fragment_best_effort", return_value=""),
        ):
            matched = self.mod._wait_for_helper_target_identity(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=77,
                expected_peer_id="6964266260",
                expected_name="Evgeniy",
                timeout_sec=0.6,
            )

        self.assertFalse(matched)

    def test_wait_for_helper_target_identity_accepts_matching_peer_after_reload(self) -> None:
        header_htmls = iter(
            [
                '<div class="MiddleHeader"><h3 class="fullName">Loading</h3></div>',
                (
                    '<div class="MiddleHeader">'
                    '<div class="Avatar" data-peer-id="6964266260"></div>'
                    '<h3 class="fullName">Evgeniy</h3>'
                    "</div>"
                ),
            ]
        )

        def fake_send_command_result(**kwargs):
            self.assertEqual(kwargs["command"]["type"], "get_html")
            return {"ok": True, "data": {"html": next(header_htmls)}}

        with (
            patch.object(self.mod, "_send_command_result", side_effect=fake_send_command_result),
            patch.object(self.mod, "_read_dialog_fragment_best_effort", return_value=""),
        ):
            matched = self.mod._wait_for_helper_target_identity(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=77,
                expected_peer_id="6964266260",
                expected_name="Evgeniy",
                timeout_sec=0.8,
            )

        self.assertTrue(matched)

    def test_wait_for_helper_target_identity_accepts_matching_route_after_two_polls(self) -> None:
        with (
            patch.object(
                self.mod,
                "_read_helper_header_identity",
                side_effect=[("", ""), ("", "")],
            ),
            patch.object(
                self.mod,
                "_read_dialog_fragment_best_effort",
                return_value="6964266260",
            ),
            patch.object(self.mod.time, "sleep", return_value=None),
        ):
            matched = self.mod._wait_for_helper_target_identity(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=77,
                expected_peer_id="6964266260",
                expected_name="Evgeniy",
                timeout_sec=0.8,
            )

        self.assertTrue(matched)

    def test_wait_for_helper_target_identity_rejects_route_when_header_conflicts(self) -> None:
        with (
            patch.object(
                self.mod,
                "_read_helper_header_identity",
                return_value=("555101371", "Тэймур Гусейнов"),
            ),
            patch.object(
                self.mod,
                "_read_dialog_fragment_best_effort",
                return_value="6964266260",
            ),
            patch.object(self.mod.time, "sleep", return_value=None),
        ):
            matched = self.mod._wait_for_helper_target_identity(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=77,
                expected_peer_id="6964266260",
                expected_name="Evgeniy",
                timeout_sec=0.6,
            )

        self.assertFalse(matched)

    def test_wait_for_helper_target_identity_rejects_stable_non_target_route_after_two_polls(self) -> None:
        with (
            patch.object(
                self.mod,
                "_read_helper_header_identity",
                side_effect=[("", ""), ("", "")],
            ),
            patch.object(
                self.mod,
                "_read_dialog_fragment_best_effort",
                side_effect=[
                    "@plaguezonebot",
                    "@plaguezonebot",
                ],
            ),
            patch.object(self.mod.time, "sleep", return_value=None),
        ):
            matched = self.mod._wait_for_helper_target_identity(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=77,
                expected_peer_id="6964266260",
                expected_name="Evgeniy",
                timeout_sec=0.8,
            )

        self.assertFalse(matched)

    def test_soft_confirm_helper_target_route_accepts_matching_route_without_conflict(self) -> None:
        with (
            patch.object(self.mod, "_read_dialog_fragment_best_effort", return_value="6964266260"),
            patch.object(self.mod, "_read_helper_header_identity", return_value=("", "")),
        ):
            matched = self.mod._soft_confirm_helper_target_route(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=77,
                expected_peer_id="6964266260",
                expected_name="Evgeniy",
                timeout_sec=0.6,
            )

        self.assertTrue(matched)

    def test_soft_confirm_helper_target_route_rejects_conflicting_header(self) -> None:
        with (
            patch.object(self.mod, "_read_dialog_fragment_best_effort", return_value="6964266260"),
            patch.object(self.mod, "_read_helper_header_identity", return_value=("555101371", "Тэймур Гусейнов")),
        ):
            matched = self.mod._soft_confirm_helper_target_route(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=77,
                expected_peer_id="6964266260",
                expected_name="Evgeniy",
                timeout_sec=0.6,
            )

        self.assertFalse(matched)

    def test_read_dialog_fragment_best_effort_prefers_page_location_over_stale_tab_url(self) -> None:
        with (
            patch.object(self.mod, "_get_page_url_best_effort", return_value="https://web.telegram.org/a/#6964266260"),
            patch.object(self.mod, "_get_tab_url", return_value="https://web.telegram.org/a/#@PLAGUEZONEBOT"),
        ):
            fragment = self.mod._read_dialog_fragment_best_effort(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=77,
                timeout_sec=0.6,
            )

        self.assertEqual(fragment, "6964266260")

    def test_get_page_url_best_effort_respects_short_timeout_budget(self) -> None:
        seen_timeouts: list[float] = []

        def fake_send_command_result(**kwargs):
            seen_timeouts.append(float(kwargs["timeout_sec"]))
            return {"ok": True, "data": {"url": "https://web.telegram.org/a/#6964266260"}}

        with patch.object(self.mod, "_send_command_result", side_effect=fake_send_command_result):
            url = self.mod._get_page_url_best_effort(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=77,
                timeout_sec=0.35,
            )

        self.assertEqual(url, "https://web.telegram.org/a/#6964266260")
        self.assertEqual(len(seen_timeouts), 1)
        self.assertGreaterEqual(seen_timeouts[0], 0.3)
        self.assertLessEqual(seen_timeouts[0], 0.35)

    def test_get_tab_meta_best_effort_reads_url_and_title(self) -> None:
        with patch.object(
            self.mod,
            "_http_json",
            return_value={
                "clients": [
                    {
                        "client_id": "client-1",
                        "tabs": [
                            {"id": 77, "url": "https://web.telegram.org/a/#6964266260", "title": "Evgeniy | Telegram"},
                        ],
                    }
                ]
            },
        ):
            tab_url, tab_title = self.mod._get_tab_meta_best_effort(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=77,
                timeout_sec=0.4,
            )

        self.assertEqual(tab_url, "https://web.telegram.org/a/#6964266260")
        self.assertEqual(tab_title, "Evgeniy | Telegram")

    def test_trace_helper_route_probe_skips_without_trace(self) -> None:
        with (
            patch.object(self.mod, "CHAT_MENTION_TRACE", False),
            patch.object(self.mod, "_get_page_url_best_effort", side_effect=AssertionError("unexpected page read")),
            patch.object(self.mod, "_get_tab_meta_best_effort", side_effect=AssertionError("unexpected tab read")),
            patch.object(self.mod, "_read_helper_header_identity", side_effect=AssertionError("unexpected header read")),
            patch.object(self.mod, "_mention_trace_step", side_effect=AssertionError("unexpected trace step")),
        ):
            self.mod._trace_helper_route_probe(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=77,
                expected_peer_id="6964266260",
                expected_name="Evgeniy",
                timeout_sec=0.4,
                step="helper-route-probe-prewait",
            )

    def test_trace_helper_route_probe_records_all_route_signals(self) -> None:
        captured: dict[str, object] = {}

        def fake_trace_step(username, step, started_at, **fields):
            captured["username"] = username
            captured["step"] = step
            captured.update(fields)

        with (
            patch.object(self.mod, "CHAT_MENTION_TRACE", True),
            patch.object(self.mod, "_get_page_url_best_effort", return_value="https://web.telegram.org/a/#6964266260"),
            patch.object(
                self.mod,
                "_get_tab_meta_best_effort",
                return_value=("https://web.telegram.org/a/#@plaguezonebot", "Plague Zone Bot"),
            ),
            patch.object(self.mod, "_read_helper_header_identity", return_value=("", "Evgeniy")),
            patch.object(self.mod, "_mention_trace_step", side_effect=fake_trace_step),
        ):
            self.mod._trace_helper_route_probe(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=77,
                expected_peer_id="6964266260",
                expected_name="Evgeniy",
                timeout_sec=0.4,
                step="helper-route-probe-prewait",
            )

        self.assertEqual(captured["username"], "peer:6964266260")
        self.assertEqual(captured["step"], "helper-route-probe-prewait")
        self.assertEqual(captured["target"], "6964266260")
        self.assertEqual(captured["page"], "6964266260")
        self.assertEqual(captured["tab"], "@plaguezonebot")
        self.assertEqual(captured["tab_title"], "Plague_Zone_Bot")
        self.assertEqual(captured["header_peer"], "—")
        self.assertEqual(captured["header_title"], "Evgeniy")
        self.assertEqual(captured["route_match"], 1)
        self.assertEqual(captured["header_match"], 1)

    def test_wait_for_current_opened_identity_uses_peer_attribute_fallback(self) -> None:
        with (
            patch.object(self.mod, "_read_current_opened_identity", side_effect=[("", ""), ("42", "Target")]),
            patch.object(self.mod.time, "sleep", return_value=None),
        ):
            peer_id, title = self.mod._wait_for_current_opened_identity(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=77,
                timeout_sec=0.8,
            )

        self.assertEqual(peer_id, "42")
        self.assertEqual(title, "Target")

    def test_poll_username_from_page_location_respects_short_timeout_budget(self) -> None:
        seen_timeouts: list[float] = []

        def fake_send_command_result(**kwargs):
            seen_timeouts.append(float(kwargs["timeout_sec"]))
            return {"ok": True, "data": {"url": "https://web.telegram.org/a/#6964266260"}}

        with (
            patch.object(self.mod, "_send_command_result", side_effect=fake_send_command_result),
            patch.object(self.mod.time, "sleep", return_value=None),
            patch.object(
                self.mod.time,
                "time",
                side_effect=itertools.chain([0.0, 0.0, 0.6], itertools.repeat(0.6)),
            ),
        ):
            username, url = self.mod._poll_username_from_page_location(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=77,
                timeout_sec=0.6,
            )

        self.assertEqual(username, "—")
        self.assertEqual(url, "https://web.telegram.org/a/#6964266260")
        self.assertEqual(len(seen_timeouts), 1)
        self.assertGreaterEqual(seen_timeouts[0], 0.4)
        self.assertLessEqual(seen_timeouts[0], 0.6)

    def test_navigate_to_group_if_requested_recovers_from_username_tab_via_history_back(self) -> None:
        with (
            patch.object(self.mod, "_detect_current_dialog_url", return_value="https://web.telegram.org/a/#@PLAGUEZONEBOT"),
            patch.object(self.mod, "_return_to_group_dialog_fast", return_value=True) as mock_fast_return,
            patch.object(self.mod, "_ensure_group_dialog_url", side_effect=AssertionError("unexpected ensure")),
        ):
            self.mod._navigate_to_group_if_requested(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=77,
                group_url="https://web.telegram.org/a/#-1002465948544",
                timeout_sec=5,
            )

        mock_fast_return.assert_called_once()

    def test_navigate_to_group_if_requested_uses_forced_return_after_ensure_failure(self) -> None:
        with (
            patch.object(self.mod, "_detect_current_dialog_url", side_effect=[
                "https://web.telegram.org/a/#@PLAGUEZONEBOT",
                "https://web.telegram.org/a/#-1002465948544",
            ]),
            patch.object(self.mod, "_return_to_group_dialog_fast", return_value=False) as mock_fast_return,
            patch.object(self.mod, "_ensure_group_dialog_url", return_value=False) as mock_ensure,
            patch.object(self.mod, "_force_return_to_group_dialog", return_value=True) as mock_force_return,
        ):
            self.mod._navigate_to_group_if_requested(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=77,
                group_url="https://web.telegram.org/a/#-1002465948544",
                timeout_sec=5,
            )

        mock_fast_return.assert_called_once()
        mock_ensure.assert_called_once()
        mock_force_return.assert_called_once()

    def test_ensure_group_dialog_url_uses_detected_page_url_after_navigate(self) -> None:
        with (
            patch.object(
                self.mod,
                "_detect_current_dialog_url",
                side_effect=["https://web.telegram.org/a/#@PLAGUEZONEBOT", "https://web.telegram.org/a/#-1002465948544"],
            ),
            patch.object(self.mod, "_send_command_result", return_value={"ok": True}),
            patch.object(self.mod, "_is_dialog_surface_open", return_value=True),
            patch.object(self.mod, "_open_group_from_dialog_list", side_effect=AssertionError("unexpected dialog list open")),
            patch.object(self.mod.time, "sleep", return_value=None),
        ):
            matched = self.mod._ensure_group_dialog_url(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=77,
                group_url="https://web.telegram.org/a/#-1002465948544",
                timeout_sec=5,
            )

        self.assertTrue(matched)

    def test_navigate_to_group_if_requested_allows_username_route_when_dialog_surface_is_open(self) -> None:
        with (
            patch.object(self.mod, "_detect_current_dialog_url", return_value="https://web.telegram.org/a/#@PLAGUEZONEBOT"),
            patch.object(self.mod, "_return_to_group_dialog_fast", return_value=False),
            patch.object(self.mod, "_ensure_group_dialog_url", return_value=False),
            patch.object(self.mod, "_force_return_to_group_dialog", return_value=False),
            patch.object(self.mod, "_is_dialog_surface_open", return_value=True),
        ):
            self.mod._navigate_to_group_if_requested(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=77,
                group_url="https://web.telegram.org/a/#-1002465948544",
                timeout_sec=5,
            )

    def test_wait_for_current_opened_identity_passes_short_budget_to_reader(self) -> None:
        budgets: list[float] = []

        def fake_read_current_opened_identity(**kwargs):
            budgets.append(float(kwargs["timeout_sec"]))
            return "42", "Target"

        with patch.object(self.mod, "_read_current_opened_identity", side_effect=fake_read_current_opened_identity):
            peer_id, title = self.mod._wait_for_current_opened_identity(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=77,
                timeout_sec=0.8,
            )

        self.assertEqual(peer_id, "42")
        self.assertEqual(title, "Target")
        self.assertEqual(len(budgets), 1)
        self.assertGreaterEqual(budgets[0], 0.4)
        self.assertLessEqual(budgets[0], 0.8)

    def test_get_current_opened_peer_id_respects_short_timeout(self) -> None:
        seen_timeouts: list[float] = []

        def fake_send_command_result(**kwargs):
            seen_timeouts.append(float(kwargs["timeout_sec"]))
            return {"ok": True, "data": {"value": "42"}}

        with patch.object(self.mod, "_send_command_result", side_effect=fake_send_command_result):
            peer_id = self.mod._get_current_opened_peer_id(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=77,
                timeout_sec=0.8,
            )

        self.assertEqual(peer_id, "42")
        self.assertEqual(len(seen_timeouts), 1)
        self.assertGreaterEqual(seen_timeouts[0], 0.4)
        self.assertLessEqual(seen_timeouts[0], 0.8)

    def test_read_helper_header_identity_respects_short_timeout(self) -> None:
        seen_timeouts: list[float] = []

        def fake_send_command_result(**kwargs):
            seen_timeouts.append(float(kwargs["timeout_sec"]))
            return {"ok": True, "data": {"html": '<div data-peer-id="42"><span class="peer-title">Target</span></div>'}}

        with patch.object(self.mod, "_send_command_result", side_effect=fake_send_command_result):
            peer_id, title = self.mod._read_helper_header_identity(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=77,
                timeout_sec=0.8,
            )

        self.assertEqual(peer_id, "42")
        self.assertEqual(title, "Target")
        self.assertEqual(len(seen_timeouts), 1)
        self.assertGreaterEqual(seen_timeouts[0], 0.4)
        self.assertLessEqual(seen_timeouts[0], 0.8)

    def test_open_helper_tab_uses_background_tab(self) -> None:
        seen_command: dict[str, object] = {}

        def fake_send_command_result(**kwargs):
            seen_command.update(kwargs["command"])
            return {"ok": True, "data": {"tabId": 77}}

        with patch.object(self.mod, "_send_command_result", side_effect=fake_send_command_result):
            tab_id = self.mod._open_helper_tab(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=1,
                url="https://web.telegram.org/a/#6964266260",
                timeout_sec=5,
            )

        self.assertEqual(tab_id, 77)
        self.assertEqual(seen_command["type"], "new_tab")
        self.assertEqual(seen_command["url"], "https://web.telegram.org/a/#6964266260")
        self.assertFalse(bool(seen_command["active"]))

    def test_read_username_via_helper_tab_returns_blank_when_target_identity_not_confirmed(self) -> None:
        with (
            patch.object(self.mod, "_helper_session_tab_id", return_value=None),
            patch.object(self.mod, "_open_helper_tab", return_value=77),
            patch.object(self.mod, "_send_command_result", return_value={"ok": True}),
            patch.object(self.mod, "_wait_for_helper_target_identity", return_value=False),
            patch.object(self.mod, "_soft_confirm_helper_target_route", return_value=False),
            patch.object(self.mod, "_poll_username_from_tab_url", side_effect=AssertionError("unexpected stale tab url read")),
            patch.object(self.mod, "_poll_username_from_page_location", side_effect=AssertionError("unexpected stale page url read")),
            patch.object(self.mod, "_send_get_html", side_effect=AssertionError("unexpected stale header read")),
            patch.object(self.mod, "_open_current_chat_user_info_and_read_username", side_effect=AssertionError("unexpected stale profile read")),
            patch.object(self.mod, "_activate_tab_best_effort", return_value=None),
            patch.object(self.mod, "_close_tab_best_effort", return_value=None),
        ):
            username, opened = self.mod._read_username_via_helper_tab(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                base_tab_id=1,
                peer_id="6964266260",
                expected_name="Evgeniy",
                timeout_sec=5,
                tg_mode="a",
            )

        self.assertEqual(username, "—")
        self.assertTrue(opened)

    def test_read_username_via_helper_tab_reuses_session_without_activate(self) -> None:
        with (
            patch.object(self.mod, "_send_command_result", return_value={"ok": True}),
            patch.object(self.mod, "_wait_for_helper_target_identity", return_value=False),
            patch.object(self.mod, "_soft_confirm_helper_target_route", return_value=False),
            patch.object(self.mod, "_poll_username_from_tab_url", side_effect=AssertionError("unexpected stale tab url read")),
            patch.object(self.mod, "_poll_username_from_page_location", side_effect=AssertionError("unexpected stale page url read")),
            patch.object(self.mod, "_send_get_html", side_effect=AssertionError("unexpected stale header read")),
            patch.object(self.mod, "_open_current_chat_user_info_and_read_username", side_effect=AssertionError("unexpected stale profile read")),
            patch.object(self.mod, "_activate_tab_best_effort", return_value=None) as mock_activate,
            patch.object(self.mod, "_close_tab_best_effort", return_value=None),
        ):
            username, opened = self.mod._read_username_via_helper_tab(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                base_tab_id=1,
                peer_id="6964266260",
                expected_name="Evgeniy",
                timeout_sec=5,
                tg_mode="a",
                helper_session={"tab_id": 77},
                restore_base_tab=False,
            )

        self.assertEqual(username, "—")
        self.assertTrue(opened)
        mock_activate.assert_not_called()

    def test_read_username_via_helper_tab_respects_overall_deadline_after_open(self) -> None:
        with (
            patch.object(self.mod, "_helper_session_tab_id", return_value=None),
            patch.object(self.mod, "_open_helper_tab", return_value=77) as mock_open,
            patch.object(self.mod, "_send_command_result", side_effect=AssertionError("unexpected helper command after deadline")),
            patch.object(self.mod, "_wait_for_helper_target_identity", side_effect=AssertionError("unexpected identity wait after deadline")),
            patch.object(self.mod, "_activate_tab_best_effort", return_value=None),
            patch.object(self.mod, "_close_tab_best_effort", return_value=None),
            patch.object(
                self.mod.time,
                "time",
                side_effect=itertools.chain([0.0, 0.0, 0.0, 10.0], itertools.repeat(10.0)),
            ),
        ):
            username, opened = self.mod._read_username_via_helper_tab(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                base_tab_id=1,
                peer_id="6964266260",
                expected_name="Evgeniy",
                timeout_sec=5,
                tg_mode="a",
            )

        self.assertEqual(username, "—")
        self.assertTrue(opened)
        self.assertEqual(mock_open.call_count, 1)

    def test_read_username_via_helper_tab_soft_route_confirm_reaches_profile_read(self) -> None:
        helper_session = {"tab_id": None, "needs_base_restore": False}

        with (
            patch.object(self.mod, "_open_helper_tab", return_value=77),
            patch.object(self.mod, "_wait_for_helper_target_identity", return_value=False),
            patch.object(self.mod, "_soft_confirm_helper_target_route", return_value=True),
            patch.object(self.mod, "_send_command_result", return_value={"ok": True}),
            patch.object(self.mod, "_poll_username_from_tab_url", side_effect=AssertionError("unexpected url polling after soft route confirm")),
            patch.object(self.mod, "_poll_username_from_page_location", side_effect=AssertionError("unexpected page-url polling after soft route confirm")),
            patch.object(self.mod, "_send_get_html", side_effect=RuntimeError("missing header")),
            patch.object(self.mod, "_open_current_chat_user_info_and_read_username", return_value="@evgeniy"),
        ):
            username, opened = self.mod._read_username_via_helper_tab(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                base_tab_id=1,
                peer_id="6964266260",
                expected_name="Evgeniy",
                timeout_sec=5,
                tg_mode="a",
                helper_session=helper_session,
                restore_base_tab=False,
            )

        self.assertEqual(username, "@evgeniy")
        self.assertTrue(opened)
        self.assertTrue(helper_session["needs_base_restore"])

    def test_close_helper_session_best_effort_skips_restore_when_not_needed(self) -> None:
        helper_session = {"tab_id": 77, "needs_base_restore": False}
        with (
            patch.object(self.mod, "_close_tab_best_effort", return_value=None) as mock_close,
            patch.object(self.mod, "_activate_tab_best_effort", return_value=None) as mock_activate,
        ):
            self.mod._close_helper_session_best_effort(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                base_tab_id=1,
                helper_session=helper_session,
                timeout_sec=5,
            )

        mock_close.assert_called_once()
        mock_activate.assert_not_called()
        self.assertIsNone(helper_session["tab_id"])
        self.assertFalse(helper_session["needs_base_restore"])

    def test_open_current_chat_user_info_and_read_username_respects_deadline(self) -> None:
        seen_command_types: list[str] = []

        def fake_send_command_result(**kwargs):
            seen_command_types.append(kwargs["command"]["type"])
            return {"ok": True}

        with (
            patch.object(self.mod, "_send_command_result", side_effect=fake_send_command_result),
            patch.object(
                self.mod.time,
                "time",
                side_effect=itertools.chain([0.0, 0.0, 2.0], itertools.repeat(2.0)),
            ),
        ):
            username = self.mod._open_current_chat_user_info_and_read_username(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=77,
                timeout_sec=5,
                deadline=1.0,
            )

        self.assertEqual(username, "—")
        self.assertEqual(seen_command_types, ["click"])

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
