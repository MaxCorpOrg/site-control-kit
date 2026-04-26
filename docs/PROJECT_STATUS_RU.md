# Project Status RU

Последнее обновление: 2026-04-26

Этот файл нужен как точка входа для любого нового чата и любого нового агента.
Перед новой задачей его нужно прочитать целиком.

Repo-root entrypoint для любого агента: `AGENT_START_HERE.md`.

Актуальный onboarding-пакет для нового агента теперь лежит в `docs/agent_handoff_ru/`.
Читать его нужно по номерам файлов, начиная с `00_START_HERE.md`.

## Сделано

### Обновление 2026-04-26
- Новый live blocker был локализован не в Telegram DOM, а в hub control-plane:
  - forced `tab_id=997919930` уже был stale; после relaunch актуальный live tab стал `997920139`;
  - temp run `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T055744Z/run.json` падал на `force-navigate:start` с `Network error: timed out`;
  - root cause: `/home/max/.site-control-kit/state.json` разросся до `88995936` байт и держал `2286` terminal command records, из-за чего `POST /api/commands` не успевал ответить до клиентского timeout.
- В `webcontrol/store.py` сделан bounded pruning terminal command history:
  - сохраняются только последние `40` terminal command records;
  - pruning выполняется на startup и перед save;
  - очереди чистятся от orphan `command_id`;
  - regression coverage добавлен в `tests/test_store.py`.
- После рестарта локального hub:
  - `/home/max/.site-control-kit/state.json` ужался до `1030707` байт;
  - persisted commands сократились до `40`;
  - direct command helpers снова проходят на живом `client-601f3396-50aa-4989-ae5d-9c450e28f65e / tab 997920139`.
- Новый live re-verify:
  - run: `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T060315Z/run.json`
  - log: `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T060315Z/export.log`
  - stats: `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T060315Z/export_stats.json`
  - результат:
    - `unique_members = 41`
    - `members_with_username = 14`
    - `history_backfilled_total = 14`
    - `deep_attempted_total = 5`
    - `deep_updated_total = 0`
    - `chat_runtime_limited = 1`
    - `discovery_new_visible = 41`
- Практический вывод:
  - exporter теперь проходит `force-navigate` и весь `chat collect`;
  - текущий blocker сместился внутрь helper-heavy `chat collect`, где `menu_missing -> helper fallback` съедает `120s`;
  - отдельный mention pass сейчас уже не падает первым, а вообще пропускается из-за `chat runtime limit reached`;
  - значит следующий путь к `100 @username` должен ускорять helper/chat-collect throughput, а не заново чинить hub timeout или stale tab binding.
- Следующий шаг после этого уже внедрён:
  - `_wait_for_helper_target_identity()` получил route-based fast-path с защитой от conflicting header;
  - `_poll_username_from_page_location()` теперь уважает короткий timeout budget;
  - helper session в chat-deep теперь живёт через весь `chat collect`, поэтому после первого helper peer live trace показывает `helper-navigate`, а не новый `helper-open-tab` на каждом step.
- Live re-verify этого шага:
  - run: `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T063418Z/run.json`
  - log: `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T063418Z/export.log`
  - stats: `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T063418Z/export_stats.json`
  - результат:
    - `unique_members = 42`
    - `members_with_username = 12`
    - `history_backfilled_total = 12`
    - `deep_attempted_total = 7`
    - `deep_updated_total = 0`
    - `chat_scroll_steps_done = 10`
    - `chat_runtime_limited = 1`
- Практический смысл нового verify:
  - helper throughput реально вырос: `deep_attempted_total` поднялся с `5` до `7` в том же `120s` окне;
  - `helper-page-url` в live trace больше не висит по `2s`, а `helper-wait-identity` на blank peer стал заметно короче;
  - текущий blocker остаётся в helper-heavy `chat collect`, но уже после снятия лишнего open-tab/page-url waste.
- Следующий live throughput-фикс после этого:
  - helper tabs теперь открываются в фоне и reuse path больше не делает лишний `activate_tab`;
  - отдельный `helper-wait-body` убран;
  - sticky helper fallback переведён на общий `chat_helper_session`, поэтому sticky/menu-missing больше не открывает новый helper tab на каждый шаг.
- Live trace после промежуточного run `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T064323Z/run.json` показал остаточный leak:
  - обычный helper reuse уже работал;
  - но sticky helper ещё плодил новые tabs (`997920230`, `997920232`, `997920234`, `997920235`);
  - stats на этом run: `unique_members = 40`, `members_with_username = 11`, `deep_attempted_total = 8`, `chat_runtime_limited = 1`.
- После sticky shared-session фикса новый live re-verify:
  - run: `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T064626Z/run.json`
  - log: `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T064626Z/export.log`
  - stats: `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T064626Z/export_stats.json`
  - trace подтвердил:
    - helper reuse удержался на одном `tab_id=997920238`;
    - дальше только `helper-navigate 0.69..1.23s` в тот же tab;
    - `helper-wait-body` больше не появляется.
  - run stats:
    - `unique_members = 36`
    - `members_with_username = 9`
    - `deep_attempted_total = 7`
    - `chat_scroll_steps_done = 11`
    - `chat_runtime_limited = 1`
- Практический вывод после последнего verify:
  - repeated helper open-tab/foreground churn больше не главный limit;
  - текущий blocker теперь уже очень узкий: `helper-wait-identity` держит примерно `2.0..2.5s` на zero-yield peer и именно там сгорает runtime внутри `chat collect`;
  - движение к `100 @username` стало ближе по runtime-path, но текущий лучший live результат по username всё ещё у run `20260426T060315Z` (`14` username), так что следующий шаг должен резать именно identity wait, а не снова session overhead.
- Следующий helper-identity шаг на 2026-04-26:
  - `_wait_for_helper_target_identity()` переведён на direct route read через `get_page_url` с fallback на stale `tab_url`;
  - добавлен early reject после двух одинаковых non-target route;
  - `_get_page_url_best_effort()` теперь уважает short budget до `0.3s`.
- Важный промежуточный diagnostic run:
  - `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T070235Z/run.json`
  - он временно ухудшил `helper-wait-identity` (avg `2.987s`, пики `3.53..3.56s`);
  - это вскрыло точный runtime bug: direct `get_page_url` всё ещё тайно ждал минимум `1s`.
- После фикса short budget новый live re-verify:
  - run: `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T070607Z/run.json`
  - log: `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T070607Z/export.log`
  - stats: `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T070607Z/export_stats.json`
  - факты:
    - `helper-wait-identity` avg вернулся к `2.243s` против `2.146s` у pre-change baseline `20260426T064626Z`;
    - основной диапазон снова `2.08..2.21s`, с одним outlier `2.88s`;
    - `unique_members = 41`
    - `members_with_username = 11`
    - `deep_attempted_total = 7`
    - `chat_scroll_steps_done = 12`
    - `chat_runtime_limited = 1`
