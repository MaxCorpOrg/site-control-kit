# Known Issues And Live Findings

## Самый Важный Актуальный Live-Факт
Для текущего пользовательского сценария новый актуальный live-факт уже другой:
- основной рабочий path сейчас `GTK GUI + tdata-history-authors`, а не старый bridge-heavy helper deep path;
- живая сессия для slot `1` подтверждена по `/home/max/telegram-api-collector/tdata_import/tdata`;
- `BigpharmaMarket` (`-1001461811598`) при `history-limit=5000` дал `34` уникальных `@username`, включая `@EgorTuchkov`;
- `-1001753733827` при `history-limit=5000` дал `135` safe usernames и показал живой progress в GUI (`1000 -> 53`, `2000 -> 75`, `3000 -> 101`, `4000 -> 123`, `5000 -> 135`);
- новый live/UX verify на 2026-04-30 для того же чата `-1001753733827`:
  - helper теперь сразу пишет `PROGRESS ... messages=0 usernames=0 stage=start`, а не молчит десятки секунд;
  - базовый progress default снижен до `250` сообщений, чтобы счётчики начинали двигаться заметно раньше;
  - direct helper probe с внешним `timeout 12s` завершился partial payload `history_messages_scanned=600`, `42` usernames, `interrupted=true`;
  - backend cancel probe через GUI-style controller после `7s` вернул partial payload `history_messages_scanned=500`, `rows=35`, `interrupted=true`;
  - значит новый operator-fact уже такой: stop-path для long history-scan рабочий и отдаёт частичный результат вместо немого обрыва.
- новый GUI-fact на 2026-04-30:
  - длинные названия чатов больше не должны делать окно практически нерегулируемым;
  - в коде это закрыто через `resizable` окно и wrap/ellipsis для длинных title-строк;
  - live X11 verify уже подтвердил normal resize hints: `WM_NORMAL_HINTS -> minimum size 46 by 46`, `_NET_WM_ACTION_RESIZE` присутствует.
- новый live GTK smoke на 2026-04-30 для того же чата `-1001753733827`:
  - GUI через `DISPLAY=:0` подключился по `tdata` и загрузил `8` чатов;
  - progress дошёл до `250` сообщений / `27` usernames, после чего stop был принят штатно;
  - финальный partial result: `history_messages_scanned=300`, `usernames_found=30`, `safe_count=30`;
  - артефакты: `/tmp/telegram_gui_smoke_export.md`, `/tmp/telegram_gui_smoke_export_usernames.txt`, `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260430T094917Z.log`.
- новый save-dialog fact на 2026-04-30:
  - `Gtk.FileChooserNative` заменён на `Gtk.FileChooserDialog`;
  - live X11 probe увидел окно `Куда сохранить Telegram export`, значит chooser-path сейчас открывается до уровня реального видимого окна.
- новый timeout fact на 2026-04-30:
  - для полного history-run больше нет дефолтного лимита `1800s`;
  - `TELEGRAM_TDATA_EXPORT_TIMEOUT_SEC=0` теперь трактуется как unlimited default;
  - если пользователь сам задаёт timeout, GUI явно сообщает про "настроенный лимит".
- новый runtime-fact этого же smoke:
  - первый прогон поймал `AttributeError: 'TelegramMembersExportWindow' object has no attribute '_is_tdata_target'` в `_handle_chats_loaded`;
  - fix уже внесён, добавлена регрессия в `tests/test_telegram_members_export_gui.py`, повторный smoke прошёл без traceback.
- old GUI freeze root cause для этого path закрыт:
  - `tdata`-режим больше не auto-launch'ит внешний portable `Telegram`, который мутировал импортированную session;
  - history-export больше не рвётся по жёсткому `180s` timeout.
- текущий residual risk для operator path:
  - perception of "зависло" теперь чаще означает долгий history scan, а не deadlock;
  - первым делом нужно смотреть, двигаются ли progress-panel и строки `PROGRESS ...`;
  - если пользователь всё ещё недоволен поведением окна, воспроизводить уже не min-size bug, а только manual drag/snap глазами на его экране;
  - если появится новый save-chooser баг, расследовать уже не старый native-portal path, а текущий `Gtk.FileChooserDialog` flow;
  - в live-логе helper могут всплывать transient `MsgidDecreaseRetryError`; если после них счётчики растут дальше, это не отдельный freeze root cause.

