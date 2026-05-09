from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.telegram_gui.logging import GuiRunLogger, tail_text_file


class GuiRunLoggingTests(unittest.TestCase):
    def test_gui_run_logger_writes_run_events_summary_and_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            logger = GuiRunLogger(workspace_root=workspace)
            events_path = logger.append_run_event(
                "run-1",
                event="run_start",
                profile="TG_CONTACT 4",
                chat_ref="-1001",
                chat_title="ROST FARMA",
                status="running",
                message="started",
            )
            summary_path = logger.write_summary("run-1", {"status": "done", "chat_title": "ROST FARMA"})
            artifacts_path = logger.write_artifacts("run-1", {"markdown": "/tmp/export.md"})

            event_rows = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
            summary_text = summary_path.read_text(encoding="utf-8")
            artifacts_text = artifacts_path.read_text(encoding="utf-8")

        self.assertEqual(events_path.name, "events.jsonl")
        self.assertEqual(event_rows[0]["chat_title"], "ROST FARMA")
        self.assertEqual(summary_path.name, "summary.json")
        self.assertEqual(artifacts_path.name, "artifacts.json")
        self.assertIn("ROST FARMA", summary_text)
        self.assertIn("export.md", artifacts_text)

    def test_tail_text_file_returns_last_lines(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "run.log"
            path.write_text("1\n2\n3\n4\n", encoding="utf-8")

            tail = tail_text_file(path, max_lines=2)

        self.assertEqual(tail, "3\n4")


if __name__ == "__main__":
    unittest.main()
