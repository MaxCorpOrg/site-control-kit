# Telegram Portable Helper Agent Guide RU

Этот guide нужен агенту, если задача относится к low-level Telegram Desktop portable layer.

## Сначала Прочитать

1. `/home/max/site-control-kit/AGENTS.md`
2. `/home/max/site-control-kit/docs/PROJECT_STATUS_RU.md`
3. `/home/max/site-control-kit/tools/telegram/portable_helper/README_RU.md`
4. `/home/max/site-control-kit/docs/TELEGRAM_PORTABLE_RU.md`

## Когда Идти Сюда

Если задача звучит так:
- импортировать `tdata.zip`;
- принять в управление существующий portable profile;
- проверить `status`/`log-diagnose`;
- отправить X11 keys, click или accessibility action в Telegram Desktop.

## Что Не Делать Этим Слоем

- не держать тут consent/state логику invite flow;
- не превращать helper в массовый action-runner;
- если задача уже на invite/session уровне, сначала смотреть `invite_manager` или внешний `telegram-portable-session-tool`.

