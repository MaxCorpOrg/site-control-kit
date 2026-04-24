# Known Issues And Live Findings

## Самый Важный Актуальный Live-Факт
Последний реальный bottleneck теперь уже не в runtime/reload/wrapper слое.
Он сместился в сам Telegram mention path:
- `click_menu_text` и новый runtime уже живы;
- wrapper уже умеет сам открыть Telegram tab через bridge client;
- но на части peer по-прежнему нет прямого `Mention`, поэтому основной рабочий path уже helper-first, а не menu-first.

Новый live-факт на 2026-04-24:
- pre-deep history backfill внедрён;
- известные peer восстанавливаются из `identity_history.json` до deep-обхода;
- smoke `/tmp/telegram_live_after_prefill.md` на `https://web.telegram.org/a/#-1002465948544` восстановил `9` username из history до deep;
- archive: `/home/max/site-control-kit/artifacts/telegram_exports/20260424_132543_chat_1002465948544_22.md`;
- первый реальный unknown deep-кандидат `8055002493` за `90s` username не отдал.

Новые live-фиксы на 2026-04-24:
- stale explicit `CHAT_IDENTITY_HISTORY` больше не должен переезжать поверх более свежего archive state;
- parser больше не должен красть `@username` из message text;
- helper-tab больше не должен возвращать stale username чужого профиля до подтверждения нужного `peer_id`/имени.

Подтверждение:
- `/tmp/telegram_live_verify.md` при явном `/home/max/telegram_contact_batches/chat_-1002465948544/identity_history.json` больше не воспроизвёл старый конфликт по `@super_pavlik`;
- chat-dir `identity_history.json` обновился и теперь снова содержит `@super_pavlik -> 1621138520`, `@alxkat -> 306536305`, `@mitiacaramba -> 1127139638`;
- `/tmp/telegram_live_verify_2.md` больше не дал ложный helper-case `6964266260 (Evgeniy) -> @Tri87true`;
- `output_usernames_cleared_total = 0`, archive: `/home/max/site-control-kit/artifacts/telegram_exports/20260424_171947_chat_1002465948544_20.md`.

Новый конкретный прогресс внутри этого bottleneck:
- exporter теперь умеет внутри одного deep-step рано понять, что текущий Telegram menu-path бесполезен;
- если первый peer возвращает `menu_missing`, оставшиеся peer этого же visible-layer сразу идут в helper-only path;
- это уже дало реальный throughput gain на живом чате.
- отдельный класс ложных данных тоже уже закрыт:
  - чисто числовые `@username` теперь считаются peer-id артефактами;
  - active history/safe/batch outputs очищены от значений вида `@1291639730`.

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
- Живой verify этого scheduler-cap уже завершён:
  - run: `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T173223Z/run.json`
  - stats: `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T173223Z/export_stats.json`
  - факты:
    - `unique_members = 27`
    - `members_with_username = 10`
    - `safe_count = 10`
    - `deep_attempted_total = 2`
    - `deep_updated_total = 2`
    - `chat_scroll_steps_done = 2`
  - практический смысл:
    - scheduler-cap теперь подтверждён не только тестами, но и живьём;
    - `latest_full.*` и `latest_safe.*` уже promoted на этот run.

### Новый live-факт по numeric username артефактам
- В одном из промежуточных live-run exporter ошибочно принял `@1291639730` за username и протащил это значение в safe/batch контур.
- Статус этого дефекта:
  - снят.
- Что сделано:
  - exporter теперь принимает username только если в нём есть буквы;
  - loader `identity_history.json` и safe/batch helper очищают старые numeric значения при чтении и пересборке;
  - active outputs уже очищены, исторические raw snapshots могут сохранять старую правду конкретного buggy run.

### Group dialog restore в целом работает лучше, чем раньше
Раньше один тяжёлый peer мог ломать остаток deep-step.
Теперь path заметно устойчивее, хотя warning-поведение всё ещё встречается.

### Новый live-факт по pre-deep history backfill
- Сделано в `scripts/export_telegram_members_non_pii.py`:
  - `_collect_members_from_chat()` вызывает `_backfill_usernames_from_history()` сразу после dedupe visible members;
  - `deep_targets` строятся уже после восстановления history-known username;
  - stats включают `history_prefilled` и `history_prefill_conflicts`.
- Проверка тестами:
  - `tests.test_telegram_export_runtime tests.test_telegram_deep_helper` -> `27 tests OK`;
  - полный Telegram-related набор -> `77 tests OK`.
