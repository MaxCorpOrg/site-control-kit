# Site Control Kit

Локальный набор инструментов для управления сайтами через браузерное расширение и локальный хаб-команд.

## Что внутри
- Локальный HTTP-хаб управления (`webcontrol`) с очередью команд и сохранением состояния.
- CLI (`sitectl` / `python3 -m webcontrol`) для отправки команд и диагностики.
- Расширение браузера (Manifest V3) для выполнения команд в реальных вкладках.
- Подробная документация для пользователя и ИИ-агентов сопровождения.

## Текущий Статус Проекта

Актуальная рабочая точка на 2026-06-03:
- основной Telegram-операторский путь: `GTK GUI -> Primary tdata`;
- в GUI есть два основных действия:
  - `Собрать @username`
  - `Сбор открытых номеров`;
- `public_phones` V1 теперь реально собирает открытые номера из:
  - `chat about`
  - `pinned/history` message text
  - `public bio/about`
  - не из приватного `user.phone`.

Что уже подтверждено:
- полный `unittest` suite: `318 tests OK`, `2 skipped`;
- `python3 -m webcontrol --help` -> OK;
- `python3 -m webcontrol browser --help` -> OK;
- `python3 -m scripts.telegram_username_collector_launcher --doctor` -> OK;
- GTK GUI видим на `DISPLAY=:0`;
- узкий live smoke `export-public-phones` на AK2 через collector venv:
  - `history_messages_scanned=50`
  - `public_phones_kept=3`
  - `chat_about_scanned=1`
  - `pinned_messages_scanned=1`
  - `user_about_scanned=31`
  - артефакты: `/tmp/ak2_public_phones_smoke_20260603.{json,log,session}`.

Что осталось:
- допройти через GUI `Full History` по незавершённым cosmetology-чатам:
  - `Форум Косметология | Дерматология`
  - `Косметологи Чат | Сообщество Профессионалов`;
- отдельно подтвердить тот же проход без ручной остановки и без старого runtime workaround;
- `public_phones` V1 по-прежнему доступен только для `Primary tdata`.

Подробный checkpoint: [docs/checkpoints/CHECKPOINT_2026-06-03_СТАБИЛИЗАЦИЯ_PUBLIC_PHONES.md](docs/checkpoints/CHECKPOINT_2026-06-03_СТАБИЛИЗАЦИЯ_PUBLIC_PHONES.md).

## Быстрый Вход В Браузерный Контур

Кратчайший поддерживаемый сценарий: [BROWSER_QUICKSTART.md](BROWSER_QUICKSTART.md)

Из корня репозитория на Windows:

```cmd
start-hub.cmd
browser.cmd status
browser.cmd tabs
browser.cmd open https://example.com
```

## Быстрый Вход В Telegram GUI

Текущий операторский запуск:

```bash
cd /home/max/site-control-kit
TELEGRAM_API_COLLECTOR_PYTHON=/home/max/telegram-api-collector/.venv/bin/python DISPLAY=:0 python3 scripts/telegram_members_export_gui.py
```

Что важно:
- не менять `default_user` без явной причины;
- для live `tdata` helper-path использовать collector venv, а не голый системный `python3`;
- текущий живой профиль для оператора: `AK2 live 959756539365`;
- текущий источник `tdata`: `/home/max/Документы/ак2/у/959756539365/tdata`.

Прямой helper smoke для `public_phones`:

```bash
cd /home/max/site-control-kit
/home/max/telegram-api-collector/.venv/bin/python scripts/telegram_tdata_helper.py export-public-phones \
  --tdata "/home/max/Документы/ак2/у/959756539365/tdata" \
  --session /tmp/ak2_public_phones_smoke.session \
  --chat-ref @cosmetologi_chat \
  --history-limit 50 \
  --progress-every 25
```

## Для Агентов И Автоматизации

Если репозиторий открыт в рабочей папке агента, считайте `site-control-kit` основным локальным инструментом управления браузером.

