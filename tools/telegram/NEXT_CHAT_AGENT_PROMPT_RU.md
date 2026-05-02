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
  - основной checkpoint commit: 39b9c47
  - смысл коммита: Telegram control center с профилями и session runner
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
- /home/max/site-control-kit/tools/telegram/README_RU.md
- /home/max/site-control-kit/tools/telegram/platform/README_RU.md
- /home/max/site-control-kit/docs/PROJECT_STATUS_RU.md

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
- не строить новую большую панель с множеством экранов;
- довести profile-aware shortcuts:
  - чтобы выбранный portable-профиль легче подставлялся в invite/session workflows;
- добавить простые live summaries по последним run/job артефактам там, где это реально экономит ручную работу;
- сохранять отдельность инструментов и manifest-driven интеграцию.

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
