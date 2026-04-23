# Диагностика проблем

## Расширение не видно в `clients`
- Проверьте, что хаб запущен.
- Проверьте URL и токен в `Options` расширения.
- В popup нажмите `Heartbeat`.

## На Linux `start-browser.sh` открывает `chrome://extensions`, но клиент не появляется автоматически
- На branded Google Chrome command-line загрузка unpacked extension может быть запрещена.
- Это не проблема хаба: Chrome игнорирует `--load-extension` и `--disable-extensions-except`.
- В таком случае загрузите `extension/` через `Load unpacked` один раз в выделенном профиле, который открыл `start-browser.sh`.
- После one-time установки используйте тот же профиль и команды `./browser.sh status`, `./browser.sh tabs`.

## Брендированный Chrome мешает, а нужен быстрый dev/debug-путь
- Используйте `./start-firefox.sh --url https://web.telegram.org/a/`.
- На обычном Firefox этот путь запускает `web-ext run` и ставит `extension/` как temporary add-on автоматически.
- На snap Firefox helper честно переводит вас в `about:debugging`, потому что `web-ext` может не достучаться до debugger port snap-сборки.
- Temporary add-on поднимается заново на каждом запуске Firefox dev-контура; это нормально для Firefox dev workflow.
- Профиль Firefox хранится отдельно в `~/.site-control-kit/firefox-profile`, поэтому Telegram cookies/session можно не терять между прогонами.
- Для snap Firefox manual шаги такие:
  - `Load Temporary Add-on`
  - выбрать `/home/max/site-control-kit/extension/manifest.json`
- Проверка та же:
  - `./browser.sh status`
  - `./browser.sh tabs`

## Telegram export не находит нужную группу, хотя Telegram открыт
- Раньше экспортёр мог смотреть только в первый клиент; теперь он ищет Telegram-вкладку по всем живым клиентам.
- Если клиентов несколько и нужен конкретный, всё равно лучше явно указать `--client-id` или `--tab-id`.
- Для подготовки профиля используйте `./start-telegram.sh`, затем повторите экспорт.

## `telegram-export.sh --source both` не открывает `Group Info -> Members`
- В текущем Telegram Web автоматическое открытие списка участников может не сработать из-за изменений DOM.
- Теперь `--source both` сначала пытается открыть `Group Info -> Members`, а если Telegram упирается, не падает жёстко: команда предупреждает и продолжает выгрузку через `chat` fallback.
- Если нужен максимально полный список, откройте `Group Info -> Members` вручную и повторите команду.

## `--source info` вернул только админов/модераторов
- В текущем Telegram Web некоторые группы в `Group Info` показывают только preview админов/модераторов/ботов, хотя hint сверху может быть `8 065 members`.
- Экспортёр теперь помечает такой режим как `info-preview` и не делает вид, что это полный список участников.
- Это не выглядит проблемой направления скролла: в живом замере на текущей группе прокрутка `вниз` и возврат `вверх` давали тот же набор из 10 peer_id.
- `chat`-режим по-прежнему собирает участников прокруткой вверх; `info`-режим использует прокрутку вниз только если Telegram реально открыл полный список `Members`.
- Для рабочего результата используйте `--source both`: он сохранит preview из `info`, а остальных активных участников доберёт из чата.

## `--force-navigate` уводит в `web.telegram.org/k/` или в корень вместо открытого чата
- Telegram Web может сначала показать список диалогов, даже если fragment URL уже правильный.
- Экспортёр теперь дополнительно проверяет, что диалог реально открыт, и при необходимости кликает по строке чата сам.
- Если info-режим собрал мало участников, это обычно не ошибка: Telegram просто подгрузил в DOM только видимую часть списка `Members`.

## `--source chat` не поднимался выше текущего экрана
- В свежем Telegram Web пропали старые `.bubbles`/`sticky_sentinel` селекторы, из-за чего chat-scroll мог застревать на `0 upward scroll steps`.
- Экспортёр переведён на новый DOM (`MessageList`, `messages-container`, `backwards-trigger`) и теперь реально листает историю вверх.
- Если нужен более широкий охват участников, увеличивайте `--chat-scroll-steps` и `--chat-max-runtime`; после этого экспортёр сам может сделать ещё несколько шагов через `--chat-auto-extra-steps`, если рост участников продолжается.
- Все новые выгрузки дополнительно складываются в `/home/max/site-control-kit/artifacts/telegram_exports`, а список путей хранится в `INDEX.md` рядом.
- `@username` больше не нужно выковыривать из markdown вручную: рядом с каждым экспортом пишутся `*_usernames.txt` и `*_usernames.json`, а их пути тоже попадают в `INDEX.md`.

## `--deep-usernames` уводил группу в личные диалоги
- Для `deep-usernames` экспортёр теперь использует временные helper tabs и возвращает активной исходную групповую вкладку.
- Если deep-проход кажется долгим, это нормально: Telegram последовательно открывает видимые профили, а не отдаёт usernames пачкой.

## Нужны просто `@username` из истории чата, без привязки к peer-card
- Используйте `python3 scripts/export_telegram_chat_mentions.py --target-count 40`.
- Этот режим собирает `@username`, которые реально встречаются в chat history/mentions, и пишет отдельные `*.txt` / `*.json` рядом с обычными Telegram export artifacts.
- Если Telegram Web листается медленно, можно запускать этот режим надолго в фоне и смотреть лог в `artifacts/telegram_exports/latest_chat_mentions_run.log`.

## Команда зависает в `pending`
- Клиент/браузер неактивен.
- Service worker «уснул» (MV3).
- Откройте popup расширения и нажмите `Опросить сейчас`.

## Ошибка `No online browser clients`
- У клиента нет свежего heartbeat.
- Проверьте `sitectl clients` или `browser.cmd status`.
- Откройте popup расширения и нажмите `Heartbeat`, затем `Опросить сейчас`.

## Команда отклонена со `status=rejected`
- Вы не указали target, а онлайн-клиентов несколько.
- Указан `client_id`, которого хаб не знает.
- Для low-level отправки используйте `--client-id`, `--client-ids` или `--broadcast`.

## Ошибка `No response from content script`
- Целевая вкладка служебная (`chrome://...`) или запрещённая для content script.
- Перезагрузите страницу и попробуйте снова.
- Убедитесь, что селектор валидный.

## Ошибка авторизации (`401 unauthorized`)
- Токен CLI/расширения не совпадает с токеном хаба.

## `navigate` работает, а `click/fill` нет
- Неверный CSS-селектор.
- Элемент внутри iframe.
- Элемент не успел появиться: используйте `wait_selector` перед `click/fill`.

## `run_script` падает из-за CSP
- На некоторых сайтах запрещён `unsafe-eval`.
- Используйте безопасные команды (`click`, `fill`, `extract_text`, `get_html`, `wait_selector`, `screenshot`) вместо `run_script`.

## Хаб «пропадает» в фоне
- В вашей среде фоновые процессы могут завершаться при окончании сессии.
- Запускайте хаб в отдельном терминале и не закрывайте его.

## Повреждён state-файл
1. Остановите хаб.
2. Сделайте бэкап `state.json`.
3. Удалите/переименуйте файл.
4. Запустите хаб — он создаст новый state автоматически.
