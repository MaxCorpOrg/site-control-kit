# Current Backlog And Next Steps

## Обновление 2026-04-30
- Для текущего GUI/tdata кейса закрыт следующий UX-кусок:
  - progress теперь виден не только в текстовом логе, но и в отдельном panel-блоке;
  - stop-button теперь штатно останавливает helper и возвращает partial result.
- Закрыт новый окно/resize дефект:
  - длинные chat-title больше не должны блокировать уменьшение GTK-окна;
  - live X11 verify уже подтвердил normal resize hints (`min-size 46x46`).
- Закрыт новый runtime-дефект в tdata GUI path:
  - первый живой smoke поймал `AttributeError ... _is_tdata_target` после загрузки чатов;
  - fix уже внесён, повторный smoke завершился без traceback.
- Закрыт дефолтный export-timeout:
  - для полного history-run `TELEGRAM_TDATA_EXPORT_TIMEOUT_SEC` теперь по умолчанию `0`, то есть без лимита.
- Закрыт save-dialog баг:
  - `Выбрать .md файл` переведён на `Gtk.FileChooserDialog`;
  - live X11 probe подтвердил появление окна `Куда сохранить Telegram export`.
- Что уже подтверждено live:
  - direct helper stop на `-1001753733827` после `timeout 12s` -> `history_messages_scanned=600`, `42` usernames, `interrupted=true`;
  - backend cancel probe после `7s` -> `history_messages_scanned=500`, `rows=35`, `interrupted=true`.
  - GTK smoke через само окно на `DISPLAY=:0` -> `8` чатов, выбран `-1001753733827`, stop после первого progress, partial result `history_messages_scanned=300`, `usernames_found=30`, `safe_count=30`.
- Практический следующий шаг для нового агента:
  - делать уже не короткий smoke, а полный history-run на целевом чате через GTK GUI рядом с пользователем;
  - проверить, устраивает ли пользователя частота progress updates, формат partial-result при stop и новый save-dialog;
  - если пользователь всё ещё жалуется на окно, проверять уже manual drag/snap поведение на его экране, а не старый min-size баг;
  - если нужно более частое подтверждение "скан жив" даже после нового default `TELEGRAM_TDATA_PROGRESS_EVERY=250`, отдельно уменьшать этот параметр, не ломая full-history default и не возвращаясь в старый bridge/helper P0 без причины.

## Обновление 2026-04-29 (добавочно)
- Новый operator-priority для текущего пользовательского кейса:
  - P0 сейчас не старый helper-route/source-of-truth для bridge path;
  - P0 сейчас это удержание и live-верификация `tdata-history-authors` path в GTK GUI.
- Что уже подтверждено:
  - `BigpharmaMarket` (`-1001461811598`) при `history-limit=5000` -> `34` уникальных `@username`, включая `@EgorTuchkov`;
  - `-1001753733827` при `history-limit=5000` -> `135` safe usernames с progress-логом в GUI.
- Практический следующий шаг для нового агента:
  - делать полный history-run (`TELEGRAM_TDATA_HISTORY_LIMIT=0`) на пользовательском целевом чате;
  - если пользователь жалуется на "зависло", сначала проверять progress и только потом увеличивать `TELEGRAM_TDATA_EXPORT_TIMEOUT_SEC`;
  - после полного прогона зафиксировать `safe_count`, путь к `.md`, `*_usernames.*` и любые наблюдения по времени выполнения в `CODEX_STATE.md`.
- Закрыт отдельный продуктовый критерий по quality-output:
  - bot-аккаунты теперь отфильтровываются из итоговых `@username` sidecar по умолчанию;
  - deep-path не тратит runtime на bot-target;
  - добавлен override `--include-bots` для диагностических запусков.
- P0 по helper-route/source-of-truth остаётся прежним:
  - нужен короткий live trace-run на реально online bridge client/tab;
  - затем выбор дополнительного стабильного сигнала для прохода к `.MiddleHeader .ChatInfo` без cross-peer misbind.

