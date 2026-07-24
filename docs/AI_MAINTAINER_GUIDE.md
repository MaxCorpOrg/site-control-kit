# Руководство сопровождения ИИ-агентом

Главная простая инструкция находится в
[START_HERE_AGENT_RU.md](../START_HERE_AGENT_RU.md). Этот документ объясняет
инженерные правила.

## Источники правды

- API: [API.md](API.md);
- архитектура: [ARCHITECTURE.md](ARCHITECTURE.md);
- безопасность: [SECURITY.md](SECURITY.md);
- текущий статус: [PROJECT_STATUS_RU.md](PROJECT_STATUS_RU.md);
- план: [ROADMAP_RU.md](ROADMAP_RU.md);
- правила конкретной папки: её `AGENTS.md`.

## Выбор слоя

- HTTP, auth, состояния доставки — `webcontrol/server.py` и `protocol.py`;
- транзакции, очереди, сессии — `store.py` и `state_backend.py`;
- агентная схема — `browser_agent.py`;
- DOM‑поиск — `extension/agent_dom.js`;
- DOM‑действие — `extension/content.js`;
- вкладки, фреймы, CDP — `extension/background.js`;
- удобная команда — `webcontrol/cli.py`;
- Telegram — отдельные `scripts/telegram_*`;
- сборка — `packaging/`.

## Как менять безопасно

1. Зафиксировать наблюдаемое текущее поведение тестом.
2. Изменить один архитектурный слой.
3. Не ослаблять auth, stale lease, idempotency или tab lock.
4. Сохранить старые CSS‑команды.
5. Обновить API, пример и тест одновременно.
6. Для нового решения добавить ADR.
7. После каждого законченного блока запустить полный unit‑набор.
8. Для расширения запустить Chrome E2E.

## Политика повторов

- чтение: `safe_retry`;
- ввод: `retry_if_not_started`;
- клик или отправка формы: `never_retry`;
- `retry_with_verification` допустим только с независимой проверкой
  постусловия.

Если команда была `running`, отсутствие результата — не доказательство
невыполнения.

## Что считать готовой DOM‑командой

- строгий локатор;
- понятная ошибка при 0 и 2+ совпадениях;
- actionability — проверка готовности элемента;
- ограниченный timeout;
- результат с проверяемым постусловием;
- iframe и открытый Shadow DOM, если применимо;
- unit и E2E;
- пример JSON;
- запись в API.

## Частые архитектурные ошибки

- добавлять второй механизм локаторов в `content.js`;
- хранить критическое состояние только в service worker;
- принимать результат без проверки активной аренды;
- разрешать сессионной команде неявную вкладку;
- подключать CDP без `finally`;
- писать секреты до маскирования;
- смешивать браузерное ядро и Telegram в одном PR;
- коммитить runtime, профиль или бинарную сборку.

## Проверки

```bash
PYTHONPATH="$PWD" python3 -m unittest discover -s tests -p 'test_*.py'
python3 scripts/check_docs.py
python3 scripts/check_repository.py --base origin/main
node --check extension/agent_dom.js
node --check extension/content.js
node --check extension/background.js
git diff --check
```

Живой E2E:

```bash
chrome_path="$(python3 scripts/install_chrome_for_testing.py)"
python3 scripts/browser_e2e.py --chrome "$chrome_path" --headed
```

## Передача работы

В `PROJECT_STATUS_RU.md` оставляйте только:

- последний завершённый блок;
- доказательства;
- текущий риск;
- следующий приоритет.

Хронологию переносите в `CHANGELOG.md` и Git.
