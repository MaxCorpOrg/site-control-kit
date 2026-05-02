# Project Status RU

Последнее обновление: 2026-05-02

Этот файл нужен как точка входа для любого нового чата и любого нового агента.
Перед новой задачей его нужно прочитать целиком.

Актуальный onboarding-пакет для нового агента теперь лежит в `docs/agent_handoff_ru/`.
Читать его нужно по номерам файлов, начиная с `00_START_HERE.md`.

## Сделано

### Базовый browser-control kit
- Хаб `webcontrol` работает как единый источник правды по клиентам, очередям и результатам.
- CLI и browser wrappers уже подходят для живого локального управления браузером.
- Расширение исполняет tab-level и DOM-level команды.
- Собран отдельный agent-handoff пакет на 11 markdown-файлов для нового агента и нового чата.
- Добавлена короткая root-entry точка `START_HERE_AGENT_RU.md`, чтобы новый агент сначала определял последнюю завершённую точку проекта, текущий риск и следующий приоритет, а не начинал работу с нуля.
- `AGENTS.md` расширен до capability-map всего проекта: теперь новый агент видит не только правила, но и полную карту подсистем, текущих возможностей, операторских артефактов, документационных контуров и правильных файлов для каждого класса задач.

### Telegram batch-flow
- Есть рабочий сценарий пакетного сохранения новых контактов в `~/telegram_contact_batches/chat_<id>/1.txt`, `2.txt`, `3.txt` и далее.
- Есть `latest_full.md/txt` и `latest_safe.md/txt`.
- Есть numbered batch files и safe snapshots.

### Telegram Invite Manager
- Добавлена видимая папка инструмента:
  - `tools/telegram_invite_manager/`
  - `tools/telegram_invite_manager/AGENT_GUIDE_RU.md`
  - `tools/telegram_invite_manager/ONE_USER_FLOW_RU.md`
  - `tools/telegram_invite_manager/NEXT_CHAT_AGENT_PROMPT_RU.md`
  - `tools/telegram_invite_manager/bin/*`
- Добавлен новый безопасный инструмент `scripts/telegram_invite_manager.py`.
- Он не делает массовый инвайт и не обходит лимиты Telegram.
- На текущем этапе это stateful manager для consent-based invite workflow:
  - импорт CSV/JSON;
  - добавление одного пользователя через `add-user`;
  - `invite_state.json`;
  - `next/run/mark/report`;
  - `dry-run`;
  - `runs/<timestamp>/invite_run.json` и `invite.log`.
- Добавлен базовый GUI wrapper: `scripts/telegram_invite_manager_gui.sh`.
- Добавлена отдельная документация: `docs/TELEGRAM_INVITE_MANAGER_RU.md`.
- Поверх manager-слоя добавлен execution-слой:
  - `scripts/telegram_invite_executor.py`
  - `scripts/telegram_invite_executor_gui.sh`
  - `docs/TELEGRAM_INVITE_EXECUTOR_RU.md`
- Новый execution-слой умеет:
  - хранить invite-link и browser-target в `invite_state.json`;
  - строить `execution_plan.json`;
  - снимать видимый `member_count` через `inspect-chat`;
  - читать видимый список участников через `visible_member_count` и `visible_member_peers`;
  - открывать/активировать Telegram chat через `site-control`;
  - нормализовать публичный `https://t.me/<handle>` в `https://web.telegram.org/k/#@<handle>`, если browser-target не задан явно;
  - выполнять осторожный `add-contact` для одного consented пользователя через Telegram Web `Add Members`;
  - автоматически привязывать before/after `inspect-chat` к live `add-contact`;
  - писать `joined` только при подтверждённом появлении выбранного `peer_id` в видимом member list или росте `member_count`, иначе оставлять `requested`;
  - писать `execution_record.json` после ручных действий оператора.
- GUI-обёртки invite-слоя выровнены с CLI:
  - добавлен общий GUI helper;
  - ошибки Python-команд теперь показываются через `zenity`, а не роняют wrapper молча;
  - executor GUI теперь покрывает `inspect-chat`, `open-chat`, `add-contact dry/prepare/live`;
  - live-режим GUI умеет спросить auto-verification before/after и delay перед повторной after-проверкой.
- Invite Executor теперь умеет привязывать Desktop portable actor к execution config:
  - `portable_actor.profile_name`;
  - `portable_actor.profile_dir`;
  - `portable_actor.account_username`;
  - `portable_actor.account_label`.