Что читать агенту:
- [AGENT_START_HERE.md](AGENT_START_HERE.md) — repo-root handoff: где мы остановились и откуда продолжать.
- [CODEX_STATE.md](CODEX_STATE.md) — последний зафиксированный state/handoff по текущей ветке работ.
- [NEXT_STEPS.md](NEXT_STEPS.md) — короткий список ближайших безопасных шагов.
- [CHANGELOG.md](CHANGELOG.md) — high-level журнал зафиксированных изменений.
- [AUTOPILOT.yaml](AUTOPILOT.yaml) — repo-local автопилот: как действовать без лишних подтверждений и чем проверять результат.
- [BROWSER_QUICKSTART.md](BROWSER_QUICKSTART.md) — короткий вход и рабочие команды.
- [AGENTS.md](AGENTS.md) — правила и политика использования инструмента в репозитории.
- [docs/AI_MAINTAINER_GUIDE.md](docs/AI_MAINTAINER_GUIDE.md) — как использовать, изменять и улучшать инструмент.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — поток команд и роли компонентов.
- [docs/API.md](docs/API.md) — контракт команд и результатов.

Практическое правило:
1. Запустить хаб.
2. Проверить `browser.cmd status`.
3. Проверить `browser.cmd tabs`.
4. Только потом выполнять реальную задачу в браузере.

## Важные Точки Входа

- [AGENT_START_HERE.md](AGENT_START_HERE.md) — короткая repo-root точка продолжения.
- [CODEX_STATE.md](CODEX_STATE.md) — последний handoff по факту.
- [docs/PROJECT_STATUS_RU.md](docs/PROJECT_STATUS_RU.md) — сводка текущего состояния на русском.
- `scripts/telegram_members_export_gui.py` — основной GTK GUI операторский вход.
- `scripts/telegram_tdata_helper.py` — прямой `tdata` helper для `list/resolve/export`.
- `scripts/export_telegram_members_non_pii.py` — sidecar/markdown export contract.
- [NEXT_STEPS.md](NEXT_STEPS.md) — что делать следующим узким шагом.

## Основные сценарии
- Открывать нужные URL во вкладках.
- Кликать по элементам, заполнять поля, ждать появления селекторов.
- Извлекать текст/HTML, делать скриншоты вкладок.
- Управлять несколькими клиентами (браузерами) через `client_id`.

## Архитектура

```text
CLI (sitectl) <----HTTP----> Локальный хаб (Python) <----HTTP poll----> Расширение браузера
                                                                      |
                                                                      +--> Content Script -> DOM-действия
```

Хаб — единый источник правды: клиенты, очередь команд, результаты выполнения.

## Runtime И Конфиги

С этого пакета стабилизации у проекта есть единый runtime-layer:

- runtime root по умолчанию: `./var/site-control-kit`;
- precedence настроек: `env` -> `.env` -> `.site-control-kit/local.yaml` -> `config/default.yaml`;
- пример переменных: [.env.example](.env.example);
- базовый конфиг: [config/default.yaml](config/default.yaml);
- shell/PowerShell wrappers больше не держат hardcoded quickstart token.

Что происходит при первом запуске:

- если legacy runtime `~/.site-control-kit` не найден, проект создаёт локальные каталоги внутри `./var/site-control-kit`;
- если legacy runtime уже существует, проект не переносит его автоматически, а создаёт pointer-файл `.site-control-kit/local.yaml` внутри репозитория;
- если токен хаба не задан через `SITECTL_TOKEN` или `.env`, локальный runtime генерирует `.site-control-kit/generated_token.txt`.

Проверить итоговое разрешение путей можно так:

```bash
python3 -m webcontrol runtime-env --format json
```

## Где лежат данные, логи и отчёты

- базовый runtime: `./var/site-control-kit`;
- legacy adoption, если найден `~/.site-control-kit`: `.site-control-kit/local.yaml`;
- локально сгенерированный токен по умолчанию: `.site-control-kit/generated_token.txt`;
- состояние хаба: `state/state.json`;
- текстовый лог хаба: `logs/hub.log`;
- machine-readable runtime logs:
  - `logs/runtime_events.jsonl`
  - `logs/runtime_errors.jsonl`
- browser/core отчёты: `reports/`;
- Telegram workspace:
  - `telegram_workspace/registry/users.json`
  - `telegram_workspace/registry/api_accounts.json`
  - `telegram_workspace/registry/secrets/`
  - `telegram_workspace/accounts/<N>/`
  - `telegram_workspace/logs/`
  - `telegram_workspace/runs/<run_id>/summary.json`
  - `telegram_workspace/runs/<run_id>/events.jsonl`
  - `telegram_workspace/runs/<run_id>/artifacts.json`
