# Центр управления Telegram

Видимая папка Telegram control center внутри `site-control-kit`.

Этот слой не заменяет существующие инструменты.
Его задача другая:
- держать registry подключённых инструментов;
- давать одну простую Telegram-точку входа для оператора и агента;
- открывать простую русскую панель без перегруза лишними экранами;
- позволять выбирать пользователя из списка portable-профилей и добавлять новых по `tdata.zip`.

## Что Уже Подключено

- `telegram_invite_manager` из текущего репозитория;
- `telegram_portable_helper` как low-level embedded helper;
- `telegram_export` как embedded export pipeline;
- `telegram_session_runner` как wrapper вокруг `/home/max/telegram-portable-session-tool`.

Все workflow продолжают жить как отдельные единицы.
Панель поверх них специально упрощена под две основные операторские кнопки:
- `Инвайты по списку`
- `Сессия и сообщения`

Low-level helper и export остаются в registry и CLI, но не засоряют основной экран.

## Структура

- `registry/tools.json` — список подключённых manifests;
- `AGENT_GUIDE_RU.md` — как агенту развивать platform layer;
- `docs/ARCHITECTURE_RU.md` — архитектура registry/panel;
- `docs/INTEGRATION_GUIDE_RU.md` — как подключать новый инструмент;
- `bin/tool-platform` — CLI доступа к catalog;
- `bin/tool-platform-panel` — Tkinter GUI-панель.

## Быстрый Старт

```bash
cd /home/max/site-control-kit/tools/telegram/platform

./bin/tool-platform validate-registry
./bin/tool-platform list-tools
./bin/tool-platform show-tool --tool-id telegram_invite_manager
./bin/tool-platform show-tool --tool-id telegram_portable_helper
./bin/tool-platform show-tool --tool-id telegram_export
./bin/tool-platform show-tool --tool-id telegram_session_runner
./bin/tool-platform-panel
```

Что умеет панель сейчас:
- показывает список уже существующих Telegram portable-пользователей;
- даёт выбрать нужного пользователя из dropdown;
- показывает статус выбранного профиля;
- умеет импортировать новый профиль по `tdata.zip`;
- умеет принять в управление уже существующую portable-папку;
- показывает две большие кнопки режима:
  - `Инвайты по списку`
  - `Сессия и сообщения`
- открывает только один рабочий экран за раз, чтобы оператор не путался;
- в режиме инвайтов умеет загрузить `.txt` / `.csv` / `.json` список username и создать invite-job;
- в режиме сессии умеет загрузить список адресатов из session-config, отредактировать его и запустить сессию кнопкой;
- рендерит детали профиля и результаты в читаемых текстовых блоках, а не в тесных таблицах.

## Что Даёт Registry

Каждый инструмент публикует `tool_manifest.json`, где описаны:
- имя и `tool_id`;
- root path;
- документация;
- базовые operator actions;
- артефакты и capability tags.

Чтобы добавить новый инструмент в платформу, не нужно ломать текущую панель.
Достаточно:
1. создать manifest рядом с инструментом;
2. добавить путь к manifest в `registry/tools.json`;
3. при необходимости обновить operator docs;
4. отдельно решить, нужен ли этому инструменту собственный операторский режим в панели или ему достаточно CLI/registry-видимости.

## Граница

Этот слой не должен превращаться в место, где живёт runtime конкретного Telegram workflow.
Он остаётся orchestration/catalog слоем плюс простой Telegram-ориентированный экран:
- сверху выбор и импорт профилей;
- ниже два понятных рабочих режима;
- low-level и вспомогательные инструменты остаются под капотом.
