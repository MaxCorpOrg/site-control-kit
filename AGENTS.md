# Правила работы агента

Этот файл задаёт правила для ИИ-агентов, которые работают с репозиторием `site-control-kit`.

## Что Это Такое
`site-control-kit` — локальный инструмент управления браузером.
Внутри него:
- Python-хаб с HTTP API, очередью команд и хранением состояния.
- интерфейс командной строки (CLI) `sitectl` и удобный слой `sitectl browser`.
- браузерное MV3-расширение, которое исполняет команды в реальных вкладках.
- Windows-обёртки `browser.cmd` и `start-hub.cmd` для быстрого старта.
- платформа с реестром для отдельных операторских инструментов и графической панели управления.

Используйте этот репозиторий как основной локальный инструмент браузерной автоматизации, когда он доступен в рабочей папке.

## Что Проект Реально Умеет Сейчас
Новый агент должен понимать проект не как "браузер с парой скриптов", а как набор рабочих подсистем.

### 1. Платформа связи с браузером
Проект уже умеет:
- поднимать локальный HTTP-хаб;
- принимать сигнал активности от браузерных клиентов;
- хранить клиентов, вкладки, очереди и результаты в `state.json`;
- выдавать команды браузеру и принимать результаты обратно;
- работать как единый источник правды по клиентам и командам.

Основные файлы:
- `webcontrol/server.py`
- `webcontrol/store.py`
- `webcontrol/config.py`
- `webcontrol/utils.py`

### 2. Командный интерфейс и обёртки
Проект уже умеет давать короткий операторский интерфейс поверх хаба.

Командный интерфейс сейчас покрывает:
- `serve`, `health`, `state`, `clients`, `send`, `wait`, `cancel`;
- `browser status`, `clients`, `tabs`;
- `browser open`, `new-tab`, `click`, `click-text`, `fill`, `focus`;
- `browser upload-file`, `native-upload-file`;
- `browser wait`, `text`, `html`, `attr`, `page-url`;
- `browser back`, `forward`, `reload`, `activate`, `close-tab`;
- `browser scroll`, `scroll-by`, `press`, `js`, `screenshot`;
- запасной путь Linux: `browser x11-click`, `browser x11-keys`.

Основные файлы:
- `webcontrol/cli.py`
- `browser.cmd`, `browser.ps1`
- `start-hub.cmd`, `start-hub.ps1`
- `scripts/browser.cmd`, `scripts/browser.ps1`
- `scripts/start_hub.sh`, `scripts/start_hub.cmd`, `scripts/start_hub.ps1`

### 3. Расширение браузера
Расширение уже умеет:
- сигнал активности и периодический опрос;
- фоновые команды уровня вкладки;
- автоматическое внедрение `content.js`, если канал сообщений потерялся;
- объявление возможностей в `meta.capabilities` сигнала активности;
- снимок экрана;
- DOM-действия внутри страницы.

Фоновые команды:
- `navigate`
- `new_tab`
- `reload`
- `activate_tab`
- `close_tab`
- `screenshot`
- `set_file_input_files`

DOM-команды:
- `back`, `forward`, `get_page_url`
- `context_click`, `click_menu_text`, `click_text`, `click`
- `clear_editable`, `fill`, `focus`, `upload_file`
- `extract_text`, `get_html`, `get_attribute`
- `wait_selector`
- `scroll`, `scroll_by`, `wheel`
- `run_script`
- `press_key`

Основные файлы:
- `extension/manifest.json`
- `extension/background.js`
- `extension/content.js`
- `extension/options.*`
- `extension/popup.*`

### 4. Операторские помощники браузера
Кроме базового моста, проект уже содержит операторские и диагностические инструменты:
- `scripts/reload_bridge_extension.sh` — самостоятельная перезагрузка и запасной путь X11 для распакованного расширения;
- `scripts/start_browser_novnc.sh` / `scripts/stop_browser_novnc.sh` — noVNC поверх X11 для визуального контроля браузера;
- `scripts/package_extension.*` — упаковка расширения;
- `examples/*.json` — примеры данных команд.

### 5. Контур экспорта Telegram
Это сейчас самая развитая прикладная часть проекта.

Проект уже умеет:
- открывать и переиспользовать нужную вкладку Telegram Web;
- собирать видимых участников чата;
- вытягивать `@username` через deep-path (`mention`, `url`, `profile`);
- вести `identity_history.json` и `discovery_state.json`;
- разделять raw и safe snapshots;
- писать numbered batch files только с новыми safe usernames;
- запускать chain of short runs с профилями `fast`, `balanced`, `deep`;
- не затирать сильные historical latest-снимки слабым прогоном;
- сохранять `run.json`, `export.log`, `export_stats.json`.

