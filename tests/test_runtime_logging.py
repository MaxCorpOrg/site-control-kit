from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from webcontrol.runtime_logging import RuntimeEventLogger


class RuntimeLoggingTests(unittest.TestCase):
    def test_runtime_logger_writes_event_and_error_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            logger = RuntimeEventLogger(
                events_path=root / "runtime_events.jsonl",
                errors_path=root / "runtime_errors.jsonl",
            )
            logger.log_event(component="hub", event="server_started", status="running", message="started")
            logger.log_exception(
                component="hub",
                event="server_crashed",
                exc=RuntimeError("boom"),
                message="crashed",
            )

            event_lines = (root / "runtime_events.jsonl").read_text(encoding="utf-8").splitlines()
            error_lines = (root / "runtime_errors.jsonl").read_text(encoding="utf-8").splitlines()

        self.assertEqual(len(event_lines), 2)
        self.assertEqual(len(error_lines), 1)
        crash_payload = json.loads(error_lines[0])
        self.assertEqual(crash_payload["component"], "hub")
        self.assertEqual(crash_payload["event"], "server_crashed")
        self.assertEqual(crash_payload["details"]["error_type"], "RuntimeError")
        self.assertIn("RuntimeError: boom", crash_payload["details"]["traceback"])


if __name__ == "__main__":
    unittest.main()
