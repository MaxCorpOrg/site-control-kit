# Инструкция для `extension`

## Назначение

MV3‑расширение получает аренды и управляет вкладками, фреймами и DOM.

## Основные файлы

`transport.js` — чистые правила долгого запроса; `background.js` — цикл,
outbox, Tab/Frame/CDP; `agent_dom.js` — локаторы; `content.js` — действия;
`manifest.json` — разрешения и версия.

## Разрешено и запрещено

Используйте общий semantic locator. Не храните единственную копию результата в
памяти service worker, не выбирайте первый неоднозначный элемент и всегда
делайте CDP detach в `finally`.

## Частые ошибки

Сон service worker, повторная регистрация listener, stale ref, недоступный
iframe, `chrome://`, CSP и два CDP attach одной вкладки.

## Проверка

`node --check` для четырёх JS‑файлов, `node --test tests/js/*.test.mjs` и
Chrome E2E.

## Что обновить

Версию manifest, heartbeat capabilities, `docs/API.md`, `docs/EXTENSION.md`,
пример и E2E.
