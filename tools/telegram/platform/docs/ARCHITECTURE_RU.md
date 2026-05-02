# Tool Platform Architecture RU

## Цель

Сделать единый control layer, который:
- не ломает standalone-инструменты;
- умеет показывать их как единый каталог;
- масштабируется через manifests, а не через ручной рефактор GUI на каждый новый кейс.

## Слои

### 1. Инструмент

Отдельный модуль или отдельный репозиторий со своей жизнью:
- код;
- документация;
- собственные артефакты;
- собственный CLI.

Примеры:
- `tools/telegram/invite_manager`
- `tools/telegram/session_runner`

### 2. Manifest

`tool_manifest.json` описывает:
- идентификатор инструмента;
- root directory;
- docs;
- actions;
- capability tags;
- артефакты.

Manifest — это контракт между инструментом и платформой.

### 3. Registry

`registry/tools.json` хранит список manifests.
Registry может ссылаться и на локальные manifests, и на внешние absolute paths.

### 4. Catalog Loader

`tool_platform/catalog.py`:
- читает registry;
- резолвит относительные пути;
- загружает manifests;
- валидирует `tool_id` и `action_id`.

### 5. CLI

`tool_platform/cli.py`:
- показывает список инструментов;
- валидирует registry;
- показывает конкретный tool card;
- умеет безопасно preview/run зарегистрированных actions.

### 6. GUI Panel

`tool_platform/gui.py`:
- показывает зарегистрированные инструменты;
- отображает docs, actions и capability tags;
- даёт profile-first управление portable-пользователями;
- не знает заранее, какие именно Telegram workflow в систему подключены.

## Ключевой Принцип

Новый инструмент добавляется через данные, а не через ручной хардкод интерфейса.

То есть масштабирование выглядит так:

```text
new tool
  -> tool_manifest.json
  -> registry/tools.json
  -> автоматически виден в CLI и GUI
```

## Почему Это Подходит Для Текущей Задачи

Пользователь хотел одновременно:
- оставить `telegram-portable-session-tool` отдельным runtime-инструментом;
- использовать уже существующий `telegram_invite_manager`;
- получить общую Telegram-панель управления.

Manifest + registry слой решает именно эту задачу.
