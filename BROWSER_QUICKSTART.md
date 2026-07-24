# Быстрый запуск управления браузером

Короткий вход в `site-control-kit` как в локальный инструмент управления браузером.

## Что Это
Инструмент состоит из трёх частей:
- локальный Python-хаб, который принимает и раздаёт команды;
- интерфейс командной строки и Windows-обёртки, через которые агент или оператор работает с браузером;
- браузерное расширение, которое исполняет команды во вкладках.

Если репозиторий открыт в рабочей папке, считайте этот инструмент основным способом управления браузером.

## Быстрый Старт

Нужно, чтобы:
- расширение Chrome или Edge уже было загружено из `extension/`;
- в настройках расширения стоял `http://127.0.0.1:8765`;
- токен расширения совпадал с токеном хаба.

Запуск из корня репозитория:

```cmd
start-hub.cmd
browser.cmd status
browser.cmd tabs
```

Если `status` показывает клиента, контур готов к работе.

## Базовые Команды

Открыть страницу:

```cmd
browser.cmd open https://example.com
browser.cmd new-tab https://example.com
```

Клик, ввод, фокус, клавиши:

```cmd
browser.cmd click "button[type='submit']"
browser.cmd fill "#email" "user@example.com"
browser.cmd focus "#search"
browser.cmd press Enter
```

Чтение данных страницы:

```cmd
browser.cmd page-url
browser.cmd text body
browser.cmd html main
browser.cmd attr "a.login" href
browser.cmd snapshot
```

Для ИИ-агента предпочтителен `snapshot`: он возвращает компактные строки и
устойчивые ссылки вида `e1`, `e2` вместо полного HTML. После снимка можно
действовать по ссылке или семантике:

```cmd
browser.cmd smart-click --role button --name "Войти" --exact
browser.cmd set-text "user@example.com" --label "Email" --exact
browser.cmd wait-for --text "Готово" --state visible
browser.cmd smart-click --ref e7
```

Доступные локаторы: `--selector`, `--ref`, `--role` с опциональным `--name`,
`--text`, `--label`, `--placeholder`, `--test-id`. Если совпадение не
единственное, уточните локатор через `--exact`, `--nth` или
`--root-selector`.

Ожидание и прокрутка:

```cmd
browser.cmd wait "#app"
browser.cmd scroll --selector "#footer"
browser.cmd scroll-by --dy 1200
```

Запасной путь X11 для системных страниц и окон без сценария страницы:

```cmd
browser.cmd --tab-id 150000238 x11-click --x-ratio 0.93 --y-ratio 0.17
browser.cmd --tab-id 150000238 x11-keys --sequence Tab --sequence Return
```

Скриншот:

```cmd
browser.cmd screenshot --output .\dist\shot.png
browser.cmd --tab-id 150000238 screenshot --full-page --output .\dist\full.png
```

Запуск JavaScript на странице:

```cmd
browser.cmd js "return { title: document.title, href: location.href };"
```

## Выбор Клиента И Вкладки

По умолчанию инструмент:
- берёт самый свежий подключённый браузерный клиент;
- работает с активной вкладкой, если не задано иное.

Работа по URL-фрагменту:

```cmd
browser.cmd --url-pattern example.com text h1
```

Работа по `tab_id`:

```cmd
browser.cmd --tab-id 150000238 screenshot --output .\dist\tab.png
```

Работа по `client_id`:

```cmd
browser.cmd --client-id client-REPLACE tabs
```

## Как Должен Работать Агент

Перед реальной задачей:
1. Запустить `start-hub.cmd`, если хаб ещё не работает.
2. Проверить `browser.cmd status`.
3. Проверить `browser.cmd tabs`.
4. Только после этого выполнять рабочие действия.

Рекомендуемый цикл агента:

1. Зафиксировать `client_id` и `tab_id`.
2. Выполнить `browser.cmd snapshot`.
3. Выбрать уникальную ссылку или семантический локатор.
4. Использовать `smart-click` / `set-text` / `wait-for`.
5. После перехода на новый документ взять новый снимок.

Машиночитаемый контракт доступен через:

```cmd
browser.cmd schema
```

Если что-то не работает:
1. Перезагрузить расширение.
2. Снова проверить `browser.cmd status`.
3. Проверить, что токен и URL в настройках расширения совпадают с хабом.

Для перезагрузки распакованного расширения в Linux есть помощник с двумя стратегиями:
- сначала самостоятельная перезагрузка через `chrome-extension://.../options.html?action=reload-self`;
- если это не помогло, запасной путь через `chrome://extensions` и `x11-click`.
- успех засчитывается только после нового сигнала активности, полученного после перезагрузки, с
  непустым `content_commands`;
- старые возможности из сохранённого состояния хаба больше не считаются
  подтверждением успешной перезагрузки.

Запуск:

```bash
cd /home/max/site-control-kit
./scripts/reload_bridge_extension.sh
```

