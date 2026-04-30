from __future__ import annotations

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


class TelegramMembersExportGuiTests(unittest.TestCase):
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
            _apply_chat_filter=lambda: applied.append(True),
            _append_log=lambda message: logs.append(message),
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

    def test_resolve_tdata_dir_prefers_matching_collector_import(self) -> None:
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
                resolved = mod.resolve_tdata_dir(root)
            finally:
                mod.TELEGRAM_API_COLLECTOR_TDATA_DIR = old_collector_tdata

        self.assertEqual(resolved, collector_tdata.resolve())

    def test_ensure_tdata_target_does_not_launch_portable_binary(self) -> None:
        backend = mod.TelegramGuiBackend(action_log_path=Path("/tmp/gui-actions.log"))
        tdata_dir = Path("/tmp/fake-tdata")
        old_python = mod.TELEGRAM_API_COLLECTOR_PYTHON
        try:
            mod.TELEGRAM_API_COLLECTOR_PYTHON = Path("/bin/true")
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
        self.assertNotIn("exc", error_box)
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


if __name__ == "__main__":
    unittest.main()