Основные файлы:
- `scripts/export_telegram_members_non_pii.py`
- `scripts/auto_collect_usernames.sh`
- `scripts/collect_new_telegram_contacts.sh`
- `scripts/collect_new_telegram_contacts_chain.sh`
- `scripts/telegram_contact_chain.py`
- `scripts/telegram_contact_batches.py`
- `scripts/telegram_profiles.py`
- `scripts/write_telegram_safe_snapshot.py`
- `scripts/telegram_members_export_app.sh`
- `scripts/telegram_members_export_gui.sh`

### 6. Контур приглашений Telegram
Это отдельный безопасный сценарий с участием оператора поверх браузерного моста.

Проект уже умеет:
- хранить state согласованных пользователей;
- импортировать CSV/JSON;
- выбирать следующую пачку usernames;
- вести `invite_state.json` и run-артефакты;
- строить execution plan;
- открывать Telegram chat через `site-control`;
- делать `inspect-chat`;
- выполнять осторожный `add-contact` для одного consented user;
- писать execution record и verification evidence.

Основные файлы:
- `scripts/telegram_invite_manager.py`
- `scripts/telegram_invite_manager_gui.sh`
- `scripts/telegram_invite_executor.py`
- `scripts/telegram_invite_executor_gui.sh`
- `scripts/telegram_invite_gui_common.sh`
- `tools/telegram/invite_manager/*`

### 7. Переносимые профили Telegram Desktop
Проект уже умеет:
- брать `zip` с `tdata`;
- поднимать отдельный Linux Telegram Desktop portable-profile;
- использовать `TelegramForcePortable`;
- кэшировать официальный runtime Telegram Desktop;
- запускать такой профиль отдельно от системного Telegram.

Основные файлы:
- `scripts/telegram_portable.py`
- `scripts/telegram_portable_gui.sh`
- `docs/TELEGRAM_PORTABLE_RU.md`
- `tools/telegram/portable_helper/*`

### 8. Дополнительные прикладные утилиты
В проекте есть и более узкие вспомогательные инструменты:
- `scripts/export_feishu_bundle.py` — отдельный Playwright-based export/translation helper для Feishu wiki bundle.
- `telegram_members_export_exe/` — готовая Windows GUI-упаковка для Telegram export сценария.
- `dist/` — операторские артефакты, скриншоты, собранный zip расширения и следы упаковочных/ручных smoke-сценариев.

### 9. Единая платформа инструментов
Проект умеет держать отдельные рабочие сценарии Telegram как самостоятельные единицы и подключать их в общий слой управления.

Сейчас этот слой уже умеет:
- читать manifests подключённых инструментов;
- держать registry embedded tools и visible wrappers;
- показывать единый catalog через CLI;
- открывать Tkinter GUI panel без жёсткого хардкода конкретного Telegram-инструмента;
- давать profile-first Telegram-панель с dropdown выбора portable-пользователя и импортом по `tdata.zip`;
- подключать внутренние `telegram_invite_manager`, `telegram_portable_helper`, `telegram_export` и visible wrapper `tools/telegram/session_runner/`.

Основные файлы:
- `tool_platform/catalog.py`
- `tool_platform/cli.py`
- `tool_platform/gui.py`
- `tools/telegram/*`
- `tools/telegram/platform/*`
- `tools/telegram/invite_manager/tool_manifest.json`

### 10. Документация и операторская база знаний
Помимо кода, в проекте уже есть рабочая база знаний, по которой агент должен быстро понять нужный контур:
- `README.md` и `BROWSER_QUICKSTART.md` — быстрый практический вход;
- `docs/API.md`, `docs/ARCHITECTURE.md`, `docs/EXTENSION.md` — технический контракт и слои;
- `docs/TROUBLESHOOTING.md`, `docs/SERVER_BROWSER_ACCESS.md`, `docs/INSTALL_OTHER_DEVICES_RU.md` — эксплуатация, удалённый доступ и подключение других машин;
- `docs/TELEGRAM_*` — отдельные дорожные карты и operator-инструкции для Telegram export / invite / portable;
- `docs/agent_handoff_ru/*` и `docs/PROJECT_STATUS_RU.md` — continuity layer между агентами и чатами.

