# Центр управления Telegram

Видимая папка Telegram control center внутри `site-control-kit`.

Этот слой не заменяет существующие инструменты.
Его задача другая:
- держать registry подключённых инструментов;
- давать одну простую Telegram-точку входа для оператора и агента;
- открывать простую русскую панель без перегруза лишними экранами;
- позволять выбирать пользователя из списка portable-профилей и добавлять новых по `tdata.zip`.

## Что Уже Подключено

- `telegram_invite_manager` из текущего репозитория;
- `telegram_portable_helper` как low-level embedded helper;
- `telegram_export` как embedded export pipeline;
- `telegram_session_runner` как wrapper вокруг `/home/max/telegram-portable-session-tool`.

Все workflow продолжают жить как отдельные единицы.
Панель поверх них специально упрощена под две основные операторские кнопки:
- `Добавить контакты из TXT`
- `Старт сессии`

Low-level helper и export остаются в registry и CLI, но не засоряют основной экран.

## Структура

- `registry/tools.json` — список подключённых manifests;
- `AGENT_GUIDE_RU.md` — как агенту развивать platform layer;
- `docs/ARCHITECTURE_RU.md` — архитектура registry/panel;
- `docs/INTEGRATION_GUIDE_RU.md` — как подключать новый инструмент;
- `bin/tool-platform` — CLI доступа к catalog;
- `bin/tool-platform-panel` — Tkinter GUI-панель.

## Быстрый Старт

```bash
cd /home/max/site-control-kit/tools/telegram/platform

./bin/tool-platform validate-registry
./bin/tool-platform list-tools
./bin/tool-platform show-tool --tool-id telegram_invite_manager
./bin/tool-platform show-tool --tool-id telegram_portable_helper
./bin/tool-platform show-tool --tool-id telegram_export
./bin/tool-platform show-tool --tool-id telegram_session_runner
./bin/tool-platform-panel
```

Что умеет панель сейчас:
- показывает список уже существующих Telegram portable-пользователей;
- даёт выбрать нужного пользователя из dropdown;
- показывает статус выбранного профиля;
- умеет импортировать новый профиль по `tdata.zip`;
- умеет принять в управление уже существующую portable-папку;
- показывает две большие кнопки режима:
  - `Добавить контакты из TXT`
  - `Старт сессии`
- открывает только один рабочий экран за раз, чтобы оператор не путался;
- в первом режиме умеет загрузить `.txt` / `.csv` / `.json` список username прямо с компьютера и запускать Desktop batch-добавление в контакты выбранного сверху Telegram portable-профиля;
- для batch-добавления контактов панель использует `telegram_invite_executor.py desktop-add-contact-batch`, который сам создаёт локальный job-state, привязывает portable actor и по очереди запускает существующий `desktop-add-contact-profile`;
- внутри `desktop-add-contact-profile` первый режим теперь использует уже подтверждённый live-path из старого sandbox-runner: `Add to contacts` берётся из live accessibility-match, а submit `Готово` считается от геометрии самой диалоговой модалки `Новый контакт`, а не от слепых статических координат;
- `contact_added` ставится только после post-verify reopen профиля: если после попытки всё ещё виден `ДОБАВИТЬ КОНТАКТ`, панель показывает `Есть ошибки`, а пользователь не помечается как успешно добавленный;
- у первого режима есть отдельные понятные кнопки:
  - `Старт добавления`
  - `Статус задачи`
  - `Что осталось`
  - `Стоп`
- в режиме сессии умеет загрузить список адресатов и шаблонов из session-config, отредактировать их и запустить сессию кнопкой;
- в режиме сессии показывает живой таймер, пока session runner работает;
- в режиме сессии есть отдельные настройки:
  - сколько сообщений за цикл;
  - сколько максимум отправить за всю сессию;
  - автоотправка или только черновик;
  - непрерывный режим `крутить до Стопа`;
- при остановке непрерывной сессии панель ожидает честный JSON-статус `stopped`, а не просто аварийный kill процесса;
- у обоих режимов есть явная кнопка `Стоп`;
- панель пишет операторский лог действий в `/tmp/telegram-control-center-panel.log`;
- длинный экран теперь можно прокручивать мышью вниз;
- рендерит детали профиля и результаты в читаемых текстовых блоках, а не в тесных таблицах.

## Что Даёт Registry

Каждый инструмент публикует `tool_manifest.json`, где описаны:
- имя и `tool_id`;
- root path;
- документация;
- базовые operator actions;
- артефакты и capability tags.

Чтобы добавить новый инструмент в платформу, не нужно ломать текущую панель.
Достаточно:
1. создать manifest рядом с инструментом;
2. добавить путь к manifest в `registry/tools.json`;
3. при необходимости обновить operator docs;
4. отдельно решить, нужен ли этому инструменту собственный операторский режим в панели или ему достаточно CLI/registry-видимости.

## Граница

Этот слой не должен превращаться в место, где живёт runtime конкретного Telegram workflow.
Он остаётся orchestration/catalog слоем плюс простой Telegram-ориентированный экран:
- сверху выбор и импорт профилей;
- ниже два понятных рабочих режима;
- low-level и вспомогательные инструменты остаются под капотом.
