# История изменений

## 2026-07-24

### Стабилизация браузерной платформы

- создана чистая ветка от `main`; старые накопленные коммиты не переносились;
- добавлены аренда и подтверждение команд, безопасные повторы,
  идемпотентность и `dead_letter` — изолятор неопределённых команд;
- состояние перенесено в SQLite с WAL — журналом предзаписи, миграцией и
  резервным копированием;
- добавлены сессии агентов, TTL — срок жизни — и блокировки вкладок;
- добавлены семантические локаторы, строгий поиск, восстановление `ref`,
  iframe, вложенные iframe и открытый Shadow DOM;
- расширение сохраняет неподтверждённые результаты в локальной очереди;
- добавлены диагностические пакеты, сокрытие секретов и ограничения CDP;
- добавлены обязательные проверки GitHub Actions и настоящий Chrome E2E;
- пользовательская, агентная и архитектурная документация сведена к русским
  источникам правды.

Доказательства и точные метрики находятся в
[`docs/reports/BROWSER_CORE_ACCEPTANCE_2026-07-24_RU.md`](docs/reports/BROWSER_CORE_ACCEPTANCE_2026-07-24_RU.md).

## 2026-07-12

### Стабилизация пакета и безопасная диагностика

- Исправлен installed-mode wrapper:
  - `/usr/bin/telegram-username-collector` и `/usr/bin/sitectl` теперь делают `cd "$APP_ROOT"` перед запуском Python;
  - установленная программа больше не зависит от текущей папки запуска.
- `telegram-username-collector --doctor` в installed-mode теперь использует `SITECTL_PRODUCT_APP_ROOT` как product root.
- `webcontrol runtime-env --format json` теперь по умолчанию редактирует `SITECTL_TOKEN`; реальный JSON secret-output доступен только через `--show-secrets`.
- GUI action-log стал полезнее для smoke/поддержки:
  - `app_started` при старте;
  - `profiles_refreshed accounts=... ready=...` при загрузке/обновлении профилей.
- Launcher теперь обрабатывает Ctrl+C без traceback и возвращает код `130`.
- Финальный `.deb` пересобран:
  - `/home/max/site-control-kit/dist/linux-deb/telegram-username-collector_0.1.0_amd64.deb`
  - sha256: `121572953110c23d69354e7438dde86d2b5ffa507fc5833a178cd248e6bb6aa5`
- Install-kit обновлён:
  - `/home/max/Рабочий стол/telegram-username-collector-install-kit/`
- Проверки:
  - `python3 -m unittest discover -s tests -p 'test_*.py'` -> `330 tests OK`, `2 skipped`
  - `./scripts/verify.sh` -> OK
  - `python3 -m webcontrol --help` -> OK
  - `python3 -m webcontrol browser --help` -> OK
  - package content check via `dpkg-deb -x` -> OK
  - build-root installed-mode `--doctor` -> OK with expected `hub_reachable=0`
  - live GUI smoke -> `/home/max/Рабочий стол/telegram-program-live-smoke-20260712T065625Z-final`
- После выдачи sudo-доступа выполнен реальный local reinstall:
  - `sudo apt install -y --reinstall ./telegram-username-collector_0.1.0_amd64.deb`
  - `/opt` payload содержит текущие фиксы;
  - `cd /tmp && telegram-username-collector --doctor` -> OK with expected `hub_reachable=0`;
  - установленная GUI-команда открылась в `Installed .deb mode`;
  - action log: `/home/max/.local/share/site-control-kit/telegram_workspace/logs/gui_actions_20260712T081230Z.log`.

## 2026-07-11

### Готовый настольный пакет, тема Shadow Admin и масштаб GTK

- Подготовлен готовый Linux desktop contour для `Telegram Username Collector`:
  - GTK-панель остаётся основным операторским интерфейсом;
  - собран `.deb`-установщик;
  - добавлено масштабирование интерфейса.
- UI scaling:
  - launcher принимает `--ui-scale FACTOR`;
  - поддерживается env `TELEGRAM_GUI_SCALE`;
  - в самой GTK-панели добавлен выбор масштаба `90%`, `100%`, `115%`, `125%`, `150%`;
  - CSS и стартовый размер окна теперь считаются от выбранного scale.
- UX polish:
  - дизайн приведён к `/home/max/Shadow_Admin/Shadow_Admin_Design_Guide_v1.0.pdf`;
  - добавлен Shadow Admin logo asset:
    - `resources/branding/shadow-admin-logo-mark.png`
  - кнопки получили явную отдачу при hover/press;
  - верх панели теперь показывает понятный `Следующий шаг`;
  - status badges переведены на русский;
  - основные кнопки переименованы под операторский flow;
  - product summary сокращён, длинные пути компактируются.
- Пакет:
  - `/home/max/site-control-kit/dist/linux-deb/telegram-username-collector_0.1.0_amd64.deb`
  - размер: около `52M`
  - финальный sha256 фиксируется в checkpoint/handoff-файлах после сборки
  - содержит `/usr/bin/telegram-username-collector`, desktop entry, bundled app under `/opt/telegram-username-collector`, extension zip and venv.
