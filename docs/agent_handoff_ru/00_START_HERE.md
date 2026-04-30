# Agent Handoff RU: Start Here

Этот пакет нужен для любого нового агента, нового чата и нового этапа работы по `site-control-kit`.
Цель пакета: дать агенту один понятный вход, чтобы он мог быстро понять проект, текущее состояние и безопасно продолжить работу без повторного исследования с нуля.

Сначала всегда читать repo-root файл `AGENT_START_HERE.md`, и только потом этот handoff-пакет.
После завершения любой задачи агент обязан обновить repo-root handoff и зафиксировать, что сделано и что нужно делать дальше.

## Для Кого Этот Пакет
- для ИИ-агентов, которые впервые заходят в репозиторий;
- для нового чата, где нет контекста прошлой работы;
- для handoff после большой серии Telegram/browser-изменений.

## Что Уже Есть В Репозитории
В проекте уже есть базовая документация:
- `AGENTS.md`
- `docs/PROJECT_WORKFLOW_RU.md`
- `docs/PROJECT_STATUS_RU.md`
- `docs/ARCHITECTURE.md`
- `docs/API.md`
- `docs/EXTENSION.md`
- `docs/AI_MAINTAINER_GUIDE.md`

Этот пакет не заменяет их полностью. Он собирает рабочую картину в одном месте, в правильном порядке чтения, и объясняет, как именно продолжать работу с текущего состояния.

## Обязательный Порядок Чтения
Читать в таком порядке:
1. `docs/agent_handoff_ru/00_START_HERE.md`
2. `docs/agent_handoff_ru/01_PROJECT_SCOPE_AND_GOALS.md`
3. `docs/agent_handoff_ru/02_ARCHITECTURE_MAP.md`
4. `docs/agent_handoff_ru/03_COMPONENTS_AND_ENTRYPOINTS.md`
5. `docs/agent_handoff_ru/04_TELEGRAM_EXPORT_PIPELINE.md`
6. `docs/agent_handoff_ru/05_STATE_AND_ARTIFACTS.md`
7. `docs/agent_handoff_ru/06_AGENT_WORKFLOW_AND_OPERATIONS.md`
8. `docs/agent_handoff_ru/07_TESTING_AND_ACCEPTANCE.md`
9. `docs/agent_handoff_ru/08_KNOWN_ISSUES_AND_LIVE_FINDINGS.md`
10. `docs/agent_handoff_ru/09_CURRENT_BACKLOG_AND_NEXT_STEPS.md`
11. `docs/agent_handoff_ru/10_HANDOFF_TEMPLATE_AND_COMMIT_POLICY.md`

После этого уже читать:
- `AGENT_START_HERE.md`
- `AGENTS.md`
- `docs/PROJECT_WORKFLOW_RU.md`
- `docs/PROJECT_STATUS_RU.md`
- при необходимости `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/EXTENSION.md`

## Быстрый Старт Для Нового Агента
Перед любыми правками выполнить:

```bash
cd /home/max/site-control-kit
git status --short --branch
git log --oneline -n 15
PYTHONPATH="$PWD" python3 -m webcontrol clients
```

Если задача связана с Telegram, дальше посмотреть:

```bash
ls -la /home/max/telegram_contact_batches/chat_-1002465948544
find /home/max/telegram_contact_batches/chat_-1002465948544/runs -maxdepth 2 -name run.json | sort | tail
find /home/max/telegram_contact_batches/chat_-1002465948544/chains -maxdepth 2 -name chain.json | sort | tail
```

Текущий живой Telegram-чат: `https://web.telegram.org/a/#-1002465948544`.

## Что Агент Должен Понять После Чтения Пакета
- какую задачу реально решает проект;
- как устроен browser bridge;
- как именно работает Telegram pipeline;
- где лежат state files и run-артефакты;
- какие live-результаты уже подтверждены;
- какие проблемы ещё не закрыты;
- какой следующий технический приоритет уже очевиден.

## Что Сейчас Самое Важное
На текущем этапе проект уже не находится в состоянии "сырой прототип".
Основной рабочий контур живой:
- hub работает;
- extension работает;
- CLI работает;
- Telegram export работает;
- batch/safe/quarantine слои работают.

