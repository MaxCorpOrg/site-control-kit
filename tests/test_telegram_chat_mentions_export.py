from __future__ import annotations

import importlib.util
import tempfile
import unittest
import itertools
from pathlib import Path
from unittest.mock import patch


def _load_mentions_module():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "scripts" / "export_telegram_chat_mentions.py"
    spec = importlib.util.spec_from_file_location("telegram_chat_mentions_export", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TelegramChatMentionsExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = _load_mentions_module()

    def test_append_unique_usernames_normalizes_and_dedupes(self) -> None:
        usernames = ["@alpha"]
        added = self.mod._append_unique_usernames(usernames, ["beta", "@ALPHA", "@gamma"])
        self.assertEqual(added, 2)
        self.assertEqual(usernames, ["@alpha", "@beta", "@gamma"])

    def test_collect_chat_mentions_stops_after_target_count(self) -> None:
        class FakeExportModule:
            CHAT_SCROLL_SETTLE_SEC = 0

            @staticmethod
            def _send_get_html(**kwargs):
                return kwargs.get("selector", "")

            @staticmethod
            def _extract_chat_mention_usernames(html):
                if html == "body":
                    return ["alpha", "beta", "gamma"]
                return []

            @staticmethod
            def _scroll_chat_up(**kwargs):
                raise AssertionError("scroll should not be called after target is reached")

        with patch.object(self.mod.time, "time", side_effect=[0.0, 0.0, 0.1]):
            usernames, stats = self.mod._collect_chat_mentions(
                export_mod=FakeExportModule(),
                server="http://127.0.0.1:8765",
                token="token",
                client_id="client-1",
                tab_id=1,
                group_url="https://web.telegram.org/a/#-1002465948544",
                timeout_sec=5,
                scroll_steps=5,
                target_count=3,
                max_runtime_sec=60,
                scroll_burst=1,
                no_growth_limit=3,
            )

        self.assertEqual(usernames, ["@alpha", "@beta", "@gamma"])
        self.assertEqual(stats["scroll_steps_done"], 0)

    def test_collect_chat_mentions_uses_scroll_burst_between_reads(self) -> None:
        html_sequence = iter(["body-1", "body-2"])
        scroll_calls: list[int] = []

        class FakeExportModule:
            CHAT_SCROLL_SETTLE_SEC = 0

            @staticmethod
            def _send_get_html(**kwargs):
                return next(html_sequence)

            @staticmethod
            def _extract_chat_mention_usernames(html):
                return ["alpha"] if html == "body-1" else ["beta"]

            @staticmethod
            def _scroll_chat_up(**kwargs):
                scroll_calls.append(1)
                return True

        with patch.object(self.mod.time, "time", side_effect=itertools.count(start=0, step=0.1)):
            with patch.object(self.mod.time, "sleep", return_value=None):
                usernames, stats = self.mod._collect_chat_mentions(
                    export_mod=FakeExportModule(),
                    server="http://127.0.0.1:8765",
                    token="token",
                    client_id="client-1",
                    tab_id=1,
                    group_url="https://web.telegram.org/a/#-1002465948544",
                    timeout_sec=5,
                    scroll_steps=4,
                    target_count=2,
                    max_runtime_sec=60,
                    scroll_burst=2,
                    no_growth_limit=3,
                )

        self.assertEqual(usernames, ["@alpha", "@beta"])
        self.assertEqual(stats["scroll_steps_done"], 2)
        self.assertEqual(len(scroll_calls), 2)

    def test_write_outputs_writes_txt_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "mentions"
            outputs = self.mod._write_outputs(
                output_base=base,
                usernames=["@alpha", "@beta"],
                group_url="https://web.telegram.org/a/#-1002465948544",
                steps_done=2,
                runtime_sec=12.34,
            )

            self.assertTrue(outputs["txt"].exists())
            self.assertTrue(outputs["json"].exists())
            self.assertEqual(outputs["txt"].read_text(encoding="utf-8"), "@alpha\n@beta\n")
            json_text = outputs["json"].read_text(encoding="utf-8")
            self.assertIn('"count": 2', json_text)
            self.assertIn('"scroll_steps_done": 2', json_text)


if __name__ == "__main__":
    unittest.main()
