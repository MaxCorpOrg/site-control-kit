# Known Issues And Live Findings

## Самый Важный Актуальный Live-Факт
Последний реальный bottleneck оказался двухслойным:
- exporter действительно терял runtime на `mention/menu` path;
- но поверх этого wrapper и `/api/clients` могли ложнопадать из-за лишних `_save()` под store-lock в хабе.

На 2026-04-23 оба слоя уже частично сняты:
- `mention`-режим больше не тупиковый: при unresolved/delivery-failure он сразу падает в helper-tab fallback;
- `webcontrol/store.py` больше не пишет `state.json` на каждый heartbeat и пустой poll, поэтому `/api/clients` снова отвечает быстро и batch wrapper снова живой.

## Что Уже Не Является Главной Проблемой
### Stale runtime
Снят.
Self-reload и capability handshake уже работают.

### Forced tab targeting
Свежий regression починен.
`CHAT_TAB_ID` без `CHAT_CLIENT_ID` теперь снова рабочий.

### Полный провал mention-path
Снят.
Есть live-подтверждённые run, где mention/deep без history backfill реально собирает новые usernames.

### Ложный fail-fast на wrapper/client detection
Снят.
На локальной `main` это проявлялось как:
- `ERROR: telegram bridge client not detected in 10s`
- при этом клиент реально был в хабе, а виноват был server-side lock contention.

После фикса store + рестарта хаба:
- прямой `curl /api/clients` снова отвечает быстро;
- `collect_new_telegram_contacts.sh` снова доходит до живого Telegram export.

## Что Подтверждено Живьём
### Fast vs Deep
На одной и той же history/discovery базе:
- `fast` дал меньше новых deep usernames, но больше опирался на backfill;
- `deep` дал больше новых реальных `@username`, но дороже по runtime.

### URL fallback живой
Есть реальные run, где `Mention` не кликается, но URL fallback всё равно вытаскивает username.

### Helper fallback в mention-режиме живой
Есть новый batch run на локальной `main`, где `Mention` вообще не открылся по нескольким peer, но exporter не завис и не оборвал шаг:
- `run.json`: `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T115545Z/run.json`
- `export.log`: `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T115545Z/export.log`
- `export_stats.json`: `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T115545Z/export_stats.json`
- live usernames из helper fallback:
  - `@Bychkov_AA`
  - `@abuzayd06`
  - `@GadkiyGri`

### Group dialog restore в целом работает лучше, чем раньше
Раньше один тяжёлый peer мог ломать остаток deep-step.
Теперь path заметно устойчивее, хотя warning-поведение всё ещё встречается.

## Основные Открытые Риски
1. Runtime по-прежнему старый: текущий Chrome client ещё не рекламирует `click_menu_text`, потому что unpacked extension не был перезагружен после обновления файлов.
2. `click_menu_text` delivery-aware path в коде уже есть, но живьём пока не подтверждён на новом runtime из-за предыдущего пункта.
3. Текущий fast mention-run дал только `3` новых usernames и упёрся в `chat runtime limit reached (120s)`.
4. `export_telegram_members_non_pii.py` остаётся монолитным.

## Самый Полезный Мысленный Фильтр Для Следующего Агента
Если следующий баг снова звучит как "не собрал username", не надо начинать с нуля.
Нужно проверить:
- был ли deep вообще запущен;
- был ли helper fallback после unresolved `Mention`;
- отвечает ли `/api/clients` быстро или снова виден store-lock/perf choke;
- рекламирует ли runtime `meta.capabilities.content_commands`;
- был ли `click_menu_text` или exporter ушёл по legacy fallback;
- не спас ли результат history backfill;
- что именно вычистил safe layer.
