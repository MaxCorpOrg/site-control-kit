from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.telegram_gui.models import ArtifactBundle, RunRecord, SessionResumeState
from scripts.telegram_gui.services.run_history import RunHistoryService


class RunHistoryServiceTests(unittest.TestCase):
    def test_append_and_list_recent_runs(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = RunHistoryService(Path(td))
            record = RunRecord(
                run_id="run-1",
                created_at="2026-05-04T10:00:00Z",
                surface_key="tdata",
                surface_label="Telegram Desktop tdata",
                surface_badge="Primary tdata",
                preset_key="full_history",
                preset_label="Full History",
                account_key="auto:slot-1",
                account_label="Слот 1",
                chat_ref="-1001",
                chat_title="BigpharmaMarket",
                output_path=Path("/tmp/export.md"),
                interrupted=False,
                safe_count=20,
                usernames_found=24,
                history_messages_scanned=4000,
                artifacts=ArtifactBundle(
                    markdown=Path("/tmp/export.md"),
                    usernames_txt=Path("/tmp/export_usernames.txt"),
                    usernames_json=Path("/tmp/export_usernames.json"),
                    safe_txt=Path("/tmp/safe.txt"),
                    safe_md=Path("/tmp/safe.md"),
                    run_log=Path("/tmp/export.log"),
                    action_log=Path("/tmp/actions.log"),
                    summary_json=Path("/tmp/summary.json"),
                    artifacts_json=Path("/tmp/artifacts.json"),
                    events_jsonl=Path("/tmp/events.jsonl"),
                ),
            )
            service.append_run(record)
            recent = service.list_recent()

        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0].surface_badge, "Primary tdata")
        self.assertEqual(recent[0].artifacts.usernames_json, Path("/tmp/export_usernames.json"))
        self.assertEqual(recent[0].artifacts.summary_json, Path("/tmp/summary.json"))

    def test_list_recent_reads_old_records_without_new_fields(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = RunHistoryService(Path(td))
            service.ensure()
            service.index_path.write_text(
                '{"run_id":"run-1","created_at":"2026-05-04T10:00:00Z","surface_key":"tdata","surface_label":"Telegram Desktop tdata","surface_badge":"Primary tdata","preset_key":"full_history","preset_label":"Full History","account_key":"auto:1","account_label":"Slot 1","chat_ref":"-1001","chat_title":"BigpharmaMarket","output_path":"/tmp/export.md","interrupted":true,"safe_count":7,"usernames_found":9,"history_messages_scanned":120,"artifacts":{"markdown":"/tmp/export.md","usernames_txt":"/tmp/export_usernames.txt"}}\n',
                encoding="utf-8",
            )
            recent = service.list_recent()

        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0].status, "partial")
        self.assertEqual(recent[0].summary().status, "partial")

    def test_save_and_load_last_session(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = RunHistoryService(Path(td))
            session = SessionResumeState(
                account_key="registry:alice",
                account_label="alice",
                chat_ref="-1001461811598",
                chat_title="BigpharmaMarket",
                output_path=Path("/tmp/export.md"),
                surface_key="tdata",
                surface_label="Telegram Desktop tdata",
                surface_badge="Primary tdata",
                preset_key="resume_last",
                preset_label="Resume Last",
                created_at="2026-05-04T10:10:00Z",
            )
            service.save_last_session(session)
            loaded = service.load_last_session()

        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.chat_ref, "-1001461811598")
        self.assertEqual(loaded.preset_key, "resume_last")
        self.assertEqual(loaded.operation_kind, "usernames")

    def test_save_and_load_last_session_public_phones(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = RunHistoryService(Path(td))
            session = SessionResumeState(
                account_key="registry:alice",
                account_label="alice",
                chat_ref="-1001461811598",
                chat_title="BigpharmaMarket",
                output_path=Path("/tmp/export_phones.md"),
                surface_key="tdata",
                surface_label="Telegram Desktop tdata",
                surface_badge="Primary tdata",
                preset_key="resume_last",
                preset_label="Resume Last",
                created_at="2026-05-04T10:10:00Z",
                operation_kind="public_phones",
            )
            service.save_last_session(session)
            loaded = service.load_last_session()

        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.operation_kind, "public_phones")
        self.assertEqual(loaded.output_path, Path("/tmp/export_phones.md"))

    def test_save_and_load_pinned_chats(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = RunHistoryService(Path(td))
            rows = [{"account_key": "auto:1", "chat_ref": "-1001", "chat_title": "BigpharmaMarket"}]
            service.save_pinned_chats(rows)
            loaded = service.load_pinned_chats()

        self.assertEqual(loaded, rows)

    def test_write_run_summary_and_artifacts_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = RunHistoryService(Path(td))
            record = RunRecord(
                run_id="run-1",
                created_at="2026-05-04T10:00:00Z",
                surface_key="tdata",
                surface_label="Telegram Desktop tdata",
                surface_badge="Primary tdata",
                preset_key="full_history",
                preset_label="Full History",
                account_key="auto:slot-1",
                account_label="Слот 1",
                chat_ref="-1001",
                chat_title="BigpharmaMarket",
                output_path=Path("/tmp/export.md"),
                interrupted=False,
                safe_count=20,
                usernames_found=24,
                history_messages_scanned=4000,
                artifacts=ArtifactBundle(
                    markdown=Path("/tmp/export.md"),
                    usernames_txt=Path("/tmp/export_usernames.txt"),
                    run_log=Path("/tmp/export.log"),
                    summary_json=Path("/tmp/summary.json"),
                    artifacts_json=Path("/tmp/artifacts.json"),
                    events_jsonl=Path("/tmp/events.jsonl"),
                ),
            )

            summary_path = service.write_run_summary(record)
            artifacts_path = service.write_run_artifacts(record)
            summary_text = summary_path.read_text(encoding="utf-8")
            artifacts_text = artifacts_path.read_text(encoding="utf-8")

        self.assertEqual(summary_path.name, "summary.json")
        self.assertEqual(artifacts_path.name, "artifacts.json")
        self.assertIn("BigpharmaMarket", summary_text)
        self.assertIn("events_jsonl", artifacts_text)

    def test_list_recent_roundtrips_public_phone_record(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = RunHistoryService(Path(td))
            record = RunRecord(
                run_id="run-phones-1",
                created_at="2026-05-04T10:00:00Z",
                surface_key="tdata",
                surface_label="Telegram Desktop tdata",
                surface_badge="Primary tdata",
                preset_key="quick_check",
                preset_label="Quick Check",
                account_key="auto:slot-1",
                account_label="Слот 1",
                chat_ref="-1001",
                chat_title="Cosmetology Chat",
                output_path=Path("/tmp/export_phones.md"),
                interrupted=False,
                safe_count=0,
                usernames_found=0,
                history_messages_scanned=120,
                artifacts=ArtifactBundle(
                    markdown=Path("/tmp/export_phones.md"),
                    usernames_txt=None,
                    phones_txt=Path("/tmp/export_phones.txt"),
                    phones_json=Path("/tmp/export_phones.json"),
                    summary_json=Path("/tmp/summary.json"),
                    artifacts_json=Path("/tmp/artifacts.json"),
                    events_jsonl=Path("/tmp/events.jsonl"),
                ),
                operation_kind="public_phones",
                phones_found=4,
                status="done",
            )
            service.append_run(record)
            recent = service.list_recent()

        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0].operation_kind, "public_phones")
        self.assertEqual(recent[0].phones_found, 4)
        self.assertEqual(recent[0].artifacts.phones_txt, Path("/tmp/export_phones.txt"))
