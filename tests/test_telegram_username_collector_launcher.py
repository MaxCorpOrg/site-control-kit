from __future__ import annotations

import contextlib
import io
import importlib
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scripts import telegram_username_collector_launcher as mod


class TelegramUsernameCollectorLauncherTests(unittest.TestCase):
    def test_launcher_fast_fails_on_windows(self) -> None:
        stderr = io.StringIO()
        with (
            patch.object(mod, "_is_windows_platform", return_value=True),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = mod.main()

        self.assertEqual(exit_code, 2)
        self.assertIn("supported only on Linux", stderr.getvalue())

    def test_launcher_prints_gtk_doctor_hint_when_import_fails(self) -> None:
        stderr = io.StringIO()
        with (
            patch.object(mod, "_is_windows_platform", return_value=False),
            patch.object(importlib, "import_module", side_effect=ModuleNotFoundError("No module named 'gi'")),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = mod.main()

        self.assertEqual(exit_code, 2)
        self.assertIn("bootstrap_telegram_workstation.sh --doctor", stderr.getvalue())

    def test_launcher_runs_gui_main_when_available(self) -> None:
        fake_gui_app = SimpleNamespace(main=lambda: 7)
        with (
            patch.object(mod, "_is_windows_platform", return_value=False),
            patch.object(importlib, "import_module", return_value=fake_gui_app),
        ):
            exit_code = mod.main()

        self.assertEqual(exit_code, 7)


if __name__ == "__main__":
    unittest.main()
