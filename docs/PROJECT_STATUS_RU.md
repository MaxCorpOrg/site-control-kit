# Project Status RU

Последнее обновление: 2026-04-19

Этот файл нужен как точка входа для любого нового чата и любого нового агента.
Перед новой задачей его нужно прочитать целиком.

## Сделано

### Базовый browser-control kit
- Хаб `webcontrol` работает как единый источник правды по клиентам, очередям и результатам.
- CLI и browser wrappers уже подходят для живого локального управления браузером.
- Расширение исполняет tab-level и DOM-level команды.

### Telegram batch-flow
- Есть рабочий сценарий пакетного сохранения новых контактов в `~/telegram_contact_batches/chat_<id>/1.txt`, `2.txt`, `3.txt` и далее.
- Есть `latest_full.md/txt` и `latest_safe.md/txt`.
- Есть numbered batch files и safe snapshots.

### Безопасность данных Telegram
- Введены `identity_history.json`, `review.txt`, `conflicts.json` и quarantine-логика.
- Известные конфликты `peer_id <-> username` не должны попадать в numbered batch как безопасные данные.

### Discovery и повторные прогоны
- Есть `discovery_state.json` между прогонами.
- Есть discovery-first режим, burst-scroll, jump-scroll.
- Есть chain-runner для серии коротких прогонов с одним состоянием discovery.
- Chain-runner уже умеет останавливаться по `target_unique_members`, `target_safe_count`, `stop-after-idle`, `stop-after-no-growth`.

### Диагностика прогонов
- Каждый run сохраняет `run.json`, `export.log`, `snapshot.md/txt`, `snapshot_safe.md/txt`.
- Есть `export_stats.json` с телеметрией экспортёра.
- `run.json` дублирует ключевые метрики: `unique_members`, `members_with_username`, `deep_updated_total`, `history_backfilled_total`, `chat_scroll_steps_done`, `chat_jump_scrolls_done`.

### History backfill
- Экспортёр теперь умеет восстанавливать уже известные `peer_id -> @username` из `identity_history.json` прямо в текущий run.
- Backfill выполняется до extra-deep, поэтому повторный прогон не начинается заново с пустого raw-слоя.

## Проверено
- Полный unit-набор проходил зелёным: `61/61`.
- Shell syntax и `py_compile` для последних изменений проходили зелёными.
- Живой smoke chain-runner подтверждён на временном каталоге:
  - `target_unique_members_reached`
  - `best_unique_members = 10`
  - `best_safe_count = 2`
- Живой Telegram smoke на реальном каталоге подтвердил backfill:
  - `history_backfilled_total = 5`
  - `members_with_username = 9`
  - `safe_count = 7`
  - артефакты:
    - `/home/max/telegram_contact_batches/chat_-2465948544/runs/20260419T170916Z/run.json`
    - `/home/max/telegram_contact_batches/chat_-2465948544/runs/20260419T170916Z/export_stats.json`
- Подтверждён рабочий path:
  - `hub -> extension -> Telegram Web -> export -> batch/safe artifacts`

## Текущие Проблемы

### 1. Плохой raw-run всё ещё может затереть полезный `latest_full`/`latest_safe`
Был живой случай, когда numbered batch уже содержал username, а очередной raw-run перезаписал `latest_full.txt` пустым результатом.
Это нужно защищать отдельно.

### 2. Raw-слой всё ещё может содержать ложные duplicate username
После backfill и deep raw-снимок может содержать несколько строк с одним и тем же `@username` на разных `peer_id`.
Сейчас safe/quarantine это уже отсекает, но raw truth set ещё не идеален.

### 3. Deep mention всё ещё flaky
Есть живые логи вида:
- `mention context ... opened`
- `WARN: mention item not clicked`

То есть deep-path ещё не production-grade.

### 4. Exporter тратит слишком много runtime на discovery до deep
На некоторых прогонах deep успевает обработать 1 профиль, а остальное время уходит на scroll/discovery.

### 5. Экспортёр остаётся монолитным
`export_telegram_members_non_pii.py` всё ещё перегружен ответственностями и требует модульного разделения.

## Последний Подтверждённый Полезный Результат
- Живой run на реальном каталоге подтвердил, что history backfill восстанавливает username даже при runtime-limited discovery.
- Артефакты проверки:
  - `/home/max/telegram_contact_batches/chat_-2465948544/runs/20260419T170916Z/run.json`
  - `/home/max/telegram_contact_batches/chat_-2465948544/runs/20260419T170916Z/export_stats.json`
  - `/home/max/telegram_contact_batches/chat_-2465948544/latest_full.md`
  - `/home/max/telegram_contact_batches/chat_-2465948544/latest_safe.txt`

## Следующий Приоритет
1. Защитить `latest_full` и `latest_safe` от деградации пустым или худшим прогоном.
2. Убрать ложные duplicate username из raw-слоя раньше, до записи `latest_full.md`.
3. После этого снова прогнать живой Telegram smoke и сравнить raw/safe/output batch на одном и том же run.

## Как Продолжать Следующему Агенту
1. Прочитать `AGENTS.md`.
2. Прочитать `docs/PROJECT_WORKFLOW_RU.md`.
3. Прочитать этот файл полностью.
4. Проверить `git status --short --branch` и `git log --oneline -n 15`.
5. Если задача про Telegram username, сначала открыть:
   - `latest_full.md`
   - `latest_safe.md`
   - последний `run.json`
   - последний `export.log`
   - `identity_history.json`
6. Только потом делать правки.
