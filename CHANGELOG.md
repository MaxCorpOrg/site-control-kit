# Changelog

## 2026-06-03

### AK2 Live Goal: `30` Unique Public Phones Closed

- Через текущий операторский путь `GTK GUI -> Primary tdata -> Full History -> Сбор открытых номеров` закрыта live-цель `30` уникальных открытых номеров.
- Использовался профиль `AK2 live 959756539365`; `default_user` не менялся.
- Хватило одного полного rerun 4-го чата:
  - `@chatkosmetologa`
  - run `20260603T095301Z`
  - `status=done`
  - `phones_found=25`
  - `history_messages_scanned=7373`
  - `surface_badge=Primary tdata`
- Cumulative результат по baseline `1-4` + новому rerun:
  - `37` unique public phones
  - aggregate-файлы сохранены в `/home/max/Документы/ак2/живой_тест_номеров/`
- Этот run одновременно подтвердил, что для GUI `export-public-phones` больше не нужен старый workaround с завышенным `TELEGRAM_TDATA_LIST_TIMEOUT_SEC`.

### Стабилизация `public_phones` И Подготовка К Следующему AK2 Тесту

- Закрыт функциональный разрыв между docs/UI и helper-реализацией:
  - `scripts/telegram_tdata_helper.py` теперь реально собирает открытые номера из `chat about`, `pinned/history` message text и `public bio/about`;
  - раньше helper фактически брал только `user about`, хотя UI и handoff уже обещали больше.
- В `scripts/export_telegram_members_non_pii.py` исправлен текст итогового markdown, чтобы он соответствовал фактическим источникам V1.
- Расширены тесты:
  - `tests/test_telegram_tdata_helper.py`
  - `tests/test_telegram_export_runtime.py`
- Проверки этого прохода:
  - `python3 -m unittest discover -s tests -p 'test_*.py'` -> `318 tests OK`, `2 skipped`
  - `python3 -m webcontrol --help` -> OK
  - `python3 -m webcontrol browser --help` -> OK
  - `python3 -m scripts.telegram_username_collector_launcher --doctor` -> OK
  - GTK GUI видим на `DISPLAY=:0`
  - direct live smoke через collector venv:
    - `/tmp/ak2_public_phones_smoke_20260603.json`
    - `/tmp/ak2_public_phones_smoke_20260603.log`
    - `history_messages_scanned=50`
    - `public_phones_kept=3`
    - `chat_about_scanned=1`
    - `pinned_messages_scanned=1`
    - `user_about_scanned=31`
- Handoff/docs синхронизированы под текущий `AK2 -> Primary tdata -> public_phones` baseline.

## 2026-05-11

### Windows Core Smoke And End-Of-Day Checkpoint

- Подтверждён narrow Windows smoke для `telegram-username-collector` и core/browser wrappers на `C:\site-control-kit-win-smoke`.
- `scripts\start_hub.cmd` снова поднимает hub на Windows без traceback.
- `python -m webcontrol runtime-env --format json --no-create` показывает `legacy-adopted` runtime, `token_file` source и реальные runtime paths.
- `browser.cmd status` и `browser.cmd tabs` подтверждены на live client `client-win-edge-manual-20260510`.
- `telegram-username-collector` на Windows подтверждён как controlled fast-fail launcher, а не как GUI runtime entrypoint.
- После rebase на актуальный `main` внесён минимальный cross-platform fix:
  - `scripts/telegram_product_runtime.py` больше не падает без определяемого home directory;
  - `tests/test_telegram_product_runtime.py` больше не требует POSIX execute bit на Windows-host.
- End-of-day docs синхронизированы:
  - `README.md`
  - `docs/ARCHITECTURE.md`
  - `NEXT_STEPS.md`
  - `AGENTS.md`
  - handoff/state docs

### Проверки

- `git diff --check`
- `python -m unittest discover -s tests -p "test_*.py"`
- `python -m webcontrol --help`
- `python -m webcontrol browser --help`
- `python -m webcontrol runtime-env --format json --no-create`
- `.\browser.cmd status`
- `.\browser.cmd tabs`
- `.\telegram-username-collector.cmd`

Финальный итог verify после rebase: `303 tests OK`.

Во время финального end-of-day verify browser client один раз успел стать stale/offline; recovery снова остался runtime-only:

- перезапуск Edge debug profile с `--disable-extensions-except=<repo>\extension`
- и `--load-extension=<repo>\extension`

После этого `browser.cmd status` и `browser.cmd tabs` снова стали зелёными.

### Риски

- adopted Edge debug profile может повторно потерять active unpacked-extension load state;
- fresh project-local runtime path по-прежнему не подтверждён на машине с existing `%USERPROFILE%\.site-control-kit`.

## 2026-05-10

### Windows Core Smoke + Release Confidence

- Починен Windows PowerShell hub launcher path.
- Усилен runtime/config слой и диагностика `runtime-env`.
- Добавлены Windows-safe launcher paths и no-GTK fast-fail contract для Telegram GUI entrypoints.
- Подтверждён live browser client после Windows smoke на adopted runtime.