- Telegram export reports по умолчанию: `reports/telegram_exports`

## Быстрый старт

### Windows

1. Откройте PowerShell в корне проекта.
2. Установите зависимости и пакет:

```powershell
py -3.11 -m pip install -r requirements.txt
py -3.11 -m pip install -e .
```

3. При необходимости создайте `.env` на основе `.env.example`.
4. Запустите хаб:

```cmd
scripts\start_hub.cmd
```

5. В Chrome/Edge откройте `chrome://extensions` или `edge://extensions`.
6. Включите `Developer mode`.
7. Нажмите `Load unpacked`.
8. Выберите папку `<repo-root>\extension`.
9. Откройте `Options` расширения и задайте:
   - `Server URL`: `http://127.0.0.1:8765`
   - `Access Token`: тот же токен, что у хаба или в `.site-control-kit\generated_token.txt`.

### Windows Core Smoke Checklist

Перед release или publish-checkpoint на Windows нужно пройти именно этот набор:

```cmd
cd <repo-root>
scripts\start_hub.cmd
browser.cmd status
browser.cmd tabs
python -m webcontrol --help
python -m webcontrol browser --help
python -m webcontrol runtime-env --format json --no-create
telegram-username-collector
```

Ожидаемый результат:
- хаб поднимается без traceback;
- `browser.cmd status` и `browser.cmd tabs` отрабатывают через текущий runtime; до подключения extension первый ответ уровня `No connected browser clients...` допустим и сам по себе не blocker;
- `runtime-env` показывает корректные runtime paths и token source;
- в fresh checkout автоматически создаются runtime-каталоги;
- UTF-8 пути и русский текст не ломаются в stdout/stderr;
- `telegram-username-collector` не пытается стартовать GTK GUI на Windows, а честно завершает запуск понятным fast-fail сообщением, что Windows GTK GUI не входит в v1.

Полный пошаговый handoff для этого smoke, включая `Terminal A` / `Terminal B`, runtime artifacts, UTF-8 probe и формат отчёта: [docs/WINDOWS_SMOKE_HANDOFF_RU.md](docs/WINDOWS_SMOKE_HANDOFF_RU.md).

Практические замечания по последнему локальному Windows rerun:
- в PowerShell bare `.cmd` удобнее вызывать как `.\browser.cmd` и `.\telegram-username-collector.cmd`;
- existing `%USERPROFILE%\.site-control-kit` переводит этот host в `legacy-adopted`, поэтому отсутствие repo-local `var\site-control-kit` в таком сценарии не blocker;
- для Git Bash helper на Windows есть `bash.cmd`, который подбирает установленный `bash.exe` и не упирается в WindowsApps stub.

### Упаковка расширения в Windows

```cmd
scripts\package_extension.cmd
```

Готовый архив: `dist\site-control-bridge-extension.zip`

### Linux/macOS

### Ubuntu `.deb` product path

Если нужен не repo checkout, а готовая программа для Ubuntu 24.04:

```bash
cd <repo-root>
bash scripts/build_linux_deb.sh
sudo apt install ./dist/linux-deb/telegram-username-collector_0.1.0_amd64.deb
telegram-username-collector --doctor
telegram-username-collector
```

Дополнительно:

```bash
telegram-username-collector --create-desktop-shortcut
```

Что делает установленная версия:
- ставит приложение в `/opt/telegram-username-collector`;
- добавляет launcher в меню приложений;
- хранит token/config в `${XDG_CONFIG_HOME:-~/.config}/site-control-kit`;
- хранит workspace/reports/state в `${XDG_DATA_HOME:-~/.local/share}/site-control-kit`;
- хранит логи в `${XDG_STATE_HOME:-~/.local/state}/site-control-kit/logs`;
- кладёт companion extension zip в `/opt/telegram-username-collector/app/resources/site-control-bridge-extension.zip`.

Подробный install/update/uninstall flow: [docs/LINUX_PRODUCT_INSTALL_RU.md](docs/LINUX_PRODUCT_INSTALL_RU.md).

## 1) Запуск хаба

```bash
cd <repo-root>
python3 -m pip install -r requirements.txt
python3 -m pip install -e .
./scripts/start_hub.sh
```

GTK GUI на Linux не ставится через `pip`.
Для него нужен системный `python3` с рабочими GTK bindings.
Проверка окружения:

