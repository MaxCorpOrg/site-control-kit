# Project Status RU

Последнее обновление: 2026-04-20

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

### Усиление mention/deep-path
- Для `mention`-режима добавлен более агрессивный запуск при stall discovery: deep теперь может запускаться раньше, даже если чат крутится по уже известной сигнатуре вида.
- Чтение `@username` из composer больше не опирается только на `innerText`: теперь есть fallback по HTML-разметке (`href`, `data-plain-text`, `mention` markup).
- Клик по пункту `Mention` стал шире по покрытию: после старых root-селекторов используются и общие `body/.btn-menu` fallback-пути возле последней точки context-click.
- В `content.js` усилен `click_text`: теперь он умеет находить текст на вложенных menu-item text span узлах и кликать ближайший кликабельный предок.
- Добавлена отдельная DOM-команда `click_menu_text` для видимых popup/context menu; Telegram mention-path теперь пробует её раньше общего `click_text`.

### Диагностика stale extension runtime
- В heartbeat `meta` добавлены `capabilities` по background/content-командам.
- CLI теперь умеет помечать browser tab-level ошибки вида `Unsupported command type in content script ...` как вероятный stale runtime и подсказывает reload в `chrome://extensions`.
- Telegram-экспортёр теперь делает preflight по `meta.capabilities` выбранного клиента:
  - если runtime не рекламирует `click_menu_text`, mention-deep не тратит попытки на неподдерживаемую DOM-команду;
  - экспортёр явно предупреждает, что будет использован legacy text-click fallback до reload unpacked extension.

## Проверено
- Полный unit-набор проходил зелёным: `78/78`.
- Shell syntax и `py_compile` для последних изменений проходили зелёными.
- Точечный прогон экспортёрных тестов после capability-preflight:
  - `tests.test_telegram_export_parser`
  - `44/44 OK`
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
- Короткий live smoke на реальном чате после усиления mention/deep подтвердил:
  - deep catch-up теперь реально запускается на коротком chat-run, а не только откладывается до бесконечности;
  - артефакты:
    - `/tmp/tg_mention_smoke.md`
    - `/tmp/tg_mention_smoke_stats.json`
  - факты:
    - `members_total = 9`
    - `members_with_username = 8`
    - `deep_attempted_total = 3`
    - `deep_updated_total = 0`
  - `history_backfilled_total = 6`
  - это значит, что scheduling mention/deep стал лучше, но live-результат по новым `@username` в этом конкретном smoke ещё не вырос.
- Новый live probe на свежем Telegram tab без history backfill подтвердил:
  - после `context_click` в `body` действительно присутствует пункт `Mention`;
  - значит, bottleneck сместился не в открытие меню, а в DOM-поиск/клик по menu item;
  - чистый snapshot:
    - `/tmp/tg_now_nohistory.md`
    - `/tmp/tg_now_nohistory.log`
  - точечный probe:
    - peer `530627292`
    - после context-click в DOM найден текст `Mention`
  - это самый сильный live-факт по текущей deep-проблеме на сегодня.
- Живой smoke по browser bridge подтвердил новую stale-runtime диагностику:
  - `browser new-tab` сейчас падает в живой среде как `Unsupported command type in content script: new_tab`;
  - CLI теперь добавляет явный `hint` про reload unpacked extension в `chrome://extensions`.
- Новый live smoke на неактивной вкладке подтвердил exporter capability-preflight:
  - живой клиент по `/api/clients` не рекламирует `content_commands`;
  - экспортёр до deep-шагов печатает:
    - `WARN: bridge runtime does not advertise content capabilities...`
  - артефакт:
    - `/tmp/tg_cap_preflight_smoke.hpX3VV/export.log`
  - тестовая вкладка `614277598` после smoke возвращена обратно на `https://yandex.ru/internet/`.

## Текущие Проблемы

### 1. Deep mention всё ещё flaky
Есть живые логи вида:
- `mention context ... opened`
- `WARN: mention item not clicked`

То есть deep-path стал сильнее по scheduling и чтению composer, а live probe подтвердил наличие `Mention` в DOM. Код уже переведён на отдельный `click_menu_text`, а экспортёр теперь умеет сам распознавать отсутствие этой команды по bridge capabilities и переключаться на legacy fallback. Но live-подтверждение нового пути всё ещё упирается в stale runtime расширения до его reload.

### 2. Прямое live-подтверждение context-menu fallback ещё неполное
Короткий smoke подтвердил запуск catch-up mention, но не дал новых `@username`.
Отдельный target-run для точечного peer снова подвис и был остановлен вручную, но state/log probe уже локализовал проблему точнее: `context_click` проходит, `Mention` есть в DOM, а ломается именно `click_text` path текущего runtime.

### 3. Живой браузерный runtime не синхронизирован с кодом репозитория
На машине обнаружен stale runtime расширения:
- `browser new-tab` в живом окружении упал как `Unsupported command type in content script: new_tab`;
- это означает, что загруженная версия background/content runtime в Chrome отстаёт от кода в репозитории.
Без reload unpacked extension часть новых правок нельзя подтвердить end-to-end.

### 4. Exporter тратит слишком много runtime на discovery до deep
На некоторых прогонах deep успевает обработать 1 профиль, а остальное время уходит на scroll/discovery.

### 5. X11 fallback для browser tab actions в этой среде ненадёжен
Проверка `_x11_send_keys` на реальном Chrome window вернула `True`, но фактический `Ctrl+T` не создал новую вкладку.
Это отдельный инфраструктурный долг browser CLI.

### 6. Best-known latest может быть исторически сильным, но не самым свежим по времени
Сейчас это осознанное поведение: `latest_*` в chat-dir означает лучший известный snapshot, а не обязательно самый свежий run.
Если пользователю нужен именно последний run как основной артефакт, это потребуется оформить отдельно.

### 7. Экспортёр остаётся монолитным
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
1. Перезагрузить unpacked extension и повторить точечный peer-run на чистом Telegram tab без history backfill.
2. После reload снять конкретный успешный `mention`-deep прогон по новому peer и сравнить `click_menu_text` против legacy fallback.
3. Починить или переосмыслить X11 fallback для `browser new-tab`.
4. Разделить browser capability/runtime compatibility и Telegram export concerns в отдельные модули/слои.
5. Отделить понятие `best-known latest` от `most-recent run` в UI и документации, если пользователю важно видеть именно последний прогон как основной артефакт.
6. Декомпозировать `export_telegram_members_non_pii.py` на модули.

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
