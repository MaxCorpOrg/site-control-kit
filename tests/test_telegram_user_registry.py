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
            raw_text = target.read_text(encoding="utf-8")
            loaded = mod.load_registry(target)
            resolved = mod.resolve_user(loaded)
            self.assertEqual(resolved.get("name"), "prod-user")
            self.assertEqual(resolved.get("profile"), "/tmp/prod-profile")
            self.assertEqual(resolved.get("token"), "very-secret-token")
            self.assertNotIn("very-secret-token", raw_text)
            self.assertIn("secret_ref", raw_text)
            secrets_dir = target.parent / "secrets" / "users"
            self.assertTrue(secrets_dir.is_dir())
            self.assertTrue(any(path.read_text(encoding="utf-8").strip() == "very-secret-token" for path in secrets_dir.iterdir()))

    def test_load_registry_migrates_inline_token_into_secret_store(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "users.json"
            target.write_text(
                """
{
  "default_user": "legacy",
  "users": [
    {
      "name": "legacy",
      "profile": "/tmp/legacy",
      "token": "legacy-token",
      "updated_at": "2026-05-04T12:00:00+00:00"
    }
  ]
}
""".strip()
                + "\n",
                encoding="utf-8",
            )
            loaded = mod.load_registry(target)
            raw_text = target.read_text(encoding="utf-8")

        resolved = mod.resolve_user(loaded)
        self.assertEqual(resolved.get("token"), "legacy-token")
        self.assertNotIn('"token"', raw_text)
        self.assertIn("secret_ref", raw_text)

    def test_add_or_update_user_by_profile_updates_existing_row(self) -> None:
        registry = mod._empty_registry()
        registry = mod.add_or_update_user(
            registry,
            name="legacy-slot",
            token="legacy-token",
            profile="/tmp/slot-1",
            set_default=True,
        )

        registry = mod.add_or_update_user_by_profile(
            registry,
            name="Слот 1",
            token="secure-slot-token",
            profile="/tmp/slot-1",
            secret_ref="users/slot1.token",
            set_default=False,
        )

        users = mod.list_users(registry)
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]["name"], "Слот 1")
        self.assertEqual(users[0]["token"], "secure-slot-token")
        self.assertEqual(users[0]["secret_ref"], "users/slot1.token")
        self.assertEqual(registry.get("default_user"), "Слот 1")

    def test_remove_user_by_profile_updates_default(self) -> None:
        registry = mod._empty_registry()
        registry = mod.add_or_update_user(
            registry,
            name="TG_CONTACT 2",
            token="token-main",
            profile="/tmp/main",
            set_default=True,
        )
        registry = mod.add_or_update_user(
            registry,
            name="@AK-LIVE",
            token="token-live",
            profile="/tmp/live",
            set_default=False,
        )

        registry = mod.remove_user_by_profile(registry, profile="/tmp/main")

        self.assertEqual(registry.get("default_user"), "@AK-LIVE")
        self.assertEqual(len(mod.list_users(registry)), 1)
        self.assertEqual(mod.list_users(registry)[0]["profile"], "/tmp/live")


if __name__ == "__main__":
    unittest.main()
