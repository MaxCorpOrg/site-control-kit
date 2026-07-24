# Порядок работы с проектом

## Перед правкой

```bash
git status --short --branch
git log --oneline -n 15
```

Прочитайте:

1. корневой `AGENTS.md`;
2. `START_HERE_AGENT_RU.md`;
3. `docs/PROJECT_STATUS_RU.md`;
4. `AGENTS.md` рабочей папки;
5. источник правды по теме.

Не переносите старую ветку целиком. Новая работа начинается от актуального
`main`, а изменения делятся по подсистемам.

## Во время работы

- одна задача — один понятный блок;
- одна новая возможность — контракт, код, пример и тест;
- протокол меняется только с версией;
- крупная зависимость добавляется только после сравнения альтернатив;
- опасное действие не повторяется вслепую;
- старые пользовательские изменения в рабочем дереве не удаляются.

## После Python‑изменения

```bash
python3 -m py_compile <изменённые-файлы.py>
PYTHONPATH="$PWD" python3 -m unittest discover -s tests -p 'test_*.py'
```

## После JavaScript‑изменения

```bash
node --check extension/agent_dom.js
node --check extension/content.js
node --check extension/background.js
node --test tests/js/agent_dom.test.mjs
```

Если изменился реальный браузерный контур, нужен `scripts/browser_e2e.py`.

## После shell‑изменения

```bash
bash -n <изменённый-скрипт.sh>
```

## Документация и безопасность

```bash
python3 scripts/check_docs.py
python3 scripts/check_repository.py --base origin/main
git diff --check
```

Документы пишутся по‑русски. Английский термин используется только там, где
он нужен для API или поиска, и объясняется через `docs/TERMS_RU.md`.

## Коммиты и PR

- сообщение коммита — по‑русски;
- один коммит решает одну задачу;
- browser core, docs и Telegram идут отдельными PR;
- перед push проверить `git diff --cached` и происхождение ветки;
- после push дождаться CI и исправить все ошибки.

## Завершение

Обновите `docs/PROJECT_STATUS_RU.md`: результат, доказательства, риск,
следующий приоритет. Не добавляйте туда длинную хронологию.
