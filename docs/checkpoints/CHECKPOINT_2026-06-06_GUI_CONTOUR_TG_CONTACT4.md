# CHECKPOINT 2026-06-06 GUI CONTOUR TG_CONTACT4

## Git Context

- branch:
  - `main`
- remote:
  - `origin = git@github.com:MaxCorpOrg/site-control-kit.git`

## Git Status Before Commit

- В commit должны попасть:
  - code changes по GUI/program contour
  - docs / handoff sync
  - этот checkpoint
- Generated локальный файл вне commit:
  - `artifacts/telegram_exports/INDEX.md`

## Что закрыто

- Рабочий contour теперь закреплён не только helper/API run-ами, но и в самой программе:
  - stale registry row `TG_CONTACT N` больше не держит GUI на broken portable-path, если repo-local `REPO_ROOT/TG_CONTACT/N` уже содержит рабочий `tdata-*`
  - initial account choice в GTK теперь предпочитает ready direct `Primary tdata` contour
  - portable card для такого аккаунта показывает direct helper/API path и не требует portable profile

## Ключевой Runtime Baseline

- Ready direct source:
  - `/home/max/site-control-kit/TG_CONTACT/4/tdata-003/tdata`
- Current GUI preferred account:
  - `TG_CONTACT 4`
- Current GUI preferred source:
  - `/home/max/site-control-kit/TG_CONTACT/4`
- Current preflight result:
  - `surface_badge=Primary tdata`
  - `tdata_ready=True`
  - note starts with `tdata доступен и будет использован как основной surface.`

## Связанные Live Run

- Quick Check:
  - run `20260606T074214Z`
  - `phones_found=1`
  - `private_phones_found=1`
- Full History:
  - run `20260606T092821Z`
  - `status=done`
  - `history_messages_scanned=187923`
  - `phones_found=145`
  - `public_count=62`
  - `private_phones_found=83`

## Изменённые Файлы Для Commit

- `README.md`
- `CHANGELOG.md`
- `NEXT_STEPS.md`
- `AGENT_START_HERE.md`
- `CODEX_STATE.md`
- `docs/ARCHITECTURE.md`
- `docs/PROJECT_STATUS_RU.md`
- `docs/agent_handoff_ru/08_KNOWN_ISSUES_AND_LIVE_FINDINGS.md`
- `docs/agent_handoff_ru/09_CURRENT_BACKLOG_AND_NEXT_STEPS.md`
- `docs/checkpoints/CHECKPOINT_2026-06-06_GUI_CONTOUR_TG_CONTACT4.md`
- `scripts/telegram_gui/backend.py`
- `scripts/telegram_gui/ui/window.py`
- `tests/test_telegram_gui_backend_features.py`
- `tests/test_telegram_members_export_gui.py`

## Проверки И Команды

- targeted tests:
  - `python3 -m unittest tests.test_telegram_gui_backend_features tests.test_telegram_members_export_gui`
  - `83 tests OK`, `2 skipped`
- full suite:
  - `python3 -m unittest discover -s tests -p 'test_*.py'`
  - `322 tests OK`, `2 skipped`
- syntax:
  - `python3 -m py_compile scripts/telegram_gui/backend.py scripts/telegram_gui/ui/window.py tests/test_telegram_gui_backend_features.py tests/test_telegram_members_export_gui.py`
- live probe:
  - `backend.load_accounts()` now resolves `TG_CONTACT 4` to `/home/max/site-control-kit/TG_CONTACT/4`
  - GUI preferred account logic picks `TG_CONTACT 4`
  - `build_preflight()` returns `Primary tdata`, `tdata_ready=True`
- after doc sync:
  - `git diff --check`

## Что дальше

- Если нужен следующий живой run без recovery-работ:
  - оставаться на `TG_CONTACT 4`
  - брать следующий чат через direct helper/API или через GUI
- Если нужен именно AK2 contour:
  - это отдельный runtime-цикл; сначала вернуть portable helper-clone профиля в `ready for export`

## Ограничения

- Этот checkpoint не меняет `default_user` в registry автоматически.
- `artifacts/telegram_exports/INDEX.md` остаётся generated local artifact и не должен публиковаться автоматически.