Если запасная кнопка `Reload` («Перезагрузить») в вашей сборке Chrome сдвинута, можно подстроить координаты:

```bash
SCB_RELOAD_X_RATIO=0.93 SCB_RELOAD_Y_RATIO=0.17 ./scripts/reload_bridge_extension.sh
```

Допустимый возраст подтверждающего сигнала активности по умолчанию равен 5 секундам.
Для медленной машины его можно увеличить явно:

```bash
SCB_MAX_HEARTBEAT_AGE_SEC=10 ./scripts/reload_bridge_extension.sh
```

Если ни самостоятельная перезагрузка, ни запасной путь не дали свежий сигнал активности, помощник завершается с
ненулевым кодом.

## Ограничения
- `chrome://*` и похожие системные страницы недоступны для сценария страницы.
- `run_script` может блокироваться CSP конкретного сайта.
- ссылки живут в пределах текущего документа; после навигации нужен новый снимок.
- схема версии 1 работает в верхнем фрейме и видит открытые Shadow DOM; ссылки
  с учётом фреймов запланированы отдельно.
- После обновления расширения всегда сначала делайте `browser.cmd status`.

## Что Обновлять При Изменениях
- `docs/API.md` — если меняется протокол или данные команд.
- `docs/EXTENSION.md` — если меняются возможности фонового процесса или сценария страницы.
- `docs/ARCHITECTURE.md` — если меняется поток команд или маршрутизация.
- `examples/` — если добавляются новые команды.
- `AGENTS.md` и `docs/AI_MAINTAINER_GUIDE.md` — если меняется работа агента.

## Связанный помощник Telegram

Для профилей Telegram Desktop в Linux с `tdata.zip` есть отдельный помощник:

```bash
cd /home/max/site-control-kit
python3 scripts/telegram_portable.py import-zip --zip "/path/to/tdata.zip" --profile-name "ak" --launch
```

Есть и графическая обёртка:

```bash
cd /home/max/site-control-kit
./scripts/telegram_portable_gui.sh
```

Если профиль уже существует, его можно принять в управление и проверить, что он запущен:

```bash
python3 scripts/telegram_portable.py adopt \
  --profile-dir "/home/max/TelegramPortableAK" \
  --profile-name "AK" \
  --account-username "@M_a_g_g_i_e"

python3 scripts/telegram_portable.py status \
  --profile-dir "/home/max/TelegramPortableAK"

python3 scripts/telegram_portable.py log-diagnose \
  --profile-dir "/home/max/TelegramPortableAK"

python3 scripts/telegram_portable.py accessibility-dump \
  --profile-dir "/home/max/TelegramPortableAK" \
  --query "Info" \
  --role "push button" \
  --match-mode exact \
  --visible-only
```

Для приглашений согласованных пользователей через этот переносимый профиль используйте исполнитель, а не ручную сборку команд:

```bash
python3 scripts/telegram_invite_executor.py ensure-portable \
  --job-dir "/home/max/telegram_invite_jobs/chat_Zhirotop_shop"

python3 scripts/telegram_invite_executor.py prepare-next \
  --job-dir "/home/max/telegram_invite_jobs/chat_Zhirotop_shop" \
  --username "@USERNAME" \
  --consent yes \
  --launch-if-needed

python3 scripts/telegram_invite_executor.py desktop-send-link \
  --job-dir "/home/max/telegram_invite_jobs/chat_Zhirotop_shop" \
  --username "@USERNAME" \
  --dry-run

python3 scripts/telegram_invite_executor.py desktop-open-add-members \
  --job-dir "/home/max/telegram_invite_jobs/chat_Zhirotop_shop" \
  --username "@USERNAME" \
  --no-type-search \
  --dry-run

python3 scripts/telegram_portable.py press-keys \
  --profile-dir "/home/max/TelegramPortableAK" \
  --sequence "Control_L+f" \
  --dry-run

python3 scripts/telegram_portable.py window-screenshot \
  --profile-dir "/home/max/TelegramPortableAK" \
  --output /tmp/tg_window.png
```

Реальная отправка через переносимый Telegram Desktop требует отдельного `--confirm-send`; запись статуса `sent` требует `--record-result`.

## Единая платформа инструментов

Если нужно увидеть встроенные и внешние инструменты Telegram в одном месте, используйте платформенный слой на основе реестра:

```bash
cd /home/max/site-control-kit/tools/telegram

cat README_RU.md
cd /home/max/site-control-kit/tools/telegram/platform

./bin/tool-platform validate-registry
./bin/tool-platform list-tools
./bin/tool-platform-panel
```

Сейчас эта панель уже подхватывает:
- встроенный `telegram_invite_manager`;
- встроенный `telegram_portable_helper`;
- встроенный `telegram_export`;
- внешний `/home/max/telegram-portable-session-tool`.