Главный текущий технический долг уже сместился в performance и resilience deep-path, а не в базовую функциональность.
При этом новый реальный путь к `100 @username` теперь идёт через discovery-aware chain runs, а не через единичные ручные smoke-проходы.
Новый свежий live-факт: control-plane timeout в hub уже тоже снят, и текущий limit теперь сидит внутри helper-heavy `chat collect`, а не в `force-navigate`.
Новый операционный факт на 2026-04-29: GUI-слой теперь поддерживает multi-account запуск Telegram-сбора (`scripts/telegram_members_export_gui.sh` + `scripts/telegram_api_accounts.py`), включая ручной/авто выбор `client_id` и добавление новых API-аккаунтов без ручного редактирования env.
Новый quality-факт на 2026-04-29: итоговые username-sidecar теперь по умолчанию исключают bot-аккаунты, deep-path не тратит runtime на bot-target, а для диагностики доступен override `--include-bots`.
Новый UX-факт на 2026-04-29: GUI запускается в операторском порядке `пользователь (default/portable dir/portable zip) -> чат/группа -> папка и basename сохранения`, а `scripts/telegram_members_export_app.sh` теперь просто проксирует в этот же GUI-поток.
Новый UX-факт v2 на 2026-04-29: GUI теперь single-window (одна форма) и умеет искать чат по названию, если URL недоступен у выбранного пользователя.
Новый UX-факт v3 на 2026-04-29: добавлен явный user-registry (`~/.site-control-kit/telegram_users/registry.json`) и dropdown-выборы пользователей/чатов в GUI.
Новый operator baseline на 2026-04-29: для portable/logged-in Telegram Desktop основной path теперь `GTK GUI -> tdata-history-authors`, где chat-list и export читаются из живой `tdata`-сессии, а не обязательно из Telegram Web.
Новый live-факт v4 на 2026-04-29: history-only `tdata` path уже подтверждён на `BigpharmaMarket` (`34` уникальных `@username` при `5000` сообщениях) и на `-1001753733827` (`135` safe usernames при `5000` сообщениях с progress в GUI).
Новый UX/live-факт на 2026-04-30: этот же GUI path теперь показывает отдельный progress panel и умеет штатно останавливать scan с partial result, поэтому длинный history-run больше не должен выглядеть как немой freeze.
Новый live-факт v5 на 2026-04-30: X11 launcher уже отдаёт окну свободный min-size `46x46`, а реальный GTK smoke на `-1001753733827` прошёл по цепочке `connect -> 8 chats -> export -> stop -> partial save`; по пути найден и сразу закрыт runtime traceback `AttributeError ... _is_tdata_target`.
Новый UX/live-факт v6 на 2026-04-30: full history-run теперь по умолчанию без export-timeout (`TELEGRAM_TDATA_EXPORT_TIMEOUT_SEC=0`), save-dialog открывается как отдельное окно `Куда сохранить Telegram export`, а error-path больше не маскируется под "завершено".
Новый repo-rule на 2026-04-30: для этого проекта нельзя считать задачу закрытой без полного живого прохода user-facing сценария; если по пути находятся баги, неправильные шаги или UX-тупики, агент обязан дожать их в том же цикле.

## Текущий Telegram Sticky-Fact
Для текущего пользовательского GUI-кейса это уже не первый path.
Сначала следующий агент обязан проверить, можно ли продолжать через `tdata-history-authors`.
Только если пользователь возвращается именно к web/bridge сбору или `tdata` недоступна, имеет смысл снова уходить в sticky/helper расследование ниже.

Для Telegram username export следующий агент не должен снова искать координаты с нуля:
- текущий рабочий path: `telegram_sticky_author` с `context_click=true`;
- клик должен быть правой кнопкой по нижней прилипшей 34px иконке автора;
- не кликать по тексту сообщения, reply-avatar и не открывать профиль левой кнопкой;
- live probe на extension `0.1.5` подтвердил `source=point`, `point={x:512,y:539}`, `rect=506,535,540,569`, `context_clicked=true` для `peer_id=8055002493`;
- если после этого нет username, текущая причина обычно `menu_missing`: Telegram Web не показывает `Mention` в этом меню;
- после `menu_missing` exporter должен запускать sticky helper fallback для того же `peer_id`; live это уже дало `@alxkat` и `@Mitiacaramba`;
- `discovery_state.json` теперь `version=2` и хранит cooldown по blank peer; если sticky peer уже в cooldown, exporter обязан переключаться на других visible peer, а не жечь шаг повторно;
- `scripts/telegram_contact_chain.py` теперь считает productive-run по discovery/coverage тоже, поэтому новый рабочий handoff-артефакт это не только `runs/*/run.json`, но и `chains/*/chain.json`;
- актуальный live chain baseline:
  - `/home/max/telegram_contact_batches/chat_-1002465948544/chains/20260425T052627Z/chain.json`
  - `discovery_progress_runs=2`
  - `discovery_new_visible_total=27`
  - `best_unique_members=23`
