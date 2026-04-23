from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


def _load_export_module():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "scripts" / "export_telegram_members_non_pii.py"
    spec = importlib.util.spec_from_file_location("telegram_export_script_selection", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TelegramClientSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = _load_export_module()

    def test_find_tab_prefers_online_client_with_matching_telegram_dialog(self) -> None:
        clients = [
            {
                "client_id": "offline-client",
                "is_online": False,
                "tabs": [{"id": 10, "active": True, "url": "https://web.telegram.org/a/#-100"}],
            },
            {
                "client_id": "online-client",
                "is_online": True,
                "tabs": [{"id": 20, "active": True, "url": "https://web.telegram.org/a/#-200"}],
            },
        ]
        client_id, tab_id = self.mod._find_tab(clients, client_id=None, tab_id=None, url_pattern="https://web.telegram.org/a/#-200")
        self.assertEqual(client_id, "online-client")
        self.assertEqual(tab_id, 20)

    def test_find_tab_searches_across_multiple_clients_when_client_id_not_provided(self) -> None:
        clients = [
            {
                "client_id": "client-a",
                "is_online": True,
                "tabs": [{"id": 1, "active": False, "url": "https://example.com"}],
            },
            {
                "client_id": "client-b",
                "is_online": True,
                "tabs": [{"id": 2, "active": True, "url": "https://web.telegram.org/k/#-2181640359"}],
            },
        ]
        client_id, tab_id = self.mod._find_tab(clients, client_id=None, tab_id=None, url_pattern="https://web.telegram.org/k/#-2181640359")
        self.assertEqual(client_id, "client-b")
        self.assertEqual(tab_id, 2)

    def test_find_tab_uses_requested_client_when_explicitly_provided(self) -> None:
        clients = [
            {
                "client_id": "client-a",
                "is_online": False,
                "tabs": [{"id": 1, "active": True, "url": "https://web.telegram.org/a/#-111"}],
            },
            {
                "client_id": "client-b",
                "is_online": True,
                "tabs": [{"id": 2, "active": True, "url": "https://web.telegram.org/a/#-222"}],
            },
        ]
        client_id, tab_id = self.mod._find_tab(clients, client_id="client-a", tab_id=None, url_pattern="")
        self.assertEqual(client_id, "client-a")
        self.assertEqual(tab_id, 1)

    def test_dialog_row_fragment_strips_telegram_channel_prefix_for_k_mode(self) -> None:
        self.assertEqual(self.mod._dialog_row_fragment("-1002465948544"), "-2465948544")
        self.assertEqual(self.mod._dialog_row_fragment("12345"), "12345")


if __name__ == "__main__":
    unittest.main()
