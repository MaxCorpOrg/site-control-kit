# Работа агента и эксплуатация

## Обязательный Старт Любой Сессии
```bash
cd /home/max/site-control-kit
git status --short --branch
git log --oneline -n 15
```

После этого:
1. прочитать `AGENTS.md`;
2. прочитать `docs/PROJECT_WORKFLOW_RU.md`;
3. прочитать `docs/PROJECT_STATUS_RU.md`;
4. только потом идти в код.

## Начало работы с Telegram
Перед Telegram-правками обязательно просмотреть:

```bash
ls -la /home/max/telegram_contact_batches/chat_-2465948544
find /home/max/telegram_contact_batches/chat_-2465948544/runs -maxdepth 2 -name run.json | sort | tail -n 3
```

И потом открыть:
- последний `run.json`
- последний `export.log`
- последний `export_stats.json`
- `identity_history.json`
- `discovery_state.json`

## Быстрая проверка браузера перед реальной работой
```bash
PYTHONPATH="$PWD" python3 -m webcontrol clients
PYTHONPATH="$PWD" python3 -m webcontrol browser tabs
```

## Начало работы с приглашениями Telegram
Перед invite-правками прочитать:

```bash
sed -n '1,260p' tools/telegram/invite_manager/AGENT_GUIDE_RU.md
sed -n '1,260p' tools/telegram/invite_manager/ONE_USER_FLOW_RU.md
sed -n '1,260p' docs/TELEGRAM_INVITE_EXECUTOR_RU.md
```

Правило безопасности:
- `add-contact` использовать только для одного пользователя из `invite_state.json` с `consent=yes`;
- `inspect-chat` использовать до и после live add, чтобы сверять member count;
- финальный Telegram `Add` выполнять только с явным `--confirm-add`;
- если нет отдельного подтверждения `joined/added`, писать статус `requested`, а не `joined`.

## Базовые Полезные Команды
### Один пакетный запуск
```bash
./scripts/collect_new_telegram_contacts.sh "https://web.telegram.org/k/#-2465948544"
```

### Цепочка запусков
```bash
./scripts/collect_new_telegram_contacts_chain.sh \
  "https://web.telegram.org/k/#-2465948544" \
  "/home/max/telegram_contact_batches" \
  --profile deep \
  --runs 3
```

### Явно заданная вкладка
```bash
env CHAT_TAB_ID=614278127 ./scripts/collect_new_telegram_contacts_chain.sh \
  "https://web.telegram.org/k/#-2465948544" \
  "/tmp/tg_chain_profile_deep" \
  --profile deep --runs 1
```

## Как Думать О Проблеме
Не начинать с предположения "Telegram сломан".
Сначала определить слой:
- browser bridge delivery;
- tab targeting;
- discovery;
- mention deep;
- URL fallback;
- backfill;
- safe layer;
- batch layer.

## Как Вести Изменения
Правильный порядок:
1. локализовать узкий момент;
2. изменить один логический блок;
3. прогнать тесты;
4. записать live evidence;
5. обновить status docs;
6. только потом коммитить.

## Что считать хорошей передачей контекста
Хороший handoff отвечает на вопросы:
- что сделали;
- что проверили;
- где лежат артефакты;
- что сломано;
- что делать следующим шагом.
