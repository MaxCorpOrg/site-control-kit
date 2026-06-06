# Архитектура

## Назначение
`site-control-kit` — локальная система управления браузером.
Она связывает CLI, хаб и браузерное расширение в один предсказуемый контур выполнения команд.

## Компоненты

### 1. `webcontrol` (Python)
Содержит:
- HTTP API сервер;
- хранилище состояния и очередь команд;
- CLI для оператора, скриптов и агентов.

Ключевые файлы:
- `webcontrol/server.py`
- `webcontrol/store.py`
- `webcontrol/cli.py`

### 2. Расширение браузера (`extension/`)
Содержит:
- `background.js` — heartbeat, polling, tab-level операции, screenshot;
- `content.js` — DOM-команды внутри страницы;
- `manifest.json`, `options.*`, `popup.*` — настройки и диагностика.

### 3. Windows-обёртки и скрипты
Содержит:
- `start-hub.cmd`, `start-hub.ps1`
- `browser.cmd`, `browser.ps1`
- `scripts/*.cmd`, `scripts/*.ps1`

Назначение:
- упростить запуск;
- убрать лишние ручные аргументы;
- дать агенту и пользователю короткий путь к живому браузеру.

### 4. Runtime-layer и launcher contracts
Содержит:
- `webcontrol/settings.py` — единое разрешение runtime root, token source и лог-путей;
- `scripts/start_hub.ps1` — Windows wrapper над `python -m webcontrol serve`;
- `scripts/telegram_username_collector_launcher.py` и `telegram-username-collector.cmd` — startup contract для Telegram GUI entrypoint.

Назначение:
- держать один источник правды по runtime mode (`project-local` vs `legacy-adopted`);
- не допускать silent quickstart fallback для токена;
- на Windows давать controlled fast-fail там, где production v1 сознательно Linux-only.

### 5. Telegram GTK operator contour
Содержит:
- `scripts/telegram_members_export_gui.py` — основной GTK entrypoint;
- `scripts/telegram_gui/ui/window.py` — операторское окно и orchestration;
- `scripts/telegram_gui/backend.py` — routing между GUI и helper/runtime слоями;
- `scripts/telegram_tdata_helper.py` — direct `Primary tdata` list/resolve/export path.

Назначение:
- держать текущий рабочий операторский путь в одном контуре:
  - `GTK GUI -> Primary tdata`;
- отделять `public_phones` от старого bridge/CDP/web fallback;
- сохранять progress, stop-path и отдельные sidecar-артефакты для длинных history-run.

### 6. Unified `public_phones` result contract
Содержит:
- один `operation_kind=public_phones` для всего phone-flow;
- `phones_found` как total unique phones;
- `private_phones_found` как private-only split;
- sidecars:
  - `*_phones.md`
  - `*_phones.txt`
  - `*_phones.json`
  - `*.private.txt`
  - `*.private.json` при наличии private-only номеров.

Назначение:
- держать одинаковую total/public/private семантику в helper, markdown/json, GUI, run history и `artifacts/telegram_exports/INDEX.md`;
- применять правило `public wins`, если один и тот же нормализованный номер найден и публично, и в `user.phone`.

## Схема Потока

```text
browser.cmd / sitectl browser
            |
            v
      webcontrol/cli.py
            |
            v
     HTTP API локального хаба
            |
            v
     очередь + state.json + маршрутизация
            |
            v
  browser extension background.js
            |
   +--------+--------+
   |                 |
   v                 v
tab-level API   content.js -> DOM страницы
```

## Поток Данных

### A. Регистрация Клиента
1. Расширение стартует.
2. Отправляет `POST /api/clients/heartbeat`.
3. Хаб обновляет клиента, его вкладки и метаданные.

### B. Жизненный Цикл Команды
1. Оператор или агент вызывает `browser.cmd ...` или `sitectl browser ...`.
2. CLI превращает это в payload команды.
3. Хаб принимает `POST /api/commands`.
4. Команда кладётся в очередь нужного клиента или клиентов.
5. Расширение делает `GET /api/commands/next?client_id=...`.
6. Получив команду, расширение исполняет её:
   - либо в `background.js`,
   - либо через `content.js` во вкладке.
7. Результат отправляется в `POST /api/commands/{id}/result`.
8. Хаб обновляет доставки, результат и агрегированный статус.

