from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tarfile
import tempfile
import unittest
import zipfile
from argparse import Namespace
from pathlib import Path
from unittest import mock


def _load_module():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "scripts" / "telegram_portable.py"
    spec = importlib.util.spec_from_file_location("telegram_portable", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_runtime_archive(archive_path: Path) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_root = Path(tmpdir)
        runtime_dir = temp_root / "Telegram"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        (runtime_dir / "Telegram").write_text("#!/usr/bin/env bash\nsleep 60\n", encoding="utf-8")
        (runtime_dir / "Updater").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        with tarfile.open(archive_path, mode="w:xz") as tf:
            tf.add(runtime_dir, arcname="Telegram")


def _write_tdata_zip(zip_path: Path, *, nested: bool = False, key_datas: str = "alpha") -> None:
    prefix = "payload/tdata" if nested else "tdata"
    with zipfile.ZipFile(zip_path, mode="w") as zf:
        zf.writestr(f"{prefix}/key_datas", key_datas)
        zf.writestr(f"{prefix}/D877F783D5D3EF8Cs", "session")
        zf.writestr(f"{prefix}/D877F783D5D3EF8C/maps", "maps")


class TelegramPortableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = _load_module()

    def _call_json(self, func, namespace) -> dict[str, object]:
        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            rc = func(namespace)
        self.assertEqual(rc, 0)
        return json.loads(stdout.getvalue())

    def test_sanitize_profile_name_normalizes_and_strips_prefix(self) -> None:
        self.assertEqual(self.mod.sanitize_profile_name("AK"), "AK")
        self.assertEqual(self.mod.sanitize_profile_name("TelegramPortable-AK"), "AK")
        self.assertEqual(self.mod.sanitize_profile_name(" ak / demo "), "ak-demo")

    def test_import_zip_creates_profile_dir_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            runtime_archive = tmp / "telegram-runtime.tar.xz"
            zip_path = tmp / "ak.zip"
            output_root = tmp / "profiles"
            runtime_cache = tmp / "runtime-cache"
            _write_runtime_archive(runtime_archive)
            _write_tdata_zip(zip_path, nested=True, key_datas="alpha")

            payload = self._call_json(
                self.mod.command_import_zip,
                Namespace(
                    zip=str(zip_path),
                    profile_name="AK",
                    output_root=str(output_root),
                    runtime_cache_dir=str(runtime_cache),
                    runtime_archive=str(runtime_archive),
                    download_url=self.mod.DEFAULT_TELEGRAM_LINUX_URL,
                    refresh_runtime=False,
                    launch=False,
                ),
            )

            profile_dir = output_root / "TelegramPortable-AK"
            self.assertEqual(payload["mode"], "created")
            self.assertEqual(payload["profile_dir"], str(profile_dir))
            self.assertTrue((profile_dir / "Telegram").is_file())
            self.assertTrue((profile_dir / "Updater").is_file())
            self.assertEqual((profile_dir / "TelegramForcePortable" / "tdata" / "key_datas").read_text(encoding="utf-8"), "alpha")
            metadata_path = Path(str(payload["metadata_path"]))
            self.assertTrue(metadata_path.is_file())
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(metadata["runtime"]["source"], "archive")
            self.assertEqual(metadata["source_zip"], str(zip_path))

    def test_import_zip_replaces_existing_tdata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            runtime_archive = tmp / "telegram-runtime.tar.xz"
            zip_alpha = tmp / "alpha.zip"
            zip_beta = tmp / "beta.zip"
            output_root = tmp / "profiles"
            runtime_cache = tmp / "runtime-cache"
            _write_runtime_archive(runtime_archive)
            _write_tdata_zip(zip_alpha, key_datas="alpha")
            _write_tdata_zip(zip_beta, key_datas="beta")

            self._call_json(
                self.mod.command_import_zip,
                Namespace(
                    zip=str(zip_alpha),
                    profile_name="AK",
                    output_root=str(output_root),
                    runtime_cache_dir=str(runtime_cache),
                    runtime_archive=str(runtime_archive),
                    download_url=self.mod.DEFAULT_TELEGRAM_LINUX_URL,
                    refresh_runtime=False,
                    launch=False,
                ),
            )

            payload = self._call_json(
                self.mod.command_import_zip,
                Namespace(
                    zip=str(zip_beta),
                    profile_name="AK",
                    output_root=str(output_root),
                    runtime_cache_dir=str(runtime_cache),
                    runtime_archive=None,
                    download_url=self.mod.DEFAULT_TELEGRAM_LINUX_URL,
                    refresh_runtime=False,
                    launch=False,
                ),
            )

            profile_dir = output_root / "TelegramPortable-AK"
            self.assertEqual(payload["mode"], "updated")
            self.assertEqual((profile_dir / "TelegramForcePortable" / "tdata" / "key_datas").read_text(encoding="utf-8"), "beta")
            self.assertEqual(payload["runtime"]["source"], "cache")

    def test_launch_command_reports_already_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            output_root = tmp / "profiles"
            profile_dir = output_root / "TelegramPortable-AK"
            profile_dir.mkdir(parents=True, exist_ok=True)
            (profile_dir / "Telegram").write_text("#!/usr/bin/env bash\nsleep 60\n", encoding="utf-8")

            with mock.patch.object(self.mod, "find_running_pids", return_value=[4242]):
                with mock.patch.object(self.mod.subprocess, "Popen") as popen_mock:
                    payload = self._call_json(
                        self.mod.command_launch,
                        Namespace(
                            profile_name="AK",
                            output_root=str(output_root),
                        ),
                    )

            self.assertEqual(payload["launch"]["status"], "already_running")
            self.assertEqual(payload["launch"]["pids"], [4242])
            popen_mock.assert_not_called()

    def test_launch_portable_starts_process_when_not_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = Path(tmpdir)
            (target_dir / "Telegram").write_text("#!/usr/bin/env bash\nsleep 60\n", encoding="utf-8")
            with mock.patch.object(self.mod, "find_running_pids", return_value=[]):
                fake_process = mock.Mock(pid=9876)
                with mock.patch.object(self.mod.subprocess, "Popen", return_value=fake_process) as popen_mock:
                    payload = self.mod.launch_portable(target_dir)

            self.assertEqual(payload["status"], "started")
            self.assertEqual(payload["pid"], 9876)
            self.assertEqual(payload["log_path"], str(target_dir / "portable-launch.log"))
            popen_mock.assert_called_once()
