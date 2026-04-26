# Project Workflow RU

Этот документ задаёт обязательный порядок работы для любого агента и любого нового чата в репозитории `site-control-kit`.

## Цель
Нельзя работать с проектом как с разрозненным набором скриптов. Работа всегда должна идти по одному и тому же циклу:
- сначала понять текущее состояние;
- потом посмотреть, что уже сделано;
- потом менять код;
- потом прогонять проверки;
- потом обновлять handoff-документацию.

## Обязательный Порядок Чтения Перед Работой
Прочитать в таком порядке:
1. `AGENTS.md`
2. `START_HERE_AGENT_RU.md`
3. `docs/agent_handoff_ru/00_START_HERE.md`
4. весь пакет `docs/agent_handoff_ru/` по порядку
5. `docs/PROJECT_WORKFLOW_RU.md`
6. `docs/PROJECT_STATUS_RU.md`
7. `README.md`
8. `BROWSER_QUICKSTART.md`
9. `docs/AI_MAINTAINER_GUIDE.md`
10. Для Telegram-задач: `docs/TELEGRAM_CLIENT_ROADMAP_RU.md`
11. Для задач про Linux Telegram Desktop portable-профили и `tdata.zip`: `docs/TELEGRAM_PORTABLE_RU.md`

Если задача затрагивает browser bridge, после чтения документации обязательно посмотреть последние изменения и текущее дерево.

Ключевая идея этого порядка:
- новый агент не должен начинать "просто исследование проекта";
- сначала он обязан понять, где проект уже остановился;
- только потом он может продолжать работу.

## Старт Любой Задачи
Перед правками выполнить:

```bash
cd /home/max/site-control-kit
git status --short --branch
git log --oneline -n 15
```

После этого просмотреть `docs/PROJECT_STATUS_RU.md` и понять:
- что уже закрыто;
- что ещё открыто;
- где текущий риск;
- какой следующий приоритет уже намечен.

## Telegram-Старт Перед Любой Диагностикой
Если задача связана с Telegram-экспортом, до изменения кода нужно просмотреть:

```bash
# примеры путей; chat-id подставляется по факту
/home/max/telegram_contact_batches/chat_<id>/latest_full.md
/home/max/telegram_contact_batches/chat_<id>/latest_safe.md
/home/max/telegram_contact_batches/chat_<id>/identity_history.json
/home/max/telegram_contact_batches/chat_<id>/discovery_state.json
/home/max/telegram_contact_batches/chat_<id>/runs/<latest>/run.json
/home/max/telegram_contact_batches/chat_<id>/runs/<latest>/export.log
/home/max/telegram_contact_batches/chat_<id>/runs/<latest>/export_stats.json
```

Нельзя делать вывод по одному `latest_full.txt`. Нужно понять, на каком уровне проблема:
- discovery/scroll;
- deep (`mention` / `url` / `profile`);
- history backfill;
- safe/quarantine layer;
- batch layer.

## Обязательный Цикл После Каждой Завершённой Правки
После каждой законченной задачи агент обязан:
1. Прогнать проверки.
2. Просмотреть результат прогонов.
3. Если задача затрагивала Telegram или browser bridge, просмотреть живые артефакты (`run.json`, `export.log`, `export_stats.json`).
4. Обновить `docs/PROJECT_STATUS_RU.md`.
5. Только потом считать задачу завершённой.

## Обязательные Проверки
Всегда запускать из корня репозитория:

```bash
PYTHONPATH="$PWD" python3 -m unittest discover -s tests -p 'test_*.py'
```

Дополнительно:

### Если менялись Python-файлы
```bash
python3 -m py_compile <изменённые_python_файлы>
```

### Если менялись shell-скрипты
```bash
bash -n <изменённые_shell_скрипты>
```

### Если меняется CLI
```bash
PYTHONPATH="$PWD" python3 -m webcontrol --help
PYTHONPATH="$PWD" python3 -m webcontrol browser --help
```

### Если меняется живой browser/Telegram контур
Нужен хотя бы один живой smoke с артефактами. Минимум нужно сохранить ссылку на:
- `run.json`
- `export.log`
- если есть, `export_stats.json`

## Правило Завершённых Задач
Любой агент должен перед новой задачей просмотреть, что уже завершено.
Источник истины для этого проекта:
1. `docs/PROJECT_STATUS_RU.md`
2. последние коммиты `git log --oneline -n 15`
3. для Telegram — последние `runs/<timestamp>/run.json`

Если задача уже была частично закрыта раньше, нельзя начинать с нуля. Нужно сначала встроиться в существующее состояние.

## Правило Handoff
После любого заметного блока работы в `docs/PROJECT_STATUS_RU.md` нужно обновить:
- `Сделано`
- `Проверено`
- `Текущие проблемы`
- `Следующий приоритет`

Новый агент должен иметь возможность открыть только `AGENTS.md` и `docs/PROJECT_STATUS_RU.md`, чтобы сразу понять, что происходит в проекте.

## Правило Коммитов
Если задача дошла до коммита:
- писать сообщение коммита по-русски;
- коммит должен отражать один логический блок, а не смесь несвязанных изменений.

## Что Считать Нарушением Workflow
Нарушением считается:
- менять код без просмотра `docs/PROJECT_STATUS_RU.md`;
- завершать задачу без тестов;
- не обновить handoff после серьёзных изменений;
- по Telegram делать выводы без просмотра `run.json` и `export.log`;
- игнорировать уже существующую историю `identity_history.json` и `discovery_state.json` при анализе проблемы.
