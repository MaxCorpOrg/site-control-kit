# Components And Entrypoints

## Python Core
### `webcontrol/server.py`
Главный HTTP hub.
Отвечает за:
- auth;
- API маршруты;
- выдачу команд;
- приём heartbeat/result.

### `webcontrol/store.py`
Состояние, очередь и persistence.
Именно тут живут client records, command states и state-file логика.

### `webcontrol/cli.py`
CLI и `sitectl browser`.
Ключевая точка для:
- browser status;
- clients/tabs;
- tab actions;
- X11 fallback helpers.

## Extension Layer
### `extension/background.js`
Делает:
- heartbeat;
- polling;
- tab-level actions;
- reload/new-tab/activate/close;
- capability advertisement.

### `extension/content.js`
Делает:
- click/fill/wait;
- extract text/html/attr;
- run_script;
- menu click logic;
- wheel/scroll commands;
- Telegram-specific DOM building blocks.

## Telegram Scripts
### `scripts/export_telegram_members_non_pii.py`
Главный Telegram exporter.
Самый сложный модуль проекта на текущий момент.
В нём сейчас сосредоточены:
- discovery;
- deep scheduling;
- history backfill;
- output sanitization;
- telemetry.

### `scripts/auto_collect_usernames.sh`
Обвязка вокруг exporter.
Делает:
- выбор client/tab;
- старт/reuse hub;
- проброс state/history/stats путей;
- запуск exporter с нужными флагами.

### `scripts/collect_new_telegram_contacts.sh`
Batch-wrapper.
Делает:
- chat dir;
- run dir;
- snapshot files;
- latest guard;
- numbered batch files;
- run.json.

### `scripts/telegram_contact_chain.py`
Chain-runner.
Делает:
- серию коротких прогонов;
- stop conditions;
- profile handling;
- skip interval after productive yield;
- chain summary.

### `scripts/telegram_profiles.py`
Общий helper profile presets.
Это единая точка правды для `fast / balanced / deep`.
Его используют:
- chain-runner;
- batch shell;
- GUI wrappers.

### `scripts/telegram_invite_manager.py`
Новый безопасный manager/state инструмент для consent-based invite workflow.
На текущем этапе умеет:
- импорт CSV/JSON;
- добавлять одного consented user через `add-user`;
- строить `invite_state.json`;
- выбирать следующую пачку usernames;
- писать `invite_run.json` и `invite.log`;
- переводить записи по status lifecycle.

### `scripts/telegram_invite_manager_gui.sh`
Базовый zenity-wrapper над Invite Manager CLI.
Это операторский слой, а не источник истины.

### `scripts/telegram_invite_executor.py`
Execution-слой поверх Invite Manager.
На текущем этапе умеет:
- хранить execution-config в `invite_state.json`;
- строить `execution_plan.json`;
- открывать нужный Telegram chat через `site-control`;
- писать `execution_record.json` после ручного действия оператора.

### `scripts/telegram_invite_executor_gui.sh`
Базовый zenity-wrapper над Invite Executor CLI.
Тоже не источник истины: правда остаётся в `invite_state.json` и execution-артефактах.

### `scripts/write_telegram_safe_snapshot.py`
Построение safe-snapshot из raw markdown.

### `scripts/telegram_contact_batches.py`
Работа с numbered batch files, best snapshot promotion и related helpers.

## GUI / Operator Layer
### `scripts/telegram_members_export_app.sh`
Zenity-обёртка для более ручного экспорта.
Теперь умеет выбирать profile.

### `scripts/telegram_members_export_gui.sh`
Progress-oriented GUI wrapper.
Тоже умеет выбирать profile.

## Главные Точки Входа Для Реальной Работы
1. Browser smoke:
```bash
PYTHONPATH="$PWD" python3 -m webcontrol clients
```
2. Один batch-run:
```bash
./scripts/collect_new_telegram_contacts.sh "https://web.telegram.org/k/#-2465948544"
```
3. Серия прогонов:
```bash
./scripts/collect_new_telegram_contacts_chain.sh "https://web.telegram.org/k/#-2465948544" \
  "/home/max/telegram_contact_batches" \
  --profile deep --runs 3
```
4. Invite Manager:
```bash
cd /home/max/site-control-kit/tools/telegram_invite_manager
./bin/telegram-invite-manager --help
./bin/telegram-invite-executor --help
```

4. Invite manager:
```bash
python3 scripts/telegram_invite_manager.py init \
  --chat-url "https://web.telegram.org/k/#-2465948544" \
  --input "/home/max/telegram_invite_jobs/chat_-2465948544/users.csv"
```
