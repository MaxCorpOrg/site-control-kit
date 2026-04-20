from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


def _load_profiles_module():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "scripts" / "telegram_profiles.py"
    spec = importlib.util.spec_from_file_location("telegram_profiles", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TelegramProfilesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = _load_profiles_module()

    def test_resolve_profile_name_falls_back_to_balanced(self) -> None:
        self.assertEqual(self.mod.resolve_profile_name("fast"), "fast")
        self.assertEqual(self.mod.resolve_profile_name("DEEP"), "deep")
        self.assertEqual(self.mod.resolve_profile_name("unknown"), "balanced")

    def test_resolve_chain_interval_uses_profile_defaults(self) -> None:
        self.assertEqual(self.mod.resolve_chain_interval("fast"), 8.0)
        self.assertEqual(self.mod.resolve_chain_interval("balanced"), 20.0)
        self.assertEqual(self.mod.resolve_chain_interval("deep"), 30.0)

    def test_build_profile_env_returns_expected_overrides(self) -> None:
        fast_env = self.mod.build_profile_env("fast")
        self.assertEqual(fast_env["CHAT_SCROLL_STEPS"], "10")
        self.assertEqual(fast_env["CHAT_DEEP_LIMIT"], "24")
        self.assertEqual(fast_env["CHAT_MAX_RUNTIME"], "120")

        deep_env = self.mod.build_profile_env("deep")
        self.assertEqual(deep_env["TELEGRAM_CHAT_DISCOVERY_SCROLL_BURST"], "3")
        self.assertEqual(deep_env["TELEGRAM_CHAT_JUMP_SCROLL_TRIGGER_STALL"], "2")


if __name__ == "__main__":
    unittest.main()
