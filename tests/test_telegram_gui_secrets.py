from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.telegram_gui.services.secrets import SecretStore, mask_secret


class SecretStoreTests(unittest.TestCase):
    def test_save_and_load_secret_with_secure_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base_dir = Path(td) / "registry" / "secrets"
            store = SecretStore(base_dir)
            secret_ref = store.save_secret(namespace="users", name="alice", token="super-secret-token")
            secret_path = store.ref_path(secret_ref)

            self.assertEqual(store.load_secret(secret_ref), "super-secret-token")
            self.assertTrue(secret_path.exists())
            self.assertTrue(store.is_secure(secret_path.parent))
            self.assertTrue(store.is_secure(secret_path))

    def test_mask_secret_keeps_edges_only(self) -> None:
        self.assertEqual(mask_secret("abcdefgh1234"), "abcd...1234")
        self.assertEqual(mask_secret("short"), "*****")

    def test_delete_secret_removes_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base_dir = Path(td) / "registry" / "secrets"
            store = SecretStore(base_dir)
            secret_ref = store.save_secret(namespace="users", name="alice", token="super-secret-token")

            deleted = store.delete_secret(secret_ref)

            self.assertIsNotNone(deleted)
            self.assertFalse(store.ref_path(secret_ref).exists())
