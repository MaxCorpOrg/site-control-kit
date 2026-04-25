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
./bin/gui-manager
./bin/gui-executor
```

GUI-обёртки теперь покрывают основной операторский поток:
- manager GUI: `init`, `status`, `next`, `add user`, `run`, `mark`, `report`;
- executor GUI: `configure`, `plan`, `inspect-chat`, `open-chat`, `add-contact dry/prepare/live`, `record`, `report`.

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

## Live Add Одного Контакта

Executor теперь умеет отдельный однопользовательский UI-path через Telegram Web `Add Members`.
Финальное действие защищено флагом `--confirm-add`.

```bash
cd /home/max/site-control-kit/tools/telegram_invite_manager

./bin/telegram-invite-executor add-contact \
  --job-dir "/home/max/telegram_invite_jobs/chat_Zhirotop_shop" \
  --username "@USERNAME" \
  --tab-id "<TELEGRAM_TAB_ID>" \
  --skip-open \
  --confirm-add \
  --record-result
```

Без `--confirm-add` команда выбирает пользователя и останавливается до внешнего действия добавления.
Если Telegram не показывает явный `joined/added`, результат записывается как `requested`, а не как `joined`.

Перед и после live add можно штатно снять счётчик чата:

```bash
./bin/telegram-invite-executor inspect-chat \
  --job-dir "/home/max/telegram_invite_jobs/chat_Zhirotop_shop" \
  --tab-id "<TELEGRAM_TAB_ID>" \
  --skip-open
```

## Агентский Документ

Для нового агента сначала читать:

```text
AGENT_GUIDE_RU.md
```

Готовый prompt для нового чата лежит здесь:

```text
NEXT_CHAT_AGENT_PROMPT_RU.md
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
Команда `add-contact` принимает одного пользователя и требует, чтобы он уже был в `invite_state.json` с `consent=yes`.
