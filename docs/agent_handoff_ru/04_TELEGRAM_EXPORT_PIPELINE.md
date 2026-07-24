# Процесс экспорта Telegram

## Основная Цепочка
Полный pipeline выглядит так:

```text
collect_new_telegram_contacts_chain.sh
  -> telegram_contact_chain.py
    -> collect_new_telegram_contacts.sh
      -> auto_collect_usernames.sh
        -> export_telegram_members_non_pii.py
          -> run artifacts + latest snapshots + batch files
```

## Что делает экспортёр по шагам
1. Проверяет целевую вкладку Telegram.
2. Загружает `identity_history.json`.
3. Загружает `discovery_state.json`.
4. Читает текущий видимый слой сообщений.
5. Собирает известных участников из visible DOM.
6. При необходимости запускает deep-path.
7. Если `Mention` не сработал, уходит в URL fallback.
8. Пишет raw markdown.
9. Применяет sanitize/history restore.
10. Пишет telemetry в `export_stats.json`.

## Поиск участников
Discovery отвечает за:
- scroll вверх;
- фиксацию signatures видимого слоя;
- сбор новых `peer_id`;
- понимание, меняется ли chat view или уже идёт плато.

Текущие техники discovery:
- normal scroll;
- burst scroll;
- jump scroll;
- revisited-view detection.

## Углублённый сбор
Deep отвечает за извлечение `@username`.
Основные режимы:
- `mention`
- `url`
- `full`

### Путь через упоминание
Работает так:
1. найти anchor/avatar current peer;
2. открыть context menu;
3. кликнуть `Mention`;
4. прочитать composer;
5. извлечь `@username`.

### Запасной путь через URL
Если mention не дал username:
1. открыть профиль/peer path;
2. извлечь username через URL/profile context;
3. вернуться в group dialog.

## Восстановление из истории
History backfill восстанавливает уже известные `peer_id -> @username` до extra-deep.
Это нужно, чтобы повторный run не выглядел пустым, если текущий runtime не успел заново пройти всех известных peer.

## Безопасный слой
Safe layer строится поверх raw snapshot.
Он нужен, чтобы:
- не выпускать конфликтные usernames в numbered batch;
- держать отдельный `latest_safe.*`;
- складывать спорные случаи в `review.txt` и `conflicts.json`.

## Защита последнего лучшего снимка
Слабый run не должен затирать хороший previous snapshot.
Поэтому wrapper сравнивает candidate/baseline и может оставить лучший historical snapshot как `latest_full` и `latest_safe`.

## Профили запуска
Теперь profile presets влияют на pipeline целиком.

### `fast`
Подходит для:
- быстрых коротких повторных проходов;
- уже накопленного history/discovery state.

### `balanced`
Нейтральный профиль по умолчанию.

### `deep`
Подходит для:
- вытягивания новых реальных `@username`;
- длиннее runtime;
- более агрессивного deep/discovery баланса.

## Практический Вывод По Профилям
На текущем live baseline:
- `fast` лучше для быстрого догруза по already-known history;
- `deep` лучше для новых `@username`.
