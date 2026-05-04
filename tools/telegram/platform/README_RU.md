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
Панель поверх них специально упрощена под три основные операторские кнопки:
- `Добавить контакты из TXT`
- `Старт сессии`
- `Совместный режим`

Low-level helper и export остаются в registry и CLI, но не засоряют основной экран.

## Структура

- `registry/tools.json` — список подключённых manifests;
- `AGENT_GUIDE_RU.md` — как агенту развивать platform layer;
- `docs/ARCHITECTURE_RU.md` — архитектура registry/panel;
- `docs/INTEGRATION_GUIDE_RU.md` — как подключать новый инструмент;
- `/home/max/site-control-kit/docs/TELEGRAM_SUPERTOOL_ROADMAP_RU.md` — стратегический roadmap следующего этапа развития;
- `/home/max/site-control-kit/tools/telegram/agent_pack/README_RU.md` — agent-layer и machine-readable checkpoint;
- `/home/max/site-control-kit/tools/telegram/agent_pack/VERIFICATION_MATRIX_RU.md` — матрица проверок по слоям;
- `/home/max/site-control-kit/tools/telegram/agent_pack/agent_state.template.json` — versioned template machine-readable state;
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
./bin/tool-platform doctor
./bin/tool-platform capabilities
./bin/tool-platform show-agent-state
./bin/tool-platform list-jobs
./bin/tool-platform list-jobs --profile-name AK --workflow-kind combined_pattern --limit 5
./bin/tool-platform show-job --job-id <job_id>
./bin/tool-platform show-artifacts --job-id <job_id>
./bin/tool-platform stop-job --job-id <job_id>
./bin/tool-platform resume-job --job-id <job_id>
./bin/tool-platform profile-health --profile-name AK --profile-dir /home/max/TelegramPortableAK
./bin/tool-platform list-locks
./bin/tool-platform-panel
```

Что умеет панель сейчас:
- показывает список уже существующих Telegram portable-пользователей;
- даёт выбрать нужного пользователя из dropdown;
- показывает статус выбранного профиля;
- показывает сводку по всем найденным профилям прямо на главном экране;
- умеет импортировать новый профиль по `tdata.zip`;
- умеет принять в управление уже существующую portable-папку;
- показывает три большие кнопки режима:
  - `Добавить контакты из TXT`
  - `Старт сессии`
  - `Совместный режим`
- открывает только один рабочий экран за раз, чтобы оператор не путался;
- в первом режиме умеет загрузить `.txt` / `.csv` / `.json` список username прямо с компьютера и запускать Desktop batch-добавление в контакты выбранного сверху Telegram portable-профиля;
- для batch-добавления контактов панель использует `telegram_invite_executor.py desktop-add-contact-batch`, который сам создаёт локальный job-state, привязывает portable actor и по очереди запускает существующий `desktop-add-contact-profile`;
- внутри `desktop-add-contact-profile` первый режим теперь использует уже подтверждённый live-path из старого sandbox-runner: `Add to contacts` берётся из live accessibility-match, а submit `Готово` считается от геометрии самой диалоговой модалки `Новый контакт`, а не от слепых статических координат;
- `contact_added` ставится только после post-verify reopen профиля: если после попытки всё ещё виден `ДОБАВИТЬ КОНТАКТ`, панель показывает `Есть ошибки`, а пользователь не помечается как успешно добавленный;
- если контакт уже был сохранён раньше и в профиле сразу видны `Изменить контакт` / `Удалить контакт`, панель теперь считает это успехом с outcome `contact_already_present`, а не ложной ошибкой;
- `Совместный режим` теперь восстанавливает свой последний статус и summary после повторного открытия панели для того же профиля;
- закрытие панели больше не оставляет за собой Tk `after`-ошибку `_drain_ui_queue` при завершении окна после живого workflow;
- если в `Совместном режиме` очередь уже полностью отработана и `selected_users=0`, панель больше не делает вид, что “добавила контакты”; теперь она явно пишет, что новых username для добавления нет и предлагает либо выбрать новый файл, либо перейти к сессии;
- у первого режима есть отдельные понятные кнопки:
  - `Старт добавления`
  - `Продолжить очередь`
  - `Повторить ошибки`
  - `Статус задачи`
  - `Что осталось`
  - `Обновить экран`
  - `Стоп`
- первый режим показывает прямо в панели:
  - предпросмотр выбранного файла;
  - сколько username осталось в очереди;
  - кого уже удалось добавить;
  - последние ошибки;
  - историю batch-запусков;
- первый режим читает `invite_state.json` и `batch_contact_add.json` напрямую, поэтому оператор видит понятный статус даже после перезапуска панели;
- в режиме сессии умеет загрузить список адресатов и шаблонов из session-config, отредактировать их и запустить сессию кнопкой;
- в режиме сессии вынесены наверх видимые настройки:
  - сколько random-walk визитов делать за цикл;
  - минимум и максимум секунд в чате;
  - сколько сообщений отправлять за цикл;
  - общий лимит;
  - автоотправка;
  - непрерывная работа до `Стоп`;
- в режиме сессии показывает живой таймер, пока session runner работает;
- в режиме сессии есть отдельные настройки:
  - сколько random-walk визитов делать за цикл;
  - сколько секунд держать открытый чат;
  - сколько сообщений за цикл;
  - сколько максимум отправить за всю сессию;
  - автоотправка или только черновик;
  - непрерывный режим `крутить до Стопа`;
- в режиме сессии панель показывает:
  - сводку по последнему run;
  - сколько сообщений реально отправлено;
  - какие сообщения остались неотправленными;
  - историю последних session-run артефактов;
- при остановке непрерывной сессии панель ожидает честный JSON-статус `stopped`, а не просто аварийный kill процесса;
- у обоих режимов есть явная кнопка `Стоп`;
- в `Совместном режиме` панель ведёт по цепочке `Добавить → Сессия` на одном и том же профиле:
  - шаг 1: выбрать файл контактов;
  - шаг 2: выполнить batch-добавление контактов;
  - шаг 3: посмотреть сводку `добавлено / ошибки / осталось`;
  - шаг 4: использовать текущие настройки и тексты сессии;
  - шаг 5: запустить session runner на том же профиле;
- если в `Совместном режиме` выключен флаг непрерывной сессии, панель теперь сама чередует шаги без ручного клика:
  - `добавление контактов -> один session-cycle -> следующий batch контактов -> следующий session-cycle`;
  - цикл продолжается, пока в очереди есть `new/checked` username или пока оператор не нажмёт `Стоп`;
- это уже подтверждено живыми прогонами на настоящем `ToolPlatformPanel`:
  - safe no-send сценарий реально дал `1 -> 1 -> 2 -> 1` для шаблона `11,2,1111,22`;
  - live auto-send сценарий реально дал `1 -> 2 -> 1` для шаблона `121` и не сломал pattern advancement после реальной отправки сообщения;
- если в `Совместном режиме` включён непрерывный режим сессии, автоматическое чередование дальше не идёт: после шага добавления запускается одна длинная сессия до `Стоп`;
- `Совместный режим` не запускает два живых действия на одном Telegram-окне одновременно: сначала завершается contact-add, потом уже стартует сессия;
- если workflow успел спланироваться, но не дошёл до реального child-step старта, stale `planned` job и stale profile lock теперь автоматически чистятся перед следующим запуском;
- у `Сессии` и `Совместного режима` есть кнопка `Продолжить workflow`, которая использует unified `resume_workflow()`, а не локальный ручной restart;
- верхний dashboard и mode screens теперь показывают operator hints поверх unified jobs:
  - `workflow уже выполняется`
  - `можно продолжить`
  - `очередь исчерпана`
  - `ошибки можно повторить`
  - `лучше перезапустить`
- `Продолжить очередь` и `Повторить ошибки` в invite-режиме теперь берут context из latest recoverable unified invite job, а не только из текущего поля `Папка задачи`;
- `Продолжить workflow` в session-режиме теперь реально продолжает recoverable `session_run` job, а не запускает новый workflow "как будто с нуля";
- `Продолжить workflow` в combined-режиме продолжает только parent `combined_pattern` job;
- `Совместный режим` больше не перетирает ручные `Файл контактов / Папка задачи / Шаблон шагов` значениями старого recoverable/completed workflow:
  - history остаётся в dashboard и hints;
  - form-state автоматически синхронизируется только от реально активного combined workflow;
- панель пишет операторский лог действий в `/tmp/telegram-control-center-panel.log`;
- persistent state для control plane теперь уходит в `~/.site-control-kit/telegram/`:
  - `agent/agent_state.json`
  - `jobs/index.json`
  - `locks/profiles.json`
  - `panel_state/combined_flows/*`
- unified workflow engine теперь живёт в `tool_platform/workflows.py` и уже реально управляет тремя workflow-kind:
  - `invite_batch`
  - `session_run`
  - `combined_pattern`
- combined workflow хранит ordered `steps` и aggregated `artifact_paths` прямо в unified jobs, поэтому combined-state панели больше не должен быть единственным source of truth;
- `profile_workspace_snapshot()` теперь собирает operator workspace по профилю:
  - `active_jobs`
  - `recent_jobs`
  - `current_lock`
  - `health`
  - `last_successful_job`
  - `artifact_index`
  - `workflow_buckets`
- `workflow_buckets` теперь есть для:
  - `invite_batch`
  - `session_run`
  - `combined_pattern`
- каждый bucket теперь хранит:
  - `active_job`
  - `last_job`
  - `recent_jobs`
  - `timeline`
  - `artifact_index`
  - `recoverable_job`
- блок `3. Workspace профиля` теперь перестроен в единый profile dashboard:
  - слева `Профиль и workflow`;
  - по центру `История профиля`;
  - справа `Артефакты и здоровье`;
- profile-wide artifact fallback теперь идёт по логике:
  - active workflow artifacts;
  - last successful / recent fallback;
  - bucket-level missing artifacts;
- в profile dashboard есть быстрые operator actions:
  - `Открыть лог панели`
  - `Открыть batch json`
  - `Открыть session run`
  - `Открыть execution record`
  - `Открыть screenshot`
- экраны `Добавить контакты`, `Сессия` и `Совместный режим` теперь не дублируют верхний dashboard длинными readback-блоками:
  - сверху остаётся единый profile workspace;
  - ниже в режиме показываются только mode-specific детали;
- живой Linux smoke последнего tranche подтвердил прямо через `ToolPlatformPanel`:
  - invite `Старт -> Стоп -> Продолжить очередь`;
  - invite `Повторить ошибки`;
  - session `Стоп -> Продолжить workflow`;
  - combined `Стоп -> Продолжить workflow`;
  - отдельный real auto-send confirm:
    - `/home/max/telegram-portable-session-tool/runs/20260504T111811Z-a0435a6f/run.json`
    - `sent_count = 1`
    - `text = Позвоню?`
- `Продолжить workflow` теперь выбирает workflow по unified bucket policy:
  - `active_job`
  - `recoverable_job`
  - `last_job`
- `Продолжить очередь` и `Повторить ошибки` в invite-режиме теперь сначала используют latest recoverable unified invite job context, а уже потом падают обратно на UI `job_dir`;
- для combined readback timeline anchor теперь идёт от `active -> last -> recoverable`, поэтому старый recoverable run не должен перетирать верхний timeline нового parent workflow;
- после завершения workflow верхний profile workspace теперь тоже перерисовывается сразу;
  - закрыт live-bug, когда нижний mode-screen уже обновился, а верхний dashboard оставался stale до ручного переключения профиля;
- длинный экран теперь можно прокручивать мышью вниз;
- рендерит детали профиля и результаты в читаемых текстовых блоках, а не в тесных таблицах.

## Что Даёт Registry

Каждый инструмент публикует `tool_manifest.json`, где описаны:
- имя и `tool_id`;
- root path;
- документация;
- базовые operator actions;
- артефакты и capability tags.
- поддерживаемые платформы;
- required capabilities;
- degraded modes.

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
- ниже три понятных рабочих режима;
- low-level и вспомогательные инструменты остаются под капотом.
