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
- `run.json` дублирует ключевые метрики: `unique_members`, `members_with_username`, `deep_updated_total`, `history_backfilled_total`, `output_usernames_cleared_total`, `chat_scroll_steps_done`, `chat_jump_scrolls_done`.
- В `run.json` теперь есть и решение по latest-снимкам: `latest_full_promoted`, `latest_safe_promoted`, `latest_full_best_source`, `latest_safe_best_source`.

### History backfill
- Экспортёр теперь умеет восстанавливать уже известные `peer_id -> @username` из `identity_history.json` прямо в текущий run.
- Backfill выполняется до extra-deep, поэтому повторный прогон не начинается заново с пустого raw-слоя.

### Защита latest-снимков
- Wrapper больше не затирает `latest_full.*` и `latest_safe.*` слабым прогоном.
- Если текущий run хуже, в chat-dir остаётся лучший known snapshot.
- После прогона wrapper умеет поднять лучший raw/safe snapshot из `runs/*/snapshot*.md`, если именно там лежит более качественный результат.

### Очистка raw output
- Перед записью markdown экспортер очищает конфликтные duplicate `@username` и может восстановить исторический username для конкретного `peer_id` в итоговом output.

## Проверено
- Полный unit-набор проходил зелёным: `67/67`.
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
- Живой слабый run на реальном каталоге подтвердил latest-guard и восстановление лучшего snapshot из истории run-артефактов:
  - `/home/max/telegram_contact_batches/chat_-2465948544/runs/20260419T172709Z/run.json`
  - `latest_full_best_source = .../runs/20260419T090950Z/snapshot.md`
  - `latest_safe_best_source = .../runs/20260419T094747Z/snapshot_safe.md`

## Текущие Проблемы

### 1. Deep mention всё ещё flaky
Есть живые логи вида:
- `mention context ... opened`
- `WARN: mention item not clicked`

То есть deep-path ещё не production-grade.

### 2. Exporter тратит слишком много runtime на discovery до deep
На некоторых прогонах deep успевает обработать 1 профиль, а остальное время уходит на scroll/discovery.

### 3. Best-known latest может быть исторически сильным, но не самым свежим по времени
Сейчас это осознанное поведение: `latest_*` в chat-dir означает лучший известный snapshot, а не обязательно самый свежий run.
Если пользователю нужен именно последний run как основной артефакт, это потребуется оформить отдельно.

### 4. Экспортёр остаётся монолитным
`export_telegram_members_non_pii.py` всё ещё перегружен ответственностями и требует модульного разделения.

## Последний Подтверждённый Полезный Результат
- Живой run на реальном каталоге подтвердил, что even weak current run не ухудшает chat-dir, а latest-снимки восстанавливаются из лучшего known run-artifact.
- Артефакты проверки:
  - `/home/max/telegram_contact_batches/chat_-2465948544/runs/20260419T172709Z/run.json`
  - `/home/max/telegram_contact_batches/chat_-2465948544/runs/20260419T172709Z/export.log`
  - `/home/max/telegram_contact_batches/chat_-2465948544/latest_full.md`
  - `/home/max/telegram_contact_batches/chat_-2465948544/latest_safe.txt`
  - `/home/max/telegram_contact_batches/chat_-2465948544/11.txt`

## Следующий Приоритет
1. Повысить реальную результативность `mention`/deep-path, чтобы сильнее росли `members_with_username`, а не только backfill/history слой.
2. Отделить понятие `best-known latest` от `most-recent run` в UI и документации, если пользователю важно видеть именно последний прогон как основной артефакт.
3. Декомпозировать `export_telegram_members_non_pii.py` на модули.

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
