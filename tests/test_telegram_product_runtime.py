from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import telegram_product_runtime as mod


DEFAULT_CONFIG_TEXT = """\
version: 1
runtime:
  root: var/site-control-kit
hub:
  host: 127.0.0.1
  port: 8765
  state_file: state/state.json
  token_file: .site-control-kit/generated_token.txt
  log_file: logs/hub.log
browser:
  profile_dir: browser-profile
  firefox_profile_dir: firefox-profile
logging:
  root_dir: logs
  runtime_events_file: logs/runtime_events.jsonl
  runtime_errors_file: logs/runtime_errors.jsonl
reports:
  root_dir: reports
telegram:
  workspace_root: telegram_workspace
  users_registry_file: registry/users.json
  api_accounts_file: registry/api_accounts.json
  managed_helper_root: managed_helper
  default_output_dir: reports/telegram_exports
"""


class ProductRuntimeTests(unittest.TestCase):
    def _make_project(self) -> Path:
        root = Path(tempfile.mkdtemp())
        (root / "config").mkdir(parents=True, exist_ok=True)
        (root / "config" / "default.yaml").write_text(DEFAULT_CONFIG_TEXT, encoding="utf-8")
        return root

    def test_create_desktop_shortcut_uses_existing_desktop_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source_file = root / "telegram-username-collector.desktop"
            source_file.write_text("[Desktop Entry]\nName=Telegram Username Collector\nExec=telegram-username-collector\n", encoding="utf-8")
            destination = root / "Desktop"
            with mock.patch.dict(
                os.environ,
                {
                    mod.PRODUCT_DESKTOP_FILE_ENV: str(source_file),
                    mod.PRODUCT_APP_ROOT_ENV: str(root / "app"),
                },
                clear=False,
            ):
                shortcut_path = mod.create_desktop_shortcut(destination=destination)
            self.assertTrue(shortcut_path.exists())
            self.assertIn("Exec=telegram-username-collector", shortcut_path.read_text(encoding="utf-8"))
            self.assertTrue(shortcut_path.stat().st_mode & stat.S_IXUSR)

    def test_gather_doctor_report_uses_explicit_helper_and_creates_token(self) -> None:
        root = self._make_project()
        helper_python = root / "helper" / "python"
        helper_python.parent.mkdir(parents=True, exist_ok=True)
        helper_python.write_text("#!/bin/sh\n", encoding="utf-8")
        helper_python.chmod(0o755)
        with mock.patch.dict(
            os.environ,
            {
                mod.PRODUCT_MODE_ENV: mod.INSTALLED_PRODUCT_MODE,
                "TELEGRAM_API_COLLECTOR_PYTHON": str(helper_python),
            },
            clear=True,
        ):
            with (
                mock.patch.object(mod, "_gtk_runtime_status", return_value="ok"),
                mock.patch.object(mod, "_hub_reachable", return_value=False),
            ):
                report = mod.gather_doctor_report(project_root=root, mutate=True)

        self.assertEqual(report.mode, mod.INSTALLED_PRODUCT_MODE)
        self.assertEqual(report.helper_source, "explicit")
        self.assertEqual(report.helper_python, helper_python)
        self.assertTrue(report.token_present)
        self.assertTrue(report.token_file.exists())
        self.assertEqual(report.overall_status, "warning")


if __name__ == "__main__":
    unittest.main()
