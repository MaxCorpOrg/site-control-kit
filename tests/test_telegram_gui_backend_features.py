from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import telegram_members_export_gui as mod


def _write_tdata_payload(tdata_dir: Path, *, key: bytes = b"key", session: bytes = b"session", maps: bytes = b"maps") -> None:
    tdata_dir.mkdir(parents=True, exist_ok=True)
    (tdata_dir / "key_datas").write_bytes(key)
    (tdata_dir / "D877F783D5D3EF8Cs").write_bytes(session)
    maps_dir = tdata_dir / "D877F783D5D3EF8C"
    maps_dir.mkdir(parents=True, exist_ok=True)
    (maps_dir / "maps").write_bytes(maps)


class TelegramGuiBackendFeatureTests(unittest.TestCase):
    def test_suggest_portable_profile_name_uses_tg_contact_slot_label(self) -> None:
        name = mod.suggest_portable_profile_name(
            Path("/home/max/site-control-kit/TG_CONTACT/2/tdata-20260430T111415Z-3-001.zip")
        )
        self.assertEqual(name, "TG_CONTACT 2")

    def test_adapter_selection_and_badges(self) -> None:
        backend = mod.TelegramGuiBackend(action_log_path=Path("/tmp/gui-actions.log"))
        tdata_target = mod.BrowserTarget(client_id="tdata:slot1", tab_id=0, tab_title="Telegram", tab_url="/tmp/tdata")
        cdp_target = mod.BrowserTarget(client_id="cdp:9229", tab_id=9229, tab_title="Telegram", tab_url="https://web.telegram.org/a/")
        bridge_target = mod.BrowserTarget(client_id="client-1", tab_id=77, tab_title="Telegram", tab_url="https://web.telegram.org/a/")

        self.assertEqual(backend.adapter_for_target(tdata_target).badge, "Primary tdata")
        self.assertEqual(backend.adapter_for_target(cdp_target).badge, "Fallback CDP")
        self.assertEqual(backend.adapter_for_target(bridge_target).badge, "Fallback Bridge")

    def test_preflight_marks_resume_unavailable_without_last_session(self) -> None:
        backend = mod.TelegramGuiBackend(action_log_path=Path("/tmp/gui-actions.log"))
        profile_dir = Path("/tmp/profile")
        profile_dir.mkdir(parents=True, exist_ok=True)
        account = mod.AccountOption(
            key="auto:1",
            label="Slot 1",
            name="Slot 1",
            token="token",
            profile_source=str(profile_dir),
            source_kind="auto",
            sort_key=(0, "slot 1", str(profile_dir)),
        )

        with patch.object(backend.run_history, "load_last_session", return_value=None):
            info = backend.build_preflight(
                account=account,
                output_path=Path("/tmp/export.md"),
                preset_key="resume_last",
                connected_target=None,
            )

        self.assertFalse(info.resume_available)
        self.assertTrue(any("Resume Last" in note for note in info.notes))

    def test_preflight_prefers_tdata_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            backend = mod.TelegramGuiBackend(action_log_path=Path(td) / "actions.log")
            profile_dir = Path(td) / "profile"
            profile_dir.mkdir(parents=True)
            account = mod.AccountOption(
                key="auto:1",
                label="Slot 1",
                name="Slot 1",
                token="token",
                profile_source=str(profile_dir),
                source_kind="auto",
                sort_key=(0, "slot 1", str(profile_dir)),
            )
            target = mod.BrowserTarget(
                client_id="tdata:slot1",
                tab_id=0,
                tab_title="Telegram Desktop",
                tab_url=str(Path(td) / "tdata"),
            )
            with (
                patch.object(mod, "resolve_tdata_dir", return_value=Path(td) / "tdata"),
                patch.object(mod, "TELEGRAM_API_COLLECTOR_PYTHON", Path(sys.executable)),
            ):
                info = backend.build_preflight(
                    account=account,
                    output_path=Path(td) / "out.md",
                    preset_key="full_history",
                    connected_target=target,
                )

        self.assertTrue(info.tdata_ready)
        self.assertEqual(info.surface_badge, "Primary tdata")

    def test_record_run_updates_artifact_index(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            backend = mod.TelegramGuiBackend(action_log_path=Path(td) / "actions.log")
            account = mod.AccountOption(
                key="registry:TG_CONTACT 4",
                label="TG_CONTACT 4",
                name="TG_CONTACT 4",
                token="token",
                profile_source=str(Path(td) / "profile"),
                source_kind="registry",
                sort_key=(0, "tg_contact_4", str(Path(td) / "profile")),
            )
            chat = mod.ChatOption(
                title="Косметолог на Миллион",
                subtitle="channel | @cosmetologna | resolved target",
                url="@cosmetologna",
                fragment="-1001506021345",
                peer_id="-1001506021345",
                active=False,
                visible=True,
                ordinal=-1,
                source_kind="resolved",
            )
            output_path = Path(td) / "cosmetologna.md"
            result = mod.ExportResult(
                output_path=output_path,
                usernames_txt=Path(td) / "cosmetologna_usernames.txt",
                usernames_json=Path(td) / "cosmetologna_usernames.json",
                safe_count=56,
                history_messages_scanned=400,
                usernames_found=56,
                interrupted=False,
                safe_txt=Path(td) / "latest_safe.txt",
                safe_md=Path(td) / "latest_safe.md",
                log_path=Path(td) / "export.log",
                action_log_path=Path(td) / "actions.log",
                surface_key="tdata",
                surface_label="Telegram Desktop tdata",
                surface_badge="Primary tdata",
                preset_key="quick_check",
                preset_label="Quick Check",
                status="done",
            )
            index_path = Path(td) / "artifacts" / "telegram_exports" / "INDEX.md"

            with (
                patch.object(mod, "ARTIFACT_INDEX_PATH", index_path),
                patch.object(backend.run_history, "ensure"),
                patch.object(backend.run_history, "append_run"),
                patch.object(backend.run_history, "save_last_session"),
            ):
                backend._record_run(
                    account=account,
                    chat=chat,
                    result=result,
                    preset_key="quick_check",
                    preset_label="Quick Check",
                )

            text = index_path.read_text(encoding="utf-8")
            self.assertIn("# Telegram Export Index", text)
            self.assertIn("Аккаунт: `TG_CONTACT 4`", text)
            self.assertIn("Чат: `Косметолог на Миллион`", text)
            self.assertIn("Preset: `Quick Check`", text)
            self.assertIn("Surface: `Primary tdata`", text)
            self.assertIn(f"Markdown: `{output_path}`", text)
            self.assertIn(f"Action log: `{Path(td) / 'actions.log'}`", text)

    def test_record_run_updates_artifact_index_for_public_phones(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            backend = mod.TelegramGuiBackend(action_log_path=Path(td) / "actions.log")
            account = mod.AccountOption(
                key="registry:TG_CONTACT 4",
                label="TG_CONTACT 4",
                name="TG_CONTACT 4",
                token="token",
                profile_source=str(Path(td) / "profile"),
                source_kind="registry",
                sort_key=(0, "tg_contact_4", str(Path(td) / "profile")),
            )
            chat = mod.ChatOption(
                title="Косметолог на Миллион",
                subtitle="channel | @cosmetologna | resolved target",
                url="@cosmetologna",
                fragment="-1001506021345",
                peer_id="-1001506021345",
                active=False,
                visible=True,
                ordinal=-1,
                source_kind="resolved",
            )
            output_path = Path(td) / "cosmetologna_phones.md"
            result = mod.ExportResult(
                output_path=output_path,
                usernames_txt=None,
                safe_count=0,
                history_messages_scanned=400,
                usernames_found=0,
                interrupted=False,
                safe_txt=None,
                safe_md=None,
                log_path=Path(td) / "export.log",
                action_log_path=Path(td) / "actions.log",
                operation_kind="public_phones",
                phones_found=7,
                phones_txt=Path(td) / "cosmetologna_phones.txt",
                phones_json=Path(td) / "cosmetologna_phones.json",
                private_phones_found=2,
                private_phones_txt=Path(td) / "cosmetologna_phones.private.txt",
                private_phones_json=Path(td) / "cosmetologna_phones.private.json",
                surface_key="tdata",
                surface_label="Telegram Desktop tdata",
                surface_badge="Primary tdata",
                preset_key="quick_check",
                preset_label="Quick Check",
                status="done",
            )
            index_path = Path(td) / "artifacts" / "telegram_exports" / "INDEX.md"

            with (
                patch.object(mod, "ARTIFACT_INDEX_PATH", index_path),
                patch.object(backend.run_history, "ensure"),
                patch.object(backend.run_history, "append_run"),
                patch.object(backend.run_history, "save_last_session"),
            ):
                recorded = backend._record_run(
                    account=account,
                    chat=chat,
                    result=result,
                    preset_key="quick_check",
                    preset_label="Quick Check",
                )

            text = index_path.read_text(encoding="utf-8")
            self.assertEqual(recorded.operation_kind, "public_phones")
            self.assertEqual(recorded.phones_found, 7)
            self.assertEqual(recorded.private_phones_found, 2)
            self.assertIn(f"Phones TXT: `{Path(td) / 'cosmetologna_phones.txt'}`", text)
            self.assertIn(f"Phones JSON: `{Path(td) / 'cosmetologna_phones.json'}`", text)
            self.assertIn(f"Private Phones TXT: `{Path(td) / 'cosmetologna_phones.private.txt'}`", text)
            self.assertIn(f"Private Phones JSON: `{Path(td) / 'cosmetologna_phones.private.json'}`", text)

    def test_bridge_export_uses_env_token_and_masks_logs(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            backend = mod.TelegramGuiBackend(action_log_path=Path(td) / "actions.log")
            account = mod.AccountOption(
                key="registry:alice",
                label="alice",
                name="alice",
                token="super-secret-token",
                profile_source=td,
                source_kind="registry",
                sort_key=(0, "alice", td),
            )
            target = mod.BrowserTarget(
                client_id="client-1",
                tab_id=7,
                tab_title="Telegram",
                tab_url="https://web.telegram.org/a/",
            )
            chat = mod.ChatOption(
                title="Test chat",
                subtitle="group",
                url="https://web.telegram.org/a/#-1001",
                fragment="-1001",
                peer_id="-1001",
                active=True,
                visible=True,
                ordinal=0,
            )
            output_path = Path(td) / "export.md"
            captured: dict[str, object] = {}

            def fake_run(*args, **kwargs):
                captured["args"] = args[0]
                captured["env"] = kwargs["env"]
                return SimpleNamespace(
                    stdout="bridge ok super-secret-token\n",
                    stderr="warn super-secret-token\n",
                    return_code=0,
                    timed_out=False,
                    forced_cancel=False,
                    cancel_requested=False,
                )

            with (
                patch.object(mod, "ACTION_LOG_DIR", Path(td) / "logs"),
                patch.object(backend.process_runner, "run", side_effect=fake_run),
                patch.object(backend, "_run_snapshot_helper", return_value={"safe_count": "12", "safe_txt": "", "safe_md": ""}),
            ):
                result = backend._run_export_via_bridge(
                    account=account,
                    target=target,
                    chat=chat,
                    output_path=output_path,
                    emit=lambda _message: None,
                    preset_key="quick_check",
                    preset_label="Quick Check",
                    surface_key="bridge",
                    surface_label="Telegram Web bridge",
                    surface_badge="Fallback Bridge",
                )

            command = captured["args"]
            env = captured["env"]
            assert isinstance(command, list)
            assert isinstance(env, dict)
            self.assertEqual(env["SITECTL_TOKEN"], "super-secret-token")
            self.assertEqual(env["SITECTL_SKIP_HUB_BOOT"], "1")
            self.assertNotIn("super-secret-token", " ".join(command))
            self.assertEqual(command[1], "")
            self.assertEqual(result.status, "done")
            run_logs = list((Path(td) / "logs").glob("export_run_*.log"))
            self.assertEqual(len(run_logs), 1)
            log_text = run_logs[0].read_text(encoding="utf-8")
            self.assertNotIn("super-secret-token", log_text)
            self.assertIn("supe...oken", log_text)

    def test_save_secure_token_for_auto_slot_creates_registry_secret_and_prefers_registry_row(self) -> None:
        old_root = mod.TELEGRAM_WORKSPACE_ROOT
        old_registry = mod.USER_REGISTRY_PATH
        old_default_profile = mod.DEFAULT_PROFILE_DIR
        try:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td) / "telegram_workspace"
                mod.TELEGRAM_WORKSPACE_ROOT = root
                mod.USER_REGISTRY_PATH = root / "registry" / "users.json"
                mod.DEFAULT_PROFILE_DIR = root / "profiles" / "default"
                mod.layout_mod.ensure_workspace(root, slots=1)
                profile_dir = root / "accounts" / "1" / "profile"
                (profile_dir / "Default").mkdir(parents=True)

                backend = mod.TelegramGuiBackend(action_log_path=root / "logs" / "actions.log")
                accounts = backend.load_accounts()
                self.assertEqual(len(accounts), 1)
                self.assertEqual(accounts[0].token_source, "quickstart")

                backend.save_secure_token(accounts[0], "slot-secure-token-12345")
                reloaded = backend.load_accounts()

                self.assertEqual(len(reloaded), 1)
                self.assertEqual(reloaded[0].source_kind, "registry")
                self.assertEqual(reloaded[0].token_source, "secret_ref")
                self.assertEqual(reloaded[0].token, "slot-secure-token-12345")
                registry_text = mod.USER_REGISTRY_PATH.read_text(encoding="utf-8")
                self.assertNotIn("slot-secure-token-12345", registry_text)
                self.assertIn("secret_ref", registry_text)
                secret_files = list((root / "registry" / "secrets" / "users").glob("*"))
                self.assertTrue(secret_files)
                self.assertTrue(any(path.read_text(encoding="utf-8").strip() == "slot-secure-token-12345" for path in secret_files))
                action_log = (root / "logs" / "actions.log").read_text(encoding="utf-8")
                self.assertNotIn("slot-secure-token-12345", action_log)
        finally:
            mod.TELEGRAM_WORKSPACE_ROOT = old_root
            mod.USER_REGISTRY_PATH = old_registry
            mod.DEFAULT_PROFILE_DIR = old_default_profile

    def test_load_accounts_imports_slot_key_once_and_clears_legacy_file(self) -> None:
        old_root = mod.TELEGRAM_WORKSPACE_ROOT
        old_registry = mod.USER_REGISTRY_PATH
        old_default_profile = mod.DEFAULT_PROFILE_DIR
        try:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td) / "telegram_workspace"
                mod.TELEGRAM_WORKSPACE_ROOT = root
                mod.USER_REGISTRY_PATH = root / "registry" / "users.json"
                mod.DEFAULT_PROFILE_DIR = root / "profiles" / "default"
                mod.layout_mod.ensure_workspace(root, slots=1)
                profile_dir = root / "accounts" / "1" / "profile"
                (profile_dir / "Default").mkdir(parents=True)
                token_path = root / "accounts" / "1" / "keys" / "api_token.txt"
                token_path.write_text("legacy-slot-token-12345\n", encoding="utf-8")

                backend = mod.TelegramGuiBackend(action_log_path=root / "logs" / "actions.log")
                accounts = backend.load_accounts()

                self.assertEqual(len(accounts), 1)
                self.assertEqual(accounts[0].source_kind, "registry")
                self.assertEqual(accounts[0].token_source, "secret_ref")
                self.assertEqual(accounts[0].token, "legacy-slot-token-12345")
                self.assertEqual(token_path.read_text(encoding="utf-8"), "")
                registry_text = mod.USER_REGISTRY_PATH.read_text(encoding="utf-8")
                self.assertNotIn("legacy-slot-token-12345", registry_text)
                action_log = (root / "logs" / "actions.log").read_text(encoding="utf-8")
                self.assertNotIn("legacy-slot-token-12345", action_log)
        finally:
            mod.TELEGRAM_WORKSPACE_ROOT = old_root
            mod.USER_REGISTRY_PATH = old_registry
            mod.DEFAULT_PROFILE_DIR = old_default_profile

    def test_load_accounts_dedupes_auto_slot_when_registry_row_uses_runtime_path(self) -> None:
        old_root = mod.TELEGRAM_WORKSPACE_ROOT
        old_registry = mod.USER_REGISTRY_PATH
        old_default_profile = mod.DEFAULT_PROFILE_DIR
        try:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td) / "telegram_workspace"
                mod.TELEGRAM_WORKSPACE_ROOT = root
                mod.USER_REGISTRY_PATH = root / "registry" / "users.json"
                mod.DEFAULT_PROFILE_DIR = root / "profiles" / "default"
                mod.layout_mod.ensure_workspace(root, slots=1)
                profile_dir = root / "accounts" / "1" / "profile"
                runtime_dir = root / "accounts" / "1" / "runtime"
                (profile_dir / "Default").mkdir(parents=True)
                runtime_dir.mkdir(parents=True, exist_ok=True)

                registry = mod.registry_mod.load_registry(mod.USER_REGISTRY_PATH)
                registry = mod.registry_mod.add_or_update_user_by_profile(
                    registry,
                    name="Слот 1",
                    token="legacy-runtime-token",
                    profile=str(runtime_dir),
                )
                mod.registry_mod.save_registry(mod.USER_REGISTRY_PATH, registry)

                backend = mod.TelegramGuiBackend(action_log_path=root / "logs" / "actions.log")
                accounts = backend.load_accounts()

                self.assertEqual([account.label for account in accounts].count("Слот 1"), 1)
                slot = next(account for account in accounts if account.label == "Слот 1")
                self.assertEqual(slot.source_kind, "registry")
                self.assertEqual(slot.profile_source, str(runtime_dir))
        finally:
            mod.TELEGRAM_WORKSPACE_ROOT = old_root
            mod.USER_REGISTRY_PATH = old_registry
            mod.DEFAULT_PROFILE_DIR = old_default_profile

    def test_save_secure_token_rejects_quickstart_default(self) -> None:
        backend = mod.TelegramGuiBackend(action_log_path=Path("/tmp/gui-actions.log"))
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

        with self.assertRaisesRegex(ValueError, "Quickstart token"):
            backend.save_secure_token(account, mod.DEFAULT_TOKEN)

    def test_save_secure_token_keeps_default_primary_profile(self) -> None:
        old_root = mod.TELEGRAM_WORKSPACE_ROOT
        old_registry = mod.USER_REGISTRY_PATH
        old_default_profile = mod.DEFAULT_PROFILE_DIR
        try:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td) / "telegram_workspace"
                mod.TELEGRAM_WORKSPACE_ROOT = root
                mod.USER_REGISTRY_PATH = root / "registry" / "users.json"
                mod.DEFAULT_PROFILE_DIR = root / "profiles" / "default"
                mod.layout_mod.ensure_workspace(root, slots=1)
                archive = Path(td) / "portable.zip"
                with zipfile.ZipFile(archive, "w") as handle:
                    handle.writestr("tdata/key_datas", b"zip-key")
                    handle.writestr("tdata/D877F783D5D3EF8Cs", b"zip-session")
                    handle.writestr("tdata/D877F783D5D3EF8C/maps", b"zip-maps")
                binary = Path(td) / "Telegram"
                binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                binary.chmod(0o755)

                backend = mod.TelegramGuiBackend(action_log_path=root / "logs" / "actions.log")
                with patch.object(mod, "find_portable_telegram_binary", return_value=binary):
                    backend.import_portable_profile(str(archive), profile_name="TG_CONTACT 2", set_default=True)
                    account = backend.load_accounts()[0]
                    backend.save_secure_token(account, "secure-primary-token-12345")
                    reloaded = backend.load_accounts()

                self.assertEqual(reloaded[0].label, "TG_CONTACT 2")
                self.assertEqual(reloaded[0].token_source, "secret_ref")
                registry = mod.registry_mod.load_registry(mod.USER_REGISTRY_PATH)
                self.assertEqual(registry.get("default_user"), "TG_CONTACT 2")
        finally:
            mod.TELEGRAM_WORKSPACE_ROOT = old_root
            mod.USER_REGISTRY_PATH = old_registry
            mod.DEFAULT_PROFILE_DIR = old_default_profile

    def test_load_accounts_keeps_missing_adopted_registry_row_visible(self) -> None:
        old_root = mod.TELEGRAM_WORKSPACE_ROOT
        old_registry = mod.USER_REGISTRY_PATH
        old_default_profile = mod.DEFAULT_PROFILE_DIR
        try:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td) / "telegram_workspace"
                archive = Path(td) / "portable.zip"
                missing_external = Path(td) / "telegram-portable-adopt-live"
                mod.TELEGRAM_WORKSPACE_ROOT = root
                mod.USER_REGISTRY_PATH = root / "registry" / "users.json"
                mod.DEFAULT_PROFILE_DIR = root / "profiles" / "default"
                mod.layout_mod.ensure_workspace(root, slots=1)
                with zipfile.ZipFile(archive, "w") as handle:
                    handle.writestr("tdata/key_datas", b"zip-key")
                    handle.writestr("tdata/D877F783D5D3EF8Cs", b"zip-session")
                    handle.writestr("tdata/D877F783D5D3EF8C/maps", b"zip-maps")

                backend = mod.TelegramGuiBackend(action_log_path=root / "logs" / "actions.log")
                backend.import_portable_profile(str(archive), profile_name="TG_CONTACT 2", set_default=True)

                registry = mod.registry_mod.load_registry(mod.USER_REGISTRY_PATH)
                registry = mod.registry_mod.add_or_update_user_by_profile(
                    registry,
                    name="@AK-ADOPTED",
                    token="adopted-secure-token-12345",
                    profile=str(missing_external),
                )
                mod.registry_mod.save_registry(mod.USER_REGISTRY_PATH, registry)
                saved_registry = mod.registry_mod.load_registry(mod.USER_REGISTRY_PATH)
                adopted_row = mod.registry_mod.find_user_by_profile(saved_registry, profile=str(missing_external))

                accounts = backend.load_accounts()

                self.assertTrue(adopted_row.get("secret_ref"))
                self.assertEqual(accounts[0].label, "TG_CONTACT 2")
                missing = next(account for account in accounts if account.label == "@AK-ADOPTED")
                self.assertEqual(missing.source_kind, "registry")
                self.assertEqual(missing.availability_state, "missing")
                self.assertIn(str(missing_external), missing.availability_detail)
                primary = next(account for account in accounts if account.label == "TG_CONTACT 2")
                self.assertEqual(primary.availability_state, "ready")
        finally:
            mod.TELEGRAM_WORKSPACE_ROOT = old_root
            mod.USER_REGISTRY_PATH = old_registry
            mod.DEFAULT_PROFILE_DIR = old_default_profile

    def test_remove_portable_profile_rejects_legacy_slot_profile(self) -> None:
        old_root = mod.TELEGRAM_WORKSPACE_ROOT
        old_registry = mod.USER_REGISTRY_PATH
        old_default_profile = mod.DEFAULT_PROFILE_DIR
        try:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td) / "telegram_workspace"
                mod.TELEGRAM_WORKSPACE_ROOT = root
                mod.USER_REGISTRY_PATH = root / "registry" / "users.json"
                mod.DEFAULT_PROFILE_DIR = root / "profiles" / "default"
                mod.layout_mod.ensure_workspace(root, slots=1)
                runtime_tdata = root / "accounts" / "1" / "runtime" / "portable_tdata"
                runtime_tdata.mkdir(parents=True, exist_ok=True)
                (runtime_tdata / "key_datas").write_text("key", encoding="utf-8")
                (runtime_tdata / "D877F783D5D3EF8Cs").write_text("session", encoding="utf-8")
                maps_dir = runtime_tdata / "D877F783D5D3EF8C"
                maps_dir.mkdir(parents=True, exist_ok=True)
                (maps_dir / "maps").write_text("maps", encoding="utf-8")

                backend = mod.TelegramGuiBackend(action_log_path=root / "logs" / "actions.log")
                with patch.object(mod, "find_portable_telegram_binary", return_value=None):
                    profiles = backend.load_portable_profiles()

                legacy = next(item for item in profiles if item.profile.slot_number == "1")
                with self.assertRaisesRegex(RuntimeError, "Legacy slot profile"):
                    backend.remove_portable_profile(str(legacy.profile_dir))
        finally:
            mod.TELEGRAM_WORKSPACE_ROOT = old_root
            mod.USER_REGISTRY_PATH = old_registry
            mod.DEFAULT_PROFILE_DIR = old_default_profile

    def test_build_preflight_exposes_owned_hub_restart_action(self) -> None:
        backend = mod.TelegramGuiBackend(action_log_path=Path("/tmp/gui-actions.log"))
        account = mod.AccountOption(
            key="registry:alice",
            label="alice",
            name="alice",
            token="secure-token",
            profile_source="/tmp/profile",
            source_kind="registry",
            sort_key=(0, "alice", "/tmp/profile"),
            secret_ref="users/alice.token",
            token_source="secret_ref",
        )

        with patch.object(
            backend,
            "inspect_account_security",
            return_value={
                "slot_number": "",
                "token_source": "secret_ref",
                "security_mode": "Local secure token",
                "security_state": "ok",
                "hub_token_status": "owned_mismatch",
                "hub_token_detail": "Hub на :8765 уже запущен этим GUI с другим токеном.",
                "hub_restart_available": True,
            },
        ):
            info = backend.build_preflight(
                account=account,
                output_path=Path("/tmp/out.md"),
                preset_key="full_history",
                connected_target=None,
            )

        self.assertTrue(info.security_restart_available)
        self.assertEqual(info.security_restart_label, "Перезапустить hub этим токеном")

    def test_build_preflight_light_skips_heavy_probes_and_deep_runs_them(self) -> None:
        old_root = mod.TELEGRAM_WORKSPACE_ROOT
        old_registry = mod.USER_REGISTRY_PATH
        old_default_profile = mod.DEFAULT_PROFILE_DIR
        try:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td) / "telegram_workspace"
                archive = Path(td) / "portable.zip"
                mod.TELEGRAM_WORKSPACE_ROOT = root
                mod.USER_REGISTRY_PATH = root / "registry" / "users.json"
                mod.DEFAULT_PROFILE_DIR = root / "profiles" / "default"
                mod.layout_mod.ensure_workspace(root, slots=1)
                with zipfile.ZipFile(archive, "w") as handle:
                    handle.writestr("tdata/key_datas", b"zip-key")
                    handle.writestr("tdata/D877F783D5D3EF8Cs", b"zip-session")
                    handle.writestr("tdata/D877F783D5D3EF8C/maps", b"zip-maps")

                backend = mod.TelegramGuiBackend(action_log_path=root / "logs" / "actions.log")
                backend.import_portable_profile(str(archive), profile_name="TG_CONTACT 2", set_default=True)
                account = next(item for item in backend.load_accounts() if item.label == "TG_CONTACT 2")
                bridge_ready = mod.FallbackReadiness(
                    surface_key="bridge",
                    surface_label="Telegram Web bridge",
                    surface_badge="Fallback Bridge",
                    state="ready",
                    detail="Bridge ready",
                )
                cdp_ready = mod.FallbackReadiness(
                    surface_key="cdp",
                    surface_label="Chrome profile direct",
                    surface_badge="Fallback CDP",
                    state="ready",
                    detail="CDP ready",
                )

                with (
                    patch.object(mod, "TELEGRAM_API_COLLECTOR_PYTHON", Path(sys.executable)),
                    patch.object(backend, "_inspect_hub_token_state", return_value={"state": "offline", "detail": "", "restart_available": False}),
                    patch.object(backend, "_run_tdata_helper", return_value={"ok": True, "items": []}) as helper_mock,
                    patch.object(backend, "probe_bridge_readiness", return_value=bridge_ready) as bridge_mock,
                    patch.object(backend, "probe_cdp_readiness", return_value=cdp_ready) as cdp_mock,
                    patch.object(backend, "_hub_reachable", return_value=False) as hub_mock,
                ):
                    backend.build_preflight(
                        account=account,
                        output_path=Path(td) / "light.md",
                        preset_key="full_history",
                        connected_target=None,
                        deep=False,
                    )
                    helper_mock.assert_not_called()
                    bridge_mock.assert_not_called()
                    cdp_mock.assert_not_called()
                    hub_mock.assert_not_called()

                    info = backend.build_preflight(
                        account=account,
                        output_path=Path(td) / "deep.md",
                        preset_key="full_history",
                        connected_target=None,
                        deep=True,
                    )

                helper_mock.assert_called_once()
                bridge_mock.assert_called_once_with(account)
                cdp_mock.assert_called_once_with(account)
                hub_mock.assert_called_once_with(account.token)
                self.assertEqual(info.fallback_bridge, bridge_ready)
                self.assertEqual(info.fallback_cdp, cdp_ready)
        finally:
            mod.TELEGRAM_WORKSPACE_ROOT = old_root
            mod.USER_REGISTRY_PATH = old_registry
            mod.DEFAULT_PROFILE_DIR = old_default_profile

    def test_probe_bridge_readiness_classifies_foreign_hub(self) -> None:
        backend = mod.TelegramGuiBackend(action_log_path=Path("/tmp/gui-actions.log"))
        account = mod.AccountOption(
            key="registry:alice",
            label="alice",
            name="alice",
            token="secure-token",
            profile_source="/tmp/profile",
            source_kind="registry",
            sort_key=(0, "alice", "/tmp/profile"),
            token_source="secret_ref",
        )

        with patch.object(
            backend,
            "_inspect_hub_token_state",
            return_value={"state": "foreign_mismatch", "detail": "На :8765 внешний hub.", "restart_available": False},
        ):
            readiness = backend.probe_bridge_readiness(account)

        self.assertEqual(readiness.state, "foreign_hub")
        self.assertIn("внешний hub", readiness.detail)

    def test_probe_bridge_readiness_marks_extension_setup_required_for_branded_chrome(self) -> None:
        backend = mod.TelegramGuiBackend(action_log_path=Path("/tmp/gui-actions.log"))
        with tempfile.TemporaryDirectory() as td:
            profile_dir = Path(td) / "profile"
            (profile_dir / "Default").mkdir(parents=True)
            account = mod.AccountOption(
                key="auto:1",
                label="Слот 1",
                name="Слот 1",
                token="secure-token",
                profile_source=str(profile_dir),
                source_kind="auto",
                sort_key=(0, "slot 1", str(profile_dir)),
                slot_number="1",
                token_source="secret_ref",
            )
            with (
                patch.object(
                    backend,
                    "_inspect_hub_token_state",
                    return_value={"state": "offline", "detail": "", "restart_available": False},
                ),
                patch.object(backend, "_resolve_best_client", return_value=None),
                patch.object(mod, "_detect_browser_binary", return_value="/usr/bin/google-chrome"),
            ):
                readiness = backend.probe_bridge_readiness(account)

        self.assertEqual(readiness.state, "extension_setup_required")
        self.assertIn("Load unpacked", readiness.detail)

    def test_prepare_bridge_surface_is_non_destructive_for_foreign_hub(self) -> None:
        backend = mod.TelegramGuiBackend(action_log_path=Path("/tmp/gui-actions.log"))
        account = mod.AccountOption(
            key="auto:1",
            label="Слот 1",
            name="Слот 1",
            token="secure-token",
            profile_source="/tmp/profile",
            source_kind="auto",
            sort_key=(0, "slot 1", "/tmp/profile"),
            slot_number="1",
            token_source="secret_ref",
        )
        foreign = mod.FallbackReadiness(
            surface_key="bridge",
            surface_label="Telegram Web bridge",
            surface_badge="Fallback Bridge",
            state="foreign_hub",
            detail="На :8765 внешний hub.",
        )

        with (
            patch.object(backend, "probe_bridge_readiness", return_value=foreign),
            patch.object(mod.subprocess, "run") as run_mock,
        ):
            readiness = backend.prepare_bridge_surface(account)

        self.assertIs(readiness, foreign)
        run_mock.assert_not_called()

    def test_prepare_cdp_surface_marks_auth_required(self) -> None:
        backend = mod.TelegramGuiBackend(action_log_path=Path("/tmp/gui-actions.log"))
        account = mod.AccountOption(
            key="auto:1",
            label="Слот 1",
            name="Слот 1",
            token="secure-token",
            profile_source="/tmp/profile",
            source_kind="auto",
            sort_key=(0, "slot 1", "/tmp/profile"),
            slot_number="1",
            token_source="secret_ref",
        )
        target = mod.BrowserTarget(
            client_id="cdp:9333",
            tab_id=9333,
            tab_title="Telegram",
            tab_url="https://web.telegram.org/a/",
        )

        with (
            patch.object(backend, "_ensure_cdp_target", return_value=target),
            patch.object(backend, "_run_cdp_helper", side_effect=RuntimeError("Selected browser profile is not logged into Telegram Web")),
        ):
            readiness = backend.prepare_cdp_surface(account)

        self.assertEqual(readiness.state, "telegram_auth_required")
        self.assertIn("not logged into telegram web", readiness.detail.lower())

    def test_probe_cdp_readiness_marks_browser_launch_failed_when_browser_missing(self) -> None:
        backend = mod.TelegramGuiBackend(action_log_path=Path("/tmp/gui-actions.log"))
        account = mod.AccountOption(
            key="auto:1",
            label="Слот 1",
            name="Слот 1",
            token="secure-token",
            profile_source="/tmp/profile",
            source_kind="auto",
            sort_key=(0, "slot 1", "/tmp/profile"),
            slot_number="1",
            token_source="secret_ref",
        )

        with (
            patch.object(backend, "_ensure_cdp_target", return_value=None),
            patch.object(mod, "_detect_browser_binary", side_effect=RuntimeError("no browser found")),
        ):
            readiness = backend.probe_cdp_readiness(account)

        self.assertEqual(readiness.state, "browser_launch_failed")
        self.assertIn("no browser found", readiness.detail)

    def test_build_preflight_prefers_ready_bridge_over_cdp(self) -> None:
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
        bridge_ready = mod.FallbackReadiness(
            surface_key="bridge",
            surface_label="Telegram Web bridge",
            surface_badge="Fallback Bridge",
            state="ready",
            detail="Bridge ready",
        )
        cdp_ready = mod.FallbackReadiness(
            surface_key="cdp",
            surface_label="Chrome profile direct",
            surface_badge="Fallback CDP",
            state="ready",
            detail="CDP ready",
        )

        with (
            patch.object(backend, "resolve_profile_dir_safe", return_value=(Path("/tmp/profile"), "ready", "Profile ready")),
            patch.object(mod, "resolve_tdata_dir", return_value=None),
            patch.object(backend, "probe_bridge_readiness", return_value=bridge_ready),
            patch.object(backend, "probe_cdp_readiness", return_value=cdp_ready),
        ):
            info = backend.build_preflight(
                account=account,
                output_path=Path("/tmp/export.md"),
                preset_key="full_history",
                connected_target=None,
                deep=True,
            )

        self.assertEqual(info.surface_badge, "Fallback Bridge")
        self.assertEqual(info.surface_key, "bridge")
        self.assertIs(info.fallback_bridge, bridge_ready)
        self.assertIs(info.fallback_cdp, cdp_ready)

    def test_build_preflight_swaps_to_cdp_when_bridge_requires_manual_setup(self) -> None:
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
        bridge_blocked = mod.FallbackReadiness(
            surface_key="bridge",
            surface_label="Telegram Web bridge",
            surface_badge="Fallback Bridge",
            state="extension_setup_required",
            detail="Load unpacked is required",
        )
        cdp_ready = mod.FallbackReadiness(
            surface_key="cdp",
            surface_label="Chrome profile direct",
            surface_badge="Fallback CDP",
            state="ready",
            detail="CDP ready",
        )

        with (
            patch.object(backend, "resolve_profile_dir_safe", return_value=(Path("/tmp/profile"), "ready", "Profile ready")),
            patch.object(mod, "resolve_tdata_dir", return_value=None),
            patch.object(backend, "probe_bridge_readiness", return_value=bridge_blocked),
            patch.object(backend, "probe_cdp_readiness", return_value=cdp_ready),
        ):
            info = backend.build_preflight(
                account=account,
                output_path=Path("/tmp/export.md"),
                preset_key="full_history",
                connected_target=None,
                deep=True,
            )

        self.assertEqual(info.surface_badge, "Fallback CDP")
        self.assertEqual(info.surface_key, "cdp")
        self.assertIn("bridge=extension_setup_required", info.surface_reason)

    def test_ensure_connected_swaps_to_cdp_when_bridge_is_blocked_externally(self) -> None:
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
        bridge_blocked = mod.FallbackReadiness(
            surface_key="bridge",
            surface_label="Telegram Web bridge",
            surface_badge="Fallback Bridge",
            state="extension_setup_required",
            detail="Load unpacked is required",
        )
        cdp_target = mod.BrowserTarget(
            client_id="cdp:9444",
            tab_id=9444,
            tab_title="Telegram",
            tab_url="https://web.telegram.org/a/",
        )
        cdp_ready = mod.FallbackReadiness(
            surface_key="cdp",
            surface_label="Chrome profile direct",
            surface_badge="Fallback CDP",
            state="ready",
            detail="CDP ready",
            target=cdp_target,
        )

        with (
            patch.object(backend, "inspect_portable_source", return_value=mod.PortableSourceInfo(slot_number="", path=None, kind="missing", detail="missing")),
            patch.object(backend._adapters_by_key["tdata"], "connect", return_value=None),
            patch.object(backend, "probe_bridge_readiness", return_value=bridge_blocked),
            patch.object(backend, "prepare_bridge_surface", return_value=bridge_blocked),
            patch.object(backend, "probe_cdp_readiness", return_value=cdp_ready),
            patch.object(backend, "_probe_cdp_target", return_value=cdp_ready),
        ):
            target = backend.ensure_connected(account, launch_browser=True)

        self.assertEqual(target.client_id, "cdp:9444")

    def test_build_preflight_uses_cached_cdp_auth_required_state(self) -> None:
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
        cached = mod.FallbackReadiness(
            surface_key="cdp",
            surface_label="Chrome profile direct",
            surface_badge="Fallback CDP",
            state="telegram_auth_required",
            detail="Telegram Web login is required",
        )
        backend._cache_fallback_readiness(account, cached)

        with (
            patch.object(backend, "resolve_profile_dir_safe", return_value=(Path("/tmp/profile"), "ready", "Profile ready")),
            patch.object(mod, "resolve_tdata_dir", return_value=None),
            patch.object(
                backend,
                "probe_bridge_readiness",
                return_value=mod.FallbackReadiness(
                    surface_key="bridge",
                    surface_label="Telegram Web bridge",
                    surface_badge="Fallback Bridge",
                    state="foreign_hub",
                    detail="foreign hub",
                ),
            ),
            patch.object(
                backend,
                "probe_cdp_readiness",
                return_value=mod.FallbackReadiness(
                    surface_key="cdp",
                    surface_label="Chrome profile direct",
                    surface_badge="Fallback CDP",
                    state="ready",
                    detail="CDP ready",
                ),
            ) as probe_mock,
        ):
            info = backend.build_preflight(
                account=account,
                output_path=Path("/tmp/export.md"),
                preset_key="full_history",
                connected_target=None,
            )

        self.assertEqual(info.fallback_cdp.state, "telegram_auth_required")
        probe_mock.assert_not_called()

    def test_import_portable_source_prefers_zip_from_tg_contact_folder(self) -> None:
        old_root = mod.TELEGRAM_WORKSPACE_ROOT
        old_registry = mod.USER_REGISTRY_PATH
        old_default_profile = mod.DEFAULT_PROFILE_DIR
        try:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td) / "telegram_workspace"
                tg_contact = Path(td) / "TG_CONTACT"
                tg_contact.mkdir(parents=True)
                archive = tg_contact / "tdata-20260428T125500Z-3-001.zip"
                with zipfile.ZipFile(archive, "w") as handle:
                    handle.writestr("tdata/key_datas", b"zip-key")
                    handle.writestr("tdata/D877F783D5D3EF8Cs", b"zip-session")
                    handle.writestr("tdata/D877F783D5D3EF8C/maps", b"zip-maps")
                extracted = tg_contact / "tdata-20260428T125500Z-3-001" / "tdata"
                extracted.mkdir(parents=True)
                (extracted / "key_datas").write_bytes(b"stale-copy")

                mod.TELEGRAM_WORKSPACE_ROOT = root
                mod.USER_REGISTRY_PATH = root / "registry" / "users.json"
                mod.DEFAULT_PROFILE_DIR = root / "profiles" / "default"
                mod.layout_mod.ensure_workspace(root, slots=3)

                backend = mod.TelegramGuiBackend(action_log_path=root / "logs" / "actions.log")
                payload = backend.import_portable_source(str(tg_contact), preferred_slot="2")
                accounts = backend.load_accounts()

                imported_zip = root / "accounts" / "2" / "imports" / archive.name
                self.assertEqual(payload["slot_number"], "2")
                self.assertEqual(payload["portable_kind"], "zip")
                self.assertTrue(imported_zip.exists())
                self.assertTrue(any(account.slot_number == "2" for account in accounts))
                slot2 = next(account for account in accounts if account.slot_number == "2")
                self.assertEqual(slot2.portable_source_kind, "zip")
                self.assertEqual(Path(slot2.portable_source_path), imported_zip)
        finally:
            mod.TELEGRAM_WORKSPACE_ROOT = old_root
            mod.USER_REGISTRY_PATH = old_registry
            mod.DEFAULT_PROFILE_DIR = old_default_profile

    def test_prepare_portable_runtime_builds_clone_and_ensure_connected_prefers_runtime_clone(self) -> None:
        old_root = mod.TELEGRAM_WORKSPACE_ROOT
        old_registry = mod.USER_REGISTRY_PATH
        old_default_profile = mod.DEFAULT_PROFILE_DIR
        try:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td) / "telegram_workspace"
                mod.TELEGRAM_WORKSPACE_ROOT = root
                mod.USER_REGISTRY_PATH = root / "registry" / "users.json"
                mod.DEFAULT_PROFILE_DIR = root / "profiles" / "default"
                mod.layout_mod.ensure_workspace(root, slots=1)
                archive = root / "accounts" / "1" / "imports" / "portable.zip"
                with zipfile.ZipFile(archive, "w") as handle:
                    handle.writestr("tdata/key_datas", b"zip-key")
                    handle.writestr("tdata/D877F783D5D3EF8Cs", b"zip-session")
                    handle.writestr("tdata/D877F783D5D3EF8C/maps", b"zip-maps")

                backend = mod.TelegramGuiBackend(action_log_path=root / "logs" / "actions.log")
                account = backend.load_accounts()[0]
                with (
                    patch.object(backend, "_run_tdata_helper", return_value={"ok": True, "items": []}),
                    patch.object(mod, "find_portable_telegram_binary", return_value=None),
                ):
                    state = backend.prepare_portable_runtime(account)
                    target = backend.ensure_connected(account, launch_browser=False)

                runtime_dir = root / "accounts" / "1" / "runtime" / "portable_tdata"
                alias_dir = root / "accounts" / "1" / "runtime" / "tdata"
                self.assertTrue(runtime_dir.exists())
                self.assertTrue((root / "accounts" / "1" / "runtime" / "portable_state.json").exists())
                self.assertTrue(alias_dir.is_symlink() or alias_dir.is_dir())
                if alias_dir.is_symlink():
                    self.assertEqual(alias_dir.resolve(), runtime_dir.resolve())
                else:
                    self.assertEqual((alias_dir / "key_datas").read_bytes(), (runtime_dir / "key_datas").read_bytes())
                self.assertEqual(state.state, "binary_missing")
                self.assertTrue(state.ready_for_export)
                self.assertEqual(target.tab_url, str(runtime_dir))
                self.assertTrue(target.client_id.startswith("tdata:"))
        finally:
            mod.TELEGRAM_WORKSPACE_ROOT = old_root
            mod.USER_REGISTRY_PATH = old_registry
            mod.DEFAULT_PROFILE_DIR = old_default_profile

    def test_prepare_portable_runtime_for_managed_profile_prefers_helper_clone(self) -> None:
        old_root = mod.TELEGRAM_WORKSPACE_ROOT
        old_registry = mod.USER_REGISTRY_PATH
        old_default_profile = mod.DEFAULT_PROFILE_DIR
        try:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td) / "telegram_workspace"
                mod.TELEGRAM_WORKSPACE_ROOT = root
                mod.USER_REGISTRY_PATH = root / "registry" / "users.json"
                mod.DEFAULT_PROFILE_DIR = root / "profiles" / "default"
                mod.layout_mod.ensure_workspace(root, slots=1)
                archive = Path(td) / "portable.zip"
                with zipfile.ZipFile(archive, "w") as handle:
                    handle.writestr("tdata/key_datas", b"zip-key")
                    handle.writestr("tdata/D877F783D5D3EF8Cs", b"zip-session")
                    handle.writestr("tdata/D877F783D5D3EF8C/maps", b"zip-maps")

                backend = mod.TelegramGuiBackend(action_log_path=root / "logs" / "actions.log")
                with patch.object(mod, "find_portable_telegram_binary", return_value=None):
                    status = backend.import_portable_profile(str(archive), profile_name="TG_CONTACT 4")
                    account = next(item for item in backend.load_accounts() if item.profile_source == str(status.profile_dir))
                    with patch.object(backend, "_run_tdata_helper", return_value={"ok": True, "items": []}):
                        state = backend.prepare_portable_runtime(account)
                        target = backend.ensure_connected(account, launch_browser=False)

                helper_tdata = status.profile_dir / "runtime" / "helper_workdir" / "tdata"
                self.assertTrue(helper_tdata.is_dir())
                self.assertEqual(state.state, "binary_missing")
                self.assertTrue(state.ready_for_export)
                self.assertEqual(state.runtime_dir, helper_tdata)
                self.assertEqual(state.helper_dir, helper_tdata.parent)
                self.assertEqual(state.helper_source, "source_tdata")
                self.assertEqual(target.tab_url, str(helper_tdata))
                self.assertTrue(target.client_id.startswith("tdata:"))
                self.assertNotEqual(state.runtime_dir, status.profile.tdata_dir)
        finally:
            mod.TELEGRAM_WORKSPACE_ROOT = old_root
            mod.USER_REGISTRY_PATH = old_registry
            mod.DEFAULT_PROFILE_DIR = old_default_profile

    def test_join_tdata_invite_uses_helper_for_managed_profile(self) -> None:
        backend = mod.TelegramGuiBackend(action_log_path=Path("/tmp/gui-actions.log"))
        account = mod.AccountOption(
            key="registry:tg_contact_4",
            label="TG_CONTACT 4",
            name="TG_CONTACT 4",
            token="token",
            profile_source="/tmp/profile",
            source_kind="registry",
            sort_key=(0, "tg_contact_4", "/tmp/profile"),
        )
        runtime_state = mod.PortableRuntimeState(
            slot_number="4",
            state="ready",
            detail="ready",
            runtime_dir=Path("/tmp/helper_tdata"),
            tdata_dir=Path("/tmp/helper_tdata"),
            ready_for_export=True,
            authorized=True,
        )
        with (
            patch.object(backend, "inspect_portable_source", return_value=mod.PortableSourceInfo(slot_number="4", path=Path("/tmp/profile"), kind="profile")),
            patch.object(backend, "prepare_portable_runtime", return_value=runtime_state),
            patch.object(backend, "_run_tdata_helper", return_value={"ok": True, "item": {"title": "Invite Chat", "peer_id": "-1001"}}) as helper_mock,
        ):
            payload = backend.join_tdata_invite(account, "https://t.me/+6FMgmFJCh0I4M2Yy")

        self.assertTrue(payload["ok"])
        helper_mock.assert_called_once_with(
            "join-invite",
            tdata_dir=Path("/tmp/helper_tdata"),
            extra_args=["--invite-link", "https://t.me/+6FMgmFJCh0I4M2Yy"],
            timeout_sec=mod.TDATA_LIST_TIMEOUT_SEC,
        )

    def test_resolve_tdata_chat_target_uses_helper_for_public_link(self) -> None:
        backend = mod.TelegramGuiBackend(action_log_path=Path("/tmp/gui-actions.log"))
        account = mod.AccountOption(
            key="registry:tg_contact_4",
            label="TG_CONTACT 4",
            name="TG_CONTACT 4",
            token="token",
            profile_source="/tmp/profile",
            source_kind="registry",
            sort_key=(0, "tg_contact_4", "/tmp/profile"),
        )
        runtime_state = mod.PortableRuntimeState(
            slot_number="4",
            state="ready",
            detail="ready",
            runtime_dir=Path("/tmp/helper_tdata"),
            tdata_dir=Path("/tmp/helper_tdata"),
            ready_for_export=True,
            authorized=True,
        )
        with (
            patch.object(backend, "inspect_portable_source", return_value=mod.PortableSourceInfo(slot_number="4", path=Path("/tmp/profile"), kind="profile")),
            patch.object(backend, "prepare_portable_runtime", return_value=runtime_state),
            patch.object(
                backend,
                "_run_tdata_helper",
                return_value={
                    "ok": True,
                    "access_state": "ok",
                    "item": {
                        "title": "Косметолог на миллион",
                        "chat_ref": "-1002269737802",
                        "peer_id": "-1002269737802",
                        "username": "@cosmetologna",
                        "subtitle": "channel",
                    },
                },
            ) as helper_mock,
        ):
            chat = backend.resolve_tdata_chat_target(account, "https://t.me/cosmetologna")

        self.assertEqual(chat.title, "Косметолог на миллион")
        self.assertEqual(chat.fragment, "-1002269737802")
        self.assertEqual(chat.url, "@cosmetologna")
        self.assertEqual(chat.source_kind, "resolved")
        helper_mock.assert_called_once_with(
            "resolve-chat",
            tdata_dir=Path("/tmp/helper_tdata"),
            extra_args=["--chat", "https://t.me/cosmetologna"],
            timeout_sec=mod.TDATA_LIST_TIMEOUT_SEC,
        )

    def test_resolve_tdata_chat_target_raises_for_resolved_but_no_access(self) -> None:
        backend = mod.TelegramGuiBackend(action_log_path=Path("/tmp/gui-actions.log"))
        account = mod.AccountOption(
            key="registry:tg_contact_4",
            label="TG_CONTACT 4",
            name="TG_CONTACT 4",
            token="token",
            profile_source="/tmp/profile",
            source_kind="registry",
            sort_key=(0, "tg_contact_4", "/tmp/profile"),
        )
        runtime_state = mod.PortableRuntimeState(
            slot_number="4",
            state="ready",
            detail="ready",
            runtime_dir=Path("/tmp/helper_tdata"),
            tdata_dir=Path("/tmp/helper_tdata"),
            ready_for_export=True,
            authorized=True,
        )
        with (
            patch.object(backend, "inspect_portable_source", return_value=mod.PortableSourceInfo(slot_number="4", path=Path("/tmp/profile"), kind="profile")),
            patch.object(backend, "prepare_portable_runtime", return_value=runtime_state),
            patch.object(
                backend,
                "_run_tdata_helper",
                return_value={
                    "ok": False,
                    "access_state": "resolved_but_no_access",
                    "detail": "History is not accessible for this profile.",
                    "item": {
                        "title": "Private chat",
                        "chat_ref": "-1001",
                        "peer_id": "-1001",
                    },
                },
            ),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                backend.resolve_tdata_chat_target(account, "@privatechat")

        self.assertIn("resolved_but_no_access", str(ctx.exception))

    def test_refresh_portable_profile_dir_syncs_stopped_launch_clone_into_helper_clone(self) -> None:
        old_root = mod.TELEGRAM_WORKSPACE_ROOT
        old_registry = mod.USER_REGISTRY_PATH
        old_default_profile = mod.DEFAULT_PROFILE_DIR
        try:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td) / "telegram_workspace"
                mod.TELEGRAM_WORKSPACE_ROOT = root
                mod.USER_REGISTRY_PATH = root / "registry" / "users.json"
                mod.DEFAULT_PROFILE_DIR = root / "profiles" / "default"
                mod.layout_mod.ensure_workspace(root, slots=1)
                archive = Path(td) / "portable.zip"
                with zipfile.ZipFile(archive, "w") as handle:
                    handle.writestr("tdata/key_datas", b"zip-key")
                    handle.writestr("tdata/D877F783D5D3EF8Cs", b"zip-session")
                    handle.writestr("tdata/D877F783D5D3EF8C/maps", b"zip-maps")

                backend = mod.TelegramGuiBackend(action_log_path=root / "logs" / "actions.log")
                with patch.object(mod, "find_portable_telegram_binary", return_value=None):
                    status = backend.import_portable_profile(str(archive), profile_name="TG_CONTACT 4")
                    launch_workdir = backend._prepare_isolated_portable_launch_clone(status)
                    launch_tdata = launch_workdir / "tdata"
                    (launch_tdata / "key_datas").write_bytes(b"launch-key")
                    helper_tdata = status.profile_dir / "runtime" / "helper_workdir" / "tdata"
                    self.assertEqual((helper_tdata / "key_datas").read_bytes(), b"zip-key")
                    with patch.object(backend, "_run_tdata_helper", return_value={"ok": True, "items": []}):
                        state = backend.refresh_portable_profile_dir(str(status.profile_dir))

                self.assertEqual((helper_tdata / "key_datas").read_bytes(), b"launch-key")
                self.assertEqual(state.state, "binary_missing")
                self.assertTrue(state.ready_for_export)
                self.assertEqual(state.helper_source, "launch_workdir")
                self.assertTrue(bool(state.last_sync_at))
        finally:
            mod.TELEGRAM_WORKSPACE_ROOT = old_root
            mod.USER_REGISTRY_PATH = old_registry
            mod.DEFAULT_PROFILE_DIR = old_default_profile

    def test_prepare_portable_runtime_marks_stale_helper_when_launch_clone_is_running(self) -> None:
        old_root = mod.TELEGRAM_WORKSPACE_ROOT
        old_registry = mod.USER_REGISTRY_PATH
        old_default_profile = mod.DEFAULT_PROFILE_DIR
        try:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td) / "telegram_workspace"
                mod.TELEGRAM_WORKSPACE_ROOT = root
                mod.USER_REGISTRY_PATH = root / "registry" / "users.json"
                mod.DEFAULT_PROFILE_DIR = root / "profiles" / "default"
                mod.layout_mod.ensure_workspace(root, slots=1)
                archive = Path(td) / "portable.zip"
                with zipfile.ZipFile(archive, "w") as handle:
                    handle.writestr("tdata/key_datas", b"zip-key")
                    handle.writestr("tdata/D877F783D5D3EF8Cs", b"zip-session")
                    handle.writestr("tdata/D877F783D5D3EF8C/maps", b"zip-maps")

                backend = mod.TelegramGuiBackend(action_log_path=root / "logs" / "actions.log")
                with patch.object(mod, "find_portable_telegram_binary", return_value=None):
                    status = backend.import_portable_profile(str(archive), profile_name="TG_CONTACT 4")
                    account = next(item for item in backend.load_accounts() if item.profile_source == str(status.profile_dir))
                    launch_workdir = backend._prepare_isolated_portable_launch_clone(status)
                    (launch_workdir / "tdata" / "key_datas").write_bytes(b"launch-key")
                    running_status = mod.PortableProfileStatus(
                        profile=status.profile,
                        running=True,
                        pid=12345,
                        state="running",
                        detail="Portable профиль уже запущен.",
                        log_path=status.log_path,
                    )
                    with patch.object(backend.portable_profiles, "status", return_value=running_status):
                        with patch.object(backend, "_run_tdata_helper", return_value={"ok": True, "items": []}):
                            state = backend.prepare_portable_runtime(account, force=False)

                self.assertEqual(state.state, "stale")
                self.assertTrue(state.ready_for_export)
                self.assertIn("после закрытия Telegram", state.detail)
                self.assertEqual(state.runtime_dir, status.profile_dir / "runtime" / "helper_workdir" / "tdata")
        finally:
            mod.TELEGRAM_WORKSPACE_ROOT = old_root
            mod.USER_REGISTRY_PATH = old_registry
            mod.DEFAULT_PROFILE_DIR = old_default_profile

    def test_refresh_portable_profile_dir_blocks_when_running_without_helper_clone(self) -> None:
        old_root = mod.TELEGRAM_WORKSPACE_ROOT
        old_registry = mod.USER_REGISTRY_PATH
        old_default_profile = mod.DEFAULT_PROFILE_DIR
        try:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td) / "telegram_workspace"
                mod.TELEGRAM_WORKSPACE_ROOT = root
                mod.USER_REGISTRY_PATH = root / "registry" / "users.json"
                mod.DEFAULT_PROFILE_DIR = root / "profiles" / "default"
                mod.layout_mod.ensure_workspace(root, slots=1)
                archive = Path(td) / "portable.zip"
                with zipfile.ZipFile(archive, "w") as handle:
                    handle.writestr("tdata/key_datas", b"zip-key")
                    handle.writestr("tdata/D877F783D5D3EF8Cs", b"zip-session")
                    handle.writestr("tdata/D877F783D5D3EF8C/maps", b"zip-maps")

                backend = mod.TelegramGuiBackend(action_log_path=root / "logs" / "actions.log")
                with patch.object(mod, "find_portable_telegram_binary", return_value=None):
                    status = backend.import_portable_profile(str(archive), profile_name="TG_CONTACT 4")
                    shutil.rmtree(status.profile_dir / "runtime" / "helper_workdir", ignore_errors=True)
                    backend._prepare_isolated_portable_launch_clone(status)
                    running_status = mod.PortableProfileStatus(
                        profile=status.profile,
                        running=True,
                        pid=12345,
                        state="running",
                        detail="Portable профиль уже запущен.",
                        log_path=status.log_path,
                    )
                    with patch.object(backend.portable_profiles, "status", return_value=running_status):
                        with self.assertRaisesRegex(RuntimeError, "helper-копия ещё не собрана"):
                            backend.refresh_portable_profile_dir(str(status.profile_dir))
        finally:
            mod.TELEGRAM_WORKSPACE_ROOT = old_root
            mod.USER_REGISTRY_PATH = old_registry
            mod.DEFAULT_PROFILE_DIR = old_default_profile

    def test_build_preflight_keeps_primary_tdata_when_portable_runtime_is_unauthorized(self) -> None:
        backend = mod.TelegramGuiBackend(action_log_path=Path("/tmp/gui-actions.log"))
        account = mod.AccountOption(
            key="auto:1",
            label="Slot 1",
            name="Slot 1",
            token="token",
            profile_source="/tmp/profile",
            source_kind="auto",
            sort_key=(0, "slot 1", "/tmp/profile"),
            slot_number="1",
        )
        source = mod.PortableSourceInfo(slot_number="1", path=Path("/tmp/source.zip"), kind="zip", detail="zip source")
        runtime = mod.PortableRuntimeState(
            slot_number="1",
            state="unauthorized",
            detail="Откройте portable Telegram для авторизации runtime clone.",
            source_path=Path("/tmp/source.zip"),
            source_kind="zip",
            runtime_dir=Path("/tmp/runtime/portable_tdata"),
            tdata_dir=Path("/tmp/runtime/portable_tdata"),
            ready_for_export=False,
            needs_rebuild=False,
            authorized=False,
        )
        bridge_ready = mod.FallbackReadiness(
            surface_key="bridge",
            surface_label="Telegram Web bridge",
            surface_badge="Fallback Bridge",
            state="ready",
            detail="Bridge ready",
            target=mod.BrowserTarget(
                client_id="client-1",
                tab_id=7,
                tab_title="Telegram",
                tab_url="https://web.telegram.org/a/",
            ),
        )
        cdp_ready = mod.FallbackReadiness(
            surface_key="cdp",
            surface_label="Chrome profile direct",
            surface_badge="Fallback CDP",
            state="ready",
            detail="CDP ready",
            target=mod.BrowserTarget(
                client_id="cdp:9333",
                tab_id=9333,
                tab_title="Telegram",
                tab_url="https://web.telegram.org/a/",
            ),
        )

        with (
            patch.object(backend, "resolve_profile_dir_safe", return_value=(Path("/tmp/profile"), "ready", "Profile ready")),
            patch.object(backend, "inspect_portable_source", return_value=source),
            patch.object(backend, "inspect_portable_runtime", return_value=runtime),
            patch.object(backend, "probe_bridge_readiness", return_value=bridge_ready),
            patch.object(backend, "probe_cdp_readiness", return_value=cdp_ready),
            patch.object(mod, "resolve_tdata_dir", return_value=None),
        ):
            info = backend.build_preflight(
                account=account,
                output_path=Path("/tmp/export.md"),
                preset_key="full_history",
                connected_target=None,
            )

        self.assertEqual(info.surface_key, "tdata")
        self.assertEqual(info.surface_badge, "Primary tdata")
        self.assertEqual({item.key: item.state for item in info.statuses}["surface"], "blocked")
        self.assertIn("Откройте portable Telegram", info.surface_reason)

    def test_launch_portable_telegram_uses_runtime_parent_as_workdir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            backend = mod.TelegramGuiBackend(action_log_path=Path(td) / "actions.log")
            binary = Path(td) / "Telegram"
            binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            binary.chmod(0o755)
            runtime_dir = Path(td) / "accounts" / "1" / "runtime" / "portable_tdata"
            runtime_dir.mkdir(parents=True)
            account = mod.AccountOption(
                key="auto:1",
                label="Slot 1",
                name="Slot 1",
                token="token",
                profile_source="/tmp/profile",
                source_kind="auto",
                sort_key=(0, "slot 1", "/tmp/profile"),
                slot_number="1",
            )
            state = mod.PortableRuntimeState(
                slot_number="1",
                state="ready",
                detail="Portable runtime clone готова.",
                source_path=Path("/tmp/source.zip"),
                source_kind="zip",
                runtime_dir=runtime_dir,
                tdata_dir=runtime_dir,
                binary_path=binary,
                ready_for_export=True,
                needs_rebuild=False,
                authorized=True,
            )
            spawned: dict[str, object] = {}

            def fake_popen(args, **kwargs):
                spawned["args"] = args
                spawned["cwd"] = kwargs.get("cwd")
                return SimpleNamespace(pid=12345)

            with (
                patch.object(backend, "prepare_portable_runtime", return_value=state),
                patch.object(mod.subprocess, "Popen", side_effect=fake_popen),
            ):
                message = backend.launch_portable_telegram(account)

        self.assertIn("Portable Telegram запущен", message)
        self.assertEqual(spawned["args"], [str(binary), "-workdir", str(runtime_dir.parent)])
        self.assertEqual(spawned["cwd"], str(binary.parent))
