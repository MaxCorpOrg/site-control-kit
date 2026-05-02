from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tarfile
import tempfile
import types
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
        self.assertEqual(self.mod.sanitize_profile_name("TelegramPortableAK"), "AK")
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

    def test_adopt_existing_legacy_profile_writes_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_dir = Path(tmpdir) / "TelegramPortableAK"
            tdata_dir = profile_dir / "TelegramForcePortable" / "tdata"
            tdata_dir.mkdir(parents=True, exist_ok=True)
            (profile_dir / "Telegram").write_text("#!/usr/bin/env bash\nsleep 60\n", encoding="utf-8")
            (tdata_dir / "key_datas").write_text("session", encoding="utf-8")

            with mock.patch.object(self.mod, "find_running_pids", return_value=[111]):
                with mock.patch.object(self.mod, "_wmctrl_windows_by_pid", return_value={111: [{"window_id": "0x1", "title": "Shop"}]}):
                    payload = self._call_json(
                        self.mod.command_adopt,
                        Namespace(
                            profile_dir=str(profile_dir),
                            profile_name="AK",
                            account_username="@M_a_g_g_i_e",
                            account_label="Maggie",
                        ),
                    )

            metadata_path = profile_dir / "portable-profile.json"
            self.assertTrue(metadata_path.is_file())
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(metadata["profile_name"], "AK")
            self.assertEqual(metadata["account"]["username"], "@M_a_g_g_i_e")
            self.assertTrue(payload["running"])
            self.assertEqual(payload["windows"][0]["window_id"], "0x1")

    def test_status_accepts_profile_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_dir = Path(tmpdir) / "TelegramPortableAK"
            profile_dir.mkdir(parents=True, exist_ok=True)
            (profile_dir / "Telegram").write_text("#!/usr/bin/env bash\nsleep 60\n", encoding="utf-8")

            with mock.patch.object(self.mod, "find_running_pids", return_value=[]):
                with mock.patch.object(self.mod, "_wmctrl_windows_by_pid", return_value={}):
                    payload = self._call_json(
                        self.mod.command_status,
                        Namespace(
                            profile_name=None,
                            profile_dir=str(profile_dir),
                            output_root=str(Path(tmpdir)),
                        ),
                    )

            self.assertEqual(payload["profile_name"], "AK")
            self.assertFalse(payload["running"])

    def test_wmctrl_windows_by_pid_reads_geometry_and_title(self) -> None:
        output = "0x0460002e 0 10413 2746 506 1110 642 GIGA Жиротоп Shop\n"

        class _Proc:
            returncode = 0
            stdout = output

        with mock.patch.object(self.mod.subprocess, "run", return_value=_Proc()):
            windows_by_pid = self.mod._wmctrl_windows_by_pid()

        self.assertEqual(windows_by_pid[10413][0]["window_id"], "0x0460002e")
        self.assertEqual(windows_by_pid[10413][0]["x"], 2746)
        self.assertEqual(windows_by_pid[10413][0]["width"], 1110)
        self.assertEqual(windows_by_pid[10413][0]["title"], "Жиротоп Shop")

    def test_open_uri_dry_run_builds_portable_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_dir = Path(tmpdir) / "TelegramPortableAK"
            profile_dir.mkdir(parents=True, exist_ok=True)
            (profile_dir / "Telegram").write_text("#!/usr/bin/env bash\nsleep 60\n", encoding="utf-8")

            payload = self._call_json(
                self.mod.command_open_uri,
                Namespace(
                    profile_name=None,
                    profile_dir=str(profile_dir),
                    output_root=str(Path(tmpdir)),
                    uri="tg://resolve?domain=alice_123",
                    dry_run=True,
                ),
            )

            self.assertEqual(payload["status"], "dry_run")
            self.assertEqual(payload["command"], [str(profile_dir / "Telegram"), "tg://resolve?domain=alice_123"])

    def test_log_diagnose_surfaces_peer_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_dir = Path(tmpdir) / "TelegramPortableAK"
            portable_dir = profile_dir / "TelegramForcePortable"
            portable_dir.mkdir(parents=True, exist_ok=True)
            (profile_dir / "Telegram").write_text("#!/usr/bin/env bash\nsleep 60\n", encoding="utf-8")
            (portable_dir / "log.txt").write_text(
                "\n".join(
                    [
                        "[2026.04.26 11:04:45] RPC Error: request 1968 got fail with code 400, error PEER_FLOOD",
                        "[2026.04.26 11:05:39] RPC Error: request 1978 got fail with code 400, error PEER_ID_INVALID",
                        "[2026.04.26 11:05:40] App Error: Can't read history till unknown local message.",
                        "[2026.04.26 11:05:41] Working dir: /tmp/TelegramForcePortable/",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            payload = self._call_json(
                self.mod.command_log_diagnose,
                Namespace(
                    profile_name=None,
                    profile_dir=str(profile_dir),
                    output_root=str(Path(tmpdir)),
                    tail_lines=100,
                    max_events=10,
                ),
            )

            self.assertEqual(payload["status"], "completed")
            self.assertTrue(payload["working_dir_seen"])
            self.assertEqual(payload["event_counts"]["RPC Error"], 2)
            self.assertEqual(payload["event_counts"]["App Error"], 1)
            self.assertEqual([item["code"] for item in payload["alerts"]], ["PEER_FLOOD", "PEER_ID_INVALID"])
            self.assertEqual(payload["recent_events"][-1]["kind"], "App Error")

    def test_type_text_dry_run_counts_sequences(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_dir = Path(tmpdir) / "TelegramPortableAK"
            profile_dir.mkdir(parents=True, exist_ok=True)
            with mock.patch.object(
                self.mod,
                "profile_status",
                return_value={"windows": [{"window_id": "0x1"}]},
            ):
                payload = self._call_json(
                    self.mod.command_type_text,
                    Namespace(
                        profile_name=None,
                        profile_dir=str(profile_dir),
                        output_root=str(Path(tmpdir)),
                        window_id="",
                        text="https://t.me/Zhirotop_shop",
                        press_enter=True,
                        dry_run=True,
                    ),
                )

            self.assertEqual(payload["status"], "dry_run")
            self.assertEqual(payload["window_id"], "0x1")
            self.assertTrue(payload["sequence_count"] > len("https://t.me/Zhirotop_shop"))

    def test_parse_x11_chords_splits_repeatable_sequences(self) -> None:
        sequences = self.mod._parse_x11_chords(["Control_L+f", "Return", "Shift_L+Tab"])
        self.assertEqual(sequences, [["Control_L", "f"], ["Return"], ["Shift_L", "Tab"]])

    def test_send_x11_key_sequence_uses_xtest_events(self) -> None:
        fake_events: list[tuple[int, int]] = []

        class _FakeDisplay:
            def keysym_to_keycode(self, keysym):
                return int(keysym)

            def sync(self):
                return None

        x_module = types.SimpleNamespace(KeyPress=2, KeyRelease=3)
        keymap = {"Control_L": 37, "f": 41, "Return": 36}
        xk_module = types.SimpleNamespace(string_to_keysym=lambda name: keymap.get(name, 0))
        display_module = types.ModuleType("Xlib.display")
        display_module.Display = lambda: _FakeDisplay()
        xtest_module = types.ModuleType("Xlib.ext.xtest")
        xtest_module.fake_input = lambda _display, event_type, keycode: fake_events.append((event_type, keycode))
        ext_module = types.ModuleType("Xlib.ext")
        ext_module.xtest = xtest_module
        xlib_module = types.ModuleType("Xlib")
        xlib_module.X = x_module
        xlib_module.XK = xk_module
        xlib_module.display = display_module

        with mock.patch.object(self.mod, "sys_platform_is_not_linux", return_value=False):
            with mock.patch.object(self.mod, "_focus_x11_window", return_value=True):
                with mock.patch.dict(
                    sys.modules,
                    {
                        "Xlib": xlib_module,
                        "Xlib.display": display_module,
                        "Xlib.ext": ext_module,
                        "Xlib.ext.xtest": xtest_module,
                    },
                ):
                    ok = self.mod._send_x11_key_sequence("0x1", [["Control_L", "f"], ["Return"]])

        self.assertTrue(ok)
        self.assertEqual(
            fake_events,
            [
                (2, 37),
                (2, 41),
                (3, 41),
                (3, 37),
                (2, 36),
                (3, 36),
            ],
        )

    def test_press_keys_dry_run_reports_sequences(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_dir = Path(tmpdir) / "TelegramPortableAK"
            profile_dir.mkdir(parents=True, exist_ok=True)
            with mock.patch.object(
                self.mod,
                "profile_status",
                return_value={"windows": [{"window_id": "0x9"}]},
            ):
                payload = self._call_json(
                    self.mod.command_press_keys,
                    Namespace(
                        profile_name=None,
                        profile_dir=str(profile_dir),
                        output_root=str(Path(tmpdir)),
                        window_id="",
                        sequence=["Control_L+f", "Return"],
                        dry_run=True,
                    ),
                )

            self.assertEqual(payload["status"], "dry_run")
            self.assertEqual(payload["window_id"], "0x9")
            self.assertEqual(payload["sequence_count"], 2)
            self.assertEqual(payload["sequences"], [["Control_L", "f"], ["Return"]])

    def test_node_matches_query_respects_state_filters(self) -> None:
        node = {
            "role": "push button",
            "name": "Info",
            "visible": True,
            "states": ["enabled", "showing", "focused"],
        }

        self.assertTrue(
            self.mod._node_matches_query(
                node,
                query="Info",
                role="push button",
                match_mode="exact",
                visible_only=True,
                state_filters=["focused", "showing"],
            )
        )
        self.assertFalse(
            self.mod._node_matches_query(
                node,
                query="Info",
                role="push button",
                match_mode="exact",
                visible_only=True,
                state_filters=["editable"],
            )
        )
        self.assertFalse(
            self.mod._node_matches_query(
                {
                    "role": "push button",
                    "name": "Info",
                    "visible": True,
                    "states": ["enabled", "visible"],
                    "showing": False,
                },
                query="Info",
                role="push button",
                match_mode="exact",
                visible_only=True,
                state_filters=[],
            )
        )

    def test_window_click_dry_run_uses_window_geometry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_dir = Path(tmpdir) / "TelegramPortableAK"
            profile_dir.mkdir(parents=True, exist_ok=True)
            with mock.patch.object(
                self.mod,
                "profile_status",
                return_value={"windows": [{"window_id": "0x2", "x": 100, "y": 50, "width": 1000, "height": 500}]},
            ):
                with mock.patch.object(self.mod, "_pick_accessible_window", side_effect=RuntimeError("no a11y")):
                    payload = self._call_json(
                        self.mod.command_window_click,
                        Namespace(
                            profile_name=None,
                            profile_dir=str(profile_dir),
                            output_root=str(Path(tmpdir)),
                            window_id="",
                            x_ratio=0.9,
                            y_ratio=0.2,
                            button=1,
                            coordinate_space="auto",
                            dry_run=True,
                        ),
                    )

            self.assertEqual(payload["status"], "dry_run")
            self.assertEqual(payload["window_id"], "0x2")
            self.assertEqual((payload["x"], payload["y"]), (1000, 150))
            self.assertEqual(payload["coordinate_space"], "window_geometry")

    def test_window_click_dry_run_prefers_accessible_window_extents(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_dir = Path(tmpdir) / "TelegramPortableAK"
            profile_dir.mkdir(parents=True, exist_ok=True)
            with mock.patch.object(
                self.mod,
                "profile_status",
                return_value={"windows": [{"window_id": "0x2", "x": 1000, "y": 500, "width": 1600, "height": 1200}]},
            ):
                with mock.patch.object(
                    self.mod,
                    "_pick_accessible_window",
                    return_value=(None, None, {"windows": [{"window_id": "0x2", "x": 1000, "y": 500, "width": 1600, "height": 1200}]}, {"x": 250, "y": 100, "width": 800, "height": 600}),
                ):
                    payload = self._call_json(
                        self.mod.command_window_click,
                        Namespace(
                            profile_name=None,
                            profile_dir=str(profile_dir),
                            output_root=str(Path(tmpdir)),
                            window_id="",
                            x_ratio=0.5,
                            y_ratio=0.25,
                            button=1,
                            coordinate_space="auto",
                            dry_run=True,
                        ),
                    )

            self.assertEqual(payload["status"], "dry_run")
            self.assertEqual(payload["window_id"], "0x2")
            self.assertEqual((payload["x"], payload["y"]), (650, 250))
            self.assertEqual(payload["coordinate_space"], "accessible_window")

    def test_window_click_dry_run_respects_explicit_window_geometry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_dir = Path(tmpdir) / "TelegramPortableAK"
            profile_dir.mkdir(parents=True, exist_ok=True)
            with mock.patch.object(
                self.mod,
                "profile_status",
                return_value={"windows": [{"window_id": "0x2", "x": 1000, "y": 500, "width": 1600, "height": 1200}]},
            ):
                with mock.patch.object(
                    self.mod,
                    "_pick_accessible_window",
                    return_value=(None, None, {"windows": [{"window_id": "0x2", "x": 1000, "y": 500, "width": 1600, "height": 1200}]}, {"x": 250, "y": 100, "width": 800, "height": 600}),
                ):
                    payload = self._call_json(
                        self.mod.command_window_click,
                        Namespace(
                            profile_name=None,
                            profile_dir=str(profile_dir),
                            output_root=str(Path(tmpdir)),
                            window_id="",
                            x_ratio=0.5,
                            y_ratio=0.25,
                            button=1,
                            coordinate_space="window_geometry",
                            dry_run=True,
                        ),
                    )

            self.assertEqual(payload["status"], "dry_run")
            self.assertEqual(payload["window_id"], "0x2")
            self.assertEqual((payload["x"], payload["y"]), (1800, 800))
            self.assertEqual(payload["coordinate_space"], "window_geometry")

    def test_window_screenshot_command_delegates_to_capture_helper(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_dir = Path(tmpdir) / "TelegramPortableAK"
            profile_dir.mkdir(parents=True, exist_ok=True)
            expected = {
                "status": "completed",
                "window_id": "0x77",
                "output_path": str(Path(tmpdir) / "shot.png"),
                "width": 1200,
                "height": 800,
            }
            with mock.patch.object(self.mod, "capture_portable_window_screenshot", return_value=expected) as capture_mock:
                payload = self._call_json(
                    self.mod.command_window_screenshot,
                    Namespace(
                        profile_name=None,
                        profile_dir=str(profile_dir),
                        output_root=str(Path(tmpdir)),
                        window_id="",
                        output=str(Path(tmpdir) / "shot.png"),
                    ),
                )

        self.assertEqual(payload, expected)
        capture_mock.assert_called_once()

    def test_accessible_click_point_falls_back_to_ancestor_segments(self) -> None:
        point = self.mod._accessible_click_point(
            {
                "path": [1, 0, 1],
                "extents": {"x": 0, "y": 0, "width": 0, "height": 0},
                "ancestors": [
                    {
                        "path": [],
                        "path_text": "/",
                        "child_count": 2,
                        "extents": {"x": 10, "y": 20, "width": 200, "height": 50},
                    },
                    {
                        "path": [1],
                        "path_text": "/1",
                        "child_count": 1,
                        "extents": {"x": 0, "y": 0, "width": 0, "height": 0},
                    },
                    {
                        "path": [1, 0],
                        "path_text": "/1/0",
                        "child_count": 3,
                        "extents": {"x": 100, "y": 200, "width": 300, "height": 60},
                    },
                ],
            }
        )
        self.assertEqual(point["mode"], "ancestor_segment")
        self.assertEqual((point["x"], point["y"]), (250, 230))
        self.assertEqual(point["branch_index"], 1)
        self.assertEqual(point["segments"], 3)

    def test_accessible_click_point_prefers_resolved_extents(self) -> None:
        point = self.mod._accessible_click_point(
            {
                "path": [0],
                "extents": {"x": 300, "y": 200, "width": 120, "height": 40},
                "resolved_extents": {"x": 1300, "y": 900, "width": 240, "height": 80},
                "ancestors": [],
            }
        )
        self.assertEqual(point["mode"], "direct_extents")
        self.assertEqual((point["x"], point["y"]), (1420, 940))

    def test_resolved_accessible_extents_translate_to_window_geometry(self) -> None:
        resolved = self.mod._resolved_accessible_extents(
            {"x": 925, "y": 169, "width": 40, "height": 54},
            accessible_window_extents={"x": 195, "y": 137, "width": 818, "height": 642},
            window_geometry={"x": 390, "y": 274, "width": 818, "height": 642},
        )
        self.assertEqual(resolved, {"x": 1120, "y": 306, "width": 40, "height": 54})

    def test_pick_accessible_matches_prefers_rightmost(self) -> None:
        matches = [
            {"name": "Search", "visible": True, "resolved_extents": {"x": 100, "y": 50, "width": 10, "height": 10}, "path": [0]},
            {"name": "Search", "visible": True, "resolved_extents": {"x": 300, "y": 20, "width": 10, "height": 10}, "path": [1]},
        ]
        picked = self.mod._pick_accessible_matches(matches, pick="rightmost")
        self.assertEqual(picked[0]["resolved_extents"]["x"], 300)

    def test_pick_accessible_matches_best_prefers_editable_focusable_field(self) -> None:
        matches = [
            {
                "name": "Поиск",
                "visible": True,
                "states": ["enabled", "showing", "visible"],
                "interfaces": ["Accessible", "Component"],
                "resolved_extents": {"x": 436, "y": 194, "width": 576, "height": 70},
                "path": [1, 1, 0, 1, 0, 3],
            },
            {
                "name": "Поиск",
                "visible": True,
                "states": ["editable", "enabled", "focusable", "showing", "visible"],
                "interfaces": ["Accessible", "Component", "EditableText", "Text"],
                "resolved_extents": {"x": 460, "y": 210, "width": 492, "height": 44},
                "path": [1, 1, 0, 1, 0, 3, 0],
            },
        ]
        picked = self.mod._pick_accessible_matches(matches, pick="best")
        self.assertIn("EditableText", picked[0]["interfaces"])
        self.assertIn("focusable", picked[0]["states"])

    def test_pick_accessible_window_prefers_status_matched_title_across_multiple_apps(self) -> None:
        class _FakeWindow:
            def __init__(self, name: str) -> None:
                self._name = name

            def get_name(self):
                return self._name

            def get_extents(self, _coord_type):
                return types.SimpleNamespace(x=100, y=200, width=300, height=400)

            def get_role_name(self):
                return "filler"

        class _FakeApp:
            def __init__(self, name: str, windows: list[_FakeWindow]) -> None:
                self._name = name
                self._windows = windows

            def get_name(self):
                return self._name

            def get_child_count(self):
                return len(self._windows)

            def get_child_at_index(self, index: int):
                return self._windows[index]

        class _FakeDesktop:
            def __init__(self, apps: list[_FakeApp]) -> None:
                self._apps = apps

            def get_child_count(self):
                return len(self._apps)

            def get_child_at_index(self, index: int):
                return self._apps[index]

        portable_window = _FakeWindow("\u200e\u2068Telegram\u2069 – (265)")
        desktop = _FakeDesktop(
            [
                _FakeApp("TelegramDesktop", [_FakeWindow("Telegram (79)")]),
                _FakeApp("TelegramDesktop", [portable_window]),
            ]
        )
        Atspi = types.SimpleNamespace(
            CoordType=types.SimpleNamespace(SCREEN=object()),
            get_desktop=lambda _index: desktop,
        )
        status_payload = {
            "windows": [
                {
                    "title": "\u200e\u2068Telegram\u2069 – (265)",
                    "window_id": "0x05e0002e",
                    "x": 1012,
                    "y": 290,
                    "width": 1636,
                    "height": 1284,
                }
            ]
        }

        with mock.patch.object(self.mod, "_import_atspi", return_value=Atspi):
            with mock.patch.object(self.mod, "profile_status", return_value=status_payload):
                imported_atspi, chosen_window, chosen_status, extents = self.mod._pick_accessible_window(Path("/tmp/TelegramPortableAK"))

        self.assertIs(imported_atspi, Atspi)
        self.assertIs(chosen_window, portable_window)
        self.assertEqual(chosen_status, status_payload)
        self.assertEqual(extents, {"x": 100, "y": 200, "width": 300, "height": 400})

    def test_type_into_accessible_node_uses_direct_unicode_text_before_ascii_fallback(self) -> None:
        chosen = {
            "path": [1],
            "resolved_extents": {"x": 100, "y": 200, "width": 120, "height": 40},
        }
        resolved = {
            "chosen": chosen,
            "node": object(),
            "status": {
                "windows": [
                    {
                        "window_id": "0x77",
                        "x": 10,
                        "y": 20,
                        "width": 800,
                        "height": 600,
                    }
                ]
            },
        }

        with mock.patch.object(self.mod, "_find_accessible_match", return_value=resolved):
            with mock.patch.object(self.mod, "_accessible_click_point", return_value={"x": 160, "y": 220, "mode": "direct_extents"}):
                with mock.patch.object(self.mod, "_resolved_window", return_value=resolved["status"]["windows"][0]):
                    with mock.patch.object(self.mod, "_focus_accessible_node") as focus_mock:
                        with mock.patch.object(self.mod, "_set_accessible_text_value", return_value=True) as set_text_mock:
                            with mock.patch.object(self.mod, "list_accessible_nodes", return_value={"match_count": 1, "matches": [{"name": "Павел"}]}):
                                with mock.patch.object(self.mod, "click_accessible_node") as click_mock:
                                    with mock.patch.object(self.mod, "_send_x11_key_sequence") as send_keys_mock:
                                        payload = self.mod.type_into_accessible_node(
                                            Path("/tmp/TelegramPortableAK"),
                                            query="Имя",
                                            text="Павел",
                                            role="text",
                                            visible_only=True,
                                            index=0,
                                            clear_first=True,
                                            state_filters=["showing"],
                                        )

        self.assertEqual(payload["status"], "typed")
        self.assertEqual(payload["input_method"], "accessible_text")
        set_text_mock.assert_called_once()
        click_mock.assert_not_called()
        send_keys_mock.assert_not_called()
        focus_mock.assert_called_once()

    def test_type_into_accessible_node_falls_back_when_unicode_direct_write_is_not_visible(self) -> None:
        chosen = {
            "path": [1],
            "resolved_extents": {"x": 100, "y": 200, "width": 120, "height": 40},
        }
        resolved = {
            "chosen": chosen,
            "node": object(),
            "status": {
                "windows": [
                    {
                        "window_id": "0x77",
                        "x": 10,
                        "y": 20,
                        "width": 800,
                        "height": 600,
                    }
                ]
            },
        }

        with mock.patch.object(self.mod, "_find_accessible_match", return_value=resolved):
            with mock.patch.object(self.mod, "_accessible_click_point", return_value={"x": 160, "y": 220, "mode": "direct_extents"}):
                with mock.patch.object(self.mod, "_resolved_window", return_value=resolved["status"]["windows"][0]):
                    with mock.patch.object(self.mod, "_focus_accessible_node"):
                        with mock.patch.object(self.mod, "_set_accessible_text_value", return_value=True):
                            with mock.patch.object(self.mod, "list_accessible_nodes", return_value={"match_count": 0, "matches": []}):
                                with mock.patch.object(self.mod, "click_accessible_node", return_value={"status": "clicked"}) as click_mock:
                                    with mock.patch.object(self.mod, "_paste_x11_text", return_value=True) as paste_mock:
                                        payload = self.mod.type_into_accessible_node(
                                            Path("/tmp/TelegramPortableAK"),
                                            query="Имя",
                                            text="Павел",
                                            role="text",
                                            visible_only=True,
                                            index=0,
                                            clear_first=True,
                                            state_filters=["showing"],
                                        )

        self.assertEqual(payload["input_method"], "x11_clipboard")
        click_mock.assert_called_once()
        paste_mock.assert_called_once_with("0x77", "Павел", clear_first=True, press_enter=False)

    def test_type_into_accessible_node_uses_clipboard_fallback_for_non_ascii(self) -> None:
        chosen = {
            "path": [1],
            "resolved_extents": {"x": 100, "y": 200, "width": 120, "height": 40},
        }
        resolved = {
            "chosen": chosen,
            "node": object(),
            "status": {
                "windows": [
                    {
                        "window_id": "0x77",
                        "x": 10,
                        "y": 20,
                        "width": 800,
                        "height": 600,
                    }
                ]
            },
        }

        with mock.patch.object(self.mod, "_find_accessible_match", return_value=resolved):
            with mock.patch.object(self.mod, "_accessible_click_point", return_value={"x": 160, "y": 220, "mode": "direct_extents"}):
                with mock.patch.object(self.mod, "_resolved_window", return_value=resolved["status"]["windows"][0]):
                    with mock.patch.object(self.mod, "_focus_accessible_node"):
                        with mock.patch.object(self.mod, "_set_accessible_text_value", return_value=False):
                            with mock.patch.object(self.mod, "click_accessible_node", return_value={"status": "clicked"}) as click_mock:
                                with mock.patch.object(self.mod, "_paste_x11_text", return_value=True) as paste_mock:
                                    payload = self.mod.type_into_accessible_node(
                                        Path("/tmp/TelegramPortableAK"),
                                        query="Имя",
                                        text="Павел",
                                        role="text",
                                        visible_only=True,
                                        index=0,
                                        clear_first=True,
                                        state_filters=["showing"],
                                    )

        self.assertEqual(payload["status"], "typed")
        self.assertEqual(payload["input_method"], "x11_clipboard")
        click_mock.assert_called_once()
        paste_mock.assert_called_once_with("0x77", "Павел", clear_first=True, press_enter=False)

    def test_type_portable_text_uses_clipboard_fallback_for_non_ascii(self) -> None:
        with mock.patch.object(
            self.mod,
            "profile_status",
            return_value={"windows": [{"window_id": "0x77", "x": 10, "y": 20, "width": 800, "height": 600}]},
        ):
            with mock.patch.object(self.mod, "_paste_x11_text", return_value=True) as paste_mock:
                payload = self.mod.type_portable_text(Path("/tmp/TelegramPortableAK"), "Павел")

        self.assertEqual(payload["status"], "typed")
        self.assertEqual(payload["input_method"], "x11_clipboard")
        paste_mock.assert_called_once_with("0x77", "Павел", press_enter=False)

    def test_paste_x11_text_collapses_selection_after_clipboard_paste(self) -> None:
        with mock.patch.object(self.mod, "_read_x11_clipboard_text", return_value="before"):
            with mock.patch.object(self.mod, "_write_x11_clipboard_text", return_value=True) as write_mock:
                with mock.patch.object(self.mod, "_send_x11_key_sequence", return_value=True) as send_mock:
                    ok = self.mod._paste_x11_text("0x77", "Павел", clear_first=True, press_enter=False)

        self.assertTrue(ok)
        self.assertEqual(write_mock.call_args_list[0], mock.call("Павел"))
        self.assertEqual(write_mock.call_args_list[-1], mock.call("before"))
        send_mock.assert_called_once_with(
            "0x77",
            [["Control_L", "a"], ["BackSpace"], ["Control_L", "v"], ["End"]],
        )

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