- Практический вывод:
  - stale `tab_url` dependency в helper identity ослаблена и short-budget bug снят;
  - явный регресс устранён;
  - текущий blocker всё ещё тот же: `helper-wait-identity` остаётся главным zero-yield cost center и ceiling `14` username пока не побит.
- Следующий helper-profile шаг на 2026-04-26:
  - `_open_current_chat_user_info_and_read_username()` теперь сначала пробует `.MiddleHeader .ChatInfo .fullName` и `.MiddleHeader .ChatInfo`;
  - пустой `RightColumn` shell больше не считается успешным profile-open: функция читает правую колонку и продолжает со следующим selector, если справа нет реального profile content.
- Manual helper verify:
  - known-good peer `306536305` после ~`11s` действительно открывает populated `User Info` с `@alxkat`, если кликать по `.MiddleHeader .ChatInfo(.fullName)`;
  - значит проблема уже не в том, что Telegram не умеет показать профиль вообще, а в том, что exporter чаще не доходит до этого места.
- Full live re-verify после этого:
  - run: `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T075023Z/run.json`
  - log: `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T075023Z/export.log`
  - stats: `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T075023Z/export_stats.json`
  - результат:
    - `unique_members = 13`
    - `members_with_username = 5`
    - `deep_attempted_total = 2`
    - `deep_updated_total = 0`
    - `chat_revisited_view_steps = 3`
    - `discovery_new_visible = 0`
- Практический вывод после этого verify:
  - пустой right-column shell уже не главный blocker;
  - новый точный blocker теперь уже перед profile-open: `helper-wait-identity` чаще завершает helper peer как `matched=0`, и exporter не доходит до исправленного `.MiddleHeader .ChatInfo` path;
  - до `100 @username` мы пока не стали ближе по live ceiling, но мы ещё сильнее локализовали, что чинить дальше.
- Следующий helper-route шаг на 2026-04-26:
  - в `scripts/export_telegram_members_non_pii.py` добавлен `_soft_confirm_helper_target_route()` с защитой от conflicting header/title;
  - при `soft=1` helper path теперь делает только короткий deadline-aware foreground kick;
  - numeric helper-route после `soft=1` больше не тратит budget на пустой `quick-url/page-url`, а сохраняет его на header/profile path.
- Проверки после этого:
  - `python3 -m py_compile scripts/export_telegram_members_non_pii.py tests/test_telegram_export_runtime.py` -> OK
  - `PYTHONPATH=/home/max/site-control-kit python3 -m unittest tests.test_telegram_export_runtime` -> `61 tests OK`
  - `PYTHONPATH=/home/max/site-control-kit python3 -m unittest discover -s tests -p 'test_*.py'` -> `160 tests OK`
- Новый живой re-verify на свежем temp root:
  - run: `/tmp/tg_mention_probe_live_softroute/chat_-1002465948544/runs/20260426T081833Z/run.json`
  - log: `/tmp/tg_mention_probe_live_softroute/chat_-1002465948544/runs/20260426T081833Z/export.log`
  - stats: `/tmp/tg_mention_probe_live_softroute/chat_-1002465948544/runs/20260426T081833Z/export_stats.json`
  - trace впервые показал реальный progress по стадиям:
    - `helper-soft-route matched=1`
    - `helper-soft-activate`
    - `helper-wait-identity matched=1 soft=1`
    - затем exporter дошёл до `helper-quick-url` и `helper-page-url`
  - key stats:
    - `unique_members = 13`
    - `members_with_username = 5`
    - `deep_attempted_total = 5`
    - `deep_updated_total = 0`
    - `chat_runtime_limited = 0`
- Но следующий свежий live-факт оказался ещё точнее:
  - runs `/tmp/tg_mention_probe_live_softroute2/chat_-1002465948544/runs/20260426T082107Z/run.json` и `/tmp/tg_mention_probe_live_softroute3/chat_-1002465948544/runs/20260426T082310Z/run.json` показали, что тот же sticky peer `972235006` легко откатывается обратно в `helper-soft-route matched=0`;
  - остальные helper peer (`1070441119`, `1410391920`, `384346224`) тоже остаются на `matched=0`;
  - helper path всё ещё не доходит до `helper-header-html` / `helper-read-profile` стабильно.
- Практический вывод после этого verify:
  - пустой shell и чистый session/open-tab overhead уже не главный blocker;
  - новый текущий blocker уже очень узкий: live Telegram DOM нестабильно materialize-ит helper-route target, поэтому `soft-route` иногда позволяет уйти дальше identity gate, но чаще helper peer всё равно умирает на `matched=0`;
  - к `100 @username` мы приблизились только по runtime-path и по диагностике; реальный live ceiling по username всё ещё не выше `14` на run `20260426T060315Z`.

### Обновление 2026-04-25
- Discovery layer доведён до orchestration:
  - `discovery_state.json` поднят до `version=2` и хранит `peer_states` с `attempt_count`, `failure_count`, `last_outcome`, `cooldown_until`;
  - blank peer после helper/mention fail получает cooldown и не должен съедать следующий run тем же sticky/deep target;
  - если sticky peer уже в cooldown, exporter больше не держит шаг в sticky-only и переключается на других visible peer.
- Live pair-run на временном discovery state подтвердил накопление покрытия между run:
  - `/home/max/site-control-kit/artifacts/telegram_exports/20260425_091528_chat_1002465948544_15.md`
  - `/home/max/site-control-kit/artifacts/telegram_exports/20260425_091937_chat_1002465948544_22.md`
  - `seen_peer_ids: 15 -> 23`
  - cooldown peers: `5364308868`, `7965869498`
- Следующий throughput-фикс сделан в chain runner:
  - `scripts/telegram_contact_chain.py` теперь считает run productive не только по `new_usernames`, но и по росту `unique_members`, `members_with_username`, `discovery_new_visible` и productive deep-yield;
  - добавлен target `--target-members-with-username`;
  - `chain.json` теперь сохраняет реальные effective env текущего запуска, а не только preset profile.
- Live chain verify на боевом chat-dir `/home/max/telegram_contact_batches/chat_-1002465948544`:
  - chain: `/home/max/telegram_contact_batches/chat_-1002465948544/chains/20260425T052627Z/chain.json`
  - run1: `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260425T052627Z/run.json`
    - `unique_members = 18`
    - `members_with_username = 9`
    - `safe_count = 9`
    - `discovery_new_visible = 18`
    - `new_usernames = 1`
  - run2: `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260425T052959Z/run.json`
    - `unique_members = 23`
    - `members_with_username = 8`
    - `safe_count = 8`
    - `discovery_new_visible = 9`
    - `new_usernames = 1`
  - ключевой факт: даже при `--stop-after-idle 1` chain выполнил оба run, потому что оба считались productive по discovery/coverage, а не только по batch delta.
