# Testing And Acceptance

## Базовое Обязательное Правило
После каждой завершённой задачи запускать:

```bash
PYTHONPATH="$PWD" python3 -m unittest discover -s tests -p 'test_*.py'
```

На текущем этапе полный suite должен быть зелёным.

## Если Менялись Python Entry Points
Дополнительно:

```bash
python3 -m py_compile <изменённые python-файлы>
```

## Если Менялись Shell Scripts
Дополнительно:

```bash
bash -n <изменённые shell-файлы>
```

## Если Менялся Browser / Telegram Контур
Нужен живой smoke.
Минимум должен существовать хотя бы один из наборов:
- `run.json`
- `export.log`
- `export_stats.json`

## Что Считать Приёмкой Для Telegram Шага
Задача считается реально проверенной, если есть:
1. зелёные unit tests;
2. зелёный shell syntax / py_compile при необходимости;
3. хотя бы один live artifact path;
4. обновлённый `docs/PROJECT_STATUS_RU.md`.

## Что Недостаточно
Недостаточно просто увидеть новый `.txt`.
Нужно понять:
- этот результат собран deep-path или backfill;
- safe layer что-то вычистил или нет;
- latest guard не затёр useful snapshot;
- run не остановился на `expired no delivery` или bad redirect.

## Acceptance Для Deep-Path Изменений
Хорошая приёмка deep-изменения:
- в `export.log` видно новый ход;
- в `export_stats.json` меняется `deep_updated_total`;
- в `run.json` видно итоговые изменения;
- в status docs записан вывод, а не только путь к файлу.

## Acceptance Для Shell / Orchestration Изменений
Хорошая приёмка orchestration-изменения:
- тест на helper-функцию;
- тест на `main()` если есть CLI/script wrapper;
- live smoke на реальном чате или хотя бы на реальном hub client.

## Acceptance Для `public_phones` Flow
Хорошая приёмка phone-flow изменения:
- targeted tests закрывают helper/runtime/backend/UI/history;
- полный `discover` остаётся зелёным;
- есть реальные артефакты `*_phones.md`, `*_phones.txt`, `*_phones.json`;
- есть хотя бы один live `Primary tdata` smoke с сохранёнными `summary.json`, `artifacts.json`, `events.jsonl`;
- отдельно зафиксировано, что старый `tdata` candidate всё ещё авторизован или уже протух, чтобы следующий агент не путал их.
- если запускается прямой helper, он идёт через collector venv, а не через голый системный `python3`:

```bash
/home/max/telegram-api-collector/.venv/bin/python scripts/telegram_tdata_helper.py export-public-phones ...
```