### C. Диагностика
- `GET /health` — жив ли хаб.
- `GET /api/clients` — какие клиенты подключены.
- `GET /api/state` — полное состояние.
- `GET /api/commands/{id}` — подробности конкретной команды.
- `python -m webcontrol runtime-env --format json --no-create` — эффективный runtime mode, token source и реальные пути до state/log/token.

## Роли Компонентов

### Хаб
Должен:
- быть единственным источником правды;
- хранить историю и очереди;
- не зависеть от того, жив ли service worker в данный момент.

### CLI
Должен:
- быть коротким и удобным;
- прятать низкоуровневый `send --type ...` за понятными командами;
- давать безопасные значения по умолчанию.

### Расширение
Должно:
- уметь периодически просыпаться и опрашивать хаб;
- корректно выбирать вкладку;
- возвращать единый формат результата и ошибок.

## Хранилище

Состояние хранится в одном JSON-файле `state.json`.

Основные разделы:
- `clients` — подключённые браузерные клиенты;
- `queues` — FIFO-очереди по клиентам;
- `commands` — карточки команд, доставки и результаты.

Требование:
- файл должен оставаться читаемым и пригодным для ручной диагностики.

## Runtime Resolution

Runtime теперь резолвится так:

1. `env`
2. `.env`
3. `.site-control-kit/local.yaml`
4. `config/default.yaml`

При этом:

- canonical default runtime root — `./var/site-control-kit`;
- для текущего Telegram operator flow long full-history export живёт на отдельном export-timeout path, а не на list-timeout;
- фактический live baseline на 2026-06-06:
  - ready direct `Primary tdata` source на этом хосте:
    - `/home/max/site-control-kit/TG_CONTACT/4/tdata-003/tdata`
  - unified `public_phones` full-history run `20260606T092821Z` уже подтвердил:
    - `history_messages_scanned=187923`
    - `phones_found=145`
    - `public_phones=62`
    - `private_phones_found=83`
  - `AK2 live 959756539365` остаётся valid operator target, но его portable helper-clone перед следующим export ещё требует readiness refresh;
- если на машине уже есть `%USERPROFILE%\.site-control-kit`, проект уходит в `legacy-adopted`, а repo-local `.site-control-kit/local.yaml` указывает на существующий runtime;
- generated local token живёт в `.site-control-kit/generated_token.txt`, если явный `SITECTL_TOKEN` не задан.

Для следующего агента это значит:

- не спорить с `runtime-env`, а брать пути и token source только оттуда;
- отсутствие repo-local `var/site-control-kit` на adopted-legacy машине не считать поломкой само по себе.

## Маршрутизация

Цель команды может задаваться так:
- `client_id` — один клиент;
- `client_ids` — список клиентов;
- `broadcast=true` — всем клиентам.

Без явного target:
- если онлайн-клиент ровно один, хаб может безопасно направить команду ему;
- если онлайн-клиентов несколько, команда должна быть отклонена как неоднозначная.

Выбор вкладки внутри клиента:
1. `target.tab_id`
2. `target.url_pattern`
3. активная вкладка
4. первая доступная вкладка

Для `sitectl browser` важно сохранять этот порядок предсказуемым.

## Типы Выполнения

### Background-команды
Выполняются на уровне вкладки или браузера:
- `navigate`
- `new_tab`
- `reload`
- `activate_tab`
- `close_tab`
- `screenshot`

### DOM-команды
Выполняются внутри страницы через `content.js`:
- `click`
- `context_click`
- `click_text`
- `clear_editable`
- `fill`
- `focus`
- `extract_text`
- `get_html`
- `get_page_url`
- `get_attribute`
- `wait_selector`
- `scroll`
- `scroll_by`
- `back`
- `forward`
- `press_key`
- `run_script`

## Устойчивость
- MV3 service worker не постоянный.
- Поэтому используются:
  - `setInterval`
  - `chrome.alarms`
- Очередь и история не живут в расширении, а сохраняются на стороне хаба.

## Ограничения
- `chrome://*` и похожие системные страницы не доступны для content script.
- Некоторые сайты запрещают `run_script` через CSP.
- На чувствительных сайтах часть действий нужно делать через DOM-команды вместо произвольного JS.
- `telegram-username-collector` в production v1 не является Windows GUI launcher: на Windows его контракт — быстрый понятный отказ без traceback и без GTK окна.

## Принципы Развития
- сохранять обратную совместимость по API, где это возможно;
- развивать `sitectl browser` как основной операторский интерфейс;
- добавлять короткие команды и хорошие defaults;
- синхронно обновлять документацию, примеры и smoke-проверки.