- Добавлена команда `ensure-portable`, которая проверяет Telegram Desktop portable-профиль перед Desktop-assisted invite-flow и при необходимости может запустить его через `telegram_portable.py launch`.
- Добавлена команда `prepare-next`:
  - проверяет portable actor;
  - при необходимости запускает профиль;
  - добавляет или выбирает одного consented пользователя;
  - переводит `new -> checked`;
  - создаёт `execution_plan.json`;
  - по умолчанию резервирует пользователя в `invite_link_created`.
- Добавлена команда `desktop-send-link`:
  - работает только по одному consented пользователю из `invite_state.json`;
  - по умолчанию принимает статусы `invite_link_created`/`checked`;
  - открывает DM через Telegram Desktop portable actor по `tg://resolve?domain=<username>`;
  - печатает ASCII invite link через X11 typing helper;
  - реально нажимает Enter только с явным `--confirm-send`;
  - переводит пользователя в `sent` только при `--record-result` после успешного `--confirm-send`.
- Добавлена команда `desktop-open-add-members`:
  - это first-cut no-API Desktop UI path через Telegram Desktop portable;
  - использует `tg://resolve?domain=<handle>` для открытия группы;
  - читает `log-diagnose` перед шагом `Add Members`;
  - открывает `Info` и `Add members` через AT-SPI accessibility primitives вместо Telegram API;
  - может ввести username в right-side search field только если этот field реально найден, иначе останавливается до ввода.
- Добавлена команда `desktop-add-contact-profile`:
  - открывает `tg://resolve?domain=<username>&profile` для одного consented пользователя;
  - делает no-API click-path `Add to contacts -> Done` по настраиваемым ratio;
  - пишет step-by-step `execution_record.json` и PNG-скриншоты (`before/after/verify`) в `executions/<id>/`.
- По состоянию на `2026-05-02` desktop-path `поиск -> профиль -> Add to contacts -> Done` подтверждён на portable actor `AK` для `@super_pavlik`:
  - исправлен выбор точного search result через `search_result_index`;
  - добавлен exact username guard в profile overlay перед `Add to contacts`;
  - submit `Готово` теперь считается от `dialog`-геометрии, а не от слепой точки под модалкой;
  - clipboard paste после ввода `Имя/Фамилия` теперь схлопывает выделение `End`, чтобы следующий клик не тратился на снятие selection.
- Executor GUI получил действия `ensure-portable` и `prepare-next`.
- Executor GUI получил действия `desktop-send dry` и `desktop-send live`.
- Текущий job `chat_Zhirotop_shop` привязан к portable actor:
  - profile: `AK`;
  - dir: `/home/max/TelegramPortableAK`;
  - account: `@M_a_g_g_i_e`;
  - target: `https://t.me/Zhirotop_shop`.
- Для следующего чата зафиксирован отдельный copy-paste prompt:
  - `tools/telegram_invite_manager/NEXT_CHAT_AGENT_PROMPT_RU.md`
  - он задаёт новому агенту стартовую точку, границы редактирования и обязательный порядок чтения.

### Telegram Desktop portable helper
- Добавлен новый helper для Linux portable-профилей Telegram Desktop:
  - `scripts/telegram_portable.py`
  - `scripts/telegram_portable_gui.sh`
- Новый helper умеет:
  - скачать официальный Linux runtime Telegram Desktop в локальный cache при первом запуске;
  - развернуть отдельную папку `~/TelegramPortable-<profile>`;
  - распаковать zip в `TelegramForcePortable/tdata`;
  - безопасно переимпортировать тот же профиль только если его процесс не запущен;
  - сразу запустить профиль и вернуть `pid/log_path`;
  - писать `portable-profile.json` с metadata по профилю.
