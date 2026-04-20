from __future__ import annotations

import unittest

from webcontrol.cli import (
    _absolute_tab_hotkey,
    _annotate_stale_extension_hint,
    _extract_command_result,
    _find_created_tab,
    _find_browser_tab,
    _pick_client,
    _tab_present,
    _tab_cycle_plan,
)


class BrowserCliHelperTests(unittest.TestCase):
    def test_pick_client_by_requested_id(self) -> None:
        clients = [
            {"client_id": "client-a", "last_seen": "2026-03-31T10:00:00+00:00"},
            {"client_id": "client-b", "last_seen": "2026-03-31T11:00:00+00:00"},
        ]
        selected = _pick_client(clients, "client-a")
        self.assertEqual(selected["client_id"], "client-a")

    def test_pick_client_uses_freshest_when_not_specified(self) -> None:
        clients = [
            {"client_id": "client-a", "last_seen": "2026-03-31T10:00:00+00:00"},
            {"client_id": "client-b", "last_seen": "2026-03-31T11:00:00+00:00"},
        ]
        selected = _pick_client(clients)
        self.assertEqual(selected["client_id"], "client-b")

    def test_extract_command_result_for_selected_client(self) -> None:
        command = {
            "deliveries": {
                "client-a": {"result": {"ok": True, "data": {"text": "hello"}}},
                "client-b": {"result": {"ok": False, "error": {"message": "boom"}}},
            }
        }
        result = _extract_command_result(command, "client-a")
        self.assertEqual(result["data"]["text"], "hello")

    def test_find_browser_tab_prefers_explicit_tab_id(self) -> None:
        client = {
            "tabs": [
                {"id": 10, "windowId": 1, "active": False, "url": "https://example.com/a"},
                {"id": 11, "windowId": 1, "active": True, "url": "https://example.com/b"},
            ]
        }
        tab = _find_browser_tab(client, {"tab_id": 10, "active": True})
        self.assertIsNotNone(tab)
        self.assertEqual(tab["id"], 10)

    def test_find_browser_tab_uses_url_pattern_before_active(self) -> None:
        client = {
            "tabs": [
                {"id": 10, "windowId": 1, "active": False, "url": "https://example.com/a"},
                {"id": 11, "windowId": 1, "active": True, "url": "https://telegram.org/b"},
            ]
        }
        tab = _find_browser_tab(client, {"url_pattern": "telegram.org", "active": True})
        self.assertIsNotNone(tab)
        self.assertEqual(tab["id"], 11)

    def test_tab_cycle_plan_prefers_shorter_reverse_path(self) -> None:
        tabs = [
            {"id": 1, "active": False},
            {"id": 2, "active": False},
            {"id": 3, "active": False},
            {"id": 4, "active": True},
            {"id": 5, "active": False},
        ]
        steps, reverse = _tab_cycle_plan(tabs, 2)  # type: ignore[misc]
        self.assertEqual(steps, 2)
        self.assertTrue(reverse)

    def test_absolute_tab_hotkey_uses_last_tab_shortcut(self) -> None:
        tabs = [{"id": index, "active": index == 1} for index in range(1, 11)]
        self.assertEqual(_absolute_tab_hotkey(tabs, 10), "9")
        self.assertIsNone(_absolute_tab_hotkey(tabs, 9))

    def test_find_created_tab_prefers_requested_url(self) -> None:
        client = {
            "tabs": [
                {"id": 10, "windowId": 1, "active": False, "url": "https://example.org"},
                {"id": 11, "windowId": 1, "active": True, "url": "chrome://newtab/"},
            ]
        }
        tab = _find_created_tab(
            client,
            window_id=1,
            previous_tab_ids={1, 2, 3},
            preferred_url="example.org",
        )
        self.assertIsNotNone(tab)
        self.assertEqual(tab["id"], 10)

    def test_find_created_tab_can_require_active(self) -> None:
        client = {
            "tabs": [
                {"id": 10, "windowId": 1, "active": False, "url": "https://example.org"},
                {"id": 11, "windowId": 1, "active": True, "url": "chrome://newtab/"},
            ]
        }
        tab = _find_created_tab(
            client,
            window_id=1,
            previous_tab_ids={1, 2, 3},
            preferred_url="example.org",
            require_active=True,
        )
        self.assertIsNotNone(tab)
        self.assertEqual(tab["id"], 11)

    def test_tab_present_detects_known_tab(self) -> None:
        client = {"tabs": [{"id": 10}, {"id": 11}]}
        self.assertTrue(_tab_present(client, 11))

    def test_tab_present_returns_false_for_missing_tab(self) -> None:
        client = {"tabs": [{"id": 10}, {"id": 11}]}
        self.assertFalse(_tab_present(client, 12))

    def test_annotate_stale_extension_hint_marks_tab_level_content_script_misroute(self) -> None:
        command_record = {
            "status": "failed",
            "deliveries": {
                "client-a": {
                    "result": {
                        "ok": False,
                        "error": {"message": "Unsupported command type in content script: new_tab"},
                    }
                }
            },
        }

        updated = _annotate_stale_extension_hint("new-tab", "client-a", command_record)
        error = updated["deliveries"]["client-a"]["result"]["error"]

        self.assertIn("hint", error)
        self.assertIn("chrome://extensions", error["hint"])

    def test_annotate_stale_extension_hint_ignores_non_tab_actions(self) -> None:
        command_record = {
            "status": "failed",
            "deliveries": {
                "client-a": {
                    "result": {
                        "ok": False,
                        "error": {"message": "Unsupported command type in content script: click"},
                    }
                }
            },
        }

        updated = _annotate_stale_extension_hint("click", "client-a", command_record)
        error = updated["deliveries"]["client-a"]["result"]["error"]

        self.assertNotIn("hint", error)


if __name__ == "__main__":
    unittest.main()
