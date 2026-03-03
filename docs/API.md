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
  "target_client_ids": ["client-123"]
}
```

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
    "queue_sizes": {"client-123": 0},
    "commands": [...]
  }
}
```

## Поддерживаемые `command.type`

- `navigate`
  - поля: `url`
- `click`
  - поля: `selector`
- `fill`
  - поля: `selector`, `value`
- `extract_text`
  - опционально: `selector`
- `get_html`
  - опционально: `selector`
- `get_attribute`
  - поля: `selector`, `attribute`
- `wait_selector`
  - поля: `selector`, опционально `timeout_ms`, `visible_only`
- `scroll`
  - или `selector`, или координаты `x`, `y`
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
