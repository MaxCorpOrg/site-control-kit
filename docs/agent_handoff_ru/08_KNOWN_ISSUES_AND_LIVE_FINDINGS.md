# Known Issues And Live Findings

## Самый Важный Актуальный Live-Факт
Последний реальный bottleneck теперь уже не в runtime/reload/wrapper слое.
Он сместился в сам Telegram mention path:
- `click_menu_text` и новый runtime уже живы;
- wrapper уже умеет сам открыть Telegram tab через bridge client;
- но на части peer по-прежнему повторяется `WARN: mention context menu not opened for peer ...`.

На 2026-04-23 инфраструктурные слои уже сняты:
- `mention`-режим больше не тупиковый: при unresolved/delivery-failure он сразу падает в helper-tab fallback;
- `webcontrol/store.py` больше не пишет `state.json` на каждый heartbeat и пустой poll, поэтому `/api/clients` снова отвечает быстро и batch wrapper снова живой.
- `scripts/reload_bridge_extension.sh` уже реально доводит локальный Chrome runtime до состояния с `meta.capabilities.content_commands`.
- `scripts/auto_collect_usernames.sh` уже умеет сам открыть `web.telegram.org` через `browser new-tab` на выбранном bridge client и не зависит только от `xdg-open`.

## Что Уже Не Является Главной Проблемой
### Stale runtime
Снят.
Self-reload и capability handshake уже подтверждены живьём.

### Forced tab targeting
Свежий regression починен.
`CHAT_TAB_ID` без `CHAT_CLIENT_ID` теперь снова рабочий.

### Полный провал mention-path
Снят.
Есть live-подтверждённые run, где mention/deep без history backfill реально собирает новые usernames.

### Ложный fail-fast на wrapper/client detection
Снят.
Это проявлялось уже двумя способами:
- server-side lock contention в хабе;
- и shell-wrapper path, который пытался открыть Telegram через `xdg-open`, то есть мимо bridge profile.

После фиксов:
- прямой `/api/clients` снова отвечает быстро;
- wrapper сначала пробует `browser new-tab` на живом bridge client;
- live smoke подтвердил `INFO: opened Telegram tab via bridge client ...` и успешный export.

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

### Runtime reload и auto-open теперь тоже подтверждены живьём
- reload:
  - `bash scripts/reload_bridge_extension.sh`
  - после него heartbeat содержит `click_menu_text`
- auto-open smoke:
  - `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T121918Z/run.json`
  - `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T121918Z/export.log`
  - `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T121918Z/export_stats.json`
  - ключевой факт: wrapper сам открыл Telegram tab через bridge client и завершил run без ручного `browser new-tab`

### Новый deep baseline на локальной `main`
- `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T122059Z/run.json`
- `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T122059Z/export.log`
- `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T122059Z/export_stats.json`
- факты:
  - `new_usernames = 4`
  - `members_with_username = 9`
  - `deep_attempted_total = 10`
  - `deep_updated_total = 9`
  - `safe_count = 9`
- практический вывод:
  - deep path уже продуктивный;
  - но упирается в `mention context menu not opened`, а не в transport/runtime.

### Group dialog restore в целом работает лучше, чем раньше
Раньше один тяжёлый peer мог ломать остаток deep-step.
Теперь path заметно устойчивее, хотя warning-поведение всё ещё встречается.

## Основные Открытые Риски
1. Главный текущий limit: Telegram не всегда открывает mention context menu по текущим anchor/selectors.
2. Даже в `deep`-профиле runtime часто уходит в helper fallback вместо прямого menu-click path.
3. Текущий честный baseline всё ещё только `9` safe usernames, а целевая планка остаётся `40+`.
4. `export_telegram_members_non_pii.py` остаётся монолитным.

## Самый Полезный Мысленный Фильтр Для Следующего Агента
Если следующий баг снова звучит как "не собрал username", не надо начинать с нуля.
Нужно проверить:
- был ли deep вообще запущен;
- был ли helper fallback после unresolved `Mention`;
- отвечает ли `/api/clients` быстро или снова виден store-lock/perf choke;
- рекламирует ли runtime `meta.capabilities.content_commands`;
- открылся ли сам context menu до попытки `click_menu_text`, или проблема случилась ещё раньше;
- не спас ли результат history backfill;
- что именно вычистил safe layer.
