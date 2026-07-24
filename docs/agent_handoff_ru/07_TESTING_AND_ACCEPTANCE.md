# Проверки и приёмка

Минимум для каждой завершённой задачи:

```bash
PYTHONPATH="$PWD" python3 -m unittest discover -s tests -p 'test_*.py'
python3 scripts/check_docs.py
python3 scripts/check_repository.py --base origin/main
git diff --check
```

Дополнительно:

- Python-модули — `py_compile`, Ruff и mypy;
- JavaScript — `node --check` и `node --test tests/js`;
- shell — `bash -n`;
- браузерный протокол — настоящий Chrome E2E.

В отчёте укажите точные команды, число тестов, пропуски и причину. «Проверено
вручную» не заменяет автоматический сценарий. Актуальные доказательства
браузерного ядра — в
[отчёте приёмки](../reports/BROWSER_CORE_ACCEPTANCE_2026-07-24_RU.md).
