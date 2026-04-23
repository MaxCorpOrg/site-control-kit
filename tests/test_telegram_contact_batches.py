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

        count, path, review_count, review_path, safe_md, safe_txt, safe_count = self.mod.save_new_batch(source, batch_dir)

        self.assertEqual(count, 2)
        self.assertEqual(path, batch_dir / "2.txt")
        self.assertEqual(review_count, 0)
        self.assertIsNone(review_path)
        self.assertIsNone(safe_md)
        self.assertIsNone(safe_txt)
        self.assertEqual(safe_count, 0)
        self.assertEqual(path.read_text(encoding="utf-8"), "@new_222\n@new_333\n")

    def test_save_new_batch_skips_empty_delta(self) -> None:
        batch_dir = self.root / "chat"
        batch_dir.mkdir()
        (batch_dir / "1.txt").write_text("@known_111\n", encoding="utf-8")

        source = self.root / "source.txt"
        source.write_text("@known_111\n", encoding="utf-8")

        count, path, review_count, review_path, safe_md, safe_txt, safe_count = self.mod.save_new_batch(source, batch_dir)

        self.assertEqual(count, 0)
        self.assertIsNone(path)
        self.assertEqual(review_count, 0)
        self.assertIsNone(review_path)
        self.assertIsNone(safe_md)
        self.assertIsNone(safe_txt)
        self.assertEqual(safe_count, 0)
        self.assertEqual([p.name for p in self.mod.numbered_batch_files(batch_dir)], ["1.txt"])

    def test_load_member_records_from_markdown_reads_username_and_peer(self) -> None:
        report = self.root / "latest_full.md"
        report.write_text(
            "# Report\n\n"
            "| # | Имя | Username | Статус | Роль | Peer ID |\n"
            "|---|---|---|---|---|---|\n"
            "| 1 | Alice | @Alice_111 | — | — | 111 |\n"
            "| 2 | Bob | — | — | — | 222 |\n",
            encoding="utf-8",
        )

        rows = self.mod.load_member_records_from_markdown(report)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].peer_id, "111")
        self.assertEqual(rows[0].name, "Alice")
        self.assertEqual(rows[0].username, "@alice_111")

    def test_load_markdown_member_rows_keeps_status_and_role(self) -> None:
        report = self.root / "latest_full.md"
        report.write_text(
            "# Report\n\n"
            "| # | Имя | Username | Статус | Роль | Peer ID |\n"
            "|---|---|---|---|---|---|\n"
            "| 1 | Alice | @Alice_111 | online | admin | 111 |\n",
            encoding="utf-8",
        )

        rows = self.mod.load_markdown_member_rows(report)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].status, "online")
        self.assertEqual(rows[0].role, "admin")

    def test_summarize_markdown_snapshot_counts_rows_and_unique_usernames(self) -> None:
        report = self.root / "latest_full.md"
        report.write_text(
            "# Report\n\n"
            "| # | Имя | Username | Статус | Роль | Peer ID |\n"
            "|---|---|---|---|---|---|\n"
            "| 1 | Alice | @Alice_111 | online | admin | 111 |\n"
            "| 2 | Bob | @Alice_111 | — | — | 222 |\n"
            "| 3 | Carol | — | — | — | 333 |\n",
            encoding="utf-8",
        )

        summary = self.mod.summarize_markdown_snapshot(report)

        self.assertEqual(summary["total_rows"], 3)
        self.assertEqual(summary["rows_with_username"], 2)
        self.assertEqual(summary["unique_usernames"], 1)
        self.assertEqual(summary["duplicate_username_rows"], 1)

    def test_should_promote_snapshot_rejects_degradation(self) -> None:
        current = {"total_rows": 12, "rows_with_username": 7, "unique_usernames": 7, "duplicate_username_rows": 0}
        candidate = {"total_rows": 9, "rows_with_username": 2, "unique_usernames": 2, "duplicate_username_rows": 0}

        self.assertFalse(self.mod.should_promote_snapshot(candidate, current))
        self.assertTrue(self.mod.should_promote_snapshot(current, candidate))

    def test_should_promote_snapshot_prefers_fewer_duplicates_for_same_unique_count(self) -> None:
        candidate = {"total_rows": 13, "rows_with_username": 7, "unique_usernames": 7, "duplicate_username_rows": 0}
        current = {"total_rows": 12, "rows_with_username": 9, "unique_usernames": 7, "duplicate_username_rows": 2}

        self.assertTrue(self.mod.should_promote_snapshot(candidate, current))

    def test_select_best_snapshot_prefers_cleaner_candidate(self) -> None:
        first = self.root / "first.md"
        first.write_text(
            "# Report\n\n"
            "| # | Имя | Username | Статус | Роль | Peer ID |\n"
            "|---|---|---|---|---|---|\n"
            "| 1 | Alice | @alice_111 | — | — | 111 |\n"
            "| 2 | Bob | @alice_111 | — | — | 222 |\n",
            encoding="utf-8",
        )
        second = self.root / "second.md"
        second.write_text(
            "# Report\n\n"
            "| # | Имя | Username | Статус | Роль | Peer ID |\n"
            "|---|---|---|---|---|---|\n"
            "| 1 | Alice | @alice_111 | — | — | 111 |\n"
            "| 2 | Bob | @bob_222 | — | — | 222 |\n",
            encoding="utf-8",
        )

        best_path, best_summary = self.mod.select_best_snapshot([first, second])

        self.assertEqual(best_path, second)
        self.assertEqual(best_summary["unique_usernames"], 2)
        self.assertEqual(best_summary["duplicate_username_rows"], 0)

    def test_save_new_batch_quarantines_conflicting_identity(self) -> None:
        batch_dir = self.root / "chat"
        batch_dir.mkdir()

        first_source = self.root / "first_source.txt"
        first_source.write_text("@alice_111\n", encoding="utf-8")
        first_md = self.root / "first_latest_full.md"
        first_md.write_text(
            "# Report\n\n"
            "| # | Имя | Username | Статус | Роль | Peer ID |\n"
            "|---|---|---|---|---|---|\n"
            "| 1 | Alice | @alice_111 | — | — | 111 |\n",
            encoding="utf-8",
        )

        count, path, review_count, review_path, safe_md, safe_txt, safe_count = self.mod.save_new_batch(first_source, batch_dir, first_md)
        self.assertEqual(count, 1)
        self.assertEqual(path, batch_dir / "1.txt")
        self.assertEqual(review_count, 0)
        self.assertIsNone(review_path)
        self.assertEqual(safe_count, 1)
        self.assertEqual(safe_md, batch_dir / "latest_safe.md")
        self.assertEqual(safe_txt, batch_dir / "latest_safe.txt")
        self.assertEqual(safe_txt.read_text(encoding="utf-8"), "@alice_111\n")

        second_source = self.root / "second_source.txt"
        second_source.write_text("@alice_111\n@bob_222\n", encoding="utf-8")
        second_md = self.root / "second_latest_full.md"
        second_md.write_text(
            "# Report\n\n"
            "| # | Имя | Username | Статус | Роль | Peer ID |\n"
            "|---|---|---|---|---|---|\n"
            "| 1 | Bob | @alice_111 | — | — | 222 |\n"
            "| 2 | Carol | @bob_222 | — | — | 333 |\n",
            encoding="utf-8",
        )

        count, path, review_count, review_path, safe_md, safe_txt, safe_count = self.mod.save_new_batch(second_source, batch_dir, second_md)

        self.assertEqual(count, 1)
        self.assertEqual(path, batch_dir / "2.txt")
        self.assertEqual(path.read_text(encoding="utf-8"), "@bob_222\n")
        self.assertEqual(review_count, 1)
        self.assertEqual(review_path, batch_dir / "review.txt")
        self.assertEqual(safe_count, 1)
        self.assertEqual(safe_md, batch_dir / "latest_safe.md")
        self.assertEqual(safe_txt, batch_dir / "latest_safe.txt")
        self.assertEqual(safe_txt.read_text(encoding="utf-8"), "@bob_222\n")
        self.assertIn("@bob_222", safe_md.read_text(encoding="utf-8"))
        self.assertNotIn("@alice_111", safe_md.read_text(encoding="utf-8"))
        self.assertIn("username_changed_owner", review_path.read_text(encoding="utf-8"))

        conflicts_json = batch_dir / "conflicts.json"
        self.assertTrue(conflicts_json.exists())
        self.assertIn("@alice_111", conflicts_json.read_text(encoding="utf-8"))

    def test_save_new_batch_accepts_username_change_for_same_peer(self) -> None:
        batch_dir = self.root / "chat"
        batch_dir.mkdir()

        first_source = self.root / "first_source.txt"
        first_source.write_text("@abuzayd06\n", encoding="utf-8")
        first_md = self.root / "first_latest_full.md"
        first_md.write_text(
            "# Report\n\n"
            "| # | Имя | Username | Статус | Роль | Peer ID |\n"
            "|---|---|---|---|---|---|\n"
            "| 1 | Teimur | @abuzayd06 | — | — | 555101371 |\n",
            encoding="utf-8",
        )

        count, path, review_count, review_path, safe_md, safe_txt, safe_count = self.mod.save_new_batch(first_source, batch_dir, first_md)
        self.assertEqual(count, 1)
        self.assertEqual(path, batch_dir / "1.txt")
        self.assertEqual(review_count, 0)
        self.assertIsNone(review_path)
        self.assertEqual(safe_count, 1)
        self.assertEqual(safe_txt.read_text(encoding="utf-8"), "@abuzayd06\n")

        second_source = self.root / "second_source.txt"
        second_source.write_text("@teimur_92\n", encoding="utf-8")
        second_md = self.root / "second_latest_full.md"
        second_md.write_text(
            "# Report\n\n"
            "| # | Имя | Username | Статус | Роль | Peer ID |\n"
            "|---|---|---|---|---|---|\n"
            "| 1 | Teimur | @teimur_92 | — | — | 555101371 |\n",
            encoding="utf-8",
        )

        count, path, review_count, review_path, safe_md, safe_txt, safe_count = self.mod.save_new_batch(second_source, batch_dir, second_md)

        self.assertEqual(count, 1)
        self.assertEqual(path, batch_dir / "2.txt")
        self.assertEqual(path.read_text(encoding="utf-8"), "@teimur_92\n")
        self.assertEqual(review_count, 0)
        self.assertIsNone(review_path)
        self.assertEqual(safe_count, 1)
        self.assertEqual(safe_txt, batch_dir / "latest_safe.txt")
        self.assertEqual(safe_txt.read_text(encoding="utf-8"), "@teimur_92\n")
        self.assertIn("@teimur_92", safe_md.read_text(encoding="utf-8"))

        history = self.mod.load_history(batch_dir)
        self.assertEqual(history["peer_to_username"]["555101371"], "@teimur_92")
        self.assertEqual(history["username_to_peer"]["@teimur_92"], "555101371")
        self.assertNotIn("@abuzayd06", history["username_to_peer"])


if __name__ == "__main__":
    unittest.main()