- Helper теперь умеет:
  - принимать существующий legacy portable-профиль через `adopt` без переимпорта `tdata`;
  - показывать `status` по профилю, включая `pid` и X11-окна;
  - показывать `list` portable-профилей под `output-root`;
  - запускать существующий профиль по `--profile-dir`;
  - открывать `tg://...` URI через `open-uri`;
  - печатать ASCII-текст в окно portable-профиля через `type-text`;
  - отправлять X11 key chords через `press-keys`;
  - разбирать `TelegramForcePortable/log.txt` через `log-diagnose`;
  - кликать по окну по относительным координатам через `window-click`;
  - снимать PNG текущего Telegram X11-окна через `window-screenshot`;
  - читать AT-SPI accessibility-узлы через `accessibility-dump`;
  - фильтровать accessibility-узлы по state (`focused`, `editable`, `showing`);
  - кликать по доступным Telegram Desktop controls через `accessibility-click`;
  - вводить ASCII-текст в accessibility-selected field через `accessibility-type-text`.

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
- После добавления `desktop-add-contact-profile` полный unit-набор снова зелёный: `167/167`.
- Полный unit-набор сейчас зелёный: `165/165`.
- После добавления `desktop-send-link` полный unit-набор зелёный: `159/159`.
- `py_compile` зелёный для `scripts/telegram_portable.py`, `scripts/telegram_invite_manager.py`, `scripts/telegram_invite_executor.py`.
- `bash -n` зелёный для Telegram GUI/wrapper скриптов invite/portable контура.
- `git diff --check` зелёный.
- Live smoke новой команды `desktop-add-contact-profile` на actor `@S_e_r_a_p_h_i_na` (`AK2`) выполнен:
  - job: `/home/max/telegram_invite_jobs/chat_Zhirotop_shop_AK2`;
  - execution record: `/home/max/telegram_invite_jobs/chat_Zhirotop_shop_AK2/executions/20260427T131700Z/execution_record.json`;
  - скриншоты: `desktop_add_contact_profile_before.png`, `desktop_add_contact_profile_after_actions.png`, `desktop_add_contact_profile_verify.png`;
  - факт: шаги `open profile -> click add -> click done -> reopen profile` выполнены кодом; автоматический strong-signal подтверждения сохранения контакта пока не зафиксирован.
- Новый live smoke `prepare-add-contact-profile` на actor `AK` (`/home/max/TelegramPortableAK`) для `@super_pavlik` на `2026-05-02` завершился успешной верификацией контакта:
  - run: `~/.local/share/telegram-sandbox-activity-runner/runs/20260502T064226-de0a009a/`;
  - итоговый submit-click: `dialog_submit_click = {x_ratio: 0.5576, y_ratio: 0.7611}`;
  - verify state: `ui_verify_contact_present`;
  - в profile verify видны `EDIT CONTACT` и `DELETE CONTACT`, а `ADD CONTACT` исчез.
- `desktop-send-link --dry-run` smoke на текущем job `chat_Zhirotop_shop` подтверждён:
  - actor: `@M_a_g_g_i_e`;
  - profile dir: `/home/max/TelegramPortableAK`;
  - window: `0x0460002e`;
  - username: `@kamaz_master1`;
  - URI: `tg://resolve?domain=kamaz_master1`;
  - message: `https://t.me/Zhirotop_shop`;
  - отправки не было, state не менялся;
  - execution record: `/home/max/telegram_invite_jobs/chat_Zhirotop_shop/executions/20260426T074654Z/execution_record.json`.
- Live one-by-one Desktop send для `@M_a_g_g_i_e -> https://t.me/Zhirotop_shop` выполнен `2026-04-26` после явного подтверждения consent для списка из 29 usernames:
  - job: `/home/max/telegram_invite_jobs/chat_Zhirotop_shop`;
  - preflight summary: `/tmp/tg_invite_desktop_preflight_20260426T075806Z.tsv`;
  - live summary: `/tmp/tg_invite_desktop_live_20260426T075842Z.tsv`;
  - все 29 новых пользователей прошли `prepare-next` и dry-run;
  - все 29 live execution records завершились `outcome=sent`, `target_status=sent`;
  - итоговый state: `sent=29`, `requested=2`;
  - первый live record: `/home/max/telegram_invite_jobs/chat_Zhirotop_shop/executions/20260426T075842Z/execution_record.json`;
  - последний live record: `/home/max/telegram_invite_jobs/chat_Zhirotop_shop/executions/20260426T080413Z/execution_record.json`.
- `log-diagnose` на текущем portable actor `@M_a_g_g_i_e` подтвердил Telegram-side ошибки в `TelegramForcePortable/log.txt`:
  - `PEER_FLOOD`;
  - `PEER_ID_INVALID`;
  - это значит, что внутренний лог пригоден для stop-signal/диагностики, но сам по себе не заменяет командный слой `Add Members`.
