# Карта архитектуры

Основной поток:

```text
агент -> CLI или HTTP -> HubServices -> SQLite -> аренда -> расширение
                               ^                            |
                               +---------- результат -------+
```

- `webcontrol/server.py` — HTTP, авторизация и маршруты;
- `webcontrol/services.py` — сервисы и долгий запрос команд;
- `webcontrol/store.py` — транзакционное состояние;
- `webcontrol/protocol.py` — статусы и политики повтора;
- `webcontrol/browser_agent.py` — контракт агентных команд;
- `extension/transport.js` — параметры долгого запроса;
- `extension/background.js` — вкладки, аренда, очередь результата и CDP;
- `extension/agent_dom.js` — снимок, локаторы, ожидания и фреймы;
- `webcontrol/cli.py` — операторский интерфейс.

Подробные границы и будущие интерфейсы описаны в
[архитектуре](../ARCHITECTURE.md). Контракт сообщений — в [API](../API.md).
