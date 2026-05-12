# Telegram Tools Hub

Это единая видимая папка Telegram-инструментов внутри `site-control-kit`.

Здесь собраны:
- `platform/` — Telegram control center и registry-driven panel;
- `agent_pack/` — агентский runbook, defaults и machine-readable entry layer;
- `invite_manager/` — consent-based invite и add-contact flow;
- `portable_helper/` — low-level Telegram Desktop portable helper;
- `export/` — Telegram export pipeline и batch/chain entrypoints;
- `session_runner/` — visible wrapper для embedded Telegram Desktop session-runner.

Session-runner runtime теперь встроен в `telegram_portable_session_tool/`, а локальная папка `session_runner/` остаётся operator-facing wrapper/manifest слоем.

## Быстрый Вход

```bash
cd /home/max/site-control-kit/tools/telegram
```

Потом:
- `NEXT_CHAT_AGENT_PROMPT_RU.md`
- `agent_pack/README_RU.md`
- `platform/README_RU.md`
- `invite_manager/README.md`
- `portable_helper/README_RU.md`
- `export/README_RU.md`
- `session_runner/README_RU.md`

## Что Здесь За Что Отвечает

### `platform/`
- единый Telegram catalog;
- platform-aware manifests и capability matrix;
- unified jobs / profile locks / doctor / capabilities CLI foundation;
- manifests;
- GUI control panel;
- выбор portable-пользователей из выпадающего списка;
- импорт новых пользователей по `tdata.zip`;
- adopt уже существующих Telegram portable-папок;
- первый большой операторский режим `Добавить контакты из TXT` для реального добавления username в личные контакты выбранного portable-профиля;
- подключение embedded tools и visible wrappers.

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

### `session_runner/`
- random walk по уже существующим группам и контактам Telegram Desktop;
- controlled auto-send только по явному allowlist-у;
- thin wrapper вокруг embedded package `telegram_portable_session_tool`.

## Главная Идея

`tools/telegram/` — это операторский и агентский хаб.
Backend-код по-прежнему может жить в `scripts/`, `tool_platform/` и других проектных слоях, но видимые входные точки Telegram теперь собраны в одном месте.

## Точка Входа Для Следующего Агента

Если нужно продолжить работу ровно с текущего checkpoint, начинать нужно с:

- `tools/telegram/NEXT_CHAT_AGENT_PROMPT_RU.md`
- `tools/telegram/agent_pack/README_RU.md`
- `tools/telegram/agent_pack/VERIFICATION_MATRIX_RU.md`
- `tools/telegram/agent_pack/agent_state.template.json`
- `~/.site-control-kit/telegram/agent/agent_state.json`

Это не общая справка по проекту, а зафиксированная точка продолжения именно с текущего состояния Telegram control center.