- После live chain:
  - `discovery_state.json` на chat-dir имеет `seen_peer_ids = 27`;
  - cooldown peers: `966384255`, `6964266260`;
  - numbered batches пополнились файлами `8.txt` и `9.txt`, суммарно это уже `16` уникальных batch usernames.
- Новые archive artifacts:
  - `/home/max/site-control-kit/artifacts/telegram_exports/20260425_092958_chat_1002465948544_18.md`
  - `/home/max/site-control-kit/artifacts/telegram_exports/20260425_093414_chat_1002465948544_23.md`
- Verify:
  - `tests/test_telegram_contact_chain.py` -> `16 tests OK`;
  - parser/runtime после mention-candidate фикса -> `50 tests OK`;
  - полный `unittest discover` -> `129 tests OK`.
- Практический вывод:
  - correctness-слой сейчас уже не главный limit;
  - новый реальный путь к `100 @username` — это длинные discovery-aware chain runs с таргетом по `members_with_username`/`safe_count`, а не одиночные ручные smoke-run.
- Новый live-факт после этого baseline:
  - `deep` chain-run на `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260425T062608Z/run.json` вскрыл новый runtime waste:
    - `8` scroll steps дали те же `15` peer;
    - `discovery_new_visible = 0`;
    - `discovery_revisit_steps = 8`;
    - `deep_attempted_total = 0`;
    - exporter дожигал весь `180s`.
- После точечного фикса repeated identical view:
  - `scripts/export_telegram_members_non_pii.py` теперь останавливает такой run раньше, независимо от `minimum_steps`;
  - stats всегда содержат `revisited_view_steps`, `burst_scrolls_done`, `jump_scrolls_done`.
- Live re-verify:
  - chain `/home/max/telegram_contact_batches/chat_-1002465948544/chains/20260425T063414Z/chain.json` завершился как `stopped_on_no_growth` уже после `2` run, а не после длинной пустой серии;
  - оба run (`20260425T063414Z`, `20260425T063708Z`) дали:
    - `chat_scroll_steps_done = 3`
    - `chat_revisited_view_steps = 3`
    - `chat_runtime_limited = 0`
    - `deep_attempted_total = 2`
    - `deep_updated_total = 0`
  - новые archives:
    - `/home/max/site-control-kit/artifacts/telegram_exports/20260425_103707_chat_1002465948544_15.md`
    - `/home/max/site-control-kit/artifacts/telegram_exports/20260425_104015_chat_1002465948544_15.md`
- Практический вывод после этого патча:
  - scroll-loop waste снят;
  - bottleneck сместился дальше, в `mention deep` без yield после repeated-view stop;
  - следующий шаг к `100` был переведён в cooldown/deprioritize для zero-yield deep peer, а не в scroll/parser/history.
- Новый live-факт после этого:
  - `_normalize_username_from_mention_input()` теперь принимает raw `username` без `@`, который реально возвращает chat mention extractor;
  - `discovery_state.json` теперь хранит `mention_candidate_states` и cooldown для zero-yield mention-кандидатов.
- Live re-verify нового mention-candidate cooldown:
  - chain `/home/max/telegram_contact_batches/chat_-1002465948544/chains/20260425T070126Z/chain.json`
  - run1 `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260425T070126Z/run.json` дал `deep_attempted_total = 2`, `deep_updated_total = 0`
  - run2 `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260425T070502Z/run.json` уже дал `deep_attempted_total = 0`, `deep_updated_total = 0`
  - `discovery_state.json` получил `mention_candidate_states` для `@plaguezonebot` и `@oleghellmode` с outcome `mention_peer_unknown`
  - новые archives:
    - `/home/max/site-control-kit/artifacts/telegram_exports/20260425_110501_chat_1002465948544_15.md`
    - `/home/max/site-control-kit/artifacts/telegram_exports/20260425_110714_chat_1002465948544_15.md`
- Практический вывод после этого verify:
  - repeated same-candidate zero-yield уже не ест второй run;
  - новый bottleneck ещё точнее: unknown mention-кандидаты, которые не мапятся в целевой `peer_id`, а не сам repeated-view или scroll-loop.
- Новый инженерный шаг после этого:
  - extra mention URL-pass теперь читает identity через waited header/opened identity fallback, а не только через один body regex;
  - добавлен безопасный exact title-match fallback для случаев без `peer_id`;
  - extra mention-pass переведён на best-effort HTML read, runtime budget и candidate cap через `TELEGRAM_CHAT_MENTION_DEEP_MAX_PER_STEP`;
  - на этом auxiliary path укорочены navigate/read/restore timeouts.
- Verify:
  - parser/runtime после этого шага -> `56 tests OK`;
  - полный `unittest discover` -> `135 tests OK`.
- Live status этого шага пока частичный:
  - temp probe `/tmp/tg_mention_probe_root/chat_-1002465948544/runs/20260425T082329Z/run.json` остался `partial`;
  - log `/tmp/tg_mention_probe_root/chat_-1002465948544/runs/20260425T082329Z/export.log` дошёл только до repeated-view stop и history backfill;
  - значит следующий live blocker уже уже не в parser/tests, а в первом реальном auxiliary mention-pass на live DOM.
### Обновление 2026-04-24
- Продолжен sticky/helper path после фикса попадания по иконке:
  - если sticky context menu открылось, но `Mention` отсутствует (`menu_missing`), exporter теперь сразу пробует helper-tab для того же sticky `peer_id`;
  - добавлены stats `sticky_helper_attempted` и `sticky_helper_updated`;
  - для best-effort команд `raise_on_fail=False` сокращён missing-result grace до 0.4..1.2s, чтобы selector miss не ждал до 90s и не съедал helper runtime.
- Live-подтверждения нового sticky helper fallback:
  - `/tmp/telegram_live_sticky_helper.md`: `306536305 -> @alxkat`;
  - `/tmp/telegram_live_sticky_helper_fastgrace.md`: `1127139638 -> @Mitiacaramba`;
  - archives:
    - `/home/max/site-control-kit/artifacts/telegram_exports/20260424_162705_chat_1002465948544_18.md`
    - `/home/max/site-control-kit/artifacts/telegram_exports/20260424_163137_chat_1002465948544_20.md`
- По сумме текущих источников уже собран deliverable на `54` уникальных `@username`:
  - `/tmp/telegram_combined_54_usernames.txt`
  - `/tmp/telegram_combined_54_usernames.json`
  - `/home/max/site-control-kit/artifacts/telegram_exports/20260424_164916_combined-usernames_1002465948544_54.txt`
  - `/home/max/site-control-kit/artifacts/telegram_exports/20260424_164916_combined-usernames_1002465948544_54.json`
