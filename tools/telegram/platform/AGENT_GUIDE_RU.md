# Tool Platform Agent Guide RU

Этот документ нужен новому агенту, который работает именно с unified platform слоем.

## Что Это За Слой

`tools/telegram/platform` — это registry-driven control layer для локальных operator tools.

Он нужен, чтобы:
- отдельные инструменты оставались самостоятельными;
- новые инструменты можно было добавлять без переписывания GUI;
- агент видел не просто разрозненные скрипты, а структурированный catalog.

## Что Считать Источником Правды

1. `registry/tools.json`
2. `tool_manifest.json` каждого подключённого инструмента
3. `tool_platform/catalog.py`
4. `tool_platform/cli.py`
5. `tool_platform/gui.py`

## Как Добавлять Новый Инструмент

1. Не вшивать его прямо в GUI.
2. Создать рядом с инструментом `tool_manifest.json`.
3. В manifest указать:
   - `tool_id`
   - `display_name`
   - `root_dir`
   - docs paths
   - operator actions
4. Добавить путь к manifest в `registry/tools.json`.
5. Обновить `README_RU.md`, если инструмент значимый для оператора.

## Что Нельзя Делать

- Нельзя хардкодить список инструментов прямо в `gui.py`.
- Нельзя ломать standalone-режим инструмента ради unified panel.
- Нельзя превращать platform layer в место, где живёт Telegram-specific runtime logic.

## Следующий Масштабируемый Шаг

Если появится ещё один локальный инструмент, правильный путь:
- сохранить его как отдельную единицу;
- дать ему свой manifest;
- зарегистрировать его в `tools/telegram/platform/registry/tools.json`.