```bash
cd <repo-root>
bash scripts/bootstrap_telegram_workstation.sh --doctor
```

На Ubuntu 24.04 минимум нужен рабочий `python3-gi` и GTK 4 runtime.

На первом запуске хаб:
- создаёт `./var/site-control-kit`, если нет legacy runtime;
- или использует `.site-control-kit/local.yaml`, если найден существующий `~/.site-control-kit`;
- генерирует локальный токен в `.site-control-kit/generated_token.txt`, если вы заранее не задали `SITECTL_TOKEN`.

## 2) Установка расширения (без публикации в Store)
1. Откройте `chrome://extensions`.
2. Включите `Developer mode`.
3. Нажмите `Load unpacked`.
4. Выберите папку: `<repo-root>/extension`.
5. Откройте `Options` расширения и проверьте:
- `Server URL`: `http://127.0.0.1:8765`
- `Access Token`: тот же, что у хаба.

Упаковка в zip:

```bash
cd <repo-root>
./scripts/package_extension.sh
```

Готовый архив: `dist/site-control-bridge-extension.zip`

### Быстрый запуск рабочего контура на Linux

Если нужен один вход в рабочий контур, используйте:

```bash
cd <repo-root>
./start-browser.sh
```

Что делает скрипт:
- поднимает хаб автоматически, если он ещё не запущен;
- предпочитает Chromium-совместимый браузер, где можно загрузить unpacked extension флагами;
- если доступен только branded `google-chrome`, открывает выделенный профиль и даёт one-time шаги для ручной загрузки `extension/`.

Если branded Chrome мешает, есть отдельный Firefox dev-path:

```bash
cd <repo-root>
./start-firefox.sh --url https://web.telegram.org/a/
```

Что делает этот запуск:
- поднимает хаб;
- на обычном Firefox запускает `web-ext run` и ставит `extension/` автоматически;
- на snap Firefox честно падает в `about:debugging` temporary-add-on path;
- использует выделенный debug-profile, чтобы Telegram cookies/session не терялись между прогонами.

Важно:
- это именно dev/debug-контур;
- temporary add-on поднимается заново на каждом запуске `start-firefox.sh`;
- на этой машине snap Firefox не даёт `web-ext` надёжно подключиться к debugger port, поэтому manual fallback для snap-сборки ожидаем.

После этого рабочие команды:

```bash
cd <repo-root>
./browser.sh status
./browser.sh tabs
./browser.sh open https://example.com
```

## 3) Проверка связи

```bash
cd <repo-root>
python3 -m webcontrol health
python3 -m webcontrol clients
```

## Простое управление браузером

После установки расширения и запуска хаба можно использовать упрощённую команду:

```cmd
scripts\browser.cmd status
scripts\browser.cmd tabs
scripts\browser.cmd open https://example.com
scripts\browser.cmd click "button[type='submit']"
scripts\browser.cmd context-click ".item"
scripts\browser.cmd clear "#editable-message-text"
scripts\browser.cmd fill "#email" "user@example.com"
scripts\browser.cmd text main
scripts\browser.cmd screenshot --output .\shot.png
```

Если онлайн-клиент один, он выбирается автоматически. Для реальных действий `browser ...` берёт самый свежий онлайн-клиент. Если онлайн-клиентов несколько, по умолчанию берётся самый свежий, либо можно указать `--client-id`.

CLI внутри Python-пакета:

```bash
sitectl browser status
sitectl browser open https://example.com
sitectl browser clear "#editable-message-text"
sitectl browser press Enter
```

Linux-обёртка:

```bash
./browser.sh status
./browser.sh text body
```

## Telegram Workflow

Для Telegram Web есть отдельный рабочий вход:

```bash
cd <repo-root>
./start-telegram.sh
```

Firefox-вариант для Telegram:

```bash
cd <repo-root>
./start-telegram-firefox.sh
```

Что делает этот запуск:
- поднимает хаб;
- открывает браузерный профиль на `web.telegram.org`;
- если bridge-клиента ещё нет, Telegram export-скрипты сами попытаются открыть этот профиль повторно.

CLI-экспорт:

```bash
cd <repo-root>
./telegram-export.sh --source both --deep-usernames
```