- новый hot-fact после baseline:
  - repeated identical discovery view теперь имеет ранний stop-path;
  - live chain `/home/max/telegram_contact_batches/chat_-1002465948544/chains/20260425T063414Z/chain.json` подтвердил `chat_scroll_steps_done=3`, `chat_revisited_view_steps=3`, `chat_runtime_limited=0`;
  - bottleneck сместился дальше, в `mention deep` без yield (`deep_attempted_total=2`, `deep_updated_total=0`).
- самый свежий hot-fact после этого:
  - `_normalize_username_from_mention_input()` теперь принимает raw `username` без `@`, который реально возвращает extractor chat mentions;
  - `discovery_state.json` уже хранит `mention_candidate_states`, а не только `peer_states`;
  - live chain `/home/max/telegram_contact_batches/chat_-1002465948544/chains/20260425T070126Z/chain.json` показал:
    - run1 `20260425T070126Z` -> `deep_attempted_total=2`, `deep_updated_total=0`
    - run2 `20260425T070502Z` -> `deep_attempted_total=0`, `deep_updated_total=0`
  - это значит: same zero-yield mention-кандидаты уже охлаждаются между run;
  - новый текущий limit уже точнее: mention-кандидаты вроде `@plaguezonebot` и `@oleghellmode`, которые не дают целевой `peer_id` и остаются `mention_peer_unknown`.
- самый свежий code-level fact после этого:
  - mention URL-pass теперь использует waited opened identity fallback и safe exact title-match fallback;
  - extra mention-pass теперь best-effort и ограничен по candidate count/runtime, а не бесконечный best-effort хвост.