## Исторический Live-Факт По Старому Bridge/Helper Path
Последний реальный bottleneck теперь уже не в hub control-plane и не до `force-navigate`.
Он уже сместился внутрь helper-heavy `chat collect`:
- forced stale `tab_id=997919930` уже не актуален; после relaunch живой tab стал `997920139`;
- temp run `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T055744Z/run.json` сначала показал `force-navigate:start -> Network error: timed out`;
- root cause был в раздутом `/home/max/.site-control-kit/state.json` (`88995936` байт, `2286` terminal commands), а не в Telegram DOM;
- `webcontrol/store.py` уже исправлен bounded pruning terminal command history, и после рестарта hub state ужался до `1030707` байт, commands -> `40`;
- новый forced live run `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T060315Z/run.json` уже проходит:
  - `force-navigate:done`
  - `chat-collect:done`
- но затем упирается в:
  - `chat_runtime_limited = 1`
  - `skip mention deep because chat runtime limit was reached`
- то есть текущий реальный blocker уже не в отдельном auxiliary mention-pass как первом фейле, а в том, что helper fallback внутри `chat collect` съедает весь `120s`.
- Следующий live-факт после helper-throughput фиксов:
  - `_wait_for_helper_target_identity()` уже умеет fast-accept по stable helper-route;
  - `_poll_username_from_page_location()` больше не тратит жёсткие `2s` на каждый blank page-url poll;
  - helper session для chat-deep уже reuse-ится через весь `chat collect`.
- Подтверждение:
  - `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T063418Z/run.json`
  - `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T063418Z/export.log`
  - `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T063418Z/export_stats.json`
  - live trace показывает:
    - первый peer -> `helper-open-tab`
    - следующие peer -> `helper-navigate` в тот же `tab_id=997920228`
  - run stats:
    - `deep_attempted_total = 7`
    - `chat_scroll_steps_done = 10`
    - `chat_runtime_limited = 1`
- Значит новый остаточный bottleneck уже ещё точнее:
  - tab/session overhead заметно снижен;
  - page-url over-wait снят;
  - текущий limit теперь в чистом per-peer helper resolve без username-yield, а не в повторном открытии helper tab или старом control-plane timeout.
- Новый live-факт после следующего throughput-шага:
  - helper tab теперь открывается в фоне, reuse path больше не делает лишний `activate_tab`, а отдельный `helper-wait-body` убран;
  - промежуточный run `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T064323Z/run.json` показал остаточный leak: sticky helper path ещё обходил общий helper session и открывал новые tabs;
  - после фикса sticky shared session следующий run `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T064626Z/run.json` больше не показал возврата к multi-tab churn:
    - один `helper-open-tab`;
    - дальше `helper-navigate 0.69..1.23s` в тот же `tab_id=997920238`;
    - `helper-wait-body` в trace отсутствует;
    - `chat_scroll_steps_done = 11`
    - `deep_attempted_total = 7`
    - `chat_runtime_limited = 1`
- Значит текущий live blocker теперь уже совсем узкий:
  - не helper open-tab churn;
  - не sticky отдельные helper tabs;
  - а `helper-wait-identity`, который на zero-yield peer стабильно держит около `2.0..2.5s` и съедает runtime до отдельного mention-pass.
- Новый live-факт после следующего identity-шага:
  - `_wait_for_helper_target_identity()` теперь читает route через direct `get_page_url`, а не только через stale heartbeat `tab_url`;
  - diagnostic run `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T070235Z/run.json` сначала ухудшил stage:
    - `helper-wait-identity` avg вырос до `2.987s`;
    - в trace появились пики `3.53..3.56s`;
  - это позволило локализовать новый точный runtime bug: `_get_page_url_best_effort()` всё ещё держал hidden minimum `1s`.
- После corrective fix:
  - run `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T070607Z/run.json`
  - log `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T070607Z/export.log`
  - stats `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T070607Z/export_stats.json`
  - `helper-wait-identity` avg вернулся к `2.243s`, что уже близко к pre-change baseline `2.146s` из `20260426T064626Z`;
  - массового `3.5s` regression больше нет;
  - но current blocker всё равно остаётся в этом же stage: норма пока всё ещё около `2.08..2.21s`, и отдельные outlier peer могут давать `2.88s`.