### 11. Регрессионные и модульные тесты
Проект уже имеет модульное покрытие ключевых слоёв:
- `tests/test_store.py`
- `tests/test_cli_browser_helpers.py`
- `tests/test_telegram_export_parser.py`
- `tests/test_telegram_contact_batches.py`
- `tests/test_telegram_contact_chain.py`
- `tests/test_telegram_profiles.py`
- `tests/test_telegram_invite_manager.py`
- `tests/test_telegram_invite_executor.py`
- `tests/test_telegram_portable.py`
- `tests/test_utils.py`

## Как Агенту Классифицировать Любую Задачу
Перед изменением кода агент должен отнести задачу к одной из подсистем.

- Хаб, auth, очередь, aggregate command status, `state.json`:
  идти в `webcontrol/server.py`, `webcontrol/store.py`, `webcontrol/config.py`.

- Короткая команда для оператора, таргетинг клиента/вкладки, X11 fallback, upload:
  идти в `webcontrol/cli.py` и wrappers.

- Новая background browser-команда:
  идти в `extension/background.js`, потом синхронизировать `docs/API.md`, `docs/EXTENSION.md`, `examples/`.

- Новая DOM-команда:
  идти в `extension/content.js`, потом синхронизировать `docs/API.md`, `docs/EXTENSION.md`, `examples/`.

- System page / Chrome page / Linux window recovery:
  сначала смотреть `browser x11-click`, `browser x11-keys`, `scripts/reload_bridge_extension.sh`.

- Telegram usernames export / chain / safe snapshots / deep-path:
  идти в экспортёрный стек и видимую папку `tools/telegram/export/`, а не в invite/portable code.

- Consent-based Telegram invite execution:
  идти в `telegram_invite_manager.py`, `telegram_invite_executor.py` и `tools/telegram/invite_manager/`, а не в экспортёр.

- Linux Telegram Desktop из `tdata.zip`:
  идти в `telegram_portable.py` и `tools/telegram/portable_helper/`, а не в browser bridge или Telegram Web code.

- Unified tool platform / graphical control panel / manifests:
  идти в `tool_platform/*.py`, `tools/telegram/platform/*`, `tools/telegram/*` и `tool_manifest.json` соответствующего инструмента, а не вшивать новый модуль прямо в существующий GUI.

- Визуальное наблюдение и ручной browser recovery:
  смотреть `start_browser_novnc.sh` / `stop_browser_novnc.sh`.

- Feishu export:
  смотреть `scripts/export_feishu_bundle.py`.

- Windows GUI-дистрибутив или готовый deliverable для Telegram export:
  смотреть `telegram_members_export_exe/` и связанные shell-wrappers.

- Упаковка extension, готовые zip/скриншоты/ручные operator artifacts:
  смотреть `scripts/package_extension.*` и `dist/`.

## С Чего Начинать Агенту
Перед любой работой прочитать в таком порядке:
1. `AGENTS.md` — этот файл, без пропусков.
2. `docs/AGENT_SIMPLE_GUIDE_RU.md` — самый простой практический путеводитель.
3. `START_HERE_AGENT_RU.md` — короткая входная точка, чтобы агент не начал работу "с нуля" и сразу продолжал с последней подтверждённой точки.
4. `docs/agent_handoff_ru/00_START_HERE.md` — единая точка входа для нового агента.
5. Весь пакет `docs/agent_handoff_ru/` по порядку файлов `00..10`.
6. `docs/PROJECT_WORKFLOW_RU.md` — обязательный порядок работы, проверки и передачи контекста.
7. `docs/PROJECT_STATUS_RU.md` — что уже сделано, что проверено, что сломано, что делать дальше.
8. `BROWSER_QUICKSTART.md` — короткий путь запуска и базовые команды.
9. `docs/AI_MAINTAINER_GUIDE.md` — как агенту использовать и развивать инструмент.
10. `docs/API.md` — протокол, типы команд, контракт результата.
11. `docs/ARCHITECTURE.md` — поток команд, роли компонентов, маршрутизация.
12. `docs/EXTENSION.md` — где реализованы фоновые и DOM-команды.
13. Для задач Telegram дополнительно: `docs/TELEGRAM_CLIENT_ROADMAP_RU.md`.
14. Для задач про переносимые профили Telegram Desktop и `tdata.zip` дополнительно: `docs/TELEGRAM_PORTABLE_RU.md`.
15. Для задач про единую платформу инструментов дополнительно: `tools/telegram/platform/README_RU.md` и `tools/telegram/platform/AGENT_GUIDE_RU.md`.
16. Для операторской структуры Telegram в целом дополнительно: `tools/telegram/README_RU.md` и `tools/telegram/AGENT_GUIDE_RU.md`.
17. Для текущего слоя управления Telegram дополнительно: `tools/telegram/agent_pack/README_RU.md`, `tools/telegram/agent_pack/VERIFICATION_MATRIX_RU.md`, `tools/telegram/agent_pack/agent_state.template.json` и рабочее состояние `~/.site-control-kit/telegram/agent/agent_state.json`.