- самый свежий live fact после этого:
  - forced `tab_id=997919930` уже stale и не должен считаться опорной точкой; после relaunch живой tab стал `997920139`;
  - temp probe `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T055744Z/run.json` показал, что новый blocker был не в Telegram DOM, а в hub timeout на `POST /api/commands`;
  - `webcontrol/store.py` уже починен bounded pruning terminal command history, поэтому `/home/max/.site-control-kit/state.json` ужался с `88995936` до `1030707` байт;
  - новый успешный forced live run:
    - `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T060315Z/run.json`
    - `unique_members=41`
    - `members_with_username=14`
    - `history_backfilled_total=14`
    - `chat_runtime_limited=1`
  - staging-факт теперь уже такой:
    - exporter проходит `force-navigate:done`;
    - exporter проходит `chat-collect:done`;
    - отдельный auxiliary mention-pass не становится первым blocker, потому что run завершает helper-heavy `chat collect` с `skip mention deep because chat runtime limit was reached`.
  - значит следующий агент должен смотреть уже не hub timeout и не старый `997919930`, а per-peer helper runtime внутри `chat collect`.
  - следующий свежий факт после этого:
    - `_wait_for_helper_target_identity()` уже умеет fast-accept по stable helper-route;
    - `_poll_username_from_page_location()` уже не держит жёсткий `2s` timeout;
    - helper session в chat-deep живёт через весь `chat collect`, поэтому live trace показывает reuse через `helper-navigate`.
  - новый live run:
    - `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T063418Z/run.json`
    - `unique_members=42`
    - `members_with_username=12`
    - `deep_attempted_total=7`
    - `chat_scroll_steps_done=10`
    - `chat_runtime_limited=1`
  - это значит:
    - helper throughput уже вырос;
    - текущий limit всё ещё в `chat collect`, но уже после снятия лишнего open-tab/page-url waste.
  - самый свежий факт после следующего throughput-шага:
    - helper tab теперь открывается в фоне и reuse path больше не делает лишний `activate_tab`;
    - `helper-wait-body` убран;
    - sticky helper fallback тоже переведён на общий `chat_helper_session`.
  - промежуточный run `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T064323Z/run.json` вскрыл остаточный sticky leak:
    - обычный helper reuse уже работал;
    - но sticky helper ещё открывал новые tabs и обходил общий session.
  - новый актуальный live run:
    - `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T064626Z/run.json`
    - trace: один `helper-open-tab`, дальше только `helper-navigate` в тот же `tab_id=997920238`
    - `helper-wait-body` в trace отсутствует
    - `chat_scroll_steps_done=11`
    - `deep_attempted_total=7`
    - `members_with_username=9`
  - значит самый свежий остаточный limit теперь уже такой:
    - не repeated open-tab;
    - не sticky helper session leak;
    - а `helper-wait-identity` примерно `2.0..2.5s` на zero-yield peer внутри `chat collect`.
  - ещё один свежий факт после этого:
    - `_wait_for_helper_target_identity()` больше не зависит только от stale hub `tab_url`: он читает route через `get_page_url` и умеет early reject по stable non-target route;
    - промежуточный run `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T070235Z/run.json` временно ухудшил latency и тем самым вскрыл скрытый bug: `_get_page_url_best_effort()` всё ещё держал floor `1s`;
    - после фикса short budget новый run `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T070607Z/run.json` вернул `helper-wait-identity` почти к baseline (`avg 2.243s`);
    - но ceiling по username не вырос: best live result всё ещё у `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T060315Z/run.json` с `14` username.
  - самый свежий факт после этого:
    - `_open_current_chat_user_info_and_read_username()` уже починен против пустого `RightColumn` shell и теперь приоритетно кликает по `.MiddleHeader .ChatInfo(.fullName)`;
    - manual helper verify на known-good peer `306536305` подтвердил, что direct helper page действительно может раскрыть populated `User Info` с `@alxkat`;
    - но full live run `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T075023Z/run.json` всё ещё не дошёл до новых helper usernames, потому что helper peer снова завершились на `helper-wait-identity matched=0`;
    - значит текущий blocker уже уже не в пустом profile shell, а в identity gate перед ним.
  - самый свежий hot-fact после этого:
    - добавлен `_soft_confirm_helper_target_route()` с защитой от conflicting header/title;
    - isolated run `/tmp/tg_mention_probe_live_softroute/chat_-1002465948544/runs/20260426T081833Z/run.json` впервые показал `helper-soft-route matched=1` и проход дальше identity gate;
    - но fresh runs `/tmp/tg_mention_probe_live_softroute2/chat_-1002465948544/runs/20260426T082107Z/run.json` и `/tmp/tg_mention_probe_live_softroute3/chat_-1002465948544/runs/20260426T082310Z/run.json` уже снова дали `helper-soft-route matched=0`;
    - значит текущий live blocker уже ещё уже: не пустой `RightColumn`, не helper session reuse, а нестабильная materialization helper-route target на live Telegram DOM;
    - лучший live ceiling по username всё ещё у `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T060315Z/run.json` с `14` username.
  - новый code-level fact на 2026-04-27:
    - для следующего узкого шага добавлен route source-of-truth probe прямо в helper-path:
    - `helper-route-probe-prewait`, `helper-route-probe-soft`, `helper-route-probe-miss`;
    - каждый probe пишет `page fragment`, `stale tab fragment/title`, `helper header peer/title`, `route_match/header_match`;
    - код: `_get_tab_meta_best_effort()`, `_trace_helper_route_probe()`.
  - новый live-факт на 2026-04-27:
    - run `/tmp/tg_route_probe_live/chat_-1002465948544/runs/20260427T063636Z/run.json` упал до helper-stage с `get_html ... expired`;
    - в `/api/clients` оба Telegram clients (`client-601f...`, `client-83e1...`) были `online=false`;
    - значит новый probe уже подтверждён тестами, но полноценная live-валидация этого probe требует активного online bridge client/tab.
- explicit chat-dir `identity_history.json` больше не должен считаться источником истины, если archive state свежее: loader теперь предпочитает newer `updated_at` и только добирает missing non-conflicting записи;
- chat parser больше не имеет права брать `@username` из текста сообщения, только из author/header block;
- helper-tab теперь обязан подтвердить ожидаемый `peer_id` или имя перед чтением username, иначе возвращает `—`;
- свежий live verify с явным stale history path сохранил корректный `@super_pavlik -> 1621138520` и не воспроизвёл старый ложный helper-case `6964266260 -> @Tri87true`;
- combined output на 54 username уже лежит в `/tmp/telegram_combined_54_usernames.txt`, но это смешанный источник, не полностью peer-bound список.
