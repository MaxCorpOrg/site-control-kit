from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tool_platform.catalog import find_action, find_tool, load_catalog
from tool_platform.cli import execute_action
from tool_platform.gui import format_profile_details, format_workflow_details
from tool_platform.telegram_gui_helpers import (
    build_session_runtime_config,
    default_invite_job_dir,
    format_session_target_label,
    parse_plaintext_usernames,
    prepare_invite_input_file,
    session_message_targets,
)
from tool_platform.telegram_profiles import (
    adopt_existing_profile,
    format_profile_label,
    import_tdata_profile,
    list_portable_profiles,
)


class ToolPlatformCatalogTests(unittest.TestCase):
    def _write_json(self, path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def test_load_catalog_resolves_relative_and_absolute_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            embedded_dir = root / "embedded_tool"
            external_dir = root / "external_tool"
            registry_dir = root / "registry"
            embedded_dir.mkdir()
            external_dir.mkdir()
            registry_dir.mkdir()

            embedded_manifest = embedded_dir / "tool_manifest.json"
            external_manifest = external_dir / "tool_manifest.json"
            registry_path = registry_dir / "tools.json"

            self._write_json(
                embedded_manifest,
                {
                    "schema_version": 1,
                    "tool_id": "embedded_tool",
                    "display_name": "Embedded Tool",
                    "root_dir": ".",
                    "docs": [{"doc_id": "readme", "label": "README", "path": "README.md"}],
                    "actions": [
                        {
                            "action_id": "help",
                            "label": "Help",
                            "argv": ["echo", "embedded"],
                            "workdir": ".",
                        }
                    ],
                },
            )
            self._write_json(
                external_manifest,
                {
                    "schema_version": 1,
                    "tool_id": "external_tool",
                    "display_name": "External Tool",
                    "root_dir": ".",
                    "actions": [
                        {
                            "action_id": "help",
                            "label": "Help",
                            "argv": ["echo", "external"],
                            "workdir": ".",
                        }
                    ],
                },
            )
            self._write_json(
                registry_path,
                {
                    "schema_version": 1,
                    "platform_name": "Test Platform",
                    "tools": [
                        {
                            "manifest_path": "../embedded_tool/tool_manifest.json",
                            "enabled": True,
                            "source_label": "embedded",
                        },
                        {
                            "manifest_path": str(external_manifest),
                            "enabled": True,
                            "source_label": "external",
                        },
                    ],
                },
            )

            catalog = load_catalog(registry_path)

            self.assertEqual(catalog.platform_name, "Test Platform")
            self.assertEqual([tool.tool_id for tool in catalog.tools], ["embedded_tool", "external_tool"])
            embedded_tool = find_tool(catalog, "embedded_tool")
            self.assertEqual(embedded_tool.docs[0].path, embedded_dir / "README.md")
            self.assertEqual(embedded_tool.source_label, "embedded")
            external_tool = find_tool(catalog, "external_tool")
            self.assertEqual(external_tool.source_label, "external")

    def test_duplicate_tool_ids_raise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            registry_dir = root / "registry"
            registry_dir.mkdir()
            tool_a_dir = root / "tool_a"
            tool_b_dir = root / "tool_b"
            tool_a_dir.mkdir()
            tool_b_dir.mkdir()
            tool_a_manifest = tool_a_dir / "tool_manifest.json"
            tool_b_manifest = tool_b_dir / "tool_manifest.json"
            registry_path = registry_dir / "tools.json"

            manifest_payload = {
                "schema_version": 1,
                "tool_id": "duplicate_id",
                "display_name": "Duplicate",
                "root_dir": ".",
                "actions": [],
            }
            self._write_json(tool_a_manifest, manifest_payload)
            self._write_json(tool_b_manifest, manifest_payload)
            self._write_json(
                registry_path,
                {
                    "schema_version": 1,
                    "tools": [
                        {"manifest_path": str(tool_a_manifest), "enabled": True},
                        {"manifest_path": str(tool_b_manifest), "enabled": True},
                    ],
                },
            )

            with self.assertRaisesRegex(ValueError, "duplicate tool_id"):
                load_catalog(registry_path)

    def test_execute_action_dry_run_returns_preview(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            manifest_dir = root / "tool"
            registry_dir = root / "registry"
            manifest_dir.mkdir()
            registry_dir.mkdir()
            manifest_path = manifest_dir / "tool_manifest.json"
            registry_path = registry_dir / "tools.json"

            self._write_json(
                manifest_path,
                {
                    "schema_version": 1,
                    "tool_id": "sample_tool",
                    "display_name": "Sample Tool",
                    "root_dir": ".",
                    "actions": [
                        {
                            "action_id": "echo_help",
                            "label": "Echo",
                            "argv": ["echo", "hello"],
                            "workdir": ".",
                        }
                    ],
                },
            )
            self._write_json(
                registry_path,
                {
                    "schema_version": 1,
                    "tools": [{"manifest_path": str(manifest_path), "enabled": True}],
                },
            )

            catalog = load_catalog(registry_path)
            tool = find_tool(catalog, "sample_tool")
            action = find_action(tool, "echo_help")
            result = execute_action(action, dry_run=True)

            self.assertEqual(result["status"], "dry_run")
            self.assertIn("echo hello", result["command"])

    def test_format_profile_label_prefers_account_label_and_running_state(self) -> None:
        self.assertEqual(
            format_profile_label(
                {
                    "profile_name": "AK",
                    "account": {
                        "label": "@M_a_g_g_i_e",
                    },
                    "running": True,
                }
            ),
            "@M_a_g_g_i_e (AK) [запущен]",
        )

    def test_list_portable_profiles_sorts_running_first(self) -> None:
        completed = mock.Mock(
            returncode=0,
            stdout=json.dumps(
                {
                    "profiles": [
                        {"profile_name": "B", "running": False},
                        {"profile_name": "A", "running": True},
                    ]
                }
            ),
            stderr="",
        )
        with mock.patch("tool_platform.telegram_profiles.subprocess.run", return_value=completed):
            profiles = list_portable_profiles("/tmp/profiles")

        self.assertEqual([item["profile_name"] for item in profiles], ["A", "B"])

    def test_import_tdata_profile_passes_account_arguments(self) -> None:
        completed = mock.Mock(
            returncode=0,
            stdout=json.dumps({"status": "completed", "profile_dir": "/tmp/TelegramPortable-AK"}),
            stderr="",
        )
        with mock.patch("tool_platform.telegram_profiles.subprocess.run", return_value=completed) as run_mock:
            result = import_tdata_profile(
                zip_path="/tmp/ak.zip",
                output_root="/tmp",
                profile_name="AK",
                account_username="@M_a_g_g_i_e",
                account_label="Maggie",
                launch=True,
            )

        argv = run_mock.call_args.args[0]
        self.assertIn("--account-username", argv)
        self.assertIn("--account-label", argv)
        self.assertIn("--launch", argv)
        self.assertEqual(result["status"], "completed")

    def test_adopt_existing_profile_passes_optional_account_fields(self) -> None:
        completed = mock.Mock(
            returncode=0,
            stdout=json.dumps({"status": "completed", "profile_dir": "/tmp/TelegramPortableAK"}),
            stderr="",
        )
        with mock.patch("tool_platform.telegram_profiles.subprocess.run", return_value=completed) as run_mock:
            adopt_existing_profile(
                profile_dir="/tmp/TelegramPortableAK",
                profile_name="AK",
                account_username="@M_a_g_g_i_e",
                account_label="Maggie",
            )

        argv = run_mock.call_args.args[0]
        self.assertEqual(
            argv[1],
            str((Path(__file__).resolve().parents[1] / "scripts" / "telegram_portable.py")),
        )
        self.assertIn("--account-username", argv)
        self.assertIn("--account-label", argv)

    def test_format_profile_details_includes_paths_and_window(self) -> None:
        details = format_profile_details(
            {
                "profile_name": "AK",
                "running": False,
                "profile_dir": "/home/max/TelegramPortableAK",
                "tdata_dir": "/home/max/TelegramPortableAK/TelegramForcePortable/tdata",
                "metadata_path": "/home/max/TelegramPortableAK/portable-profile.json",
                "telegram_log_path": "/home/max/TelegramPortableAK/TelegramForcePortable/log.txt",
                "account": {
                    "username": "@M_a_g_g_i_e",
                    "label": "Maggie",
                },
                "pids": [],
                "windows": [{"title": "Макс Михайлов", "window_id": "0x1"}],
            }
        )

        self.assertIn("Профиль Telegram", details)
        self.assertIn("@M_a_g_g_i_e", details)
        self.assertIn("Заголовок окна: Макс Михайлов", details)
        self.assertIn("Папка профиля: /home/max/TelegramPortableAK", details)

    def test_format_workflow_details_includes_docs_and_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            manifest_dir = root / "tool"
            registry_dir = root / "registry"
            manifest_dir.mkdir()
            registry_dir.mkdir()
            manifest_path = manifest_dir / "tool_manifest.json"
            registry_path = registry_dir / "tools.json"

            self._write_json(
                manifest_path,
                {
                    "schema_version": 1,
                    "tool_id": "sample_tool",
                    "display_name": "Sample Tool",
                    "description": "Readable workflow summary",
                    "root_dir": ".",
                    "docs": [{"doc_id": "readme", "label": "README", "path": "README.md"}],
                    "actions": [
                        {
                            "action_id": "echo_help",
                            "label": "Echo",
                            "argv": ["echo", "hello"],
                            "workdir": ".",
                        }
                    ],
                    "capabilities": ["alpha", "beta"],
                    "tags": ["telegram", "demo"],
                    "artifacts": {"runs_dir": "runs"},
                },
            )
            self._write_json(
                registry_path,
                {
                    "schema_version": 1,
                    "tools": [{"manifest_path": str(manifest_path), "enabled": True}],
                },
            )

            catalog = load_catalog(registry_path)
            tool = find_tool(catalog, "sample_tool")
            details = format_workflow_details(tool)

        self.assertIn("Инструмент Telegram", details)
        self.assertIn("Readable workflow summary", details)
        self.assertIn("- README:", details)
        self.assertIn("- runs_dir: runs", details)

    def test_default_invite_job_dir_uses_chat_fragment_slug(self) -> None:
        result = default_invite_job_dir(
            "https://web.telegram.org/k/#-2465948544",
            "/tmp/telegram_invite_jobs",
        )
        self.assertEqual(str(result), "/tmp/telegram_invite_jobs/chat_-2465948544")

    def test_parse_plaintext_usernames_skips_comments_and_deduplicates(self) -> None:
        usernames = parse_plaintext_usernames(
            """
            # comment
            @Alice_test
            bob_test
            @alice_test
            """
        )
        self.assertEqual(usernames, ["@alice_test", "@bob_test"])

    def test_prepare_invite_input_file_converts_txt_into_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "users.txt"
            source.write_text("@alice_test\nbob_test\n", encoding="utf-8")

            prepared = prepare_invite_input_file(source, root / "tmp")
            rows = prepared.read_text(encoding="utf-8")

        self.assertTrue(str(prepared).endswith(".invite-import.csv"))
        self.assertIn("username,consent,source", rows)
        self.assertIn("@alice_test,yes,panel_txt_import", rows)
        self.assertIn("@bob_test,yes,panel_txt_import", rows)

    def test_session_message_targets_reads_message_policy_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "message_policy": {
                            "message_targets": [
                                {"label": "Alice", "handle": "@alice_test", "kind": "contact"}
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            targets = session_message_targets(config_path)

        self.assertEqual(targets[0]["handle"], "@alice_test")

    def test_format_session_target_label_includes_label_handle_and_kind(self) -> None:
        self.assertEqual(
            format_session_target_label(
                {"label": "Alice", "handle": "@alice_test", "kind": "contact"}
            ),
            "Alice · @alice_test · контакт",
        )

    def test_build_session_runtime_config_overrides_targets_and_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = root / "base.json"
            output = root / "runtime.json"
            base.write_text(
                json.dumps(
                    {
                        "portable_profile_dir": "/home/max/TelegramPortableAK",
                        "message_policy": {
                            "target_mode": "rotating_contacts",
                            "auto_send": False,
                            "message_targets": [
                                {"label": "Old", "handle": "@old_test", "kind": "contact"}
                            ],
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            result = build_session_runtime_config(
                base_config_path=base,
                output_path=output,
                message_targets=[
                    {"label": "Alice", "handle": "@alice_test", "kind": "contact"},
                    {"label": "Group", "handle": "@group_test", "kind": "group"},
                ],
                portable_profile_dir="/home/max/TelegramPortable-AK2",
                auto_send=True,
            )
            payload = json.loads(result.read_text(encoding="utf-8"))

        self.assertEqual(payload["portable_profile_dir"], "/home/max/TelegramPortable-AK2")
        self.assertTrue(payload["message_policy"]["auto_send"])
        self.assertEqual(payload["message_policy"]["target_mode"], "rotating_all")
        self.assertEqual(len(payload["message_policy"]["message_targets"]), 2)


if __name__ == "__main__":
    unittest.main()
