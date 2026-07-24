# Экспорт участников Telegram

Видимая папка Telegram export pipeline внутри `tools/telegram/`.

Основной код живёт в:
- `scripts/export_telegram_members_non_pii.py`
- `scripts/collect_new_telegram_contacts.sh`
- `scripts/collect_new_telegram_contacts_chain.sh`
- `scripts/telegram_contact_chain.py`
- `scripts/telegram_members_export_app.sh`
- `scripts/telegram_members_export_gui.sh`

## Быстрый Старт

```bash
cd /home/max/site-control-kit/tools/telegram/export

./bin/telegram-exporter --help
./bin/telegram-export-chain --help
./bin/telegram-export-batch "https://web.telegram.org/k/#-2465948544"
```

## Что Это Делает

- собирает участников Telegram Web;
- вытягивает `@username`;
- ведёт `identity_history.json` и `discovery_state.json`;
- пишет safe/raw snapshots;
- создаёт numbered batch files;
- запускает chain of short runs.

## Подключение В Единую Платформу

Инструмент подключён через:

```text
tool_manifest.json
../platform/registry/tools.json
```

## Основные Документы

- `../../../docs/TELEGRAM_CLIENT_ROADMAP_RU.md`
- `../../../docs/PROJECT_STATUS_RU.md`
