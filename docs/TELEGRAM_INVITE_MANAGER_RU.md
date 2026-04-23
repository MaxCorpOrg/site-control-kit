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
- `tests/test_telegram_invite_manager.py`

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
- dry-run
- run artifacts
- explicit mark command
- summary report

## Что Пока Не Реализовано
На текущем этапе нет живого Telegram invite execution path.
Это осознанно.
Сначала собран надёжный manager/state слой.

Следующий шаг можно делать отдельно:
- invite link workflow
- join request workflow
- полуавтоматический browser-assisted flow

## Следующий Логичный Шаг
Самый правильный следующий шаг: добавить безопасный `invite link / join request` orchestration path, а не автоматическое массовое добавление людей в чат.
