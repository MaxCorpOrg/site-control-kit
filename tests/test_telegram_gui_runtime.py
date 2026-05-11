from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from scripts.telegram_gui import runtime as mod


class GuiRuntimePathsTests(unittest.TestCase):
    def test_installed_mode_moves_artifact_index_into_runtime_reports(self) -> None:
        settings = SimpleNamespace(
            project_root=Path("/opt/telegram-username-collector/app"),
            telegram_workspace_root=Path("/home/test/.local/share/site-control-kit/telegram_workspace"),
            telegram_users_registry_file=Path("/home/test/.local/share/site-control-kit/telegram_workspace/registry/users.json"),
            browser_profile_dir=Path("/home/test/.local/share/site-control-kit/browser-profile"),
            telegram_default_output_dir=Path("/home/test/.local/share/site-control-kit/reports/telegram_exports"),
            telegram_managed_helper_root=Path("/home/test/.local/share/site-control-kit/telegram_workspace/managed_helper"),
            runtime_events_log_file=Path("/home/test/.local/state/site-control-kit/logs/runtime_events.jsonl"),
            runtime_errors_log_file=Path("/home/test/.local/state/site-control-kit/logs/runtime_errors.jsonl"),
            server_url="http://127.0.0.1:8765",
        )
        product_paths = SimpleNamespace(
            installed_mode=True,
            mode="installed",
            extension_dir=Path("/opt/telegram-username-collector/app/extension"),
            extension_zip_path=Path("/opt/telegram-username-collector/app/resources/site-control-bridge-extension.zip"),
            desktop_file=Path("/usr/share/applications/telegram-username-collector.desktop"),
            icon_path=Path("/usr/share/icons/hicolor/256x256/apps/telegram-username-collector.png"),
        )
        with (
            mock.patch.object(mod, "load_runtime_settings", return_value=settings),
            mock.patch.object(mod, "resolve_product_paths", return_value=product_paths),
            mock.patch.object(mod, "venv_python_path", return_value=Path("/home/test/.local/share/site-control-kit/telegram_workspace/managed_helper/.venv/bin/python")),
        ):
            paths = mod.load_gui_runtime_paths(mutate=False)

        self.assertEqual(paths.artifact_index_path, settings.telegram_default_output_dir / "INDEX.md")
        self.assertEqual(paths.extension_dir, product_paths.extension_dir)
        self.assertEqual(paths.extension_zip_path, product_paths.extension_zip_path)
        self.assertEqual(paths.product_mode, "installed")


if __name__ == "__main__":
    unittest.main()