## Следующий Приоритет P0
### Добор Username Через Более Агрессивный Helper/Discovery Path
Статус на 2026-04-27:
- control-plane timeout уже снят:
  - stale `tab_id=997919930` больше не нужно дожимать;
  - `webcontrol/store.py` уже pruning-ит terminal command history;
  - `/home/max/.site-control-kit/state.json` ужался с `88995936` до `1030707` байт;
  - forced live run `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T060315Z/run.json` проходит `force-navigate` и весь `chat collect`.
- новый точный blocker после этого:
  - не до `force-navigate:done`;
  - не между `force-navigate:done` и `chat-collect:start`;
  - не в первом отдельном auxiliary mention-pass;
  - а внутри `chat collect`, где серия `menu_missing -> helper-open-tab -> helper-wait-body -> helper-wait-identity` по нескольким peer съедает `120s`.
- свежий live baseline после этого фикса:
  - run `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T060315Z/run.json`
  - `unique_members = 41`
  - `members_with_username = 14`
  - `history_backfilled_total = 14`
  - `deep_attempted_total = 5`
  - `deep_updated_total = 0`
  - `chat_runtime_limited = 1`
  - `discovery_new_visible = 41`
- значит новый P0 уже уже конкретный:
  - ускорять helper-heavy `chat collect`;
  - уменьшать per-peer helper cost до того, как run упрётся в `CHAT_MAX_RUNTIME=120`;
  - только после этого смотреть, сколько места остаётся на отдельный mention pass.
- следующий live сдвиг после этого уже есть:
  - route-based helper identity fast-path и bounded page-url poll уже внедрены;
  - helper session reuse между scroll-step уже работает;
  - live run `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T063418Z/run.json` показал:
    - `deep_attempted_total = 7`
    - `chat_scroll_steps_done = 10`
    - `chat_runtime_limited = 1`
  - в `export.log` видно reuse:
    - первый peer -> `helper-open-tab`
    - дальше -> `helper-navigate`
- значит текущий P0 теперь ещё уже:
  - не тратить следующий цикл на инфраструктуру helper tab reuse;
  - искать, как снизить zero-yield per-peer helper resolve после `helper-navigate`, потому что именно он теперь съедает остаток `120s`.
- следующий live сдвиг после этого уже тоже сделан:
  - helper tab переведён в background mode;
  - reuse path больше не делает лишний `activate_tab`;
  - `helper-wait-body` убран;
  - sticky helper fallback теперь reuse-ит тот же `chat_helper_session`.
- промежуточный run `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T064323Z/run.json` показал, что без последнего sticky фикса leak ещё оставался:
  - sticky helper path открывал новые tabs;
  - `deep_attempted_total = 8`
  - `members_with_username = 11`
- финальный live re-verify `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T064626Z/run.json` уже подтвердил:
  - один `helper-open-tab` и дальше только `helper-navigate` в тот же `tab_id=997920238`;
  - `helper-wait-body` полностью исчез;
  - `chat_scroll_steps_done = 11`;
  - `deep_attempted_total = 7`;
  - `chat_runtime_limited = 1`.
- значит новый P0 теперь уже предельно конкретный:
  - резать `helper-wait-identity` на zero-yield peer;
  - не тратить следующий цикл на sticky/open-tab/session plumbing, оно уже доведено до рабочего reuse.
- следующий live сдвиг после этого тоже уже сделан:
  - `_wait_for_helper_target_identity()` переведён на direct route read через `get_page_url`;
  - добавлен early reject для stable non-target route;
  - `_get_page_url_best_effort()` теперь поддерживает real short budgets до `0.3s`.
- важный промежуточный факт:
  - run `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T070235Z/run.json` сначала дал regression по `helper-wait-identity`;
  - это не новый DOM blocker, а полезный диагностический шаг, который вскрыл hidden `1s` floor в `_get_page_url_best_effort()`.
