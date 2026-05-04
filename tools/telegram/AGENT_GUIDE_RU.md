# Telegram Tools Agent Guide RU

Этот файл нужен новому агенту, если задача относится именно к Telegram-контуру проекта.

## Сначала Прочитать

1. `/home/max/site-control-kit/AGENTS.md`
2. `/home/max/site-control-kit/docs/PROJECT_STATUS_RU.md`
3. `/home/max/site-control-kit/tools/telegram/NEXT_CHAT_AGENT_PROMPT_RU.md`
4. `/home/max/site-control-kit/tools/telegram/README_RU.md`
5. `/home/max/site-control-kit/tools/telegram/agent_pack/README_RU.md`
6. `/home/max/site-control-kit/tools/telegram/agent_pack/VERIFICATION_MATRIX_RU.md`
7. `/home/max/site-control-kit/tools/telegram/agent_pack/agent_state.template.json`
8. `~/.site-control-kit/telegram/agent/agent_state.json`

Потом открыть нужную ветку:
- export: `tools/telegram/export/README_RU.md`
- invite: `tools/telegram/invite_manager/AGENT_GUIDE_RU.md`
- portable helper: `tools/telegram/portable_helper/README_RU.md`
- platform: `tools/telegram/platform/AGENT_GUIDE_RU.md`
- session runner: `tools/telegram/session_runner/AGENT_GUIDE_RU.md`

## Как Думать О Структуре

- `tools/telegram/` — это хаб видимых Telegram entrypoints;
- `tools/telegram/agent_pack/` — это agent-layer: defaults, runbook, verification matrix и persistent next-step layer;
- `scripts/telegram_*` — это backend entrypoints и runtime logic;
- `tool_platform/*.py` — registry/panel backend, а не Telegram business logic;
- `tools/telegram/session_runner/` — это видимая оболочка для `/home/max/telegram-portable-session-tool`;
- внешний `/home/max/telegram-portable-session-tool` остаётся отдельным runtime repo.

## Правило Расширения

Если появляется новый Telegram-инструмент:
1. дать ему видимую папку в `tools/telegram/`;
2. добавить `tool_manifest.json`, если он должен жить в unified panel;
3. не смешивать его runtime-логику с `tool_platform`.

## Правило Agent-Layer

Если изменение затрагивает приоритеты, defaults или следующий рекомендуемый шаг для агента:
1. обновить human docs;
2. обновить `tools/telegram/NEXT_CHAT_AGENT_PROMPT_RU.md`;
3. синхронизировать `~/.site-control-kit/telegram/agent/agent_state.json`.