- Новый live-факт после следующего helper-profile шага:
  - пустой `RightColumn` shell больше не считается успешным profile-open;
  - helper profile-open теперь приоритетно кликает по `.MiddleHeader .ChatInfo .fullName` и `.MiddleHeader .ChatInfo`.
- Manual verify:
  - known-good peer `306536305` после ~`11s` и клика по `.MiddleHeader .ChatInfo(.fullName)` реально показывает `User Info` с `@alxkat`;
  - это доказывает, что profile path на текущем DOM живой, если до него дойти правильным selector.
- Новый full live run:
  - `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T075023Z/run.json`
  - `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T075023Z/export.log`
  - `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T075023Z/export_stats.json`
  - run остался weak:
    - `deep_attempted_total = 2`
    - `deep_updated_total = 0`
    - `chat_revisited_view_steps = 3`
    - `discovery_new_visible = 0`
  - главное уточнение:
    - helper usernames не появились не потому, что справа открывается пустой shell;
    - а потому, что оба helper peer завершились на `helper-wait-identity ... matched=0` и exporter не дошёл до исправленного profile-open path.
- Новый live-факт после следующего helper-route шага:
  - `_soft_confirm_helper_target_route()` уже добавлен и не принимает route при conflicting header/title;
  - soft-route path теперь делает короткий deadline-aware foreground kick;
  - numeric helper-route после `soft=1` больше не тратит budget на пустой `quick-url/page-url`.
- Первый свежий isolated run:
  - `/tmp/tg_mention_probe_live_softroute/chat_-1002465948544/runs/20260426T081833Z/run.json`
  - `/tmp/tg_mention_probe_live_softroute/chat_-1002465948544/runs/20260426T081833Z/export.log`
  - `/tmp/tg_mention_probe_live_softroute/chat_-1002465948544/runs/20260426T081833Z/export_stats.json`
  - live trace впервые показал:
    - `helper-soft-route matched=1`
    - `helper-soft-activate`
    - `helper-wait-identity matched=1 soft=1`
    - затем `helper-quick-url` и `helper-page-url`
  - run stats:
    - `deep_attempted_total = 5`
    - `deep_updated_total = 0`
    - `chat_runtime_limited = 0`
    - `members_with_username = 5`
- Но следующий live-факт после двух fresh-run ещё точнее:
  - `/tmp/tg_mention_probe_live_softroute2/chat_-1002465948544/runs/20260426T082107Z/run.json`
  - `/tmp/tg_mention_probe_live_softroute3/chat_-1002465948544/runs/20260426T082310Z/run.json`
  - тот же sticky peer `972235006` уже снова дал `helper-soft-route matched=0`;
  - обычные helper peer `1070441119`, `1410391920`, `384346224` тоже закончили на `matched=0`;
  - до `helper-header-html` / `helper-read-profile` exporter в этих run не дошёл.
- Значит текущий live blocker теперь ещё уже:
  - не helper open-tab/session reuse;
  - не пустой profile shell;
  - а нестабильная materialization helper-route target на live Telegram DOM;
  - soft-route fallback уже умеет иногда провести peer на одну стадию дальше, но пока не стабильно и без username-yield.
- Новый code/live-факт на 2026-04-27:
  - в exporter добавлен route source-of-truth trace probe:
    - `helper-route-probe-prewait`
    - `helper-route-probe-soft`
    - `helper-route-probe-miss`
  - probe логирует четыре конкурирующих сигнала для одного helper peer:
    - `get_page_url` fragment
    - stale `tab_url` fragment
    - stale `tab title`
    - helper header `peer_id/title`
  - плюс итоговые индикаторы `route_match/header_match`.
- Текущее ограничение live-валидации этого шага:
  - run `/tmp/tg_route_probe_live/chat_-1002465948544/runs/20260427T063636Z/run.json` завершился ранним `get_html ... expired`;
  - в `/api/clients` Telegram bridge clients (`client-601f...`, `client-83e1...`) были `online=false`;
  - поэтому новый probe подтверждён unit/regression слоем, но не подтверждён полным live helper-stage trace на online client.

Новый эксплуатационный факт на 2026-04-29:
- для ручной/автоматической смены аккаунтов и клиентов больше не нужен отдельный shell-хак:
  - `scripts/telegram_members_export_gui.sh` теперь умеет выбирать `auto/manual` `client_id`;
  - можно добавлять/хранить API-аккаунты через `scripts/telegram_api_accounts.py`;
  - `run_chat_export_once.sh` принимает target overrides (`client_id`, `tab_id`) и валидирует target client до запуска экспорта.

