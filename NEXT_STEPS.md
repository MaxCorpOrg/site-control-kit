# Next Steps

Дата: 2026-07-12

## Текущий baseline

- Ветка: `main`
- Готовый desktop package:
  - `/home/max/site-control-kit/dist/linux-deb/telegram-username-collector_0.1.0_amd64.deb`
  - sha256: `121572953110c23d69354e7438dde86d2b5ffa507fc5833a178cd248e6bb6aa5`
- Готовая папка для переноса на другой ПК:
  - `/home/max/Рабочий стол/telegram-username-collector-install-kit/`
  - внутри `.deb`, `.sha256`, `INSTALL_RU.md`
- Основной запуск после установки:
  - `telegram-username-collector`
- Installed-mode wrapper исправлен:
  - `/usr/bin/telegram-username-collector` и `/usr/bin/sitectl` делают `cd "$APP_ROOT"` перед `python -m ...`
- JSON diagnostics безопаснее:
  - `python3 -m webcontrol runtime-env --format json` редактирует `SITECTL_TOKEN` по умолчанию
  - для реального JSON-секрета нужен явный `--show-secrets`
- GUI action-log теперь появляется даже без экспорта:
  - `app_started`
  - `profiles_refreshed accounts=... ready=...`
- Визуальный baseline:
  - Shadow Admin тёмная pixel/mono тема из `/home/max/Shadow_Admin/Shadow_Admin_Design_Guide_v1.0.pdf`
  - логотип `resources/branding/shadow-admin-logo-mark.png`
  - заметный hover/press feedback у кнопок
  - плашка `Следующий шаг`
  - русские status badges
  - основные кнопки: `1. Подключить Telegram`, `Найти чат`, `Выбрать файл отчёта`, `Начать сбор @username`, `Собрать номера`
- Масштабирование:
  - в GUI: поле `Масштаб интерфейса`
  - из CLI: `telegram-username-collector --ui-scale 1.25`
  - из env: `TELEGRAM_GUI_SCALE=1.25`
- Основной операторский путь: `GTK GUI -> Primary tdata`
- Ready direct helper source на этом хосте:
  - `/home/max/site-control-kit/TG_CONTACT/4/tdata-003/tdata`
- `default_user` не менять без отдельной причины
- `AK2 live 959756539365` не потерян, но его portable helper-clone перед следующим export ещё требует readiness refresh

## Что уже подтверждено

- `.deb` собран и проверен через `dpkg-deb --info` / `dpkg-deb --contents` / `dpkg-deb -x`
- Package content содержит текущие fixes:
  - `cd "$APP_ROOT"`
  - `SITECTL_TOKEN_REDACTED`
  - `app_started`
  - `profiles_refreshed`
- Repo GUI smoke на `DISPLAY=:0` с `--ui-scale 1.15` поднимает окно `Telegram Username Collector`
- Extracted `.deb` smoke:
  - `--help` работает
  - `--doctor` работает
  - `hub_reachable=0` был ожидаемым warning, потому что хаб в smoke не запускался
- Build-root installed-mode `--doctor`:
  - `gtk_runtime=ok`
  - `extension_zip_ready=1`
  - `project_root=.../opt/telegram-username-collector/app`
- Live panel smoke:
  - final folder: `/home/max/Рабочий стол/telegram-program-live-smoke-20260712T065625Z-final`
  - hover screenshot: `/home/max/Рабочий стол/telegram-program-live-smoke-20260712T065625Z-final/screenshot-hover-refresh.png`
  - safe click `Обновить профили` прошёл без падения панели
  - action log: `/home/max/.local/share/site-control-kit/telegram_workspace/logs/gui_actions_20260712T065533Z.log`
  - action log содержит `app_started` и `profiles_refreshed`
- Ctrl+C smoke:
  - код `130`
  - без traceback
- Реальная локальная переустановка уже выполнена:
  - `sudo apt install -y --reinstall ./telegram-username-collector_0.1.0_amd64.deb`
  - `/opt/telegram-username-collector/app` проверен и содержит текущие фиксы
  - `cd /tmp && telegram-username-collector --doctor` -> `project_root=/opt/telegram-username-collector/app`, `gtk_runtime=ok`, `extension_zip_ready=1`
  - `telegram-username-collector --ui-scale 1.15` открыл GUI в `Installed .deb mode`
  - installed action log: `/home/max/.local/share/site-control-kit/telegram_workspace/logs/gui_actions_20260712T081230Z.log`
