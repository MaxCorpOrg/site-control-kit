from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from scripts.telegram_gui.services.process_runner import ProcessRunner, TaskController


class ProcessRunnerTests(unittest.TestCase):
    def test_cancel_notifies_even_when_process_exits_quickly_after_sigterm(self) -> None:
        runner = ProcessRunner()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            helper = root / "cancel_helper.py"
            helper.write_text(
                "\n".join(
                    [
                        "import json, signal, sys, time",
                        "stop = False",
                        "def handler(*_args):",
                        "    global stop",
                        "    stop = True",
                        "signal.signal(signal.SIGTERM, handler)",
                        "if hasattr(signal, 'SIGBREAK'):",
                        "    signal.signal(signal.SIGBREAK, handler)",
                        "print('PROGRESS chat=x messages=0 usernames=0 stage=start', file=sys.stderr, flush=True)",
                        "while not stop:",
                        "    time.sleep(0.05)",
                        "print(json.dumps({'ok': True, 'interrupted': True}), flush=True)",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            controller = TaskController()
            notices: list[str] = []
            result_box: dict[str, object] = {}

            def worker() -> None:
                result_box["result"] = runner.run(
                    [sys.executable, str(helper)],
                    cwd=str(root),
                    timeout_sec=5,
                    controller=controller,
                    emit_stderr=notices.append,
                    on_cancel_begin=lambda: notices.append("cancel-begin"),
                )

            thread = threading.Thread(target=worker)
            thread.start()
            time.sleep(0.2)
            controller.request_cancel()
            thread.join(timeout=5)

        self.assertFalse(thread.is_alive())
        result = result_box.get("result")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(any(line == "cancel-begin" for line in notices))
        self.assertTrue(result.cancel_requested)
        if os.name == "nt":
            self.assertTrue(result.return_code != 0 or result.forced_cancel or '"interrupted": true' in result.stdout)
        else:
            self.assertFalse(result.forced_cancel)
            self.assertIn('"interrupted": true', result.stdout)
