from __future__ import annotations

import contextlib
import io
import importlib
import unittest
from pathlib import Path
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

    def test_launcher_handles_keyboard_interrupt_without_traceback(self) -> None:
        fake_gui_app = SimpleNamespace(main=lambda: (_ for _ in ()).throw(KeyboardInterrupt()))
        stderr = io.StringIO()
        with (
            patch.object(mod, "_is_windows_platform", return_value=False),
            patch.object(importlib, "import_module", return_value=fake_gui_app),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = mod.main()

        self.assertEqual(exit_code, 130)
        self.assertIn("interrupted by user", stderr.getvalue())

    def test_launcher_applies_ui_scale_before_gui_import(self) -> None:
        fake_gui_app = SimpleNamespace(main=lambda: 0)
        with (
            patch.object(mod, "_is_windows_platform", return_value=False),
            patch.object(importlib, "import_module", return_value=fake_gui_app),
            patch.dict(mod.os.environ, {}, clear=True),
        ):
            exit_code = mod.main(["--ui-scale", "1.25"])
            self.assertEqual(mod.os.environ.get("TELEGRAM_GUI_SCALE"), "1.25")

        self.assertEqual(exit_code, 0)

    def test_launcher_rejects_invalid_ui_scale(self) -> None:
        stderr = io.StringIO()
        with (
            patch.object(mod, "_is_windows_platform", return_value=False),
            contextlib.redirect_stderr(stderr),
            self.assertRaises(SystemExit) as raised,
        ):
            mod.main(["--ui-scale", "3"])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("scale must be between 0.75 and 1.75", stderr.getvalue())

    def test_launcher_doctor_prints_report_without_importing_gui(self) -> None:
        stdout = io.StringIO()
        with (
            patch.object(mod, "_is_windows_platform", return_value=False),
            patch.object(mod, "gather_doctor_report", return_value=SimpleNamespace()),
            patch.object(mod, "format_doctor_report", return_value="overall_status=ok\n"),
            patch.object(importlib, "import_module") as import_gui,
            contextlib.redirect_stdout(stdout),
        ):
            exit_code = mod.main(["--doctor"])

        self.assertEqual(exit_code, 0)
        self.assertIn("overall_status=ok", stdout.getvalue())
        import_gui.assert_not_called()

    def test_launcher_creates_desktop_shortcut(self) -> None:
        stdout = io.StringIO()
        shortcut_path = Path("/tmp/Telegram Username Collector.desktop")
        with (
            patch.object(mod, "_is_windows_platform", return_value=False),
            patch.object(mod, "create_desktop_shortcut", return_value=shortcut_path),
            contextlib.redirect_stdout(stdout),
        ):
            exit_code = mod.main(["--create-desktop-shortcut"])

        self.assertEqual(exit_code, 0)
        self.assertIn(str(shortcut_path), stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