Внутри каждой рабочей папки сначала прочитать ближайший `AGENTS.md`: он объясняет назначение каталога, порядок работы, ограничения и частые ошибки.

## Язык документации

- Вся документация и инструкции для агента пишутся по-русски.
- Английское слово допустимо, если это имя продукта, команда, путь, ключ протокола или термин без короткого точного перевода.
- Необходимый английский термин при первом употреблении поясняется по-русски; общий словарь находится в `docs/TERMS_RU.md`.
- Имена команд, ключи JSON и идентификаторы в коде не переводятся.
- Новый или изменённый документ проверяется на понятность без знания внутренней истории проекта.

Запрещено начинать изменения в коде, не просмотрев `docs/PROJECT_STATUS_RU.md`. Этот файл нужен, чтобы новый чат или новый агент не дублировал уже закрытые задачи и видел текущие дыры.

Новый агент не должен воспринимать проект как пустой контекст.
Он обязан сначала определить:
- последний завершённый блок;
- текущий риск;
- следующий приоритет;
- и только потом продолжать работу именно с этой точки.

## Миссия
Поддерживать и улучшать `Site Control Kit` как локальную платформу управления сайтами:
- хаб должен оставаться простым, наблюдаемым и предсказуемым;
- команды должны быть короткими и удобными для оператора и агента;
- браузерное управление должно быть пригодным для реальной работы, а не только для демо.

## Политика Использования
- Считать `site-control-kit` основным браузерным инструментом по умолчанию.
- На Windows предпочитать `browser.cmd` и `start-hub.cmd`.
- В Python-окружениях предпочитать `sitectl browser`.
- Перед обходными путями сначала проверять живой контур через `browser status`, `browser clients` или `browser tabs`.
- Если инструмент можно улучшить ради текущей задачи, это допустимо и желательно.
- Для задач вида "есть `tdata.zip`, нужно открыть Telegram Desktop этого пользователя на Linux" предпочитать `scripts/telegram_portable.py` и `scripts/telegram_portable_gui.sh`, а не ручную раскладку файлов.

## Неприкосновенные Правила
1. По возможности сохранять обратную совместимость API.
2. Никогда не ослаблять проверку токена и авторизации без явного решения.
3. Любые изменения протокола документировать в `docs/API.md`.
4. Любые изменения UX команд документировать в `README.md` и `BROWSER_QUICKSTART.md`.
5. При изменении возможностей расширения обновлять `docs/EXTENSION.md`.
6. При изменении payload-команд обновлять `examples/`.
7. Не добавлять внешние зависимости без технического обоснования.

## Источники Правды
- Протокол: `docs/API.md`
- Архитектура: `docs/ARCHITECTURE.md`
- Агентный workflow: `docs/AI_MAINTAINER_GUIDE.md`
- Внутренности расширения: `docs/EXTENSION.md`
- Безопасность: `docs/SECURITY.md`

## Обязательный Рабочий Контур
Перед задачами реального управления браузером:
1. Запустить хаб.
2. Проверить `browser status`.
3. Проверить `browser tabs`.
4. Только потом отправлять рабочие команды.

Если расширение было перезагружено или обновлено, сначала снова проверить `browser status`.

## Минимальные Проверки
- Обязательно запускать: `PYTHONPATH="$PWD" python3 -m unittest discover -s tests -p 'test_*.py'`
- При изменении CLI полезно проверить:
  - `PYTHONPATH="$PWD" python3 -m webcontrol --help`
  - `PYTHONPATH="$PWD" python3 -m webcontrol browser --help`
- При изменении браузерного контура полезно делать smoke-проверку:
  - `browser.cmd status`
  - `browser.cmd tabs`
  - `browser.cmd open https://example.com`
  - `browser.cmd text h1`

## Обязательный Цикл Работы
Каждая завершённая задача должна проходить через один и тот же цикл:
1. Проверить текущее состояние дерева:
   - `git status --short --branch`
2. Просмотреть уже завершённые задачи и последнее состояние проекта:
   - `docs/PROJECT_STATUS_RU.md`
   - `git log --oneline -n 15`
