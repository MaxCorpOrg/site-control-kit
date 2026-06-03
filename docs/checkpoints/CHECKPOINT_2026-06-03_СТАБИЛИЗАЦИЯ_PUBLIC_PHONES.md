# Контрольная Точка 2026-06-03: Стабилизация `public_phones`

## Где мы находимся

- Репозиторий: `/home/max/site-control-kit`
- Ветка: `main`
- Основной операторский путь: `GTK GUI -> Primary tdata`
- Текущий live профиль: `AK2 live 959756539365`
- Текущий live source: `/home/max/Документы/ак2/у/959756539365/tdata`

## Что зафиксировано этим checkpoint

- Закрыт реальный разрыв между docs/UI и helper-реализацией:
  - `public_phones` helper раньше фактически собирал только `user about`
  - теперь он реально собирает:
    - `chat about`
    - `pinned/history` message text
    - `public bio/about`
- Обновлён текст итогового phone-markdown, чтобы он соответствовал фактическому scope.
- README, handoff и agent docs синхронизированы под текущий `AK2 -> Primary tdata -> public_phones` baseline.

## Ключевые файлы изменений

- `scripts/telegram_tdata_helper.py`
- `scripts/export_telegram_members_non_pii.py`
- `tests/test_telegram_tdata_helper.py`
- `tests/test_telegram_export_runtime.py`
- `README.md`
- `AGENTS.md`
- `AGENT_START_HERE.md`
- `CODEX_STATE.md`
- `docs/PROJECT_STATUS_RU.md`
- `docs/agent_handoff_ru/07_TESTING_AND_ACCEPTANCE.md`
- `docs/agent_handoff_ru/08_KNOWN_ISSUES_AND_LIVE_FINDINGS.md`
- `docs/agent_handoff_ru/09_CURRENT_BACKLOG_AND_NEXT_STEPS.md`
- `NEXT_STEPS.md`
- `CHANGELOG.md`

## Что проверено

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m webcontrol --help
python3 -m webcontrol browser --help
python3 -m scripts.telegram_username_collector_launcher --doctor
```

Результат:
- `318 tests OK`, `2 skipped`
- оба CLI help зелёные
- `--doctor` зелёный
- GTK GUI видим на `DISPLAY=:0`

## Live доказательства

- Direct helper smoke через collector venv:
  - `/tmp/ak2_public_phones_smoke_20260603.json`
  - `/tmp/ak2_public_phones_smoke_20260603.log`
  - `/tmp/ak2_public_phones_smoke_20260603.session`
- Важные stats:
  - `history_messages_scanned=50`
  - `public_phones_kept=3`
  - `chat_about_scanned=1`
  - `pinned_messages_scanned=1`
  - `user_about_scanned=31`
- Ранее сохранённый partial/full-history batch:
  - `/home/max/Документы/ак2/живой_тест_номеров/ak2_cosmetology_public_phones_full_history_summary_20260602T110438Z.json`
  - `/home/max/.site-control-kit/telegram_workspace/logs/gui_ak2_cosmetology_full_history_phones_20260602T110438Z.log`

## Ограничения и важные правила

- `public_phones` V1 работает только для `Primary tdata`
- приватное `user.phone` не читается
- `default_user` не менять без отдельной причины
- direct helper-run надо делать через:
  - `/home/max/telegram-api-collector/.venv/bin/python`
- системный `python3` на этом host может дать:
  - `Missing opentele dependency. Run this helper via the collector venv.`

## Что осталось следующим шагом

1. Запустить GUI:

```bash
cd /home/max/site-control-kit
TELEGRAM_API_COLLECTOR_PYTHON=/home/max/telegram-api-collector/.venv/bin/python DISPLAY=:0 python3 scripts/telegram_members_export_gui.py
```

2. Выбрать `AK2 live 959756539365`
3. Подключить `Primary tdata`
4. Оставить `Full History`
5. Допройти `Форум Косметология | Дерматология` без ручной остановки
6. Затем прогнать `Косметологи Чат | Сообщество Профессионалов`
7. Сохранить новые `*_phones.md`, `*_phones.txt`, `*_phones.json`, `summary.json`, `artifacts.json`, `events.jsonl`

## Что не включать в commit

- `.site-control-kit/`
- `TG_CONTACT/`
- `dist/`
- `*.log`
- токены и временные session-файлы
- `artifacts/telegram_exports/INDEX.md`, если это только локальный generated live-след