- Важно: combined `54` смешивает peer-bound member sidecars и chat-mentions; строго peer-bound sticky/helper path пока даёт новые username медленнее.
- Закрыт stale-history conflict:
  - `_load_identity_history()` теперь сравнивает `updated_at` и предпочитает более свежий archive state перед устаревшим explicit `CHAT_IDENTITY_HISTORY`;
  - более старый history-файл используется только как secondary source для отсутствующих non-conflicting записей;
  - live verify с явным `/home/max/telegram_contact_batches/chat_-1002465948544/identity_history.json` больше не воспроизводит конфликт `@super_pavlik`;
  - chat-dir `identity_history.json` обновлён и теперь снова содержит:
    - `@super_pavlik -> 1621138520`
    - `@alxkat -> 306536305`
    - `@mitiacaramba -> 1127139638`
- Закрыт parser false-positive по message text:
  - `_parse_chat_members()` больше не берёт `@username` из текста сообщения;
  - username ищется только в author/header block;
  - это убрало ложный захват `@super_pavlik` у peer `1663660771`.
- Закрыт stale helper misbind:
  - helper-tab теперь ждёт подтверждение ожидаемого `peer_id` или имени перед чтением username;
  - прежний ложный кейс `6964266260 (Evgeniy) -> @Tri87true` больше не воспроизводится;
  - live verify `/tmp/telegram_live_verify_2.md` дал `20` members, `8` usernames и `output_usernames_cleared_total = 0`;
  - archive: `/home/max/site-control-kit/artifacts/telegram_exports/20260424_171947_chat_1002465948544_20.md`.
- Добавлен sticky-author path для Telegram username export:
  - `extension/content.js` теперь поддерживает `telegram_sticky_author`;
  - правый клик делается по нижней прилипшей 34px иконке автора через `elementsFromPoint`, без клика по тексту сообщения и без ухода в профиль;
  - `scripts/export_telegram_members_non_pii.py` использует sticky-author mention первым и ограничивает deep текущим sticky peer, если он найден.
- Live-проверка на `https://web.telegram.org/a/#-1002465948544` после перезапуска Chrome с extension `0.1.5`:
  - `peer_id=8055002493`;
  - `source=point`;
  - `point={x:512,y:539}`;
  - `rect=506,535,540,569`, `34x34`;
  - `context_click=true` вернул `context_clicked=true`;
  - menu-path отработал, но `Mention` в текущем Telegram menu отсутствует: результат `menu_missing`.
  - heartbeat capabilities пока не рекламируют `telegram_sticky_author`, но direct command выполняется; exporter использует direct command и не блокируется этим флагом.
- Live wrapper smoke после фикса sticky icon:
  - output: `/tmp/telegram_live_sticky_icon.md`;
  - archive: `/home/max/site-control-kit/artifacts/telegram_exports/20260424_143524_chat_1002465948544_18.md`;
  - результат: `18` members, `10` usernames;
  - log-факт: `sticky chat author 6964266260 (Evgeniy)` -> `sticky mention unresolved ... (menu_missing)`.
- Добавлены stats sticky-path:
  - `sticky_authors_seen`
  - `sticky_mention_attempted`
  - `sticky_mention_updated`
- Добавлен pre-deep history backfill для Telegram chat export:
  - `scripts/export_telegram_members_non_pii.py` теперь восстанавливает username из `historical_peer_to_username` сразу после dedupe visible members и до выбора `deep_targets`;
  - уже известные peer больше не тратят `CHAT_DEEP_LIMIT` и helper/deep runtime;
  - stats получили `history_prefilled` и `history_prefill_conflicts`.
- Закрыт регрессионный тестом новый важный сценарий:
  - если `peer_id` уже есть в history, `_collect_members_from_chat()` проставляет username до deep;
  - `_enrich_usernames_deep_chat()` в этом случае не вызывается.
- Verify:
  - `node --check extension/content.js && node --check extension/background.js` -> OK;
  - `tests.test_telegram_export_parser tests.test_telegram_export_runtime` -> `43 tests OK`;
  - расширенный Telegram-related набор -> `82 tests OK`;
  - полный `unittest discover` -> `117 tests OK`.
- Live smoke на текущем чате `https://web.telegram.org/a/#-1002465948544`:
  - output: `/tmp/telegram_live_after_prefill.md`;
  - archive: `/home/max/site-control-kit/artifacts/telegram_exports/20260424_132543_chat_1002465948544_22.md`;
  - sidecars:
    - `/home/max/site-control-kit/artifacts/telegram_exports/20260424_132543_chat_1002465948544_22_usernames_txt.txt`
    - `/home/max/site-control-kit/artifacts/telegram_exports/20260424_132543_chat_1002465948544_22_usernames_json.json`
  - результат:
    - `unique_members = 22`
    - `usernames = 9`
    - `pre-deep history backfill restored 9 username(s)`
    - `deep processed = 1`
    - `deep filled = 0`
- Практический вывод:
  - known peer вроде `1291639730 -> @Bychkov_AA` больше не становится первым deep-кандидатом;
  - следующий bottleneck уже в скорости helper/discovery для реально неизвестных peer, например live peer `8055002493`, который не отдал username за `90s`.

### Обновление 2026-04-23
- Зафиксировано новое live-state после полного verify на активном bridge-клиенте:
  - run: `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T173223Z/run.json`
  - log: `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T173223Z/export.log`
  - stats: `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T173223Z/export_stats.json`
  - результат:
    - `unique_members = 27`
    - `members_with_username = 10`
    - `safe_count = 10`
    - `deep_attempted_total = 2`
    - `deep_updated_total = 2`
    - `new_usernames = 2`
  - новые numbered batch данные:
    - `/home/max/telegram_contact_batches/chat_-1002465948544/7.txt`
    - `@oleg_klsnkv`
    - `@andreu_bogatchenko`
  - `latest_full.*` и `latest_safe.*` теперь уже promoted именно на этот run, а не на более старый baseline.
- Подтверждён live-поведенчески и scheduler-cap:
  - `TELEGRAM_CHAT_DEEP_STEP_MAX_SEC` не только покрыт тестом, но и реально даёт переход к следующему scroll-step вместо монопольного зависания в первом deep-layer.
- Зафиксирован и закрыт новый downstream дефект:
  - exporter раньше мог принять чисто числовой peer-id за `@username` и протащить это значение в history/safe/batch слой;
  - теперь numeric артефакты вида `@1291639730` фильтруются в exporter, history-loader и `scripts/telegram_contact_batches.py`;
  - текущие active outputs (`latest_full.*`, `latest_safe.*`, `identity_history.json`, numbered batches) очищены от этого ложного класса данных.

### Обновление 2026-04-23
- В chat deep scheduler добавлен cap на runtime одного visible-layer:
  - `scripts/export_telegram_members_non_pii.py` теперь учитывает `TELEGRAM_CHAT_DEEP_STEP_MAX_SEC`;
  - `scripts/telegram_profiles.py` задаёт profile defaults:
    - `fast = 45s`
    - `balanced = 60s`
    - `deep = 90s`
  - это нужно, чтобы первый deep-step не съедал весь runtime run’а и exporter чаще доходил до следующих scroll layers.
