# Telegram Tools Hub

Это единая видимая папка Telegram-инструментов внутри `site-control-kit`.

Здесь собраны:
- `platform/` — общая registry-driven control panel;
- `invite_manager/` — consent-based invite и add-contact flow;
- `portable_helper/` — low-level Telegram Desktop portable helper;
- `export/` — Telegram export pipeline и batch/chain entrypoints.

Отдельный внешний репозиторий `/home/max/telegram-portable-session-tool` не копируется сюда как код, но подключён в `platform/registry/tools.json` как standalone tool.

## Быстрый Вход

```bash
cd /home/max/site-control-kit/tools/telegram
```

Потом:
- `platform/README_RU.md`
- `invite_manager/README.md`
- `portable_helper/README_RU.md`
- `export/README_RU.md`

## Что Здесь За Что Отвечает

### `platform/`
- единый catalog;
- manifests;
- GUI control panel;
- подключение embedded и external tools.

### `invite_manager/`
- выбор consented пользователей;
- execution plan;
- Telegram Web add-contact;
- Telegram Desktop portable actor flow.

### `portable_helper/`
- import/adopt/status/list portable profiles;
- `open-uri`, `type-text`, `press-keys`;
- accessibility/X11 primitives для Telegram Desktop.

### `export/`
- сбор `@username` из Telegram Web;
- numbered batches;
- safe snapshots;
- chain-runner и GUI wrappers.

## Главная Идея

`tools/telegram/` — это операторский и агентский хаб.
Backend-код по-прежнему может жить в `scripts/`, `tool_platform/` и других проектных слоях, но видимые входные точки Telegram теперь собраны в одном месте.

