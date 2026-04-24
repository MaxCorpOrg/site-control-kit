# Site Control Kit

Локальный набор инструментов для управления сайтами через браузерное расширение и локальный хаб-команд.

## Что внутри
- Локальный HTTP-хаб управления (`webcontrol`) с очередью команд и сохранением состояния.
- CLI (`sitectl` / `python3 -m webcontrol`) для отправки команд и диагностики.
- Расширение браузера (Manifest V3) для выполнения команд в реальных вкладках.
- Подробная документация для пользователя и ИИ-агентов сопровождения.

## Быстрый Вход В Браузерный Контур

Кратчайший поддерживаемый сценарий: [BROWSER_QUICKSTART.md](BROWSER_QUICKSTART.md)

Из корня репозитория на Windows:

```cmd
start-hub.cmd
browser.cmd status
browser.cmd tabs
browser.cmd open https://example.com
```

## Для Агентов И Автоматизации

Если репозиторий открыт в рабочей папке агента, считайте `site-control-kit` основным локальным инструментом управления браузером.

Что читать агенту:
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

## Основные сценарии
- Открывать нужные URL во вкладках.
- Кликать по элементам, заполнять поля, ждать появления селекторов.
- Извлекать текст/HTML, делать скриншоты вкладок.
- Управлять несколькими клиентами (браузерами) через `client_id`.
- Выгружать `@username` из Telegram-чата и сохранять только новые контакты батчами.

## Telegram: батчи новых контактов

Для сценария "каждый запуск = новый файл только с новыми `@username`" есть скрипт:

```bash
cd /home/max/site-control-kit
./scripts/collect_new_telegram_contacts.sh "https://web.telegram.org/k/#-2465948544"
```

Что он делает:
- создаёт папку `~/telegram_contact_batches/chat_<id>`;
- старается переиспользовать точную Telegram-вкладку по URL-фрагменту и передаёт её `tab_id` в экспортёр;
- если нужная Telegram-вкладка уже открыта на этом же `#chat`, больше не перезагружает её через `navigate`, чтобы не терять текущую позицию в истории сообщений;
- передаёт в экспортёр `identity_history.json`, чтобы deep-сбор не переназначал `@username` между разными `peer_id`, если история уже знает стабильную связку;
- если новый run видит уже известный `peer_id` без `@username`, восстанавливает его из `identity_history.json` ещё до extra-deep, чтобы повторный прогон не начинал заново с пустого raw-слоя;
- перед записью raw-снимка очищает конфликтные duplicate `@username`, чтобы `latest_full.md` был ближе к truth set, а не только safe-слой;
- ведёт `discovery_state.json`, чтобы следующий запуск знал уже просмотренные слои чата (`data-mid/data-peer-id`) и не тратил первые шаги на тот же самый DOM-срез;
- в `discovery_state.json` теперь хранится и история deep-исходов по `peer_id`, чтобы repeated failure-кандидаты не лезли первыми в каждом новом run;
- если запуск стартует на уже известном слое из `discovery_state.json`, deep сразу откладывается и runtime уходит в прокрутку, а не в повторный mention по тем же людям;
- в `mention`-deep сначала пытается использовать текущий anchor/sticky avatar в чате как стабильную точку для открытия контекстного меню, и только потом откатывается к message-local селекторам;
- если у конкретного peer Telegram не отдаёт пункт `Mention` или mention не дал `@username`, `mention`-режим больше не застревает на этом человеке, а делает лёгкий URL-probe fallback и возвращается в чат;
- если runtime позволяет, `mention`-deep теперь обрабатывает несколько peer за один scroll-step, а не только одного;
- если текущий visible-layer уже даёт результат, deep может продолжить работу на том же слое ещё одним батчем до scroll;
- если Telegram два раза подряд отвечает `No visible menu item found by text`, deep раньше прекращает бесполезные повторные попытки и быстрее уходит в fallback;
- repeated failure peer теперь автоматически деградируют в приоритете deep-выбора, а fresh peer идут раньше;
- repeated failure peer теперь ещё и попадают в мягкий cooldown: если есть более свежие кандидаты, deep не тратит первую волну на заведомо проблемный peer;
- если текущий deep-step уже дал сильный результат и до конца runtime осталось мало, exporter может закончить run раньше, не сжигая хвост времени на малополезный discovery;
- если задан высокий `CHAT_MIN_MEMBERS`, chat-экспорт переходит в discovery-first режим: сначала быстрее добирает новых авторов, отслеживает смену видимого слоя чата по `data-mid/data-peer-id` и при застое делает мягкий burst-скролл, а deep запускает реже, чтобы не сжечь весь runtime на первых шагах;
- парсит не только явные sender-label блоки, но и avatar-only группы сообщений, поэтому видимых участников из текущего DOM собирается больше;
- сохраняет полный последний снимок в `latest_full.md` и `latest_full.txt`;
- сохраняет безопасный снимок после identity-фильтрации в `latest_safe.md` и `latest_safe.txt`;
- если текущий прогон получился слабее уже существующего snapshot, не затирает `latest_full.*` и `latest_safe.*`, а оставляет лучший known state в chat-dir;
- после прогона умеет поднять лучший raw/safe snapshot из `runs/*/snapshot*.md`, если именно там лежит более качественный результат;
- сохраняет отдельный лог запуска в `runs/<timestamp>/` с `run.json`, `export.log`, `export_stats.json`, `snapshot.md`, `snapshot.txt`;
- если запуск прерван `Ctrl+C`/`TERM`, пишет структурный `run.json` со статусом `partial` и сохраняет partial-снапшоты в `runs/<timestamp>/`;
- пишет только новые контакты в `1.txt`, `2.txt`, `3.txt` и так далее;
- если `@username` внезапно сменил владельца (`peer_id`) между запусками, не пишет его в numbered batch, а кладёт случай в `review.txt` и `conflicts.json`.

