# Telegram Tools Agent Guide RU

Этот файл нужен новому агенту, если задача относится именно к Telegram-контуру проекта.

## Сначала Прочитать

1. `/home/max/site-control-kit/AGENTS.md`
2. `/home/max/site-control-kit/docs/PROJECT_STATUS_RU.md`
3. `/home/max/site-control-kit/tools/telegram/README_RU.md`

Потом открыть нужную ветку:
- export: `tools/telegram/export/README_RU.md`
- invite: `tools/telegram/invite_manager/AGENT_GUIDE_RU.md`
- portable helper: `tools/telegram/portable_helper/README_RU.md`
- platform: `tools/telegram/platform/AGENT_GUIDE_RU.md`

## Как Думать О Структуре

- `tools/telegram/` — это хаб видимых Telegram entrypoints;
- `scripts/telegram_*` — это backend entrypoints и runtime logic;
- `tool_platform/*.py` — registry/panel backend, а не Telegram business logic;
- внешний `/home/max/telegram-portable-session-tool` остаётся отдельным repo и подключается через manifest.

## Правило Расширения

Если появляется новый Telegram-инструмент:
1. дать ему видимую папку в `tools/telegram/`;
2. добавить `tool_manifest.json`, если он должен жить в unified panel;
3. не смешивать его runtime-логику с `tool_platform`.