Примечание:
- `--force-navigate` теперь умеет переживать Telegram redirect в `web.telegram.org/k/` и сам доводит вкладку до реального открытого диалога;
- если Telegram Web не даёт автоматически открыть `Group Info -> Members`, режим `--source both` теперь не падает, а продолжает выгрузку через `chat` fallback;
- если Telegram Web в `Group Info` отдаёт только preview админов/модераторов вместо полного каталога участников, экспортёр теперь помечает это как `info-preview` и рекомендует `--source both`;
- если `Group Info -> Members` открылся, но в DOM загружена только часть списка, экспортёр честно предупредит сколько участников видно сейчас и какой общий hint вернул Telegram;
- направление скролла тут важно только для `chat`-режима: чат читается прокруткой вверх, а `info`-режим использует прокрутку вниз только когда Telegram реально отдал список участников; в `info-preview` смена направления колеса обычно ничего не меняет;
- в текущем Telegram Web chat-проход больше не опирается на старые `.bubbles`-селектора: инструмент умеет листать историю через новый `MessageList/backwards-trigger` DOM и реально поднимать новых авторов из истории;
- chat-проход теперь может автоматически продлеваться после `--chat-scroll-steps`, пока реально появляются новые авторы; лимит задаётся через `--chat-auto-extra-steps`;
- каждый экспорт дополнительно архивируется в [artifacts/telegram_exports](artifacts/telegram_exports) и записывается в индекс [INDEX.md](artifacts/telegram_exports/INDEX.md);
- рядом с каждым экспортом теперь автоматически пишутся отдельные sidecar-файлы `*_usernames.txt` и `*_usernames.json`, чтобы собранные `@username` можно было брать без парсинга markdown-таблицы;
- экспортёр теперь автоматически ведёт per-chat history в [artifacts/telegram_exports/state](artifacts/telegram_exports/state) и при следующем прогоне поднимает уже известные `@username` из прошлых archived sidecars;
- sticky-author path теперь работает через `telegram_sticky_author`: правый клик делается по нижней прилипшей 34px иконке автора, а не по тексту сообщения и не через открытие профиля левой кнопкой;
- `--deep-usernames` больше не должен уводить основную групповую вкладку в личные диалоги: usernames дочитываются через временные helper tabs;
- если текущий Telegram Web отвечает `No visible menu item found by text`, это теперь трактуется как честный признак отсутствия `Mention` в текущем menu-path: exporter сразу уходит в helper-only path и не тратит оставшийся deep-step на пустые retry;
- exporter и safe/batch слой теперь отфильтровывают ложные `@username`, состоящие только из цифр: артефакты вида `@1291639730` больше не должны попадать в новые `latest_safe.*`, `identity_history.json` и numbered batches;
- `--deep-usernames` в `info`-режиме может работать заметно дольше обычного запуска, потому что Telegram последовательно открывает видимые профили;
- live baseline на 2026-04-23 для чата `https://web.telegram.org/a/#-1002465948544`: `fast` batch-run `20260423T173223Z` дошёл до `27` visible members и `10` safe usernames, а `latest_full.*` и `latest_safe.*` были обновлены на этот run;
- для максимально полного списка участников всё равно лучше вручную открыть `Group Info -> Members` перед повторным запуском.

GUI-экспорт:

```bash
cd <repo-root>
./scripts/telegram_members_export_gui.sh
```

Новый Linux-first install/run path для этого GUI:

```bash
cd <repo-root>
bash scripts/bootstrap_telegram_workstation.sh --doctor
bash scripts/bootstrap_telegram_workstation.sh
telegram-username-collector
```

Что это даёт:
- `telegram-username-collector --doctor` теперь даёт product/runtime диагностику без запуска GTK окна;
- `telegram-username-collector --create-desktop-shortcut` создаёт ярлык текущему Linux-пользователю;
- `bootstrap_telegram_workstation.sh --doctor` проверяет `gi/GTK`, `python3`, helper requirements и текущий helper source;
- `--doctor` теперь также печатает resolved runtime root, logs root, reports root и JSONL-логи;
- обычный `bootstrap_telegram_workstation.sh` поднимает managed helper venv в `./var/site-control-kit/telegram_workspace/managed_helper/.venv`;
- launcher `telegram-username-collector` идёт из `pyproject.toml` и поднимает тот же single-window GUI;
- внутренний ownership GUI теперь разделён так: `scripts/telegram_gui/app.py` = thin launcher/composition, `scripts/telegram_gui/backend.py` = backend owner, `scripts/telegram_gui/ui/window.py` = window/app owner;
- если launcher запущен из Python-окружения без GTK bindings, он теперь завершается понятной ошибкой и отправляет в `bootstrap_telegram_workstation.sh --doctor`, а не падает build/import traceback;
- helper discovery order теперь такой: `TELEGRAM_API_COLLECTOR_PYTHON` -> managed helper venv -> legacy external collector path;
- если уже существует legacy workspace `~/.site-control-kit/telegram_workspace`, bootstrap остаётся на нём через `.site-control-kit/local.yaml`, а не переносит данные автоматически.

