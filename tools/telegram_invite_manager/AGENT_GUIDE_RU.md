# Agent Guide RU: Telegram Invite Manager

Этот файл — короткая инструкция для агента, который продолжает работу с invite-инструментом.

## Сначала Прочитать

Из корня проекта:

```bash
cd /home/max/site-control-kit
```

Обязательно прочитать:
- `AGENTS.md`
- `docs/PROJECT_STATUS_RU.md`
- `docs/TELEGRAM_INVITE_MANAGER_RU.md`
- `docs/TELEGRAM_INVITE_EXECUTOR_RU.md`
- `tools/telegram_invite_manager/README.md`
- `tools/telegram_invite_manager/ONE_USER_FLOW_RU.md`

## Что Уже Сделано

Есть manager-слой:
- импорт CSV/JSON;
- `add-user` для одного пользователя;
- `invite_state.json`;
- `next/run/mark/report`;
- `runs/<timestamp>/invite_run.json`;
- GUI wrapper.

Есть execution-слой:
- `configure`;
- `plan`;
- `open-chat`;
- `record`;
- `report`;
- `executions/<timestamp>/execution_plan.json`;
- `executions/<timestamp>/execution_record.json`;
- GUI wrapper.

Есть видимая папка инструмента:

```text
tools/telegram_invite_manager/
```

## Как Работать С Одним Пользователем

1. Добавить пользователя только при явном consent.
2. Перевести его в `checked`.
3. Настроить invite-link.
4. Создать execution-plan на `limit 1`.
5. Открыть чат через `site-control`.
6. После ручного действия записать результат через `record`.

Полная команда лежит в `ONE_USER_FLOW_RU.md`.

## Важные Статусы

- `new` — пользователь добавлен и ждёт проверки.
- `checked` — оператор подтвердил, что можно делать invite workflow.
- `invite_link_created` — создан или зарезервирован invite-plan.
- `sent` — ссылка/приглашение отправлены.
- `requested` — пользователь подал join request.
- `approved` — заявка одобрена.
- `joined` — пользователь вступил.
- `skipped` — не обрабатывать.
- `failed` — действие не удалось.

## Проверки После Правок

Всегда запускать:

```bash
cd /home/max/site-control-kit
PYTHONPATH="$PWD" python3 -m unittest discover -s tests -p 'test_*.py'
```

Если менялись Python-файлы:

```bash
python3 -m py_compile scripts/telegram_invite_manager.py scripts/telegram_invite_executor.py
```

Если менялись shell-файлы:

```bash
bash -n scripts/telegram_invite_manager_gui.sh scripts/telegram_invite_executor_gui.sh \
  tools/telegram_invite_manager/bin/telegram-invite-manager \
  tools/telegram_invite_manager/bin/telegram-invite-executor
```

## Что Нельзя Делать

- Не добавлять массовую автодобавлялку.
- Не делать multi-account обход лимитов.
- Не использовать список usernames без подтверждённого согласия.
- Не затирать state без бэкапа или явного запроса пользователя.

## Текущий Следующий Шаг

Живой one-user smoke в рабочем каталоге уже подтверждён:

```text
/home/max/telegram_invite_jobs/chat_-2465948544/
```

Факты smoke:
- `add-user` добавил `@sitectl_smoke_user`;
- `run --limit 1 --to-status checked` перевёл запись в `checked`;
- `plan --limit 1 --reserve` создал `execution_plan.json`;
- `open-chat` через `site-control` открыл Telegram tab `614280462`;
- после проверки запись помечена как `skipped` с reason `smoke_test_completed`.

Артефакты:
- `/tmp/tg_invite_real_add.json`
- `/tmp/tg_invite_real_run.json`
- `/tmp/tg_invite_real_configure.json`
- `/tmp/tg_invite_real_plan.json`
- `/tmp/tg_invite_real_open.json`
- `/tmp/tg_invite_real_record.json`
- `/home/max/telegram_invite_jobs/chat_-2465948544/executions/20260424T123754Z/execution_plan.json`
- `/home/max/telegram_invite_jobs/chat_-2465948544/executions/20260424T123800Z/execution_record.json`

Следующий практический шаг:
- заменить smoke username и placeholder invite-link на реальные значения;
- провести один consented user через тот же flow;
- после ручной отправки ссылки записать `sent`, `requested` или `joined`.

Для финального реального invite нужны:
- конкретный `@username` пользователя с consent;
- реальный invite-link нужного чата.

Без этих двух значений агент может проверять только manager/executor/open-chat, но не факт отправки приглашения.
