# Project Status RU

Последнее обновление: 2026-04-23

Этот файл нужен как точка входа для любого нового чата и любого нового агента.
Перед новой задачей его нужно прочитать целиком.

Актуальный onboarding-пакет для нового агента теперь лежит в `docs/agent_handoff_ru/`.
Читать его нужно по номерам файлов, начиная с `00_START_HERE.md`.

## Сделано

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
- Текущий локальный unit-набор зелёный: `88/88`.
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