- Новый no-API portable accessibility layer подтверждён live safe-smoke на текущем actor `@M_a_g_g_i_e`:
  - accessibility dump для `Info`:
    - `/tmp/tg_portable_accessibility_info_20260426.json`
  - accessibility dump для `Add members`:
    - `/tmp/tg_portable_accessibility_add_members_20260426.json`
  - dry-run executor orchestration:
    - `/tmp/tg_desktop_open_add_members_dry_20260426.json`
  - факты:
    - `Info` виден как AT-SPI `push button` с screen extents;
    - `Add members` виден в accessibility tree как `push button`, но у самого узла пока `0x0` extents, поэтому helper использует ancestor-based click fallback;
    - `desktop-open-add-members --dry-run` уже встроен в invite execution flow и использует `tg://resolve?domain=Zhirotop_shop`.
- Новый no-API keyboard слой для Telegram Desktop подтверждён live на текущем actor `@M_a_g_g_i_e`:
  - helper получил команду `press-keys`;
  - исправлен реальный баг в `_send_x11_key_sequence`, из-за которого X11 key path был фактически пустым;
  - live artifacts:
    - `/tmp/tg_portable_keyboard_20260426/press_ctrl_f.json`
    - `/tmp/tg_portable_keyboard_20260426/press_escape_after_ctrl_f.json`
  - факты:
    - `Control_L+f` стабильно переводит Telegram Desktop в search layout без клика по правому header;
    - `Escape` возвращает layout обратно в обычный chat view;
    - keyboard-path теперь можно использовать как отдельный no-API fallback для дальнейшего direct-add исследования.
- Для no-API Desktop path добавлены state-aware accessibility dump и Telegram-only screenshot helper:
  - `accessibility-dump` теперь умеет `--state focused`;
  - helper получил команду `window-screenshot`, которая снимает PNG по X11 `window_id`, а не bbox активного экрана;
  - live artifacts:
    - `/tmp/tg_portable_focus_20260426/summary.json`
    - `/tmp/tg_portable_focus_cycle_20260426/summary.json`
    - `/tmp/tg_portable_tabwalk_20260426/summary.json`
    - `/tmp/tg_portable_click_screens_20260426/summary.json`
  - факты:
    - текущий keyboard focus в Telegram ходит в основном между левым global `Search` и `Write a message...`, а не уходит в правый header/sidebar;
    - `Search messages` accessibility-click на текущем окне визуально не меняет layout;
    - `Info` и `Chat menu` accessibility-click стабильно открывают pinned messages overlay, а не group info sidebar.
- После добавления `press-keys`, state-aware dump, `window-screenshot` и live click/focus smoke полный unit-набор снова зелёный: `165/165`; `git diff --check` зелёный.
- После добавления `prepare-next` полный unit-набор снова зелёный: `148/148`.
- После добавления portable actor / ensure-portable полный unit-набор был зелёный: `146/146`.
- После добавления root-entry onboarding-файла полный unit-набор снова зелёный: `143/143`.
- После расширения `AGENTS.md` до полной capability-map полный unit-набор снова зелёный: `143/143`.
- После добавления Invite Manager полный unit-набор был зелёный: `117/117`.
- После добавления Invite Executor полный unit-набор был зелёный: `123/123`.
- После добавления one-user режима полный unit-набор зелёный: `127/127`.
- После добавления `add-contact` и `inspect-chat` для одного consented пользователя полный unit-набор зелёный: `133/133`.
- Новый `Invite Manager` покрыт unit-тестами:
  - `tests/test_telegram_invite_manager.py`
  - `7/7 OK`
- Новый `Invite Executor` покрыт unit-тестами:
  - `tests/test_telegram_invite_executor.py`
  - `17/17 OK`
- Dry-run smoke нового execution-слоя подтверждён:
  - job dir:
    - `/tmp/tg_invite_executor_smoke.GKdXBN/job`
  - configure:
    - `/tmp/tg_invite_executor_configure.json`
  - plan:
    - `/tmp/tg_invite_executor_plan.json`
  - open-chat dry-run:
    - `/tmp/tg_invite_executor_open.json`
  - факты:
    - execution-plan выбрал `2` consented users;
    - `reserve` перевёл их в `invite_link_created`;
    - `open-chat` собрал корректную browser-команду через `--url-pattern ... activate`.
