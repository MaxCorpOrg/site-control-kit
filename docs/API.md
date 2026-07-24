# API и протокол браузерного ядра

Базовый адрес по умолчанию: `http://127.0.0.1:8765`.

Версия протокола: `2.0`.

Версия агентного API: `1.1`.

Версия расширения: `0.2.0`.

## Общие правила

Все маршруты `/api/*` требуют токен в одном из заголовков:

```http
X-Access-Token: <token>
```

или:

```http
Authorization: Bearer <token>
```

Токен в URL или теле JSON запрещён. Хаб вернёт соответственно
`token_in_url_forbidden` или `token_in_body_forbidden`. Заголовок `Origin`
проверяется по списку разрешённых источников.

Успешный ответ всегда содержит `"ok": true`. Ошибка содержит:

```json
{
  "ok": false,
  "error": "понятное описание",
  "error_code": "стабильный_машинный_код"
}
```

## Состояния доставки

Одна команда может иметь несколько доставок — по одной на браузерный клиент.
Жизненный цикл доставки:

```text
queued -> leased -> acknowledged -> running
   |          |            |           |
   +----------+------------+-----------+--> completed
                                      +--> failed
                                      +--> cancelled
                                      +--> expired
                                      +--> dead_letter
```

Пояснения:

- `queued` — стоит в очереди;
- `leased` — временно выдана расширению в аренду;
- `acknowledged` — расширение подтвердило получение;
- `running` — действие началось;
- `completed` — результат принят;
- `failed` — расширение вернуло ошибку;
- `expired` — истёк срок команды;
- `dead_letter` — безопасный автоматический повтор невозможен;
- `cancelled` — команда отменена.

Для доставки используются четыре разных идентификатора:

- `command_id` — постоянный идентификатор команды;
- `delivery_id` — постоянный идентификатор доставки одному клиенту;
- `lease_token` — одноразовый токен текущей аренды;
- `idempotency_key` — ключ идемпотентности, защищающий от повторной постановки
  одинаковой команды.

Старый результат без `delivery_id` и `lease_token` временно принимается только
при наличии активной аренды. В принятом результате это видно по
`legacy_delivery_identifiers: true`.

## Политики повторов

- `never_retry` — никогда не повторять автоматически;
- `retry_if_not_started` — повторять, только если действие не дошло до
  `running`;
- `retry_with_verification` — повторять после внешней проверки постусловия;
- `safe_retry` — безопасный повтор чтения или ожидания.

По умолчанию чтение получает `safe_retry`, ввод текста —
`retry_if_not_started`, опасные действия — `never_retry`.

Если аренда опасного действия истекла после `running`, доставка переходит в
`dead_letter`: хаб не рискует выполнить клик или отправку формы второй раз.
Результат со старым `lease_token` получает HTTP `409` и код `stale_lease`.

## Служебные маршруты

### `GET /health`

Не требует токен.

```json
{
  "ok": true,
  "service": "site-control-hub",
  "version": "0.1"
}
```

### `GET /api/agent/schema`

Возвращает машиночитаемую схему агентного API: версии, маршруты, состояния,
локаторы, ожидания и новые типы команд.

### `GET /api/state`

Возвращает диагностическое представление клиентов, очередей, команд, сессий и
блокировок. Источником правды является SQLite; `state.json` остаётся удобным
для ручного чтения зеркалом.

### `GET /api/storage/journal?limit=100`

Возвращает хвост журнала переходов состояния.

### `POST /api/storage/backup`

Создаёт согласованную резервную копию SQLite.

```json
{
  "destination": "необязательный/путь/к/копии.sqlite3"
}
```

Если путь не передан, хаб создаёт имя рядом с рабочей базой.

## Браузерные клиенты

### `POST /api/clients/heartbeat`

Расширение сообщает, что оно живо, перечисляет вкладки и возможности:

```json
{
  "client_id": "client-123",
  "extension_version": "0.2.0",
  "user_agent": "Mozilla/5.0 ...",
  "tabs": [
    {
      "id": 12,
      "windowId": 1,
      "active": true,
      "title": "Пример",
      "url": "https://example.com/"
    }
  ],
  "meta": {
    "extension": "site-control-bridge",
    "protocol_version": "2.0",
    "capabilities": ["delivery_ack", "sessions", "iframes", "semantic_snapshot"]
  }
}
```

### `GET /api/clients`

Возвращает все известные клиенты. Поле `is_online` означает, что heartbeat
достаточно свежий для безопасного автовыбора.

## Постановка и доставка команды

### `POST /api/commands`

```json
{
  "issued_by": "agent-1",
  "session_id": "необязательный-uuid",
  "idempotency_key": "уникальный-ключ-операции",
  "retry_policy": "safe_retry",
  "timeout_ms": 20000,
  "lease_duration_ms": 60000,
  "max_attempts": 3,
  "confirmation": {
    "confirmed": true,
    "reason": "оператор подтвердил отправку"
  },
  "target": {
    "client_id": "client-123",
    "tab_id": 12
  },
  "command": {
    "type": "snapshot",
    "include_frames": true
  }
}
```

