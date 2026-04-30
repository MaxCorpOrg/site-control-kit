from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts import telegram_workspace_layout as mod


class TelegramWorkspaceLayoutTests(unittest.TestCase):
    def test_ensure_workspace_creates_slots_and_registry(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "telegram_workspace"
            payload = mod.ensure_workspace(root, slots=3)

            self.assertEqual(payload["slots"], 3)
            self.assertTrue((root / "registry" / "users.json").exists())
            self.assertTrue((root / "accounts" / "1" / "profile").exists())
            self.assertTrue((root / "accounts" / "3" / "keys" / "api_token.txt").exists())

    def test_list_profiles_includes_slot_profile_and_zip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "telegram_workspace"
            mod.ensure_workspace(root, slots=2)
            slot1 = root / "accounts" / "1"
            (slot1 / "profile" / "Default").mkdir(parents=True)
            (slot1 / "imports" / "portable.zip").write_bytes(b"PK")

            rows = mod.list_profiles(root)
            names = [name for name, _value in rows]

            self.assertIn("auto-slot-1-profile", names)
            self.assertIn("auto-slot-1-zip-portable", names)
            self.assertNotIn("auto-slot-2-profile", names)

    def test_list_profiles_skips_empty_default_and_empty_slots(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "telegram_workspace"
            mod.ensure_workspace(root, slots=2)

            rows = mod.list_profiles(root)

            self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
