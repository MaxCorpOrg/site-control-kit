# CHECKPOINT 2026-06-03 AK2 30 UNIQUE PUBLIC PHONES

## Git Context

- branch:
  - `main`
- remote:
  - `origin = git@github.com:MaxCorpOrg/site-control-kit.git`

## Git Status Before Commit

- В индекс и commit должны попасть только docs/handoff/checkpoint обновления этого live-pass.
- Локальный generated файл вне commit:
  - `artifacts/telegram_exports/INDEX.md`

## Что закрыто

- Цель `30 unique public phones` закрыта на реальном live-run через текущий путь:
  - `GTK GUI -> Primary tdata -> Full History -> Сбор открытых номеров`
  - профиль: `AK2 live 959756539365`
  - `default_user` не менялся
  - старый workaround с большим `TELEGRAM_TDATA_LIST_TIMEOUT_SEC` не использовался

## Ключевой run

- Чат:
  - `Форум Косметология | Дерматология`
  - `@chatkosmetologa`
- Run:
  - `20260603T095301Z`
  - `status=done`
  - `phones_found=25`
  - `history_messages_scanned=7373`
  - `duration_sec=1049`
  - `surface_badge=Primary tdata`

## Итог по номерам

- Baseline до rerun:
  - `14` unique phones
- Новый rerun:
  - `23` новых unique phones
- Cumulative total:
  - `37` unique phones
- Goal file:
  - `30` номеров сохранены в aggregate progress files

## Артефакты

- Rerun output:
  - `/home/max/Документы/ак2/живой_тест_номеров/ak2_cosmetology_04_chatkosmetologa_rerun_20260603_phones.md`
  - `/home/max/Документы/ак2/живой_тест_номеров/ak2_cosmetology_04_chatkosmetologa_rerun_20260603_phones.txt`
  - `/home/max/Документы/ак2/живой_тест_номеров/ak2_cosmetology_04_chatkosmetologa_rerun_20260603_phones.json`
- Aggregate/session:
  - `/home/max/Документы/ак2/живой_тест_номеров/ak2_cosmetology_public_phones_30_unique_progress_20260603.txt`
  - `/home/max/Документы/ак2/живой_тест_номеров/ak2_cosmetology_public_phones_30_unique_progress_20260603.json`
  - `/home/max/Документы/ак2/живой_тест_номеров/ak2_cosmetology_public_phones_30_unique_progress_20260603.md`
  - `/home/max/Документы/ак2/живой_тест_номеров/ak2_cosmetology_public_phones_30_unique_session_20260603T095221Z.json`
  - `/home/max/Документы/ак2/живой_тест_номеров/ak2_cosmetology_public_phones_30_unique_session_20260603T095221Z.md`
  - `/home/max/Документы/ак2/живой_тест_номеров/ak2_cosmetology_public_phones_30_unique_runner_20260603T095221Z.log`
- Run metadata:
  - `/home/max/.site-control-kit/telegram_workspace/logs/gui_ak2_cosmetology_30_unique_20260603T095221Z.log`
  - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260603T095301Z.log`
  - `/home/max/.site-control-kit/telegram_workspace/runs/20260603T095301Z/summary.json`
  - `/home/max/.site-control-kit/telegram_workspace/runs/20260603T095301Z/artifacts.json`
  - `/home/max/.site-control-kit/telegram_workspace/runs/20260603T095301Z/events.jsonl`

## Изменённые Файлы Для Commit

- `README.md`
- `CHANGELOG.md`
- `AGENT_START_HERE.md`
- `CODEX_STATE.md`
- `NEXT_STEPS.md`
- `docs/ARCHITECTURE.md`
- `docs/PROJECT_STATUS_RU.md`
- `docs/agent_handoff_ru/08_KNOWN_ISSUES_AND_LIVE_FINDINGS.md`
- `docs/agent_handoff_ru/09_CURRENT_BACKLOG_AND_NEXT_STEPS.md`
- `docs/checkpoints/CHECKPOINT_2026-06-03_AK2_30_UNIQUE_PUBLIC_PHONES.md`

## Проверки И Команды

- baseline verify уже был зелёным до этого checkpoint:
  - `python3 -m unittest discover -s tests -p 'test_*.py'` -> `318 tests OK`, `2 skipped`
  - `python3 -m webcontrol --help` -> OK
  - `python3 -m webcontrol browser --help` -> OK
  - `python3 -m scripts.telegram_username_collector_launcher --doctor` -> OK
- live run:
  - `TELEGRAM_API_COLLECTOR_PYTHON=/home/max/telegram-api-collector/.venv/bin/python DISPLAY=:0 python3 /tmp/ak2_cosmetology_public_phones_30_runner.py`
- после doc-sync:
  - `git diff --check`

## Что дальше

- Если нужен следующий live-pass, он уже не про достижение `30`, а про дополнительное покрытие target-ов:
  - `@kosmetologi_chat_ru`
  - `@cosmetologna`
  - `@cosmochatrussia`
- Старый `TELEGRAM_TDATA_LIST_TIMEOUT_SEC` workaround больше не считать обязательным для `export-public-phones`.

## Ограничения

- Этот checkpoint фиксирует только уже собранные открытые номера из доступной истории и публичных источников.
- Приватное `user.phone` не читается.
- Дополнительные чаты после `@chatkosmetologa` в этом pass не запускались, потому что цель `30` была достигнута раньше.
