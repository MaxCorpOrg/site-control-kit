# Browser Quickstart

Короткий вход в `site-control-kit` как в локальный инструмент управления браузером.

## Что Это
Инструмент состоит из трёх частей:
- локальный Python-хаб, который принимает и раздаёт команды;
- CLI и Windows-обёртки, через которые агент или оператор работает с браузером;
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

Для Linux есть единый запускной вход:

```bash
cd /home/max/site-control-kit
./start-browser.sh
./browser.sh status
./browser.sh tabs
```

Скрипт `start-browser.sh` сам поднимет хаб и попытается запустить совместимый браузерный клиент.

## Базовые Команды

Открыть страницу:

```cmd
browser.cmd open https://example.com
browser.cmd new-tab https://example.com
```

Клик, ввод, фокус, клавиши:

```cmd
browser.cmd click "button[type='submit']"
browser.cmd context-click ".item"
browser.cmd clear "#editable-message-text"
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
```

Ожидание и прокрутка:

```cmd
browser.cmd wait "#app"
browser.cmd scroll --selector "#footer"
browser.cmd scroll-by --dy 1200
```

Скриншот:

```cmd
browser.cmd screenshot --output .\dist\shot.png
```

Запуск JavaScript на странице:

```cmd
browser.cmd js "return { title: document.title, href: location.href };"
```

## Выбор Клиента И Вкладки

По умолчанию инструмент:
- берёт самый свежий онлайн браузерный клиент;
- работает с активной вкладкой, если не задано иное.

Если онлайн-клиентов несколько и вы работаете через low-level `send`, лучше всегда указывать `--client-id` или `--broadcast`. Без явного target команда будет автоматически направлена только когда онлайн-клиент ровно один.

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

Если что-то не работает:
1. Перезагрузить расширение.
2. Снова проверить `browser.cmd status`.
3. Проверить, что токен и URL в настройках расширения совпадают с хабом.

Если на Linux доступен только branded `google-chrome`, учтите:
1. current Chrome builds могут игнорировать `--load-extension` и `--disable-extensions-except`;
2. в этом случае `./start-browser.sh` откроет выделенный профиль на `chrome://extensions`;
3. unpacked extension нужно загрузить один раз вручную из папки `extension/`;
4. после этого дальше можно работать обычными командами `./browser.sh ...`.

## Ограничения
- `chrome://*` и похожие системные страницы недоступны для content script.
- `run_script` может блокироваться CSP конкретного сайта.
- После обновления расширения всегда сначала делайте `browser.cmd status`.

## Что Обновлять При Изменениях
- `docs/API.md` — если меняется протокол или payload команд.
- `docs/EXTENSION.md` — если меняются background/content возможности.
- `docs/ARCHITECTURE.md` — если меняется поток команд или маршрутизация.
- `examples/` — если добавляются новые команды.
- `AGENTS.md` и `docs/AI_MAINTAINER_GUIDE.md` — если меняется агентный workflow.
