from __future__ import annotations

import os
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import telegram_members_export_gui as mod
from scripts.telegram_gui.services import portable_profiles as portable_profiles_service


def _write_tdata_payload(tdata_dir: Path) -> None:
    tdata_dir.mkdir(parents=True, exist_ok=True)
    (tdata_dir / "key_datas").write_bytes(b"key")
    (tdata_dir / "D877F783D5D3EF8Cs").write_bytes(b"session")
    maps_dir = tdata_dir / "D877F783D5D3EF8C"
    maps_dir.mkdir(parents=True, exist_ok=True)
    (maps_dir / "maps").write_bytes(b"maps")


class TelegramGuiPortableProfilesTests(unittest.TestCase):
    def test_import_portable_profile_creates_managed_metadata_and_registry_row(self) -> None:
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
                    status = backend.import_portable_profile(
                        str(archive),
                        profile_name="AK",
                        account_username="@ak_user",
                        account_label="@AK",
                    )
                    profiles = backend.load_portable_profiles()
                    accounts = backend.load_accounts()

                self.assertTrue(status.profile_dir.is_dir())
                self.assertTrue((status.profile_dir / "portable-profile.json").exists())
                self.assertTrue((status.profile.portable_dir / "tdata").is_dir())
                self.assertTrue(any(item.profile_name == "AK" for item in profiles))
                account = next(item for item in accounts if item.profile_source == str(status.profile_dir))
                self.assertEqual(account.source_kind, "registry")
                self.assertEqual(account.portable_profile_dir, str(status.profile_dir))
                registry_text = mod.USER_REGISTRY_PATH.read_text(encoding="utf-8")
                self.assertIn(str(status.profile_dir), registry_text)
                self.assertNotIn(mod.DEFAULT_TOKEN, registry_text)
        finally:
            mod.TELEGRAM_WORKSPACE_ROOT = old_root
            mod.USER_REGISTRY_PATH = old_registry
            mod.DEFAULT_PROFILE_DIR = old_default_profile

    def test_adopt_portable_profile_writes_metadata_and_creates_workspace_link(self) -> None:
        old_root = mod.TELEGRAM_WORKSPACE_ROOT
        old_registry = mod.USER_REGISTRY_PATH
        old_default_profile = mod.DEFAULT_PROFILE_DIR
        try:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td) / "telegram_workspace"
                external = Path(td) / "ExternalPortable"
                portable_dir = external / "TelegramForcePortable"
                _write_tdata_payload(portable_dir / "tdata")
                binary = external / "Telegram"
                binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                binary.chmod(0o755)
                mod.TELEGRAM_WORKSPACE_ROOT = root
                mod.USER_REGISTRY_PATH = root / "registry" / "users.json"
                mod.DEFAULT_PROFILE_DIR = root / "profiles" / "default"
                mod.layout_mod.ensure_workspace(root, slots=1)

                backend = mod.TelegramGuiBackend(action_log_path=root / "logs" / "actions.log")
                with patch.object(mod, "find_portable_telegram_binary", return_value=binary):
                    status = backend.adopt_portable_profile(
                        str(external),
                        profile_name="USER2",
                        account_username="@user2",
                        account_label="@USER2",
                    )
                    profiles = backend.load_portable_profiles()

                self.assertTrue((external / "portable-profile.json").exists())
                self.assertEqual(status.profile_dir, external.resolve())
                self.assertTrue(any(item.profile_dir == external.resolve() for item in profiles))
                linked = list((root / "PortableProfiles").glob("LinkedPortable-*"))
                self.assertTrue(linked)
                self.assertTrue(any(item.is_symlink() for item in linked))
        finally:
            mod.TELEGRAM_WORKSPACE_ROOT = old_root
            mod.USER_REGISTRY_PATH = old_registry
            mod.DEFAULT_PROFILE_DIR = old_default_profile

    def test_load_portable_profiles_syncs_legacy_slot_runtime_metadata(self) -> None:
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
                _write_tdata_payload(runtime_tdata)

                backend = mod.TelegramGuiBackend(action_log_path=root / "logs" / "actions.log")
                with patch.object(mod, "find_portable_telegram_binary", return_value=None):
                    profiles = backend.load_portable_profiles()

                self.assertTrue((root / "accounts" / "1" / "runtime" / "portable-profile.json").exists())
                legacy = next(item for item in profiles if item.profile.slot_number == "1")
                self.assertEqual(legacy.profile.source_kind, "slot_runtime")
                self.assertEqual(legacy.state, "binary_missing")
        finally:
            mod.TELEGRAM_WORKSPACE_ROOT = old_root
            mod.USER_REGISTRY_PATH = old_registry
            mod.DEFAULT_PROFILE_DIR = old_default_profile

    def test_launch_portable_profile_dir_reports_already_running(self) -> None:
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
                binary = Path(td) / "Telegram"
                binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                binary.chmod(0o755)
                archive = Path(td) / "portable.zip"
                with zipfile.ZipFile(archive, "w") as handle:
                    handle.writestr("tdata/key_datas", b"zip-key")
                    handle.writestr("tdata/D877F783D5D3EF8Cs", b"zip-session")
                    handle.writestr("tdata/D877F783D5D3EF8C/maps", b"zip-maps")

                backend = mod.TelegramGuiBackend(action_log_path=root / "logs" / "actions.log")
                with patch.object(mod, "find_portable_telegram_binary", return_value=binary):
                    status = backend.import_portable_profile(str(archive), profile_name="RUNNER")

                spawned: dict[str, object] = {}

                def fake_popen(args, **kwargs):
                    spawned["args"] = args
                    spawned["cwd"] = kwargs.get("cwd")
                    return SimpleNamespace(pid=os.getpid())

                with patch.object(portable_profiles_service.subprocess, "Popen", side_effect=fake_popen):
                    launched, already_running = backend.launch_portable_profile_dir(str(status.profile_dir))
                    second, second_running = backend.launch_portable_profile_dir(str(status.profile_dir))

                self.assertFalse(already_running)
                self.assertTrue(second_running)
                self.assertEqual(launched.profile_dir, status.profile_dir)
                self.assertEqual(second.profile_dir, status.profile_dir)
                launch_workdir = status.profile_dir / "runtime" / "launch_workdir"
                helper_tdata = status.profile_dir / "runtime" / "helper_workdir" / "tdata"
                self.assertEqual(
                    spawned["args"],
                    [str(binary), "-workdir", str(launch_workdir)],
                )
                self.assertEqual(spawned["cwd"], str(binary.parent))
                self.assertTrue((launch_workdir / "tdata").is_dir())
                self.assertTrue(helper_tdata.is_dir())
                self.assertTrue((status.profile.portable_dir / "tdata").is_dir())
        finally:
            mod.TELEGRAM_WORKSPACE_ROOT = old_root
            mod.USER_REGISTRY_PATH = old_registry
            mod.DEFAULT_PROFILE_DIR = old_default_profile

    def test_import_portable_profile_can_set_default_primary_label(self) -> None:
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
                    backend.import_portable_profile(
                        str(archive),
                        profile_name="TG_CONTACT 2",
                        set_default=True,
                    )
                    accounts = backend.load_accounts()
                    profiles = backend.load_portable_profiles()

                self.assertTrue(any(item.profile_name == "TG_CONTACT 2" for item in profiles))
                self.assertEqual(accounts[0].label, "TG_CONTACT 2")
                self.assertTrue(accounts[0].profile_source.endswith("PortableProfiles/TelegramPortable-tg-contact-2"))
                registry_text = mod.USER_REGISTRY_PATH.read_text(encoding="utf-8")
                self.assertIn('"default_user": "TG_CONTACT 2"', registry_text)
        finally:
            mod.TELEGRAM_WORKSPACE_ROOT = old_root
            mod.USER_REGISTRY_PATH = old_registry
            mod.DEFAULT_PROFILE_DIR = old_default_profile

    def test_remove_profile_deletes_managed_directory_and_preserves_adopted_external_folder(self) -> None:
        old_root = mod.TELEGRAM_WORKSPACE_ROOT
        old_registry = mod.USER_REGISTRY_PATH
        old_default_profile = mod.DEFAULT_PROFILE_DIR
        try:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td) / "telegram_workspace"
                external = Path(td) / "ExternalPortable"
                mod.TELEGRAM_WORKSPACE_ROOT = root
                mod.USER_REGISTRY_PATH = root / "registry" / "users.json"
                mod.DEFAULT_PROFILE_DIR = root / "profiles" / "default"
                mod.layout_mod.ensure_workspace(root, slots=1)
                archive = Path(td) / "portable.zip"
                with zipfile.ZipFile(archive, "w") as handle:
                    handle.writestr("tdata/key_datas", b"zip-key")
                    handle.writestr("tdata/D877F783D5D3EF8Cs", b"zip-session")
                    handle.writestr("tdata/D877F783D5D3EF8C/maps", b"zip-maps")
                portable_dir = external / "TelegramForcePortable"
                _write_tdata_payload(portable_dir / "tdata")
                binary = Path(td) / "Telegram"
                binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                binary.chmod(0o755)
                shutil.copy2(binary, external / "Telegram")

                backend = mod.TelegramGuiBackend(action_log_path=root / "logs" / "actions.log")
                with patch.object(mod, "find_portable_telegram_binary", return_value=binary):
                    managed = backend.import_portable_profile(str(archive), profile_name="TEMP-MANAGED")
                    adopted = backend.adopt_portable_profile(str(external), profile_name="TEMP-ADOPTED")
                    managed_secret_ref = mod.registry_mod.find_user_by_profile(
                        mod.registry_mod.load_registry(mod.USER_REGISTRY_PATH),
                        profile=str(managed.profile_dir),
                    ).get("secret_ref")
                    adopted_secret_ref = mod.registry_mod.find_user_by_profile(
                        mod.registry_mod.load_registry(mod.USER_REGISTRY_PATH),
                        profile=str(adopted.profile_dir),
                    ).get("secret_ref")
                    managed_result = backend.remove_portable_profile(str(managed.profile_dir))
                    adopted_result = backend.remove_portable_profile(str(adopted.profile_dir))

                self.assertFalse(managed.profile_dir.exists())
                self.assertTrue(external.exists())
                self.assertTrue((external / "portable-profile.json").exists())
                self.assertEqual(managed_result.profile_kind, "managed")
                self.assertFalse(managed_result.external_data_preserved)
                self.assertEqual(adopted_result.profile_kind, "adopted")
                self.assertTrue(adopted_result.external_data_preserved)
                registry = mod.registry_mod.load_registry(mod.USER_REGISTRY_PATH)
                self.assertFalse(mod.registry_mod.find_user_by_profile(registry, profile=str(managed.profile_dir)))
                self.assertFalse(mod.registry_mod.find_user_by_profile(registry, profile=str(adopted.profile_dir)))
                if managed_secret_ref:
                    self.assertFalse((root / "registry" / "secrets" / managed_secret_ref).exists())
                if adopted_secret_ref:
                    self.assertFalse((root / "registry" / "secrets" / adopted_secret_ref).exists())
                linked = list((root / "PortableProfiles").glob("LinkedPortable-*"))
                self.assertFalse(linked)
        finally:
            mod.TELEGRAM_WORKSPACE_ROOT = old_root
            mod.USER_REGISTRY_PATH = old_registry
            mod.DEFAULT_PROFILE_DIR = old_default_profile

    def test_remove_missing_adopted_profile_cleans_registry_and_workspace_link(self) -> None:
        old_root = mod.TELEGRAM_WORKSPACE_ROOT
        old_registry = mod.USER_REGISTRY_PATH
        old_default_profile = mod.DEFAULT_PROFILE_DIR
        try:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td) / "telegram_workspace"
                external = Path(td) / "ExternalPortable"
                archive = Path(td) / "portable.zip"
                portable_dir = external / "TelegramForcePortable"
                _write_tdata_payload(portable_dir / "tdata")
                binary = Path(td) / "Telegram"
                binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                binary.chmod(0o755)
                shutil.copy2(binary, external / "Telegram")
                with zipfile.ZipFile(archive, "w") as handle:
                    handle.writestr("tdata/key_datas", b"zip-key")
                    handle.writestr("tdata/D877F783D5D3EF8Cs", b"zip-session")
                    handle.writestr("tdata/D877F783D5D3EF8C/maps", b"zip-maps")

                mod.TELEGRAM_WORKSPACE_ROOT = root
                mod.USER_REGISTRY_PATH = root / "registry" / "users.json"
                mod.DEFAULT_PROFILE_DIR = root / "profiles" / "default"
                mod.layout_mod.ensure_workspace(root, slots=1)

                backend = mod.TelegramGuiBackend(action_log_path=root / "logs" / "actions.log")
                with patch.object(mod, "find_portable_telegram_binary", return_value=binary):
                    backend.import_portable_profile(str(archive), profile_name="TG_CONTACT 2", set_default=True)
                    adopted = backend.adopt_portable_profile(str(external), profile_name="@AK-ADOPTED")

                linked = list((root / "PortableProfiles").glob("LinkedPortable-*"))
                self.assertTrue(linked)
                shutil.rmtree(external)

                result = backend.remove_portable_profile(str(adopted.profile_dir))
                registry = mod.registry_mod.load_registry(mod.USER_REGISTRY_PATH)
                accounts = backend.load_accounts()

                self.assertEqual(result.profile_kind, "adopted")
                self.assertTrue(result.external_data_preserved)
                self.assertFalse(mod.registry_mod.find_user_by_profile(registry, profile=str(adopted.profile_dir)))
                self.assertFalse(list((root / "PortableProfiles").glob("LinkedPortable-*")))
                self.assertTrue(any(account.label == "TG_CONTACT 2" for account in accounts))
                self.assertFalse(any(account.profile_source == str(adopted.profile_dir) for account in accounts))
        finally:
            mod.TELEGRAM_WORKSPACE_ROOT = old_root
            mod.USER_REGISTRY_PATH = old_registry
            mod.DEFAULT_PROFILE_DIR = old_default_profile
