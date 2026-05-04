# Next Chat Agent Prompt RU

Ниже готовый prompt для нового чата по текущему Telegram-контуру.
Его можно вставить целиком без сокращений.

```text
Работай в проекте /home/max/site-control-kit.

Контекст:
- Это не новый проект и не новая ветка работы.
- Продолжай именно с checkpoint после Telegram control center, profile-first панели и visible session-runner.
- Не начинай исследование с нуля.

Что нужно сделать первым делом:
1. Перейди в /home/max/site-control-kit
2. Выполни:
   - git status --short --branch
   - git log --oneline -n 15
3. Дополнительно проверь standalone repo session-runner:
   - git -C /home/max/telegram-portable-session-tool status --short --branch
   - git -C /home/max/telegram-portable-session-tool log --oneline -n 10
4. Прочитай в таком порядке:
   - /home/max/site-control-kit/AGENTS.md
   - /home/max/site-control-kit/START_HERE_AGENT_RU.md
   - /home/max/site-control-kit/docs/PROJECT_STATUS_RU.md
   - /home/max/site-control-kit/tools/telegram/agent_pack/README_RU.md
   - /home/max/site-control-kit/tools/telegram/agent_pack/VERIFICATION_MATRIX_RU.md
   - /home/max/site-control-kit/tools/telegram/agent_pack/agent_state.template.json
   - ~/.site-control-kit/telegram/agent/agent_state.json
   - ~/.site-control-kit/telegram/agent/workspace_checkpoint.json
   - /home/max/site-control-kit/tools/telegram/README_RU.md
   - /home/max/site-control-kit/tools/telegram/AGENT_GUIDE_RU.md
   - /home/max/site-control-kit/tools/telegram/platform/README_RU.md
   - /home/max/site-control-kit/tools/telegram/platform/AGENT_GUIDE_RU.md
   - /home/max/site-control-kit/tools/telegram/session_runner/README_RU.md
   - /home/max/site-control-kit/tools/telegram/session_runner/AGENT_GUIDE_RU.md
   - /home/max/site-control-kit/docs/TELEGRAM_PORTABLE_RU.md
   - /home/max/telegram-portable-session-tool/AGENTS.md
   - /home/max/telegram-portable-session-tool/README_RU.md
   - /home/max/telegram-portable-session-tool/examples/session.example.json

Точка, на которой проект зафиксирован сейчас:
- site-control-kit:
  - ветка: codex/telegram-client-hardening
  - последние checkpoint commits:
    - `241a903` — усилен timeline и artifact center Telegram панели
    - `188f2bd` — шаблонный совместный режим Telegram панели
    - `2be8229` — сохранение `step_pattern/step_cursor` в combined-state
  - смысл текущей точки: live combined bug уже закрыт на новом workflow/job engine, и текущий приоритет смещён в operator workspace / timeline / artifact center
- standalone session tool:
  - репозиторий: /home/max/telegram-portable-session-tool
  - ветка: main
  - текущий commit: 0c5a49d
- теги восстановления:
  - site-control-kit: restore-20260502-telegram-control-center
  - session tool: restore-20260502-session-tool

Что уже сделано и считается текущей базой:
- в /home/max/site-control-kit/tools/telegram собран единый Telegram hub;
- в /home/max/site-control-kit/tools/telegram/platform есть Telegram control center;
- panel теперь profile-first:
  - показывает dropdown существующих portable-пользователей;
  - умеет Refresh Status;
  - умеет Launch;
  - умеет импортировать нового пользователя по tdata.zip;
  - умеет adopt уже существующую portable-папку;
- import-zip в scripts/telegram_portable.py теперь умеет сразу сохранять account.username и account.label;
- session-runner виден внутри site-control-kit через:
  - /home/max/site-control-kit/tools/telegram/session_runner
  - /home/max/site-control-kit/tools/telegram/platform/registry/tools.json
- реальный runtime session-runner всё ещё живёт отдельно:
  - /home/max/telegram-portable-session-tool
- совместный режим панели уже не состоит из двух ручных кнопок:
  - теперь это один `Старт совместного режима`;
  - `1` = добавление контактов;
  - `2` = сессия и сообщения;
  - поддерживается шаблон вроде `11,2,1111,22,1,222,1111`;
- parser шаблона и сохранение `step_pattern/step_cursor` уже починены;
- panel-harness на самом `ToolPlatformPanel` уже подтверждал корректную последовательность шагов;
- теперь и реальная живая панель это подтверждает:
  - safe no-send live-pass на `ToolPlatformPanel` дал `1 -> 1 -> 2 -> 1` для шаблона `11,2,1111,22`;
  - live auto-send confirm дал `1 -> 2 -> 1` для шаблона `121` и реально отправил `1` сообщение;
  - stale `planned` combined job, stale profile lock и ложный modal `showerror(-15)` после stop тоже закрыты.
- foundation-слой уже начал выноситься из GUI:
- foundation-слой уже не только начат, но и частично включён в реальный control-plane:
  - versioned agent-pack defaults:
    - `/home/max/site-control-kit/tools/telegram/agent_pack/agent_state.template.json`
    - `/home/max/site-control-kit/tools/telegram/agent_pack/VERIFICATION_MATRIX_RU.md`
  - persistent agent state: `~/.site-control-kit/telegram/agent/agent_state.json`;
  - unified jobs: `~/.site-control-kit/telegram/jobs/index.json`;
  - profile locks: `~/.site-control-kit/telegram/locks/profiles.json`;
  - persistent combined state: `~/.site-control-kit/telegram/panel_state/combined_flows/*`;
  - tool manifests уже знают `supported_platforms`, `required_capabilities`, `degraded_modes`;
  - `tool-platform` уже умеет `doctor`, `capabilities`, `show-agent-state`, `list-jobs`, `list-locks`.
- новый workflow engine уже живёт в:
  - `/home/max/site-control-kit/tool_platform/workflows.py`;
  - `/home/max/site-control-kit/tool_platform/jobs.py`;
- сейчас через него уже реально запускаются из панели:
  - `invite_batch`;
  - `session_run`;
  - `combined_pattern`;
- combined workflow теперь хранит ordered child step history и aggregated artifact index в unified jobs, а `load_combined_flow_state()` предпочитает jobs как primary truth;
- в `gui.py` уже удалены старые ручные combined auto-step handlers, а `Старт добавления` / `Старт сессии` / `Старт совместного режима` идут через:
  - `plan_workflow()`;
  - `run_workflow()`;
  - `complete_workflow_step()`;
  - `stop_workflow_job()`;
- панель уже показывает unified jobs summary по каждому из трёх режимов и quick actions для артефактов профиля:
  - лог панели;
  - batch json;
  - session run;
  - execution record;
  - screenshot.
- operator workspace tranche уже тоже частично закрыт:
  - `profile_workspace_snapshot()` теперь отдаёт:
    - `active_jobs`
    - `recent_jobs`
    - `current_lock`
    - `health`
    - `last_successful_job`
    - `artifact_index`
    - `workflow_buckets`
  - `workflow_buckets` уже есть для:
    - `invite_batch`
    - `session_run`
    - `combined_pattern`
  - каждый bucket теперь содержит:
    - `active_job`
    - `last_job`
    - `recent_jobs`
    - `timeline`
    - `artifact_index`
    - `recoverable_job`
  - `list-jobs` теперь поддерживает filters:
    - `--profile-name`
    - `--profile-dir`
    - `--workflow-kind`
    - `--status`
    - `--limit`
  - invite/session/combined экраны в `gui.py` теперь сверху рендерят один и тот же pattern:
    - current workflow summary
    - workflow timeline
    - artifact center
    - mode-specific details
  - `Продолжить workflow` теперь выбирает workflow по bucket-правилу:
    - `active_job`
    - `recoverable_job`
    - `last_job`
  - `Продолжить очередь` / `Повторить ошибки` теперь используют latest recoverable unified invite job context, а не только текущий UI `job_dir`;
  - следующий tranche `Resume / Retry UX` уже тоже закрыт:
    - `profile_workspace_snapshot()` теперь отдаёт operator hints:
      - `resume_hint`
      - `continue_queue_hint`
      - `retry_failed_hint`
      - `next_operator_action`
    - invite `Продолжить очередь` и `Повторить ошибки` используют latest recoverable unified invite context;
    - session `Продолжить workflow` реально продолжает recoverable `session_run` job;
    - combined `Продолжить workflow` продолжает только parent `combined_pattern` job;
    - stale form override в `Совместном режиме` закрыт: completed/recoverable history больше не перетирает ручные `input_path / invite_job_dir / step_pattern`;
  - timeline anchor для combined readback уже поправлен на `active -> last -> recoverable`, чтобы старый recoverable run не перетирал верхний timeline.
  - верхний блок `3. Workspace профиля` теперь реально перестроен в dashboard:
    - `Профиль и workflow`
    - `История профиля`
    - `Артефакты и здоровье`
  - workspace dashboard теперь берёт source of truth из unified jobs и profile workspace snapshot, а не из cached panel-state;
  - profile-wide artifact fallback уже починен на логику:
    - active workflow artifacts
    - last successful / recent fallback
    - bucket-level missing artifacts
  - live-bug класса `нижний mode refresh обновился, а верхний workspace остался stale` уже закрыт и покрыт regression-тестом;
  - живой screenshot нового dashboard сохранён в:
    - `/tmp/telegram-profile-workspace-dashboard.png`
  - panel-layer smoke после фикса stale dashboard refresh:
    - `/tmp/telegram-profile-dashboard-safe-live-2/result.json`
  - в этом smoke подтвердилось:
    - `Последний успешный workflow` обновился до только что завершённого job;
    - верхний timeline сразу показал новый parent workflow и его child step;
    - stale подмена старым recoverable workflow больше не воспроизводится.
  - новые live-артефакты tranche `Resume / Retry UX`:
    - `/tmp/telegram-resume-retry-live/20260504T111030Z/result.json`
    - `/tmp/telegram-resume-retry-live-postfix/20260504T111649Z/result.json`
    - `/tmp/telegram-resume-retry-send-confirm.json`
    - `/home/max/telegram-portable-session-tool/runs/20260504T111811Z-a0435a6f/run.json`
  - по реальному panel-smoke подтверждено:
    - invite `Старт -> Стоп -> Продолжить очередь`;
    - invite `Повторить ошибки`;
    - session `Стоп -> Продолжить workflow`;
    - combined `Стоп -> Продолжить workflow`;
    - отдельный real auto-send confirm с `sent_count = 1` и `sent: true`.
  - tranche `Architecture Audit + Next Tranche` теперь тоже закрыт:
    - top action hint перебалансирован:
      - свежий `completed` / `dry_run` workflow теперь выигрывает у старого recoverable в верхнем workspace summary;
      - recoverable workflow при этом остаётся доступным в bucket-level hints и Resume UX;
    - grouped profile history и compact timeline теперь собираются на стороне `tool_platform/jobs.py`, а не в локальном GUI readback;
    - profile artifact center теперь строится в snapshot-модели:
      - `artifact_shortcuts`
      - `artifact_center`
      - session fallback через `session_history_snapshot()`, если unified `session_run` jobs ещё не принесли `artifact_paths`;
    - закрыт живой readback-баг:
      - после свежего session send shortcut `Открыть session run` больше не ведёт в старый combined `run_dir`;
      - теперь он стабильно указывает на свежий standalone `run.json` до и после restart панели;
    - новые live-артефакты:
      - safe no-send readback smoke:
        - `/tmp/telegram-architecture-audit-safe-readback/result.json`
      - final real auto-send confirm:
        - `/tmp/telegram-architecture-audit-send-confirm-final/result.json`
        - `/home/max/telegram-portable-session-tool/runs/20260504T140725Z-0c50fab7/run.json`
      - в final confirm подтверждено:
        - `sent_count = 1`
        - `message_count = 1`
        - `text = Хорошего дня!`
        - `artifact_shortcuts.session_run = /home/max/telegram-portable-session-tool/runs/20260504T140725Z-0c50fab7/run.json`

Что сейчас важно не потерять:
- session-runner не копировать вручную в site-control-kit без отдельного решения;
- tool_platform не превращать в место, где живёт runtime бизнес-логика Telegram;
- panel держать простой и функциональной, не раздувать в тяжелую систему экранов;
- в site-control-kit сейчас есть untracked локальные папки пользователя:
  - /home/max/site-control-kit/.codex
  - /home/max/site-control-kit/TG_APP
  - /home/max/site-control-kit/telegram_ak
  - их не трогать и не коммитить.

Какие файлы являются основной точкой входа именно для этой текущей стадии:
- /home/max/site-control-kit/tools/telegram/NEXT_CHAT_AGENT_PROMPT_RU.md
- /home/max/site-control-kit/tools/telegram/agent_pack/README_RU.md
- /home/max/site-control-kit/tools/telegram/agent_pack/VERIFICATION_MATRIX_RU.md
- /home/max/site-control-kit/tools/telegram/agent_pack/agent_state.template.json
- /home/max/site-control-kit/tools/telegram/README_RU.md
- /home/max/site-control-kit/tools/telegram/platform/README_RU.md
- /home/max/site-control-kit/docs/PROJECT_STATUS_RU.md
- /home/max/site-control-kit/docs/TELEGRAM_SUPERTOOL_ROADMAP_RU.md
- ~/.site-control-kit/telegram/agent/agent_state.json
- ~/.site-control-kit/telegram/agent/workspace_checkpoint.json

Если задача про panel/control center, куда лезть:
- /home/max/site-control-kit/tool_platform/gui.py
- /home/max/site-control-kit/tool_platform/catalog.py
- /home/max/site-control-kit/tool_platform/cli.py
- /home/max/site-control-kit/tool_platform/telegram_profiles.py
- /home/max/site-control-kit/tools/telegram/platform/registry/tools.json

Если задача про portable-профили и tdata:
- /home/max/site-control-kit/scripts/telegram_portable.py
- /home/max/site-control-kit/tools/telegram/portable_helper/*
- /home/max/site-control-kit/docs/TELEGRAM_PORTABLE_RU.md

Если задача про session-runner:
- visible wrapper:
  - /home/max/site-control-kit/tools/telegram/session_runner/*
- standalone runtime:
  - /home/max/telegram-portable-session-tool/*

Текущий логичный следующий шаг:
- не возвращаться к старому расследованию `не чередует`: этот live-баг уже закрыт;
- не возвращаться и к старой постановке `сделать timeline/history поверх unified jobs`: базовый operator workspace уже реализован;
- не возвращаться и к tranche `Resume / Retry / Continue queue`: он уже реализован и подтверждён живыми panel-smoke;
- не возвращаться и к rebalance `top action hint` / `artifact_shortcuts.session_run`: этот tranche уже закрыт и подтверждён safe/read-send live acceptance;
- двигаться дальше по следующему tranche:
  - делать richer profile artifact history поверх уже рабочего artifact center;
  - поднимать sent/draft-level session timeline для profile workspace и session summary;
  - ещё сильнее утончать `gui.py` и `telegram_gui_helpers.py`, чтобы они оставались thin client/readback wrapper над `tool_platform/jobs.py` и `tool_platform/workflows.py`;
  - по возможности уменьшать зависимость artifact center от `session_history_snapshot()` fallback и писать `artifact_paths` прямо в unified `session_run` jobs;
- параллельно продолжать следующий tranche cross-platform adapters из `docs/TELEGRAM_SUPERTOOL_ROADMAP_RU.md`, не пытаясь сразу вытянуть full Telegram Desktop parity на Windows/macOS.

Как работать:
- сначала восстанови контекст по этим файлам, потом меняй код;
- не начинай с рефактора ради рефактора;
- если меняешь поведение проекта, обновляй docs/PROJECT_STATUS_RU.md;
- если меняешь Telegram-хаб, обновляй tools/telegram/*.md;
- коммиты пиши по-русски.

Обязательные проверки после правок:
- PYTHONPATH="$PWD" python3 -m unittest discover -s tests -p 'test_*.py'
- если менялись Python entrypoints:
  - python3 -m py_compile tool_platform/*.py scripts/telegram_portable.py scripts/telegram_invite_executor.py
- если менялись shell wrappers:
  - bash -n tools/telegram/platform/bin/tool-platform tools/telegram/platform/bin/tool-platform-panel tools/telegram/session_runner/bin/telegram-session-runner

Если нужно откатиться к текущей зафиксированной точке:
- git checkout restore-20260502-telegram-control-center
- git -C /home/max/telegram-portable-session-tool checkout restore-20260502-session-tool

В финале каждой заметной задачи:
- обнови /home/max/site-control-kit/docs/PROJECT_STATUS_RU.md
- обнови релевантные Telegram docs
- оставь понятный handoff
- закоммить изменения на русском
```
