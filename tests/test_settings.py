from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from webcontrol import settings as mod


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


class RuntimeSettingsTests(unittest.TestCase):
    def _make_project(self) -> Path:
        root = Path(tempfile.mkdtemp())
        (root / "config").mkdir(parents=True, exist_ok=True)
        (root / "config" / "default.yaml").write_text(DEFAULT_CONFIG_TEXT, encoding="utf-8")
        return root

    def test_project_local_defaults(self) -> None:
        root = self._make_project()
        with mock.patch.dict(os.environ, {}, clear=True):
            settings = mod.load_runtime_settings(project_root=root, mutate=False)

        self.assertEqual(settings.runtime_root, root / "var" / "site-control-kit")
        self.assertEqual(settings.hub_state_file, root / "var" / "site-control-kit" / "state" / "state.json")
        self.assertEqual(settings.logs_root, root / "var" / "site-control-kit" / "logs")
        self.assertEqual(settings.reports_root, root / "var" / "site-control-kit" / "reports")
        self.assertEqual(
            settings.runtime_events_log_file,
            root / "var" / "site-control-kit" / "logs" / "runtime_events.jsonl",
        )
        self.assertEqual(
            settings.runtime_errors_log_file,
            root / "var" / "site-control-kit" / "logs" / "runtime_errors.jsonl",
        )
        self.assertEqual(settings.telegram_workspace_root, root / "var" / "site-control-kit" / "telegram_workspace")
        self.assertEqual(settings.telegram_default_output_dir, root / "var" / "site-control-kit" / "reports" / "telegram_exports")
        self.assertEqual(settings.hub_token_file, root / ".site-control-kit" / "generated_token.txt")

    def test_runtime_override_from_env_wins(self) -> None:
        root = self._make_project()
        custom_runtime = root / "custom-runtime"
        with mock.patch.dict(os.environ, {"SITECTL_RUNTIME_ROOT": str(custom_runtime)}, clear=True):
            settings = mod.load_runtime_settings(project_root=root, mutate=False)

        self.assertEqual(settings.runtime_root, custom_runtime)
        self.assertEqual(settings.hub_state_file, custom_runtime / "state" / "state.json")
        self.assertEqual(settings.telegram_workspace_root, custom_runtime / "telegram_workspace")

    def test_generates_legacy_local_config_pointer(self) -> None:
        root = self._make_project()
        fake_home = Path(tempfile.mkdtemp())
        legacy_root = fake_home / ".site-control-kit"
        (legacy_root / "telegram_workspace").mkdir(parents=True, exist_ok=True)
        (legacy_root / "state.json").write_text("{}", encoding="utf-8")

        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(mod.Path, "home", return_value=fake_home):
                settings = mod.load_runtime_settings(project_root=root, mutate=True)

        self.assertTrue(settings.local_config_path.exists())
        self.assertTrue(settings.local_config_generated)
        self.assertEqual(settings.runtime_root, legacy_root)
        self.assertEqual(settings.hub_state_file, legacy_root / "state.json")
        self.assertEqual(settings.telegram_workspace_root, legacy_root / "telegram_workspace")

    def test_resolve_hub_token_generates_file(self) -> None:
        root = self._make_project()
        with mock.patch.dict(os.environ, {}, clear=True):
            settings = mod.load_runtime_settings(project_root=root, mutate=True)
            token = mod.resolve_hub_token(settings, mutate=True)

        self.assertTrue(token.startswith("sitectl-"))
        self.assertEqual(settings.hub_token_file.read_text(encoding="utf-8").strip(), token)

    def test_mutate_creates_runtime_directories(self) -> None:
        root = self._make_project()
        with mock.patch.dict(os.environ, {}, clear=True):
            settings = mod.load_runtime_settings(project_root=root, mutate=True)

        self.assertTrue(settings.logs_root.is_dir())
        self.assertTrue(settings.reports_root.is_dir())
        self.assertTrue(settings.telegram_workspace_root.is_dir())
        self.assertTrue(settings.runtime_events_log_file.parent.is_dir())
        self.assertTrue(settings.runtime_errors_log_file.parent.is_dir())

    def test_format_runtime_env_shell(self) -> None:
        root = self._make_project()
        with mock.patch.dict(os.environ, {}, clear=True):
            settings = mod.load_runtime_settings(project_root=root, mutate=False)
            rendered = mod.format_runtime_env(settings, token="abc123", shell="shell")

        self.assertIn("export SITECTL_RUNTIME_ROOT=", rendered)
        self.assertIn("export SITECTL_RUNTIME_EVENTS_LOG=", rendered)
        self.assertIn("export SITECTL_RUNTIME_ERRORS_LOG=", rendered)
        self.assertIn("export SITECTL_TOKEN=abc123", rendered)

    def test_format_runtime_env_json_includes_token_source_and_paths(self) -> None:
        root = self._make_project()
        with mock.patch.dict(os.environ, {}, clear=True):
            settings = mod.load_runtime_settings(project_root=root, mutate=False)
            rendered = mod.format_runtime_env(
                settings,
                token="abc123",
                token_source="token_file",
                shell="json",
            )

        payload = json.loads(rendered)
        self.assertEqual(payload["SITECTL_TOKEN_SOURCE"], "token_file")
        self.assertEqual(payload["SITECTL_TOKEN_FILE"], str(root / ".site-control-kit" / "generated_token.txt"))
        self.assertEqual(payload["SITECTL_RUNTIME_MODE"], "project-local")

    def test_resolve_hub_token_with_source_reports_missing_when_not_created(self) -> None:
        root = self._make_project()
        with mock.patch.dict(os.environ, {}, clear=True):
            settings = mod.load_runtime_settings(project_root=root, mutate=False)
            token, source = mod.resolve_hub_token_with_source(settings, mutate=False)

        self.assertEqual(token, "")
        self.assertEqual(source, "missing")


if __name__ == "__main__":
    unittest.main()
