from __future__ import annotations

import unittest

from webcontrol.cli import _extract_command_result, _parse_xwininfo_windows, _pick_client, build_parser


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

    def test_pick_client_uses_freshest_online_when_required(self) -> None:
        clients = [
            {"client_id": "client-a", "last_seen": "2026-03-31T12:00:00+00:00", "is_online": False},
            {"client_id": "client-b", "last_seen": "2026-03-31T11:00:00+00:00", "is_online": True},
        ]
        selected = _pick_client(clients, require_online=True)
        self.assertEqual(selected["client_id"], "client-b")

    def test_pick_client_rejects_offline_requested_client_when_online_required(self) -> None:
        clients = [
            {"client_id": "client-a", "last_seen": "2026-03-31T12:00:00+00:00", "is_online": False},
        ]
        with self.assertRaisesRegex(RuntimeError, "offline"):
            _pick_client(clients, "client-a", require_online=True)

    def test_extract_command_result_for_selected_client(self) -> None:
        command = {
            "deliveries": {
                "client-a": {"result": {"ok": True, "data": {"text": "hello"}}},
                "client-b": {"result": {"ok": False, "error": {"message": "boom"}}},
            }
        }
        result = _extract_command_result(command, "client-a")
        self.assertEqual(result["data"]["text"], "hello")

    def test_parse_xwininfo_windows(self) -> None:
        output = """
             0x3a00004 "Extensions - Site Control Bridge - Google Chrome": ("google-chrome (/tmp/site-control-kit-manual-profile-2)" "Google-chrome")  1298x736+68+32  +68+32
        """
        windows = _parse_xwininfo_windows(output)
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0]["window_id"], "0x3a00004")
        self.assertEqual(windows[0]["width"], 1298)
        self.assertEqual(windows[0]["height"], 736)

    def test_build_parser_accepts_browser_x11_click(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["browser", "x11-click", "--x-ratio", "0.5", "--y-ratio", "0.75"])
        self.assertEqual(args.command, "browser")
        self.assertEqual(args.browser_action, "x11-click")
        self.assertAlmostEqual(args.x_ratio, 0.5)
        self.assertAlmostEqual(args.y_ratio, 0.75)
        self.assertEqual(args.button, 1)


if __name__ == "__main__":
    unittest.main()
