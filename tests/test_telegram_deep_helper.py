from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


def _load_export_module():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "scripts" / "export_telegram_members_non_pii.py"
    spec = importlib.util.spec_from_file_location("telegram_export_script", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TelegramDeepHelperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = _load_export_module()

    def test_info_deep_uses_helper_tab_username(self) -> None:
        members = [{"peer_id": "123", "name": "Alice", "username": "—", "role": "", "status": ""}]
        with (
            patch.object(self.mod, "_read_username_via_helper_tab", return_value=("@alicefit", True)),
            patch.object(self.mod, "_close_helper_session_best_effort", return_value=None),
        ):
            attempted, updated, opened_peer_ids = self.mod._enrich_usernames_deep(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=100,
                timeout_sec=5,
                group_url="https://web.telegram.org/a/#-1002465948544",
                members=members,
            )
        self.assertEqual(attempted, 1)
        self.assertEqual(updated, 1)
        self.assertEqual(opened_peer_ids, ["123"])
        self.assertEqual(members[0]["username"], "@alicefit")

    def test_chat_deep_uses_helper_tab_without_leaving_group(self) -> None:
        members = [{"peer_id": "456", "name": "Bob", "username": "—", "role": "", "status": ""}]
        with (
            patch.object(self.mod, "_return_to_group_dialog_reliable", return_value=True),
            patch.object(self.mod, "_get_tab_url", return_value="https://web.telegram.org/a/#-1002465948544"),
            patch.object(self.mod, "_try_username_via_mention_action", return_value="—"),
            patch.object(self.mod, "_read_username_via_helper_tab", return_value=("@bobmass", True)),
            patch.object(self.mod, "_close_helper_session_best_effort", return_value=None),
        ):
            attempted, updated, opened, opened_peer_ids = self.mod._enrich_usernames_deep_chat(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=100,
                timeout_sec=5,
                members=members,
                group_url="https://web.telegram.org/a/#-1002465948544",
                max_runtime_sec=5.0,
                mode="full",
            )
        self.assertEqual(attempted, 1)
        self.assertEqual(updated, 1)
        self.assertEqual(opened, 1)
        self.assertEqual(opened_peer_ids, ["456"])
        self.assertEqual(members[0]["username"], "@bobmass")

    def test_read_username_via_helper_tab_reuses_session_tab(self) -> None:
        helper_session = {"tab_id": None}

        def fake_send_command_result(**kwargs):
            command_type = kwargs["command"]["type"]
            if command_type in {"wait_selector", "navigate", "activate_tab"}:
                return {"ok": True}
            raise AssertionError(f"Unexpected command type: {command_type}")

        with (
            patch.object(self.mod, "_open_helper_tab", return_value=777) as mock_open,
            patch.object(self.mod, "_activate_tab_best_effort", return_value=None),
            patch.object(self.mod, "_send_command_result", side_effect=fake_send_command_result),
            patch.object(self.mod, "_wait_for_helper_target_identity", return_value=True),
            patch.object(self.mod, "_poll_username_from_tab_url", side_effect=[("—", False), ("—", False)]),
            patch.object(self.mod, "_poll_username_from_page_location", side_effect=[("@alpha_fit", False), ("@beta_fit", False)]),
        ):
            username_a, opened_a = self.mod._read_username_via_helper_tab(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                base_tab_id=100,
                peer_id="111",
                timeout_sec=5,
                tg_mode="a",
                helper_session=helper_session,
            )
            username_b, opened_b = self.mod._read_username_via_helper_tab(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                base_tab_id=100,
                peer_id="222",
                timeout_sec=5,
                tg_mode="a",
                helper_session=helper_session,
            )

        self.assertEqual(username_a, "@alpha_fit")
        self.assertEqual(username_b, "@beta_fit")
        self.assertTrue(opened_a)
        self.assertTrue(opened_b)
        self.assertEqual(helper_session["tab_id"], 777)
        self.assertEqual(mock_open.call_count, 1)

    def test_read_username_via_helper_tab_can_leave_helper_active_between_peers(self) -> None:
        helper_session = {"tab_id": None}

        def fake_send_command_result(**kwargs):
            command_type = kwargs["command"]["type"]
            if command_type in {"wait_selector", "activate_tab"}:
                return {"ok": True}
            raise AssertionError(f"Unexpected command type: {command_type}")

        with (
            patch.object(self.mod, "_open_helper_tab", return_value=777),
            patch.object(self.mod, "_activate_tab_best_effort", return_value=None) as mock_activate,
            patch.object(self.mod, "_send_command_result", side_effect=fake_send_command_result),
            patch.object(self.mod, "_wait_for_helper_target_identity", return_value=True),
            patch.object(self.mod, "_poll_username_from_tab_url", return_value=("—", False)),
            patch.object(self.mod, "_poll_username_from_page_location", return_value=("@alpha_fit", False)),
        ):
            username, opened = self.mod._read_username_via_helper_tab(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                base_tab_id=100,
                peer_id="111",
                timeout_sec=5,
                tg_mode="a",
                helper_session=helper_session,
                restore_base_tab=False,
            )

        self.assertEqual(username, "@alpha_fit")
        self.assertTrue(opened)
        self.assertEqual(helper_session["tab_id"], 777)
        mock_activate.assert_not_called()

    def test_close_helper_session_best_effort_closes_reused_tab(self) -> None:
        helper_session = {"tab_id": 777}
        with (
            patch.object(self.mod, "_close_tab_best_effort", return_value=None) as mock_close,
            patch.object(self.mod, "_activate_tab_best_effort", return_value=None) as mock_activate,
        ):
            self.mod._close_helper_session_best_effort(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                base_tab_id=100,
                helper_session=helper_session,
                timeout_sec=3,
            )

        mock_close.assert_called_once()
        mock_activate.assert_called_once()
        self.assertIsNone(helper_session["tab_id"])

    def test_read_username_via_helper_tab_tolerates_missing_header_shell(self) -> None:
        helper_session = {"tab_id": None}

        def fake_send_command_result(**kwargs):
            command_type = kwargs["command"]["type"]
            if command_type in {"wait_selector", "activate_tab"}:
                return {"ok": True}
            raise AssertionError(f"Unexpected command type: {command_type}")

        with (
            patch.object(self.mod, "_open_helper_tab", return_value=888),
            patch.object(self.mod, "_activate_tab_best_effort", return_value=None),
            patch.object(self.mod, "_send_command_result", side_effect=fake_send_command_result),
            patch.object(self.mod, "_wait_for_helper_target_identity", return_value=True),
            patch.object(self.mod, "_poll_username_from_tab_url", return_value=("—", False)),
            patch.object(self.mod, "_poll_username_from_page_location", return_value=("—", False)),
            patch.object(self.mod, "_send_get_html", side_effect=RuntimeError("missing header")),
            patch.object(self.mod, "_open_current_chat_user_info_and_read_username", return_value="@gamma_fit"),
        ):
            username, opened = self.mod._read_username_via_helper_tab(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                base_tab_id=100,
                peer_id="333",
                timeout_sec=5,
                tg_mode="a",
                helper_session=helper_session,
            )

        self.assertEqual(username, "@gamma_fit")
        self.assertTrue(opened)

    def test_open_current_chat_user_info_prefers_current_telegram_header_selector(self) -> None:
        click_selectors: list[str] = []

        def fake_send_command_result(**kwargs):
            command = kwargs["command"]
            command_type = command["type"]
            if command_type == "click":
                click_selectors.append(command["selector"])
                return {"ok": command["selector"] == ".chat-info"}
            if command_type == "wait_selector":
                return {"ok": True}
            raise AssertionError(f"Unexpected command type: {command_type}")

        profile_html = (
            '<div id="RightColumn">'
            '<div class="multiline-item"><span class="title">@alpha_fit</span>'
            '<span class="subtitle">Username</span></div>'
            "</div>"
        )

        with (
            patch.object(self.mod, "_send_command_result", side_effect=fake_send_command_result),
            patch.object(self.mod, "_send_get_html", return_value=profile_html),
            patch.object(self.mod, "_close_profile_card", return_value=None),
        ):
            username = self.mod._open_current_chat_user_info_and_read_username(
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=777,
                timeout_sec=5,
            )

        self.assertEqual(username, "@alpha_fit")
        self.assertEqual(click_selectors, [".chat-info"])


if __name__ == "__main__":
    unittest.main()