- Регрессия закрыта тестом:
  - `tests/test_telegram_export_runtime.py` проверяет, что budget deep-step реально режется по cap.
- Live verification этого scheduler-cap шага теперь уже подтверждена:
  - после восстановления online heartbeat run `20260423T173223Z` реально дошёл до второго scroll-step и сохранил новый best-known snapshot.

### Обновление 2026-04-23
- Ускорен deep helper path в текущем Telegram Web:
  - если первый же `context menu` в шаге показывает, что `Mention` отсутствует (`menu_missing`), exporter больше не тратит оставшийся deep-step на повторные mention-попытки;
  - оставшиеся peer этого же visible-layer сразу переводятся в helper-only path;
  - helper tab теперь может оставаться активной между peer внутри такого шага, без лишнего возврата на base tab после каждого helper-read.
- Новый live fast-run подтвердил измеримый прирост throughput:
  - run: `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T141227Z/run.json`
  - log: `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T141227Z/export.log`
  - stats: `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T141227Z/export_stats.json`
  - за те же `120s` deep-step теперь обработал `4` peer, а не `3`;
  - `deep_attempted_total` вырос `3 -> 4`;
  - `latest_safe.*` после wrapper refresh остаётся на корректном snapshot с `@teimur_92`.

### Обновление 2026-04-23
- Починена promotion policy для `latest_safe.*`:
  - в `scripts/telegram_contact_batches.py` `select_best_snapshot(..., prefer_peer_updates=True)` теперь path-aware и учитывает rename того же `peer_id` как полезный identity update;
  - в `scripts/collect_new_telegram_contacts.sh` safe-path сравнение и выбор best snapshot переведены в `safe`-mode, где peer-rename может перевесить старый, но более жирный baseline.
- Проверка на текущем каталоге `/home/max/telegram_contact_batches/chat_-1002465948544` подтвердила новый выбор:
  - helper теперь выбирает `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T134454Z/snapshot_safe.md` как лучший safe snapshot;
  - `latest_safe.txt` обновлён и теперь содержит `@teimur_92` вместо старого `@abuzayd06`.

### Обновление 2026-04-23
- Починен downstream overwrite свежих live usernames:
  - в `scripts/export_telegram_members_non_pii.py` final sanitize больше не восстанавливает historical username поверх свежего live/helper результата автоматически;
  - historical restore теперь включается только если текущий username реально конфликтует с другим peer/history, а не просто отличается от старого значения;
  - в `scripts/telegram_contact_batches.py` safe/history layer теперь принимает смену username у того же `peer_id` как допустимое обновление, если новый username не принадлежит другому peer.
- Новый live fast-run подтвердил это на том же конфликтном кейсе:
  - run: `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T134454Z/run.json`
  - log: `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T134454Z/export.log`
  - stats: `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T134454Z/export_stats.json`
  - helper снова добыл `@Teimur_92` для peer `555101371`;
  - `snapshot_safe.md` этого run уже содержит `@teimur_92`, а numbered batch `5.txt` тоже содержит `@teimur_92`;
  - `identity_history.json` обновился на `555101371 -> @teimur_92`, а старая запись `@abuzayd06` удалена из `username_to_peer`.
- Остаточный нюанс после этого фикса уже другой:
  - `latest_safe.txt` в chat-dir может остаться старым не из-за safe-conflict, а потому что wrapper выбирает более сильный snapshot по общему числу usernames;
  - в live run `20260423T134454Z` это и произошло: safe snapshot был корректный, но не был promoted в `latest_safe.*`, потому что baseline snapshot содержал `8` usernames против `7`.

### Обновление 2026-04-23
- Добавлен отдельный Firefox dev/debug contour для bridge:
  - `extension/manifest.json` теперь содержит и `background.service_worker`, и `background.scripts` c `preferred_environment`, чтобы один и тот же background path поднимался и в Chromium, и в Firefox;
  - добавлен `browser_specific_settings.gecko.id`, чтобы Firefox-path был стабильнее для dev-run;
  - `extension/background.js` больше не падает на `runtime.onSuspend`, если среда его не предоставляет.
- Добавлены launcher-скрипты:
  - `./start-firefox.sh`
  - `./start-telegram-firefox.sh`
  - `scripts/start_firefox.sh`
- Firefox path использует `web-ext run` и выделенный профиль `~/.site-control-kit/firefox-profile`:
  - это снимает Chrome-specific блокировку на `--load-extension`;
  - но это именно dev/debug path, а не доказательство, что Telegram bottleneck уже снят сам собой.
  - на этой машине обнаружен ещё один конкретный нюанс: системный Firefox установлен как snap wrapper, и `web-ext` не поднимает temporary add-on автоматически из-за refused debugger port; поэтому helper на snap Firefox падает в `about:debugging` manual fallback.
- Заодно подтверждён и следующий настоящий продуктовый дефект уже внутри Telegram pipeline:
  - в live fast-run `20260423T131912Z` helper добыл `@Teimur_92` для peer `555101371`;
  - но финальный safe/full output вернул этому peer старое историческое значение `@abuzayd06`;
  - значит после helper/discovery есть downstream overwrite в history-backfill или sanitize layer.

### Обновление 2026-04-23
- Живой DOM Telegram Web на этой группе уточнён ещё сильнее:
  - старые `.bubbles .bubbles-group-avatar.user-avatar...` селекторы больше не являются основным anchor-path;
  - текущий рабочий peer-anchor это `sender-group-container` + `.Avatar[data-peer-id]` / `.message-title-name-container.interactive`.
- В `scripts/export_telegram_members_non_pii.py` mention/open-dialog path переведён на текущие anchor selectors:
  - это сняло старый слой `mention context menu not opened` для части peer;
  - теперь exporter чаще доходит до меню и уже там понимает, что `Mention` в текущем Telegram UI обычно отсутствует.
- Новый live-факт по текущему Telegram Web:
  - после context-click на sender-name открывается `MessageContextMenu`;
  - его реальные item сейчас такие: `Reply`, `Copy Text`, `Copy Message Link`, `Forward`, `Select`, `Report`;
  - `Mention` в нём нет;
  - значит главный остаточный limit уже не в доставке или selector lookup, а в самом product-path Telegram.
- В exporter добавлен ранний bailout:
  - если открытое menu-text не содержит `Mention`, exporter сразу прыгает в helper fallback и не тратит лишние retry на `click_menu_text`.
- Новый live smoke после этой правки:
  - `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T130122Z/run.json`
  - `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T130122Z/export.log`
  - `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T130122Z/export_stats.json`
  - новый реальный helper-resolve в fast path:
    - `@Teimur_92`
  - safe ceiling пока не вырос выше `9`, но exporter теперь тратит время уже ближе к полезному path.

