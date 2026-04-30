from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts import telegram_user_registry as mod


class TelegramUserRegistryTests(unittest.TestCase):
    def test_add_update_and_resolve_default(self) -> None:
        registry = mod._empty_registry()
        registry = mod.add_or_update_user(
            registry,
            name="user-a",
            token="token-a-12345",
            profile="/tmp/profile-a",
            set_default=True,
        )
        registry = mod.add_or_update_user(
            registry,
            name="user-b",
            token="token-b-12345",
            profile="/tmp/profile-b",
            set_default=False,
        )
        resolved = mod.resolve_user(registry)
        self.assertEqual(resolved.get("name"), "user-a")
        self.assertEqual(resolved.get("profile"), "/tmp/profile-a")

        registry = mod.add_or_update_user(
            registry,
            name="user-b",
            token="token-b-updated",
            profile="/tmp/profile-b2",
            set_default=True,
        )
        resolved2 = mod.resolve_user(registry)
        self.assertEqual(resolved2.get("name"), "user-b")
        self.assertEqual(resolved2.get("token"), "token-b-updated")
        self.assertEqual(resolved2.get("profile"), "/tmp/profile-b2")

    def test_remove_updates_default(self) -> None:
        registry = mod._empty_registry()
        registry = mod.add_or_update_user(registry, name="a", token="token-a", set_default=True)
        registry = mod.add_or_update_user(registry, name="b", token="token-b", set_default=False)
        registry = mod.remove_user(registry, name="a")
        self.assertEqual(registry.get("default_user"), "b")

    def test_save_and_load_roundtrip(self) -> None:
        registry = mod._empty_registry()
        registry = mod.add_or_update_user(
            registry,
            name="prod-user",
            token="very-secret-token",
            profile="/tmp/prod-profile",
            set_default=True,
        )
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "users.json"
            mod.save_registry(target, registry)
            loaded = mod.load_registry(target)
            resolved = mod.resolve_user(loaded)
            self.assertEqual(resolved.get("name"), "prod-user")
            self.assertEqual(resolved.get("profile"), "/tmp/prod-profile")


if __name__ == "__main__":
    unittest.main()