- Проверка живьём:
  - `/tmp/telegram_live_after_prefill.md`;
  - `/tmp/telegram_live_after_prefill_usernames.txt`;
  - `/home/max/site-control-kit/artifacts/telegram_exports/20260424_132543_chat_1002465948544_22_usernames_json.json`.
- Практический смысл:
  - если следующий run снова тратит deep на peer, который уже есть в `identity_history.json`, это регрессия.

### Новый live-факт по sticky-author icon path
- `telegram_sticky_author` теперь выбирает нижнюю прилипшую 34px avatar через `elementsFromPoint`.
- Правый клик не должен идти по тексту сообщения, reply-avatar или профилю.
- Если menu открылось, но `Mention` отсутствует, exporter теперь запускает helper-tab для того же sticky `peer_id`.
- Live helper fallback уже добыл:
  - `306536305 -> @alxkat`;
  - `1127139638 -> @Mitiacaramba`.
- Direct live probe на extension `0.1.5`:
  - `source=point`;
  - `point={x:512,y:539}`;
  - `rect=506,535,540,569`;
  - `context_clicked=true`.
- Wrapper live smoke:
  - `/tmp/telegram_live_sticky_icon.md`;
  - `/home/max/site-control-kit/artifacts/telegram_exports/20260424_143524_chat_1002465948544_18.md`;
  - результат: `18` members, `10` usernames;
  - sticky peer `6964266260` дошёл до `menu_missing`, значит координаты уже не главный сбой.
- Проверка тестами:
  - `python3 -m unittest discover -s tests -p 'test_*.py'` -> `112 tests OK`.

### Combined 50+ Username Artifact
- Уже есть combined deliverable выше целевой планки `50`:
  - `/tmp/telegram_combined_54_usernames.txt`
  - `/tmp/telegram_combined_54_usernames.json`
  - `/home/max/site-control-kit/artifacts/telegram_exports/20260424_164916_combined-usernames_1002465948544_54.txt`
  - `/home/max/site-control-kit/artifacts/telegram_exports/20260424_164916_combined-usernames_1002465948544_54.json`
- Важно для следующего агента:
  - это объединение нескольких источников: peer-bound member exports, sticky/helper live runs, chat-mentions, numbered batches;
  - это не равно "54 peer-bound участника, подтверждённых свежим profile helper";
  - строгий peer-bound сбор всё ещё надо ускорять отдельно.

## Основные Открытые Риски
0. Sticky-author click-path уже исправлен на правый клик по нижней 34px иконке, но Telegram Web всё ещё может не показывать `Mention` в этом меню; тогда это `menu_missing`, а не ошибка координат.
1. Главный текущий limit: в текущем Telegram Web menu-path часто вообще не содержит `Mention`, даже когда context menu открылось корректно.
2. Даже в `deep`-профиле runtime часто уходит в helper fallback вместо прямого menu-click path; sticky helper уже работает, но один helper resolve всё ещё может занимать десятки секунд.
3. Даже после helper-only switch, pre-deep history backfill и sticky helper fallback throughput peer-bound сбора пока ограничен.
4. Scheduler-cap и history prefill уже подтверждены, но сами по себе не снимают throughput ceiling helper-path.
5. Текущий честный baseline теперь `10` safe usernames в `latest-safe` контуре этой группы, но целевая планка всё ещё остаётся `40+`.
6. Heartbeat capability metadata может не рекламировать `telegram_sticky_author` даже после reload, хотя direct command работает. Не считайте это блокером exporter path, пока команда реально исполняется.
7. `export_telegram_members_non_pii.py` остаётся монолитным.

## Правило `ё-моё` Для Следующего Агента
Если следующий баг снова звучит как "не собрал username", не надо начинать с нуля.

`ё-моё` = если `Mention` ёкнулся, моё правило такое: правой кнопкой по нижней прилипшей иконке автора, затем helper fallback, фильтр numeric `@username`, проверка `identity_history.json`, `latest_safe.txt` и numbered batches.

Минимальный чеклист:
- sticky-author path использовал `telegram_sticky_author context_click=true`, а не клик по тексту/профилю;
- был ли deep вообще запущен;
- были ли history-known peer восстановлены до deep, а не отправлены в helper повторно;
- был ли helper fallback после unresolved `Mention` или `No visible menu item found by text`;
- отвечает ли `/api/clients` быстро или снова виден store-lock/perf choke;
- рекламирует ли runtime `meta.capabilities.content_commands`;
- не протащился ли в safe/history слой numeric peer-id под видом `@username`;
- что именно вычистил safe layer и какой snapshot реально promoted в `latest_*`.