- One-user smoke подтверждён:
  - job dir:
    - `/tmp/tg_invite_one_user.qsvVAc/job`
  - add-user:
    - `/tmp/tg_invite_one_add.json`
  - plan:
    - `/tmp/tg_invite_one_plan.json`
  - open-chat dry-run:
    - `/tmp/tg_invite_one_open.json`
  - факты:
    - `add-user` создал job с нуля через `--chat-url`;
    - один consented user попал в `new`;
    - manager `run --limit 1` перевёл его в `checked`;
    - executor `plan --limit 1 --reserve` перевёл его в `invite_link_created`.
- Живой one-user smoke в рабочем каталоге подтверждён:
  - job dir:
    - `/home/max/telegram_invite_jobs/chat_-2465948544`
  - execution plan:
    - `/home/max/telegram_invite_jobs/chat_-2465948544/executions/20260424T123754Z/execution_plan.json`
  - execution record:
    - `/home/max/telegram_invite_jobs/chat_-2465948544/executions/20260424T123800Z/execution_record.json`
  - bridge result:
    - `open-chat` создал Telegram tab `614280462`
    - URL: `https://web.telegram.org/k/#-2465948544`
  - тестовая запись `@sitectl_smoke_user` после проверки помечена как `skipped`, чтобы не мешать реальной очереди.
- Живой one-user test для `@Kamaz_master1 -> https://t.me/Zhirotop_shop` подтверждён:
  - job dir:
    - `/home/max/telegram_invite_jobs/chat_Zhirotop_shop`
  - invite run:
    - `/home/max/telegram_invite_jobs/chat_Zhirotop_shop/runs/20260424T142342Z/invite_run.json`
  - execution plan:
    - `/home/max/telegram_invite_jobs/chat_Zhirotop_shop/executions/20260424T142347Z/execution_plan.json`
  - live browser evidence:
    - `/tmp/tg_invite_zhiritop_page_url.json`
    - `/tmp/tg_invite_zhiritop_body_text.json`
    - `/tmp/tg_invite_zhiritop_report.json`
  - bridge result:
    - открыт Telegram tab `614280505`;
    - URL подтверждён как `https://web.telegram.org/k/#@Zhirotop_shop`;
    - body text подтверждает открытый чат `Жиротоп Shop`.
  - на `2026-04-24` фактическая отправка сообщения пользователю не выполнялась; статус `@kamaz_master1` был `invite_link_created`.
- Live add test для `@Kamaz_master1 -> https://t.me/Zhirotop_shop` выполнен `2026-04-25`:
  - Telegram Web tab:
    - `614280764`
  - live URL:
    - `https://web.telegram.org/k/#@Zhirotop_shop`
  - UI-path:
    - `Add Members` открыт через `#column-right .profile-container.can-add-members button.btn-circle.btn-corner`;
    - поиск `.add-members-container .selector-search-input` по `Kamaz_master1`;
    - найден контакт `Камаз`, `data-peer-id="1404471788"`;
    - открыт popup `Are you sure you want to add Камаз ...`;
    - финальный `Add` нажат через `.popup-add-members .popup-buttons button:nth-child(1)`.
  - результат:
    - popup закрылся;
    - видимых ошибок `privacy/cannot/too many/error` не было;
    - сервисного `joined/added` не найдено;
    - счётчик остался `2 440 members`;
    - state записан как `requested`, не `joined`.
  - execution record:
    - `/home/max/telegram_invite_jobs/chat_Zhirotop_shop/executions/20260425T052501Z/execution_record.json`
- Live add test для `@olegoleg48 -> https://t.me/Zhirotop_shop` выполнен `2026-04-25`:
  - before/after verification:
    - `inspect-chat` до действия показал `2 440 members`;
    - `inspect-chat` после действия и после ожидания также показал `2 440 members`.
  - live add result:
    - `add-contact` нашёл пользователя как `Oleg S`, `data-peer-id="1410391920"`;
    - финальный `Add` был нажат;
    - видимых ошибок Telegram не показал;
    - state записан как `requested`, не `joined`.
  - execution record:
    - `/home/max/telegram_invite_jobs/chat_Zhirotop_shop/executions/20260425T061336Z/execution_record.json`
  - практический вывод:
    - live `Add` path работает;
    - рост количества участников по member count не подтверждён;
    - проверка `inspect-chat` до и после live add теперь обязательна.