### Обновление 2026-04-23
- На локальной `main` добит automation-layer для reload/runtime и wrapper-open path:
  - `webcontrol/cli.py` получил рабочий `browser x11-click` через `xwininfo + libX11/libXtst` без зависимости от `wmctrl/xdotool/python-xlib`;
  - `scripts/reload_bridge_extension.sh` теперь реально проходит end-to-end на этой машине;
  - после reload heartbeat снова рекламирует `meta.capabilities.content_commands`, включая `click_menu_text`.
- `scripts/auto_collect_usernames.sh` теперь сначала открывает Telegram через уже подключённый bridge client (`browser new-tab`), и только потом падает в `xdg-open` fallback:
  - это сняло ложный fail-fast после reload, когда клиент жив, но в его tabs пока нет `web.telegram.org`;
  - живой smoke подтвердил, что wrapper сам открыл Telegram tab и дошёл до export без ручного `browser new-tab`.
- Новые live run-артефакты на реальном чате `https://web.telegram.org/a/#-1002465948544`:
  - auto-open smoke:
    - `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T121918Z/run.json`
    - `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T121918Z/export.log`
    - `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T121918Z/export_stats.json`
  - deep run после стабилизации runtime/wrapper:
    - `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T122059Z/run.json`
    - `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T122059Z/export.log`
    - `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T122059Z/export_stats.json`
  - результат deep run:
    - `new_usernames = 4`
    - `members_with_username = 9`
    - `deep_attempted_total = 10`
    - `deep_updated_total = 9`
    - `safe_count = 9`
  - новые archive artifacts:
    - `/home/max/site-control-kit/artifacts/telegram_exports/20260423_162026_chat_1002465948544_6.md`
    - `/home/max/site-control-kit/artifacts/telegram_exports/20260423_162026_chat_1002465948544_6_usernames_txt.txt`
    - `/home/max/site-control-kit/artifacts/telegram_exports/20260423_162026_chat_1002465948544_6_usernames_json.json`
    - `/home/max/site-control-kit/artifacts/telegram_exports/20260423_162710_chat_1002465948544_14.md`
    - `/home/max/site-control-kit/artifacts/telegram_exports/20260423_162710_chat_1002465948544_14_usernames_txt.txt`
    - `/home/max/site-control-kit/artifacts/telegram_exports/20260423_162710_chat_1002465948544_14_usernames_json.json`
- Текущий честный ceiling уже измерен:
  - transport/runtime/wrapper слой работает;
  - главный остаточный bottleneck сместился в Telegram mention-path, где часто встречается `WARN: mention context menu not opened for peer ...`;
  - даже при этом helper fallback и helper-tab path продолжают добывать реальные `@username`, так что deep run больше не бесполезный.

### Обновление 2026-04-23
- Из удалённой ветки `origin/codex/telegram-client-hardening` возвращены missing onboarding/status docs и Telegram batch/profile слой:
  - `docs/agent_handoff_ru/00..10`
  - `docs/PROJECT_WORKFLOW_RU.md`
  - `docs/PROJECT_STATUS_RU.md`
  - `scripts/auto_collect_usernames.sh`
  - `scripts/collect_new_telegram_contacts.sh`
  - `scripts/collect_new_telegram_contacts_chain.sh`
  - `scripts/reload_bridge_extension.sh`
  - `scripts/telegram_contact_batches.py`
  - `scripts/telegram_contact_chain.py`
  - `scripts/telegram_members_export_gui.sh`
  - `scripts/telegram_profiles.py`
- В локальный exporter добавлены совместимые batch-flags:
  - `--identity-history`
  - `--discovery-state`
  - `--stats-output`
- Exporter теперь пишет `export_stats.json`, умеет загружать history/discovery state и backfill-ить известные usernames из `identity_history.json`.
- В `mention`-deep path добавлен delivery-aware bailout:
  - exporter больше не застревает в тупике `mention-only`;
  - если `Mention` не открылся или menu-path не сработал, `mention`-режим сразу падает в helper-tab fallback;
  - живой run подтвердил реальные helper-resolve:
    - `@Bychkov_AA`
    - `@abuzayd06`
    - `@GadkiyGri`
- В extension/runtime слое возвращены capability-метаданные heartbeat и DOM-команда `click_menu_text`:
  - `extension/background.js` снова публикует `meta.capabilities`;
  - `extension/content.js` снова умеет `click_menu_text` и лучше ищет menu-item.
- В хабе снят новый perf bottleneck:
  - `register_client()` больше не пишет `state.json` на каждый heartbeat, если изменился только `last_seen`;
  - `pop_next_command()` больше не пишет `state.json` при пустой очереди;
  - `snapshot()` больше не пишет `state.json`, если статусы не изменились;
  - после рестарта хаба прямой `curl /api/clients` снова отвечает быстро, и wrapper перестал ложно падать на “telegram bridge client not detected”.
- Живой batch-run после этих фиксов впервые снова прошёл end-to-end на локальной main-ветке:
  - `run.json`: `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T115545Z/run.json`
  - `export.log`: `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T115545Z/export.log`
  - `export_stats.json`: `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T115545Z/export_stats.json`
  - результат:
    - `new_usernames = 3`
    - `unique_members = 6`
    - `deep_attempted_total = 4`
    - `deep_updated_total = 3`
    - `safe_count = 3`
  - batch artifacts:
    - `/home/max/telegram_contact_batches/chat_-1002465948544/1.txt`
    - `/home/max/telegram_contact_batches/chat_-1002465948544/latest_full.txt`
    - `/home/max/telegram_contact_batches/chat_-1002465948544/latest_safe.txt`
  - archive artifacts:
    - `/home/max/site-control-kit/artifacts/telegram_exports/20260423_155811_chat_1002465948544_6.md`
    - `/home/max/site-control-kit/artifacts/telegram_exports/20260423_155811_chat_1002465948544_6_usernames_txt.txt`
    - `/home/max/site-control-kit/artifacts/telegram_exports/20260423_155811_chat_1002465948544_6_usernames_json.json`

### Базовый browser-control kit
- Хаб `webcontrol` работает как единый источник правды по клиентам, очередям и результатам.
- CLI и browser wrappers уже подходят для живого локального управления браузером.
- Расширение исполняет tab-level и DOM-level команды.
- Собран отдельный agent-handoff пакет на 11 markdown-файлов для нового агента и нового чата.

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
- Chain-runner теперь умеет не ждать обычный интервал после run, который завершился сильным `deep-yield`: если exporter сам остановился на продуктивном deep-шаге, следующая короткая попытка стартует сразу.
- Chain-runner получил профили `fast`, `balanced`, `deep`: они задают дефолтный интервал и набор env-настроек для collect-script, при этом ручные env всё ещё имеют приоритет.
- Профили вынесены в общий helper `scripts/telegram_profiles.py`, поэтому те же режимы теперь доступны и для shell/GUI-скриптов, а не только внутри chain-runner.
- Исправлен forced-tab regression в `auto_collect_usernames.sh`: теперь `CHAT_TAB_ID` без явного `CHAT_CLIENT_ID` корректно резолвится обратно в пару `client_id/tab_id`, а не ломает таргетинг.

