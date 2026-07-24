# Проверки и приёмка

## Базовое Обязательное Правило
После каждой завершённой задачи запускать:

```bash
PYTHONPATH="$PWD" python3 -m unittest discover -s tests -p 'test_*.py'
```

На текущем этапе полный suite должен быть зелёным.

## Если менялись точки входа Python
Дополнительно:

```bash
python3 -m py_compile <изменённые python-файлы>
```

## Если менялись сценарии оболочки
Дополнительно:

```bash
bash -n <изменённые shell-файлы>
```

## Если менялся браузерный контур или Telegram
Нужен живой smoke.
Минимум должен существовать хотя бы один из наборов:
- `run.json`
- `export.log`
- `export_stats.json`

## Что считать приёмкой шага Telegram
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

## Приёмка изменений углублённого сбора
Хорошая приёмка deep-изменения:
- в `export.log` видно новый ход;
- в `export_stats.json` меняется `deep_updated_total`;
- в `run.json` видно итоговые изменения;
- в status docs записан вывод, а не только путь к файлу.

## Приёмка изменений оболочки и оркестрации
Хорошая приёмка orchestration-изменения:
- тест на helper-функцию;
- тест на `main()` если есть CLI/script wrapper;
- live smoke на реальном чате или хотя бы на реальном hub client.
