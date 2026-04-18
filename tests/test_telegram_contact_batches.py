from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


def _load_batch_module():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "scripts" / "telegram_contact_batches.py"
    spec = importlib.util.spec_from_file_location("telegram_contact_batches", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TelegramContactBatchesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = _load_batch_module()

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_load_usernames_normalizes_and_dedupes(self) -> None:
        source = self.root / "source.txt"
        source.write_text("@Alice_123\nnoise\n@alice_123\n@Bob_456\n", encoding="utf-8")

        usernames = self.mod.load_usernames(source)

        self.assertEqual(usernames, ["@alice_123", "@bob_456"])

    def test_next_batch_number_ignores_non_numbered_files(self) -> None:
        batch_dir = self.root / "chat"
        batch_dir.mkdir()
        (batch_dir / "1.txt").write_text("@one_111\n", encoding="utf-8")
        (batch_dir / "5.txt").write_text("@five_555\n", encoding="utf-8")
        (batch_dir / "latest_full.txt").write_text("@latest_777\n", encoding="utf-8")

        next_number = self.mod.next_batch_number(batch_dir)

        self.assertEqual(next_number, 6)

    def test_save_new_batch_writes_only_new_usernames(self) -> None:
        batch_dir = self.root / "chat"
        batch_dir.mkdir()
        (batch_dir / "1.txt").write_text("@known_111\n", encoding="utf-8")

        source = self.root / "source.txt"
        source.write_text("@known_111\n@new_222\n@new_333\n", encoding="utf-8")

        count, path = self.mod.save_new_batch(source, batch_dir)

        self.assertEqual(count, 2)
        self.assertEqual(path, batch_dir / "2.txt")
        self.assertEqual(path.read_text(encoding="utf-8"), "@new_222\n@new_333\n")

    def test_save_new_batch_skips_empty_delta(self) -> None:
        batch_dir = self.root / "chat"
        batch_dir.mkdir()
        (batch_dir / "1.txt").write_text("@known_111\n", encoding="utf-8")

        source = self.root / "source.txt"
        source.write_text("@known_111\n", encoding="utf-8")

        count, path = self.mod.save_new_batch(source, batch_dir)

        self.assertEqual(count, 0)
        self.assertIsNone(path)
        self.assertEqual([p.name for p in self.mod.numbered_batch_files(batch_dir)], ["1.txt"])


if __name__ == "__main__":
    unittest.main()