- После hardening auto-verification выполнен безопасный live smoke invite execution `2026-04-25`:
  - inspect artifact:
    - `/tmp/tg_invite_executor_inspect_20260425.json`
  - report artifact:
    - `/tmp/tg_invite_executor_report_20260425.json`
  - факты:
    - `inspect-chat` на живом bridge сработал через новый общий snapshot-helper;
    - `open_or_activate_chat` открыл tab `614281030`;
    - видимый счётчик прочитан как `2 667 members`;
    - `report` теперь показывает `latest_execution_records` и их verification summary;
    - live `Add` заново не выполнялся, чтобы не превращать smoke в реальное действие над пользователем.
- После hardening member-list verification и нормализации `t.me -> web.telegram` выполнен ещё один безопасный live smoke `2026-04-25`:
  - inspect artifact:
    - `/tmp/tg_invite_executor_inspect_members_20260425_v3.json`
  - факты:
    - job `/home/max/telegram_invite_jobs/chat_Zhirotop_shop` по-прежнему хранит `chat_url = https://t.me/Zhirotop_shop`;
    - `inspect-chat` без явного `tab_id` открыл `browser new-tab https://web.telegram.org/k/#@Zhirotop_shop`;
    - live URL подтверждён как `https://web.telegram.org/k/#@Zhirotop_shop`;
    - видимый счётчик прочитан как `2 667 members`;
    - `visible_member_peers` вернул видимого участника `1960795556 / @joinhide9_bot`.
- Shell syntax и `py_compile` для последних изменений проходили зелёными.
- Новый `telegram_portable.py` покрыт unit-тестами:
  - `tests/test_telegram_portable.py`
  - `5/5 OK`
- После добавления `adopt/status/list` и portable actor точечные тесты зелёные:
  - `tests.test_telegram_portable`
  - `tests.test_telegram_invite_executor`
  - `25/25 OK`
- Для helper'а пройдены:
  - `python3 -m py_compile scripts/telegram_portable.py`
  - `bash -n scripts/telegram_portable_gui.sh`
- Текущий live portable actor принят в управление:
  - metadata:
    - `/home/max/TelegramPortableAK/portable-profile.json`
  - ensure artifact:
    - `/tmp/tg_invite_portable_actor_20260426.json`
  - факты:
    - `profile_name = AK`;
    - `account.username = @M_a_g_g_i_e`;
    - `running = true`;
    - `pid = 10413`;
    - X11 window `0x0460002e`;
    - окно Telegram Desktop открыто на `Жиротоп Shop`.
- Dry-run `prepare-next` на текущем job подтвердил быстрый pipeline и корректный empty-queue guard:
  - job:
    - `/home/max/telegram_invite_jobs/chat_Zhirotop_shop`
  - artifact:
    - `/tmp/tg_invite_prepare_next_20260426.json`
  - факт:
    - portable actor `@M_a_g_g_i_e` проверен;
    - команда вернула `status = no_candidates`, потому что текущие 2 пользователя уже `requested`;
    - новых `new/checked` пользователей сейчас нет.
- Live smoke нового Telegram portable helper подтверждён:
  - import artifact:
    - `/tmp/tg_portable_smoke_import.json`
  - profile dir:
    - `/tmp/tg_portable_smoke/TelegramPortable-smoke-ak`
  - metadata:
    - `/tmp/tg_portable_smoke/TelegramPortable-smoke-ak/portable-profile.json`
  - launch log:
    - `/tmp/tg_portable_smoke/TelegramPortable-smoke-ak/portable-launch.log`
  - факты:
    - helper сам собрал portable-папку из zip `telegram_ak/tdata-20260425T113735Z-3-001.zip`;
    - внутри создан `TelegramForcePortable/tdata/key_datas`;
    - Telegram стартовал именно из portable-папки и затем был остановлен после smoke-проверки.
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

### 0. Invite execution пока operator-assisted
Теперь кроме manager/state слоя есть и execution-слой, но он пока безопасно ограничен:
- configure/plan/open-chat/inspect-chat/add-contact/desktop-add-contact-profile/record/report;
- portable actor / ensure-portable для Telegram Desktop portable executor identity;
- prepare-next для быстрого one-user queue/plan/reserve pipeline;
- `open-chat` уже использует `site-control`;
- `add-contact` теперь сам пишет verification evidence before/after и умеет подтверждать `joined` по видимому member list;
- actual Telegram invite action по-прежнему остаётся за оператором.
- Для `desktop-add-contact-profile` пока нет стабильного machine-check сигнала "контакт точно сохранён" на всех UI-вариантах профиля Telegram Desktop (modal/full-profile), поэтому результат остаётся operator-verified.

