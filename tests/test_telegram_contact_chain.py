from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


def _load_chain_module():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "scripts" / "telegram_contact_chain.py"
    spec = importlib.util.spec_from_file_location("telegram_contact_chain", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TelegramContactChainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = _load_chain_module()

    def test_chat_slug_from_group_url_uses_fragment(self) -> None:
        slug = self.mod.chat_slug_from_group_url("https://web.telegram.org/k/#-2465948544")
        self.assertEqual(slug, "-2465948544")

    def test_latest_run_json_picks_newest_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            chat_dir = Path(tmpdir) / "chat"
            (chat_dir / "runs" / "20260419T100000Z").mkdir(parents=True)
            (chat_dir / "runs" / "20260419T100000Z" / "run.json").write_text("{}", encoding="utf-8")
            (chat_dir / "runs" / "20260419T110000Z").mkdir(parents=True)
            expected = chat_dir / "runs" / "20260419T110000Z" / "run.json"
            expected.write_text("{}", encoding="utf-8")

            actual = self.mod.latest_run_json(chat_dir)

        self.assertEqual(actual, expected)

    def test_should_stop_after_idle_uses_threshold(self) -> None:
        self.assertFalse(self.mod.should_stop_after_idle(1, 2))
        self.assertTrue(self.mod.should_stop_after_idle(2, 2))
        self.assertFalse(self.mod.should_stop_after_idle(5, 0))


if __name__ == "__main__":
    unittest.main()
