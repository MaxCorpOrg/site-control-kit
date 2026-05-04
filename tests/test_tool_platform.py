from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tool_platform.agent_state import default_agent_state, ensure_agent_state, load_agent_state, save_agent_state
from tool_platform.catalog import find_action, find_tool, load_catalog
from tool_platform.cli import execute_action
from tool_platform.gui import (
    format_combined_flow_state,
    format_profile_details,
    format_session_operator_summary,
    format_workflow_details,
)
from tool_platform.jobs import (
    active_workflow_job,
    append_job_step,
    finish_job,
    get_job,
    list_jobs,
    profile_id_for,
    profile_workspace_snapshot,
    start_job,
    update_job_step,
    workflow_artifact_index,
)
from tool_platform.locks import (
    acquire_profile_lock,
    force_release_profile_lock,
    get_profile_lock,
    release_profile_lock,
)
from tool_platform.platform_adapters import current_platform_id, platform_doctor_report
from tool_platform.telegram_gui_helpers import (
    DEFAULT_PANEL_STATE_ROOT,
    active_profile_conflict,
    build_session_runtime_config,
    combined_contact_add_transition,
    combined_step_label,
    combined_session_transition,
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
    parse_combined_step_pattern,
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
from tool_platform.workflows import (
    CommandSpec as WorkflowCommandSpec,
    combined_state_from_jobs,
    complete_workflow_step,
    default_combined_workflow_context,
    migrate_legacy_combined_state,
    plan_workflow,
    resume_workflow,
    run_workflow,
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

    def test_catalog_loads_platform_metadata(self) -> None:
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
                    "tool_id": "platform_tool",
                    "display_name": "Platform Tool",
                    "root_dir": ".",
                    "supported_platforms": ["linux"],
                    "required_capabilities": ["window_automation"],
                    "degraded_modes": {"windows": "read-only"},
                    "actions": [],
                },
            )
            self._write_json(
                registry_path,
                {
                    "schema_version": 1,
                    "tools": [{"manifest_path": str(manifest_path), "enabled": True}],
                },
            )

            tool = find_tool(load_catalog(registry_path), "platform_tool")

        self.assertEqual(tool.supported_platforms, ("linux",))
        self.assertEqual(tool.required_capabilities, ("window_automation",))
        self.assertEqual(tool.degraded_modes, {"windows": "read-only"})

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
                    "supported_platforms": ["linux"],
                    "required_capabilities": ["window_automation"],
                    "degraded_modes": {"windows": "docs only"},
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
        self.assertIn("Поддерживаемые ОС: linux", details)

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
                    "step_pattern": "11,2",
                    "step_cursor": 2,
                    "step_label": "сессия и сообщения",
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
        self.assertEqual(state["step_pattern"], "11,2")
        self.assertEqual(state["step_cursor"], 2)
        self.assertEqual(state["step_label"], "сессия и сообщения")
        self.assertEqual(state["input_path"], "/tmp/users.txt")
        self.assertEqual(state["invite_job_dir"], "/tmp/job")
        self.assertEqual(state["last_status"], "completed")

    def test_default_combined_flow_state_starts_in_contact_add_phase(self) -> None:
        state = default_combined_flow_state("AK", "/home/max/TelegramPortableAK")
        self.assertEqual(state["phase"], "contact_add")
        self.assertEqual(state["last_status"], "idle")
        self.assertEqual(state["step_pattern"], "12")
        self.assertEqual(state["step_cursor"], 0)

    def test_combined_contact_add_transition_auto_starts_session_after_success(self) -> None:
        transition = combined_contact_add_transition(
            previous_state=default_combined_flow_state("AK", "/home/max/TelegramPortableAK"),
            payload={
                "status": "completed",
                "selected_users": 1,
                "failed_count": 0,
                "remaining_candidates": 3,
            },
            session_continuous=False,
        )

        self.assertEqual(transition["phase"], "session_ready")
        self.assertEqual(transition["last_action"], "combined_contact_add_finished_auto")
        self.assertTrue(transition["auto_start_session"])
        self.assertIn("запускаю шаг сессии", transition["status_text"])

    def test_combined_contact_add_transition_continues_after_partial_errors(self) -> None:
        transition = combined_contact_add_transition(
            previous_state=default_combined_flow_state("AK", "/home/max/TelegramPortableAK"),
            payload={
                "status": "completed_with_errors",
                "selected_users": 2,
                "failed_count": 1,
                "remaining_candidates": 10,
            },
            session_continuous=False,
        )

        self.assertEqual(transition["phase"], "session_ready")
        self.assertEqual(transition["last_action"], "combined_contact_add_finished_auto")
        self.assertTrue(transition["auto_start_session"])
        self.assertIn("ошибки сохранены", transition["status_text"].lower())

    def test_combined_contact_add_transition_stops_when_queue_finishes_after_session(self) -> None:
        previous_state = default_combined_flow_state("AK", "/home/max/TelegramPortableAK")
        previous_state["last_session_status"] = "completed"
        previous_state["last_session_run_dir"] = "/tmp/run"

        transition = combined_contact_add_transition(
            previous_state=previous_state,
            payload={
                "status": "completed",
                "selected_users": 0,
                "failed_count": 0,
                "remaining_candidates": 0,
            },
            session_continuous=False,
        )

        self.assertEqual(transition["phase"], "stopped")
        self.assertEqual(transition["last_action"], "combined_contact_add_noop_after_session")
        self.assertFalse(transition["auto_start_session"])
        self.assertIn("очередь контактов закончилась", transition["status_text"].lower())

    def test_combined_session_transition_loops_back_to_contact_add_when_pending_left(self) -> None:
        transition = combined_session_transition(
            payload={"status": "completed"},
            invite_snapshot={"pending_total": 2},
            session_continuous=False,
        )

        self.assertEqual(transition["phase"], "contact_add")
        self.assertEqual(transition["last_action"], "combined_session_finished_next_contact")
        self.assertTrue(transition["auto_start_contact_add"])
        self.assertIn("осталось username", transition["status_text"].lower())

    def test_combined_session_transition_stops_for_continuous_session(self) -> None:
        transition = combined_session_transition(
            payload={"status": "completed"},
            invite_snapshot={"pending_total": 5},
            session_continuous=True,
        )

        self.assertEqual(transition["phase"], "stopped")
        self.assertEqual(transition["last_action"], "combined_session_finished")
        self.assertFalse(transition["auto_start_contact_add"])
        self.assertIn("непрерывная сессия", transition["status_text"].lower())

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

    def test_parse_combined_step_pattern_keeps_only_add_and_session_steps(self) -> None:
        self.assertEqual(
            parse_combined_step_pattern("11,2,1111,22,1,222,1111"),
            list("11211112212221111"),
        )
        self.assertEqual(combined_step_label("1"), "добавление контактов")
        self.assertEqual(combined_step_label("2"), "сессия и сообщения")

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

    def test_format_session_operator_summary_shows_next_target_templates_and_last_send(self) -> None:
        summary = format_session_operator_summary(
            {
                "status": "ready",
                "messages_sent_total": 2,
                "message_cursor": 1,
                "message_target_cursor": 0,
                "last_run": {
                    "run_id": "20260503T120000Z-test",
                    "status": "completed",
                    "visit_count": 2,
                    "message_count": 2,
                    "sent_count": 1,
                    "message_target_username": "@alice_test",
                    "sent_messages": [
                        {"index": 1, "text": "Первое", "sent": True, "send_mode": "auto"}
                    ],
                    "unsent_messages": [
                        {"index": 2, "text": "Третье", "sent": False, "send_mode": "draft_only"}
                    ],
                },
            },
            session_targets=[{"label": "Alice", "handle": "@alice_test", "kind": "contact"}],
            session_templates=["Первое", "Второе", "Третье"],
            visits_per_cycle=4,
            view_min_seconds=3,
            view_max_seconds=7,
            messages_per_cycle=2,
            total_message_limit=4,
            auto_send=True,
            continuous=False,
        )

        self.assertIn("Следующий адресат: Alice · @alice_test · контакт", summary)
        self.assertIn("- #1 · Второе", summary)
        self.assertIn("- #2 · Третье", summary)
        self.assertIn("После этого цикла общий лимит будет исчерпан.", summary)
        self.assertIn("Последние реально отправленные", summary)
        self.assertIn("Неотправленные / оставшиеся в строке ввода", summary)

    def test_format_combined_flow_state_shows_next_username_and_session_preview(self) -> None:
        summary = format_combined_flow_state(
            {
                "phase": "contact_add",
                "workflow_job_id": "20260504T100000Z-abcd1234",
                "job_status": "running",
                "job_summary": "Автопереход к следующему шагу",
                "next_hint": "Дождись завершения текущего subprocess.",
                "steps_total": 3,
                "last_action": "combined_session_finished_next_contact",
                "last_status": "completed",
                "input_path": "/tmp/users.txt",
                "invite_job_dir": "/tmp/job",
                "recent_step": {
                    "step_index": 2,
                    "step_code": "1",
                    "step_kind": "invite_batch",
                    "step_status": "completed",
                    "started_at": "2026-05-04T10:00:00Z",
                    "completed_at": "2026-05-04T10:00:05Z",
                    "artifact_paths": {"job_dir": "/tmp/job"},
                },
            },
            profile_label="@M_a_g_g_i_e (AK) [запущен]",
            session_targets=[{"label": "Alice", "handle": "@alice_test", "kind": "contact"}],
            session_templates=["Первое", "Второе"],
            visits_per_cycle=3,
            view_min_seconds=4,
            view_max_seconds=8,
            messages_per_cycle=2,
            total_message_limit=0,
            auto_send=True,
            continuous=False,
            invite_snapshot={
                "status": "ready",
                "pending_total": 5,
                "added_total": 2,
                "failed_total": 1,
                "pending_usernames": ["@next_contact"],
            },
            session_snapshot={
                "status": "ready",
                "messages_sent_total": 1,
                "message_cursor": 0,
                "message_target_cursor": 0,
                "last_run": {
                    "status": "completed",
                    "visit_count": 2,
                    "sent_count": 1,
                    "sent_messages": [
                        {"index": 1, "text": "Первое", "sent": True, "send_mode": "auto"}
                    ],
                },
            },
        )

        self.assertIn("Следующий username в очереди: @next_contact", summary)
        self.assertIn("Следующий адресат для сообщения: Alice · @alice_test · контакт", summary)
        self.assertIn("Workflow job: 20260504T100000Z-abcd1234", summary)
        self.assertIn("Workflow status: running", summary)
        self.assertIn("Подсказка engine: Дождись завершения текущего subprocess.", summary)
        self.assertIn("Последний шаг engine", summary)
        self.assertIn("код 1", summary)
        self.assertIn("Следующие тексты для сессии:", summary)
        self.assertIn("- #1 · Первое", summary)
        self.assertIn("Что дальше: система сама запускает следующий шаг добавления.", summary)

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
        self.assertEqual(snapshot["last_run"]["sent_messages"][0]["text"], "Привет")
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

    def test_agent_state_roundtrip_uses_persistent_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "agent_state.json"
            ensure_agent_state(state_path)
            payload = load_agent_state(state_path)
            payload["next_recommended_step"] = "Run doctor first"
            save_agent_state(payload, state_path)
            updated = load_agent_state(state_path)

        self.assertEqual(updated["next_recommended_step"], "Run doctor first")
        self.assertEqual(updated["default_decisions"]["platform_support"], "tiered")

    def test_job_index_start_finish_and_workspace_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            index_path = Path(tmp_dir) / "jobs" / "index.json"
            started = start_job(
                tool_id="telegram_session_runner",
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                phase="session_running",
                summary="Running session",
                index_path=index_path,
            )
            finish_job(
                started["job_id"],
                payload={"status": "completed", "run_dir": "/tmp/run-1", "summary": "Done"},
                fallback_phase="session_running",
                index_path=index_path,
            )
            record = get_job(started["job_id"], index_path)
            workspace = profile_workspace_snapshot(
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                index_path=index_path,
            )

        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record["status"], "completed")
        self.assertEqual(record["artifact_paths"]["run_dir"], "/tmp/run-1")
        self.assertEqual(workspace["profile_id"], profile_id_for("AK", "/home/max/TelegramPortableAK"))
        self.assertEqual(workspace["last_successful_job"]["job_id"], started["job_id"])

    def test_job_steps_and_artifact_index_accumulate_child_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            index_path = Path(tmp_dir) / "jobs" / "index.json"
            started = start_job(
                tool_id="telegram_combined_flow",
                workflow_kind="combined_pattern",
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                phase="contact_add",
                status="planned",
                summary="Combined ready",
                context={"step_pattern": "12"},
                index_path=index_path,
            )
            step = append_job_step(
                started["job_id"],
                step_code="1",
                step_kind="invite_batch",
                action_label="combined contact add",
                status="running",
                summary="Running step",
                index_path=index_path,
            )
            update_job_step(
                started["job_id"],
                step_id=step["step_id"],
                status="completed",
                summary="Done step",
                artifact_paths={"job_dir": "/tmp/job-1"},
                completed=True,
                index_path=index_path,
            )

            job = get_job(started["job_id"], index_path)
            artifacts = workflow_artifact_index(started["job_id"], index_path=index_path)

        self.assertIsNotNone(job)
        assert job is not None
        self.assertEqual(len(job["steps"]), 1)
        self.assertEqual(job["steps"][0]["step_kind"], "invite_batch")
        self.assertEqual(artifacts["job_dir"], "/tmp/job-1")

    def test_plan_and_run_invite_workflow_generates_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            index_path = Path(tmp_dir) / "jobs" / "index.json"
            with mock.patch("tool_platform.workflows._build_invite_batch_command") as builder:
                builder.return_value = WorkflowCommandSpec(argv=["python3", "invite.py"], cwd=Path(tmp_dir))
                planned = plan_workflow(
                    workflow_kind="invite_batch",
                    tool_id="telegram_invite_manager",
                    profile_name="AK",
                    profile_dir="/home/max/TelegramPortableAK",
                    context={"invite_job_dir": "/tmp/job", "input_path": "/tmp/users.txt"},
                    summary="Invite planned",
                    index_path=index_path,
                )
                execution = run_workflow(planned["job_id"], index_path=index_path)

        self.assertEqual(execution["status"], "ready")
        self.assertEqual(execution["command"].argv, ["python3", "invite.py"])
        self.assertEqual(execution["step"]["step_kind"], "invite_batch")

    def test_combined_workflow_auto_advances_from_contact_step_to_session_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            index_path = Path(tmp_dir) / "jobs" / "index.json"
            combined_context = default_combined_workflow_context("AK", "/home/max/TelegramPortableAK")
            combined_context.update(
                {
                    "input_path": "/tmp/users.txt",
                    "invite_job_dir": "/tmp/job",
                    "session_config_path": "/tmp/session.json",
                    "continuous_session": False,
                    "step_pattern": "12",
                    "message_settings": {
                        "base_config_path": "/tmp/session.json",
                        "message_targets": [],
                        "message_templates": [],
                        "messages_per_cycle": 0,
                        "total_message_limit": 0,
                        "visits_per_cycle": 2,
                        "view_min_seconds": 3,
                        "view_max_seconds": 4,
                        "auto_send": False,
                    },
                }
            )
            with mock.patch("tool_platform.workflows._build_invite_batch_command") as invite_builder, mock.patch(
                "tool_platform.workflows._build_session_run_command"
            ) as session_builder:
                invite_builder.return_value = WorkflowCommandSpec(argv=["python3", "invite.py"], cwd=Path(tmp_dir))
                session_builder.return_value = (
                    WorkflowCommandSpec(argv=["python3", "session.py"], cwd=Path(tmp_dir)),
                    Path(tmp_dir) / "runtime.json",
                )
                planned = plan_workflow(
                    workflow_kind="combined_pattern",
                    tool_id="telegram_combined_flow",
                    profile_name="AK",
                    profile_dir="/home/max/TelegramPortableAK",
                    context=combined_context,
                    summary="Combined planned",
                    index_path=index_path,
                )
                first = run_workflow(planned["job_id"], index_path=index_path)
                result = complete_workflow_step(
                    planned["job_id"],
                    payload={
                        "status": "completed",
                        "selected_users": 1,
                        "failed_count": 0,
                        "remaining_candidates": 3,
                        "job_dir": "/tmp/job",
                    },
                    index_path=index_path,
                )
                job = get_job(planned["job_id"], index_path=index_path)

        self.assertEqual(first["step"]["step_code"], "1")
        self.assertEqual(result["status"], "continued")
        self.assertEqual(result["next_step"]["step_code"], "2")
        assert job is not None
        self.assertEqual(job["workflow_kind"], "combined_pattern")
        self.assertEqual(job["steps"][0]["status"], "completed")
        self.assertEqual(job["steps"][1]["status"], "running")

    def test_combined_workflow_finishes_when_contact_queue_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            index_path = Path(tmp_dir) / "jobs" / "index.json"
            combined_context = default_combined_workflow_context("AK", "/home/max/TelegramPortableAK")
            combined_context.update(
                {
                    "input_path": "/tmp/users.txt",
                    "invite_job_dir": "/tmp/job",
                    "session_config_path": "/tmp/session.json",
                    "continuous_session": False,
                    "step_pattern": "12",
                    "message_settings": {
                        "base_config_path": "/tmp/session.json",
                        "message_targets": [],
                        "message_templates": [],
                        "messages_per_cycle": 0,
                        "total_message_limit": 0,
                        "visits_per_cycle": 2,
                        "view_min_seconds": 3,
                        "view_max_seconds": 4,
                        "auto_send": False,
                    },
                }
            )
            with mock.patch("tool_platform.workflows._build_invite_batch_command") as invite_builder:
                invite_builder.return_value = WorkflowCommandSpec(argv=["python3", "invite.py"], cwd=Path(tmp_dir))
                planned = plan_workflow(
                    workflow_kind="combined_pattern",
                    tool_id="telegram_combined_flow",
                    profile_name="AK",
                    profile_dir="/home/max/TelegramPortableAK",
                    context=combined_context,
                    summary="Combined planned",
                    index_path=index_path,
                )
                run_workflow(planned["job_id"], index_path=index_path)
                result = complete_workflow_step(
                    planned["job_id"],
                    payload={
                        "status": "completed",
                        "selected_users": 0,
                        "failed_count": 0,
                        "remaining_candidates": 0,
                        "job_dir": "/tmp/job",
                    },
                    index_path=index_path,
                )
                job = get_job(planned["job_id"], index_path=index_path)

        self.assertEqual(result["status"], "completed")
        self.assertIsNone(result["next_command"])
        assert job is not None
        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["phase"], "stopped")
        self.assertEqual(job["context"]["last_action"], "combined_contact_add_noop")

    def test_combined_workflow_continuous_session_stops_pattern_advancement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            index_path = Path(tmp_dir) / "jobs" / "index.json"
            combined_context = default_combined_workflow_context("AK", "/home/max/TelegramPortableAK")
            combined_context.update(
                {
                    "input_path": "/tmp/users.txt",
                    "invite_job_dir": "/tmp/job",
                    "session_config_path": "/tmp/session.json",
                    "continuous_session": True,
                    "step_pattern": "12",
                    "message_settings": {
                        "base_config_path": "/tmp/session.json",
                        "message_targets": [],
                        "message_templates": [],
                        "messages_per_cycle": 0,
                        "total_message_limit": 0,
                        "visits_per_cycle": 2,
                        "view_min_seconds": 3,
                        "view_max_seconds": 4,
                        "auto_send": False,
                    },
                }
            )
            with mock.patch("tool_platform.workflows._build_invite_batch_command") as invite_builder, mock.patch(
                "tool_platform.workflows._build_session_run_command"
            ) as session_builder, mock.patch(
                "tool_platform.workflows._combined_invite_snapshot",
                return_value={"pending_total": 7},
            ):
                invite_builder.return_value = WorkflowCommandSpec(argv=["python3", "invite.py"], cwd=Path(tmp_dir))
                session_builder.return_value = (
                    WorkflowCommandSpec(argv=["python3", "session.py"], cwd=Path(tmp_dir)),
                    Path(tmp_dir) / "runtime.json",
                )
                planned = plan_workflow(
                    workflow_kind="combined_pattern",
                    tool_id="telegram_combined_flow",
                    profile_name="AK",
                    profile_dir="/home/max/TelegramPortableAK",
                    context=combined_context,
                    summary="Combined planned",
                    index_path=index_path,
                )
                run_workflow(planned["job_id"], index_path=index_path)
                complete_workflow_step(
                    planned["job_id"],
                    payload={
                        "status": "completed",
                        "selected_users": 1,
                        "failed_count": 0,
                        "remaining_candidates": 7,
                        "job_dir": "/tmp/job",
                    },
                    index_path=index_path,
                )
                result = complete_workflow_step(
                    planned["job_id"],
                    payload={
                        "status": "completed",
                        "run_dir": "/tmp/run",
                        "sent_count": 0,
                    },
                    index_path=index_path,
                )
                job = get_job(planned["job_id"], index_path=index_path)

        self.assertEqual(result["status"], "completed")
        self.assertIsNone(result["next_command"])
        assert job is not None
        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["phase"], "stopped")
        self.assertEqual(job["context"]["last_action"], "combined_session_finished")

    def test_resume_workflow_returns_current_running_step_or_next_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            index_path = Path(tmp_dir) / "jobs" / "index.json"
            with mock.patch("tool_platform.workflows._build_invite_batch_command") as builder:
                builder.return_value = WorkflowCommandSpec(argv=["python3", "invite.py"], cwd=Path(tmp_dir))
                planned = plan_workflow(
                    workflow_kind="invite_batch",
                    tool_id="telegram_invite_manager",
                    profile_name="AK",
                    profile_dir="/home/max/TelegramPortableAK",
                    context={"invite_job_dir": "/tmp/job", "input_path": "/tmp/users.txt"},
                    summary="Invite planned",
                    index_path=index_path,
                )
                run_workflow(planned["job_id"], index_path=index_path)
                running = resume_workflow(planned["job_id"], index_path=index_path)
                complete_workflow_step(
                    planned["job_id"],
                    payload={"status": "completed", "job_dir": "/tmp/job"},
                    index_path=index_path,
                )
                resumed = resume_workflow(planned["job_id"], index_path=index_path)

        self.assertEqual(running["status"], "already_running")
        self.assertEqual(resumed["status"], "terminal")

    def test_combined_state_from_jobs_prefers_job_context_over_legacy_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            index_path = Path(tmp_dir) / "jobs" / "index.json"
            context = default_combined_workflow_context("AK", "/home/max/TelegramPortableAK")
            context.update({"phase": "session_ready", "step_pattern": "11,2", "step_cursor": 2})
            planned = plan_workflow(
                workflow_kind="combined_pattern",
                tool_id="telegram_combined_flow",
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                context=context,
                summary="Combined planned",
                index_path=index_path,
            )

            state = combined_state_from_jobs(
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                index_path=index_path,
            )

        self.assertEqual(state["workflow_job_id"], planned["job_id"])
        self.assertEqual(state["phase"], "session_ready")
        self.assertEqual(state["step_pattern"], "11,2")
        self.assertEqual(state["step_cursor"], 2)

    def test_profile_locks_detect_conflict_and_force_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            locks_path = Path(tmp_dir) / "locks.json"
            first = acquire_profile_lock(
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                owner_tool_id="telegram_invite_manager",
                job_id="job-1",
                locks_path=locks_path,
            )
            second = acquire_profile_lock(
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                owner_tool_id="telegram_session_runner",
                job_id="job-2",
                locks_path=locks_path,
            )
            current = get_profile_lock(
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                locks_path=locks_path,
            )
            released = release_profile_lock(
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                owner_tool_id="telegram_invite_manager",
                job_id="job-1",
                locks_path=locks_path,
            )
            force_release_profile_lock(
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                locks_path=locks_path,
            )

        self.assertTrue(first["acquired"])
        self.assertFalse(second["acquired"])
        self.assertEqual(current["owner_tool_id"], "telegram_invite_manager")
        self.assertTrue(released)

    def test_migrate_legacy_combined_state_copies_tmp_state_into_persistent_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            legacy_root = Path(tmp_dir) / "legacy"
            new_root = Path(tmp_dir) / "new"
            legacy_path = combined_flow_state_path(
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                state_root=legacy_root,
            )
            legacy_path.parent.mkdir(parents=True, exist_ok=True)
            legacy_path.write_text(
                json.dumps({"phase": "session_ready", "step_pattern": "12"}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            migrated = migrate_legacy_combined_state(
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                new_state_root=new_root,
                legacy_state_root=legacy_root,
            )
            loaded = load_combined_flow_state(
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                state_root=new_root,
            )

        self.assertEqual(migrated["phase"], "session_ready")
        self.assertEqual(loaded["phase"], "session_ready")
        self.assertEqual(loaded["step_pattern"], "12")

    def test_platform_doctor_report_contains_current_platform_and_capabilities(self) -> None:
        report = platform_doctor_report()
        self.assertEqual(report["current_platform_id"], current_platform_id())
        self.assertIn("capabilities", report)
        self.assertIn("gui", report["capabilities"])


if __name__ == "__main__":
    unittest.main()