### Диагностика прогонов
- Каждый run сохраняет `run.json`, `export.log`, `snapshot.md/txt`, `snapshot_safe.md/txt`.
- Есть `export_stats.json` с телеметрией экспортёра.
- `run.json` дублирует ключевые метрики: `unique_members`, `members_with_username`, `deep_updated_total`, `history_backfilled_total`, `output_usernames_cleared_total`, `chat_scroll_steps_done`, `chat_jump_scrolls_done`, `chat_deep_priority_rounds`, `chat_deep_yield_stop`.
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
- `mention`-режим больше не тупиковый: если `Mention` у конкретного peer не дал `@username`, deep-chat делает лёгкий URL fallback для этого же peer и не сжигает шаг целиком впустую.
- `mention`-deep теперь может брать несколько peer за один scroll-step, если оставшегося runtime достаточно.
- Если текущий visible-layer уже даёт хорошие `@username`, deep может сделать дополнительный батч на этом же слое до scroll.
- Если Telegram два раза подряд отвечает `No visible menu item found by text`, deep раньше прекращает бесполезные повторные попытки и быстрее уходит в fallback.
- Возврат в group dialog после URL/mention fallback теперь проверяется явно: один сложный peer больше не должен ломать весь остаток deep-шага.
- `discovery_state.json` теперь хранит `deep_peer_history`: repeated failure peer автоматически опускаются ниже в порядке deep-target selection, а свежие кандидаты идут раньше.
- repeated failure peer теперь получают ещё и мягкий cooldown: если в текущем visible-layer есть альтернативы, deep сначала тратит батч на них, а не на заведомо тяжёлый peer.
- Если текущий deep-step уже дал сильный результат и до конца runtime осталось мало, exporter может закончить run раньше и не тратить хвост времени на малополезный discovery.

### Диагностика stale extension runtime
- В heartbeat `meta` добавлены `capabilities` по background/content-командам.
- CLI теперь умеет помечать browser tab-level ошибки вида `Unsupported command type in content script ...` как вероятный stale runtime и подсказывает reload в `chrome://extensions`.
- Telegram-экспортёр теперь делает preflight по `meta.capabilities` выбранного клиента:
  - если runtime не рекламирует `click_menu_text`, mention-deep не тратит попытки на неподдерживаемую DOM-команду;
  - экспортёр явно предупреждает, что будет использован legacy text-click fallback до reload unpacked extension.
- CLI получил отдельное действие `browser x11-click`:
  - можно кликать по системным страницам и окнам без content script через относительные координаты окна;
  - это стало базой для best-effort helper `scripts/reload_bridge_extension.sh`.
- CLI получил и `browser x11-keys`:
  - можно отправлять `Tab`, `Return`, модификаторы и другие X11 key sequences прямо в окно Chrome;
  - helper теперь может работать не только мышью, но и клавиатурой на system-page уровне.
- В `options.html` и `popup.html` добавлен self-reload trigger:
  - `chrome-extension://<id>/options.html?action=reload-self`
  - `chrome-extension://<id>/popup.html?action=reload-self`
  - при открытии такой страницы расширение вызывает `chrome.runtime.reload()` само.

## Проверено
- Текущий локальный unit-набор зелёный: `91/91`.
- `python3 -m py_compile webcontrol/cli.py` -> OK.
- `bash -n scripts/auto_collect_usernames.sh` -> OK.
- Живой reload helper подтверждён на локальной `main`:
  - `bash scripts/reload_bridge_extension.sh`
  - heartbeat после reload содержит `content_commands`, включая `click_menu_text`.
- Живой auto-open smoke подтверждён:
  - wrapper сам напечатал `INFO: opened Telegram tab via bridge client ...`
  - run завершился успешно без ручного `browser new-tab`.
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
- Живое сравнение профилей на одной и той же базе (`identity_history.json + discovery_state.json`) показало:
  - `fast`:
    - `/tmp/tg_chain_profile_fast/chat_-2465948544/runs/20260420T114702Z/run.json`
    - `unique_members = 11`
    - `deep_updated_total = 1`
    - `history_backfilled_total = 8`
    - `chat_scroll_steps_done = 0`
  - `deep`:
    - `/tmp/tg_chain_profile_deep/chat_-2465948544/runs/20260420T115310Z/run.json`
    - `unique_members = 13`
    - `deep_updated_total = 3`
    - `history_backfilled_total = 5`
    - `chat_scroll_steps_done = 3`
  - практический вывод:
    - `deep` лучше добывает новые реальные `@username`;
    - `fast` полезен как быстрый повторный проход по уже накопленной истории.
- Тот же live smoke отдельно подтвердил, что `expired no delivery` внутри `click_menu_text` теперь повторяется как устойчивый pattern, а не единичный фейл: следующий оптимизационный шаг должен быть delivery-aware bailout и более ранний URL fallback.
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
- В живом X11-контуре подтверждено:
  - helper может открыть отдельную quiet-tab на `chrome://extensions/?id=...` через browser wrapper;
  - для дальнейшего reload не нужен content script, потому что появился `browser x11-click`.
- Живой smoke нового CLI-действия подтверждён:
  - `browser x11-click` успешно отработал на системной quiet-tab `chrome://newtab/`;
  - результат вернул X11-координаты и window id:
    - `tabId = 614278005`
    - `windowId = 0x03400020`
    - `via = x11_click`
- После фикса `_x11_send_keys` живой browser bridge реально вернулся к полной работе:
  - `browser activate --tab-id 614278010` успешно сработал через `x11_fallback`;
  - `browser x11-click` теперь умеет поднимать неактивную вкладку в многотабовом окне;
  - `browser x11-keys` тоже проходит по той же цепочке.
- Self-reload расширения подтверждён живьём:
  - `./scripts/reload_bridge_extension.sh` на вкладке `614278010` успешно довёл runtime до нового состояния;
  - после этого в heartbeat появились `meta.capabilities.background_commands` и `meta.capabilities.content_commands`;
  - это сняло stale-runtime как инфраструктурный блокер.
- Post-reload smoke подтверждён:
  - `browser new-tab 'https://web.telegram.org/k/#-2465948544'` снова завершился `completed`, без старой content-script misroute ошибки;
  - новый tab: `614278035`
  - URL: `https://web.telegram.org/k/#-2465948544`
- Новый live smoke на Telegram после reload подтвердил:
  - stale-runtime блок больше не мешает mention-пути;
  - в логе уже есть:
    - `INFO: mention context for peer 530627292 opened via anchor avatar`
  - это сужает текущий bottleneck уже до клика по menu item / чтения composer, а не до загрузки старого runtime.