- после corrective fix run `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T070607Z/run.json` уже вернул stage почти к baseline:
  - `helper-wait-identity` avg `2.243s`;
  - `unique_members = 41`
  - `members_with_username = 11`
  - `deep_attempted_total = 7`
  - `chat_scroll_steps_done = 12`
  - `chat_runtime_limited = 1`
- значит новый P0 после этого не меняется по сути:
  - short-budget bug уже снят;
  - но сам zero-yield helper identity wait всё ещё основной limit и лучший live ceiling `14 @username` пока не побит.
- следующий шаг после этого уже тоже проверен:
  - helper profile-open path починен против пустого `RightColumn` shell;
  - приоритет клик-селекторов смещён на `.MiddleHeader .ChatInfo(.fullName)`.
- manual verify подтвердил:
  - direct helper page на known-good peer `306536305` может показать `@alxkat`, если до working `.MiddleHeader .ChatInfo` path реально дойти.
- full live run `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T075023Z/run.json` показал, что текущий P0 стал ещё уже:
  - profile shell bug уже не основной blocker;
  - exporter почти не доходит до repaired profile-open path, потому что helper peer раньше заканчиваются на `helper-wait-identity matched=0`.
- значит новый P0 теперь уже максимально конкретный:
  - либо ослаблять/обходить helper identity gate для route-matched peer;
  - либо находить более прямой путь к populated `User Info`, который не зависит от позднего helper identity confirmation.
- следующий live сдвиг после этого уже есть:
  - `_soft_confirm_helper_target_route()` добавлен и не принимает conflicting header/title;
  - helper path при `soft=1` делает короткий deadline-aware foreground kick;
  - numeric helper-route после `soft=1` больше не тратит budget на пустой URL polling.
- первый чистый live run этого шага:
  - `/tmp/tg_mention_probe_live_softroute/chat_-1002465948544/runs/20260426T081833Z/run.json`
  - показал первый реальный шаг дальше identity gate:
    - `helper-soft-route matched=1`
    - `helper-wait-identity matched=1 soft=1`
    - затем `helper-quick-url` и `helper-page-url`
  - при этом:
    - `deep_attempted_total = 5`
    - `deep_updated_total = 0`
    - `chat_runtime_limited = 0`
- но два следующих fresh-run:
  - `/tmp/tg_mention_probe_live_softroute2/chat_-1002465948544/runs/20260426T082107Z/run.json`
  - `/tmp/tg_mention_probe_live_softroute3/chat_-1002465948544/runs/20260426T082310Z/run.json`
  - показали, что тот же sticky peer `972235006` легко скатывается обратно в `helper-soft-route matched=0`, а обычные helper peer тоже завершаются на `matched=0`.
- значит новый P0 после этого уже предельно конкретный:
  - не чинить снова shell/session/open-tab;
  - не тратить цикл на старый `helper-page-url` waste, он уже подрезан;
  - разбираться именно с тем, почему target helper-route на live DOM то materialize-ится, то нет.
- следующий логический ход (обновлено на 2026-04-27):
  - code-level шаг source-of-truth уже внедрён:
    - в trace добавлены `helper-route-probe-prewait`, `helper-route-probe-soft`, `helper-route-probe-miss`;
    - probe сравнивает `get_page_url`, stale `tab_url`+title и helper header identity в одном peer-cycle;
  - но live-подтверждение этого probe пока заблокировано средой:
    - run `/tmp/tg_route_probe_live/chat_-1002465948544/runs/20260427T063636Z/run.json` упал ранним `get_html ... expired`;
    - `/api/clients` показывал Telegram clients в `online=false`;
  - следующий практический шаг:
    - поднять online bridge client/tab и повторить короткий trace-run;
    - по новому probe выбрать безопасный дополнительный signal для стабильного прохода к `.MiddleHeader .ChatInfo` без cross-peer misbind.