GUI-скрипты `scripts/telegram_members_export_app.sh` и `scripts/telegram_members_export_gui.sh` теперь тоже пишут safe-артефакты рядом с выбранным выходным файлом:
- `telegram_export_<chat-id>/latest_safe.md`
- `telegram_export_<chat-id>/latest_safe.txt`
- `telegram_export_<chat-id>/review.txt`
- `telegram_export_<chat-id>/conflicts.json`

Параметры можно менять через env, например:

```bash
CHAT_MIN_MEMBERS=10 CHAT_MAX_MEMBERS=10 CHAT_SCROLL_STEPS=40 CHAT_DEEP_LIMIT=20 \
  ./scripts/collect_new_telegram_contacts.sh "https://web.telegram.org/k/#-2465948544"
```

Для серии коротких прогонов с тем же `discovery_state.json` есть chain-runner:

```bash
cd /home/max/site-control-kit
./scripts/collect_new_telegram_contacts_chain.sh "https://web.telegram.org/k/#-2465948544" \
  "/home/max/telegram_contact_batches" \
  --profile balanced \
  --runs 5 \
  --interval-sec 20 \
  --stop-after-idle 2 \
  --stop-after-no-growth 2 \
  --target-unique-members 30
```

По умолчанию chain-runner теперь не ждёт `interval-sec` после run, который завершился на сильном `deep-yield`: если в `run.json` пришли `chat_deep_yield_stop=1` и `deep_updated_total>0`, следующий короткий прогон стартует сразу. Отключить это можно через `--no-skip-interval-on-productive-yield` или `TELEGRAM_CHAIN_SKIP_INTERVAL_ON_PRODUCTIVE_YIELD=0`.
Также у chain-runner появились профили `fast`, `balanced`, `deep`: они задают дефолтный `interval-sec` и безопасный набор env для collect-script. `fast` быстрее идёт по коротким проходам, `deep` даёт более длинный runtime и агрессивнее включает discovery/deep настройки, а ручные env по-прежнему имеют приоритет над профилем.
Те же профили теперь понимают и shell/GUI-обвязки через общий helper `scripts/telegram_profiles.py`: можно выставить `CHAT_PROFILE=fast|balanced|deep`, а GUI-скрипты дают этот выбор через отдельный диалог перед запуском.

Живой профильный smoke на одном и том же Telegram-чате сейчас показывает такую картину:
- `fast`: `unique_members=11`, `deep_updated_total=1`, `history_backfilled_total=8`, `chat_scroll_steps_done=0`
- `deep`: `unique_members=13`, `deep_updated_total=3`, `history_backfilled_total=5`, `chat_scroll_steps_done=3`