Это осознанно:
- сначала собран надёжный state/reporting/execution каркас;
- теперь зафиксирован Desktop actor `@M_a_g_g_i_e` для `Zhirotop_shop`;
- только потом можно делать живой `invite link / join request` orchestration path.

### 1. Deep mention уже рабочий, но остаётся неоднородным
Есть подтверждённые live-run, где mention/deep без history backfill реально собрал новые `@username`.
Но есть и peer, для которых `Mention` в конкретном DOM-срезе не появляется или даёт miss.

То есть deep-path больше не сломан инфраструктурно: stale runtime снят, `click_menu_text` живой, composer-read рабочий. Текущий узкий момент уже прикладной: неодинаковая доступность `Mention` и разный throughput по разным peer/слоям чата.

### 2. Throughput deep-path уже вырос, но всё ещё ниже желаемого на длинных run
Сейчас основной рост по новым `@username` уже пошёл:
- на коротких run deep умеет делать `processed 3 / filled 3` прямо в одном scroll-step;
- один неудачный peer больше не ломает весь batch-step.

Следующий резерв уже не в починке path, а в общем балансе runtime между discovery и deep на длинных прогонах.

## Следующий Приоритет

### Для Telegram export
- delivery-aware bailout после `expired no delivery`;
- более ранний URL fallback;
- повторный live smoke `fast` vs `deep`.

### Для Invite Manager
- текущий Desktop actor для `Zhirotop_shop` проверяется через `ensure-portable`, а `desktop-send-link` уже закрывает безопасный one-user dry/live path через Telegram Desktop portable;
- live-отправка всё ещё требует явного `--confirm-send` и consented username; текущая очередь `chat_Zhirotop_shop` пуста для `checked/new`, оба известных пользователя уже `requested`;
- основной рабочий поток для direct add остаётся через `site-control-kit` / Telegram Web (`open-chat -> inspect-chat -> add-contact`), а Desktop no-API path пока не должен заменять его как primary flow;
- no-API path для Desktop начат через AT-SPI accessibility layer, но финальный direct-add ещё не закрыт end-to-end;
- если возвращаться к Desktop-треку позже, сначала нужно стабилизировать вход в реальный `Add Members` search sheet без ручного угадывания hitpoint;
- вынести подтверждение вступления за пределы текущего видимого member list, если нужный peer не попал в правую панель сразу;
- по возможности привязать это подтверждение к отдельному Telegram-visible signal, а не только к общему `member_count`;
- довести безопасный orchestration path через invite links / join requests;
- следующий Desktop-specific шаг: после добавления нового consented username выполнить `prepare-next`, затем `desktop-send-link --dry-run`, и только по явному операторскому решению `desktop-send-link --confirm-send --record-result`;
- не делать принудительное массовое добавление пользователей;
- при первом live-шаге обязательно сохранять execution record и зафиксировать его в этом status-файле.

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
- Для invite/portable трека подтверждён actor binding:
  - `chat_Zhirotop_shop` теперь хранит `portable_actor` для `@M_a_g_g_i_e`;
  - `/home/max/TelegramPortableAK` принят в управление через `telegram_portable.py adopt`;
  - `ensure-portable` подтвердил live process/window:
    - `/tmp/tg_invite_portable_actor_20260426.json`.
- Для invite/portable трека подтверждён `desktop-send-link --dry-run`:
  - actor: `@M_a_g_g_i_e`;
  - username: `@kamaz_master1`;
  - execution record: `/home/max/telegram_invite_jobs/chat_Zhirotop_shop/executions/20260426T074654Z/execution_record.json`;
  - отправки не было, state не менялся.
- Для invite/portable трека подтверждён live smoke `desktop-add-contact-profile` на `AK2`:
  - actor: `@S_e_r_a_p_h_i_na`;
  - username: `@bulan04`;
  - execution record: `/home/max/telegram_invite_jobs/chat_Zhirotop_shop_AK2/executions/20260427T131700Z/execution_record.json`;
  - факт: full flow отработал кодом с evidence-скриншотами, но итог "contact saved" пока подтверждается только визуально оператором.
