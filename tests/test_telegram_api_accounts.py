from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts import telegram_api_accounts as mod


class TelegramApiAccountsTests(unittest.TestCase):
    def test_add_update_and_resolve_default(self) -> None:
        registry = mod._empty_registry()
        registry = mod.add_or_update_account(
            registry,
            name="acc-1",
            token="token-1-abcdef",
            client_id="client-a",
            set_default=True,
        )
        registry = mod.add_or_update_account(
            registry,
            name="acc-2",
            token="token-2-abcdef",
            client_id="client-b",
            set_default=False,
        )
        resolved = mod.resolve_account(registry)
        self.assertEqual(resolved.get("name"), "acc-1")
        self.assertEqual(resolved.get("client_id"), "client-a")

        registry = mod.add_or_update_account(
            registry,
            name="acc-2",
            token="token-2-updated",
            client_id="client-c",
            set_default=True,
        )
        resolved2 = mod.resolve_account(registry)
        self.assertEqual(resolved2.get("name"), "acc-2")
        self.assertEqual(resolved2.get("token"), "token-2-updated")
        self.assertEqual(resolved2.get("client_id"), "client-c")

    def test_remove_updates_default(self) -> None:
        registry = mod._empty_registry()
        registry = mod.add_or_update_account(registry, name="a", token="token-a", set_default=True)
        registry = mod.add_or_update_account(registry, name="b", token="token-b", set_default=False)
        registry = mod.remove_account(registry, name="a")
        self.assertEqual(registry.get("default_account"), "b")

    def test_save_and_load_roundtrip(self) -> None:
        registry = mod._empty_registry()
        registry = mod.add_or_update_account(
            registry,
            name="prod",
            token="very-secret-token",
            client_id="client-prod",
            set_default=True,
        )
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "accounts.json"
            mod.save_registry(target, registry)
            loaded = mod.load_registry(target)
            resolved = mod.resolve_account(loaded)
            self.assertEqual(resolved.get("name"), "prod")
            self.assertEqual(resolved.get("client_id"), "client-prod")


if __name__ == "__main__":
    unittest.main()