3. Для Telegram-задач до правок просмотреть последние артефакты:
   - `chat_<id>/latest_full.md`
   - `chat_<id>/latest_safe.md`
   - последний `runs/<timestamp>/run.json`
   - последний `runs/<timestamp>/export.log`
   - если есть, `runs/<timestamp>/export_stats.json`
   - `identity_history.json`
   - `discovery_state.json`
4. После каждой законченной правки обязательно прогнать проверки.
5. После проверок обновить `docs/PROJECT_STATUS_RU.md`:
   - что сделано;
   - что проверено;
   - что осталось;
   - какой следующий логичный шаг.
6. Только потом считать задачу завершённой.

## Правило Проверок Для Этого Проекта
Это правило обязательное для любого агента и любого чата:
- После каждой завершённой задачи запускать полный unit-набор:
  - `PYTHONPATH="$PWD" python3 -m unittest discover -s tests -p 'test_*.py'`
- Если менялись Python entrypoints или большие Python-модули:
  - `python3 -m py_compile <изменённые python-файлы>`
- Если менялись shell-скрипты:
  - `bash -n <изменённые shell-файлы>`
- Если меняется живой browser/Telegram контур:
  - делать хотя бы один живой smoke и сохранять путь к `run.json`/`export.log` в `docs/PROJECT_STATUS_RU.md`

Нельзя завершать задачу сообщением "готово", если проверки не были запущены или явно не описано, почему их нельзя было выполнить.

## Telegram-Специфичный Диагностический Порядок
Если задача связана с тем, что Telegram "не собрал username", "застрял", "ничего не сохранил" или "сохранил не того":
1. Сначала определить, на каком слое сбой:
   - discovery/scroll;
   - mention-deep/url-deep;
   - backfill из `identity_history.json`;
   - safe/quarantine слой;
   - batch layer.
2. Не делать вывод по одному `latest_full.txt`; всегда смотреть ещё:
   - `latest_full.md`
   - `latest_safe.md`
   - последний `run.json`
   - последний `export.log`
3. Если новый прогон дал результат хуже исторического, отдельно проверить, не затёр ли он полезные safe/raw-артефакты.
4. Перед следующей правкой явно зафиксировать в `docs/PROJECT_STATUS_RU.md`, что именно сейчас является узким местом.

## Правило коммитов и передачи контекста
- Коммиты для проектной работы писать осмысленно и по-русски.
- После серии изменений агент обязан оставить в `docs/PROJECT_STATUS_RU.md` короткий handoff:
  - последний завершённый блок;
  - доказательства проверки;
  - текущий риск;
  - следующий приоритет.

## Куда Вносить Изменения
- `webcontrol/cli.py` — CLI, `sitectl browser`, удобные команды и разбор аргументов.
- `webcontrol/server.py` — HTTP API, auth, маршрутизация и выдача команд.
- `webcontrol/store.py` — очередь, состояния, агрегирование статусов, persistence.
- `extension/background.js` — heartbeat, polling, tab-level команды, screenshot.
- `extension/content.js` — DOM-команды, чтение страницы, click/fill/wait/text/html/js.
- `scripts/*.cmd`, `scripts/*.ps1` — Windows-вход и удобство использования.
- `tool_platform/*.py` — registry, manifest loader, unified CLI и GUI control panel.
- `tools/telegram/*` — единый видимый Telegram tools hub.
- `tools/telegram/platform/*` — видимая папка platform-layer, registry и документация.

## Инварианты
- Хаб — единственный источник правды по клиентам, очередям и результатам.
- Каждая команда имеет стабильный `id`.
- Агрегированный статус должен соответствовать доставкам и результатам.
- Автовыбор клиента должен оставаться безопасным и предсказуемым.
- `state.json` должен оставаться пригодным для ручной диагностики.

## Ограничения, О Которых Агент Должен Помнить
- `chrome://*` и аналогичные защищённые страницы не управляются content script.
- `run_script` может ломаться из-за CSP сайта.
- MV3 service worker может засыпать, поэтому polling и alarms критичны.
- HH, банки, корпоративные панели и похожие сайты могут ограничивать часть сценариев, особенно выполнение JS.

## Политика Улучшений
Допустимо и полезно:
- добавлять более короткие и понятные команды;
- улучшать выбор клиента и вкладки;
- делать Windows-обёртки удобнее;
- улучшать диагностику ошибок и подсказки;
- расширять матрицу команд расширения.

Нельзя:
- ломать существующий поток без обновления документации;
- менять контракт молча;
- оставлять новые возможности без примеров и smoke-проверок.
