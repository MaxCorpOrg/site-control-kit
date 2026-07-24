# Планировщик сессий Telegram

Видимая папка session-runner инструмента внутри `site-control-kit`.

Этот слой нужен, чтобы Telegram Desktop random-walk и controlled auto-send были видны в общем Telegram-хабе рядом с `invite_manager`, `portable_helper` и `export`.

Runtime-код теперь встроен в `site-control-kit` как package:

- `telegram_portable_session_tool/`

Но для оператора и агента вход теперь идёт через эту папку:

- `bin/telegram-session-runner`
- `tool_manifest.json`

## Что Делает Инструмент

- ходит по уже существующим группам и контактам Telegram Desktop portable-профиля;
- поддерживает random walk по текущему sidebar-пулу чатов;
- отделяет общий visit-пул от allowlist-а для сообщений;
- умеет controlled auto-send только по явному списку адресатов;
- работает без Telegram API через low-level Desktop actions.

## Быстрый Старт

```bash
cd /home/max/site-control-kit/tools/telegram/session_runner

./bin/telegram-session-runner --help
./bin/telegram-session-runner sync-preview \
  --config examples/session.example.json
```

## Важная Граница

Это visible wrapper над embedded package.

Release package включает runtime-код без приватных `runs`, `.state`, `.git` и пользовательских конфигов.
