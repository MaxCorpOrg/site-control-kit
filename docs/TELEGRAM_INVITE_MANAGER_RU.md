# Telegram Invite Manager RU

## Что Это
`Telegram Invite Manager` — новый безопасный инструмент внутри `site-control-kit` для точечной работы с пользователями, которые уже дали согласие на вступление в чат.

Это не инструмент массового добавления пользователей и не инструмент обхода лимитов Telegram.
На текущем этапе он решает manager/state/reporting задачу:
- загружает список пользователей;
- нормализует usernames;
- хранит статусы;
- умеет выбирать следующую пачку пользователей;
- пишет run-артефакты;
- позволяет безопасно продолжать работу с места остановки.

## Файлы Инструмента
- `scripts/telegram_invite_manager.py`
- `scripts/telegram_invite_manager_gui.sh`
- `scripts/telegram_invite_executor.py`
- `scripts/telegram_invite_executor_gui.sh`
- `tests/test_telegram_invite_manager.py`
- `tests/test_telegram_invite_executor.py`

## Где Хранится Состояние
По умолчанию job-каталоги лежат в:

```text
~/telegram_invite_jobs/chat_<slug>/
```

Внутри:
- `invite_state.json`
- `runs/<timestamp>/invite_run.json`
- `runs/<timestamp>/invite.log`

## Поддерживаемый Вход
### CSV
Поддерживаются колонки:
- `username`
- `display_name`
- `note`
- `consent`
- `source`

### JSON
Поддерживается либо:
- список объектов
- либо объект вида `{ "users": [...] }`

## Статусы
Инструмент использует такие статусы:
- `new`
- `checked`
- `invite_link_created`
- `sent`
- `requested`
- `approved`
- `joined`
- `skipped`
- `failed`

### Семантика На Текущем Этапе
- `new` — новый consented user
- `checked` — пользователь обработан оператором
- `invite_link_created` — подготовлен invite link workflow
- `sent` — приглашение/ссылка отправлена
- `requested` — пользователь подал join request
- `approved` — заявка одобрена
- `joined` — пользователь вступил
- `skipped` — запись не должна обрабатываться, например нет consent
- `failed` — обработка не удалась

## Команды CLI
### `init`
Создаёт новый job и `invite_state.json`.

Пример:

```bash
python3 scripts/telegram_invite_manager.py init \
  --chat-url "https://web.telegram.org/k/#-2465948544" \
  --input "/home/max/telegram_invite_jobs/chat_-2465948544/users.csv"
```

### `status`
Показывает агрегированное состояние job.

### `next`
Возвращает следующую пачку пользователей для обработки.

### `add-user`
Добавляет одного пользователя в существующий job.
Команда требует явный `--consent yes`, чтобы случайно не отправить в обработку пользователя без подтверждения.

Пример:

```bash
python3 scripts/telegram_invite_manager.py add-user \
  --job-dir "/home/max/telegram_invite_jobs/chat_-2465948544" \
  --chat-url "https://web.telegram.org/k/#-2465948544" \
  --username @alice_123 \
  --display-name "Alice" \
  --note "one user test" \
  --source manual \
  --consent yes
```

### `run`
Обрабатывает следующую пачку и создаёт run-артефакты.
По умолчанию переводит `new -> checked`.

Есть `--dry-run`.

### `mark`
Ручная смена статуса для конкретных usernames.

### `report`
Сводный отчёт по job и последним run.

## Примеры
```bash
cd /home/max/site-control-kit

python3 scripts/telegram_invite_manager.py init \
  --chat-url "https://web.telegram.org/k/#-2465948544" \
  --input "/home/max/telegram_invite_jobs/chat_-2465948544/users.csv"

python3 scripts/telegram_invite_manager.py status \
  --job-dir "/home/max/telegram_invite_jobs/chat_-2465948544"

python3 scripts/telegram_invite_manager.py next \
  --job-dir "/home/max/telegram_invite_jobs/chat_-2465948544" \
  --limit 3

python3 scripts/telegram_invite_manager.py add-user \
  --job-dir "/home/max/telegram_invite_jobs/chat_-2465948544" \
  --chat-url "https://web.telegram.org/k/#-2465948544" \
  --username @alice_123 \
  --consent yes

python3 scripts/telegram_invite_manager.py run \
  --job-dir "/home/max/telegram_invite_jobs/chat_-2465948544" \
  --limit 3 \
  --dry-run

python3 scripts/telegram_invite_manager.py mark \
  --job-dir "/home/max/telegram_invite_jobs/chat_-2465948544" \
  --username @alice_123 \
  --status sent \
  --reason manual_send
```

## GUI Wrapper
Есть базовый GUI wrapper:

```bash
bash scripts/telegram_invite_manager_gui.sh
```

Он нужен как удобный операторский слой поверх CLI, но источник истины всё равно остаётся в `invite_state.json` и run-артефактах.

## Что Уже Реализовано
- CSV/JSON import
- username normalization
- consent filtering
- state file
- next-batch selection
- one-user add command
- dry-run
- run artifacts
- explicit mark command
- summary report
- execution-config внутри `invite_state.json`
- execution-plan через отдельный `Telegram Invite Executor`
- browser-assisted `open-chat` через `site-control`
- автонормализация публичного `https://t.me/<handle>` в `https://web.telegram.org/k/#@<handle>` при открытии чата без явного browser-target
- execution-record артефакты и update статусов после ручных действий
- auto-verification before/after для live `add-contact`, чтобы `joined` фиксировался только по подтверждаемому сигналу
- подтверждение `joined` теперь опирается не только на `member_count`, но и на появление выбранного `peer_id` в видимом списке участников

## Что Пока Не Реализовано
На текущем этапе есть только безопасный operator-assisted execution path.
Нет forced-add/mass-add логики и нет обхода лимитов Telegram.

Следующий шаг можно делать отдельно:
- invite link workflow
- join request workflow
- более сильное подтверждение вступления за пределами текущего видимого member list
- живой smoke на поднятом browser bridge

## Следующий Логичный Шаг
Самый правильный следующий шаг: добить живой `invite link / join request` orchestration path поверх нового execution-слоя, а не автоматическое массовое добавление людей в чат.
