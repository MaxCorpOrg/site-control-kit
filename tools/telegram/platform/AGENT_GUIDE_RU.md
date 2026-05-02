# Telegram Control Center Agent Guide RU

Этот документ нужен новому агенту, который работает именно с Telegram control center слоем.

## Что Это За Слой

`tools/telegram/platform` — это registry-driven control layer для локальных Telegram workflow.

Он нужен, чтобы:
- отдельные инструменты оставались самостоятельными;
- новые инструменты можно было добавлять без переписывания GUI;
- агент видел не просто разрозненные скрипты, а структурированный catalog;
- оператор мог выбирать нужного Telegram portable-пользователя без ручного ввода путей.

## Что Считать Источником Правды

1. `registry/tools.json`
2. `tool_manifest.json` каждого подключённого инструмента
3. `tool_platform/catalog.py`
4. `tool_platform/cli.py`
5. `tool_platform/gui.py`
6. `tool_platform/telegram_profiles.py`

## Как Добавлять Новый Инструмент

1. Не вшивать его список прямо в GUI.
2. Создать рядом с инструментом `tool_manifest.json`.
3. В manifest указать:
   - `tool_id`
   - `display_name`
   - `root_dir`
   - docs paths
   - operator actions
4. Добавить путь к manifest в `registry/tools.json`.
5. Обновить `README_RU.md`, если инструмент значимый для оператора.
6. Если инструмент использует Telegram Desktop portable actor, подумать, нужен ли ему выбор профиля из общей панели, а не отдельная форма.

## Что Нельзя Делать

- Нельзя хардкодить список инструментов прямо в `gui.py`.
- Нельзя ломать standalone-режим инструмента ради unified panel.
- Нельзя превращать platform layer в место, где живёт Telegram-specific runtime logic.
- Нельзя плодить отдельные сложные экраны там, где хватает простого profile-first управления и manifest actions.

## Следующий Масштабируемый Шаг

Если появится ещё один локальный инструмент, правильный путь:
- сохранить его как отдельную единицу;
- дать ему свой manifest;
- зарегистрировать его в `tools/telegram/platform/registry/tools.json`.