- Новый прямой live probe после reload подтвердил end-to-end mention-path без history backfill:
  - для `peer 530627292` основной экспортёр на живом runtime собрал `@Tier555`;
  - артефакты:
    - `/tmp/tg_live_nohistory_verify.ZW8Ucj/snapshot.md`
    - `/tmp/tg_live_nohistory_verify.ZW8Ucj/export_stats.json`
  - факты:
    - `history_backfilled_total = 0`
    - `deep_attempted_total = 1`
    - `deep_updated_total = 1`
- Новый общий live smoke без history backfill подтвердил, что mention/deep уже работает серийно, а не только на одном точечном peer:
  - артефакты:
    - `/tmp/tg_live_general_nohistory2.IYo4yH/snapshot.md`
    - `/tmp/tg_live_general_nohistory2.IYo4yH/export_stats.json`
  - факты:
    - `members_total = 7`
    - `members_with_username = 3`
    - `history_backfilled_total = 0`
    - `deep_attempted_total = 3`
    - `deep_updated_total = 3`
  - живые username, подтверждённые этим run:
    - `@oleg_klsnkv`
    - `@Heavy_seas`
    - `@olegoleg48`
- Новый live run после увеличения deep-batch подтвердил, что один шаг теперь реально обрабатывает несколько peer подряд:
  - артефакты:
    - `/tmp/tg_live_batch_boost.h1cwzl/snapshot.md`
    - `/tmp/tg_live_batch_boost.h1cwzl/export_stats.json`
  - факты:
    - `chat deep step 0: processed 3`
    - `deep_attempted_total = 3`
    - `deep_updated_total = 3`
    - там же подтвердился URL fallback для `@xpenguinfromhell`
- Новый live run после фикса возврата в group dialog подтвердил, что multi-peer deep больше не сыпется после тяжёлого URL/mention случая:
  - артефакты:
    - `/tmp/tg_live_batch_boost3.7ErTfD/snapshot.md`
    - `/tmp/tg_live_batch_boost3.7ErTfD/export_stats.json`
  - факты:
    - `chat deep step 0: processed 3, filled 3`
    - `history_backfilled_total = 0`
    - подтверждённые username:
      - `@oleg_klsnkv`
      - `@xpenguinfromhell`
      - `@olegoleg48`
- Новый seeded-history smoke подтвердил, что deep ranking реально учитывает прошлые неудачи:
  - артефакт:
    - `/tmp/tg_ranked_history_smoke.a5rnGA/export.log`
  - факт:
    - peer `530627292` был заранее помечен как repeated failure в `discovery_state.json`
    - deep первым взял других visible peer (`547163094`, затем `858739581`), а не проблемный peer из seeded history
- Новый live smoke после усиления group-dialog readiness подтвердил, что warning `deep chat not in target group dialog` больше не вылез в успешном mention-run:
  - артефакты:
    - `/tmp/tg_same_view_priority_fix.AVw7fW/export.log`
    - `/tmp/tg_same_view_priority_fix.AVw7fW/export_stats.json`
  - факты:
    - `deep_attempted_total = 3`
    - `deep_updated_total = 3`
    - подтверждены:
      - `@Tier555`
      - `@oleg_klsnkv`
      - `@fuckeeva`

## Текущие Проблемы

### 1. Deep mention уже рабочий, но остаётся неоднородным
Есть подтверждённые live-run, где mention/deep без history backfill реально собрал новые `@username`.
Но есть и peer, для которых `Mention` в конкретном DOM-срезе не появляется или даёт miss.

То есть deep-path больше не сломан инфраструктурно: stale runtime снят, `click_menu_text` живой, composer-read рабочий. Текущий узкий момент уже прикладной: неодинаковая доступность `Mention` и разный throughput по разным peer/слоям чата.

### 2. Throughput deep-path уже вырос, но всё ещё ниже желаемого на длинных run
Сейчас основной рост по новым `@username` уже пошёл:
- на коротких run deep умеет делать `processed 3 / filled 3` прямо в одном scroll-step;
- один неудачный peer больше не ломает весь batch-step.

Следующий резерв уже не в починке path, а в общем балансе runtime между discovery и deep на длинных прогонах.

### 3. Reload helper стал рабочим, но fallback-кнопка ещё зависит от геометрии
Основной stale-runtime блок снят через self-reload страницы расширения.
Что уже точно работает:
- self-reload через `chrome-extension://.../options.html?action=reload-self`;
- проверка появления `content_commands` после reload;
- post-reload browser commands (`new-tab`, `activate`, `x11-click`, `x11-keys`).

Что ещё остаётся best-effort:
- fallback-клик по кнопке Reload на `chrome://extensions`;
- его точные координаты всё ещё зависят от сборки Chrome/масштаба окна.

### 4. Exporter всё ещё тратит слишком много runtime на discovery до deep
После последних фиксов короткие no-history run уже дают `3/3` успешных deep-update на видимом слое.
Но на длинных прогонах runtime всё ещё может упираться в общий бюджет раньше, чем deep пройдёт следующий слой visible peer.

### 5. X11 fallback для browser tab actions в этой среде ненадёжен
Проверка `_x11_send_keys` на реальном Chrome window вернула `True`, но фактический `Ctrl+T` не создал новую вкладку.
Это отдельный инфраструктурный долг browser CLI.

### 6. Best-known latest может быть исторически сильным, но не самым свежим по времени
Сейчас это осознанное поведение: `latest_*` в chat-dir означает лучший известный snapshot, а не обязательно самый свежий run.
Если пользователю нужен именно последний run как основной артефакт, это потребуется оформить отдельно.

### 7. Экспортёр остаётся монолитным
`export_telegram_members_non_pii.py` всё ещё перегружен ответственностями и требует модульного разделения.

## Последний Подтверждённый Полезный Результат
- Живой no-history run на новом runtime подтвердил, что основной export path уже собирает новые `@username` без помощи `identity_history.json` и обрабатывает несколько peer в одном deep-step.
- Артефакты проверки:
  - `/tmp/tg_live_batch_boost3.7ErTfD/snapshot.md`
  - `/tmp/tg_live_batch_boost3.7ErTfD/export_stats.json`
- Ключевой факт:
  - `deep_updated_total = 3`
  - `history_backfilled_total = 0`
  - `chat deep step 0: processed 3, filled 3`
  - это значит, что mention/deep снова приносит новые реальные username, а не только восстанавливает старые знания из истории, и делает это батчем, а не по одному peer.

## Следующий Приоритет
1. Снизить runtime-затраты discovery относительно deep, чтобы multi-peer deep чаще успевал проходить следующий слой visible peer.
2. Поднять приоритеты deep-target'ов: раньше брать тех peer, у кого вероятность успешного `Mention` выше.
3. Разделить browser capability/runtime compatibility и Telegram export concerns в отдельные модули/слои.
4. Отделить понятие `best-known latest` от `most-recent run` в UI и документации, если пользователю важно видеть именно последний прогон как основной артефакт.
5. Декомпозировать `export_telegram_members_non_pii.py` на модули.

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
