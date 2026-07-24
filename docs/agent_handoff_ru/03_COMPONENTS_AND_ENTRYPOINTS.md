# Компоненты и точки входа

| Задача | Куда идти | Что проверить |
| --- | --- | --- |
| Доставка команды | `webcontrol/services.py`, `store.py`, `protocol.py` | долгий запрос, аренда, stale lease, идемпотентность |
| HTTP и токен | `webcontrol/server.py` | заголовок, Origin, совместимость |
| Команда CLI | `webcontrol/cli.py` | `--help`, старый синтаксис |
| Транспорт расширения | `extension/transport.js`, `background.js` | один запрос, backoff, пробуждение |
| Вкладка или CDP | `extension/background.js` | detach в `finally`, outbox |
| DOM и локатор | `extension/agent_dom.js` | strict, iframe, Shadow DOM |
| Сквозная проверка | `scripts/browser_e2e.py` | настоящий Chrome |
| Telegram | `scripts/telegram_*` | отдельный PR и профильные тесты |
| Упаковка | `packaging/` | чистая установка |

До правки прочитайте `AGENTS.md` выбранной папки. После правки обновляйте
канонический документ, а не эту таблицу, если изменился сам контракт.
