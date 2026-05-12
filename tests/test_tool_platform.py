from __future__ import annotations

import json
import io
import os
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from tool_platform.agent_state import default_agent_state, ensure_agent_state, load_agent_state, save_agent_state
from tool_platform.catalog import find_action, find_tool, load_catalog
from tool_platform.cli import execute_action, main as cli_main
from tool_platform.gui import (
    ToolPlatformPanel,
    build_combined_start_context,
    format_combined_flow_state,
    format_profile_details,
    format_profile_workspace_summary,
    format_profile_workspace_history,
    format_profiles_overview,
    format_session_operator_summary,
    format_session_history,
    format_workflow_timeline,
    format_workflow_details,
)
from tool_platform.jobs import (
    active_workflow_job,
    append_job_step,
    finish_job,
    get_job,
    list_jobs,
    profile_artifact_index,
    profile_history_groups,
    profile_id_for,
    profile_workspace_snapshot,
    repair_historical_artifacts,
    repair_invite_artifacts,
    repair_session_artifacts,
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
    hide_portable_profile,
    import_tdata_profile,
    list_hidden_profile_records,
    list_portable_profiles,
    remove_portable_profile,
    unhide_portable_profile,
)
from tool_platform.workflows import (
    CommandSpec as WorkflowCommandSpec,
    cleanup_failed_workflow_start,
    combined_state_from_jobs,
    complete_workflow_step,
    default_combined_workflow_context,
    migrate_legacy_combined_state,
    plan_workflow,
    profile_health,
    resume_workflow,
    run_workflow,
    stop_workflow_job,
)


class ToolPlatformCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self._workflow_state_tmp = tempfile.TemporaryDirectory()
        self._workflow_state_patcher = mock.patch(
            "tool_platform.workflows.DEFAULT_WORKFLOW_STATE_ROOT",
            Path(self._workflow_state_tmp.name) / "panel_state",
        )
        self._workflow_state_patcher.start()

    def tearDown(self) -> None:
        self._workflow_state_patcher.stop()
        self._workflow_state_tmp.cleanup()
        super().tearDown()

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

    def test_list_portable_profiles_filters_hidden_records(self) -> None:
        completed = mock.Mock(
            returncode=0,
            stdout=json.dumps(
                {
                    "profiles": [
                        {"profile_name": "A", "profile_dir": "/tmp/TelegramPortable-A", "running": True},
                        {"profile_name": "B", "profile_dir": "/tmp/TelegramPortable-B", "running": False},
                    ]
                }
            ),
            stderr="",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "hidden_profiles.json"
            hide_portable_profile(
                profile_dir="/tmp/TelegramPortable-B",
                profile_name="B",
                account_label="B",
                state_path=state_path,
            )
            with mock.patch("tool_platform.telegram_profiles.subprocess.run", return_value=completed):
                profiles = list_portable_profiles("/tmp/profiles", hidden_state_path=state_path)
                profiles_with_hidden = list_portable_profiles(
                    "/tmp/profiles",
                    include_hidden=True,
                    hidden_state_path=state_path,
                )

        self.assertEqual([item["profile_name"] for item in profiles], ["A"])
        self.assertEqual([item["profile_name"] for item in profiles_with_hidden], ["A", "B"])

    def test_hidden_profile_records_can_be_restored(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "hidden_profiles.json"
            hide_portable_profile(
                profile_dir="/tmp/TelegramPortable-B",
                profile_name="B",
                account_username="@b",
                account_label="B Label",
                state_path=state_path,
            )
            self.assertEqual(len(list_hidden_profile_records(state_path)), 1)

            unhide_portable_profile(profile_dir="/tmp/TelegramPortable-B", state_path=state_path)

            self.assertEqual(list_hidden_profile_records(state_path), [])

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

    def test_remove_portable_profile_rejects_running_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_dir = Path(tmpdir) / "TelegramPortable-AK2"
            profile_dir.mkdir()
            with mock.patch(
                "tool_platform.telegram_profiles.get_profile_status",
                return_value={"running": True, "profile_name": "AK2"},
            ):
                with self.assertRaisesRegex(RuntimeError, "процесс запущен"):
                    remove_portable_profile(profile_dir=profile_dir)

    def test_remove_portable_profile_rejects_locked_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_dir = Path(tmpdir) / "TelegramPortable-AK2"
            profile_dir.mkdir()
            with mock.patch(
                "tool_platform.telegram_profiles.get_profile_status",
                return_value={"running": False, "profile_name": "AK2"},
            ), mock.patch(
                "tool_platform.telegram_profiles.get_profile_lock",
                return_value={"owner_tool_id": "telegram_invite_manager", "job_id": "job-1"},
            ):
                with self.assertRaisesRegex(RuntimeError, "удерживается live workflow"):
                    remove_portable_profile(profile_dir=profile_dir)

    def test_remove_portable_profile_deletes_directory_and_keeps_hidden_state_clean(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            profile_dir = root / "TelegramPortable-AK2"
            profile_dir.mkdir()
            (profile_dir / "Telegram").write_text("", encoding="utf-8")
            hidden_state = root / "hidden_profiles.json"
            hide_portable_profile(profile_dir=profile_dir, profile_name="AK2", state_path=hidden_state)

            with mock.patch(
                "tool_platform.telegram_profiles.get_profile_status",
                return_value={
                    "running": False,
                    "profile_name": "AK2",
                    "account": {"label": "@S_e_r_a_p_h_i_na"},
                },
            ), mock.patch(
                "tool_platform.telegram_profiles.get_profile_lock",
                return_value=None,
            ):
                payload = remove_portable_profile(profile_dir=profile_dir, hidden_state_path=hidden_state)

            self.assertEqual(payload["status"], "deleted")
            self.assertFalse(profile_dir.exists())
            self.assertEqual(list_hidden_profile_records(hidden_state), [])

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
                "attach_status": "exact_window",
                "attach_message": "Окно профиля найдено.",
                "attach_candidates": [{"title": "Макс Михайлов", "window_id": "0x1"}],
                "windows": [{"title": "Макс Михайлов", "window_id": "0x1"}],
            }
        )

        self.assertIn("Профиль Telegram", details)
        self.assertIn("@M_a_g_g_i_e", details)
        self.assertIn("Заголовок окна: Макс Михайлов", details)
        self.assertIn("Статус attach: окно найдено", details)
        self.assertIn("Папка профиля: /home/max/TelegramPortableAK", details)

    def test_format_profile_workspace_summary_shows_attach_problem(self) -> None:
        summary = format_profile_workspace_summary(
            {
                "profile_name": "AK2",
                "profile_dir": "/home/max/TelegramPortable-AK2",
                "running": True,
                "attach_status": "running_without_window",
                "attach_message": "Процесс запущен, но собственного окна нет.",
                "attach_candidates": [],
                "windows": [],
                "account": {"username": "@seraphina", "label": "@S_e_r_a_p_h_i_na"},
            },
            {
                "resume_hint": "можно продолжить",
                "continue_queue_hint": "нет данных",
                "retry_failed_hint": "нет данных",
                "next_operator_action": "Запустить новый workflow.",
            },
        )

        self.assertIn("Attach: окно не найдено", summary)
        self.assertIn("Подсказка attach: Процесс запущен, но собственного окна нет.", summary)

    def test_format_profiles_overview_includes_attach_status(self) -> None:
        overview = format_profiles_overview(
            [
                {
                    "profile_name": "AK2",
                    "running": True,
                    "attach_status": "running_without_window",
                    "account": {"label": "@S_e_r_a_p_h_i_na"},
                }
            ]
        )

        self.assertIn("окно не найдено", overview)

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
            with mock.patch("tool_platform.telegram_gui_helpers.combined_state_from_jobs", return_value=None):
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

    def test_contact_add_batch_command_passes_execution_id_when_provided(self) -> None:
        spec = contact_add_batch_command(
            input_path=None,
            job_dir="/tmp/job",
            profile_name="AK",
            portable_profile_dir="/home/max/TelegramPortableAK",
            execution_id="20260508T110000Z",
        )

        self.assertIn("--execution-id", spec.argv)
        self.assertIn("20260508T110000Z", spec.argv)

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
                        "started_at": "2026-05-03T10:00:00Z",
                        "completed_at": "2026-05-03T10:02:00Z",
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
        self.assertEqual(snapshot["progress_summary"]["history_source"], "batch_json")
        self.assertEqual(snapshot["progress_summary"]["processed_count"], 1)
        self.assertEqual(snapshot["progress_summary"]["elapsed_seconds"], 120)
        self.assertEqual(snapshot["progress_summary"]["queue_remaining_total"], 1)

    def test_contact_job_snapshot_prefers_running_progress_json_for_live_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            job_dir = Path(tmp_dir) / "job"
            execution_dir = job_dir / "executions" / "20260508T110000Z"
            execution_dir.mkdir(parents=True)
            (job_dir / "invite_state.json").write_text(
                json.dumps(
                    {
                        "chat_url": "contacts://ak3",
                        "source_file": "/tmp/users.txt",
                        "updated_at": "2026-05-08T11:00:00Z",
                        "users": [
                            {"username": "@alice_test", "status": "contact_added"},
                            {"username": "@bob_test", "status": "checked"},
                            {"username": "@carol_test", "status": "checked"},
                            {"username": "@dave_test", "status": "failed"},
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (execution_dir / "batch_progress.json").write_text(
                json.dumps(
                    {
                        "execution_id": "20260508T110000Z",
                        "status": "running",
                        "selected_target": 19,
                        "processed_count": 5,
                        "added_count": 4,
                        "already_present_count": 0,
                        "failed_count": 1,
                        "remaining_in_run": 14,
                        "queue_remaining_total": 1443,
                        "elapsed_seconds": 300,
                        "rate_per_minute": 1.0,
                        "eta_seconds": 840,
                        "current_username": "@bob_test",
                        "last_outcome": "contact_added_verified",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            snapshot = contact_job_snapshot(job_dir)

        self.assertEqual(snapshot["progress_summary"]["history_source"], "progress_json")
        self.assertEqual(snapshot["progress_summary"]["processed_count"], 5)
        self.assertEqual(snapshot["progress_summary"]["remaining_in_run"], 14)
        self.assertEqual(snapshot["progress_summary"]["queue_remaining_total"], 1443)
        self.assertEqual(snapshot["progress_summary"]["eta_seconds"], 840)
        self.assertEqual(snapshot["progress_summary"]["current_username"], "@bob_test")

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
            history_text = format_session_history(snapshot)

        self.assertEqual(snapshot["messages_sent_total"], 3)
        self.assertEqual(snapshot["last_run"]["run_id"], "20260503T100000Z-aaaa")
        self.assertEqual(snapshot["last_run"]["sent_count"], 1)
        self.assertEqual(snapshot["last_run"]["draft_count"], 1)
        self.assertEqual(snapshot["last_run"]["sent_messages"][0]["text"], "Привет")
        self.assertEqual(snapshot["last_run"]["unsent_messages"][0]["text"], "Напомни")
        self.assertEqual(snapshot["last_run"]["sent_preview"], ["Привет"])
        self.assertEqual(snapshot["last_run"]["draft_preview"], ["Напомни"])
        self.assertIn("черновиков 1", history_text)
        self.assertIn("sent: Привет", history_text)
        self.assertIn("draft: Напомни", history_text)

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

    def test_workspace_snapshot_builds_buckets_and_health_from_unified_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            index_path = Path(tmp_dir) / "jobs" / "index.json"
            invite_job = start_job(
                tool_id="telegram_invite_manager",
                workflow_kind="invite_batch",
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                phase="stopped",
                status="completed_with_errors",
                summary="Invite needs retry",
                recoverable=True,
                context={"invite_job_dir": "/tmp/invite-job"},
                steps=[
                    {
                        "step_id": "invite-step-1",
                        "step_index": 0,
                        "step_code": "1",
                        "step_kind": "invite_batch",
                        "status": "completed_with_errors",
                        "summary": "Invite partial",
                        "started_at": "2026-05-04T07:00:00Z",
                        "completed_at": "2026-05-04T07:00:05Z",
                        "artifact_paths": {"job_dir": "/tmp/invite-job"},
                    }
                ],
                index_path=index_path,
            )
            session_job = start_job(
                tool_id="telegram_session_runner",
                workflow_kind="session_run",
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                phase="session_running",
                status="running",
                summary="Session running",
                steps=[
                    {
                        "step_id": "session-step-1",
                        "step_index": 0,
                        "step_code": "2",
                        "step_kind": "session_run",
                        "status": "running",
                        "summary": "Running session",
                        "started_at": "2026-05-04T07:10:00Z",
                        "completed_at": "",
                        "artifact_paths": {"run_dir": "/tmp/session-run"},
                    }
                ],
                index_path=index_path,
            )
            combined_job = start_job(
                tool_id="telegram_combined_flow",
                workflow_kind="combined_pattern",
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                phase="stopped",
                status="completed",
                summary="Combined done",
                artifact_paths={"run_dir": "/tmp/combined-run"},
                steps=[
                    {
                        "step_id": "combined-step-1",
                        "step_index": 0,
                        "step_code": "1",
                        "step_kind": "invite_batch",
                        "status": "completed",
                        "summary": "Contact step done",
                        "started_at": "2026-05-04T07:20:00Z",
                        "completed_at": "2026-05-04T07:20:05Z",
                        "artifact_paths": {"execution_record": "/tmp/combined-record.json"},
                    }
                ],
                index_path=index_path,
            )
            workspace = profile_workspace_snapshot(
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                index_path=index_path,
            )

        self.assertEqual(workspace["current_lock"], None)
        self.assertTrue(workspace["health"]["session_runtime_reachable"])
        invite_bucket = workspace["workflow_buckets"]["invite_batch"]
        session_bucket = workspace["workflow_buckets"]["session_run"]
        combined_bucket = workspace["workflow_buckets"]["combined_pattern"]
        self.assertEqual(invite_bucket["recoverable_job"]["job_id"], invite_job["job_id"])
        self.assertEqual(session_bucket["active_job"]["job_id"], session_job["job_id"])
        self.assertEqual(combined_bucket["last_job"]["job_id"], combined_job["job_id"])
        self.assertEqual(invite_bucket["timeline"][0]["summary"], "Invite partial")
        self.assertEqual(session_bucket["artifact_index"]["run_dir"], "/tmp/session-run")
        self.assertEqual(combined_bucket["artifact_index"]["execution_record"], "/tmp/combined-record.json")
        self.assertIn("progress_summary", session_bucket)
        self.assertIn("progress_summary", combined_bucket)

    def test_profile_workspace_snapshot_prefers_active_artifacts_then_recent_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            index_path = Path(tmp_dir) / "jobs" / "index.json"
            start_job(
                tool_id="telegram_invite_manager",
                workflow_kind="invite_batch",
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                phase="stopped",
                status="completed",
                summary="Invite done",
                artifact_paths={"batch_json": "/tmp/invite-batch.json"},
                index_path=index_path,
            )
            start_job(
                tool_id="telegram_session_runner",
                workflow_kind="session_run",
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                phase="session_running",
                status="running",
                summary="Session running",
                artifact_paths={"run_dir": "/tmp/session-run"},
                index_path=index_path,
            )
            start_job(
                tool_id="telegram_combined_flow",
                workflow_kind="combined_pattern",
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                phase="stopped",
                status="completed",
                summary="Combined done",
                artifact_paths={"execution_record": "/tmp/combined-record.json"},
                index_path=index_path,
            )

            workspace = profile_workspace_snapshot(
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                index_path=index_path,
            )
            artifacts = profile_artifact_index(
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                index_path=index_path,
            )

        self.assertEqual(workspace["artifact_index"]["run_dir"], "/tmp/session-run")
        self.assertEqual(artifacts["run_dir"], "/tmp/session-run")
        self.assertEqual(artifacts["batch_json"], "/tmp/invite-batch.json")
        self.assertEqual(artifacts["execution_record"], "/tmp/combined-record.json")

    def test_profile_workspace_snapshot_includes_operator_hints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            index_path = Path(tmp_dir) / "jobs" / "index.json"
            invite_job_dir = Path(tmp_dir) / "invite-job"
            invite_job_dir.mkdir(parents=True, exist_ok=True)
            (invite_job_dir / "invite_state.json").write_text(
                json.dumps(
                    {
                        "users": [
                            {"username": "@one", "status": "new"},
                            {"username": "@two", "status": "failed"},
                            {"username": "@three", "status": "contact_added"},
                        ]
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            start_job(
                tool_id="telegram_invite_manager",
                workflow_kind="invite_batch",
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                phase="stopped",
                status="completed_with_errors",
                summary="Invite partial",
                recoverable=True,
                context={
                    "input_path": "/tmp/users.txt",
                    "invite_job_dir": str(invite_job_dir),
                    "statuses": ["new", "checked"],
                },
                index_path=index_path,
            )

            workspace = profile_workspace_snapshot(
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                index_path=index_path,
            )
            invite_bucket = workspace["workflow_buckets"]["invite_batch"]

        self.assertEqual(workspace["resume_hint"], "можно продолжить")
        self.assertIn("осталось 1", workspace["continue_queue_hint"])
        self.assertIn("ошибки можно повторить: 1", workspace["retry_failed_hint"])
        self.assertEqual(invite_bucket["resume_hint"], "можно продолжить")
        self.assertTrue(invite_bucket["continue_queue_allowed"])
        self.assertTrue(invite_bucket["retry_failed_allowed"])
        self.assertEqual(invite_bucket["next_operator_action"], "Повторить ошибки invite batch.")

    def test_profile_workspace_snapshot_prefers_fresh_completed_job_over_older_recoverable_for_top_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            index_path = Path(tmp_dir) / "jobs" / "index.json"
            old_job = start_job(
                tool_id="telegram_session_runner",
                workflow_kind="session_run",
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                phase="stopped",
                status="stopped",
                summary="Old recoverable session",
                recoverable=True,
                index_path=index_path,
            )
            fresh_job = start_job(
                tool_id="telegram_session_runner",
                workflow_kind="session_run",
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                phase="stopped",
                status="completed",
                summary="Fresh completed session",
                index_path=index_path,
            )
            payload = json.loads(index_path.read_text(encoding="utf-8"))
            for item in payload["jobs"]:
                if item["job_id"] == old_job["job_id"]:
                    item["started_at"] = "2026-05-04T09:00:00Z"
                    item["updated_at"] = "2026-05-04T09:00:05Z"
                    item["completed_at"] = "2026-05-04T09:00:05Z"
                if item["job_id"] == fresh_job["job_id"]:
                    item["started_at"] = "2026-05-04T09:10:00Z"
                    item["updated_at"] = "2026-05-04T09:10:05Z"
                    item["completed_at"] = "2026-05-04T09:10:05Z"
            index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            workspace = profile_workspace_snapshot(
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                index_path=index_path,
            )

        self.assertEqual(workspace["last_successful_job"]["job_id"], fresh_job["job_id"])
        self.assertEqual(workspace["resume_hint"], "лучше перезапустить")
        self.assertEqual(workspace["next_operator_action"], "Запустить новый workflow.")

    def test_profile_workspace_snapshot_exposes_history_groups_timeline_and_artifact_shortcuts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            index_path = root / "jobs" / "index.json"
            invite_batch_json = root / "invite-batch.json"
            invite_batch_json.write_text("{}", encoding="utf-8")
            execution_record = root / "execution_record.json"
            execution_record.write_text("{}", encoding="utf-8")
            run_dir = root / "session-run"
            run_dir.mkdir()
            run_json = run_dir / "run.json"
            run_json.write_text(
                json.dumps(
                    {
                        "run_id": "20260504T092500Z-session",
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
            (run_dir / "plan.json").write_text("{}", encoding="utf-8")
            screenshot = run_dir / "after.png"
            screenshot.write_text("png", encoding="utf-8")

            start_job(
                tool_id="telegram_invite_manager",
                workflow_kind="invite_batch",
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                phase="stopped",
                status="completed",
                summary="Invite done",
                artifact_paths={"batch_json": str(invite_batch_json)},
                index_path=index_path,
            )
            start_job(
                tool_id="telegram_combined_flow",
                workflow_kind="combined_pattern",
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                phase="stopped",
                status="completed",
                summary="Combined done",
                steps=[
                    {
                        "step_id": "combined-1",
                        "step_index": 0,
                        "step_code": "1",
                        "step_kind": "invite_batch",
                        "status": "completed",
                        "summary": "Contact add done",
                        "started_at": "2026-05-04T09:20:00Z",
                        "completed_at": "2026-05-04T09:20:05Z",
                        "artifact_paths": {"execution_record": str(execution_record)},
                    }
                ],
                index_path=index_path,
            )
            session_job = start_job(
                tool_id="telegram_session_runner",
                workflow_kind="session_run",
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                phase="session_running",
                status="running",
                summary="Session running",
                artifact_paths={"run_dir": str(run_dir), "screenshot_path": str(screenshot)},
                steps=[
                    {
                        "step_id": "session-1",
                        "step_index": 0,
                        "step_code": "2",
                        "step_kind": "session_run",
                        "status": "running",
                        "summary": "Session cycle",
                        "started_at": "2026-05-04T09:25:00Z",
                        "completed_at": "",
                        "artifact_paths": {"run_dir": str(run_dir)},
                    }
                ],
                index_path=index_path,
            )
            payload = json.loads(index_path.read_text(encoding="utf-8"))
            ordered_timestamps = {
                str(session_job["job_id"]): ("2026-05-04T09:25:00Z", "2026-05-04T09:25:05Z"),
            }
            for item in payload["jobs"]:
                started_at, updated_at = ordered_timestamps.get(
                    str(item.get("job_id") or ""),
                    ("2026-05-04T09:10:00Z", "2026-05-04T09:10:05Z"),
                )
                item["started_at"] = started_at
                item["updated_at"] = updated_at
                if str(item.get("status") or "") in {"completed", "running"}:
                    item["completed_at"] = "" if str(item.get("status") or "") == "running" else updated_at
            index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            workspace = profile_workspace_snapshot(
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                index_path=index_path,
            )

        self.assertEqual(workspace["history_groups"][0]["job"]["job_id"], session_job["job_id"])
        self.assertEqual(workspace["history_groups"][0]["job"]["session_summary"]["sent_count"], 1)
        self.assertEqual(workspace["history_groups"][0]["steps"][0]["session_summary"]["draft_count"], 1)
        self.assertEqual(workspace["profile_timeline"][0]["entry_kind"], "job")
        self.assertEqual(workspace["profile_timeline"][1]["entry_kind"], "step")
        self.assertEqual(workspace["profile_timeline"][0]["session_summary"]["message_target_username"], "@alice_test")
        self.assertEqual(workspace["artifact_shortcuts"]["session_run"], str(run_json))
        self.assertEqual(workspace["artifact_shortcuts"]["batch_json"], str(invite_batch_json))
        self.assertEqual(workspace["artifact_shortcuts"]["execution_record"], str(execution_record))
        self.assertEqual(workspace["artifact_shortcuts"]["screenshot"], str(screenshot))
        self.assertEqual(workspace["artifact_provenance"]["session_run"], "stored")
        self.assertTrue(any(item["artifact_kind"] == "session_run" and item["available"] for item in workspace["artifact_center"]))
        self.assertTrue(
            any(
                item["artifact_kind"] == "session_run" and item["provenance"] == "stored"
                for item in workspace["artifact_center"]
            )
        )
        self.assertTrue(
            any(
                item["artifact_kind"] == "plan_json"
                and item["path"] == str(run_dir / "plan.json")
                and item["provenance"] == "stored"
                for item in workspace["artifact_history"]
            )
        )
        child_provenance = workspace["workflow_buckets"]["combined_pattern"]["child_artifact_provenance"]
        self.assertEqual(child_provenance["session_run"]["session_run"], "stored")
        history_text = format_profile_workspace_history(
            {"profile_name": "AK", "profile_dir": "/home/max/TelegramPortableAK"},
            workspace,
        )
        self.assertIn("отправлено 1", history_text)
        self.assertIn("черновиков 1", history_text)
        self.assertIn("sent: Привет", history_text)
        self.assertIn("draft: Напомни", history_text)

    def test_profile_workspace_snapshot_prefers_session_bucket_for_session_run_shortcut(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            index_path = root / "jobs" / "index.json"
            old_combined_run_dir = root / "combined-run"
            old_combined_run_dir.mkdir()
            (old_combined_run_dir / "run.json").write_text("{}", encoding="utf-8")
            fresh_session_run_dir = root / "session-run"
            fresh_session_run_dir.mkdir()
            fresh_run_json = fresh_session_run_dir / "run.json"
            fresh_run_json.write_text("{}", encoding="utf-8")

            combined_job = start_job(
                tool_id="telegram_combined_flow",
                workflow_kind="combined_pattern",
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                phase="stopped",
                status="completed",
                summary="Combined done",
                artifact_paths={"run_dir": str(old_combined_run_dir)},
                index_path=index_path,
            )
            session_job = start_job(
                tool_id="telegram_session_runner",
                workflow_kind="session_run",
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                phase="stopped",
                status="completed",
                summary="Session done",
                artifact_paths={"run_dir": str(fresh_session_run_dir)},
                index_path=index_path,
            )
            payload = json.loads(index_path.read_text(encoding="utf-8"))
            for item in payload["jobs"]:
                if item["job_id"] == combined_job["job_id"]:
                    item["started_at"] = "2026-05-04T09:10:00Z"
                    item["updated_at"] = "2026-05-04T09:10:05Z"
                    item["completed_at"] = "2026-05-04T09:10:05Z"
                if item["job_id"] == session_job["job_id"]:
                    item["started_at"] = "2026-05-04T09:20:00Z"
                    item["updated_at"] = "2026-05-04T09:20:05Z"
                    item["completed_at"] = "2026-05-04T09:20:05Z"
            index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            workspace = profile_workspace_snapshot(
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                index_path=index_path,
            )

        self.assertEqual(workspace["last_successful_job"]["job_id"], session_job["job_id"])
        self.assertEqual(workspace["artifact_shortcuts"]["session_run"], str(fresh_run_json))

    def test_profile_workspace_snapshot_falls_back_to_session_history_for_session_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            index_path = root / "jobs" / "index.json"
            run_dir = root / "session-run"
            run_dir.mkdir()
            run_json = run_dir / "run.json"
            run_json.write_text("{}", encoding="utf-8")
            screenshot = run_dir / "after.png"
            screenshot.write_text("png", encoding="utf-8")

            start_job(
                tool_id="telegram_session_runner",
                workflow_kind="session_run",
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                phase="stopped",
                status="completed",
                summary="Session done without artifact_paths",
                index_path=index_path,
            )
            with mock.patch(
                "tool_platform.telegram_gui_helpers.session_history_snapshot",
                return_value={
                    "last_run": {
                        "run_dir": str(run_dir),
                        "path": str(run_json),
                    }
                },
            ):
                workspace = profile_workspace_snapshot(
                    profile_name="AK",
                    profile_dir="/home/max/TelegramPortableAK",
                    index_path=index_path,
                )

        self.assertEqual(workspace["artifact_shortcuts"]["session_run"], str(run_json))
        self.assertEqual(workspace["artifact_shortcuts"]["screenshot"], str(screenshot))
        self.assertEqual(workspace["artifact_provenance"]["session_run"], "fallback")
        self.assertTrue(
            any(
                item["artifact_kind"] == "session_run" and item["provenance"] == "fallback"
                for item in workspace["artifact_center"]
            )
        )

    def test_profile_workspace_snapshot_builds_session_snapshot_from_unified_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            index_path = root / "jobs" / "index.json"
            runs_dir = root / "runs"
            runs_dir.mkdir()
            run_dir = runs_dir / "20260504T111811Z-a0435a6f"
            run_dir.mkdir()
            run_json = run_dir / "run.json"
            run_json.write_text(
                json.dumps(
                    {
                        "run_id": run_dir.name,
                        "status": "completed",
                        "visits": [{}],
                        "sent_count": 1,
                        "plan": {"message_target_username": "@alice_test"},
                        "messages": [{"index": 1, "text": "Привет", "sent": True}],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (run_dir / "plan.json").write_text("{}", encoding="utf-8")
            (run_dir / "after.png").write_text("png", encoding="utf-8")
            state_path = root / "session_state.json"
            state_path.write_text("{}", encoding="utf-8")
            runtime_root = root / "runtime_configs"
            runtime_root.mkdir()
            runtime_config = runtime_root / "20260504T111811Z-7723a42a-2de67ebe.json"
            runtime_config.write_text("{}", encoding="utf-8")

            start_job(
                tool_id="telegram_session_runner",
                workflow_kind="session_run",
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                phase="stopped",
                status="completed",
                summary="Session done",
                context={
                    "last_runtime_config_path": str(runtime_config),
                    "last_session_state_path": str(state_path),
                    "last_session_runs_dir": str(runs_dir),
                },
                steps=[
                    {
                        "step_id": "session-step-1",
                        "step_index": 0,
                        "step_code": "2",
                        "step_kind": "session_run",
                        "status": "completed",
                        "summary": "Session step done",
                        "started_at": "2026-05-04T11:18:11Z",
                        "completed_at": "2026-05-04T11:18:19Z",
                    }
                ],
                index_path=index_path,
            )

            with mock.patch(
                "tool_platform.telegram_gui_helpers.session_history_snapshot",
                return_value={
                    "status": "ready",
                    "state_file": str(state_path),
                    "runs_dir": str(runs_dir),
                    "messages_sent_total": 7,
                    "message_cursor": 3,
                    "message_target_cursor": 1,
                    "history": [],
                    "latest_runs": [],
                    "last_run": {},
                },
            ), mock.patch("tool_platform.jobs._session_runtime_config_root", return_value=runtime_root):
                workspace = profile_workspace_snapshot(
                    profile_name="AK",
                    profile_dir="/home/max/TelegramPortableAK",
                    index_path=index_path,
                )

        self.assertEqual(workspace["session_snapshot"]["last_run"]["path"], str(run_json))
        self.assertEqual(workspace["session_snapshot"]["messages_sent_total"], 7)
        self.assertEqual(workspace["session_snapshot"]["message_cursor"], 3)
        self.assertEqual(workspace["session_snapshot"]["history_source"], "unified_jobs+state_fallback")
        self.assertEqual(workspace["session_snapshot"]["progress_summary"]["status"], "completed")
        self.assertEqual(workspace["session_snapshot"]["progress_summary"]["history_source"], "unified_jobs+state_fallback")
        self.assertEqual(workspace["artifact_shortcuts"]["session_run"], str(run_json))
        self.assertEqual(workspace["artifact_shortcuts"]["screenshot"], str(run_dir / "after.png"))

    def test_profile_workspace_snapshot_builds_session_progress_summary_for_running_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            index_path = root / "jobs" / "index.json"
            started = start_job(
                tool_id="telegram_session_runner",
                workflow_kind="session_run",
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                phase="session_running",
                status="running",
                summary="Session running",
                context={
                    "continuous_session": False,
                    "session_baseline_sent_total": 5,
                    "session_target_sent_total": 8,
                    "message_settings": {
                        "messages_per_cycle": 3,
                        "total_message_limit": 10,
                        "message_targets": [{"label": "@alice_test"}],
                        "message_templates": ["Привет!"],
                    },
                },
                index_path=index_path,
            )
            payload = json.loads(index_path.read_text(encoding="utf-8"))
            payload["jobs"][0]["started_at"] = "2020-05-08T09:00:00Z"
            payload["jobs"][0]["updated_at"] = "2020-05-08T09:00:30Z"
            index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            with mock.patch(
                "tool_platform.telegram_gui_helpers.session_history_snapshot",
                return_value={
                    "status": "ready",
                    "state_file": str(root / "session_state.json"),
                    "runs_dir": str(root / "runs"),
                    "messages_sent_total": 6,
                    "message_cursor": 0,
                    "message_target_cursor": 0,
                    "history": [],
                    "latest_runs": [],
                    "last_run": {},
                },
            ):
                workspace = profile_workspace_snapshot(
                    profile_name="AK",
                    profile_dir="/home/max/TelegramPortableAK",
                    index_path=index_path,
                )

        progress = workspace["session_snapshot"]["progress_summary"]
        self.assertEqual(progress["status"], "running")
        self.assertEqual(progress["processed_count"], 1)
        self.assertEqual(progress["selected_target"], 3)
        self.assertEqual(progress["remaining_in_run"], 2)
        self.assertEqual(progress["current_target_label"], "@alice_test")
        self.assertEqual(progress["current_template_preview"], "Привет!")
        self.assertEqual(progress["run_mode"], "bounded")
        self.assertEqual(progress["eta_mode"], "bounded")
        self.assertIn(progress["eta_reason"], {"bounded_target", "insufficient_rate"})

    def test_profile_workspace_snapshot_exposes_session_artifacts_and_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            index_path = root / "jobs" / "index.json"
            state_path = root / "session_state.json"
            runs_dir = root / "runs"
            run_dir = runs_dir / "20260504T080201Z-e8f2e87d"
            runtime_config = root / "runtime_config.json"
            run_dir.mkdir(parents=True)
            state_path.write_text(
                json.dumps(
                    {
                        "messages_sent_total": 4,
                        "message_cursor": 1,
                        "message_target_cursor": 0,
                        "history": [],
                    }
                ),
                encoding="utf-8",
            )
            runtime_config.write_text("{}", encoding="utf-8")
            run_json = run_dir / "run.json"
            run_json.write_text(
                json.dumps(
                    {
                        "run_id": run_dir.name,
                        "status": "completed",
                        "visits": [{"username": "@alice_test"}],
                        "sent_count": 1,
                        "plan": {"message_target_username": "@alice_test"},
                        "messages": [{"index": 1, "text": "Привет", "sent": True, "send_mode": "auto"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (run_dir / "plan.json").write_text("{}", encoding="utf-8")
            (run_dir / "after.png").write_text("png", encoding="utf-8")
            start_job(
                tool_id="telegram_session_runner",
                workflow_kind="session_run",
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                phase="stopped",
                status="completed",
                summary="Session done",
                artifact_paths={
                    "state_path": str(state_path),
                    "runs_dir": str(runs_dir),
                    "runtime_config": str(runtime_config),
                    "session_run": str(run_json),
                },
                context={
                    "message_settings": {
                        "messages_per_cycle": 1,
                        "message_targets": [{"label": "@alice_test"}],
                        "message_templates": ["Привет"],
                    }
                },
                index_path=index_path,
            )

            with mock.patch(
                "tool_platform.telegram_gui_helpers.session_history_snapshot",
                return_value={
                    "status": "ready",
                    "state_file": str(state_path),
                    "runs_dir": str(runs_dir),
                    "messages_sent_total": 4,
                    "message_cursor": 1,
                    "message_target_cursor": 0,
                    "history": [],
                    "latest_runs": [],
                    "last_run": {},
                },
            ):
                workspace = profile_workspace_snapshot(
                    profile_name="AK",
                    profile_dir="/home/max/TelegramPortableAK",
                    index_path=index_path,
                )

        bucket = workspace["workflow_buckets"]["session_run"]
        shortcuts = bucket["artifact_shortcuts"]
        self.assertEqual(shortcuts["session_run"], str(run_json))
        self.assertEqual(shortcuts["run_dir"], str(run_dir))
        self.assertEqual(shortcuts["plan_json"], str(run_dir / "plan.json"))
        self.assertEqual(shortcuts["runtime_config"], str(runtime_config))
        self.assertEqual(shortcuts["state_path"], str(state_path))
        self.assertEqual(shortcuts["screenshot"], str(run_dir / "after.png"))
        self.assertEqual(bucket["artifact_provenance"]["session_run"], "stored")
        self.assertEqual(bucket["progress_summary"]["artifact_status"]["status"], "complete")
        self.assertEqual(workspace["artifact_shortcuts"]["plan_json"], str(run_dir / "plan.json"))
        self.assertEqual(workspace["artifact_shortcuts"]["runtime_config"], str(runtime_config))
        self.assertEqual(workspace["artifact_shortcuts"]["state_path"], str(state_path))

    def test_profile_workspace_snapshot_uses_session_history_for_idle_progress_preview(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            index_path = root / "jobs" / "index.json"
            state_path = root / "session_state.json"
            runs_dir = root / "runs"
            with mock.patch(
                "tool_platform.telegram_gui_helpers.session_history_snapshot",
                return_value={
                    "status": "ready",
                    "state_file": str(state_path),
                    "runs_dir": str(runs_dir),
                    "messages_sent_total": 9,
                    "message_cursor": 12,
                    "message_target_cursor": 11,
                    "history": [],
                    "latest_runs": [],
                    "last_run": {
                        "run_id": "last-run",
                        "message_target_username": "@history_target",
                        "sent_preview": ["Исторический шаблон"],
                        "draft_preview": [],
                    },
                },
            ):
                workspace = profile_workspace_snapshot(
                    profile_name="AK",
                    profile_dir="/home/max/TelegramPortableAK",
                    index_path=index_path,
                )

        progress = workspace["workflow_buckets"]["session_run"]["progress_summary"]
        self.assertEqual(progress["current_target_label"], "@history_target")
        self.assertEqual(progress["current_template_preview"], "Исторический шаблон")
        self.assertEqual(progress["next_action_text"], "Подготовить и запустить session_run workflow.")

    def test_profile_workspace_snapshot_marks_continuous_session_eta_and_combined_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            index_path = root / "jobs" / "index.json"
            start_job(
                tool_id="telegram_session_runner",
                workflow_kind="session_run",
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                phase="session_running",
                status="running",
                summary="Session continuous",
                context={
                    "continuous_session": True,
                    "session_baseline_sent_total": 1,
                    "message_settings": {
                        "messages_per_cycle": 2,
                        "message_targets": [{"label": "@alice_test"}],
                        "message_templates": ["Привет"],
                    },
                },
                index_path=index_path,
            )
            start_job(
                tool_id="telegram_combined_flow",
                workflow_kind="combined_pattern",
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                phase="session_running",
                status="running",
                summary="Combined running",
                context={
                    "phase": "session_running",
                    "step_pattern": "12",
                    "step_cursor": 1,
                    "continuous_session": True,
                },
                index_path=index_path,
            )

            with mock.patch(
                "tool_platform.telegram_gui_helpers.session_history_snapshot",
                return_value={
                    "status": "ready",
                    "state_file": str(root / "session_state.json"),
                    "runs_dir": str(root / "runs"),
                    "messages_sent_total": 2,
                    "message_cursor": 0,
                    "message_target_cursor": 0,
                    "history": [],
                    "latest_runs": [],
                    "last_run": {},
                },
            ):
                workspace = profile_workspace_snapshot(
                    profile_name="AK",
                    profile_dir="/home/max/TelegramPortableAK",
                    index_path=index_path,
                )

        session_progress = workspace["workflow_buckets"]["session_run"]["progress_summary"]
        self.assertEqual(session_progress["eta_mode"], "continuous")
        self.assertFalse(session_progress["eta_available"])
        self.assertEqual(session_progress["eta_reason"], "continuous_session")
        combined_progress = workspace["workflow_buckets"]["combined_pattern"]["progress_summary"]
        self.assertEqual(combined_progress["child_progress"]["run_mode"], "continuous")
        self.assertTrue(combined_progress["pattern_advancement_blocked"])
        self.assertIn("ручного Стопа", combined_progress["pattern_advancement_blocker"])

    def test_repair_session_artifacts_apply_backfills_standalone_parent_from_latest_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            index_path = root / "jobs" / "index.json"
            runs_dir = root / "runs"
            runs_dir.mkdir()
            run_dir_1 = runs_dir / "20260504T111048Z-116d3278"
            run_dir_2 = runs_dir / "20260504T111051Z-fe0c1d48"
            for run_dir, text in ((run_dir_1, "Черновик"), (run_dir_2, "Финал")):
                run_dir.mkdir()
                (run_dir / "run.json").write_text(
                    json.dumps(
                        {
                            "run_id": run_dir.name,
                            "status": "stopped",
                            "visits": [],
                            "sent_count": 0,
                            "plan": {"message_target_username": "@alice_test"},
                            "messages": [{"index": 1, "text": text, "sent": False}],
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                (run_dir / "plan.json").write_text("{}", encoding="utf-8")
                (run_dir / "after.png").write_text("png", encoding="utf-8")
            state_path = root / "session_state.json"
            state_path.write_text("{}", encoding="utf-8")
            runtime_root = root / "runtime_configs"
            runtime_root.mkdir()
            runtime_config_1 = runtime_root / "20260504T111047Z-31b86371-51661910.json"
            runtime_config_2 = runtime_root / "20260504T111047Z-31b86371-5fba47d7.json"
            runtime_config_1.write_text("{}", encoding="utf-8")
            runtime_config_2.write_text("{}", encoding="utf-8")

            started = start_job(
                tool_id="telegram_session_runner",
                workflow_kind="session_run",
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                phase="stopped",
                status="stopped",
                summary="Session stopped",
                context={
                    "last_runtime_config_path": str(runtime_config_2),
                    "last_session_state_path": str(state_path),
                    "last_session_runs_dir": str(runs_dir),
                    "recent_step": {
                        "step_id": "legacy-step-2",
                        "artifact_paths": {},
                    },
                },
                steps=[
                    {
                        "step_id": "legacy-step-1",
                        "step_index": 0,
                        "step_code": "2",
                        "step_kind": "session_run",
                        "status": "stopped",
                        "summary": "Первый прогон",
                        "started_at": "2026-05-04T11:10:47Z",
                        "completed_at": "2026-05-04T11:10:50Z",
                    },
                    {
                        "step_id": "legacy-step-2",
                        "step_index": 1,
                        "step_code": "2",
                        "step_kind": "session_run",
                        "status": "stopped",
                        "summary": "Второй прогон",
                        "started_at": "2026-05-04T11:10:51Z",
                        "completed_at": "2026-05-04T11:10:53Z",
                    },
                ],
                index_path=index_path,
            )

            with mock.patch("tool_platform.jobs._session_runtime_config_root", return_value=runtime_root):
                preview = repair_session_artifacts(job_id=started["job_id"], apply=False, index_path=index_path)
                preview_job = get_job(started["job_id"], index_path=index_path)
                applied = repair_session_artifacts(job_id=started["job_id"], apply=True, index_path=index_path)
                repaired_job = get_job(started["job_id"], index_path=index_path)

        assert preview_job is not None
        assert repaired_job is not None
        self.assertFalse(preview["changed"])
        self.assertEqual(preview_job["artifact_paths"], {})
        self.assertTrue(preview["repaired_steps"])
        self.assertTrue(applied["changed"])
        self.assertEqual(repaired_job["artifact_paths"]["run_dir"], str(run_dir_2))
        self.assertEqual(repaired_job["artifact_paths"]["session_run"], str(run_dir_2 / "run.json"))
        self.assertEqual(repaired_job["artifact_paths"]["runtime_config"], str(runtime_config_2))
        self.assertEqual(repaired_job["context"]["last_session_run_dir"], str(run_dir_2))
        self.assertEqual(repaired_job["context"]["recent_step"]["artifact_paths"]["run_dir"], str(run_dir_2))
        self.assertEqual(repaired_job["steps"][0]["artifact_paths"]["run_dir"], str(run_dir_1))
        self.assertEqual(repaired_job["steps"][1]["artifact_paths"]["run_dir"], str(run_dir_2))

    def test_repair_session_artifacts_keeps_combined_parent_invite_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            index_path = root / "jobs" / "index.json"
            runs_dir = root / "runs"
            runs_dir.mkdir()
            session_run_dir = runs_dir / "20260504T080201Z-e8f2e87d"
            session_run_dir.mkdir()
            run_json = session_run_dir / "run.json"
            run_json.write_text(
                json.dumps(
                    {
                        "run_id": session_run_dir.name,
                        "status": "completed",
                        "visits": [],
                        "sent_count": 0,
                        "plan": {"message_target_username": "@alice_test"},
                        "messages": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (session_run_dir / "plan.json").write_text("{}", encoding="utf-8")
            state_path = root / "session_state.json"
            state_path.write_text("{}", encoding="utf-8")
            runtime_root = root / "runtime_configs"
            runtime_root.mkdir()
            runtime_config = runtime_root / "20260504T080131Z-b86acee2-11111111.json"
            runtime_config.write_text("{}", encoding="utf-8")

            started = start_job(
                tool_id="telegram_combined_flow",
                workflow_kind="combined_pattern",
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                phase="stopped",
                status="completed",
                summary="Combined done",
                artifact_paths={"job_dir": "/tmp/invite-job", "run_dir": "/tmp/invite-job/executions/20260504T080131Z"},
                context={
                    "last_runtime_config_path": str(runtime_config),
                    "last_session_state_path": str(state_path),
                    "last_session_runs_dir": str(runs_dir),
                },
                steps=[
                    {
                        "step_id": "combined-invite",
                        "step_index": 0,
                        "step_code": "1",
                        "step_kind": "invite_batch",
                        "status": "completed",
                        "summary": "Invite done",
                        "started_at": "2026-05-04T08:01:31Z",
                        "completed_at": "2026-05-04T08:01:33Z",
                        "artifact_paths": {"job_dir": "/tmp/invite-job"},
                    },
                    {
                        "step_id": "combined-session",
                        "step_index": 1,
                        "step_code": "2",
                        "step_kind": "session_run",
                        "status": "completed",
                        "summary": "Session done",
                        "started_at": "2026-05-04T08:02:01Z",
                        "completed_at": "2026-05-04T08:02:10Z",
                    },
                ],
                index_path=index_path,
            )

            with mock.patch("tool_platform.jobs._session_runtime_config_root", return_value=runtime_root):
                report = repair_session_artifacts(job_id=started["job_id"], apply=True, index_path=index_path)
                repaired_job = get_job(started["job_id"], index_path=index_path)
                aggregated_artifacts = workflow_artifact_index(started["job_id"], index_path=index_path)

        assert repaired_job is not None
        self.assertTrue(report["changed"])
        self.assertEqual(repaired_job["artifact_paths"]["job_dir"], "/tmp/invite-job")
        self.assertEqual(repaired_job["artifact_paths"]["run_dir"], "/tmp/invite-job/executions/20260504T080131Z")
        session_step = next(step for step in repaired_job["steps"] if step["step_id"] == "combined-session")
        self.assertEqual(session_step["artifact_paths"]["run_dir"], str(session_run_dir))
        self.assertEqual(session_step["artifact_paths"]["session_run"], str(run_json))
        self.assertEqual(aggregated_artifacts["session_run"], str(run_json))

    def test_repair_session_artifacts_leaves_ambiguous_session_match_unresolved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            index_path = root / "jobs" / "index.json"
            runs_dir = root / "runs"
            runs_dir.mkdir()
            for suffix in ("aaa11111", "bbb22222"):
                run_dir = runs_dir / f"20260504T111811Z-{suffix}"
                run_dir.mkdir()
                (run_dir / "run.json").write_text("{}", encoding="utf-8")
            state_path = root / "session_state.json"
            state_path.write_text("{}", encoding="utf-8")

            started = start_job(
                tool_id="telegram_session_runner",
                workflow_kind="session_run",
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                phase="stopped",
                status="completed",
                summary="Ambiguous session",
                context={
                    "last_session_state_path": str(state_path),
                    "last_session_runs_dir": str(runs_dir),
                },
                steps=[
                    {
                        "step_id": "ambiguous-step",
                        "step_index": 0,
                        "step_code": "2",
                        "step_kind": "session_run",
                        "status": "completed",
                        "summary": "Ambiguous run",
                        "started_at": "2026-05-04T11:18:11Z",
                        "completed_at": "2026-05-04T11:18:12Z",
                    }
                ],
                index_path=index_path,
            )

            report = repair_session_artifacts(job_id=started["job_id"], apply=False, index_path=index_path)
            repaired_job = get_job(started["job_id"], index_path=index_path)

        assert repaired_job is not None
        self.assertFalse(report["changed"])
        self.assertFalse(report["repaired_steps"])
        self.assertTrue(report["unresolved"])
        self.assertEqual(repaired_job["steps"][0]["artifact_paths"], {})

    def test_repair_invite_artifacts_apply_canonicalizes_parent_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            index_path = root / "jobs" / "index.json"
            legacy_root = root / "legacy-invite-jobs"
            canonical_root = root / "runtime" / "telegram" / "invite_jobs"
            legacy_job_dir = legacy_root / "contact_add__AK3__sample"
            canonical_job_dir = canonical_root / legacy_job_dir.name
            run_dir = canonical_job_dir / "executions" / "20260508T090000Z"
            run_dir.mkdir(parents=True)
            (canonical_job_dir / "invite_state.json").write_text("{}", encoding="utf-8")
            (run_dir / "batch_progress.json").write_text("{}", encoding="utf-8")
            batch_json = run_dir / "batch_contact_add.json"
            batch_json.write_text("{}", encoding="utf-8")
            execution_record = run_dir / "execution_record.json"
            execution_record.write_text("{}", encoding="utf-8")
            log_path = run_dir / "batch_contact_add.log"
            log_path.write_text("log", encoding="utf-8")

            started = start_job(
                tool_id="telegram_invite_manager",
                workflow_kind="invite_batch",
                profile_name="AK3",
                profile_dir="/home/max/site-control-kit/runtime/telegram/profiles/TelegramPortable-AK3",
                phase="stopped",
                status="completed",
                summary="Invite done",
                artifact_paths={"job_dir": str(legacy_job_dir)},
                context={
                    "invite_job_dir": str(legacy_job_dir),
                    "last_invite_run_dir": str(legacy_job_dir / "executions" / run_dir.name),
                },
                index_path=index_path,
            )

            with mock.patch("tool_platform.telegram_gui_helpers.LEGACY_INVITE_JOBS_ROOT", legacy_root), mock.patch(
                "tool_platform.telegram_gui_helpers.DEFAULT_INVITE_OUTPUT_ROOT",
                canonical_root,
            ):
                preview = repair_invite_artifacts(job_id=started["job_id"], apply=False, index_path=index_path)
                preview_job = get_job(started["job_id"], index_path=index_path)
                applied = repair_invite_artifacts(job_id=started["job_id"], apply=True, index_path=index_path)
                repaired_job = get_job(started["job_id"], index_path=index_path)

        assert preview_job is not None
        assert repaired_job is not None
        self.assertFalse(preview["changed"])
        self.assertEqual(preview_job["artifact_paths"]["job_dir"], str(legacy_job_dir))
        self.assertTrue(applied["changed"])
        self.assertEqual(repaired_job["artifact_paths"]["job_dir"], str(canonical_job_dir))
        self.assertEqual(repaired_job["artifact_paths"]["run_dir"], str(run_dir))
        self.assertEqual(repaired_job["artifact_paths"]["batch_json"], str(batch_json))
        self.assertEqual(repaired_job["artifact_paths"]["execution_record"], str(execution_record))
        self.assertEqual(repaired_job["artifact_paths"]["log_path"], str(log_path))
        self.assertEqual(repaired_job["context"]["invite_job_dir"], str(canonical_job_dir))
        self.assertEqual(repaired_job["context"]["last_invite_run_dir"], str(run_dir))

    def test_repair_invite_artifacts_keeps_combined_parent_session_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            index_path = root / "jobs" / "index.json"
            legacy_root = root / "legacy-invite-jobs"
            canonical_root = root / "runtime" / "telegram" / "invite_jobs"
            legacy_job_dir = legacy_root / "contact_add__AK3__sample"
            canonical_job_dir = canonical_root / legacy_job_dir.name
            run_dir = canonical_job_dir / "executions" / "20260508T090500Z"
            run_dir.mkdir(parents=True)
            (canonical_job_dir / "invite_state.json").write_text("{}", encoding="utf-8")
            batch_json = run_dir / "batch_contact_add.json"
            batch_json.write_text("{}", encoding="utf-8")

            started = start_job(
                tool_id="telegram_combined_flow",
                workflow_kind="combined_pattern",
                profile_name="AK3",
                profile_dir="/home/max/site-control-kit/runtime/telegram/profiles/TelegramPortable-AK3",
                phase="stopped",
                status="completed",
                summary="Combined done",
                artifact_paths={"session_run": "/tmp/session-run/run.json"},
                context={
                    "invite_job_dir": str(legacy_job_dir),
                    "recent_step": {"step_kind": "invite_batch", "artifact_paths": {}},
                },
                steps=[
                    {
                        "step_id": "combined-invite",
                        "step_index": 0,
                        "step_code": "1",
                        "step_kind": "invite_batch",
                        "status": "completed",
                        "summary": "Invite step done",
                        "started_at": "2026-05-08T09:05:00Z",
                        "completed_at": "2026-05-08T09:05:10Z",
                    }
                ],
                index_path=index_path,
            )

            with mock.patch("tool_platform.telegram_gui_helpers.LEGACY_INVITE_JOBS_ROOT", legacy_root), mock.patch(
                "tool_platform.telegram_gui_helpers.DEFAULT_INVITE_OUTPUT_ROOT",
                canonical_root,
            ):
                report = repair_invite_artifacts(job_id=started["job_id"], apply=True, index_path=index_path)
                repaired_job = get_job(started["job_id"], index_path=index_path)

        assert repaired_job is not None
        self.assertTrue(report["changed"])
        self.assertEqual(repaired_job["artifact_paths"]["session_run"], "/tmp/session-run/run.json")
        self.assertEqual(repaired_job["artifact_paths"]["job_dir"], str(canonical_job_dir))
        self.assertEqual(repaired_job["context"]["invite_job_dir"], str(canonical_job_dir))
        self.assertEqual(repaired_job["steps"][0]["artifact_paths"]["batch_json"], str(batch_json))

    def test_repair_historical_artifacts_dry_run_combines_session_and_invite_without_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            index_path = root / "jobs" / "index.json"
            legacy_root = root / "legacy-invite-jobs"
            canonical_root = root / "runtime" / "telegram" / "invite_jobs"
            legacy_job_dir = legacy_root / "contact_add__AK__sample"
            canonical_job_dir = canonical_root / legacy_job_dir.name
            invite_run_dir = canonical_job_dir / "executions" / "20260508T090500Z"
            invite_run_dir.mkdir(parents=True)
            (canonical_job_dir / "invite_state.json").write_text("{}", encoding="utf-8")
            invite_batch_json = invite_run_dir / "batch_contact_add.json"
            invite_batch_json.write_text("{}", encoding="utf-8")

            session_runs_dir = root / "session-runs"
            session_run_dir = session_runs_dir / "20260508T090600Z-abcdef12"
            session_run_dir.mkdir(parents=True)
            session_run_json = session_run_dir / "run.json"
            session_run_json.write_text(
                json.dumps(
                    {
                        "run_id": session_run_dir.name,
                        "status": "completed",
                        "visits": [],
                        "sent_count": 0,
                        "plan": {"message_target_username": "@alice_test"},
                        "messages": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (session_run_dir / "plan.json").write_text("{}", encoding="utf-8")
            session_state_path = root / "session_state.json"
            session_state_path.write_text("{}", encoding="utf-8")
            runtime_root = root / "runtime-configs"
            runtime_root.mkdir()
            runtime_config = runtime_root / "20260508T090500Z-combined-11111111.json"
            runtime_config.write_text("{}", encoding="utf-8")

            started = start_job(
                tool_id="telegram_combined_flow",
                workflow_kind="combined_pattern",
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                phase="stopped",
                status="completed",
                summary="Combined legacy done",
                artifact_paths={"job_dir": str(legacy_job_dir)},
                context={
                    "invite_job_dir": str(legacy_job_dir),
                    "last_runtime_config_path": str(runtime_config),
                    "last_session_state_path": str(session_state_path),
                    "last_session_runs_dir": str(session_runs_dir),
                },
                steps=[
                    {
                        "step_id": "combined-invite",
                        "step_index": 0,
                        "step_code": "1",
                        "step_kind": "invite_batch",
                        "status": "completed",
                        "summary": "Invite step done",
                        "started_at": "2026-05-08T09:05:00Z",
                        "completed_at": "2026-05-08T09:05:10Z",
                    },
                    {
                        "step_id": "combined-session",
                        "step_index": 1,
                        "step_code": "2",
                        "step_kind": "session_run",
                        "status": "completed",
                        "summary": "Session step done",
                        "started_at": "2026-05-08T09:06:00Z",
                        "completed_at": "2026-05-08T09:06:10Z",
                    },
                ],
                index_path=index_path,
            )

            with mock.patch("tool_platform.telegram_gui_helpers.LEGACY_INVITE_JOBS_ROOT", legacy_root), mock.patch(
                "tool_platform.telegram_gui_helpers.DEFAULT_INVITE_OUTPUT_ROOT",
                canonical_root,
            ), mock.patch("tool_platform.jobs._session_runtime_config_root", return_value=runtime_root):
                report = repair_historical_artifacts(job_id=started["job_id"], apply=False, index_path=index_path)
                preview_job = get_job(started["job_id"], index_path=index_path)

        assert preview_job is not None
        self.assertFalse(report["changed"])
        self.assertTrue(report["would_change"])
        self.assertEqual(report["repair_counts"]["total"]["matched_jobs"], 1)
        self.assertGreaterEqual(report["repair_counts"]["session"]["repaired_steps"], 1)
        self.assertGreaterEqual(report["repair_counts"]["invite"]["repaired_steps"], 1)
        self.assertTrue(report["session_report"]["repaired_steps"])
        self.assertTrue(report["invite_report"]["repaired_steps"])
        self.assertEqual(preview_job["artifact_paths"]["job_dir"], str(legacy_job_dir))
        self.assertEqual(preview_job["steps"][0]["artifact_paths"], {})
        self.assertEqual(preview_job["steps"][1]["artifact_paths"], {})
        self.assertEqual(report["session_report"]["repaired_steps"][0]["artifact_paths"]["session_run"], str(session_run_json))
        self.assertEqual(report["invite_report"]["repaired_steps"][0]["artifact_paths"]["batch_json"], str(invite_batch_json))

    def test_repair_historical_artifacts_keeps_ambiguous_session_unresolved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            index_path = root / "jobs" / "index.json"
            runs_dir = root / "runs"
            runs_dir.mkdir()
            for suffix in ("aaa11111", "bbb22222"):
                run_dir = runs_dir / f"20260504T111811Z-{suffix}"
                run_dir.mkdir()
                (run_dir / "run.json").write_text("{}", encoding="utf-8")
            state_path = root / "session_state.json"
            state_path.write_text("{}", encoding="utf-8")

            started = start_job(
                tool_id="telegram_session_runner",
                workflow_kind="session_run",
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                phase="stopped",
                status="completed",
                summary="Ambiguous session",
                context={
                    "last_session_state_path": str(state_path),
                    "last_session_runs_dir": str(runs_dir),
                },
                steps=[
                    {
                        "step_id": "ambiguous-step",
                        "step_index": 0,
                        "step_code": "2",
                        "step_kind": "session_run",
                        "status": "completed",
                        "summary": "Ambiguous run",
                        "started_at": "2026-05-04T11:18:11Z",
                        "completed_at": "2026-05-04T11:18:12Z",
                    }
                ],
                index_path=index_path,
            )

            report = repair_historical_artifacts(job_id=started["job_id"], apply=False, index_path=index_path)

        self.assertFalse(report["would_change"])
        self.assertGreaterEqual(report["repair_counts"]["total"]["unresolved"], 1)
        self.assertTrue(any(item["source"] == "session" for item in report["unresolved"]))

    def test_profile_history_groups_preserve_unified_step_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            index_path = Path(tmp_dir) / "jobs" / "index.json"
            started = start_job(
                tool_id="telegram_combined_flow",
                workflow_kind="combined_pattern",
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                phase="contact_add",
                status="running",
                summary="Combined running",
                steps=[
                    {
                        "step_id": "step-1",
                        "step_index": 0,
                        "step_code": "1",
                        "step_kind": "invite_batch",
                        "status": "completed",
                        "summary": "Contact batch done",
                        "started_at": "2026-05-04T08:00:00Z",
                        "completed_at": "2026-05-04T08:00:02Z",
                    },
                    {
                        "step_id": "step-2",
                        "step_index": 1,
                        "step_code": "2",
                        "step_kind": "session_run",
                        "status": "running",
                        "summary": "Session running",
                        "started_at": "2026-05-04T08:00:03Z",
                        "completed_at": "",
                    },
                ],
                index_path=index_path,
            )

            groups = profile_history_groups(
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                limit=3,
                step_limit=4,
                index_path=index_path,
            )

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["job"]["job_id"], started["job_id"])
        self.assertEqual([step["step_code"] for step in groups[0]["steps"]], ["1", "2"])

    def test_list_jobs_accepts_profile_filters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            index_path = Path(tmp_dir) / "jobs" / "index.json"
            start_job(
                tool_id="telegram_invite_manager",
                workflow_kind="invite_batch",
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                phase="stopped",
                status="completed",
                summary="Invite done",
                index_path=index_path,
            )
            start_job(
                tool_id="telegram_session_runner",
                workflow_kind="session_run",
                profile_name="BK",
                profile_dir="/home/max/TelegramPortableBK",
                phase="stopped",
                status="completed",
                summary="Session done",
                index_path=index_path,
            )

            by_name = list_jobs(profile_name="AK", index_path=index_path)
            by_dir = list_jobs(profile_dir="/home/max/TelegramPortableBK", index_path=index_path)

        self.assertEqual(len(by_name), 1)
        self.assertEqual(by_name[0]["profile_name"], "AK")
        self.assertEqual(len(by_dir), 1)
        self.assertEqual(by_dir[0]["profile_name"], "BK")

    def test_cli_list_jobs_supports_workspace_filters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            index_path = Path(tmp_dir) / "jobs" / "index.json"
            start_job(
                tool_id="telegram_session_runner",
                workflow_kind="session_run",
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                phase="stopped",
                status="completed",
                summary="Session done",
                index_path=index_path,
            )
            stdout = io.StringIO()
            with mock.patch("tool_platform.cli.list_jobs") as list_jobs_mock, redirect_stdout(stdout):
                list_jobs_mock.side_effect = lambda **kwargs: list_jobs(index_path=index_path, **kwargs)
                exit_code = cli_main(["list-jobs", "--profile-name", "AK", "--workflow-kind", "session_run", "--limit", "5"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(len(payload["jobs"]), 1)
        self.assertEqual(payload["jobs"][0]["workflow_kind"], "session_run")

    def test_cli_repair_session_artifacts_supports_apply_flag(self) -> None:
        stdout = io.StringIO()
        with mock.patch(
            "tool_platform.cli.repair_session_artifacts",
            return_value={
                "status": "completed",
                "matched_jobs": ["job-1"],
                "matched_steps": [],
                "repaired_jobs": [],
                "repaired_steps": [],
                "unresolved": [],
            },
        ) as repair_mock, redirect_stdout(stdout):
            exit_code = cli_main(["repair-session-artifacts", "--job-id", "job-1", "--apply"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        repair_mock.assert_called_once_with(job_id="job-1", profile_name=None, profile_dir=None, apply=True)
        self.assertEqual(payload["matched_jobs"], ["job-1"])

    def test_cli_repair_invite_artifacts_supports_apply_flag(self) -> None:
        stdout = io.StringIO()
        with mock.patch(
            "tool_platform.cli.repair_invite_artifacts",
            return_value={
                "status": "completed",
                "matched_jobs": ["job-2"],
                "matched_steps": [],
                "repaired_jobs": [],
                "repaired_steps": [],
                "unresolved": [],
            },
        ) as repair_mock, redirect_stdout(stdout):
            exit_code = cli_main(["repair-invite-artifacts", "--job-id", "job-2", "--apply"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        repair_mock.assert_called_once_with(job_id="job-2", profile_name=None, profile_dir=None, apply=True)
        self.assertEqual(payload["matched_jobs"], ["job-2"])

    def test_cli_repair_historical_artifacts_supports_filters_and_apply_flag(self) -> None:
        stdout = io.StringIO()
        with mock.patch(
            "tool_platform.cli.repair_historical_artifacts",
            return_value={
                "status": "completed",
                "apply": True,
                "would_change": True,
                "matched_jobs": ["job-3"],
                "repair_counts": {},
                "session_report": {},
                "invite_report": {},
                "unresolved": [],
            },
        ) as repair_mock, redirect_stdout(stdout):
            exit_code = cli_main(
                [
                    "repair-historical-artifacts",
                    "--job-id",
                    "job-3",
                    "--profile-name",
                    "AK",
                    "--profile-dir",
                    "/home/max/TelegramPortableAK",
                    "--apply",
                ]
            )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        repair_mock.assert_called_once_with(
            job_id="job-3",
            profile_name="AK",
            profile_dir="/home/max/TelegramPortableAK",
            apply=True,
        )
        self.assertTrue(payload["would_change"])

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

    def test_format_workflow_timeline_includes_summary_and_times(self) -> None:
        text = format_workflow_timeline(
            {
                "job_id": "job-1",
                "status": "stopped",
                "phase": "stopped",
                "steps": [
                    {
                        "step_index": 0,
                        "step_code": "1",
                        "step_kind": "invite_batch",
                        "status": "completed",
                        "summary": "Добавление завершено",
                        "started_at": "2026-05-04T07:00:00Z",
                        "completed_at": "2026-05-04T07:00:05Z",
                    }
                ],
            }
        )

        self.assertIn("Добавление завершено", text)
        self.assertIn("2026-05-04T07:00:00Z -> 2026-05-04T07:00:05Z", text)

    def test_plan_and_run_invite_workflow_generates_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            index_path = Path(tmp_dir) / "jobs" / "index.json"
            with mock.patch("tool_platform.workflows._build_invite_batch_command") as builder, mock.patch(
                "tool_platform.workflows._invite_execution_id_for_job",
                return_value="20260508T110000Z",
            ):
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
                job = get_job(planned["job_id"], index_path=index_path)

        self.assertEqual(execution["status"], "ready")
        self.assertEqual(execution["command"].argv, ["python3", "invite.py"])
        self.assertEqual(execution["step"]["step_kind"], "invite_batch")
        self.assertEqual(
            execution["step"]["artifact_paths"]["progress_json"],
            "/tmp/job/executions/20260508T110000Z/batch_progress.json",
        )
        assert job is not None
        self.assertEqual(job["context"]["invite_execution_id"], "20260508T110000Z")
        self.assertEqual(job["context"]["last_invite_run_dir"], "/tmp/job/executions/20260508T110000Z")

    def test_plan_and_run_invite_workflow_normalizes_legacy_job_dir_to_canonical_twin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            index_path = root / "jobs" / "index.json"
            legacy_root = root / "legacy-invite-jobs"
            canonical_root = root / "runtime" / "telegram" / "invite_jobs"
            legacy_job_dir = legacy_root / "contact_add__AK3__sample"
            canonical_job_dir = canonical_root / legacy_job_dir.name
            canonical_job_dir.mkdir(parents=True)
            with mock.patch("tool_platform.telegram_gui_helpers.LEGACY_INVITE_JOBS_ROOT", legacy_root), mock.patch(
                "tool_platform.telegram_gui_helpers.DEFAULT_INVITE_OUTPUT_ROOT",
                canonical_root,
            ), mock.patch("tool_platform.workflows._build_invite_batch_command") as builder, mock.patch(
                "tool_platform.workflows._invite_execution_id_for_job",
                return_value="20260508T110500Z",
            ):
                builder.return_value = WorkflowCommandSpec(argv=["python3", "invite.py"], cwd=root)
                planned = plan_workflow(
                    workflow_kind="invite_batch",
                    tool_id="telegram_invite_manager",
                    profile_name="AK3",
                    profile_dir="/home/max/site-control-kit/runtime/telegram/profiles/TelegramPortable-AK3",
                    context={"invite_job_dir": str(legacy_job_dir), "input_path": "/tmp/users.txt"},
                    summary="Invite planned",
                    index_path=index_path,
                )
                execution = run_workflow(planned["job_id"], index_path=index_path)
                job = get_job(planned["job_id"], index_path=index_path)

        self.assertEqual(execution["status"], "ready")
        self.assertEqual(execution["step"]["artifact_paths"]["job_dir"], str(canonical_job_dir))
        self.assertEqual(
            execution["step"]["artifact_paths"]["progress_json"],
            str(canonical_job_dir / "executions" / "20260508T110500Z" / "batch_progress.json"),
        )
        assert job is not None
        self.assertEqual(job["context"]["invite_job_dir"], str(canonical_job_dir))
        self.assertEqual(
            job["context"]["last_invite_run_dir"],
            str(canonical_job_dir / "executions" / "20260508T110500Z"),
        )

    def test_profile_workspace_snapshot_normalizes_continue_queue_context_to_canonical_job_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            index_path = root / "jobs" / "index.json"
            legacy_root = root / "legacy-invite-jobs"
            canonical_root = root / "runtime" / "telegram" / "invite_jobs"
            legacy_job_dir = legacy_root / "contact_add__AK3__sample"
            canonical_job_dir = canonical_root / legacy_job_dir.name
            canonical_job_dir.mkdir(parents=True)
            invite_state_path = canonical_job_dir / "invite_state.json"
            invite_state_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "chat_url": "contacts://AK3",
                        "source_file": "/tmp/users.txt",
                        "updated_at": "2026-05-08T11:00:00Z",
                        "users": [
                            {"username": "@done", "status": "contact_added"},
                            {"username": "@next", "status": "new"},
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            start_job(
                tool_id="telegram_invite_manager",
                workflow_kind="invite_batch",
                profile_name="AK3",
                profile_dir="/home/max/site-control-kit/runtime/telegram/profiles/TelegramPortable-AK3",
                phase="stopped",
                status="completed",
                summary="Invite done",
                context={
                    "invite_job_dir": str(legacy_job_dir),
                    "input_path": "/tmp/users.txt",
                    "invite_batch_limit": 10,
                    "statuses": ["new", "checked"],
                },
                index_path=index_path,
            )
            with mock.patch("tool_platform.telegram_gui_helpers.LEGACY_INVITE_JOBS_ROOT", legacy_root), mock.patch(
                "tool_platform.telegram_gui_helpers.DEFAULT_INVITE_OUTPUT_ROOT",
                canonical_root,
            ), mock.patch(
                "tool_platform.telegram_profiles.get_profile_status",
                return_value={"running": True, "attach_status": "exact_window", "attach_message": "", "attach_candidates": []},
            ):
                workspace = profile_workspace_snapshot(
                    profile_name="AK3",
                    profile_dir="/home/max/site-control-kit/runtime/telegram/profiles/TelegramPortable-AK3",
                    index_path=index_path,
                )

        bucket = workspace["workflow_buckets"]["invite_batch"]
        self.assertEqual(bucket["continue_queue_context"]["invite_job_dir"], str(canonical_job_dir))
        self.assertEqual(bucket["invite_snapshot"]["job_dir"], str(canonical_job_dir))
        self.assertEqual(bucket["continue_queue_hint"], "можно продолжить: осталось 1")

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

    def test_resume_workflow_restarts_recoverable_session_job_after_stop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            index_path = Path(tmp_dir) / "jobs" / "index.json"
            with mock.patch("tool_platform.workflows._build_session_run_command") as builder:
                builder.return_value = (
                    WorkflowCommandSpec(argv=["python3", "session.py"], cwd=Path(tmp_dir)),
                    Path(tmp_dir) / "runtime.json",
                )
                planned = plan_workflow(
                    workflow_kind="session_run",
                    tool_id="telegram_session_runner",
                    profile_name="AK",
                    profile_dir="/home/max/TelegramPortableAK",
                    context={"continuous_session": False, "message_settings": {"base_config_path": "/tmp/config.json"}},
                    summary="Session planned",
                    index_path=index_path,
                )
                run_workflow(planned["job_id"], index_path=index_path)
                stop_workflow_job(planned["job_id"], summary="Остановлено оператором", index_path=index_path)
                resumed = resume_workflow(planned["job_id"], index_path=index_path)

        self.assertEqual(resumed["status"], "ready")
        self.assertIsNotNone(resumed["command"])
        self.assertEqual(str((resumed["job"] or {}).get("status") or ""), "running")

    def test_complete_workflow_step_enriches_session_job_artifacts_from_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            index_path = root / "jobs" / "index.json"
            runs_dir = root / "runs"
            run_id = "20260504T101500Z-run"
            run_dir = runs_dir / run_id
            run_dir.mkdir(parents=True)
            run_json = run_dir / "run.json"
            plan_json = run_dir / "plan.json"
            screenshot = run_dir / "after.png"
            state_path = root / "session_state.json"
            runtime_config = root / "runtime.json"
            state_path.write_text("{}", encoding="utf-8")
            runtime_config.write_text("{}", encoding="utf-8")
            plan_json.write_text("{}", encoding="utf-8")
            screenshot.write_text("png", encoding="utf-8")
            run_json.write_text(
                json.dumps(
                    {
                        "run_id": run_id,
                        "status": "completed",
                        "visits": [{}],
                        "sent_count": 1,
                        "plan": {"message_target_username": "@alice_test"},
                        "messages": [{"index": 1, "text": "Привет", "sent": True}],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            with mock.patch("tool_platform.workflows._build_session_run_command") as builder, mock.patch(
                "tool_platform.workflows._session_runtime_paths",
                return_value=(state_path, runs_dir),
            ):
                builder.return_value = (
                    WorkflowCommandSpec(argv=["python3", "session.py"], cwd=root),
                    runtime_config,
                )
                planned = plan_workflow(
                    workflow_kind="session_run",
                    tool_id="telegram_session_runner",
                    profile_name="AK",
                    profile_dir="/home/max/TelegramPortableAK",
                    context={"continuous_session": False, "message_settings": {"base_config_path": "/tmp/config.json"}},
                    summary="Session planned",
                    index_path=index_path,
                )
                run_workflow(planned["job_id"], index_path=index_path)
                result = complete_workflow_step(
                    planned["job_id"],
                    payload={"status": "completed", "run_id": run_id, "sent_count": 1},
                    index_path=index_path,
                )
                job = get_job(planned["job_id"], index_path=index_path)

        self.assertEqual(result["status"], "completed")
        assert job is not None
        self.assertEqual(job["artifact_paths"]["run_dir"], str(run_dir))
        self.assertEqual(job["artifact_paths"]["session_run"], str(run_json))
        self.assertEqual(job["artifact_paths"]["plan_json"], str(plan_json))
        self.assertEqual(job["artifact_paths"]["screenshot_path"], str(screenshot))
        self.assertEqual(job["artifact_paths"]["state_path"], str(state_path))
        self.assertEqual(job["artifact_paths"]["runtime_config"], str(runtime_config))

    def test_gui_resume_candidate_prefers_active_then_recoverable_job(self) -> None:
        panel = object.__new__(ToolPlatformPanel)
        panel._selected_profile_workflow_bucket = lambda workflow_kind, limit=12: {
            "active_job": {"job_id": "running-job", "status": "running"},
            "recoverable_job": {"job_id": "recoverable-job", "status": "stopped", "recoverable": True},
            "last_job": {"job_id": "last-job", "status": "completed"},
        }

        candidate = ToolPlatformPanel._resume_candidate_workflow_job(panel, "session_run")

        self.assertEqual(candidate["job_id"], "running-job")

    def test_gui_invite_recoverable_context_prefers_latest_recoverable_job_context(self) -> None:
        class DummyVar:
            def __init__(self) -> None:
                self.value = ""

            def set(self, value: str) -> None:
                self.value = value

            def get(self) -> str:
                return self.value

        panel = object.__new__(ToolPlatformPanel)
        panel.invite_input_path_var = DummyVar()
        panel.invite_job_dir_var = DummyVar()
        panel._selected_profile_workflow_bucket = lambda workflow_kind: {
            "recoverable_job": {
                "job_id": "recoverable-invite",
                "status": "stopped",
                "recoverable": True,
                "context": {
                    "input_path": "/tmp/users.txt",
                    "invite_job_dir": "/tmp/invite-job",
                },
            }
        }

        context = ToolPlatformPanel._invite_recoverable_context(panel)

        self.assertEqual(context["input_path"], "/tmp/users.txt")
        self.assertEqual(panel.invite_input_path_var.get(), "/tmp/users.txt")
        self.assertEqual(panel.invite_job_dir_var.get(), "/tmp/invite-job")

    def test_refresh_combined_dashboard_keeps_manual_inputs_when_only_last_job_exists(self) -> None:
        class DummyVar:
            def __init__(self, value: str = "") -> None:
                self.value = value

            def set(self, value: str) -> None:
                self.value = value

            def get(self) -> str:
                return self.value

        panel = object.__new__(ToolPlatformPanel)
        panel.combined_input_path_var = DummyVar("/home/max/контакты/1.txt")
        panel.combined_job_dir_var = DummyVar("/home/max/telegram_invite_jobs/contact_add__AK__1")
        panel.session_config_path_var = DummyVar("/home/max/telegram-portable-session-tool/examples/session.example.json")
        panel.combined_step_pattern_var = DummyVar("12")
        panel.combined_phase_var = DummyVar()
        panel.combined_status_var = DummyVar()
        panel.combined_preview_var = DummyVar()
        panel.combined_state_text = object()
        panel.combined_contact_text = object()
        panel.combined_session_text = object()
        panel.combined_targets_text = object()
        panel._set_readonly_text = mock.Mock()
        panel._session_preview_context = lambda: {}
        panel._combined_targets_summary = lambda: "targets"
        panel._selected_profile = lambda: {
            "profile_name": "AK",
            "profile_dir": "/home/max/TelegramPortableAK",
        }
        panel._selected_profile_workspace = lambda limit=8, timeline_limit=8: {
            "workflow_buckets": {
                "combined_pattern": {
                    "active_job": None,
                    "last_job": {
                        "job_id": "combined-last",
                        "status": "completed",
                        "context": {
                            "input_path": "/tmp/stale-users.txt",
                            "invite_job_dir": "/tmp/stale-job",
                            "session_config_path": "/tmp/stale-session.json",
                            "step_pattern": "21",
                        },
                    },
                    "recoverable_job": {
                        "job_id": "combined-recoverable",
                        "status": "stopped",
                        "recoverable": True,
                        "context": {
                            "input_path": "/tmp/recoverable-users.txt",
                            "invite_job_dir": "/tmp/recoverable-job",
                            "session_config_path": "/tmp/recoverable-session.json",
                            "step_pattern": "22",
                        },
                    },
                }
            },
            "session_snapshot": {
                "status": "ready",
                "last_run": {"run_id": "run-1", "status": "completed", "sent_messages": []},
            },
        }
        state = {
            "phase": "stopped",
            "input_path": "/tmp/stale-users.txt",
            "invite_job_dir": "/tmp/stale-job",
            "session_config_path": "/tmp/stale-session.json",
            "step_pattern": "21",
            "last_status": "completed",
            "last_action": "combined_contact_add_finished",
        }
        captured_session_snapshot: dict[str, object] = {}

        with mock.patch("tool_platform.gui.combined_state_from_jobs", return_value=state), mock.patch(
            "tool_platform.gui.preview_invite_input_file", return_value={"unique_usernames": 1, "duplicates": 0, "invalid_count": 0}
        ), mock.patch(
            "tool_platform.gui.contact_job_snapshot", return_value={"pending_total": 0, "failed_total": 0, "added_total": 1}
        ), mock.patch(
            "tool_platform.gui.format_combined_operator_action", return_value="operator"
        ), mock.patch(
            "tool_platform.gui.format_combined_flow_state",
            side_effect=lambda *args, **kwargs: captured_session_snapshot.update(
                {"payload": dict(kwargs.get("session_snapshot") or {})}
            )
            or "state",
        ), mock.patch(
            "tool_platform.gui.format_contact_dashboard_snapshot", return_value="contact"
        ), mock.patch(
            "tool_platform.gui.format_contact_errors", return_value="errors"
        ), mock.patch(
            "tool_platform.gui.format_session_dashboard_snapshot", return_value="session"
        ), mock.patch(
            "tool_platform.gui.format_profile_label", return_value="AK"
        ):
            ToolPlatformPanel._refresh_combined_dashboard(panel)

        self.assertEqual(panel.combined_input_path_var.get(), "/home/max/контакты/1.txt")
        self.assertEqual(panel.combined_job_dir_var.get(), "/home/max/telegram_invite_jobs/contact_add__AK__1")
        self.assertEqual(
            panel.session_config_path_var.get(),
            "/home/max/telegram-portable-session-tool/examples/session.example.json",
        )
        self.assertEqual(panel.combined_step_pattern_var.get(), "12")
        self.assertEqual(captured_session_snapshot["payload"]["last_run"]["run_id"], "run-1")

    def test_refresh_combined_dashboard_prefers_workspace_combined_state(self) -> None:
        class DummyVar:
            def __init__(self, value: str = "") -> None:
                self.value = value

            def set(self, value: str) -> None:
                self.value = value

            def get(self) -> str:
                return self.value

        panel = object.__new__(ToolPlatformPanel)
        panel.combined_input_path_var = DummyVar()
        panel.combined_job_dir_var = DummyVar()
        panel.session_config_path_var = DummyVar()
        panel.combined_step_pattern_var = DummyVar()
        panel.combined_phase_var = DummyVar()
        panel.combined_status_var = DummyVar()
        panel.combined_preview_var = DummyVar()
        panel.combined_state_text = object()
        panel.combined_contact_text = object()
        panel.combined_session_text = object()
        panel.combined_targets_text = object()
        panel._set_readonly_text = mock.Mock()
        panel._session_preview_context = lambda: {}
        panel._combined_targets_summary = lambda: "targets"
        panel._selected_profile = lambda: {
            "profile_name": "AK3",
            "profile_dir": "/home/max/site-control-kit/runtime/telegram/profiles/TelegramPortable-AK3",
        }
        panel._selected_profile_workspace = lambda limit=8, timeline_limit=8: {
            "workflow_buckets": {
                "combined_pattern": {
                    "active_job": None,
                    "combined_state": {
                        "phase": "session_ready",
                        "input_path": "/tmp/users.txt",
                        "invite_job_dir": "/tmp/invite-job",
                        "session_config_path": "/tmp/session.json",
                        "step_pattern": "21",
                        "last_status": "completed",
                        "last_action": "combined_contact_add_finished_auto",
                    },
                    "progress_summary": {
                        "phase_label": "Шаг 2 готов: можно запускать сессию",
                        "current_step_label": "сессия и сообщения",
                        "next_step_label": "добавление контактов",
                    },
                }
            },
            "session_snapshot": {"status": "missing"},
        }

        with mock.patch("tool_platform.gui.combined_state_from_jobs", side_effect=AssertionError("should not call fallback")), mock.patch(
            "tool_platform.gui.resolve_combined_contact_preview",
            return_value={"invite_snapshot": None, "preview_text": "preview", "preview_payload": None, "preview_error": ""},
        ), mock.patch(
            "tool_platform.gui.format_combined_operator_action",
            return_value="operator",
        ), mock.patch(
            "tool_platform.gui.build_combined_dashboard_texts",
            return_value={"state_text": "state", "contact_text": "contact", "session_text": "session", "targets_text": "targets"},
        ) as build_mock:
            ToolPlatformPanel._refresh_combined_dashboard(panel)

        self.assertEqual(panel.combined_input_path_var.get(), "/tmp/users.txt")
        self.assertEqual(panel.combined_job_dir_var.get(), "/tmp/invite-job")
        self.assertEqual(panel.session_config_path_var.get(), "/tmp/session.json")
        self.assertEqual(panel.combined_step_pattern_var.get(), "21")
        self.assertEqual(build_mock.call_args.kwargs["progress_summary"]["current_step_label"], "сессия и сообщения")

    def test_refresh_session_dashboard_uses_workspace_session_snapshot(self) -> None:
        panel = object.__new__(ToolPlatformPanel)
        panel.session_summary_text = object()
        panel.session_history_text = object()
        panel._set_readonly_text = mock.Mock()
        panel._session_preview_context = lambda: {}
        panel._selected_profile_workspace = lambda limit=8, timeline_limit=8: {
            "workflow_buckets": {"session_run": {"resume_hint": "можно продолжить"}},
            "session_snapshot": {
                "status": "ready",
                "messages_sent_total": 3,
                "message_cursor": 1,
                "message_target_cursor": 0,
                "latest_runs": [],
                "last_run": {
                    "run_id": "session-run-1",
                    "status": "completed",
                    "visit_count": 1,
                    "message_count": 1,
                    "sent_count": 1,
                    "message_target_username": "@alice_test",
                    "sent_messages": [],
                    "unsent_messages": [],
                },
            },
        }

        with mock.patch("tool_platform.gui.format_session_operator_action", return_value="operator"), mock.patch(
            "tool_platform.gui.format_session_operator_summary", return_value="summary"
        ) as summary_mock, mock.patch(
            "tool_platform.gui.format_session_history", return_value="history"
        ) as history_mock:
            ToolPlatformPanel._refresh_session_dashboard(panel)

        self.assertEqual(summary_mock.call_args.args[0]["last_run"]["run_id"], "session-run-1")
        self.assertEqual(history_mock.call_args.args[0]["last_run"]["run_id"], "session-run-1")

    def test_refresh_invite_dashboard_uses_workspace_progress_summary(self) -> None:
        panel = object.__new__(ToolPlatformPanel)
        panel.invite_job_dir_var = mock.Mock()
        panel.invite_job_dir_var.get.return_value = "/tmp/job"
        panel.invite_input_path_var = mock.Mock()
        panel.invite_input_path_var.get.return_value = ""
        panel.invite_summary_text = object()
        panel.invite_queue_text = object()
        panel.invite_added_text = object()
        panel.invite_failed_text = object()
        panel.invite_history_text = object()
        panel.invite_preview_var = mock.Mock()
        panel._set_readonly_text = mock.Mock()
        panel._selected_profile_workflow_bucket = lambda workflow_kind: {
            "invite_snapshot": {
                "status": "ready",
                "pending_total": 14,
                "added_total": 4,
                "failed_total": 1,
                "pending_usernames": ["@bob_test"],
                "added_usernames": ["@alice_test"],
                "latest_errors": [],
                "latest_runs": [],
                "progress_summary": {
                    "status": "running",
                    "history_source": "progress_json",
                    "selected_target": 19,
                    "processed_count": 5,
                    "remaining_in_run": 14,
                    "queue_remaining_total": 1443,
                    "added_count": 4,
                    "already_present_count": 0,
                    "failed_count": 1,
                    "elapsed_seconds": 300,
                    "rate_per_minute": 1.0,
                    "eta_seconds": 840,
                    "current_username": "@bob_test",
                    "last_outcome": "contact_added_verified",
                },
            },
            "progress_summary": {
                "status": "running",
                "history_source": "progress_json",
                "selected_target": 19,
                "processed_count": 5,
                "remaining_in_run": 14,
                "queue_remaining_total": 1443,
                "added_count": 4,
                "already_present_count": 0,
                "failed_count": 1,
                "elapsed_seconds": 300,
                "rate_per_minute": 1.0,
                "eta_seconds": 840,
            },
        }

        with mock.patch("tool_platform.gui.format_invite_operator_action", return_value="operator"), mock.patch(
            "tool_platform.gui.contact_job_snapshot"
        ) as snapshot_mock:
            ToolPlatformPanel._refresh_invite_dashboard(panel)

        snapshot_mock.assert_not_called()
        preview_text = panel.invite_preview_var.set.call_args.args[0]
        self.assertIn("Обработано: 5/19", preview_text)
        self.assertIn("ETA: 00:14:00", preview_text)
        summary_text = panel._set_readonly_text.call_args_list[0].args[1]
        self.assertIn("Прогресс invite batch", summary_text)
        self.assertIn("Скорость: 1.00/мин", summary_text)

    def test_poll_tool_snapshot_reschedules_when_workflow_job_is_active_before_process_registration(self) -> None:
        panel = object.__new__(ToolPlatformPanel)
        panel._process_lock = threading.Lock()
        panel._active_processes = {}
        panel._active_job_ids = {"telegram_invite_manager": "job-1"}
        panel._monitor_after_ids = {}
        panel.after = mock.Mock(return_value="after-id")
        panel._refresh_invite_dashboard = mock.Mock()
        panel._refresh_combined_dashboard = mock.Mock()
        panel._refresh_session_dashboard = mock.Mock()
        panel._log_event = mock.Mock()

        ToolPlatformPanel._poll_tool_snapshot(panel, "telegram_invite_manager")

        panel._refresh_invite_dashboard.assert_called_once()
        panel.after.assert_called_once()
        self.assertEqual(panel._monitor_after_ids["telegram_invite_manager"], "after-id")

    def test_gui_resume_workflow_for_tool_does_not_restart_running_job(self) -> None:
        panel = object.__new__(ToolPlatformPanel)
        panel._selected_profile_resume_decision = lambda workflow_kind: {
            "kind": "running",
            "job": {"job_id": "running-job", "status": "running"},
            "allowed": False,
            "hint": "workflow уже выполняется",
            "action_text": "Жди завершения текущего workflow или останови его вручную.",
        }
        refresh_callback = mock.Mock()
        info_messages: list[str] = []

        with mock.patch("tool_platform.gui.messagebox.showinfo", side_effect=lambda title, text: info_messages.append(str(text))):
            with mock.patch("tool_platform.gui.resume_workflow") as resume_workflow_mock:
                ToolPlatformPanel._resume_workflow_for_tool(
                    panel,
                    tool_id="telegram_session_runner",
                    workflow_kind="session_run",
                    refresh_callback=refresh_callback,
                )

        resume_workflow_mock.assert_not_called()
        refresh_callback.assert_called_once()
        self.assertTrue(info_messages)
        self.assertIn("Жди завершения", info_messages[0])

    def test_gui_plan_workflow_blocks_on_bad_attach(self) -> None:
        panel = object.__new__(ToolPlatformPanel)
        panel._profiles = [
            {
                "profile_name": "AK2",
                "profile_dir": "/home/max/TelegramPortable-AK2",
            }
        ]
        panel._active_tool_id = "telegram_invite_manager"
        panel.profile_combo = mock.Mock()
        panel.profile_combo.current.return_value = 0
        panel.profile_manager_window = None
        panel._refresh_profile_workspace_dashboard = mock.Mock()
        panel._refresh_dashboard_for_tool = mock.Mock()
        panel._refresh_summary = mock.Mock()
        panel._log_event = mock.Mock()
        refresh_callback = mock.Mock()
        error_messages: list[str] = []

        with mock.patch(
            "tool_platform.gui.get_profile_status",
            return_value={
                "profile_name": "AK2",
                "profile_dir": "/home/max/TelegramPortable-AK2",
                "running": True,
                "attach_status": "running_without_window",
                "attach_message": "Процесс профиля запущен, но собственное окно не найдено.",
                "attach_candidates": [],
                "windows": [],
            },
        ), mock.patch(
            "tool_platform.gui.messagebox.showerror",
            side_effect=lambda title, text: error_messages.append(str(text)),
        ), mock.patch("tool_platform.gui.plan_workflow") as plan_mock:
            ToolPlatformPanel._plan_and_start_workflow(
                panel,
                tool_id="telegram_invite_manager",
                workflow_kind="invite_batch",
                context={"input_path": "/tmp/users.txt"},
                summary="invite",
                refresh_callback=refresh_callback,
            )

        plan_mock.assert_not_called()
        refresh_callback.assert_called_once()
        self.assertTrue(error_messages)
        self.assertIn("не готов к безопасному live attach", error_messages[0])
        self.assertIn("окно не найдено", error_messages[0])

    def test_complete_workflow_event_refreshes_profile_dashboard_after_mode_callback(self) -> None:
        panel = object.__new__(ToolPlatformPanel)
        panel._set_tool_busy = mock.Mock()
        panel._cancel_tool_monitor = mock.Mock()
        panel._stop_session_timer = mock.Mock()
        panel._render_workflow_status = mock.Mock()
        panel._log_event = mock.Mock()
        panel._refresh_profile_workspace_dashboard = mock.Mock()
        panel._active_job_ids = {}
        panel._active_job_contexts = {}
        mode_refresh = mock.Mock()

        with mock.patch(
            "tool_platform.gui.complete_workflow_step",
            return_value={
                "job": {"status": "completed", "summary": "Done", "profile_dir": "/home/max/TelegramPortableAK"},
                "next_command": None,
                "next_action_label": "",
                "next_step": {},
            },
        ):
            ToolPlatformPanel._complete_workflow_event(
                panel,
                {
                    "tool_id": "telegram_combined_flow",
                    "workflow_job_id": "job-1",
                    "action_label": "combined step",
                    "payload": {"status": "completed", "summary": "Done"},
                    "error_text": "",
                    "stopped": False,
                    "refresh_callback": mode_refresh,
                    "on_payload_success": None,
                    "step_kind": "invite_batch",
                },
            )

        mode_refresh.assert_called_once()
        panel._refresh_profile_workspace_dashboard.assert_called_once()

    def test_stop_workflow_job_updates_recent_step_and_recoverable_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            index_path = Path(tmp_dir) / "jobs" / "index.json"
            combined_context = default_combined_workflow_context("AK", "/home/max/TelegramPortableAK")
            combined_context.update(
                {
                    "input_path": "/tmp/users.txt",
                    "invite_job_dir": "/tmp/job",
                    "step_pattern": "12",
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
                    acquire_lock=True,
                    index_path=index_path,
                )
                run_workflow(planned["job_id"], index_path=index_path)
                stopped = stop_workflow_job(planned["job_id"], summary="Остановлено оператором", index_path=index_path)

        self.assertEqual(stopped["status"], "stopped")
        self.assertTrue(stopped["recoverable"])
        self.assertIn("Продолжить workflow", stopped["next_hint"])
        self.assertEqual(stopped["context"]["last_status"], "stopped")
        self.assertEqual(stopped["context"]["last_action"], "combined_contact_add_stopped")
        self.assertEqual(stopped["context"]["recent_step"]["step_status"], "stopped")
        self.assertTrue(stopped["context"]["recent_step"]["completed_at"])

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

    def test_build_combined_start_context_resets_cursor_and_uses_current_ui_values(self) -> None:
        context = build_combined_start_context(
            profile_name="AK",
            profile_dir="/home/max/TelegramPortableAK",
            input_path="/home/max/контакты/1.txt",
            invite_job_dir="/home/max/telegram_invite_jobs/contact_add__AK__1",
            session_config_path="/home/max/telegram-portable-session-tool/examples/session.example.json",
            step_pattern="11,2,1111,22",
            continuous_session=False,
            invite_batch_limit=1,
            account_username="@M_a_g_g_i_e",
            account_label="@M_a_g_g_i_e",
            message_settings={
                "auto_send": False,
                "messages_per_cycle": 0,
                "message_targets": [{"kind": "contact", "username": "@M_a_x_i_m_M_i_k_h_a_i_l_o_v"}],
            },
        )

        self.assertEqual(context["phase"], "contact_add")
        self.assertEqual(context["step_pattern"], "11,2,1111,22")
        self.assertEqual(context["step_cursor"], 0)
        self.assertEqual(context["step_label"], "добавление контактов")
        self.assertEqual(context["input_path"], "/home/max/контакты/1.txt")
        self.assertEqual(context["invite_job_dir"], "/home/max/telegram_invite_jobs/contact_add__AK__1")
        self.assertEqual(
            context["session_config_path"],
            "/home/max/telegram-portable-session-tool/examples/session.example.json",
        )
        self.assertEqual(context["last_action"], "combined_manual_start")
        self.assertEqual(context["last_status"], "planned")
        self.assertEqual(context["recent_step"], {})
        self.assertFalse(context["continuous_session"])

    def test_cleanup_failed_workflow_start_marks_job_error_and_releases_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            index_path = Path(tmp_dir) / "jobs" / "index.json"
            locks_path = Path(tmp_dir) / "locks" / "profiles.json"
            planned = plan_workflow(
                workflow_kind="combined_pattern",
                tool_id="telegram_combined_flow",
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                context=default_combined_workflow_context("AK", "/home/max/TelegramPortableAK"),
                summary="Combined planned",
                acquire_lock=False,
                index_path=index_path,
            )
            acquire_profile_lock(
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                owner_tool_id="telegram_combined_flow",
                job_id=planned["job_id"],
                locks_path=locks_path,
            )
            with mock.patch("tool_platform.workflows.DEFAULT_JOB_INDEX_PATH", index_path), mock.patch(
                "tool_platform.workflows.DEFAULT_WORKFLOW_STATE_ROOT",
                Path(tmp_dir) / "panel_state",
            ), mock.patch("tool_platform.workflows.release_profile_lock") as release_mock:
                release_mock.side_effect = lambda **kwargs: release_profile_lock(
                    locks_path=locks_path,
                    **kwargs,
                )
                cleaned = cleanup_failed_workflow_start(
                    planned["job_id"],
                    error_text="boom",
                    index_path=index_path,
                )

            lock = get_profile_lock(
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                locks_path=locks_path,
            )

        self.assertEqual(cleaned["status"], "error")
        self.assertEqual(cleaned["phase"], "review")
        self.assertEqual(cleaned["last_error"], "boom")
        self.assertTrue(cleaned["recoverable"])
        self.assertIsNotNone(cleaned["completed_at"])
        self.assertIsNone(lock)
        self.assertEqual(cleaned["context"]["last_status"], "error")
        self.assertEqual(cleaned["context"]["last_summary"], "boom")

    def test_plan_workflow_releases_stale_terminal_lock_before_acquiring_new_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            index_path = Path(tmp_dir) / "jobs" / "index.json"
            locks_path = Path(tmp_dir) / "locks" / "profiles.json"
            finished = start_job(
                tool_id="telegram_combined_flow",
                workflow_kind="combined_pattern",
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                phase="stopped",
                status="completed",
                summary="Finished workflow",
                index_path=index_path,
            )
            acquire_profile_lock(
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                owner_tool_id="telegram_combined_flow",
                job_id=finished["job_id"],
                locks_path=locks_path,
            )
            with mock.patch("tool_platform.workflows.get_profile_lock") as get_lock_mock, mock.patch(
                "tool_platform.workflows.release_profile_lock"
            ) as release_mock, mock.patch("tool_platform.workflows.acquire_profile_lock") as acquire_mock:
                get_lock_mock.side_effect = lambda **kwargs: get_profile_lock(locks_path=locks_path, **kwargs)
                release_mock.side_effect = lambda **kwargs: release_profile_lock(locks_path=locks_path, **kwargs)
                acquire_mock.side_effect = lambda **kwargs: acquire_profile_lock(locks_path=locks_path, **kwargs)
                planned = plan_workflow(
                    workflow_kind="combined_pattern",
                    tool_id="telegram_combined_flow",
                    profile_name="AK",
                    profile_dir="/home/max/TelegramPortableAK",
                    context=default_combined_workflow_context("AK", "/home/max/TelegramPortableAK"),
                    summary="Combined planned",
                    acquire_lock=True,
                    index_path=index_path,
                )

            current_lock = get_profile_lock(
                profile_name="AK",
                profile_dir="/home/max/TelegramPortableAK",
                locks_path=locks_path,
            )

        self.assertEqual(current_lock["job_id"], planned["job_id"])
        self.assertEqual(current_lock["owner_tool_id"], "telegram_combined_flow")
        self.assertNotEqual(current_lock["job_id"], finished["job_id"])

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
            with mock.patch("tool_platform.telegram_gui_helpers.combined_state_from_jobs", return_value=None):
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

    def test_platform_doctor_report_wayland_warnings(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"XDG_SESSION_TYPE": "wayland", "WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"},
            clear=False,
        ):
            report = platform_doctor_report("linux")

        self.assertIn("warnings", report)
        self.assertIn("Wayland detected", report["warnings"])
        self.assertEqual(report["capabilities"]["display_session"]["session_type"], "wayland")
        self.assertEqual(report["capabilities"]["window_automation"]["wayland_display"], "wayland-0")

    @mock.patch("tool_platform.workflows.profile_workspace_snapshot")
    @mock.patch("tool_platform.workflows.get_profile_status")
    @mock.patch("tool_platform.workflows.get_profile_lock", return_value=None)
    @mock.patch("tool_platform.workflows.list_jobs", return_value=[])
    @mock.patch("tool_platform.workflows.platform_capabilities")
    @mock.patch("tool_platform.workflows.platform_doctor_report")
    def test_profile_health_includes_workspace_health_and_wayland_diagnostics(
        self,
        doctor_mock,
        capabilities_mock,
        _jobs_mock,
        _lock_mock,
        status_mock,
        workspace_mock,
    ) -> None:
        doctor_mock.return_value = {
            "platform_id": "linux",
            "capabilities": {},
            "warnings": ["Wayland detected"],
        }
        capabilities_mock.return_value = {
            "display_session": {
                "available": True,
                "detail": "DISPLAY/WAYLAND_DISPLAY",
                "session_type": "wayland",
                "display": ":0",
                "wayland_display": "wayland-0",
                "warnings": ["Wayland detected"],
            },
            "window_automation": {
                "available": True,
                "detail": "wmctrl + python3-xlib",
                "warnings": [
                    "Wayland detected",
                    "X11 primitives available",
                    "safe attach still requires profile-owned X11 window confirmation",
                ],
            },
        }
        status_mock.return_value = {
            "running": False,
            "attach_status": "no_process",
            "attach_message": "",
            "attach_candidates": [],
            "session_type": "wayland",
            "display": ":0",
            "wayland_display": "wayland-0",
            "display_backend": "x11",
            "attach_proof_mode": "x11_window_confirmation",
        }
        workspace_mock.return_value = {
            "last_successful_job": None,
            "artifact_index": {},
            "workflow_buckets": {},
            "health": {
                "session_type": "wayland",
                "display_backend": "x11",
                "attach_proof_mode": "x11_window_confirmation",
                "capability_warnings": ["Wayland detected"],
            },
        }

        payload = profile_health(profile_name="AK5", profile_dir="/tmp/TelegramPortable-AK5")

        self.assertEqual(payload["profile_status"]["session_type"], "wayland")
        self.assertEqual(payload["workspace_health"]["display_backend"], "x11")
        self.assertEqual(payload["workspace_health"]["attach_proof_mode"], "x11_window_confirmation")
        self.assertIn("Wayland detected", payload["doctor"]["warnings"])


if __name__ == "__main__":
    unittest.main()
