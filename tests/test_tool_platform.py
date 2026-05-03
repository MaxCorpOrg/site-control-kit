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
    active_profile_conflict,
    build_session_runtime_config,
    combined_flow_state_path,
    contact_job_snapshot,
    contact_add_batch_command,
    default_combined_flow_state,
    default_invite_job_dir,
    default_contact_add_job_dir,
    format_session_target_label,
    invite_manager_init_command,
    load_combined_flow_state,
    parse_plaintext_usernames,
    preview_invite_input_file,
    prepare_invite_input_file,
    save_combined_flow_state,
    session_config_defaults,
    session_history_snapshot,
    session_plan_command,
    session_message_targets,
    session_run_command,
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

    def test_default_contact_add_job_dir_uses_profile_and_filename(self) -> None:
        result = default_contact_add_job_dir(
            profile_name="AK",
            input_path="/tmp/users.txt",
            output_root="/tmp/telegram_invite_jobs",
        )
        self.assertEqual(str(result), "/tmp/telegram_invite_jobs/contact_add__AK__users")

    def test_combined_flow_state_roundtrip_preserves_phase_and_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = combined_flow_state_path(
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                state_root=tmp_dir,
            )
            save_combined_flow_state(
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                state_root=tmp_dir,
                payload={
                    "phase": "session_ready",
                    "input_path": "/tmp/users.txt",
                    "invite_job_dir": "/tmp/job",
                    "last_status": "completed",
                },
            )
            state = load_combined_flow_state(
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                state_root=tmp_dir,
            )
            exists_before_cleanup = state_path.exists()

        self.assertTrue(exists_before_cleanup)
        self.assertEqual(state["phase"], "session_ready")
        self.assertEqual(state["input_path"], "/tmp/users.txt")
        self.assertEqual(state["invite_job_dir"], "/tmp/job")
        self.assertEqual(state["last_status"], "completed")

    def test_default_combined_flow_state_starts_in_contact_add_phase(self) -> None:
        state = default_combined_flow_state("AK", "/home/max/TelegramPortableAK")
        self.assertEqual(state["phase"], "contact_add")
        self.assertEqual(state["last_status"], "idle")

    def test_active_profile_conflict_detects_same_running_profile(self) -> None:
        conflict = active_profile_conflict(
            {
                "telegram_invite_manager": "/home/max/TelegramPortableAK",
                "telegram_session_runner": "/home/max/TelegramPortableAK2",
            },
            "/home/max/TelegramPortableAK",
            current_tool_id="telegram_combined_flow",
        )
        self.assertEqual(conflict, ("telegram_invite_manager", "/home/max/TelegramPortableAK"))

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

    def test_preview_invite_input_file_counts_duplicates_and_invalid_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "users.txt"
            source.write_text("@alice_test\nbob_test\nbad!\n@alice_test\n", encoding="utf-8")

            preview = preview_invite_input_file(source)

        self.assertEqual(preview["unique_usernames"], 2)
        self.assertEqual(preview["duplicates"], 1)
        self.assertEqual(preview["invalid_count"], 1)
        self.assertEqual(preview["usernames"], ["@alice_test", "@bob_test"])

    def test_invite_manager_init_command_uses_converted_txt_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "users.txt"
            source.write_text("@alice_test\n", encoding="utf-8")

            spec = invite_manager_init_command(
                chat_url="https://web.telegram.org/k/#-2465948544",
                input_path=source,
                job_dir=root / "job",
                output_root=root / "jobs",
                temp_dir=root / "tmp",
            )

        self.assertIn("init", spec.argv)
        self.assertIn("--input", spec.argv)
        input_index = spec.argv.index("--input") + 1
        self.assertTrue(spec.argv[input_index].endswith(".invite-import.csv"))
        self.assertEqual(spec.cwd, Path(__file__).resolve().parents[1])

    def test_contact_add_batch_command_targets_executor_and_selected_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "users.txt"
            source.write_text("@alice_test\n", encoding="utf-8")

            spec = contact_add_batch_command(
                input_path=source,
                job_dir=root / "job",
                profile_name="AK",
                portable_profile_dir="/home/max/TelegramPortableAK",
                account_username="@M_a_g_g_i_e",
                account_label="Maggie",
                limit=5,
                output_root=root / "jobs",
                temp_dir=root / "tmp",
            )

        self.assertIn("desktop-add-contact-batch", spec.argv)
        self.assertIn("--portable-profile-name", spec.argv)
        self.assertIn("AK", spec.argv)
        self.assertIn("--portable-profile-dir", spec.argv)
        self.assertIn("/home/max/TelegramPortableAK", spec.argv)
        self.assertIn("--confirm-add", spec.argv)
        self.assertIn("--launch-if-needed", spec.argv)
        self.assertEqual(spec.cwd, Path(__file__).resolve().parents[1])

    def test_contact_add_batch_command_can_continue_existing_job_without_input(self) -> None:
        spec = contact_add_batch_command(
            input_path=None,
            job_dir="/tmp/job",
            profile_name="AK",
            portable_profile_dir="/home/max/TelegramPortableAK",
            statuses=["failed"],
        )

        self.assertIn("desktop-add-contact-batch", spec.argv)
        self.assertNotIn("--input", spec.argv)
        self.assertIn("--statuses", spec.argv)
        self.assertIn("failed", spec.argv)

    def test_contact_job_snapshot_reads_state_and_latest_batch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            job_dir = Path(tmp_dir) / "job"
            executions_dir = job_dir / "executions" / "20260503T100000Z"
            executions_dir.mkdir(parents=True)
            (job_dir / "invite_state.json").write_text(
                json.dumps(
                    {
                        "chat_url": "contacts://maggie",
                        "source_file": "/tmp/users.txt",
                        "updated_at": "2026-05-03T10:00:00Z",
                        "users": [
                            {"username": "@alice_test", "status": "new", "attempts": 0},
                            {
                                "username": "@bob_test",
                                "status": "failed",
                                "attempts": 2,
                                "last_attempt_at": "2026-05-03T10:00:00Z",
                                "history": [{"reason": "desktop_contact_batch_failed"}],
                            },
                            {"username": "@carol_test", "status": "contact_added", "attempts": 1},
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (executions_dir / "batch_contact_add.json").write_text(
                json.dumps(
                    {
                        "execution_id": "20260503T100000Z",
                        "status": "completed_with_errors",
                        "added_count": 1,
                        "already_present_count": 1,
                        "failed_count": 1,
                        "remaining_candidates": 1,
                        "selected_users": 2,
                        "results": [
                            {"username": "@bob_test", "status": "failed", "error": "button not found"}
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            snapshot = contact_job_snapshot(job_dir)

        self.assertEqual(snapshot["pending_total"], 1)
        self.assertEqual(snapshot["added_total"], 1)
        self.assertEqual(snapshot["failed_total"], 1)
        self.assertEqual(snapshot["pending_usernames"], ["@alice_test"])
        self.assertEqual(snapshot["latest_errors"][0]["username"], "@bob_test")
        self.assertEqual(snapshot["latest_runs"][0]["execution_id"], "20260503T100000Z")
        self.assertEqual(snapshot["latest_runs"][0]["already_present_count"], 1)

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

    def test_session_config_defaults_reads_templates_and_limits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "message_policy": {
                            "auto_send": True,
                            "drafts_per_run": 3,
                            "total_message_limit": 9,
                            "templates": ["Привет", "Как дела?"],
                            "message_targets": [
                                {"label": "Alice", "handle": "@alice_test", "kind": "contact"}
                            ],
                        }
                    }
                ),
                encoding="utf-8",
            )

            defaults = session_config_defaults(config_path)

        self.assertTrue(defaults["auto_send"])
        self.assertEqual(defaults["drafts_per_run"], 3)
        self.assertEqual(defaults["total_message_limit"], 9)
        self.assertEqual(defaults["templates"], ["Привет", "Как дела?"])
        self.assertEqual(defaults["message_targets"][0]["handle"], "@alice_test")
        self.assertEqual(defaults["random_walk_visits_per_run"], 6)
        self.assertEqual(defaults["view_min_seconds"], 3)
        self.assertEqual(defaults["view_max_seconds"], 6)

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
                        "session": {
                            "random_walk_visits_per_run": 6,
                            "view_min_seconds": 3,
                            "view_max_seconds": 6,
                        },
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
                message_templates=["Привет", "Как дела?"],
                drafts_per_run=4,
                total_message_limit=7,
                portable_profile_dir="/home/max/TelegramPortable-AK2",
                auto_send=True,
                session_overrides={
                    "random_walk_visits_per_run": 9,
                    "view_min_seconds": 4,
                    "view_max_seconds": 8,
                },
            )
            payload = json.loads(result.read_text(encoding="utf-8"))

        self.assertEqual(payload["portable_profile_dir"], "/home/max/TelegramPortable-AK2")
        self.assertTrue(payload["message_policy"]["auto_send"])
        self.assertEqual(payload["message_policy"]["target_mode"], "rotating_all")
        self.assertEqual(payload["message_policy"]["drafts_per_run"], 4)
        self.assertEqual(payload["message_policy"]["total_message_limit"], 7)
        self.assertEqual(payload["message_policy"]["templates"], ["Привет", "Как дела?"])
        self.assertEqual(payload["message_policy"]["target_username"], "")
        self.assertEqual(len(payload["message_policy"]["message_targets"]), 2)
        self.assertEqual(payload["session"]["random_walk_visits_per_run"], 9)
        self.assertEqual(payload["session"]["view_min_seconds"], 4)
        self.assertEqual(payload["session"]["view_max_seconds"], 8)

    def test_session_history_snapshot_reads_state_and_run_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            state_file = root / "session_state.json"
            runs_dir = root / "runs" / "20260503T100000Z-aaaa"
            runs_dir.mkdir(parents=True)
            state_file.write_text(
                json.dumps(
                    {
                        "messages_sent_total": 3,
                        "message_cursor": 2,
                        "message_target_cursor": 1,
                        "history": [
                            {
                                "run_id": "20260503T100000Z-aaaa",
                                "visit_count": 4,
                                "sent_count": 1,
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (runs_dir / "run.json").write_text(
                json.dumps(
                    {
                        "run_id": "20260503T100000Z-aaaa",
                        "status": "completed",
                        "visits": [{}, {}],
                        "sent_count": 1,
                        "plan": {"message_target_username": "@alice_test"},
                        "messages": [
                            {"index": 1, "text": "Привет", "sent": True},
                            {"index": 2, "text": "Напомни", "sent": False},
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            snapshot = session_history_snapshot(state_file=state_file, runs_dir=root / "runs")

        self.assertEqual(snapshot["messages_sent_total"], 3)
        self.assertEqual(snapshot["last_run"]["run_id"], "20260503T100000Z-aaaa")
        self.assertEqual(snapshot["last_run"]["sent_count"], 1)
        self.assertEqual(snapshot["last_run"]["unsent_messages"][0]["text"], "Напомни")

    def test_session_plan_command_targets_standalone_cli(self) -> None:
        spec = session_plan_command(config_path="/tmp/runtime.json", state_file="/tmp/state.json")
        self.assertEqual(spec.argv[:4], ["python3", "-m", "telegram_portable_session_tool.cli", "plan-session"])
        self.assertEqual(spec.cwd, Path("/home/max/telegram-portable-session-tool"))

    def test_session_run_command_adds_execute_and_auto_send_flags(self) -> None:
        spec = session_run_command(
            config_path="/tmp/runtime.json",
            state_file="/tmp/state.json",
            runs_dir="/tmp/runs",
            auto_send=True,
            launch_if_needed=True,
            continuous=True,
        )
        self.assertIn("--execute", spec.argv)
        self.assertIn("--launch-if-needed", spec.argv)
        self.assertIn("--auto-send", spec.argv)
        self.assertIn("--continuous", spec.argv)


if __name__ == "__main__":
    unittest.main()
