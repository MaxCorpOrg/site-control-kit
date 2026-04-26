from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


def _load_chain_module():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "scripts" / "telegram_contact_chain.py"
    spec = importlib.util.spec_from_file_location("telegram_contact_chain", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TelegramContactChainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = _load_chain_module()

    def test_chat_slug_from_group_url_uses_fragment(self) -> None:
        slug = self.mod.chat_slug_from_group_url("https://web.telegram.org/k/#-2465948544")
        self.assertEqual(slug, "-2465948544")

    def test_latest_run_json_picks_newest_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            chat_dir = Path(tmpdir) / "chat"
            (chat_dir / "runs" / "20260419T100000Z").mkdir(parents=True)
            (chat_dir / "runs" / "20260419T100000Z" / "run.json").write_text("{}", encoding="utf-8")
            (chat_dir / "runs" / "20260419T110000Z").mkdir(parents=True)
            expected = chat_dir / "runs" / "20260419T110000Z" / "run.json"
            expected.write_text("{}", encoding="utf-8")

            actual = self.mod.latest_run_json(chat_dir)

        self.assertEqual(actual, expected)

    def test_should_stop_after_idle_uses_threshold(self) -> None:
        self.assertFalse(self.mod.should_stop_after_idle(1, 2))
        self.assertTrue(self.mod.should_stop_after_idle(2, 2))
        self.assertFalse(self.mod.should_stop_after_idle(5, 0))

    def test_should_stop_after_no_growth_uses_threshold(self) -> None:
        self.assertFalse(self.mod.should_stop_after_no_growth(1, 2))
        self.assertTrue(self.mod.should_stop_after_no_growth(2, 2))
        self.assertFalse(self.mod.should_stop_after_no_growth(5, 0))

    def test_reached_chain_target_requires_positive_threshold(self) -> None:
        self.assertTrue(self.mod.reached_chain_target(22, 20))
        self.assertFalse(self.mod.reached_chain_target(19, 20))
        self.assertFalse(self.mod.reached_chain_target(50, 0))

    def test_discovery_new_visible_reads_nested_chat_stats(self) -> None:
        self.assertEqual(
            self.mod.discovery_new_visible(
                {
                    "chat_stats": {
                        "discovery_new_visible": 7,
                    }
                }
            ),
            7,
        )
        self.assertEqual(
            self.mod.discovery_new_visible(
                {
                    "chat_discovery_new_visible": 5,
                    "chat_stats": {
                        "discovery_new_visible": 2,
                    },
                }
            ),
            5,
        )
        self.assertEqual(self.mod.discovery_new_visible({}), 0)

    def test_is_productive_discovery_run_requires_new_visible_peers(self) -> None:
        self.assertTrue(self.mod.is_productive_discovery_run({"chat_discovery_new_visible": 3}))
        self.assertFalse(self.mod.is_productive_discovery_run({"chat_discovery_new_visible": 0}))
        self.assertFalse(self.mod.is_productive_discovery_run({}))

    def test_is_productive_deep_yield_requires_stop_flag_and_updates(self) -> None:
        self.assertTrue(
            self.mod.is_productive_deep_yield(
                {
                    "chat_deep_yield_stop": 1,
                    "deep_updated_total": 2,
                }
            )
        )
        self.assertFalse(
            self.mod.is_productive_deep_yield(
                {
                    "chat_deep_yield_stop": 1,
                    "deep_updated_total": 0,
                }
            )
        )
        self.assertFalse(
            self.mod.is_productive_deep_yield(
                {
                    "chat_deep_yield_stop": 0,
                    "deep_updated_total": 3,
                }
            )
        )
        self.assertFalse(self.mod.is_productive_deep_yield({}))

    def test_should_skip_interval_after_run_respects_chain_flag(self) -> None:
        payload = {
            "chat_deep_yield_stop": 1,
            "deep_updated_total": 3,
        }
        self.assertTrue(self.mod.should_skip_interval_after_run(payload, True))
        self.assertFalse(self.mod.should_skip_interval_after_run(payload, False))
        self.assertFalse(
            self.mod.should_skip_interval_after_run(
                {
                    "chat_deep_yield_stop": 1,
                    "deep_updated_total": 0,
                },
                True,
            )
        )

    def test_resolve_interval_sec_uses_profile_default_and_env_override(self) -> None:
        self.assertEqual(self.mod.resolve_interval_sec(None, "fast"), 8.0)
        with mock.patch.dict("os.environ", {"TELEGRAM_CHAIN_INTERVAL_SEC": "11.5"}, clear=False):
            self.assertEqual(self.mod.resolve_interval_sec(None, "fast"), 11.5)
        self.assertEqual(self.mod.resolve_interval_sec(6.0, "deep"), 6.0)

    def test_build_collect_env_applies_profile_defaults_without_overwrite(self) -> None:
        with mock.patch.dict("os.environ", {"CHAT_MAX_RUNTIME": "999"}, clear=False):
            env = self.mod.build_collect_env("deep")

        self.assertEqual(env["TELEGRAM_CHAIN_PROFILE"], "deep")
        self.assertEqual(env["CHAT_MAX_RUNTIME"], "999")
        self.assertEqual(env["CHAT_DEEP_LIMIT"], "60")
        self.assertEqual(env["TELEGRAM_CHAT_DISCOVERY_SCROLL_BURST"], "3")

    def test_collect_env_snapshot_keeps_effective_overrides(self) -> None:
        env = {
            "TELEGRAM_CHAIN_PROFILE": "fast",
            "CHAT_PROFILE": "fast",
            "CHAT_MAX_RUNTIME": "90",
            "CHAT_SCROLL_STEPS": "4",
            "CHAT_DEEP_LIMIT": "8",
            "CHAT_CLIENT_ID": "client-1",
            "UNRELATED": "drop-me",
        }

        snapshot = self.mod.collect_env_snapshot(env)

        self.assertEqual(
            snapshot,
            {
                "TELEGRAM_CHAIN_PROFILE": "fast",
                "CHAT_PROFILE": "fast",
                "CHAT_SCROLL_STEPS": "4",
                "CHAT_DEEP_LIMIT": "8",
                "CHAT_MAX_RUNTIME": "90",
                "CHAT_CLIENT_ID": "client-1",
            },
        )

    def test_main_skips_sleep_after_productive_yield_run(self) -> None:
        group_url = "https://web.telegram.org/k/#-2465948544"
        payloads = [
            {
                "status": "completed",
                "new_usernames": 1,
                "unique_members": 10,
                "safe_count": 2,
                "members_with_username": 3,
                "chat_deep_yield_stop": 1,
                "deep_updated_total": 2,
            },
            {
                "status": "completed",
                "new_usernames": 0,
                "unique_members": 10,
                "safe_count": 2,
                "members_with_username": 3,
                "chat_deep_yield_stop": 0,
                "deep_updated_total": 0,
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = Path(tmpdir) / "out"
            chat_dir = self.mod.chat_dir_for(group_url, output_root)
            run_index = {"value": 0}

            def fake_run(*_args, **_kwargs):
                run_index["value"] += 1
                self.assertEqual(_kwargs["env"]["TELEGRAM_CHAIN_PROFILE"], "fast")
                self.assertEqual(_kwargs["env"]["CHAT_MAX_RUNTIME"], "120")
                run_dir = chat_dir / "runs" / f"20260420T12000{run_index['value']}Z"
                run_dir.mkdir(parents=True, exist_ok=True)
                (run_dir / "run.json").write_text(
                    json.dumps(payloads[run_index["value"] - 1], ensure_ascii=False),
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(["bash"], 0)

            argv = [
                "telegram_contact_chain.py",
                group_url,
                str(output_root),
                "--runs",
                "2",
                "--profile",
                "fast",
            ]

            with (
                mock.patch.object(self.mod.subprocess, "run", side_effect=fake_run),
                mock.patch.object(self.mod.time, "sleep") as sleep_mock,
                mock.patch.object(sys, "argv", argv),
            ):
                exit_code = self.mod.main()

            self.assertEqual(exit_code, 0)
            sleep_mock.assert_not_called()

            chain_json = sorted((chat_dir / "chains").glob("*/chain.json"))[-1]
            payload = json.loads(chain_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["profile"], "fast")
            self.assertEqual(payload["interval_sec"], 8.0)
            self.assertEqual(payload["productive_yield_runs"], 1)
            self.assertTrue(payload["attempts"][0]["productive_yield"])
            self.assertFalse(payload["attempts"][1]["productive_yield"])

    def test_main_sleeps_when_productive_skip_disabled(self) -> None:
        group_url = "https://web.telegram.org/k/#-2465948544"
        payload = {
            "status": "completed",
            "new_usernames": 1,
            "unique_members": 10,
            "safe_count": 2,
            "members_with_username": 3,
            "chat_deep_yield_stop": 1,
            "deep_updated_total": 2,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = Path(tmpdir) / "out"
            chat_dir = self.mod.chat_dir_for(group_url, output_root)
            run_index = {"value": 0}

            def fake_run(*_args, **_kwargs):
                run_index["value"] += 1
                self.assertEqual(_kwargs["env"]["TELEGRAM_CHAIN_PROFILE"], "deep")
                self.assertEqual(_kwargs["env"]["CHAT_DEEP_LIMIT"], "60")
                run_dir = chat_dir / "runs" / f"20260420T13000{run_index['value']}Z"
                run_dir.mkdir(parents=True, exist_ok=True)
                (run_dir / "run.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                return subprocess.CompletedProcess(["bash"], 0)

            argv = [
                "telegram_contact_chain.py",
                group_url,
                str(output_root),
                "--runs",
                "2",
                "--profile",
                "deep",
                "--interval-sec",
                "7",
                "--no-skip-interval-on-productive-yield",
            ]

            with (
                mock.patch.object(self.mod.subprocess, "run", side_effect=fake_run),
                mock.patch.object(self.mod.time, "sleep") as sleep_mock,
                mock.patch.object(sys, "argv", argv),
            ):
                exit_code = self.mod.main()

            self.assertEqual(exit_code, 0)
            sleep_mock.assert_called_once_with(7.0)

    def test_main_discovery_progress_prevents_idle_stop_without_new_batch_rows(self) -> None:
        group_url = "https://web.telegram.org/k/#-2465948544"
        payloads = [
            {
                "status": "completed",
                "new_usernames": 0,
                "unique_members": 10,
                "safe_count": 3,
                "members_with_username": 6,
                "chat_stats": {
                    "discovery_new_visible": 10,
                },
            },
            {
                "status": "completed",
                "new_usernames": 0,
                "unique_members": 12,
                "safe_count": 3,
                "members_with_username": 7,
                "chat_stats": {
                    "discovery_new_visible": 4,
                },
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = Path(tmpdir) / "out"
            chat_dir = self.mod.chat_dir_for(group_url, output_root)
            run_index = {"value": 0}

            def fake_run(*_args, **_kwargs):
                run_index["value"] += 1
                run_dir = chat_dir / "runs" / f"20260420T14000{run_index['value']}Z"
                run_dir.mkdir(parents=True, exist_ok=True)
                (run_dir / "run.json").write_text(
                    json.dumps(payloads[run_index["value"] - 1], ensure_ascii=False),
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(["bash"], 0)

            argv = [
                "telegram_contact_chain.py",
                group_url,
                str(output_root),
                "--runs",
                "2",
                "--stop-after-idle",
                "1",
            ]

            with (
                mock.patch.object(self.mod.subprocess, "run", side_effect=fake_run),
                mock.patch.object(self.mod.time, "sleep"),
                mock.patch.object(sys, "argv", argv),
            ):
                exit_code = self.mod.main()

            self.assertEqual(exit_code, 0)
            self.assertEqual(run_index["value"], 2)

            chain_json = sorted((chat_dir / "chains").glob("*/chain.json"))[-1]
            payload = json.loads(chain_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "completed")
            self.assertEqual(payload["discovery_progress_runs"], 2)
            self.assertEqual(payload["best_members_with_username"], 7)
            self.assertEqual(payload["attempts"][0]["idle_runs"], 0)
            self.assertTrue(payload["attempts"][0]["discovery_progress"])
            self.assertTrue(payload["attempts"][0]["productive_run"])

    def test_main_stops_after_target_members_with_username(self) -> None:
        group_url = "https://web.telegram.org/k/#-2465948544"
        payload = {
            "status": "completed",
            "new_usernames": 0,
            "unique_members": 40,
            "safe_count": 20,
            "members_with_username": 100,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = Path(tmpdir) / "out"
            chat_dir = self.mod.chat_dir_for(group_url, output_root)

            def fake_run(*_args, **_kwargs):
                run_dir = chat_dir / "runs" / "20260420T150001Z"
                run_dir.mkdir(parents=True, exist_ok=True)
                (run_dir / "run.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                return subprocess.CompletedProcess(["bash"], 0)

            argv = [
                "telegram_contact_chain.py",
                group_url,
                str(output_root),
                "--runs",
                "3",
                "--target-members-with-username",
                "100",
            ]

            with (
                mock.patch.object(self.mod.subprocess, "run", side_effect=fake_run),
                mock.patch.object(sys, "argv", argv),
            ):
                exit_code = self.mod.main()

            self.assertEqual(exit_code, 0)

            chain_json = sorted((chat_dir / "chains").glob("*/chain.json"))[-1]
            chain_payload = json.loads(chain_json.read_text(encoding="utf-8"))
            self.assertEqual(chain_payload["status"], "target_members_with_username_reached")
            self.assertEqual(chain_payload["target_members_with_username"], 100)


if __name__ == "__main__":
    unittest.main()