Правила цели:

- `client_id` — один клиент;
- `client_ids` — список клиентов;
- `broadcast: true` — все известные клиенты;
- без цели хаб выбирает единственный онлайн-клиент;
- при нескольких онлайн-клиентах неявный выбор отклоняется.

Команда внутри сессии обязана явно задавать один `client_id` и `tab_id`.
Сессия должна владеть блокировкой этой вкладки.

Повтор того же `idempotency_key` с тем же отпечатком возвращает существующую
команду и `idempotency_reused: true`. Другой payload с тем же ключом получает
HTTP `409` и `idempotency_conflict`.

### `GET /api/commands/next?client_id=<id>`

Расширение получает аренду следующей команды:

```json
{
  "ok": true,
  "command": {
    "id": "command-uuid",
    "delivery_id": "delivery-uuid",
    "lease_token": "одноразовый-токен",
    "attempt_number": 1,
    "lease_expires_at": "2026-07-24T09:00:00+00:00",
    "session_id": "session-uuid",
    "target": {
      "client_id": "client-123",
      "tab_id": 12
    },
    "command": {
      "type": "snapshot"
    }
  }
}
```

Пустая очередь возвращает `"command": null`.

### `POST /api/commands/{command_id}/ack`

Подтверждает получение аренды:

```json
{
  "client_id": "client-123",
  "delivery_id": "delivery-uuid",
  "lease_token": "одноразовый-токен"
}
```

### `POST /api/commands/{command_id}/status`

Расширение сообщает о начале выполнения:

```json
{
  "client_id": "client-123",
  "delivery_id": "delivery-uuid",
  "lease_token": "одноразовый-токен",
  "status": "running",
  "reason": "browser_action_started"
}
```

### `POST /api/commands/{command_id}/result`

```json
{
  "client_id": "client-123",
  "delivery_id": "delivery-uuid",
  "lease_token": "одноразовый-токен",
  "result_id": "result-uuid",
  "finished_at": "2026-07-24T09:00:01Z",
  "ok": true,
  "status": "completed",
  "data": {
    "text": "результат"
  },
  "error": null,
  "logs": [],
  "diagnostics": {
    "console_tail": [],
    "network_errors": []
  }
}
```

Повтор полностью одинакового результата безопасен. Другой терминальный
результат для уже завершённой доставки получает HTTP `409` и
`result_conflict`.

### `GET /api/commands/{command_id}`

Возвращает карточку команды со всеми доставками, переходами, попытками и
результатами.

### `POST /api/commands/{command_id}/cancel`

Переводит незавершённые доставки в `cancelled`.

## Сессии и блокировки вкладок

Сессия связывает владельца, браузерный клиент, политику безопасности,
блокировки вкладок и артефакты одного сценария.

### `POST /api/sessions`

```json
{
  "owner_id": "agent-1",
  "client_id": "client-123",
  "ttl_seconds": 300,
  "policy": {
    "allowed_domains": ["example.com"],
    "denied_domains": [],
    "read_only": false,
    "allow_input": true,
    "allow_file_upload": false,
    "allow_form_submit": false,
    "allow_download": false,
    "allow_cdp": false,
    "max_tabs": 3,
    "max_session_duration_seconds": 900,
    "require_dangerous_confirmation": true,
    "capture_screenshots": true,
    "capture_console": false,
    "capture_network": false,
    "capture_har": false,
    "capture_trace": false,
    "capture_video": false,
    "secrets": ["строка-для-маскирования"]
  }
}
```

CDP — Chrome DevTools Protocol, протокол инструментов разработчика Chrome.
Захват консоли, сети, HAR и трассировки требует `allow_cdp: true`.
Поля HAR, trace и video зарезервированы политикой, но полноценная запись этих
форматов ещё не реализована.

### `GET /api/sessions`

Возвращает список сессий.

### `GET /api/sessions/{session_id}`

Возвращает одну сессию.

### `POST /api/sessions/{session_id}/heartbeat`

Продлевает срок жизни сессии и её блокировок.

### `POST /api/sessions/{session_id}/close`

```json
{
  "reason": "scenario_finished"
}
```

Закрывает сессию и освобождает её блокировки.

### `POST /api/sessions/{session_id}/locks`

```json
{
  "client_id": "client-123",
  "tab_id": 12,
  "lock_mode": "exclusive"
}
```

Режимы:

- `exclusive` — только эта сессия;
- `shared_read` — несколько сессий могут читать, изменение запрещено;
- `operator_override` — явный операторский перехват с записью события.

### `POST /api/sessions/{session_id}/locks/release`

