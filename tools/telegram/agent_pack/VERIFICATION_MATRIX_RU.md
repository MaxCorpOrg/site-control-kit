# Verification Matrix RU

Этот файл нужен следующему агенту как короткая матрица проверок по слоям Telegram supertool.

## Обязательный минимум после заметной задачи

1. `PYTHONPATH="$PWD" python3 -m unittest discover -s tests -p 'test_*.py'`
2. `git diff --check`

## Если менялись foundation-модули control plane

Файлы:
- `tool_platform/jobs.py`
- `tool_platform/locks.py`
- `tool_platform/workflows.py`
- `tool_platform/agent_state.py`
- `tool_platform/catalog.py`
- `tool_platform/cli.py`

Проверить:
1. `python3 -m py_compile tool_platform/*.py`
2. `PYTHONPATH="$PWD" python3 -m unittest tests.test_tool_platform`
3. `./tools/telegram/platform/bin/tool-platform validate-registry`
4. `./tools/telegram/platform/bin/tool-platform doctor`
5. `./tools/telegram/platform/bin/tool-platform capabilities`

## Если менялись GUI/orchestration слои панели

Файлы:
- `tool_platform/gui.py`
- `tool_platform/telegram_gui_helpers.py`

Проверить:
1. `python3 -m py_compile tool_platform/gui.py tool_platform/telegram_gui_helpers.py`
2. `PYTHONPATH="$PWD" python3 -m unittest tests.test_tool_platform`
3. `./tools/telegram/platform/bin/tool-platform-panel`
4. Для smoke на Linux подтвердить окно через `wmctrl -lx` или `xwininfo`

## Если менялись Invite/Desktop flows

Файлы:
- `scripts/telegram_invite_executor.py`
- `scripts/telegram_invite_manager.py`
- `tools/telegram/invite_manager/*`

Проверить:
1. `python3 -m py_compile scripts/telegram_invite_executor.py scripts/telegram_invite_manager.py`
2. `PYTHONPATH="$PWD" python3 -m unittest tests.test_telegram_invite_executor tests.test_telegram_invite_manager`
3. `bash -n tools/telegram/invite_manager/bin/telegram-invite-manager tools/telegram/invite_manager/bin/telegram-invite-executor`

## Если менялись portable/session flows

Файлы:
- `scripts/telegram_portable.py`
- `tools/telegram/session_runner/*`
- standalone runtime `/home/max/telegram-portable-session-tool/*`

Проверить:
1. `python3 -m py_compile scripts/telegram_portable.py`
2. `bash -n tools/telegram/session_runner/bin/telegram-session-runner`
3. Если менялся standalone runtime:
   - `python3 -m py_compile telegram_portable_session_tool/*.py`
   - `PYTHONPATH=/home/max/telegram-portable-session-tool python3 -m unittest discover -s tests -p 'test_*.py'`

## Если менялись manifests/platform metadata

Файлы:
- `tools/telegram/*/tool_manifest.json`
- `tools/telegram/platform/registry/tools.json`

Проверить:
1. `./tools/telegram/platform/bin/tool-platform validate-registry`
2. `./tools/telegram/platform/bin/tool-platform list-tools`
3. `./tools/telegram/platform/bin/tool-platform show-tool --tool-id <tool_id>`

## Если менялся cross-platform adapter layer

Файлы:
- `tool_platform/platform_adapters/*`

Проверить:
1. `python3 -m py_compile tool_platform/platform_adapters/*.py`
2. `PYTHONPATH="$PWD" python3 -m unittest tests.test_tool_platform`
3. `./tools/telegram/platform/bin/tool-platform doctor`
4. `./tools/telegram/platform/bin/tool-platform capabilities`

## Live Telegram smoke

Делать только если изменение затрагивает реальный operator lane.

Сохранять в `docs/PROJECT_STATUS_RU.md`:
- путь к `run.json` или `batch_contact_add.json`
- путь к screenshot/log, если он подтверждает live-fix
- какой профиль использовался
- что именно считалось критерием успеха