- более старый статус на 2026-04-25 для контекста:
- sticky-author click-path уже внедрён: правый клик попадает в нижнюю 34px иконку автора через `telegram_sticky_author`, live probe дал `source=point`, `context_clicked=true`;
- sticky-author mention сейчас упирается не в координаты, а в отсутствие `Mention` в Telegram menu (`menu_missing`), после чего exporter уже запускает sticky helper fallback;
- sticky helper fallback подтвердил новые peer-bound usernames: `@alxkat` и `@Mitiacaramba`;
- live wrapper smoke `/tmp/telegram_live_sticky_icon.md` подтвердил это в обычном exporter path: `18` members, `10` usernames, sticky peer `6964266260` дошёл до `menu_missing`;
- combined artifact уже превысил цель 50: `/tmp/telegram_combined_54_usernames.txt`, но это объединение peer-bound и chat-mentions источников;
- pre-deep history backfill уже сделан;
- stale explicit history override уже закрыт;
- parser false-positive из message text уже закрыт;
- helper stale cross-peer misbind уже закрыт;
- known peer больше не должен тратить helper/deep runtime, если username есть в `identity_history.json`;
- live smoke `/tmp/telegram_live_after_prefill.md` подтвердил `9` pre-deep restored usernames на чате `https://web.telegram.org/a/#-1002465948544`;
- live verify `/tmp/telegram_live_verify_2.md` на явном stale history path дал `20` members, `8` usernames и `output_usernames_cleared_total = 0`;
- новый unknown peer `8055002493` стал первым реальным deep-кандидатом, но не отдал username за `90s`;
- значит P0 остаётся helper/discovery throughput, но уже для реально неизвестных peer, а не для повторного обхода history-known людей.
- discovery-aware chain baseline уже есть:
  - `/home/max/telegram_contact_batches/chat_-1002465948544/chains/20260425T052627Z/chain.json`
  - live chain с `--stop-after-idle 1` всё равно выполнил оба run, потому что продуктивность теперь считается и по discovery/coverage;
  - `discovery_progress_runs=2`, `discovery_new_visible_total=27`, `best_unique_members=23`.
- numbered batches после нового live chain:
  - `8.txt`
  - `9.txt`
  - суммарно `16` уникальных batch usernames.

Нужен следующий логический шаг:
- не тратить ещё цикл на старый generic `Mention` path как на основной;
- если sticky-author найден, работать с ним через правый клик по нижней иконке, а не через профиль или текст сообщения;
- не тратить deep на peer, уже восстановленные из history;
- использовать discovery-aware chain как основной исполнительный контур к `100`, а не только как вспомогательный smoke-run;
- усиливать discovery/scroll и helper-tab throughput, чтобы за тот же runtime проходить больше peer;
- отдельно держать границу: "combined 50+" уже есть, "50 peer-bound members from fresh helper/profile" ещё нет;
- только так двигать общий набор usernames к цели `100`.
- текущий baseline после свежего live-verify уже заметно лучше прежнего:
  - fast run `20260423T173223Z` дал `27` visible members и `10` safe usernames;
  - `latest_full.*` и `latest_safe.*` уже promoted на этот run;
  - но deep всё ещё обработал только `2` peer за `120s`;
  - а новый verify `20260424_171947_chat_1002465948544_20.md` подтвердил, что correctness-слой уже стабилен и следующий шаг должен улучшать именно throughput helper/discovery, а не снова чинить history/latest layer.
- scheduler cap уже внедрён в код (`TELEGRAM_CHAT_DEEP_STEP_MAX_SEC`), а chain runner уже умеет не умирать на пустом batch delta, поэтому следующий практический шаг теперь такой:
  - запускать длинные chain-run именно через `scripts/telegram_contact_chain.py`;
  - использовать `--target-members-with-username 100` или `--target-safe-count 100`;
  - смотреть не только на `new_usernames`, но и на `discovery_new_visible`, `best_unique_members`, `best_members_with_username`, `seen_peer_ids`;
  - если `discovery_new_visible > 0`, не считать цепочку "пустой", даже если текущий batch прибавил мало.
