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
- `click`, `context_click`, `click_text`, `clear_editable`, `fill`, `focus`
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

## Ограничения MV3
- Service worker непостоянный.
- На страницах `chrome://*` и ряде служебных URL content script не работает.
- Некоторые сайты блокируют `run_script` через CSP (`unsafe-eval` запрещён).

## Как добавить новую команду
1. Обновить схему/описание в `docs/API.md`.
2. Реализовать в `content.js` или `background.js`.
3. Сохранить единый формат ошибок (`message`, опционально `stack`/`hint`).
4. Добавить пример payload в `examples/`.
