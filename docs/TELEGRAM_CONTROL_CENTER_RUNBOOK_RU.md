# Telegram Control Center: Maintainer Runbook

Этот документ для поддерживающего агента или техоператора.

Он нужен для:
- historical repair;
- canonical path recovery;
- live диагностики `profile-health`;
- работы с unified jobs и runtime root.

## Канонические Пути

Runtime root:

`/home/max/site-control-kit/runtime/telegram`

Ключевые пути:
- profiles:
  - `runtime/telegram/profiles/`
- invite jobs:
  - `runtime/telegram/invite_jobs/`
- session configs/state/runs:
  - `runtime/telegram/session/`
- unified jobs / locks / agent state:
  - `runtime/telegram/state/`
- panel log:
  - `runtime/telegram/logs/panel/telegram-control-center-panel.log`

## Основные Диагностические Команды

```bash
cd /home/max/site-control-kit

./tools/telegram/platform/bin/tool-platform doctor
./tools/telegram/platform/bin/tool-platform capabilities
./tools/telegram/platform/bin/tool-platform list-locks
./tools/telegram/platform/bin/tool-platform list-jobs --limit 10
./tools/telegram/platform/bin/tool-platform show-job --job-id <job_id>
./tools/telegram/platform/bin/tool-platform show-artifacts --job-id <job_id>
./tools/telegram/platform/bin/tool-platform profile-health --profile-name AK3 --profile-dir /home/max/site-control-kit/runtime/telegram/profiles/TelegramPortable-AK3
```

## Explicit Repair: Invite

Preview:

```bash
./tools/telegram/platform/bin/tool-platform repair-invite-artifacts --profile-name AK3 --profile-dir /home/max/site-control-kit/runtime/telegram/profiles/TelegramPortable-AK3
```

Apply:

```bash
./tools/telegram/platform/bin/tool-platform repair-invite-artifacts --profile-name AK3 --profile-dir /home/max/site-control-kit/runtime/telegram/profiles/TelegramPortable-AK3 --apply
```

Что делает:
- canonicalize `invite_job_dir`;
- canonicalize `last_invite_run_dir`;
- backfill missing invite `artifact_paths`;
- сохраняет явный operator-controlled repair path вместо скрытой автоперезаписи.

## Explicit Repair: Session

Preview:

```bash
./tools/telegram/platform/bin/tool-platform repair-session-artifacts --profile-name AK3 --profile-dir /home/max/site-control-kit/runtime/telegram/profiles/TelegramPortable-AK3
```

Apply:

```bash
./tools/telegram/platform/bin/tool-platform repair-session-artifacts --profile-name AK3 --profile-dir /home/max/site-control-kit/runtime/telegram/profiles/TelegramPortable-AK3 --apply
```

## Recovery: Профиль Запущен, Но Окна Нет

Если `profile-health` показывает:
- `running = true`
- `attach_status = running_without_window`

не нужно ослаблять attach gating.

Правильный порядок:
1. зафиксировать текущее состояние через `profile-health`;
2. relaunch project-local профиля;
3. убедиться, что `attach_status = exact_window`;
4. только потом делать live invite/session/combined.

## Recovery: История Или Артефакты Указывают На Legacy Path

Порядок:
1. сначала `show-job`;
2. затем `show-artifacts`;
3. затем preview соответствующего repair;
4. и только если `unresolved = 0`, делать `--apply`.

Нельзя молча перезаписывать history просто при readback.

## Что Считать Release Gate

Для текущего product-grade цикла release gate такой:
- оператор понимает, где импортировать, запускать, скрывать и удалять профиль;
- `invite` живёт на canonical `runtime/telegram`;
- `session` и `combined` видят понятный progress/readback;
- historical artifacts открываются предсказуемо через explicit repair path;
- `gui.py` остаётся thin render/form-state слоем.

## Проверки После Кода

```bash
cd /home/max/site-control-kit
PYTHONPATH=\"$PWD\" python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m py_compile tool_platform/gui.py tool_platform/telegram_gui_helpers.py tool_platform/jobs.py tool_platform/workflows.py tool_platform/cli.py
git diff --check
```
