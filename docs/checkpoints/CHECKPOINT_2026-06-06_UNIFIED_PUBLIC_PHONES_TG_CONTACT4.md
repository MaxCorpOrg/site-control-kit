# CHECKPOINT 2026-06-06 UNIFIED PUBLIC PHONES TG_CONTACT4

## Git Context

- branch:
  - `main`
- remote:
  - `origin = git@github.com:MaxCorpOrg/site-control-kit.git`

## Git Status Before Commit

- В commit должны попасть:
  - code changes по unified `public_phones`
  - tests
  - repo docs / handoff docs
  - этот checkpoint
- Generated локальный файл вне commit:
  - `artifacts/telegram_exports/INDEX.md`

## Что закрыто

- Unified `public_phones` flow доведён до согласованного состояния:
  - `phones_found` = total unique phones
  - `private_phones_found` = private-only split
  - overlap rule = `public wins`
  - `*.private.txt` и `*.private.json` попадают в run history, `artifacts.json` и `artifacts/telegram_exports/INDEX.md`
- Обновлены:
  - `AGENTS.md`
  - `scripts/telegram_tdata_helper.py`
  - `scripts/export_telegram_members_non_pii.py`
  - `scripts/telegram_gui/models.py`
  - `scripts/telegram_gui/app.py`
  - `scripts/telegram_gui/backend.py`
  - `scripts/telegram_gui/services/artifact_index.py`
  - `scripts/telegram_gui/ui/window.py`
  - Telegram/UI regression tests

## Ключевые Live Run

- Quick Check:
  - source:
    - `/home/max/site-control-kit/TG_CONTACT/4/tdata-003/tdata`
  - chat:
    - `-1002465948544`
  - run:
    - `20260606T074214Z`
    - `phones_found=1`
    - `private_phones_found=1`
    - `public_count=0`

- Full History:
  - source:
    - `/home/max/site-control-kit/TG_CONTACT/4/tdata-003/tdata`
  - chat:
    - `НаДопинге 2.0 ЧАТ | Бодибилдинг | Фитнес | Спорт Фармакология`
    - `-1002465948544`
  - run:
    - `20260606T092821Z`
    - `status=done`
    - `history_messages_scanned=187923`
    - `phones_found=145`
    - `public_count=62`
    - `private_phones_found=83`

## Артефакты

- Quick Check:
  - `/tmp/site-control-live-private-phones-1_phones.md`
  - `/tmp/site-control-live-private-phones-1_phones.txt`
  - `/tmp/site-control-live-private-phones-1_phones.json`
  - `/tmp/site-control-live-private-phones-1_phones.private.txt`
  - `/tmp/site-control-live-private-phones-1_phones.private.json`
  - `/home/max/.site-control-kit/telegram_workspace/runs/20260606T074214Z/summary.json`
  - `/home/max/.site-control-kit/telegram_workspace/runs/20260606T074214Z/artifacts.json`
  - `/home/max/.site-control-kit/telegram_workspace/runs/20260606T074214Z/events.jsonl`

- Full History:
  - `/tmp/tg4_nadopinge_full_history_phones_20260606_phones.md`
  - `/tmp/tg4_nadopinge_full_history_phones_20260606_phones.txt`
  - `/tmp/tg4_nadopinge_full_history_phones_20260606_phones.json`
  - `/tmp/tg4_nadopinge_full_history_phones_20260606_phones.private.txt`
  - `/tmp/tg4_nadopinge_full_history_phones_20260606_phones.private.json`
  - `/tmp/tg4_direct_full_history_actions_20260606.log`
  - `/home/max/.site-control-kit/telegram_workspace/runs/20260606T092821Z/summary.json`
  - `/home/max/.site-control-kit/telegram_workspace/runs/20260606T092821Z/artifacts.json`
  - `/home/max/.site-control-kit/telegram_workspace/runs/20260606T092821Z/events.jsonl`

## Изменённые Файлы Для Commit

- `AGENTS.md`
- `README.md`
- `CHANGELOG.md`
- `NEXT_STEPS.md`
- `AGENT_START_HERE.md`
- `CODEX_STATE.md`
- `docs/ARCHITECTURE.md`
- `docs/PROJECT_STATUS_RU.md`
- `docs/agent_handoff_ru/08_KNOWN_ISSUES_AND_LIVE_FINDINGS.md`
- `docs/agent_handoff_ru/09_CURRENT_BACKLOG_AND_NEXT_STEPS.md`
- `docs/checkpoints/CHECKPOINT_2026-06-06_UNIFIED_PUBLIC_PHONES_TG_CONTACT4.md`
- `scripts/export_telegram_members_non_pii.py`
- `scripts/telegram_tdata_helper.py`
- `scripts/telegram_gui/app.py`
- `scripts/telegram_gui/backend.py`
- `scripts/telegram_gui/models.py`
- `scripts/telegram_gui/services/artifact_index.py`
- `scripts/telegram_gui/ui/window.py`
- `tests/test_telegram_export_runtime.py`
- `tests/test_telegram_gui_backend_features.py`
- `tests/test_telegram_gui_run_history.py`
- `tests/test_telegram_members_export_gui.py`
- `tests/test_telegram_tdata_helper.py`

## Проверки И Команды

- targeted tests:
  - `python3 -m unittest tests.test_telegram_tdata_helper tests.test_telegram_export_runtime tests.test_telegram_gui_backend_features tests.test_telegram_gui_run_history tests.test_telegram_members_export_gui`
  - `169 tests OK`, `2 skipped`
- full suite:
  - `python3 -m unittest discover -s tests -p 'test_*.py'`
  - `319 tests OK`, `2 skipped`
- runtime / syntax:
  - `python3 -m py_compile scripts/telegram_tdata_helper.py scripts/export_telegram_members_non_pii.py scripts/telegram_gui/models.py scripts/telegram_gui/app.py scripts/telegram_gui/backend.py scripts/telegram_gui/ui/window.py tests/test_telegram_tdata_helper.py tests/test_telegram_export_runtime.py tests/test_telegram_gui_backend_features.py tests/test_telegram_gui_run_history.py tests/test_telegram_members_export_gui.py`
  - `python3 -m webcontrol --help`
  - `python3 -m webcontrol browser --help`
- live run:
  - backend `Quick Check` run `20260606T074214Z`
  - direct helper/API `Full History` run `20260606T092821Z`
- после doc-sync:
  - `git diff --check`

## Что дальше

- Если нужен следующий live-pass без recovery-работ, продолжать на ready source `TG_CONTACT 4`:
  - либо анализировать текущие `145` номеров
  - либо брать следующий чат тем же helper/API path
- Если нужен именно AK2-run:
  - сначала вернуть portable helper-clone `AK2 live 959756539365` в `ready for export`

## Ограничения

- Этот checkpoint не делает `AK2 live 959756539365` автоматически ready; это отдельный runtime-вопрос.
- `artifacts/telegram_exports/INDEX.md` остаётся generated local artifact и не должен публиковаться автоматически.
