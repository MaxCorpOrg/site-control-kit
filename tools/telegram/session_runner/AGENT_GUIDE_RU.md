# Telegram Session Runner Agent Guide RU

Этот файл нужен, если задача относится к Telegram Desktop session-runner внутри общего Telegram-хаба.

## Что Сначала Открыть

1. `/home/max/site-control-kit/AGENTS.md`
2. `/home/max/site-control-kit/docs/PROJECT_STATUS_RU.md`
3. `/home/max/site-control-kit/tools/telegram/session_runner/README_RU.md`
4. `/home/max/site-control-kit/telegram_portable_session_tool/`

## Как Думать Об Этом Слое

- `tools/telegram/session_runner/` в `site-control-kit` — это видимая оболочка и registry entry.
- Реальный CLI и runtime теперь встроены в package `telegram_portable_session_tool`.
- `tool_manifest.json` и `bin/telegram-session-runner` должны оставаться тонкими и предсказуемыми.

## Что Здесь Можно Менять

- manifest;
- wrapper scripts;
- локальную Telegram-хаб документацию;
- привязку к общей Telegram control panel.

## Что Здесь Не Нужно Делать

- не дублировать runtime-код session-runner в wrapper-слое;
- не переносить сюда low-level Desktop primitives из `scripts/telegram_portable.py`;
- не расходиться с embedded package по operator contract без явной синхронизации.