- Новый сдвиг после live re-verify:
  - repeated identical view stop-path уже внедрён и подтверждён chain `/home/max/telegram_contact_batches/chat_-1002465948544/chains/20260425T063414Z/chain.json`;
  - scroll waste снят, но оба run (`20260425T063414Z`, `20260425T063708Z`) всё равно дали `deep_attempted_total=2`, `deep_updated_total=0`;
  - это и было переведено в следующий P0: не scroll-loop, а zero-yield deep peer после repeated-view stop.
- Новый сдвиг после следующего live verify:
  - chain `/home/max/telegram_contact_batches/chat_-1002465948544/chains/20260425T070126Z/chain.json` уже показал effect от mention-candidate cooldown;
  - run1 `20260425T070126Z` дал `deep_attempted_total=2`, `deep_updated_total=0`;
  - run2 `20260425T070502Z` уже дал `deep_attempted_total=0`, `deep_updated_total=0`;
  - `discovery_state.json` получил `mention_candidate_states` для `@plaguezonebot` и `@oleghellmode` с `mention_peer_unknown`.
- Значит новый P0 уже ещё точнее:
  - repeated same-candidate zero-yield снят;
  - теперь нужно усиливать path, где mention-кандидат вообще не раскрывает целевой `peer_id`, а не просто повторно cooldown-ить те же имена.
- Новый сдвиг после следующего кода:
  - mention URL-pass уже получил waited identity fallback, safe title-match fallback, candidate cap и runtime cap;
  - unit/regression слой на этом уже зелёный (`135 tests OK`);
  - temp forced live-probe `/tmp/tg_mention_probe_root/chat_-1002465948544/runs/20260425T082329Z/run.json` всё ещё `partial`, то есть новый текущий P0 уже внутри первого auxiliary mention-pass на live DOM, а не в самом candidate selection/test слое.

Отдельный подшаг рядом с этим приоритетом:
- больше не нужен как P0:
  - promotion policy для `latest_safe.*` уже учитывает fresh peer-rename.
  - numeric `@username` артефакты уже отфильтрованы в exporter/history/safe-layer.
  - pre-deep history backfill уже внедрён и покрыт тестом.

## Почему Это Следующий Приоритет
Потому что live smoke уже доказал:
- pipeline рабочий;
- profiles рабочие;
- batch wrapper снова рабочий;
- store-lock bottleneck в хабе уже снят;
- runtime reload уже рабочий, heartbeat рекламирует `click_menu_text`;
- wrapper уже сам открывает Telegram tab через bridge client;
- helper fallback в `mention`-режиме уже приносит реальных людей на живом чате;
- live body snapshot подтвердил, что текущий `MessageContextMenu` не содержит `Mention`;
- numeric false-positive username уже снят и не должен больше искажать safe/history outputs;
- значит главный остаточный limit уже в product-path Telegram и в throughput helper/discovery слоя.

## Предлагаемый План Для Следующего Инженерного Шага
1. Поднять throughput helper fallback:
   - уменьшить `helper-wait-identity` на zero-yield peer;
   - сильнее сокращать profile-open path внутри helper;
   - агрессивнее заполнять несколько peer за один visible-layer.
   - `helper-open-tab` и `helper-wait-body` уже больше не главный focus для следующего цикла;
   - с учётом нового reuse особенно смотреть на blank helper resolves после `helper-navigate`, а не на повторный open-tab.
   - direct route read и short-budget bug уже закрыты; следующий подшаг должен резать саму логику identity confirmation, а не снова transport timeout floor.
   - пустой right-column shell уже починен; следующий реальный подшаг должен доводить exporter до repaired `.MiddleHeader .ChatInfo` path, а не ещё раз править shell detection.
