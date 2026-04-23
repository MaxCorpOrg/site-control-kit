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

### Быстрый запуск рабочего контура на Linux

Если нужен один вход в рабочий контур, используйте:

```bash
cd /home/max/site-control-kit
./start-browser.sh
```

Что делает скрипт:
- поднимает хаб автоматически, если он ещё не запущен;
- предпочитает Chromium-совместимый браузер, где можно загрузить unpacked extension флагами;
- если доступен только branded `google-chrome`, открывает выделенный профиль и даёт one-time шаги для ручной загрузки `extension/`.

Если branded Chrome мешает, есть отдельный Firefox dev-path:

```bash
cd /home/max/site-control-kit
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
cd /home/max/site-control-kit
./browser.sh status
./browser.sh tabs
./browser.sh open https://example.com
```

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
cd /home/max/site-control-kit
./start-telegram.sh
```

Firefox-вариант для Telegram:

```bash
cd /home/max/site-control-kit
./start-telegram-firefox.sh
```

Что делает этот запуск:
- поднимает хаб;
- открывает браузерный профиль на `web.telegram.org`;
- если bridge-клиента ещё нет, Telegram export-скрипты сами попытаются открыть этот профиль повторно.

CLI-экспорт:

```bash
cd /home/max/site-control-kit
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
- каждый экспорт дополнительно архивируется в [artifacts/telegram_exports](/home/max/site-control-kit/artifacts/telegram_exports) и записывается в индекс [INDEX.md](/home/max/site-control-kit/artifacts/telegram_exports/INDEX.md);
- рядом с каждым экспортом теперь автоматически пишутся отдельные sidecar-файлы `*_usernames.txt` и `*_usernames.json`, чтобы собранные `@username` можно было брать без парсинга markdown-таблицы;
- `--deep-usernames` больше не должен уводить основную групповую вкладку в личные диалоги: usernames дочитываются через временные helper tabs;
- `--deep-usernames` в `info`-режиме может работать заметно дольше обычного запуска, потому что Telegram последовательно открывает видимые профили;
- для максимально полного списка участников всё равно лучше вручную открыть `Group Info -> Members` перед повторным запуском.

GUI-экспорт:

```bash
cd /home/max/site-control-kit
./scripts/telegram_members_export_app.sh
```

Быстрый сбор именно `@username`, встречающихся в chat history/mentions:

```bash
cd /home/max/site-control-kit
python3 scripts/export_telegram_chat_mentions.py --target-count 40
```

Этот режим не пытается привязать username к карточке участника. Он просто листает историю чата и сохраняет найденные `@username` в `*.txt` / `*.json`.

Разовый CLI-сценарий для chat-mode:

```bash
cd /home/max/site-control-kit
./scripts/run_chat_export_once.sh "$SITECTL_TOKEN"
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
cd /home/max/site-control-kit
./scripts/verify.sh
```

Если уже есть живой браузерный клиент и нужно прогнать live smoke:

```bash
cd /home/max/site-control-kit
./scripts/verify.sh --live-browser
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