```json
{
  "client_id": "client-123",
  "tab_id": 12
}
```

## Семантический снимок и локаторы

Команда `snapshot` возвращает краткое представление доступных элементов:

```json
{
  "type": "snapshot",
  "include_frames": true,
  "include_hidden": false,
  "limit": 200
}
```

Элемент содержит `ref`, `frame_id`, `role`, доступное имя `name`, `value`,
`placeholder`, видимость, доступность и редактируемость. Ссылка имеет вид
`f3:e7`: первая часть задаёт фрейм, вторая — элемент.

Стратегии локатора:

- `ref` — ссылка из снимка;
- `role` — семантическая роль и необязательное доступное имя;
- `label` — подпись поля;
- `placeholder` — подсказка поля;
- `test_id` — `data-testid`, `data-test-id` или `data-test`;
- `text` — текст;
- `css` — CSS-селектор как низкоуровневый запасной путь.

Общие поля:

```json
{
  "strategy": "role",
  "value": "button",
  "name": "Сохранить",
  "exact": true,
  "nth": 0,
  "root_selector": "#dialog",
  "frame_id": 3
}
```

`nth` применяется только явно. Неоднозначный локатор завершается ошибкой
`ambiguous_match` с количеством и кратким списком кандидатов.

Если элемент по `ref` был заменён в DOM, расширение ищет единственного
кандидата по `id`, тестовому идентификатору, роли и имени или `placeholder`.
Неоднозначное восстановление запрещено.

Открытые Shadow DOM поддерживаются. Закрытый Shadow DOM через обычные
DOM-команды недоступен.

## Агентные DOM-команды

### `smart_click`

```json
{
  "type": "smart_click",
  "locator": {
    "strategy": "role",
    "value": "button",
    "name": "Сохранить",
    "exact": true
  },
  "timeout_ms": 10000,
  "proof": {
    "expected_text": "Готово",
    "expected_url": "https://example.com/done",
    "timeout_ms": 5000
  }
}
```

До клика проверяются наличие, видимость, доступность, стабильность и
возможность получить событие. Поле `proof` задаёт проверку результата.

### `set_editable_text`

```json
{
  "type": "set_editable_text",
  "locator": {
    "strategy": "label",
    "value": "Имя"
  },
  "value": "Анна"
}
```

Использует нативный setter значения и события `input`/`change`, поэтому
совместим с контролируемыми полями React и похожих библиотек.

### `wait_for`

```json
{
  "type": "wait_for",
  "locator": {
    "strategy": "text",
    "value": "Готово",
    "exact": true
  },
  "state": "visible",
  "timeout_ms": 10000
}
```

Состояния: `attached`, `detached`, `visible`, `hidden`, `enabled`, `editable`,
`stable`, `actionable`, `text`, `value`.

### Выбор фрейма

`frame_id` берётся из снимка. Для прямого выбора также поддерживаются:

- точный идентификатор `frame_id`;
- подстрока URL;
- имя фрейма;
- CSS-селектор элемента `iframe` в родительском документе.

Работают вложенные и кросс-доменные iframe, если URL фрейма разрешён
`host_permissions` расширения.

## Фоновые команды

- `navigate`: `url`, необязательные ожидания;
- `new_tab`: `url`, `active`, ожидания;
- `reload`: `ignore_cache`;
- `activate_tab`;
- `close_tab`;
- `screenshot`: `full_page`;
- `set_file_input_files`: установка файлов через CDP.

Для навигации можно ждать загрузку документа, совпадение URL, тишину DOM,
сетевой покой или исчезновение индикатора загрузки. CDP‑ожидания требуют
разрешения сессии.

## Совместимые старые команды

Сохранены существующие CSS-команды:

- `click`, `context_click`, `click_text`, `click_menu_text`;
- `clear_editable`, `fill`, `focus`, `upload_file`;
- `extract_text`, `get_html`, `get_attribute`, `get_page_url`;
- `wait_selector`, `scroll`, `scroll_by`, `wheel`;
- `back`, `forward`, `press_key`, `run_script`;
- `telegram_sticky_author`.

Они нужны для обратной совместимости, но новым агентным сценариям следует
использовать `snapshot`, `smart_click`, `set_editable_text` и `wait_for`.

## Telegram webhook

`POST /api/telegram/webhook` сохранён без изменения. Он извлекает
`message.from` или `callback_query.from` и делает upsert полей
`telegram_id`/`username`.

## Ограничения

- `chrome://*` и другие защищённые страницы недоступны content script;
- произвольный `run_script` может блокироваться CSP — политикой безопасности
  содержимого сайта;
- закрытый Shadow DOM не доступен через DOM API;
- автоматический повтор опасного действия после начала выполнения запрещён;
- старые клиенты без ack поддерживаются только как переходный режим и не дают
  полной гарантии протокола 2.0.
