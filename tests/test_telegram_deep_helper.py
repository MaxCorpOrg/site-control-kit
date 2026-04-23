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
        with patch.object(self.mod, "_read_username_via_helper_tab", return_value=("@alicefit", True)):
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


if __name__ == "__main__":
    unittest.main()