- Проверки:
  - `python3 -m py_compile` по изменённым launcher/GUI/test файлам -> OK
  - targeted GUI tests -> `53 tests OK`, `2 skipped`
  - full suite -> `324 tests OK`, `2 skipped`
  - `python3 -m webcontrol --help` -> OK
  - `python3 -m webcontrol browser --help` -> OK
  - `git diff --check` -> OK
  - `dpkg-deb --info` / `dpkg-deb --contents` -> OK
  - repo GUI smoke on `DISPLAY=:0` -> window appeared, hover/press feedback checked on `Обновить профили`, safe click completed
  - extracted `.deb` smoke -> `--help` and `--doctor` OK
  - hover screenshot -> `/tmp/shadow_admin_gui_final2_hover_refresh_20260711.png`
  - press screenshot -> `/tmp/shadow_admin_gui_final2_press_refresh_20260711.png`
- Ограничение:
  - реальный `sudo apt install` не выполнялся; установочный артефакт проверен через `dpkg-deb` и запуск из распакованного installed-mode дерева.

## 2026-06-06

### Графический контур закреплён на готовом `TG_CONTACT 4`

- Зафиксирован именно текущий рабочий contour внутри программы и GTK GUI:
  - stale registry row `TG_CONTACT N` теперь может автоматически перейти на repo-local `REPO_ROOT/TG_CONTACT/N`, если там есть рабочий `tdata-*`
  - initial account selection в GUI теперь предпочитает самый актуальный ready `TG_CONTACT` direct `Primary tdata` contour
  - для такого аккаунта portable card теперь честно показывает direct helper/API path без требования portable profile
- В текущем live окружении это закрепило:
  - `TG_CONTACT 4`
  - `/home/max/site-control-kit/TG_CONTACT/4`
  - `Primary tdata`
  - `tdata_ready=True`
- Проверки:
  - targeted GUI/backend tests -> `83 tests OK`, `2 skipped`
  - full suite -> `322 tests OK`, `2 skipped`

### Единый поток `public_phones` и полная проверка истории TG_CONTACT 4

- Завершён unified pass для `public_phones` без введения нового operation kind:
  - `phones_found` теперь трактуется как total unique phones;
  - `private_phones_found` сохраняет private-only split;
  - если один и тот же номер найден и публично, и в `user.phone`, действует правило `public wins`.
- Обновлены helper/export/GUI/history/index слои:
  - `scripts/telegram_tdata_helper.py`
  - `scripts/export_telegram_members_non_pii.py`
  - `scripts/telegram_gui/models.py`
  - `scripts/telegram_gui/backend.py`
  - `scripts/telegram_gui/services/artifact_index.py`
  - `scripts/telegram_gui/ui/window.py`
- Теперь `public_phones` сохраняет не только `*_phones.md/txt/json`, но и `*.private.txt/json`, а `artifacts/telegram_exports/INDEX.md` индексирует их в том же run.
- Расширены regression tests:
  - `tests/test_telegram_tdata_helper.py`
  - `tests/test_telegram_export_runtime.py`
  - `tests/test_telegram_gui_backend_features.py`
  - `tests/test_telegram_gui_run_history.py`
  - `tests/test_telegram_members_export_gui.py`
- Проверки:
  - targeted tests -> `169 tests OK`, `2 skipped`
  - full suite -> `319 tests OK`, `2 skipped`
  - `python3 -m py_compile` по затронутым Telegram-файлам -> OK
  - `python3 -m webcontrol --help` -> OK
  - `python3 -m webcontrol browser --help` -> OK
- Live verify на ready direct source `/home/max/site-control-kit/TG_CONTACT/4/tdata-003/tdata`:
  - `Quick Check` run `20260606T074214Z` -> `phones_found=1`, `private_phones_found=1`
  - `Full History` run `20260606T092821Z` по чату `-1002465948544` -> `status=done`, `history_messages_scanned=187923`, `phones_found=145`, `public_count=62`, `private_phones_found=83`
  - артефакты full-history:
    - `/tmp/tg4_nadopinge_full_history_phones_20260606_phones.md`
    - `/tmp/tg4_nadopinge_full_history_phones_20260606_phones.txt`
    - `/tmp/tg4_nadopinge_full_history_phones_20260606_phones.json`
    - `/tmp/tg4_nadopinge_full_history_phones_20260606_phones.private.txt`
    - `/tmp/tg4_nadopinge_full_history_phones_20260606_phones.private.json`
    - `/home/max/.site-control-kit/telegram_workspace/runs/20260606T092821Z/{summary.json,artifacts.json,events.jsonl}`

## 2026-06-03

### Достигнута цель AK2: 30 уникальных открытых телефонов

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

### Проверка ядра Windows и итоговая контрольная точка

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

### Проверка ядра Windows и готовность к выпуску

- Починен Windows PowerShell hub launcher path.
- Усилен runtime/config слой и диагностика `runtime-env`.
- Добавлены Windows-safe launcher paths и no-GTK fast-fail contract для Telegram GUI entrypoints.
- Подтверждён live browser client после Windows smoke на adopted runtime.
