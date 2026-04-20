# Расширение браузера (внутреннее устройство)

## Файлы
- `manifest.json` — манифест, разрешения, точки входа.
- `background.js` — heartbeat, polling, маршрутизация команд, отправка результатов.
- `content.js` — выполнение команд над DOM.
- `options.*` — страница настроек.
- `popup.*` — оперативная диагностика и ручные кнопки (`Опросить сейчас`, `Heartbeat`).

## Пути выполнения

## 1) Команды, выполняемые в background
- `navigate`
- `new_tab`
- `reload`
- `activate_tab`
- `close_tab`
- `screenshot`

## 2) Команды через content script
`background` отправляет сообщение во вкладку:
```js
{ type: "site-control-command", command: { ... } }
```

`content.js` отвечает:
```js
{ ok: true, data: {...} }
```
или
```js
{ ok: false, error: {...} }
```

Ключевые DOM-команды:
- `click`, `click_text`, `fill`, `focus`
- `extract_text`, `get_html`, `get_attribute`, `get_page_url`
- `wait_selector`, `scroll`, `scroll_by`
- `back`, `forward`, `press_key`, `run_script`

## Логика выбора вкладки
1. `target.tab_id`
2. `target.url_pattern`
3. активная вкладка текущего окна
4. первая доступная вкладка

## Режимы опроса
- Частый `setInterval`.
- Резервный `chrome.alarms` (на случай «засыпания» worker).

## Что хранится в `chrome.storage.local`
- `serverUrl`
- `token`
- `clientId`
- `pollIntervalMs`
- `heartbeatIntervalMs`
- служебные поля диагностики (`lastPollAt`, `lastHeartbeatAt`, `lastCommand...`)

## Heartbeat meta
В heartbeat расширение отправляет не только `extension_version`, но и `meta.capabilities`:
- `background_commands` — что умеет service worker без content script;
- `content_commands` — что умеет DOM-слой.

Это нужно для диагностики stale runtime: когда браузер работает на старой загруженной версии расширения, а код в репозитории уже ушёл вперёд.

## Ограничения MV3
- Service worker непостоянный.
- На страницах `chrome://*` и ряде служебных URL content script не работает.
- Некоторые сайты блокируют `run_script` через CSP (`unsafe-eval` запрещён).

## Замечание по `click_text`
`click_text` ищет текст не только на parent menu-item, но и на вложенных text-span узлах, а затем поднимается к ближайшему кликабельному предку.
Это важно для Telegram Web и похожих UI, где видимый текст лежит в `.btn-menu-item-text`, а кликабельный контейнер — выше по DOM.

## Как добавить новую команду
1. Обновить схему/описание в `docs/API.md`.
2. Реализовать в `content.js` или `background.js`.
3. Сохранить единый формат ошибок (`message`, опционально `stack`/`hint`).
4. Добавить пример payload в `examples/`.