- Для live invite-link рассылки подтверждён one-by-one Desktop flow:
  - actor: `@M_a_g_g_i_e`;
  - target chat: `https://t.me/Zhirotop_shop`;
  - 29 consented usernames из списка оператора получили live execution records со статусом `sent`;
  - итоговый state job: `sent=29`, `requested=2`;
  - summary: `/tmp/tg_invite_desktop_live_20260426T075842Z.tsv`.
- Для no-API Desktop path подтверждён live accessibility слой на текущем actor:
  - `/tmp/tg_portable_accessibility_info_20260426.json`
  - `/tmp/tg_portable_accessibility_add_members_20260426.json`
  - `/tmp/tg_desktop_open_add_members_dry_20260426.json`
  - факт: Telegram Desktop на Linux отдаёт `Info` и `Add members` в AT-SPI tree, поэтому следующий direct-add шаг можно делать через код без Telegram API и без blind координат как основного метода.
- Для no-API Desktop path подтверждён и отдельный keyboard fallback:
  - `/tmp/tg_portable_keyboard_20260426/press_ctrl_f.json`
  - `/tmp/tg_portable_keyboard_20260426/press_escape_after_ctrl_f.json`
  - факт: `press-keys` теперь реально меняет Telegram Desktop layout (`Ctrl+F` открывает search, `Escape` закрывает), значит следующий no-API шаг можно строить не только через click-path, но и через shortcut/focus navigation.
- Для no-API Desktop path подтверждён Telegram-only screenshot helper и click validation:
  - `/tmp/tg_portable_click_screens_20260426/baseline.png`
  - `/tmp/tg_portable_click_screens_20260426/search_messages_click.png`
  - `/tmp/tg_portable_click_screens_20260426/info_click.png`
  - `/tmp/tg_portable_click_screens_20260426/summary.json`
  - факт: `Search messages` accessibility-click на текущем окне визуально ничего не открывает, а `Info` / `Chat menu` воспроизводимо открывают `77 pinned messages`; значит следующий поиск входа в `Add members` нужно вести по другому control-path.
- Для нового `AK` portable-only add-contact path подтверждён username-safe desktop route:
  - поиск `@super_pavlik` открывается по `search_result_index = 2`, а не по первому похожему каналу;
  - клик по заголовку чата (`window-click` на header area) стабильно открывает profile overlay с `ДОБАВИТЬ КОНТАКТ`;
  - AT-SPI на profile overlay реально отдаёт exact username label `@super_pavlik`, поэтому tool теперь может делать post-open guard "ввели один username -> в профиле видим тот же exact username";
  - локальные regression checks после этого зелёные:
    - `python3 -m py_compile /home/max/site-control-kit/scripts/telegram_portable.py`;
    - `python3 -m unittest /home/max/site-control-kit/tests/test_telegram_portable.py`;
  - live evidence:
    - `~/.local/share/telegram-sandbox-activity-runner/runs/20260502T054306-8c3daf4f/`;
  - остаточный gap:
    - exact username verification уже проходит, но автоматический клик по `ДОБАВИТЬ КОНТАКТ` в этом path всё ещё не переводит экран в stable `Новый контакт -> Готово`, поэтому последний submit-step пока остаётся недобитым.
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
1. Для Invite/Desktop: держать основным рабочим путём `site-control-kit` / Telegram Web flow (`open-chat -> inspect-chat -> add-contact`) и не подменять его Desktop-guessing path.
2. Для Invite/Desktop: обобщить успешный `desktop-add-contact-profile` smoke с `AK/@super_pavlik` на другие профили и UI-варианты Telegram Desktop, чтобы submit больше не требовал ручной докалибровки по каждому кейсу.
3. Снизить runtime-затраты discovery относительно deep, чтобы multi-peer deep чаще успевал проходить следующий слой visible peer.
4. Поднять приоритеты deep-target'ов: раньше брать тех peer, у кого вероятность успешного `Mention` выше.
5. Разделить browser capability/runtime compatibility и Telegram export concerns в отдельные модули/слои.
6. Отделить понятие `best-known latest` от `most-recent run` в UI и документации, если пользователю важно видеть именно последний прогон как основной артефакт.
7. Декомпозировать `export_telegram_members_non_pii.py` на модули.

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