Новый live-факт на 2026-04-25:
- discovery state стал persistent и полезным между run, а не просто формальным файлом:
  - live pair-run `/home/max/site-control-kit/artifacts/telegram_exports/20260425_091528_chat_1002465948544_15.md` и `/home/max/site-control-kit/artifacts/telegram_exports/20260425_091937_chat_1002465948544_22.md` дал `seen_peer_ids: 15 -> 23`;
  - blank peers `5364308868` и `7965869498` попали в cooldown вместо повторного сжигания каждого следующего run.
- chain orchestration тоже уже адаптирован под этот discovery layer:
  - `/home/max/telegram_contact_batches/chat_-1002465948544/chains/20260425T052627Z/chain.json`
  - даже с `--stop-after-idle 1` chain выполнил `2` live run подряд, потому что оба были productive по discovery/coverage;
  - run1 дал `18` unique members, `9` members_with_username, `discovery_new_visible=18`;
  - run2 дал `23` unique members, `8` members_with_username, `discovery_new_visible=9`;
  - суммарно `discovery_progress_runs=2`, `discovery_new_visible_total=27`.
- Следующий реальный bottleneck после этого уже уже:
  - на боевом `discovery_state.json` cooldown peers сейчас `966384255` и `6964266260`;
  - оба пришли как `helper_blank:context_missing`;
  - значит scheduler/idle layer уже не главный limit, а helper-resolve для реально неизвестных peer всё ещё слабый.
- Новый live-факт после следующей правки:
  - repeated identical view stop-path уже внедрён и live-подтверждён;
  - chain `/home/max/telegram_contact_batches/chat_-1002465948544/chains/20260425T063414Z/chain.json` больше не жёг весь `180s` на одном и том же слое;
  - run `20260425T063414Z` и `20260425T063708Z` остановились с `chat_scroll_steps_done=3`, `chat_revisited_view_steps=3`, `chat_runtime_limited=0`.
- Это сдвинуло bottleneck ещё точнее:
  - scroll waste уже не главный источник потерь;
  - следующий limit теперь в `chat mention deep done: processed 2, filled 0`;
  - discovery state при этом не получил новых `peer_states`, значит zero-yield deep peer пока недостаточно хорошо запоминаются между run.
- Новый live-факт после следующего фикса:
  - raw chat mentions теперь нормально нормализуются даже без префикса `@`;
  - `discovery_state.json` уже хранит `mention_candidate_states` и cooldown именно для zero-yield mention-кандидатов;
  - chain `/home/max/telegram_contact_batches/chat_-1002465948544/chains/20260425T070126Z/chain.json` это подтвердил:
    - run1 `20260425T070126Z` дал `deep_attempted_total=2`, `deep_updated_total=0`;
    - run2 `20260425T070502Z` уже дал `deep_attempted_total=0`, `deep_updated_total=0`.
- Это сдвинуло bottleneck ещё раз:
  - repeated same-candidate zero-yield уже снят;
  - теперь текущий limit не в повторении тех же mention-кандидатов, а в кандидатах, которые вообще не раскрывают целевой `peer_id` и уходят в `mention_peer_unknown`;
  - live discovery state уже содержит такие записи:
    - `@plaguezonebot`
    - `@oleghellmode`
- Новый code-level факт после этого:
  - mention URL-pass теперь читает identity через waited opened header/attribute fallback и safe unique title-match fallback;
  - extra mention-pass теперь best-effort, ограничен по runtime и по candidate count через `TELEGRAM_CHAT_MENTION_DEEP_MAX_PER_STEP`.
- Новый live-факт после этого:
  - temp probe `/tmp/tg_mention_probe_root/chat_-1002465948544/runs/20260425T082329Z/run.json` остался `partial`;
  - forced live run на `client-601f3396-50aa-4989-ae5d-9c450e28f65e` / `tab 997919930` дошёл только до:
    - `chat auto-stop after repeated identical discovery view (4 steps)`
    - `history backfill restored 5 username(s)`
  - `chat mention deep done` не появился, значит новый остаточный limit сидит уже внутри первого auxiliary mention-pass на live DOM.

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
5. Текущий честный baseline теперь `10` safe usernames в `latest-safe` контуре этой группы, но целевая планка уже поднята до `100 @username`.
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
