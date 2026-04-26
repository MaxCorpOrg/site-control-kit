# START HERE: Agent Entry Point

Этот файл — короткая входная точка для любого нового агента, который впервые заходит в репозиторий `site-control-kit` или начинает новый чат без контекста.

Если ты агент и открыл проект, сначала прочитай именно этот файл, а уже потом иди глубже.

## Что Это За Проект
`site-control-kit` — локальная платформа управления браузером и прикладными сценариями поверх него.

Внутри проекта:
- Python-хаб `webcontrol`;
- CLI `sitectl` / `python3 -m webcontrol`;
- MV3 browser extension;
- Telegram automation scripts;
- отдельные operator tools и handoff-документация.

Проект уже не находится на стадии "просто прототипа".
Нельзя заходить в него как в пустую папку и начинать работу с нуля.

`AGENTS.md` теперь содержит не только правила работы, но и расширенную capability-map проекта:
- какие подсистемы уже есть;
- что именно каждая из них умеет;
- в какие файлы идти по каждому типу задачи.

## Главное Правило Для Любого Нового Агента
Твоя первая задача не "что-нибудь сделать".
Твоя первая задача:
1. понять, на чём остановился предыдущий агент;
2. определить последний завершённый блок;
3. понять текущий риск;
4. продолжать именно с этой точки, а не уходить в соседнюю случайную задачу.

## Обязательный Порядок Чтения
Читай в таком порядке:

1. `AGENTS.md`
2. `START_HERE_AGENT_RU.md`
3. `docs/agent_handoff_ru/00_START_HERE.md`
4. весь пакет `docs/agent_handoff_ru/` по порядку `00..10`
5. `docs/PROJECT_WORKFLOW_RU.md`
6. `docs/PROJECT_STATUS_RU.md`
7. `BROWSER_QUICKSTART.md`
8. `docs/AI_MAINTAINER_GUIDE.md`
9. `docs/API.md`
10. `docs/ARCHITECTURE.md`
11. `docs/EXTENSION.md`
12. если задача про Telegram roadmap/export: `docs/TELEGRAM_CLIENT_ROADMAP_RU.md`
13. если задача про Linux Telegram Desktop profile из `tdata.zip`: `docs/TELEGRAM_PORTABLE_RU.md`

## Что Нужно Понять До Любых Правок
До правок ты обязан ответить себе на четыре вопроса:

1. Что уже сделано в проекте?
Источник истины: `docs/PROJECT_STATUS_RU.md`

2. Где проект остановился в последний раз?
Источник истины: секции `Текущие Проблемы`, `Следующий Приоритет`, `Последний Подтверждённый Полезный Результат` в `docs/PROJECT_STATUS_RU.md`

3. Что изменялось недавно?
Источник истины:

```bash
git status --short --branch
git log --oneline -n 15
```

4. Какие task-specific документы нужно открыть перед действием?
Примеры:
- Telegram export: latest run artifacts + `docs/TELEGRAM_CLIENT_ROADMAP_RU.md`
- Telegram invite: `docs/TELEGRAM_INVITE_MANAGER_RU.md` и `docs/TELEGRAM_INVITE_EXECUTOR_RU.md`
- Telegram Desktop portable: `docs/TELEGRAM_PORTABLE_RU.md`

## Как Правильно Продолжать Работу
Правильная модель такая:

- не начинать заново исследование проекта, если уже есть handoff;
- не перепридумывать следующий шаг, если он уже зафиксирован в `docs/PROJECT_STATUS_RU.md`;
- не уходить в соседний рефактор, если текущий приоритет уже указан;
- не делать вывод по одному файлу или одному артефакту;
- после своей задачи обязательно обновить `docs/PROJECT_STATUS_RU.md`, чтобы следующий агент снова продолжил с правильной точки.

## Быстрый Старт Перед Любой Работой

```bash
cd /home/max/site-control-kit
git status --short --branch
git log --oneline -n 15
```

Потом:
- открыть `docs/PROJECT_STATUS_RU.md` целиком;
- определить последний завершённый блок;
- определить следующий приоритет;
- только после этого идти в код.

## Если Задача Про Browser Bridge
Сначала проверить живой контур:

```bash
PYTHONPATH="$PWD" python3 -m webcontrol clients
PYTHONPATH="$PWD" python3 -m webcontrol browser tabs
```

## Если Задача Про Telegram
До изменения кода сначала смотреть не только документацию, но и артефакты последнего run:
- `latest_full.md`
- `latest_safe.md`
- последний `run.json`
- последний `export.log`
- если есть, `export_stats.json`
- `identity_history.json`
- `discovery_state.json`

## Если Задача Про Telegram Desktop Portable
Не собирать профиль вручную, если уже есть `tdata.zip`.
Сначала использовать:
- `scripts/telegram_portable.py`
- `scripts/telegram_portable_gui.sh`
- `docs/TELEGRAM_PORTABLE_RU.md`

## Когда Работа Считается Завершённой
Работа не завершена, если:
- не прогнаны проверки;
- не обновлён `docs/PROJECT_STATUS_RU.md`;
- не зафиксировано, что сделано и что следующий агент должен делать дальше.

Этот файл должен оставаться короткой "входной дверью".
Детали лежат в `AGENTS.md`, handoff-пакете и `docs/PROJECT_STATUS_RU.md`.