Вывод по факту: `deep` лучше добывает новые реальные `@username`, а `fast` лучше для короткого повторного прохода по уже известной истории.

## Telegram Invite Manager

Для аккуратной работы с пользователями, которые уже дали согласие на вступление в чат, добавлен отдельный manager/state слой:

- `tools/telegram_invite_manager/`
- `scripts/telegram_invite_manager.py`
- `scripts/telegram_invite_manager_gui.sh`
- `scripts/telegram_invite_executor.py`
- `scripts/telegram_invite_executor_gui.sh`
- `docs/TELEGRAM_INVITE_MANAGER_RU.md`
- `docs/TELEGRAM_INVITE_EXECUTOR_RU.md`

Это не инструмент массового добавления пользователей. На текущем этапе он решает безопасную manager-задачу:
- импорт CSV/JSON;
- нормализация `@username`;
- хранение `invite_state.json`;
- выбор следующей пачки пользователей;
- `dry-run`;
- run-артефакты `invite_run.json` и `invite.log`;
- ручная смена статусов через CLI.

Поверх него теперь есть execution-слой для operator-assisted workflow через `site-control`:
- хранение execution-config внутри `invite_state.json`;
- `execution_plan.json` и execution-логи;
- `open-chat` через `python3 -m webcontrol browser ...`;
- запись операторских результатов обратно в state через `record`.

Пример:

```bash
cd /home/max/site-control-kit
python3 scripts/telegram_invite_manager.py init \
  --chat-url "https://web.telegram.org/k/#-2465948544" \
  --input "/home/max/telegram_invite_jobs/chat_-2465948544/users.csv"

python3 scripts/telegram_invite_manager.py run \
  --job-dir "/home/max/telegram_invite_jobs/chat_-2465948544" \
  --limit 3 \
  --dry-run

python3 scripts/telegram_invite_manager.py add-user \
  --job-dir "/home/max/telegram_invite_jobs/chat_-2465948544" \
  --chat-url "https://web.telegram.org/k/#-2465948544" \
  --username @alice_123 \
  --consent yes

python3 scripts/telegram_invite_executor.py configure \
  --job-dir "/home/max/telegram_invite_jobs/chat_-2465948544" \
  --invite-link "https://t.me/+example" \
  --url-pattern "web.telegram.org/k/#-2465948544" \
  --requires-approval

python3 scripts/telegram_invite_executor.py plan \
  --job-dir "/home/max/telegram_invite_jobs/chat_-2465948544" \
  --limit 3 \
  --reserve

python3 scripts/telegram_invite_executor.py open-chat \
  --job-dir "/home/max/telegram_invite_jobs/chat_-2465948544" \
  --dry-run
```

Видимый вход в инструмент:

```bash
cd /home/max/site-control-kit/tools/telegram_invite_manager
./bin/telegram-invite-manager --help
./bin/telegram-invite-executor --help
```

`run.json` теперь дублирует ключевую телеметрию экспортёра: `unique_members`, `members_with_username`, `chat_scroll_steps_done`, `chat_jump_scrolls_done`, `deep_updated_total`, `history_backfilled_total`, `output_usernames_cleared_total`, `chat_deep_priority_rounds`, `chat_deep_yield_stop`, а полный сырой payload лежит в `export_stats.json`.
Также в `run.json` есть признаки продвижения/сохранения latest-снимков: `latest_full_promoted`, `latest_safe_promoted`, `latest_full_best_source`, `latest_safe_best_source`.

Если Telegram Web перестал реально прокручиваться, chat-экспорт теперь завершится предупреждением `chat scroll stuck after 3 attempts`, вместо длинного пустого прогона.
Если burst всё ещё упирается в тот же DOM-слой, экспортёр включает более агрессивный `jump-scroll` и пытается перепрыгнуть дальше по истории.

После обновления файлов в `extension/` Chrome обычно требует `Reload` для unpacked extension на странице `chrome://extensions`, иначе новая логика content-script не подхватится в уже установленном расширении.

Для Linux helper теперь сначала пытается self-reload через страницу самого расширения, а если это не помогло, открывает `chrome://extensions` и жмёт Reload через X11 fallback:

```bash
cd /home/max/site-control-kit
./scripts/reload_bridge_extension.sh
```

