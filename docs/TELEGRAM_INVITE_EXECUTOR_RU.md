# Telegram Invite Executor RU

## Что Это
`Telegram Invite Executor` — новый безопасный execution-слой внутри `site-control-kit` для `Telegram Invite Manager`.

Он не делает массовое добавление пользователей в чат и не реализует обход лимитов Telegram.
Его задача другая:
- держать конфигурацию consent-based invite workflow;
- готовить execution-plan для оператора;
- использовать `site-control` для открытия нужного Telegram-чата;
- сохранять execution-артефакты;
- записывать результат ручных действий обратно в `invite_state.json`.

## Файлы
- `scripts/telegram_invite_executor.py`
- `scripts/telegram_invite_executor_gui.sh`
- `tests/test_telegram_invite_executor.py`

## Как Он Связан С Invite Manager
`Invite Manager` остаётся источником истины по пользователям и статусам:
- `invite_state.json`
- `invite_run.json`

`Invite Executor` использует тот же `invite_state.json`, но работает уже на слое исполнения:
- `configure`
- `plan`
- `open-chat`
- `record`
- `report`

## Что Хранится В State
В `invite_state.json` теперь может появляться секция:

```json
{
  "execution": {
    "invite_link": "https://t.me/+example",
    "message_template": "Привет! Вот ссылка для вступления в чат: {invite_link}",
    "note": "operator-assisted flow",
    "requires_approval": true,
    "browser_target": {
      "client_id": "client-123",
      "tab_id": 0,
      "url_pattern": "web.telegram.org/k/#-2465948544",
      "active": true
    }
  }
}
```

## Execution Артефакты
По умолчанию execution-каталог:

```text
~/telegram_invite_jobs/chat_<slug>/executions/<timestamp>/
```

Внутри:
- `execution_plan.json`
- `execution.log`
- `execution_record.json`
- `execution_record.log`

## Команды

### `configure`
Сохраняет invite-link и browser-target в `invite_state.json`.

Пример:

```bash
cd /home/max/site-control-kit
python3 scripts/telegram_invite_executor.py configure \
  --job-dir "/home/max/telegram_invite_jobs/chat_-2465948544" \
  --invite-link "https://t.me/+example" \
  --message-template "Привет! Вот ссылка для вступления в чат: {invite_link}" \
  --url-pattern "web.telegram.org/k/#-2465948544" \
  --requires-approval
```

### `plan`
Готовит execution-plan для следующей пачки пользователей.

По умолчанию берёт пользователей из статуса `checked`.

Если передан `--reserve`, выбранные пользователи переводятся в `invite_link_created`, чтобы не попасть повторно в другую операторскую сессию.

Пример:

```bash
cd /home/max/site-control-kit
python3 scripts/telegram_invite_executor.py plan \
  --job-dir "/home/max/telegram_invite_jobs/chat_-2465948544" \
  --limit 3 \
  --reserve
```

### `open-chat`
Использует `site-control` browser CLI, чтобы открыть или активировать нужный Telegram-чат.

Логика такая:
- если в execution-config есть `tab_id`, будет `browser --tab-id ... activate`
- если есть `url_pattern`, будет `browser --url-pattern ... activate`
- иначе будет `browser new-tab <chat_url>`

Сначала можно проверить dry-run:

```bash
cd /home/max/site-control-kit
python3 scripts/telegram_invite_executor.py open-chat \
  --job-dir "/home/max/telegram_invite_jobs/chat_-2465948544" \
  --dry-run
```

### `record`
После ручного действия оператор записывает результат обратно в state.

Пример:

```bash
cd /home/max/site-control-kit
python3 scripts/telegram_invite_executor.py record \
  --job-dir "/home/max/telegram_invite_jobs/chat_-2465948544" \
  --username @alice_123 \
  --status sent \
  --reason manual_link_sent
```

### `report`
Показывает:
- текущее агрегированное состояние job;
- execution-config;
- последние execution-plan;
- preview следующей execution-пачки.

## GUI Wrapper
Есть базовый wrapper:

```bash
bash scripts/telegram_invite_executor_gui.sh
```

Он не заменяет CLI, а только упрощает операторский слой.

## Безопасная Семантика
Этот слой не должен:
- автоматически массово добавлять пользователей в чат;
- переключать аккаунты для обхода лимитов;
- маскировать спам под “growth automation”.

Правильный сценарий:
1. менеджерит consented users;
2. готовит execution-plan;
3. открывает нужный чат через `site-control`;
4. оператор выполняет безопасный invite workflow;
5. результат записывается через `record`.

## Следующий Шаг
Следующий логичный шаг — не forced-add path, а:
- безопасный invite link / join request orchestration;
- optional operator checklist для реального Telegram UI;
- затем живой smoke на поднятом browser bridge.