2. Усилить discovery:
   - использовать уже существующий cooldown как сигнал для ротации peer между run;
   - раньше отбрасывать peer без практического шанса на новый username;
   - отдельным счётчиком отслеживать рост `seen_peer_ids` в `discovery_state.json`.
   - правило помнить zero-yield `mention deep` peer уже внедрено через `mention_candidate_states`;
   - следующий подшаг: отдельным правилом поднимать/приоритизировать только те mention-кандидаты, которые реально раскрывают `peer_id`, а `mention_peer_unknown` не гонять каждый run.
   - следующий подшаг после этого: разрезать первый auxiliary mention-pass на live DOM и найти, какой именно subcommand съедает его до `chat mention deep done`.
3. Отдельно проверить unknown peer path:
   - начинать с peer, которых нет в `identity_history.json`;
   - не считать успешным run, который снова прошёл только history-known людей.
4. Повторить chain-run `CHAT_PROFILE=deep` с таргетом на `100`.
5. Сравнить:
   - `new_usernames`
   - `deep_updated_total`
   - `members_with_username`
   - `discovery_new_visible`
   - `best_unique_members`
   - `chat_revisited_view_steps`
   - `chat_runtime_limited`
   - содержимое `latest_full.txt` и `latest_safe.txt`
6. Если helper/discovery optimisation всё ещё не даёт роста, искать следующий источник usernames внутри Telegram Web, а не тратить ещё один цикл на obsolete `Mention` path.
   - это теперь особенно важно для кандидатов класса `mention_peer_unknown`, где сам mention уже виден, но profile mapping не даёт peer-bound результата.

## Следующий Приоритет P1
### Разрезать Монолитный Exporter
`export_telegram_members_non_pii.py` уже слишком большой.
Следующее архитектурное улучшение:
- вынести profile/deep selection;
- вынести history/state helpers;
- вынести output/reporting.
- отдельно вынести batch-compatible stats/history/discovery слой, чтобы shell wrappers не зависели от монолита.

## Следующий Приоритет P2
### Единый User-Facing Control Layer
Сейчас shell/GUI уже понимают profile presets.
На 2026-04-29 здесь уже есть новый слой:
- `scripts/telegram_members_export_gui.sh` получил multi-account режим (saved API accounts + auto/manual `client_id`);
- `scripts/telegram_api_accounts.py` хранит реестр аккаунтов и default routing;
- `run_chat_export_once.sh` поддерживает target override (`client_id`, `tab_id`) для GUI/manual запусков.
Но дальше можно сделать ещё лучше:
- унифицировать user prompts;
- показывать summary по profile effect;
- добавлять run summary сразу в GUI после завершения.

## Что Делать Не Нужно В Первую Очередь
- переписывать весь hub;
- пытаться заменять всё Telegram API-клиентом;
- делать большой UI-рефактор поверх zenity;
- добавлять внешние зависимости без явной необходимости.

## Хороший Следующий Acceptance
Хороший следующий результат будет таким:
- новый live chain даёт больше, чем текущий baseline:
  - baseline chain: `/home/max/telegram_contact_batches/chat_-1002465948544/chains/20260425T052627Z/chain.json`
  - baseline run ceiling внутри него:
    - `best_unique_members = 23`
    - `best_members_with_username = 9`
    - `discovery_new_visible_total = 27`
- в `export.log` меньше пустых retry на menu-path и больше реально обработанных peer через helper/discovery;
- `chain.json` больше не останавливается слишком рано на `idle`, пока discovery ещё находит новые peer;
- `latest_full.txt` / `latest_safe.txt` растут дальше к целевой планке `100`;
- если run обновил username у уже известного peer, это изменение не теряется ни в `snapshot_safe`, ни в `identity_history`, ни в `latest_safe.*`;
- если в raw run всплывёт очередной numeric peer-id, он не доезжает до `latest_safe.*` и numbered batch.
