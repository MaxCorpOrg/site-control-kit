from __future__ import annotations

import os
import subprocess
import threading
import time
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import sys

from scripts import telegram_members_export_gui as mod


def _doctor_bash_command(script: Path) -> list[str]:
    if os.name == "nt":
        return [str(Path(__file__).resolve().parents[1] / "bash.cmd"), str(script), "--doctor"]
    return ["bash", str(script), "--doctor"]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _gui_script_path() -> Path:
    return _repo_root() / "scripts" / "telegram_members_export_gui.py"


def _gui_wrapper_path() -> Path:
    return _repo_root() / "scripts" / "telegram_members_export_gui.sh"


class TelegramMembersExportGuiTests(unittest.TestCase):
    def test_app_exports_owner_module_symbols(self) -> None:
        from scripts.telegram_gui import backend as backend_mod
        from scripts.telegram_gui.ui import window as window_mod

        self.assertIs(mod.TelegramGuiBackend, backend_mod.TelegramGuiBackend)
        self.assertIs(mod.TelegramMembersExportWindow, window_mod.TelegramMembersExportWindow)
        self.assertIs(mod.TelegramMembersExportApp, window_mod.TelegramMembersExportApp)

    @unittest.skipUnless(os.name == "nt", "Windows-only startup contract")
    def test_windows_script_entrypoint_fast_fails_without_traceback(self) -> None:
        result = subprocess.run(
            [sys.executable, str(_gui_script_path())],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            timeout=20,
        )

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout.strip(), "")
        self.assertIn("supported only on Linux", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    @unittest.skipUnless(os.name == "nt", "Windows-only startup contract")
    def test_windows_bash_wrapper_fast_fails_without_traceback(self) -> None:
        result = subprocess.run(
            [str(_repo_root() / "bash.cmd"), str(_gui_wrapper_path())],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            timeout=20,
        )

        combined_output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 2)
        self.assertNotEqual(result.stdout.strip(), "Python")
        self.assertIn("supported only on Linux", combined_output)
        self.assertNotIn("Traceback", combined_output)

    def test_export_timeout_default_is_unlimited(self) -> None:
        self.assertIsNone(mod.TDATA_EXPORT_TIMEOUT_SEC)
        self.assertIsNone(mod._tdata_helper_timeout_seconds("export-chat"))

    def test_preferred_output_dir_creates_missing_parent(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "nested" / "result.md"
            resolved = mod._preferred_output_dir(str(target))
            self.assertEqual(resolved, target.parent)
            self.assertTrue(resolved.is_dir())

    def test_render_progress_state_marks_failed_export_as_error(self) -> None:
        class FakeProgressBar:
            def __init__(self) -> None:
                self.fraction = None
                self.text = ""
                self.pulsed = False

            def set_fraction(self, value: float) -> None:
                self.fraction = value

            def set_text(self, value: str) -> None:
                self.text = value

            def pulse(self) -> None:
                self.pulsed = True

        class FakeLabel:
            def __init__(self) -> None:
                self.value = ""

            def set_label(self, value: str) -> None:
                self.value = value

            def get_label(self) -> str:
                return self.value

        state = mod.ExportProgressState(
            chat_ref="-1001",
            messages_scanned=166750,
            usernames_found=272,
            started_at=time.monotonic() - 1800,
            last_update_at=time.monotonic(),
            done=True,
            failed=True,
        )
        fake_window = types.SimpleNamespace(
            export_progress_state=state,
            current_controller=None,
            progress_bar=FakeProgressBar(),
            progress_status_label=FakeLabel(),
            progress_meta_label=FakeLabel(),
            progress_hint_label=FakeLabel(),
        )

        mod.TelegramMembersExportWindow._render_progress_state(fake_window)

        self.assertEqual(fake_window.progress_status_label.get_label(), "Сканирование остановилось с ошибкой")
        self.assertEqual(fake_window.progress_bar.fraction, 0.0)
        self.assertIn("166750", fake_window.progress_bar.text)

    def test_finish_task_error_marks_export_progress_failed(self) -> None:
        class FakeButton:
            def __init__(self) -> None:
                self.sensitive = True

            def set_sensitive(self, value: bool) -> None:
                self.sensitive = value

        class FakeLabel:
            def __init__(self) -> None:
                self.value = ""

            def set_label(self, value: str) -> None:
                self.value = value

            def get_label(self) -> str:
                return self.value

        progress = mod.ExportProgressState(started_at=time.monotonic(), last_update_at=time.monotonic())
        logs: list[str] = []
        errors: list[str] = []
        renders: list[bool] = []
        fake_window = types.SimpleNamespace(
            current_task="export",
            current_controller=None,
            stop_button=FakeButton(),
            hero_status=FakeLabel(),
            export_progress_state=progress,
            _append_log=lambda message: logs.append(message),
            _render_progress_state=lambda: renders.append(True),
            _show_error=lambda text: errors.append(text),
        )

        result = mod.TelegramMembersExportWindow._finish_task_error(fake_window, RuntimeError("boom"))

        self.assertFalse(result)
        self.assertEqual(fake_window.current_task, None)
        self.assertEqual(fake_window.hero_status.get_label(), "Ошибка")
        self.assertFalse(fake_window.stop_button.sensitive)
        self.assertTrue(progress.done)
        self.assertTrue(progress.failed)
        self.assertEqual(logs, ["Ошибка: boom"])
        self.assertEqual(errors, ["boom"])
        self.assertEqual(renders, [True])

    def test_close_request_during_export_requests_cancel_and_defers_close(self) -> None:
        class FakeLabel:
            def __init__(self) -> None:
                self.value = ""

            def set_label(self, value: str) -> None:
                self.value = value

            def get_label(self) -> str:
                return self.value

        class FakeController:
            def __init__(self) -> None:
                self.cancel_requested = False

            def request_cancel(self) -> None:
                self.cancel_requested = True

        progress = mod.ExportProgressState(started_at=time.monotonic(), last_update_at=time.monotonic())
        controller = FakeController()
        logs: list[str] = []
        renders: list[bool] = []
        idle_calls: list[object] = []
        fake_window = types.SimpleNamespace(
            current_task="export",
            current_controller=controller,
            export_progress_state=progress,
            hero_status=FakeLabel(),
            _close_after_task=False,
            _append_log=lambda message: logs.append(message),
            _render_progress_state=lambda: renders.append(True),
            get_application=lambda: None,
            destroy=lambda: None,
        )

        with patch.object(mod.GLib, "idle_add", side_effect=lambda callback, *args: idle_calls.append((callback, args))):
            result = mod.TelegramMembersExportWindow._on_close_request(fake_window)

        self.assertTrue(result)
        self.assertTrue(controller.cancel_requested)
        self.assertTrue(fake_window._close_after_task)
        self.assertEqual(fake_window.hero_status.get_label(), "Останавливаем и закрываем...")
        self.assertEqual(logs, ["Запрошено закрытие окна после мягкой остановки экспорта."])
        self.assertEqual(renders, [True])
        self.assertEqual(idle_calls, [])
        self.assertEqual(progress.stage, "stop-requested")

    def test_close_request_without_active_export_schedules_immediate_close(self) -> None:
        idle_calls: list[object] = []
        fake_window = types.SimpleNamespace(
            current_task=None,
            current_controller=None,
            export_progress_state=None,
            get_application=lambda: None,
            destroy=lambda: None,
            _close_window_now=lambda: False,
        )

        with patch.object(mod.GLib, "idle_add", side_effect=lambda callback, *args: idle_calls.append((callback, args))):
            result = mod.TelegramMembersExportWindow._on_close_request(fake_window)

        self.assertFalse(result)
        self.assertEqual(idle_calls, [(fake_window._close_window_now, ())])

    def test_finish_task_success_finalizes_pending_close(self) -> None:
        class FakeButton:
            def __init__(self) -> None:
                self.sensitive = True

            def set_sensitive(self, value: bool) -> None:
                self.sensitive = value

        callbacks: list[str] = []
        fake_window = types.SimpleNamespace(
            current_task="export",
            current_controller=object(),
            stop_button=FakeButton(),
            _finalize_pending_close=lambda: callbacks.append("finalize"),
        )

        result = mod.TelegramMembersExportWindow._finish_task_success(
            fake_window,
            lambda payload: callbacks.append(f"callback:{payload}"),
            "done",
        )

        self.assertFalse(result)
        self.assertEqual(fake_window.current_task, None)
        self.assertEqual(fake_window.current_controller, None)
        self.assertFalse(fake_window.stop_button.sensitive)
        self.assertEqual(callbacks, ["callback:done", "finalize"])

    def test_handle_chats_loaded_supports_tdata_target(self) -> None:
        class FakeLabel:
            def __init__(self) -> None:
                self.value = ""

            def set_label(self, value: str) -> None:
                self.value = value

            def get_label(self) -> str:
                return self.value

        backend = mod.TelegramGuiBackend(action_log_path=Path("/tmp/gui-actions.log"))
        applied: list[bool] = []
        logs: list[str] = []
        fake_window = types.SimpleNamespace(
            backend=backend,
            connected_target=None,
            chat_rows=[],
            hero_status=FakeLabel(),
            chat_meta_label=FakeLabel(),
            recent_runs=[],
            pinned_chats=[],
            _selected_account=lambda: None,
            _apply_chat_filter=lambda: applied.append(True),
            _append_log=lambda message: logs.append(message),
        )
        fake_window._merge_known_chat_rows = lambda chats: mod.TelegramMembersExportWindow._merge_known_chat_rows(
            fake_window, chats
        )
        target = mod.BrowserTarget(
            client_id="tdata:test",
            tab_id=0,
            tab_title="Telegram Desktop",
            tab_url="/tmp/tdata",
        )
        chats = [
            mod.ChatOption(
                title="Test chat",
                subtitle="group",
                url="-1001",
                fragment="-1001",
                peer_id="-1001",
                active=True,
                visible=True,
                ordinal=0,
            )
        ]

        mod.TelegramMembersExportWindow._handle_chats_loaded(fake_window, (target, chats))

        self.assertEqual(fake_window.connected_target, target)
        self.assertEqual(fake_window.chat_rows, chats)
        self.assertEqual(fake_window.hero_status.get_label(), "Список чатов загружен")
        self.assertIn("напрямую из Telegram-сессии", fake_window.chat_meta_label.get_label())
        self.assertEqual(logs, ["Чаты загружены: 1"])
        self.assertEqual(applied, [True])

    def test_handle_chats_loaded_appends_known_history_chat_when_missing(self) -> None:
        class FakeLabel:
            def __init__(self) -> None:
                self.value = ""

            def set_label(self, value: str) -> None:
                self.value = value

            def get_label(self) -> str:
                return self.value

        backend = mod.TelegramGuiBackend(action_log_path=Path("/tmp/gui-actions.log"))
        account = mod.AccountOption(
            key="registry:TG_CONTACT 2",
            label="TG_CONTACT 2",
            name="TG_CONTACT 2",
            token="token",
            profile_source="/tmp/profile",
            source_kind="registry",
            sort_key=(0, "tg_contact_2", "/tmp/profile"),
        )
        known_run = mod.RunRecord(
            run_id="run-1",
            created_at="2026-05-05T12:00:00Z",
            surface_key="tdata",
            surface_label="Telegram Desktop tdata",
            surface_badge="Primary tdata",
            preset_key="quick_check",
            preset_label="Quick Check",
            account_key="registry:@AK-LIVE",
            account_label="@AK-LIVE",
            chat_ref="-1001461811598",
            chat_title="Чат BigpharmaMarket",
            output_path=Path("/tmp/bigpharma.md"),
            interrupted=False,
            safe_count=12,
            usernames_found=12,
            history_messages_scanned=400,
            artifacts=mod.ArtifactBundle(
                markdown=Path("/tmp/bigpharma.md"),
                usernames_txt=Path("/tmp/bigpharma_usernames.txt"),
            ),
            status="done",
        )
        applied: list[bool] = []
        logs: list[str] = []
        fake_window = types.SimpleNamespace(
            backend=backend,
            connected_target=None,
            chat_rows=[],
            hero_status=FakeLabel(),
            chat_meta_label=FakeLabel(),
            recent_runs=[known_run],
            pinned_chats=[],
            _selected_account=lambda: account,
            _apply_chat_filter=lambda: applied.append(True),
            _append_log=lambda message: logs.append(message),
        )
        fake_window._merge_known_chat_rows = lambda chats: mod.TelegramMembersExportWindow._merge_known_chat_rows(
            fake_window, chats
        )
        target = mod.BrowserTarget(
            client_id="tdata:test",
            tab_id=0,
            tab_title="Telegram Desktop",
            tab_url="/tmp/tdata",
        )
        chats = [
            mod.ChatOption(
                title="Test chat",
                subtitle="group",
                url="-1001",
                fragment="-1001",
                peer_id="-1001",
                active=True,
                visible=True,
                ordinal=0,
            )
        ]

        mod.TelegramMembersExportWindow._handle_chats_loaded(fake_window, (target, chats))

        self.assertEqual(len(fake_window.chat_rows), 2)
        self.assertEqual(fake_window.chat_rows[1].fragment, "-1001461811598")
        self.assertEqual(fake_window.chat_rows[1].title, "Чат BigpharmaMarket")
        self.assertEqual(fake_window.chat_rows[1].source_kind, "known")
        self.assertIn("known chats из истории/закреплений", fake_window.chat_meta_label.get_label())
        self.assertEqual(logs, ["Чаты загружены: 1 (+1 known)"])
        self.assertEqual(applied, [True])

    def test_save_security_token_inline_validates_empty_and_quickstart(self) -> None:
        class FakeLabel:
            def __init__(self) -> None:
                self.value = ""

            def set_label(self, value: str) -> None:
                self.value = value

            def get_label(self) -> str:
                return self.value

        class FakeEntry:
            def __init__(self, value: str) -> None:
                self.value = value

            def get_text(self) -> str:
                return self.value

            def set_text(self, value: str) -> None:
                self.value = value

        account = mod.AccountOption(
            key="auto:1",
            label="Слот 1",
            name="Слот 1",
            token=mod.DEFAULT_TOKEN,
            profile_source="/tmp/profile",
            source_kind="auto",
            sort_key=(0, "slot 1", "/tmp/profile"),
            slot_number="1",
            token_source="quickstart",
        )
        fake_window = types.SimpleNamespace(
            _selected_account=lambda: account,
            security_token_entry=FakeEntry("   "),
            security_feedback_label=FakeLabel(),
        )

        mod.TelegramMembersExportWindow._save_security_token_inline(fake_window)
        self.assertEqual(fake_window.security_feedback_label.get_label(), "Введите token перед сохранением.")

        fake_window.security_token_entry.set_text(mod.DEFAULT_TOKEN)
        mod.TelegramMembersExportWindow._save_security_token_inline(fake_window)
        self.assertEqual(
            fake_window.security_feedback_label.get_label(),
            "Quickstart token нельзя сохранять как secure token.",
        )

    def test_run_export_blocks_known_chat_for_tdata_when_not_in_live_dialog_list(self) -> None:
        class FakeEntry:
            def __init__(self, value: str) -> None:
                self.value = value

            def get_text(self) -> str:
                return self.value

            def set_text(self, value: str) -> None:
                self.value = value

        backend = mod.TelegramGuiBackend(action_log_path=Path("/tmp/gui-actions.log"))
        account = mod.AccountOption(
            key="registry:TG_CONTACT 2",
            label="TG_CONTACT 2",
            name="TG_CONTACT 2",
            token="token",
            profile_source="/tmp/profile",
            source_kind="registry",
            sort_key=(0, "tg_contact_2", "/tmp/profile"),
        )
        chat = mod.ChatOption(
            title="Чат BigpharmaMarket",
            subtitle="known chat | history | @AK-LIVE",
            url="-1001461811598",
            fragment="-1001461811598",
            peer_id="-1001461811598",
            active=False,
            visible=True,
            ordinal=99,
            source_kind="known",
        )
        target = mod.BrowserTarget(
            client_id="tdata:test",
            tab_id=0,
            tab_title="Telegram Desktop",
            tab_url="/tmp/tdata",
        )
        errors: list[str] = []
        fake_window = types.SimpleNamespace(
            _selected_account=lambda: account,
            _selected_chat=lambda: chat,
            output_entry=FakeEntry("/tmp/out.md"),
            _selected_preset_key=lambda: "quick_check",
            last_session=None,
            connected_target=target,
            backend=backend,
            _show_error=lambda text: errors.append(text),
        )

        mod.TelegramMembersExportWindow._run_export(fake_window)

        self.assertEqual(len(errors), 1)
        self.assertIn("known chat", errors[0])
        self.assertIn("live dialog list", errors[0])

    def test_save_security_token_inline_reloads_same_profile(self) -> None:
        class FakeLabel:
            def __init__(self) -> None:
                self.value = ""

            def set_label(self, value: str) -> None:
                self.value = value

            def get_label(self) -> str:
                return self.value

        class FakeEntry:
            def __init__(self, value: str) -> None:
                self.value = value

            def get_text(self) -> str:
                return self.value

            def set_text(self, value: str) -> None:
                self.value = value

        class FakeRevealer:
            def __init__(self) -> None:
                self.revealed = True

            def set_reveal_child(self, value: bool) -> None:
                self.revealed = value

        account = mod.AccountOption(
            key="auto:1",
            label="Слот 1",
            name="Слот 1",
            token=mod.DEFAULT_TOKEN,
            profile_source="/tmp/profile",
            source_kind="auto",
            sort_key=(0, "slot 1", "/tmp/profile"),
            slot_number="1",
            token_source="quickstart",
        )
        logs: list[str] = []
        reload_calls: list[tuple[str, str]] = []
        saved: list[tuple[str, str]] = []
        fake_window = types.SimpleNamespace(
            _selected_account=lambda: account,
            security_token_entry=FakeEntry("new-secure-token-12345"),
            security_feedback_label=FakeLabel(),
            output_entry=FakeEntry("/tmp/export.md"),
            backend=types.SimpleNamespace(save_secure_token=lambda acc, token: saved.append((acc.label, token))),
            hero_status=FakeLabel(),
            security_form_revealer=FakeRevealer(),
            _append_log=lambda message: logs.append(message),
            _load_accounts_into_ui=lambda **kwargs: reload_calls.append(
                (kwargs.get("preferred_profile_source") or "", kwargs.get("preserve_output") or "")
            ),
            _sanitize_text=lambda text: text,
        )

        mod.TelegramMembersExportWindow._save_security_token_inline(fake_window)

        self.assertEqual(saved, [("Слот 1", "new-secure-token-12345")])
        self.assertEqual(fake_window.hero_status.get_label(), "Secure token сохранён")
        self.assertIn("registry secret store", fake_window.security_feedback_label.get_label())
        self.assertFalse(fake_window.security_form_revealer.revealed)
        self.assertEqual(reload_calls, [("/tmp/profile", "/tmp/export.md")])
        self.assertEqual(logs, ["Secure token сохранён для профиля: Слот 1"])

    def test_refresh_fallback_card_shows_manual_bridge_setup_hint(self) -> None:
        class FakeLabel:
            def __init__(self) -> None:
                self.value = ""

            def set_label(self, value: str) -> None:
                self.value = value

            def get_label(self) -> str:
                return self.value

        class FakeBox:
            def __init__(self) -> None:
                self.visible = False

            def set_visible(self, value: bool) -> None:
                self.visible = value

        class FakeButton:
            def __init__(self) -> None:
                self.sensitive = False

            def set_sensitive(self, value: bool) -> None:
                self.sensitive = value

        info = mod.PreflightInfo(
            surface_key="fallback",
            surface_label="Fallback surface",
            surface_badge="Fallback required",
            is_primary=False,
            tdata_ready=False,
            helper_ready=False,
            output_path=None,
            preset_key="full_history",
            preset_label="Full History",
            history_limit="0",
            timeout_sec=None,
            resume_available=False,
            fallback_bridge=mod.FallbackReadiness(
                surface_key="bridge",
                surface_label="Telegram Web bridge",
                surface_badge="Fallback Bridge",
                state="extension_setup_required",
                detail="Load unpacked is required",
            ),
            fallback_cdp=mod.FallbackReadiness(
                surface_key="cdp",
                surface_label="Chrome profile direct",
                surface_badge="Fallback CDP",
                state="client_offline",
                detail="CDP browser profile is offline",
            ),
        )
        fake_window = types.SimpleNamespace(
            fallback_card=FakeBox(),
            fallback_title_label=FakeLabel(),
            fallback_bridge_label=FakeLabel(),
            fallback_cdp_label=FakeLabel(),
            fallback_hint_label=FakeLabel(),
            fallback_prepare_bridge_button=FakeButton(),
            fallback_retry_button=FakeButton(),
            current_task=None,
            _fallback_state_label=lambda readiness: mod.TelegramMembersExportWindow._fallback_state_label(None, readiness),  # type: ignore[arg-type]
        )

        mod.TelegramMembersExportWindow._refresh_fallback_card(fake_window, info, object())

        self.assertTrue(fake_window.fallback_card.visible)
        self.assertEqual(fake_window.fallback_title_label.get_label(), "Fallback required")
        self.assertIn("extension_setup_required", fake_window.fallback_bridge_label.get_label())
        self.assertIn("Load unpacked", fake_window.fallback_hint_label.get_label())
        self.assertTrue(fake_window.fallback_prepare_bridge_button.sensitive)
        self.assertTrue(fake_window.fallback_retry_button.sensitive)

    def test_handle_bridge_prepared_sets_connected_target(self) -> None:
        class FakeLabel:
            def __init__(self) -> None:
                self.value = ""

            def set_label(self, value: str) -> None:
                self.value = value

            def get_label(self) -> str:
                return self.value

        target = mod.BrowserTarget(
            client_id="client-1",
            tab_id=77,
            tab_title="Telegram",
            tab_url="https://web.telegram.org/a/",
        )
        readiness = mod.FallbackReadiness(
            surface_key="bridge",
            surface_label="Telegram Web bridge",
            surface_badge="Fallback Bridge",
            state="ready",
            detail="Bridge ready",
            target=target,
        )
        logs: list[str] = []
        refreshed: list[bool] = []
        fake_window = types.SimpleNamespace(
            connected_target=None,
            hero_status=FakeLabel(),
            _append_log=lambda message: logs.append(message),
            _refresh_preflight=lambda **kwargs: refreshed.append(bool(kwargs.get("schedule_deep"))),
        )

        mod.TelegramMembersExportWindow._handle_bridge_prepared(fake_window, readiness)

        self.assertEqual(fake_window.connected_target, target)
        self.assertEqual(fake_window.hero_status.get_label(), "Bridge profile готов")
        self.assertEqual(logs, ["Fallback bridge: ready | Bridge ready"])
        self.assertEqual(refreshed, [True])

    def test_do_activate_presents_window_before_bootstrap(self) -> None:
        order: list[str] = []
        fake_window = types.SimpleNamespace(
            present=lambda: order.append("present"),
            bootstrap_async=lambda: order.append("bootstrap"),
        )
        fake_app = types.SimpleNamespace(backend=object(), window=None)

        with (
            patch.object(mod, "install_css"),
            patch.object(mod, "TelegramMembersExportWindow", return_value=fake_window),
        ):
            mod.TelegramMembersExportApp.do_activate(fake_app)

        self.assertEqual(order, ["present", "bootstrap"])
        self.assertIs(fake_app.window, fake_window)

    def test_output_path_change_refreshes_light_only(self) -> None:
        refresh_calls: list[dict[str, object]] = []
        fake_window = types.SimpleNamespace(
            _ui_syncing=False,
            _refresh_preflight=lambda **kwargs: refresh_calls.append(kwargs),
        )

        mod.TelegramMembersExportWindow._on_output_path_changed(fake_window)

        self.assertEqual(refresh_calls, [{}])

    def test_chat_selection_refreshes_light_only(self) -> None:
        class FakeLabel:
            def __init__(self) -> None:
                self.value = ""

            def set_label(self, value: str) -> None:
                self.value = value

            def get_label(self) -> str:
                return self.value

        class FakeEntry:
            def __init__(self, value: str) -> None:
                self.value = value

            def get_text(self) -> str:
                return self.value

            def set_text(self, value: str) -> None:
                self.value = value

        chat = mod.ChatOption(
            title="BigpharmaMarket",
            subtitle="group",
            url="https://web.telegram.org/a/#-1001",
            fragment="-1001",
            peer_id="-1001",
            active=True,
            visible=True,
            ordinal=0,
        )
        refresh_calls: list[dict[str, object]] = []
        fake_window = types.SimpleNamespace(
            _selected_chat=lambda: chat,
            chat_title_label=FakeLabel(),
            chat_url_label=FakeLabel(),
            output_entry=FakeEntry("/tmp/export.md"),
            _refresh_preflight=lambda **kwargs: refresh_calls.append(kwargs),
        )

        mod.TelegramMembersExportWindow._on_chat_selected(fake_window)

        self.assertEqual(fake_window.chat_title_label.get_label(), "BigpharmaMarket")
        self.assertEqual(refresh_calls, [{}])

    def test_slugify_filename_strips_telegram_suffix(self) -> None:
        self.assertEqual(mod.slugify_filename("BigpharmaMarket | Telegram"), "bigpharmamarket")
        self.assertEqual(mod.slugify_filename("https://web.telegram.org/a/#-1002465948544"), "web.telegram.org_a_-1002465948544")

    def test_normalize_chat_options_keeps_current_dialog_and_dedupes(self) -> None:
        rows = mod.normalize_chat_options(
            {
                "mode": "a",
                "current_url": "https://web.telegram.org/a/#-1001",
                "current_title": "BigpharmaMarket | Telegram",
                "items": [
                    {
                        "index": 1,
                        "title": "BigpharmaMarket",
                        "subtitle": "group",
                        "fragment": "-1001",
                        "url": "https://web.telegram.org/a/#-1001",
                        "active": True,
                        "visible": True,
                    },
                    {
                        "index": 2,
                        "title": "BigpharmaMarket duplicate",
                        "subtitle": "group",
                        "fragment": "-1001",
                        "url": "https://web.telegram.org/a/#-1001",
                        "active": False,
                        "visible": True,
                    },
                    {
                        "index": 3,
                        "title": "Other",
                        "subtitle": "channel",
                        "fragment": "-1002",
                        "url": "https://web.telegram.org/a/#-1002",
                        "active": False,
                        "visible": True,
                    },
                ],
            }
        )

        self.assertEqual([row.title for row in rows], ["BigpharmaMarket", "Other"])
        self.assertTrue(rows[0].active)
        self.assertEqual(rows[0].url, "https://web.telegram.org/a/#-1001")

    def test_normalize_tdata_chat_options_keeps_chat_ref(self) -> None:
        rows = mod.normalize_tdata_chat_options(
            {
                "items": [
                    {
                        "title": "Чат BigpharmaMarket",
                        "chat_ref": "-1001461811598",
                        "username": "",
                        "peer_id": "-1001461811598",
                        "subtitle": "channel",
                    }
                ]
            }
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].title, "Чат BigpharmaMarket")
        self.assertEqual(rows[0].fragment, "-1001461811598")
        self.assertEqual(rows[0].url, "-1001461811598")

    def test_parse_progress_line_reads_counts_and_flags(self) -> None:
        payload = mod.parse_progress_line(
            "PROGRESS chat=-1001753733827 messages=4000 usernames=122 interrupted=1 done=1 stage=done"
        )

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["chat"], "-1001753733827")
        self.assertEqual(payload["messages"], "4000")
        self.assertEqual(payload["usernames"], "122")
        self.assertEqual(payload["interrupted"], "1")
        self.assertEqual(payload["done"], "1")

    def test_backend_load_accounts_skips_empty_slots(self) -> None:
        old_root = mod.TELEGRAM_WORKSPACE_ROOT
        old_registry = mod.USER_REGISTRY_PATH
        old_default_profile = mod.DEFAULT_PROFILE_DIR
        try:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td) / "telegram_workspace"
                mod.TELEGRAM_WORKSPACE_ROOT = root
                mod.USER_REGISTRY_PATH = root / "registry" / "users.json"
                mod.DEFAULT_PROFILE_DIR = root / "profiles" / "default"
                mod.layout_mod.ensure_workspace(root, slots=3)
                (root / "accounts" / "1" / "profile" / "Default").mkdir(parents=True)

                backend = mod.TelegramGuiBackend(action_log_path=root / "logs" / "actions.log")
                accounts = backend.load_accounts()

                self.assertEqual([account.label for account in accounts], ["Слот 1"])
            
        finally:
            mod.TELEGRAM_WORKSPACE_ROOT = old_root
            mod.USER_REGISTRY_PATH = old_registry
            mod.DEFAULT_PROFILE_DIR = old_default_profile

    def test_resolve_best_client_ignores_offline_entries(self) -> None:
        backend = mod.TelegramGuiBackend(action_log_path=Path("/tmp/gui-actions.log"))
        clients = [
            {
                "client_id": "offline-client",
                "is_online": False,
                "last_seen": "2026-04-29T10:00:00+00:00",
                "tabs": [{"id": 1, "active": True, "title": "Old Chat", "url": "https://web.telegram.org/a/#-1001"}],
            },
            {
                "client_id": "online-client",
                "is_online": True,
                "last_seen": "2026-04-29T10:05:00+00:00",
                "tabs": [{"id": 2, "active": True, "title": "Telegram", "url": "https://web.telegram.org/a/"}],
            },
        ]

        with patch.object(backend, "_list_clients", return_value=clients):
            target = backend._resolve_best_client("token", known_client_ids=set(), require_online=True)

        self.assertIsNotNone(target)
        assert target is not None
        self.assertEqual(target.client_id, "online-client")
        self.assertEqual(target.tab_id, 2)

    def test_fetch_chats_retries_when_first_payload_is_empty(self) -> None:
        backend = mod.TelegramGuiBackend(action_log_path=Path("/tmp/gui-actions.log"))
        account = mod.AccountOption(
            key="auto:1",
            label="Slot 1",
            name="Slot 1",
            token="token",
            profile_source="/tmp/profile",
            source_kind="auto",
            sort_key=(0, "slot 1", "/tmp/profile"),
        )
        target = mod.BrowserTarget(
            client_id="client-1",
            tab_id=77,
            tab_title="Telegram",
            tab_url="https://web.telegram.org/a/",
        )
        responses = [
            {"ok": True, "data": {"value": {"mode": "a", "current_url": "https://web.telegram.org/a/", "items": []}}},
            {
                "ok": True,
                "data": {
                    "value": {
                        "mode": "a",
                        "current_url": "https://web.telegram.org/a/#-1001",
                        "current_title": "BigpharmaMarket | Telegram",
                        "items": [
                            {
                                "index": 0,
                                "title": "BigpharmaMarket",
                                "subtitle": "group",
                                "fragment": "-1001",
                                "url": "https://web.telegram.org/a/#-1001",
                                "active": True,
                                "visible": True,
                            }
                        ],
                    }
                },
            },
        ]

        with (
            patch.object(backend, "ensure_connected", side_effect=[target, target]),
            patch.object(backend, "_wait_for_chat_list_ready", return_value=None),
            patch.object(mod.export_mod, "_send_command_result", side_effect=responses),
            patch.object(mod.time, "sleep", return_value=None),
        ):
            refreshed, chats = backend.fetch_chats(account, target)

        self.assertEqual(refreshed.client_id, "client-1")
        self.assertEqual(len(chats), 1)
        self.assertEqual(chats[0].title, "BigpharmaMarket")

    def test_merge_cdp_export_payload_keeps_members_and_mentions(self) -> None:
        rows = mod.merge_cdp_export_payload(
            {
                "snapshots": [
                    {
                        "members": [
                            {
                                "peer_id": "1001",
                                "name": "Alice",
                                "username": "@alice_name",
                                "status": "из чата",
                                "role": "admin",
                            }
                        ],
                        "info_members": [],
                        "mentions": ["@alice_name", "@bob_name"],
                    }
                ]
            }
        )

        usernames = [row["username"] for row in rows]
        self.assertIn("@alice_name", usernames)
        self.assertIn("@bob_name", usernames)
        mention_rows = [row for row in rows if row["peer_id"].startswith("mention:")]
        self.assertEqual(len(mention_rows), 1)
        self.assertEqual(mention_rows[0]["username"], "@bob_name")

    def test_fetch_chats_uses_cdp_helper_for_cdp_target(self) -> None:
        backend = mod.TelegramGuiBackend(action_log_path=Path("/tmp/gui-actions.log"))
        account = mod.AccountOption(
            key="auto:1",
            label="Slot 1",
            name="Slot 1",
            token="token",
            profile_source="/tmp/profile",
            source_kind="auto",
            sort_key=(0, "slot 1", "/tmp/profile"),
        )
        target = mod.BrowserTarget(
            client_id="cdp:9444",
            tab_id=9444,
            tab_title="Telegram",
            tab_url="https://web.telegram.org/a/",
        )

        with patch.object(
            backend,
            "_run_cdp_helper",
            return_value={
                "current_url": "https://web.telegram.org/a/#-1001",
                "current_title": "BigpharmaMarket | Telegram",
                "items": [
                    {
                        "index": 0,
                        "title": "BigpharmaMarket",
                        "subtitle": "group",
                        "fragment": "-1001",
                        "url": "https://web.telegram.org/a/#-1001",
                        "active": True,
                        "visible": True,
                    }
                ],
            },
        ):
            refreshed, chats = backend.fetch_chats(account, target)

        self.assertEqual(refreshed.client_id, "cdp:9444")
        self.assertEqual(refreshed.tab_url, "https://web.telegram.org/a/#-1001")
        self.assertEqual(len(chats), 1)
        self.assertEqual(chats[0].title, "BigpharmaMarket")

    def test_resolve_tdata_dir_prefers_extracted_tdata(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            extracted = root / "tdata-20260428T125500Z-3-001" / "tdata"
            extracted.mkdir(parents=True)

            resolved = mod.resolve_tdata_dir(root)

        self.assertEqual(resolved, extracted)

    def test_list_candidate_tdata_dirs_uses_collector_only_in_explicit_debug_mode(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "profile"
            root.mkdir(parents=True)
            (root / "tdata").mkdir()
            (root / "tdata" / "key_datas").write_bytes(b"stale-local-copy")

            archive = root / "tdata-20260428T125500Z-3-001.zip"
            with zipfile.ZipFile(archive, "w") as handle:
                handle.writestr("tdata/key_datas", b"zip-key")
                handle.writestr("tdata/D877F783D5D3EF8Cs", b"zip-session")
                handle.writestr("tdata/D877F783D5D3EF8C/maps", b"zip-maps")

            collector_tdata = Path(td) / "collector" / "tdata_import" / "tdata"
            (collector_tdata / "D877F783D5D3EF8C").mkdir(parents=True)
            (collector_tdata / "key_datas").write_bytes(b"zip-key")
            (collector_tdata / "D877F783D5D3EF8Cs").write_bytes(b"zip-session")
            (collector_tdata / "D877F783D5D3EF8C" / "maps").write_bytes(b"zip-maps")

            old_collector_tdata = mod.TELEGRAM_API_COLLECTOR_TDATA_DIR
            try:
                mod.TELEGRAM_API_COLLECTOR_TDATA_DIR = collector_tdata
                default_candidates = mod.list_candidate_tdata_dirs(root)
                debug_candidates = mod.list_candidate_tdata_dirs(root, include_collector_debug=True)
            finally:
                mod.TELEGRAM_API_COLLECTOR_TDATA_DIR = old_collector_tdata

        self.assertNotEqual(default_candidates[0], collector_tdata.resolve())
        self.assertEqual(debug_candidates[-1], collector_tdata.resolve())

    def test_ensure_tdata_target_does_not_launch_portable_binary(self) -> None:
        backend = mod.TelegramGuiBackend(action_log_path=Path("/tmp/gui-actions.log"))
        tdata_dir = Path("/tmp/fake-tdata")
        old_python = mod.TELEGRAM_API_COLLECTOR_PYTHON
        try:
            mod.TELEGRAM_API_COLLECTOR_PYTHON = Path(sys.executable)
            with (
                patch.object(mod, "list_candidate_tdata_dirs", return_value=[tdata_dir]),
                patch.object(backend, "_run_tdata_helper", return_value={"ok": True, "items": []}),
                patch.object(backend, "_launch_portable_telegram_best_effort") as launch_mock,
            ):
                target = backend._ensure_tdata_target(Path("/tmp/profile"), launch_browser=True)
        finally:
            mod.TELEGRAM_API_COLLECTOR_PYTHON = old_python

        self.assertIsNotNone(target)
        launch_mock.assert_not_called()

    def test_run_tdata_helper_streams_progress_lines(self) -> None:
        backend = mod.TelegramGuiBackend(action_log_path=Path("/tmp/gui-actions.log"))
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            helper = root / "fake_helper.py"
            helper.write_text(
                "\n".join(
                    [
                        "import json, sys",
                        "print('PROGRESS chat=x messages=1000 usernames=18', file=sys.stderr, flush=True)",
                        "print(json.dumps({'ok': True, 'items': []}))",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            tdata_dir = root / "tdata"
            tdata_dir.mkdir()
            old_python = mod.TELEGRAM_API_COLLECTOR_PYTHON
            old_helper = mod.TDATA_HELPER_SCRIPT
            try:
                mod.TELEGRAM_API_COLLECTOR_PYTHON = Path(sys.executable)
                mod.TDATA_HELPER_SCRIPT = helper
                seen: list[str] = []
                payload = backend._run_tdata_helper(
                    "list-chats",
                    tdata_dir=tdata_dir,
                    emit=seen.append,
                    timeout_sec=5,
                )
            finally:
                mod.TELEGRAM_API_COLLECTOR_PYTHON = old_python
                mod.TDATA_HELPER_SCRIPT = old_helper

        self.assertEqual(payload, {"ok": True, "items": []})
        self.assertEqual(seen, ["PROGRESS chat=x messages=1000 usernames=18"])

    def test_run_tdata_helper_timeout_is_actionable_for_export(self) -> None:
        backend = mod.TelegramGuiBackend(action_log_path=Path("/tmp/gui-actions.log"))
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            helper = root / "slow_helper.py"
            helper.write_text(
                "\n".join(
                    [
                        "import time",
                        "time.sleep(2)",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            tdata_dir = root / "tdata"
            tdata_dir.mkdir()
            old_python = mod.TELEGRAM_API_COLLECTOR_PYTHON
            old_helper = mod.TDATA_HELPER_SCRIPT
            try:
                mod.TELEGRAM_API_COLLECTOR_PYTHON = Path(sys.executable)
                mod.TDATA_HELPER_SCRIPT = helper
                with self.assertRaises(RuntimeError) as ctx:
                    backend._run_tdata_helper(
                        "export-chat",
                        tdata_dir=tdata_dir,
                        timeout_sec=1,
                    )
            finally:
                mod.TELEGRAM_API_COLLECTOR_PYTHON = old_python
                mod.TDATA_HELPER_SCRIPT = old_helper

        self.assertIn("TELEGRAM_TDATA_HISTORY_LIMIT", str(ctx.exception))
        self.assertIn("TELEGRAM_TDATA_EXPORT_TIMEOUT_SEC", str(ctx.exception))

    def test_run_tdata_helper_returns_partial_payload_on_cancel(self) -> None:
        backend = mod.TelegramGuiBackend(action_log_path=Path("/tmp/gui-actions.log"))
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
                        "messages = 0",
                        "while not stop and messages < 500:",
                        "    time.sleep(0.1)",
                        "    messages += 100",
                        "    print(f'PROGRESS chat=x messages={messages} usernames=5', file=sys.stderr, flush=True)",
                        "payload = {'ok': True, 'rows': [], 'stats': {'history_messages_scanned': messages, 'interrupted': 1 if stop else 0}, 'interrupted': bool(stop)}",
                        "print(json.dumps(payload), flush=True)",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            tdata_dir = root / "tdata"
            tdata_dir.mkdir()
            old_python = mod.TELEGRAM_API_COLLECTOR_PYTHON
            old_helper = mod.TDATA_HELPER_SCRIPT
            try:
                mod.TELEGRAM_API_COLLECTOR_PYTHON = Path(sys.executable)
                mod.TDATA_HELPER_SCRIPT = helper
                seen: list[str] = []
                controller = mod.TaskController()
                result_box: dict[str, object] = {}
                error_box: dict[str, Exception] = {}

                def worker() -> None:
                    try:
                        result_box["payload"] = backend._run_tdata_helper(
                            "export-chat",
                            tdata_dir=tdata_dir,
                            emit=seen.append,
                            timeout_sec=10,
                            controller=controller,
                        )
                    except Exception as exc:  # pragma: no cover - assertion path inspects this
                        error_box["exc"] = exc

                thread = threading.Thread(target=worker)
                thread.start()
                time.sleep(0.35)
                controller.request_cancel()
                thread.join(timeout=5)
            finally:
                mod.TELEGRAM_API_COLLECTOR_PYTHON = old_python
                mod.TDATA_HELPER_SCRIPT = old_helper

        self.assertFalse(thread.is_alive())
        if "exc" in error_box:
            if os.name != "nt":
                self.fail(f"unexpected cancel error: {error_box['exc']}")
            self.assertIsInstance(error_box["exc"], mod.TaskCancelled)
        else:
            payload = result_box.get("payload")
            self.assertIsInstance(payload, dict)
            assert isinstance(payload, dict)
            self.assertTrue(payload["interrupted"])
            self.assertGreaterEqual(int((payload.get("stats") or {}).get("history_messages_scanned") or 0), 0)
        self.assertTrue(any(line.startswith("PROGRESS chat=x messages=0 usernames=0 stage=start") for line in seen))
        self.assertTrue(any("Остановка сканирования" in line for line in seen))

    def test_run_tdata_helper_export_chat_without_timeout_limit(self) -> None:
        backend = mod.TelegramGuiBackend(action_log_path=Path("/tmp/gui-actions.log"))
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            helper = root / "no_timeout_helper.py"
            helper.write_text(
                "\n".join(
                    [
                        "import json, time",
                        "time.sleep(1.2)",
                        "print(json.dumps({'ok': True, 'rows': [], 'stats': {'history_messages_scanned': 12}}), flush=True)",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            tdata_dir = root / "tdata"
            tdata_dir.mkdir()
            old_python = mod.TELEGRAM_API_COLLECTOR_PYTHON
            old_helper = mod.TDATA_HELPER_SCRIPT
            try:
                mod.TELEGRAM_API_COLLECTOR_PYTHON = Path(sys.executable)
                mod.TDATA_HELPER_SCRIPT = helper
                payload = backend._run_tdata_helper(
                    "export-chat",
                    tdata_dir=tdata_dir,
                    timeout_sec=None,
                )
            finally:
                mod.TELEGRAM_API_COLLECTOR_PYTHON = old_python
                mod.TDATA_HELPER_SCRIPT = old_helper

        self.assertEqual(payload["stats"]["history_messages_scanned"], 12)

    def test_run_tdata_helper_serializes_parallel_calls(self) -> None:
        backend = mod.TelegramGuiBackend(action_log_path=Path("/tmp/gui-actions.log"))
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            helper = root / "parallel_helper.py"
            helper.write_text(
                "\n".join(
                    [
                        "import json, time",
                        "time.sleep(0.2)",
                        "print(json.dumps({'ok': True, 'items': []}), flush=True)",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            tdata_dir = root / "tdata"
            tdata_dir.mkdir()
            old_python = mod.TELEGRAM_API_COLLECTOR_PYTHON
            old_helper = mod.TDATA_HELPER_SCRIPT
            active_lock = threading.Lock()
            active_calls = 0
            max_active = 0
            original_run = backend.process_runner.run

            def wrapped_run(*args, **kwargs):
                nonlocal active_calls, max_active
                with active_lock:
                    active_calls += 1
                    max_active = max(max_active, active_calls)
                try:
                    return original_run(*args, **kwargs)
                finally:
                    with active_lock:
                        active_calls -= 1

            try:
                mod.TELEGRAM_API_COLLECTOR_PYTHON = Path(sys.executable)
                mod.TDATA_HELPER_SCRIPT = helper
                backend.process_runner.run = wrapped_run  # type: ignore[method-assign]
                errors: list[Exception] = []

                def worker() -> None:
                    try:
                        backend._run_tdata_helper("list-chats", tdata_dir=tdata_dir, timeout_sec=5)
                    except Exception as exc:  # pragma: no cover - assertion inspects collected errors
                        errors.append(exc)

                threads = [
                    threading.Thread(target=worker)
                    for _ in range(2)
                ]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(timeout=5)
            finally:
                backend.process_runner.run = original_run  # type: ignore[method-assign]
                mod.TELEGRAM_API_COLLECTOR_PYTHON = old_python
                mod.TDATA_HELPER_SCRIPT = old_helper

        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(errors, [])
        self.assertEqual(max_active, 1)

    def test_selected_helper_python_prefers_managed_env_before_legacy(self) -> None:
        old_managed = mod.MANAGED_HELPER_PYTHON
        old_legacy = mod.TELEGRAM_API_COLLECTOR_PYTHON
        try:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                managed = root / "managed" / ".venv" / "bin" / "python"
                legacy = root / "legacy" / ".venv" / "bin" / "python"
                managed.parent.mkdir(parents=True, exist_ok=True)
                legacy.parent.mkdir(parents=True, exist_ok=True)
                managed.write_text("#!/bin/sh\n", encoding="utf-8")
                legacy.write_text("#!/bin/sh\n", encoding="utf-8")
                os.chmod(managed, 0o755)
                os.chmod(legacy, 0o755)
                mod.MANAGED_HELPER_PYTHON = managed
                mod.TELEGRAM_API_COLLECTOR_PYTHON = legacy
                with patch.dict(os.environ, {"TELEGRAM_API_COLLECTOR_PYTHON": ""}, clear=False):
                    selected = mod._selected_helper_python()
        finally:
            mod.MANAGED_HELPER_PYTHON = old_managed
            mod.TELEGRAM_API_COLLECTOR_PYTHON = old_legacy

        assert selected is not None
        self.assertEqual(selected[0], "managed")
        self.assertEqual(selected[1], managed)

    def test_packaged_resource_paths_live_under_scripts_dir(self) -> None:
        self.assertEqual(mod.RUN_ONCE_SCRIPT.parent, mod.SCRIPTS_DIR)
        self.assertEqual(mod.SAFE_SNAPSHOT_SCRIPT.parent, mod.SCRIPTS_DIR)
        self.assertEqual(mod.START_BROWSER_SCRIPT.parent, mod.SCRIPTS_DIR)
        self.assertEqual(mod.CDP_HELPER_SCRIPT.parent, mod.SCRIPTS_DIR)
        self.assertEqual(mod.TDATA_HELPER_SCRIPT.parent, mod.SCRIPTS_DIR)
        self.assertEqual(mod.HELPER_REQUIREMENTS_FILE.parent, mod.SCRIPTS_DIR)

    def test_bootstrap_doctor_reports_linux_install_foundation_paths(self) -> None:
        script = Path(__file__).resolve().parents[1] / "scripts" / "bootstrap_telegram_workstation.sh"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            env = os.environ.copy()
            env["TELEGRAM_WORKSPACE_ROOT"] = str(root / "workspace")
            env["TELEGRAM_MANAGED_HELPER_ROOT"] = str(root / "workspace" / "managed_helper")
            env["PYTHON_BIN"] = sys.executable
            completed = subprocess.run(
                _doctor_bash_command(script),
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )

        self.assertIn("workspace_root=", completed.stdout)
        self.assertIn("runtime_root=", completed.stdout)
        self.assertIn("runtime_events_log=", completed.stdout)
        self.assertIn("runtime_errors_log=", completed.stdout)
        self.assertIn("managed_helper_root=", completed.stdout)
        self.assertIn("requirements_ready=1", completed.stdout)
        self.assertIn("selected_helper_source=", completed.stdout)



if __name__ == "__main__":
    unittest.main()
