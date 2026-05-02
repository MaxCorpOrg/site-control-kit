# Telegram Session Runner Agent Guide RU

Этот файл нужен, если задача относится к Telegram Desktop session-runner внутри общего Telegram-хаба.

## Что Сначала Открыть

1. `/home/max/site-control-kit/AGENTS.md`
2. `/home/max/site-control-kit/docs/PROJECT_STATUS_RU.md`
3. `/home/max/site-control-kit/tools/telegram/session_runner/README_RU.md`
4. `/home/max/telegram-portable-session-tool/AGENTS.md`
5. `/home/max/telegram-portable-session-tool/README_RU.md`

## Как Думать Об Этом Слое

- `tools/telegram/session_runner/` в `site-control-kit` — это видимая оболочка и registry entry.
- Реальный CLI и runtime лежат в `/home/max/telegram-portable-session-tool`.
- `tool_manifest.json` и `bin/telegram-session-runner` должны оставаться тонкими и предсказуемыми.

## Что Здесь Можно Менять

- manifest;
- wrapper scripts;
- локальную Telegram-хаб документацию;
- привязку к общей Telegram control panel.

## Что Здесь Не Нужно Делать

- не дублировать runtime-код session-runner в wrapper-слое без отдельного решения;
- не переносить сюда low-level Desktop primitives из `scripts/telegram_portable.py`;
- не расходиться с standalone repo по operator contract без явной синхронизации.