Если геометрия окна отличается, координаты можно подстроить через env:

```bash
SCB_RELOAD_X_RATIO=0.93 SCB_RELOAD_Y_RATIO=0.17 ./scripts/reload_bridge_extension.sh
```

CLI также получил прямое X11-действие для браузерного окна:

```bash
cd /home/max/site-control-kit
PYTHONPATH="$PWD" python3 -m webcontrol browser --tab-id 614278005 x11-click --x-ratio 0.93 --y-ratio 0.17
PYTHONPATH="$PWD" python3 -m webcontrol browser --tab-id 614278005 x11-keys --sequence Tab --sequence Return
```

## Browser Observability: noVNC

Для визуального контроля браузера и ручного recovery можно поднять локальный noVNC-слой поверх X11:

```bash
cd /home/max/site-control-kit
./scripts/start_browser_novnc.sh
```

Скрипт ожидает локально установленные пакеты:
- `x11vnc`
- `websockify`
- `noVNC` web files, по умолчанию в `/usr/share/novnc`

По умолчанию noVNC слушает только `127.0.0.1:6080`, а VNC-порт проброшен только на localhost. Это не заменяет текущий browser bridge; это вспомогательный режим для наблюдения за живым браузером, ручной прокрутки и отладки нестабильных DOM-сценариев.

Остановить можно так:

```bash
cd /home/max/site-control-kit
./scripts/stop_browser_novnc.sh
```

## Архитектура

```text
CLI (sitectl) <----HTTP----> Локальный хаб (Python) <----HTTP poll----> Расширение браузера
                                                                      |
                                                                      +--> Content Script -> DOM-действия
```

Хаб — единый источник правды: клиенты, очередь команд, результаты выполнения.

## Быстрый старт

### Windows

1. Откройте PowerShell в корне проекта.
2. Установите пакет в editable-режиме:

```powershell
python -m pip install -e .
```

3. Запустите хаб:

```cmd
scripts\start_hub.cmd
```

4. В Chrome/Edge откройте `chrome://extensions` или `edge://extensions`.
5. Включите `Developer mode`.
6. Нажмите `Load unpacked`.
7. Выберите папку `C:\site-control-kit\extension`.
8. Откройте `Options` расширения и задайте:
   - `Server URL`: `http://127.0.0.1:8765`
   - `Access Token`: тот же токен, что у хаба.

### Упаковка расширения в Windows

```cmd
scripts\package_extension.cmd
```

Готовый архив: `dist\site-control-bridge-extension.zip`

### Linux/macOS

## 1) Запуск хаба

```bash
cd /home/max/site-control-kit
./scripts/start_hub.sh
```

Если `SITECTL_TOKEN` не задан, используется быстрый локальный токен:
`local-bridge-quickstart-2026`.

Важно: для реальной/удалённой эксплуатации задайте свой токен:

```bash
cd /home/max/site-control-kit
export SITECTL_TOKEN='ваш-сильный-секретный-токен'
./scripts/start_hub.sh
```

## 2) Установка расширения (без публикации в Store)
1. Откройте `chrome://extensions`.
2. Включите `Developer mode`.
3. Нажмите `Load unpacked`.
4. Выберите папку: `/home/max/site-control-kit/extension`.
5. Откройте `Options` расширения и проверьте:
- `Server URL`: `http://127.0.0.1:8765`
- `Access Token`: тот же, что у хаба.

Упаковка в zip:

```bash
cd /home/max/site-control-kit
./scripts/package_extension.sh
```

Готовый архив: `dist/site-control-bridge-extension.zip`

## 3) Проверка связи

```bash
cd /home/max/site-control-kit
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
scripts\browser.cmd fill "#email" "user@example.com"
scripts\browser.cmd text main
scripts\browser.cmd screenshot --output .\shot.png
```

Если клиент один, он выбирается автоматически. Если клиентов несколько, по умолчанию берётся самый свежий, либо можно указать `--client-id`.

CLI внутри Python-пакета:

```bash
sitectl browser status
sitectl browser open https://example.com
sitectl browser press Enter
```

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

## 5) Просмотр состояния хаба

```bash
python3 -m webcontrol state
```

## Установка CLI как команды `sitectl`

```bash
cd /home/max/site-control-kit
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
cd /home/max/site-control-kit
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
