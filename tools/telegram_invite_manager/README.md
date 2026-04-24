# Telegram Invite Manager

Видимая папка инструмента внутри `site-control-kit`.

Основной код пока остаётся в общих проектных каталогах:
- `scripts/telegram_invite_manager.py`
- `scripts/telegram_invite_executor.py`
- `scripts/telegram_invite_manager_gui.sh`
- `scripts/telegram_invite_executor_gui.sh`
- `docs/TELEGRAM_INVITE_MANAGER_RU.md`
- `docs/TELEGRAM_INVITE_EXECUTOR_RU.md`

Эта папка нужна как удобная точка входа для оператора и нового агента.

## Быстрый Старт

```bash
cd /home/max/site-control-kit/tools/telegram_invite_manager

./bin/telegram-invite-manager --help
./bin/telegram-invite-executor --help
```

## Один Пользователь

Подробный сценарий лежит в:

```text
ONE_USER_FLOW_RU.md
```

Короткий пример:

```bash
cd /home/max/site-control-kit/tools/telegram_invite_manager

./bin/telegram-invite-manager add-user \
  --job-dir "/home/max/telegram_invite_jobs/chat_-2465948544" \
  --chat-url "https://web.telegram.org/k/#-2465948544" \
  --username "@USERNAME" \
  --consent yes
```

## Агентский Документ

Для нового агента сначала читать:

```text
AGENT_GUIDE_RU.md
```

Потом смотреть:
- `ONE_USER_FLOW_RU.md`
- `../../docs/TELEGRAM_INVITE_MANAGER_RU.md`
- `../../docs/TELEGRAM_INVITE_EXECUTOR_RU.md`
- `../../docs/PROJECT_STATUS_RU.md`

## Где Лежат Данные

Рабочие данные не хранятся в репозитории.
Они лежат в:

```text
/home/max/telegram_invite_jobs/chat_<slug>/
```

Для вашего текущего чата:

```text
/home/max/telegram_invite_jobs/chat_-2465948544/
```

Внутри:
- `invite_state.json`
- `runs/<timestamp>/invite_run.json`
- `executions/<timestamp>/execution_plan.json`
- `executions/<timestamp>/execution_record.json`

## Безопасная Граница

Инструмент предназначен для consent-based workflow.
Он не должен превращаться в массовую автодобавлялку, переключатель аккаунтов или обход лимитов Telegram.