- Unified `public_phones` flow теперь согласован в helper, GUI, history и `INDEX.md`:
  - `phones_found` = total unique phones
  - `private_phones_found` = private-only split
  - overlap rule = `public wins`
- Полный suite зелёный:
  - `python3 -m unittest discover -s tests -p 'test_*.py'` -> `330 tests OK`, `2 skipped`
- Общий verify:
  - `./scripts/verify.sh` -> OK
- Базовые runtime-check команды зелёные:
  - `python3 -m webcontrol --help`
  - `python3 -m webcontrol browser --help`
- `python3 -m py_compile` по затронутым Telegram-файлам -> OK
- GTK GUI видим на `DISPLAY=:0`
- Live `Quick Check` на ready source уже сохранён:
  - run `20260606T074214Z`
  - `phones_found=1`
  - `private_phones_found=1`
  - `/tmp/site-control-live-private-phones-1_phones.{md,txt,json,private.txt,private.json}`
- Full-history run на том же source уже завершён:
  - чат `НаДопинге 2.0 ЧАТ | Бодибилдинг | Фитнес | Спорт Фармакология`
  - run `20260606T092821Z`
  - `status=done`
  - `history_messages_scanned=187923`
  - `phones_found=145`
  - `public_count=62`
  - `private_phones_found=83`
  - `/tmp/tg4_nadopinge_full_history_phones_20260606_phones.{md,txt,json,private.txt,private.json}`
  - `/home/max/.site-control-kit/telegram_workspace/runs/20260606T092821Z/{summary.json,artifacts.json,events.jsonl}`
- GUI contour теперь закреплён на этом же source:
  - stale registry rows `TG_CONTACT N` могут автоматически резолвиться в repo-local `/home/max/site-control-kit/TG_CONTACT/N`
  - initial GTK selection теперь предпочитает самый актуальный ready `TG_CONTACT` direct `Primary tdata`
  - в текущем окружении это даёт selected account `TG_CONTACT 4`

## Что осталось

- Optional packaging check перед внешней передачей на другой ПК:
  - повторить установку из `/home/max/Рабочий стол/telegram-username-collector-install-kit/` на чистой/тестовой Ubuntu-среде
  - запустить `cd /tmp && telegram-username-collector --doctor`
  - открыть GUI из desktop launcher / меню приложений
- Если нужен следующий live-pass без recovery-работ, идти уже через ready source `TG_CONTACT 4`:
  - либо анализировать текущие `145` номеров,
  - либо брать следующий чат тем же direct helper/API path
- Если нужен именно AK2-run:
  - сначала вернуть helper-clone профиля `AK2 live 959756539365` в `ready for export`
- Не расширять `public_phones` на bridge/CDP/web fallback без отдельной задачи

## Следующий узкий контур

```bash
cd /home/max/site-control-kit
/home/max/telegram-api-collector/.venv/bin/python scripts/telegram_tdata_helper.py export-public-phones \
  --tdata "/home/max/site-control-kit/TG_CONTACT/4/tdata-003/tdata" \
  --session /tmp/tg4_public_phones_smoke.session \
  --chat-ref -1002465948544 \
  --history-limit 50 \
  --progress-every 25
```

Если нужен GUI-path:
1. Запустить `scripts/telegram_members_export_gui.py`
2. Выбрать ready `Primary tdata` source
3. Оставить `Full History` или `Quick Check`
4. Сохранить `*_phones.md`, `*_phones.txt`, `*_phones.json`, `*.private.*`, `summary.json`, `artifacts.json`, `events.jsonl`

## Что не перепутать

- Для прямого helper-run использовать collector venv:
  - `/home/max/telegram-api-collector/.venv/bin/python`
- Голый системный `python3` может дать:
  - `Missing opentele dependency. Run this helper via the collector venv.`
- Generated `artifacts/telegram_exports/INDEX.md` не тащить в commit, если это только локальный live-след
- Не коммитить:
  - `.site-control-kit/`
  - `TG_CONTACT/`
  - `dist/`
  - `*.log`
  - токены, ключи, временные сессии
