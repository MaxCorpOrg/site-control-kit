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
- в `mention`-deep сначала пытается использовать текущий anchor/sticky avatar в чате как стабильную точку для открытия контекстного меню, и только потом откатывается к message-local селекторам;
- если задан высокий `CHAT_MIN_MEMBERS`, chat-экспорт переходит в discovery-first режим: сначала быстрее добирает новых авторов, отслеживает смену видимого слоя чата по `data-mid/data-peer-id` и при застое делает мягкий burst-скролл, а deep запускает реже, чтобы не сжечь весь runtime на первых шагах;
- парсит не только явные sender-label блоки, но и avatar-only группы сообщений, поэтому видимых участников из текущего DOM собирается больше;
- сохраняет полный последний снимок в `latest_full.md` и `latest_full.txt`;
- сохраняет безопасный снимок после identity-фильтрации в `latest_safe.md` и `latest_safe.txt`;
- сохраняет отдельный лог запуска в `runs/<timestamp>/` с `run.json`, `export.log`, `snapshot.md`, `snapshot.txt`;
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

Если Telegram Web перестал реально прокручиваться, chat-экспорт теперь завершится предупреждением `chat scroll stuck after 3 attempts`, вместо длинного пустого прогона.

После обновления файлов в `extension/` Chrome обычно требует `Reload` для unpacked extension на странице `chrome://extensions`, иначе новая логика content-script не подхватится в уже установленном расширении.

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