Что умеет GUI теперь:
- отдельное GTK-приложение вместо `zenity`-формы;
- единый Telegram workspace по умолчанию: `./var/site-control-kit/telegram_workspace`;
- при наличии legacy runtime тот же GUI может работать поверх `~/.site-control-kit/telegram_workspace` через локальный pointer-config;
- реестр пользователей (имя + профиль + API token): `telegram_workspace/registry/users.json`;
- слоты пользователей `1..10`: `telegram_workspace/accounts/<N>/`:
  - `profile/` (данные профиля, включая `tdata`/portable browser data),
  - `imports/` (zip-архивы профилей),
  - `keys/` (`api_token.txt`, `api_id.txt`, `api_hash.txt`);
- в списке профилей показываются только реальные профили/zip, пустые auto-slots больше не засоряют UI;
- если в выбранном профиле найден `tdata` или matching `tdata-*.zip`, GUI сначала ищет живую Telegram Desktop session через API, включая импортированный portable `tdata`, без экрана авторизации;
- в `tdata`-режиме GUI не должен запускать внешний portable Telegram автоматически: сбор и список чатов идут напрямую через API/helper, чтобы не ломать импортированную сессию;
- в GUI `tdata`-экспорт теперь идёт по авторам сообщений из chat history (`history-only`), а не по общему списку `participants`;
- в `history-only` path фильтруются bots, non-user sender'ы и записи без валидного `@username`;
- глубина history настраивается через `TELEGRAM_TDATA_HISTORY_LIMIT` (`0` по умолчанию = весь доступный history), шаг progress через `TELEGRAM_TDATA_PROGRESS_EVERY`;
- timeout для helper тоже настраивается:
  - `TELEGRAM_TDATA_LIST_TIMEOUT_SEC` для чтения списка чатов;
  - `TELEGRAM_TDATA_EXPORT_TIMEOUT_SEC` для длинного history-export;
- progress helper теперь попадает в live-log GUI строками вида `PROGRESS chat=... messages=... usernames=...`;
- каждый запуск дополнительно получает machine-readable sidecars:
  - `telegram_workspace/runs/<run_id>/summary.json`
  - `telegram_workspace/runs/<run_id>/artifacts.json`
  - `telegram_workspace/runs/<run_id>/events.jsonl`;
- если `tdata` недоступен, GUI падает обратно на старый Telegram Web path;
- список чатов и групп показывается внутри приложения;
- выбранный чат можно открыть прямо в Telegram из GUI перед запуском;
- итоговый `.md` выбирается через системный `Save As` диалог: там задаются и папка, и имя файла;
- экспорт принудительно открывает выбранный чат перед сбором, поэтому не требует заранее открытого URL.

Быстрый сбор именно `@username`, встречающихся в chat history/mentions:

```bash
cd <repo-root>
python3 scripts/export_telegram_chat_mentions.py --target-count 40
```

Этот режим не пытается привязать username к карточке участника. Он просто листает историю чата и сохраняет найденные `@username` в `*.txt` / `*.json`.

Разовый CLI-сценарий для chat-mode:

```bash
cd <repo-root>
./scripts/run_chat_export_once.sh "$SITECTL_TOKEN"
```

Принудительный таргет на конкретный клиент/вкладку:

```bash
./scripts/run_chat_export_once.sh "$SITECTL_TOKEN" "/tmp/chat_export.md" "https://web.telegram.org/a/#-1002465948544" 20 10 12 180 mention 0 "client-REPLACE_ME" "123456789"
```

Важно:
- если на Linux доступен только branded `google-chrome`, one-time загрузите unpacked extension из `extension/` в выделенном профиле;
- после этого Telegram-скрипты будут использовать уже этот профиль и искать Telegram-вкладку по всем живым клиентам, а не только по первому найденному.

