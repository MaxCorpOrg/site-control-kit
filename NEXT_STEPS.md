# Next Steps

Дата: 2026-06-03

## Текущий baseline

- Ветка: `main`
- Основной операторский путь: `GTK GUI -> Primary tdata`
- Текущий живой профиль: `AK2 live 959756539365`
- Текущий live source: `/home/max/Документы/ак2/у/959756539365/tdata`
- `default_user` не менять без отдельной причины

## Что уже подтверждено

- `public_phones` V1 теперь реально собирает:
  - `chat about`
  - `pinned/history` message text
  - `public bio/about`
- Полный suite зелёный:
  - `python3 -m unittest discover -s tests -p 'test_*.py'` -> `318 tests OK`, `2 skipped`
- Базовые runtime-check команды зелёные:
  - `python3 -m webcontrol --help`
  - `python3 -m webcontrol browser --help`
  - `python3 -m scripts.telegram_username_collector_launcher --doctor`
- GTK GUI видим на `DISPLAY=:0`
- Узкий live smoke helper-а на AK2 уже сохранён:
  - `/tmp/ak2_public_phones_smoke_20260603.json`
  - `/tmp/ak2_public_phones_smoke_20260603.log`
- Частичный полный batch от 2026-06-02 уже есть:
  - `/home/max/Документы/ак2/живой_тест_номеров/ak2_cosmetology_public_phones_full_history_summary_20260602T110438Z.json`
  - `/home/max/.site-control-kit/telegram_workspace/logs/gui_ak2_cosmetology_full_history_phones_20260602T110438Z.log`
- Live goal `30 unique public phones` уже закрыт:
  - rerun `@chatkosmetologa` `20260603T095301Z` -> `status=done`, `phones_found=25`, `history_messages_scanned=7373`
  - cumulative total -> `37` unique open phones
  - aggregate:
    - `/home/max/Документы/ак2/живой_тест_номеров/ak2_cosmetology_public_phones_30_unique_progress_20260603.json`
    - `/home/max/Документы/ак2/живой_тест_номеров/ak2_cosmetology_public_phones_30_unique_session_20260603T095221Z.json`

## Что осталось

- Если нужен следующий live-pass, идти уже не за целью `30`, а за дополнительным покрытием target-ов:
  - `Косметологи Чат | Сообщество Профессионалов` -> `@kosmetologi_chat_ru`
  - `@cosmetologna`
  - `@cosmochatrussia`
- При необходимости отдельным новым batch-сводом сохранить прирост сверх текущих `37` уникальных номеров.
- Не расширять `public_phones` на bridge/CDP/web fallback без отдельной задачи.

## Следующий узкий контур

```bash
cd /home/max/site-control-kit
TELEGRAM_API_COLLECTOR_PYTHON=/home/max/telegram-api-collector/.venv/bin/python DISPLAY=:0 python3 scripts/telegram_members_export_gui.py
```

В GUI:
1. Выбрать `AK2 live 959756539365`
2. Подключить `Primary tdata`
3. Оставить `Full History`
4. Начинать уже с `@kosmetologi_chat_ru`
5. Затем при необходимости идти в `@cosmetologna`
6. Затем в `@cosmochatrussia`
7. Сохранить `*_phones.md`, `*_phones.txt`, `*_phones.json`, `summary.json`, `artifacts.json`, `events.jsonl`

## Что не перепутать

- Для прямого helper-run использовать collector venv:
  - `/home/max/telegram-api-collector/.venv/bin/python`
- Голый системный `python3` может дать:
  - `Missing opentele dependency. Run this helper via the collector venv.`
- Live confirm уже показал, что для GUI `export-public-phones` больше не нужен завышенный `TELEGRAM_TDATA_LIST_TIMEOUT_SEC`.
- Не коммитить:
  - `.site-control-kit/`
  - `TG_CONTACT/`
  - `dist/`
  - `*.log`
  - токены, ключи, временные сессии
  - generated `artifacts/telegram_exports/INDEX.md`, если это только локальный live-след
