# Telegram Export Agent Guide RU

Этот guide нужен агенту, если задача относится к Telegram export pipeline.

## Сначала Прочитать

1. `/home/max/site-control-kit/AGENTS.md`
2. `/home/max/site-control-kit/docs/PROJECT_STATUS_RU.md`
3. `/home/max/site-control-kit/tools/telegram/export/README_RU.md`
4. `/home/max/site-control-kit/docs/TELEGRAM_CLIENT_ROADMAP_RU.md`

## Когда Идти Сюда

Если задача связана с:
- `@username` export из Telegram Web;
- `identity_history.json`;
- `discovery_state.json`;
- safe snapshots;
- numbered batches;
- chain-runner.

## Что Не Делать Этим Слоем

- не смешивать export-поток с invite manager;
- не использовать export как direct-add/send инструмент;
- если задача про Telegram Desktop portable, смотреть `portable_helper` или `invite_manager`.

