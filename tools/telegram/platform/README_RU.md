# Tool Platform

Видимая папка unified platform внутри `site-control-kit`.

Эта платформа не заменяет существующие инструменты.
Её задача другая:
- держать registry подключённых инструментов;
- уметь подключать и embedded-модули из `site-control-kit`, и внешние standalone-репозитории;
- давать общую точку входа для оператора и агента;
- открывать графическую control panel без ручной склейки каждого нового инструмента.

## Что Уже Подключено

- `telegram_invite_manager` из текущего репозитория;
- `telegram_portable_helper` как low-level embedded helper;
- `telegram_export` как embedded export pipeline;
- `telegram_portable_session_tool` как отдельный внешний репозиторий `/home/max/telegram-portable-session-tool`.

Оба инструмента продолжают жить как отдельные единицы.
Платформа только регистрирует их manifests и показывает единый catalog.

## Структура

- `registry/tools.json` — список подключённых manifests;
- `AGENT_GUIDE_RU.md` — как агенту развивать platform layer;
- `docs/ARCHITECTURE_RU.md` — архитектура registry/panel;
- `docs/INTEGRATION_GUIDE_RU.md` — как подключать новый инструмент;
- `bin/tool-platform` — CLI доступа к catalog;
- `bin/tool-platform-panel` — Tkinter GUI control panel.

## Быстрый Старт

```bash
cd /home/max/site-control-kit/tools/telegram/platform

./bin/tool-platform validate-registry
./bin/tool-platform list-tools
./bin/tool-platform show-tool --tool-id telegram_invite_manager
./bin/tool-platform show-tool --tool-id telegram_portable_helper
./bin/tool-platform show-tool --tool-id telegram_export
./bin/tool-platform show-tool --tool-id telegram_portable_session_tool
./bin/tool-platform-panel
```

## Что Даёт Registry

Каждый инструмент публикует `tool_manifest.json`, где описаны:
- имя и `tool_id`;
- root path;
- документация;
- базовые operator actions;
- артефакты и capability tags.

Чтобы добавить новый инструмент в платформу, не нужно хардкодить его в GUI.
Достаточно:
1. создать manifest рядом с инструментом;
2. добавить путь к manifest в `registry/tools.json`;
3. при необходимости обновить operator docs.

## Граница

Этот слой не должен превращаться в новую бизнес-логику Telegram.
Он остаётся orchestration/catalog слоем поверх уже существующих отдельных инструментов.