## 4) Примеры команд

```bash
# Открыть страницу в активной вкладке клиента
python3 -m webcontrol send \
  --type navigate \
  --client-id client-REPLACE_ME \
  --url "https://example.com" \
  --wait 20
```

```bash
# Заполнить поле и кликнуть кнопку
python3 -m webcontrol send --type fill --client-id client-REPLACE_ME --selector "#email" --value "user@example.com"
python3 -m webcontrol send --type click --client-id client-REPLACE_ME --selector "button[type='submit']"
```

```bash
# Подождать селектор
python3 -m webcontrol send --type wait_selector --client-id client-REPLACE_ME --selector "body" --wait 20
```

```bash
# Извлечь текст
python3 -m webcontrol send --type extract_text --client-id client-REPLACE_ME --selector "main" --wait 20
```

Важно:
- `send` без явного target теперь безопаснее: если онлайн-клиент ровно один, он выбирается автоматически.
- Если онлайн-клиентов несколько, команда без `--client-id`, `--client-ids` или `--broadcast` будет отклонена хабом.

## 5) Просмотр состояния хаба

```bash
python3 -m webcontrol state
```

## 6) Автоматическая Проверка

Базовый verify-контур одной командой:

```bash
cd <repo-root>
./scripts/verify.sh
```

Если уже есть живой браузерный клиент и нужно прогнать live smoke:

```bash
cd <repo-root>
./scripts/verify.sh --live-browser
```

## Установка CLI как команды `sitectl`

```bash
cd <repo-root>
python3 -m pip install -e .
```

После этого можно использовать:

```bash
sitectl clients
sitectl state
sitectl send --type navigate --client-id client-... --url https://example.com --wait 20
```

## Работа на других устройствах
Подробно: [INSTALL_OTHER_DEVICES_RU.md](docs/INSTALL_OTHER_DEVICES_RU.md)

Коротко:
1. Скопировать репозиторий на устройство.
2. Запустить хаб.
3. Загрузить расширение в браузер.
4. Указать URL/токен.
5. Проверить `clients`.

Поддерживаемые браузеры для загрузки unpacked-расширения:
- Google Chrome
- Microsoft Edge
- Brave
- Chromium
- Opera
- Яндекс Браузер

Отдельно для локальной отладки:
- Firefox через `web-ext run` и временную установку расширения

## Документация
- [CHANGES_RU.md](docs/CHANGES_RU.md) — полный перечень реализованных изменений.
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — архитектура и жизненный цикл команд.
- [API.md](docs/API.md) — API и контракт команд.
- [EXTENSION.md](docs/EXTENSION.md) — внутренняя логика расширения.
- [SECURITY.md](docs/SECURITY.md) — безопасность и рекомендации.
- [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — диагностика проблем.
- [AI_MAINTAINER_GUIDE.md](docs/AI_MAINTAINER_GUIDE.md) — как агенту использовать, изменять и улучшать инструмент.
- [AGENTS.md](AGENTS.md) — правила для ИИ-агентов и политика применения `site-control-kit` как основного браузерного инструмента.

## Структура проекта

```text
webcontrol/         # Python: сервер, очередь, CLI
extension/          # Расширение браузера (MV3)
scripts/            # Вспомогательные скрипты запуска/упаковки/экспорта
docs/               # Полная документация
examples/           # Примеры payload-команд
tests/              # Автотесты
```

## Важные ограничения
- `run_script` может блокироваться CSP сайта (`unsafe-eval`), это нормально.
- На служебных страницах (`chrome://*`) content script не работает.
- Manifest V3 service worker может «засыпать», поэтому есть polling + alarms.

## Правовые границы
Используйте инструмент только для сайтов и систем, где у вас есть разрешение на автоматизацию.

## Публикация на GitHub

```bash
cd <repo-root>
git config user.name "Ваше имя в GitHub"
git config user.email "ваш_email@example.com"
git add .
git commit -m "Стартовая версия: локальный хаб, расширение и документация (RU)"
git remote add origin https://github.com/<ВАШ_ЛОГИН>/site-control-kit.git
git push -u origin main
```

Если репозиторий `site-control-kit` ещё не создан в GitHub:
1. Откройте GitHub и создайте пустой репозиторий `site-control-kit` без README/.gitignore.
2. Выполните команды выше для первого push.
