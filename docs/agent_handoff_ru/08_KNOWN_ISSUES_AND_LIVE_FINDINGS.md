# Known Issues And Live Findings

## Самый Важный Актуальный Live-Факт
Последний реальный bottleneck теперь уже не в runtime/reload/wrapper слое.
Он сместился в сам Telegram mention path:
- `click_menu_text` и новый runtime уже живы;
- wrapper уже умеет сам открыть Telegram tab через bridge client;
- но на части peer по-прежнему повторяется `WARN: mention context menu not opened for peer ...`.

Новый конкретный прогресс внутри этого bottleneck:
- exporter теперь умеет внутри одного deep-step рано понять, что текущий Telegram menu-path бесполезен;
- если первый peer возвращает `menu_missing`, оставшиеся peer этого же visible-layer сразу идут в helper-only path;
- это уже дало реальный throughput gain на живом чате.

Отдельно:
- branded Chrome по-прежнему может мешать именно установке unpacked extension флагами;
- для этого теперь добавлен отдельный Firefox dev-path через `./start-firefox.sh` / `./start-telegram-firefox.sh`;
- он полезен как альтернативный runtime для отладки, но не отменяет текущий Telegram-layer bottleneck сам по себе;
- на текущей машине Firefox установлен через snap wrapper, и `web-ext` не может стабильно подключиться к debugger port, поэтому для snap Firefox helper использует `about:debugging` manual fallback вместо ложного обещания “полностью автоматически”.

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

### Новый live-факт после selector refresh
Он уточнил bottleneck ещё сильнее:
- current Telegram DOM действительно использует `sender-group-container` + `.Avatar[data-peer-id]` / `.message-title-name-container.interactive`;
- после перевода mention/open-dialog path на эти anchors старый `context_missing` почти исчез;
- но затем открылось следующее ограничение: текущий `MessageContextMenu` не содержит `Mention`.

Подтверждение через live body snapshot:
- `/tmp/tg_body_context_name.json`
- в нём у открытого `MessageContextMenu_items` реальные items:
  - `Reply`
  - `Copy Text`
  - `Copy Message Link`
  - `Forward`
  - `Select`
  - `Report`
- значит старый `Mention` path в этой версии Telegram Web не является надёжным источником usernames.

Из этого уже сделан следующий практический шаг:
- exporter теперь читает menu snapshot;
- если в нём нет `Mention`, он сразу идёт в helper fallback;
- это не подняло ceiling выше `9` safe usernames мгновенно, но сняло часть пустых retry.

### Новый live-факт по history/safe слою
- Есть подтверждённый случай, где fresh helper-resolve не сохранился в финальный safe/full output.
- В fast run `20260423T131912Z` exporter живьём напечатал:
  - `INFO: chat helper 555101371 -> @Teimur_92`
- Но в итоговых batch/snapshot артефактах этот peer снова оказался как `@abuzayd06`.
- Практический вывод:
  - текущий limit уже не только в menu/helper throughput;
  - есть отдельный downstream bug, где history backfill или final sanitize может перетирать свежий live username более старым значением.

### Статус этого history/safe дефекта
Снят.

Подтверждение:
- live run: `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T134454Z/run.json`
- log: `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T134454Z/export.log`
- stats: `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T134454Z/export_stats.json`
- `export.log` снова содержит:
  - `INFO: chat helper 555101371 -> @Teimur_92`
- но теперь это значение дошло и в downstream outputs:
  - `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T134454Z/snapshot_safe.md`
  - `/home/max/telegram_contact_batches/chat_-1002465948544/5.txt`
  - `/home/max/telegram_contact_batches/chat_-1002465948544/identity_history.json`
- в `identity_history.json`:
  - `peer_to_username["555101371"] == "@teimur_92"`
  - `username_to_peer["@teimur_92"] == "555101371"`
  - старой `username_to_peer["@abuzayd06"]` больше нет

Новый остаточный нюанс уже не в самом safe/history conflict:
Снят.

Подтверждение:
- safe promotion policy теперь path-aware для peer rename:
  - `scripts/telegram_contact_batches.py` умеет сравнивать snapshots в `prefer_peer_updates=True` режиме;
  - `scripts/collect_new_telegram_contacts.sh` использует этот режим для `latest_safe.*`.
- На текущем chat-dir helper уже выбирает:
  - `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T134454Z/snapshot_safe.md`
  как лучший safe snapshot вместо старого baseline.
- После применения новой policy текущий:
  - `/home/max/telegram_contact_batches/chat_-1002465948544/latest_safe.txt`
  уже содержит `@teimur_92`.

### Новый live baseline после helper-only switch
- run: `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T141227Z/run.json`
- log: `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T141227Z/export.log`
- stats: `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T141227Z/export_stats.json`
- подтверждённый факт:
  - после первого `menu_missing` exporter переключил остаток шага в helper-only;
  - за `120s` fast profile теперь обработал `4` peer, а не `3`;
  - `deep_attempted_total = 4`
  - `deep_updated_total = 1`
- это не сняло потолок `7 safe usernames`, но уже доказало, что текущий путь можно ускорять без нового переписывания хаба/bridge.

### Новый engineering-step после этого baseline
- В exporter уже добавлен `TELEGRAM_CHAT_DEEP_STEP_MAX_SEC`, чтобы один deep-step не съедал весь runtime run’а.
- Profile defaults уже заведены:
  - `fast = 45s`
  - `balanced = 60s`
  - `deep = 90s`
- Но живой verify именно этого scheduler-cap пока не завершён:
  - в конце текущей итерации hub был перезапущен автоматически;
  - после этого browser bridge остался в `is_online=false`;
  - новый run `20260423T152850Z` завис ещё до meaningful exporter telemetry и не дошёл до `run.json`.
- Практический смысл:
  - код и тесты для нового scheduler-cap уже есть;
  - следующий live запуск нужно делать только после восстановления heartbeat-клиента.

### Group dialog restore в целом работает лучше, чем раньше
Раньше один тяжёлый peer мог ломать остаток deep-step.
Теперь path заметно устойчивее, хотя warning-поведение всё ещё встречается.

## Основные Открытые Риски
1. Главный текущий limit: в текущем Telegram Web menu-path часто вообще не содержит `Mention`, даже когда context menu открылось корректно.
2. Даже в `deep`-профиле runtime часто уходит в helper fallback вместо прямого menu-click path.
3. Даже после helper-only switch deep throughput пока всё ещё ограничен: fast run обрабатывает `4` peer за `120s`, а не десятки.
4. Новый scheduler-cap добавлен, но ещё не подтверждён живьём из-за offline bridge после hub restart.
5. Текущий честный baseline всё ещё только `7` safe usernames в latest-safe контуре этой группы, а целевая планка остаётся `40+`.
6. `export_telegram_members_non_pii.py` остаётся монолитным.

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
