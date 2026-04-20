# State And Artifacts

## Базовый Chat Directory
Типовой каталог:

```text
/home/max/telegram_contact_batches/chat_<id>/
```

Пример реального каталога:

```text
/home/max/telegram_contact_batches/chat_-2465948544/
```

## Основные Файлы В Chat Dir
### `latest_full.md`
Текущий raw markdown snapshot.

### `latest_full.txt`
Список raw usernames.

### `latest_safe.md`
Safe markdown snapshot.

### `latest_safe.txt`
Safe usernames.

### `identity_history.json`
История соответствий `peer_id -> username`.
Ключевой файл для backfill и защиты от ложных переназначений.

### `discovery_state.json`
Состояние discovery между прогонами.
Содержит:
- view signatures;
- deep peer history;
- признаки already-seen слоёв.

### `review.txt`
Спорные случаи, не попавшие в safe layer.

### `conflicts.json`
Структурированные конфликты по usernames.

### `1.txt`, `2.txt`, `3.txt`, ...
Numbered batches новых safe usernames.

## Run Artifacts
Каждый run создаёт каталог:

```text
chat_<id>/runs/<timestamp>/
```

Внутри обычно лежат:
- `run.json`
- `export.log`
- `export_stats.json`
- `snapshot.md`
- `snapshot.txt`
- `snapshot_safe.md`
- `snapshot_safe.txt`

## Что Важно Смотреть В `run.json`
Минимум:
- `status`
- `profile`
- `unique_members`
- `members_with_username`
- `deep_updated_total`
- `history_backfilled_total`
- `chat_scroll_steps_done`
- `chat_runtime_limited`
- `chat_deep_yield_stop`

## Что Важно Смотреть В `export.log`
Именно лог показывает реальный ход exporter:
- какой peer взят;
- сработал ли `Mention`;
- был ли `click_menu_text miss`;
- был ли `expired no delivery`;
- ушёл ли exporter в URL fallback;
- вернулся ли в group dialog.

## Что Важно Смотреть В `export_stats.json`
Это структурированная телеметрия.
Особенно полезны поля:
- `members_total`
- `members_with_username`
- `deep_attempted_total`
- `deep_updated_total`
- `history_backfilled_total`
- `chat_stats`

## Chain Artifacts
Для chain-runner есть отдельный каталог:

```text
chat_<id>/chains/<timestamp>/
```

Обычно внутри:
- `chain.json`
- `chain.log`

`chain.json` важен для сравнения профилей и stop logic.
