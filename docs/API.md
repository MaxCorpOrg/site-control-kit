# API и протокол команд

Базовый URL: `http://127.0.0.1:8765`

## Аутентификация
Поддерживаются заголовки:
- `X-Access-Token: <token>`
- `Authorization: Bearer <token>`

Быстрый локальный токен по умолчанию:
- `local-bridge-quickstart-2026`

Все `/api/*` endpoints требуют токен.

## Health

`GET /health`

Ответ:
```json
{ "ok": true, "service": "site-control-hub", "version": "0.1" }
```

## Клиенты

## `POST /api/clients/heartbeat`
Запрашивается расширением.

Пример запроса:
```json
{
  "client_id": "client-123",
  "extension_version": "0.1.0",
  "user_agent": "...",
  "tabs": [
    { "id": 12, "windowId": 1, "active": true, "title": "...", "url": "https://..." }
  ],
  "meta": { "extension": "site-control-bridge", "platform": "Linux" }
}
```

Ответ:
```json
{ "ok": true, "client": { "client_id": "client-123", "last_seen": "..." } }
```

## `GET /api/clients`
Ответ:
```json
{ "ok": true, "clients": [ ... ] }
```

Каждый клиент может содержать служебное поле:
- `is_online` — есть ли свежий heartbeat и можно ли безопасно использовать клиента по умолчанию.

## Telegram webhook

## `POST /api/telegram/webhook`
Принимает Telegram Bot API update и сохраняет identity пользователя из `message.from` или `callback_query.from`.

Сохраняемые поля:
- `telegram_id = from.id`
- `username = from.username ? "@<username>" : null`

Повторный update для того же `telegram_id` делает upsert и обновляет `username`, если пользователь сменил его или удалил.

Пример запроса:
```json
{
  "update_id": 1,
  "message": {
    "message_id": 10,
    "from": { "id": 123456, "username": "alice" },
    "text": "/start"
  }
}
```

Ответ:
```json
{
  "ok": true,
  "source": "message.from",
  "telegram_user": {
    "telegram_id": 123456,
    "username": "@alice",
    "created_at": "...",
    "updated_at": "...",
    "changed": true
  }
}
```

## Команды

## `POST /api/commands`
Создаёт команду и ставит в очередь.

Пример запроса:
```json
{
  "issued_by": "cli",
  "timeout_ms": 20000,
  "target": {
    "client_id": "client-123",
    "tab_id": 12,
    "url_pattern": "example.com",
    "active": true,
    "broadcast": false,
    "client_ids": ["client-a", "client-b"]
  },
  "command": {
    "type": "click",
    "selector": "button.submit"
  }
}
```

Ответ:
```json
{
  "ok": true,
  "command_id": "uuid",
  "status": "pending",
  "target_client_ids": ["client-123"],
  "error": null
}
```

Правила target:
- `client_id` — отправить одному известному клиенту;
- `client_ids` — отправить известным клиентам из списка;
- `broadcast=true` — отправить всем известным клиентам;
- если target не задан и онлайн-клиент ровно один, команда будет направлена ему автоматически;
- если target не задан и онлайн-клиентов несколько, команда будет отклонена со `status: "rejected"`.

## `GET /api/commands/next?client_id=<id>`
Выдаёт следующую команду клиенту.

Ответ с командой:
```json
{
  "ok": true,
  "command": {
    "id": "uuid",
    "created_at": "...",
    "timeout_ms": 20000,
    "target": { "client_id": "client-123" },
    "command": { "type": "click", "selector": "button" }
  }
}
```

Если команд нет:
```json
{ "ok": true, "command": null }
```

## `POST /api/commands/{id}/result`
Расширение отправляет результат выполнения.

Пример запроса:
```json
{
  "client_id": "client-123",
  "ok": true,
  "status": "completed",
  "data": { "text": "..." },
  "error": null,
  "logs": []
}
```

Ответ:
```json
{ "ok": true, "command": { "id": "...", "status": "completed", "deliveries": { ... } } }
```

## `GET /api/commands/{id}`
Получить полную карточку команды.

## `POST /api/commands/{id}/cancel`
Отмена команды (активные доставки переводятся в `cancelled`).

## Снимок состояния

## `GET /api/state`
```json
{
  "ok": true,
  "state": {
    "version": 1,
    "clients": [...],
    "telegram_users": {"123456": {"telegram_id": 123456, "username": "@alice"}},
    "queue_sizes": {"client-123": 0},
    "commands": [...]
  }
}
```

## Поддерживаемые `command.type`

- `navigate`
  - поля: `url`
- `new_tab`
  - поля: `url`, опционально `active`
- `click`
  - поля: `selector`
- `context_click`
  - поля: `selector`
- `click_text`
  - поля: `text`, опционально `root_selector`, `near_last_context`
- `telegram_sticky_author`
  - поля: опционально `expected_peer_id`, `click`, `context_click`
  - возвращает нижний sticky author avatar Telegram Web: `peer_id`, `name`, `role`, `username`, `source`, `point`, `rect`, `candidates`
  - `context_click=true` открывает context menu правой кнопкой только на большой 34px avatar, найденной нижней `elementsFromPoint`-пробой; fallback на текст сообщения для клика не используется
  - если `expected_peer_id` задан и такой нижней point-avatar сейчас нет, команда возвращает `found=false`, чтобы exporter не кликал не туда
- `clear_editable`
  - поля: `selectors` — массив CSS-селекторов, проверяемых по очереди
- `fill`
  - поля: `selector`, `value`
- `focus`
  - поля: `selector`
- `extract_text`
  - опционально: `selector`
- `get_html`
  - опционально: `selector`
- `get_page_url`
  - без обязательных полей
- `get_attribute`
  - поля: `selector`, `attribute`
- `wait_selector`
  - поля: `selector`, опционально `timeout_ms`, `visible_only`
- `scroll`
  - или `selector`, или координаты `x`, `y`
- `scroll_by`
  - поля: `delta_x`, `delta_y`, опционально `selector`
- `back`
  - без обязательных полей
- `forward`
  - без обязательных полей
- `reload`
  - опционально: `ignore_cache`
- `activate_tab`
  - без обязательных полей
- `close_tab`
  - без обязательных полей
- `press_key`
  - поля: `key`, опционально `selector`, `ctrl`, `alt`, `shift`, `meta`
- `run_script`
  - поля: `script`, опционально `args`
- `screenshot`
  - без обязательных полей

## Контракт результата
Расширение возвращает:
- `ok` — boolean
- `status` — обычно `completed` или `failed`
- `data` — полезные данные
- `error` — ошибка (если есть)
- `logs` — массив строк (опционально)
