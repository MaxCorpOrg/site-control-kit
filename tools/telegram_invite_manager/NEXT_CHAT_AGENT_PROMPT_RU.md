# Next Chat Agent Prompt RU

Ниже готовый prompt для нового чата.
Его можно вставить целиком без сокращений.

```text
Работай в проекте /home/max/site-control-kit.

Контекст:
- Основной текущий фокус: Telegram Invite Manager / Telegram Invite Executor / GUI-панель оператора.
- Не начинай с нуля и не переисследуй проект вслепую.
- Продолжай работу с уже подтверждённой точки.

Что нужно сделать первым делом:
1. Перейди в /home/max/site-control-kit
2. Выполни:
   - git status --short --branch
   - git log --oneline -n 15
3. Прочитай в таком порядке:
   - /home/max/AGENTS.md
   - /home/max/site-control-kit/docs/PROJECT_STATUS_RU.md
   - /home/max/site-control-kit/docs/TELEGRAM_INVITE_MANAGER_RU.md
   - /home/max/site-control-kit/docs/TELEGRAM_INVITE_EXECUTOR_RU.md
   - /home/max/site-control-kit/tools/telegram_invite_manager/README.md
   - /home/max/site-control-kit/tools/telegram_invite_manager/AGENT_GUIDE_RU.md
   - /home/max/site-control-kit/tools/telegram_invite_manager/ONE_USER_FLOW_RU.md
   - /home/max/site-control-kit/docs/agent_handoff_ru/00_START_HERE.md
   - затем handoff-пакет по номерам до 10 включительно

Что где лежит:
- Код проекта: /home/max/site-control-kit
- Видимая папка invite-инструмента: /home/max/site-control-kit/tools/telegram_invite_manager
- Основной код invite-инструмента:
  - /home/max/site-control-kit/scripts/telegram_invite_manager.py
  - /home/max/site-control-kit/scripts/telegram_invite_executor.py
  - /home/max/site-control-kit/scripts/telegram_invite_manager_gui.sh
  - /home/max/site-control-kit/scripts/telegram_invite_executor_gui.sh
- Runtime state site-control: /home/max/.site-control-kit
- Invite job data: /home/max/telegram_invite_jobs

Куда можно лезть по этой задаче:
- Можно редактировать:
  - scripts/telegram_invite_manager.py
  - scripts/telegram_invite_executor.py
  - scripts/telegram_invite_manager_gui.sh
  - scripts/telegram_invite_executor_gui.sh
  - scripts/telegram_invite_gui_common.sh
  - tests/test_telegram_invite_manager.py
  - tests/test_telegram_invite_executor.py
  - docs/TELEGRAM_INVITE_MANAGER_RU.md
  - docs/TELEGRAM_INVITE_EXECUTOR_RU.md
  - docs/PROJECT_STATUS_RU.md
  - docs/agent_handoff_ru/*
  - tools/telegram_invite_manager/*
- Не трогай без явной необходимости:
  - /home/max/.site-control-kit
  - /home/max/.cache/site-control-kit
  - unrelated части репозитория
  - /home/max/telegram_ak

Что уже подтверждено live:
- one-user flow существует и работает
- open-chat работает
- inspect-chat умеет снимать видимый member count
- add-contact доходит до реального Add Members / Add popup
- но direct add не подтвердил рост member count
- поэтому без отдельного доказательства нельзя ставить joined
- для ambiguous случая статус ставим requested

Текущие важные live-факты:
- job для живого чата:
  - /home/max/telegram_invite_jobs/chat_Zhirotop_shop
- подтверждённые execution records:
  - /home/max/telegram_invite_jobs/chat_Zhirotop_shop/executions/20260425T052501Z/execution_record.json
  - /home/max/telegram_invite_jobs/chat_Zhirotop_shop/executions/20260425T061336Z/execution_record.json
- current pattern:
  - popup Add закрывается
  - ошибок Telegram не видно
  - member count не растёт автоматически

Как работать:
- Сначала разберись в текущем состоянии, потом вноси изменения
- Не делай массовую автодобавлялку
- Не делай multi-account обход лимитов
- Не помечай joined без отдельного подтверждения
- Перед live add используй inspect-chat
- После live add снова используй inspect-chat
- Если меняешь код, обязательно прогоняй тесты
- После изменений обновляй docs и handoff
- Коммиты пиши по-русски

Обязательные проверки после правок:
- python3 -m py_compile scripts/telegram_invite_manager.py scripts/telegram_invite_executor.py
- bash -n scripts/telegram_invite_manager_gui.sh scripts/telegram_invite_executor_gui.sh scripts/telegram_invite_gui_common.sh tools/telegram_invite_manager/bin/telegram-invite-manager tools/telegram_invite_manager/bin/telegram-invite-executor tools/telegram_invite_manager/bin/gui-manager tools/telegram_invite_manager/bin/gui-executor
- PYTHONPATH="$PWD" python3 -m unittest discover -s tests -p 'test_*.py'

Если задача упирается в live browser bridge:
- проверь:
  - PYTHONPATH="$PWD" python3 -m webcontrol health
  - PYTHONPATH="$PWD" python3 -m webcontrol clients
  - PYTHONPATH="$PWD" python3 -m webcontrol browser tabs
- если хаб не поднят, используй:
  - ./scripts/start_hub.sh

Текущий логичный следующий шаг:
- усиливать не mass-add, а надёжную операторскую панель
- автоматически связывать inspect-chat before/after с add-contact
- добавлять отдельную проверку факта вступления через список участников или другой подтверждаемый сигнал
- улучшать GUI-поток, чтобы оператор мог работать без ручной сборки CLI

В финале каждой заметной задачи:
- обнови docs/PROJECT_STATUS_RU.md
- обнови профильные docs invite-инструмента
- оставь понятный handoff
- закоммить изменения на русском
```

