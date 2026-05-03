# Project Status RU

Последнее обновление: 2026-05-03

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
  - `tools/telegram/invite_manager/`
  - `tools/telegram/invite_manager/AGENT_GUIDE_RU.md`
  - `tools/telegram/invite_manager/ONE_USER_FLOW_RU.md`
  - `tools/telegram/invite_manager/NEXT_CHAT_AGENT_PROMPT_RU.md`
  - `tools/telegram/invite_manager/bin/*`
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
  - `tools/telegram/invite_manager/NEXT_CHAT_AGENT_PROMPT_RU.md`
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

### Unified tool platform
- Добавлен отдельный registry-driven platform layer:
  - `tool_platform/catalog.py`
  - `tool_platform/cli.py`
  - `tool_platform/gui.py`
  - `tools/telegram/NEXT_CHAT_AGENT_PROMPT_RU.md`
  - `tools/telegram/README_RU.md`
  - `tools/telegram/AGENT_GUIDE_RU.md`
  - `tools/telegram/platform/*`
  - `tools/telegram/export/*`
  - `tools/telegram/portable_helper/*`
  - `tools/telegram/session_runner/*`
- Платформа уже умеет:
  - подключать embedded инструменты и visible wrappers через `tool_manifest.json`;
  - валидировать registry;
  - показывать единый catalog через CLI;
  - открывать Tkinter control panel с docs, actions и artifacts;
  - показывать portable-пользователей в dropdown;
  - импортировать нового пользователя по `tdata.zip`;
  - принимать в управление уже существующую portable-папку через adopt прямо из панели;
  - рендерить profile/workflow details в читаемых text-card блоках вместо тесных table rows, чтобы UI не ломался на Linux HiDPI scaling;
  - показывать оператору только несколько понятных режимов без конкуренции за одно окно:
    - `Добавить контакты из TXT`
    - `Сессия и сообщения`
    - `Совместный режим`
  - в первом режиме принимать `.txt/.csv/.json` список username и реально добавлять эти username в контакты выбранного Telegram Desktop portable-профиля;
  - для первого режима использовать новый orchestration-командный слой `desktop-add-contact-batch`, который сам создаёт/продолжает local state и по очереди вызывает `desktop-add-contact-profile`;
  - для первого режима показывать прямо в панели preview списка, очередь `осталось`, блок `уже добавлены`, последние ошибки и историю batch-запусков;
  - для первого режима уметь не только стартовать новую задачу, но и отдельно `Продолжить очередь` и `Повторить ошибки` по уже сохранённому `invite_state.json` без повторного выбора файла;
  - для первого режима читать operator summaries напрямую из `invite_state.json` и `executions/*/batch_contact_add.json`, чтобы после рестарта панели не терялась видимость состояния;
  - в режиме сессии загружать из session-config не только список адресатов, но и шаблоны сообщений, автоотправку и лимиты;
  - в режиме сессии держать ключевые настройки в верхней видимой карточке, а не глубоко внутри нижнего блока:
    - сколько random-walk визитов делать за цикл;
    - минимум и максимум секунд в чате;
    - сколько сообщений отправлять за цикл;
    - общий лимит сообщений;
    - автоотправка;
    - непрерывная работа до `Стоп`;
  - в режиме сессии позволять править в панели:
    - кому писать;
    - какой текст отправлять;
    - сколько random-walk визитов делать за цикл;
    - сколько секунд держать открытый чат;
    - сколько сообщений отправлять за цикл;
    - сколько максимум отправить за всю непрерывную сессию;
  - в режиме сессии показывать живой таймер, пока session runner работает;
  - в режиме сессии запускать session runner либо на один цикл, либо в непрерывном режиме `до Стопа`;
  - в режиме сессии читать `session_state.json` и `runs/*/run.json`, чтобы прямо в панели показывать summary, историю последних запусков и сообщения, которые остались неотправленными;
  - в новом `Совместном режиме` вести один и тот же профиль по цепочке `Добавить → Сессия`, сохраняя panel-only phase-state и не разрешая второй live-процесс на тот же профиль;
  - в новом `Совместном режиме`, если непрерывная сессия выключена, автоматически чередовать шаги:
    - `batch контактов -> один session-cycle -> следующий batch -> следующий session-cycle`;
    - цикл продолжается, пока в очереди есть `new/checked` username или пока оператор не остановит его;
  - если в `Совместном режиме` включена непрерывная сессия, panel orchestration специально не делает дальнейшее чередование: после contact batch стартует одна длинная сессия до `Стоп`;
  - session runner больше не страдает от panel-regression, где GUI по умолчанию перетирал `auto_send=true` обратно в `false`;
  - для реальной отправки сообщений session runner теперь использует каскад `кнопка Отправить -> двойной Return`, потому что один AT-SPI click по кнопке в живом `TelegramPortableAK` не всегда доводил действие до реального outgoing message;
  - непрерывный CLI-режим `run-session --continuous` умеет корректно завершаться статусом `stopped` после operator stop по `SIGTERM`, а не только аварийным kill.
- Отдельно собран новый видимый Telegram tools hub:
  - `tools/telegram/`
  - `platform/`
  - `invite_manager/`
  - `portable_helper/`
  - `session_runner/`
  - `export/`
- В registry уже подключены:
  - `tools/telegram/invite_manager/tool_manifest.json`;
  - `tools/telegram/portable_helper/tool_manifest.json`;
  - `tools/telegram/export/tool_manifest.json`;
  - `tools/telegram/session_runner/tool_manifest.json`.
- Это зафиксировало новый рабочий контракт:
  - отдельные инструменты живут сами по себе;
  - общая панель читает manifests и orchestration metadata;
  - session-runner виден из Telegram-хаба как отдельная единица, даже если runtime остаётся в standalone repo.
  - для нового агента теперь есть отдельная точка входа `tools/telegram/NEXT_CHAT_AGENT_PROMPT_RU.md`, зафиксированная именно на текущем checkpoint.

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
- После перевода Telegram control center в русский двухрежимный UX подтверждены:
  - `python3 -m py_compile tool_platform/*.py scripts/telegram_portable.py scripts/telegram_invite_executor.py scripts/telegram_invite_manager.py`
  - `PYTHONPATH="$PWD" python3 -m unittest discover -s tests -p 'test_*.py'` → `199 OK`
  - `bash -n tools/telegram/platform/bin/tool-platform tools/telegram/platform/bin/tool-platform-panel tools/telegram/session_runner/bin/telegram-session-runner tools/telegram/invite_manager/bin/telegram-invite-manager tools/telegram/invite_manager/bin/telegram-invite-executor`
  - `./tools/telegram/platform/bin/tool-platform validate-registry`
  - live GUI smoke: окно `Центр управления Telegram` поднято, `xwininfo` подтвердил `1460x980`, старый английский тестовый экземпляр панели закрыт.
  - дополнительный live UX-fix: блок `Добавить / подключить профили` вынесен в отдельное окно, чтобы большие режимы были видны сразу на основном экране.
  - первый режим панели переименован из ложного `Старт инвайтов` в честный `Добавить контакты из TXT`;
  - критический функциональный fix: первый режим больше не создаёт пустой invite-job вместо действия, а запускает `desktop-add-contact-batch` и реально работает как orchestration-слой поверх `desktop-add-contact-profile`;
  - критический live-fix: запуск panel actions переведён с прямого синхронного вызова на фоновый subprocess с безопасным возвратом через main-thread queue, поэтому `Показать план` и `Старт` больше не упираются в Tk thread-boundary;
  - добавлены явные `Стоп`-кнопки для invite/session режимов, общий лог панели `/tmp/telegram-control-center-panel.log` и вертикальная прокрутка длинного экрана;
  - live smoke самой панели через callbacks подтверждён:
    - `Старт добавления` вернул batch summary по реальному `desktop-add-contact-batch`;
    - `Показать план` для session runner вернул статус `Завершено` и план с визитами/черновиком;
    - `Стоп` подтвердил остановку долгой фоновой команды со статусом `Остановлено`.
  - после добивки режима `Сессия и сообщения` дополнительно подтверждены:
    - `python3 -m py_compile telegram_portable_session_tool/*.py`
    - `PYTHONPATH=/home/max/telegram-portable-session-tool python3 -m unittest discover -s tests -p 'test_*.py'` → `14 OK`
    - live investigation по реальному `TelegramPortableAK`:
      - run `/tmp/telegram-session-live-smoke-runs/20260503T112957Z-49d6569a/run.json` показал, что одного accessibility-click по `Отправить` недостаточно: черновик оставался в поле ввода;
      - после усиления send-cascade live run `/tmp/telegram-session-live-smoke-runs-2/20260503T113146Z-c631d2e3/run.json` реально отправил `Добрый день!`;
      - post-run screenshot `/tmp/telegram-session-live-smoke-after-final-2.png` подтвердил исходящее сообщение `Добрый день! 14:31` и пустое поле `Сообщение...`;
    - live stop smoke непрерывной сессии:
      - отдельный parent PID получил `SIGTERM`, завершился с `rc=0`;
      - итоговый JSON `/tmp/telegram-session-continuous-stop-output.json` вернул `status: stopped`, `continuous: true`, `cycle_count: 2`.
  - safe smoke нового backend batch-path подтверждён на реальном portable actor `AK/@M_a_g_g_i_e` без изменения контактов:
    - команда: `python3 scripts/telegram_invite_executor.py desktop-add-contact-batch ... --confirm-add --dry-run`
    - результат: `status=dry_run`, `selected_users=1`, `failed_count=0`, `remaining_candidates=1`;
    - артефакт: `/tmp/telegram-contact-batch-smoke.memxTC/job/executions/20260503T103931Z/batch_contact_add.json`
  - после добивки operator-summary слоя панели подтверждены:
    - `python3 -m py_compile tool_platform/gui.py tool_platform/telegram_gui_helpers.py tests/test_tool_platform.py`
    - `PYTHONPATH="$PWD" python3 -m unittest tests.test_tool_platform` → `25 OK`
    - helper-слой теперь покрывает preview списка, snapshot очереди контактов, retry/continue command-shaping и session history snapshot.
  - после добивки combined/persistent-state слоя дополнительно подтверждены:
    - `python3 -m py_compile tool_platform/gui.py tool_platform/telegram_gui_helpers.py tests/test_tool_platform.py`
    - `PYTHONPATH="$PWD" python3 -m unittest tests.test_tool_platform` → `28 OK`
    - helper-слой теперь покрывает:
      - persistent combined-flow state;
      - phase restore после перезапуска панели;
      - profile-conflict guard для live-процессов;
      - новую верхнюю раскладку session settings.
  - после добивки live-case `контакт уже есть` дополнительно подтверждены:
    - `python3 -m py_compile scripts/telegram_invite_executor.py tests/test_telegram_invite_executor.py`
    - `PYTHONPATH="$PWD" python3 -m unittest tests.test_telegram_invite_executor` → `31 OK`
    - live smoke на actor `AK/@M_a_g_g_i_e` для `@abs11144`:
      - `/tmp/telegram-existing-contact-smoke/20260503T150245Z/job/executions/20260503T150245Z/batch_contact_add.json`
      - итог: `status=completed`, `added_count=1`, `already_present_count=1`, `failed_count=0`
      - user-level outcome: `contact_already_present`
      - verify снова подтвердил `Изменить контакт` / `Удалить контакт`, а `Добавить контакт` не видно, поэтому пользователь корректно оставлен в `contact_added`, а не в `failed`.
  - после живого panel-smoke combined режима дополнительно подтверждены:
    - `python3 -m py_compile tool_platform/gui.py`
    - `PYTHONPATH="$PWD" python3 -m unittest tests.test_tool_platform` → `28 OK`
    - live panel harness `Добавить контакты из TXT`:
      - `/tmp/telegram-panel-live-harness-logged/panel-live-result.json`
      - summary уже показывает `добавлено: 1`, `уже было: 1`, `ошибок: 0`;
      - panel log `/tmp/telegram-control-center-panel.log` фиксирует `Старт` и `Завершено` для живого batch-действия.
    - live panel harness `Совместный режим`:
      - `/tmp/telegram-panel-combined-harness-fixed/combined-panel-result.json`
      - шаг `добавление` завершился как success без ручного `Разрешить переход`;
      - шаг `сессия` завершился как `completed` с безопасным run без отправки сообщений;
      - после нового открытия панели combined summary и status корректно восстановились для профиля `AK`;
      - отдельный GUI-fix: закрытие окна больше не оставляет Tk traceback `invalid command name ... _drain_ui_queue`.
  - после диагностики жалобы `в совместном режиме не добавляет` выявлена и закрыта конкретная операторская причина:
    - у профиля `AK` в persisted combined-state оставался старый `job_dir` уже отработанной очереди;
    - backend честно возвращал `selected_users=0`, но combined UX до фикса выглядел как будто шаг просто “ничего не сделал”;
    - теперь panel-layer явно показывает статус `Новых username для добавления нет; выбери другой файл или запускай сессию`;
    - stale combined-state для `AK` вручную сброшен с временного harness-path на пустой стартовый state.
- Для нового unified tool platform зелёные:
  - `PYTHONPATH="$PWD" python3 -m unittest discover -s tests -p 'test_*.py'`
  - `python3 -m py_compile tool_platform/*.py scripts/telegram_invite_executor.py scripts/telegram_portable.py`
  - `bash -n tools/telegram/platform/bin/tool-platform tools/telegram/platform/bin/tool-platform-panel tools/telegram/invite_manager/bin/telegram-invite-manager tools/telegram/invite_manager/bin/telegram-invite-executor tools/telegram/portable_helper/bin/telegram-portable tools/telegram/portable_helper/bin/telegram-portable-gui tools/telegram/export/bin/telegram-exporter tools/telegram/export/bin/telegram-export-chain tools/telegram/export/bin/telegram-export-batch tools/telegram/session_runner/bin/telegram-session-runner scripts/telegram_invite_executor_gui.sh`
  - `./tools/telegram/platform/bin/tool-platform validate-registry`
  - `./tools/telegram/platform/bin/tool-platform list-tools`
- Registry подтвердил подключение двух инструментов:
  - embedded `telegram_invite_manager`;
  - embedded `telegram_portable_helper`;
  - embedded `telegram_export`;
  - visible wrapper `telegram_session_runner`.
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

### 3. Telegram control center уже стал понятным операторским экраном, но summary-слой ещё можно усилить
Новая панель уже умеет:
- выбирать portable-пользователя из dropdown;
- импортировать нового пользователя по `tdata.zip`;
- принимать в управление существующие папки;
- разделять работу на два режима:
  - `Добавить контакты из TXT`
  - `Сессия и сообщения`
- подставлять выбранный профиль в runtime-config session runner;
- принимать файл со списком username и запускать batch-добавление этих username в личные контакты выбранного профиля;
- запускать session runner кнопкой с отдельно редактируемым списком адресатов сообщений.

Следующий запас уже не в базовом UX, а в более удобных summary и быстрых переходах к последним job/run артефактам.

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

### Для Unified Tool Platform
- держать registry-driven слой тонким и не переносить туда Telegram-specific business logic;
- подключать новые инструменты через `tool_manifest.json`, а не через ручную прошивку в GUI;
- не раздувать операторскую панель сверх двух основных режимов без явной пользы;
- следующим шагом показывать summaries для последних invite-job и session-run artifacts без разрастания панели в сложный конструктор экранов;
- при необходимости аккуратно привязать invite-flow к выбранному portable-профилю без смешивания low-level helper логики с UX формы.

### 4. Reload helper стал рабочим, но fallback-кнопка ещё зависит от геометрии
Основной stale-runtime блок снят через self-reload страницы расширения.
Что уже точно работает:
- self-reload через `chrome-extension://.../options.html?action=reload-self`;
- проверка появления `content_commands` после reload;
- post-reload browser commands (`new-tab`, `activate`, `x11-click`, `x11-keys`).

Что ещё остаётся best-effort:
- fallback-клик по кнопке Reload на `chrome://extensions`;
- его точные координаты всё ещё зависят от сборки Chrome/масштаба окна.

### 5. Exporter всё ещё тратит слишком много runtime на discovery до deep
После последних фиксов короткие no-history run уже дают `3/3` успешных deep-update на видимом слое.
Но на длинных прогонах runtime всё ещё может упираться в общий бюджет раньше, чем deep пройдёт следующий слой visible peer.

### 6. X11 fallback для browser tab actions в этой среде ненадёжен
Проверка `_x11_send_keys` на реальном Chrome window вернула `True`, но фактический `Ctrl+T` не создал новую вкладку.
Это отдельный инфраструктурный долг browser CLI.

### 7. Best-known latest может быть исторически сильным, но не самым свежим по времени
Сейчас это осознанное поведение: `latest_*` в chat-dir означает лучший известный snapshot, а не обязательно самый свежий run.
Если пользователю нужен именно последний run как основной артефакт, это потребуется оформить отдельно.

### 8. Экспортёр остаётся монолитным
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
  - этот исторический gap теперь закрыт новым submit-path через live `match_origin` + dialog geometry; см. evidence `20260503T131500Z-fix-abs11144` ниже.
- Для batch-добавления контактов через Telegram control center закрыт ложноположительный success-path:
  - `desktop-add-contact-profile` теперь после `reopen_profile_for_verify` сам снимает явную verify-проверку по доступным кнопкам `Добавить контакт` / `Удалить контакт` / `Изменить контакт`;
  - если после попытки всё ещё виден `Добавить контакт`, команда теперь возвращает `status=failed`, `outcome=contact_not_added`, а не старый ложный success;
  - `desktop-add-contact-batch` теперь помечает пользователя как `contact_added` только при `contact_added_verified`; иначе пишет `failed` и поднимает `completed_with_errors` в batch summary;
  - live evidence на actor `AK/@M_a_g_g_i_e` для `@abs11144`:
    - `/home/max/telegram_invite_jobs/contact_add__AK__1/executions/20260503T124800Z-debug-abs11144/execution_record.json`;
    - ключевой факт: verify снова увидел `Добавить контакт`, поэтому новый код честно остановился на `contact_not_added` и не записал фальшивый `contact_added`.
- Для batch-добавления контактов через Telegram control center подтверждён новый рабочий submit-path на текущем `AK`:
  - из `/home/max/telegram-portable-session-tool` подтверждена важная операционная деталь: критические X11-клики надо считать в `window_geometry`, а не отдавать в `auto`/`accessible_window`;
  - сам рабочий add-contact submit-path перенесён из `/home/max/n8n_ai_call_center/tools/telegram_sandbox_activity_runner/telegram_sandbox_activity_runner.py`;
  - `desktop-add-contact-profile` теперь:
    - ищет `ДОБАВИТЬ КОНТАКТ` через live accessibility-match;
    - открывает модалку `Новый контакт` через `window-click --coordinate-space window_geometry` по live `match_origin`;
    - вычисляет submit `Готово` от live-геометрии dialog ancestor, а не только по статическим fallback ratio;
  - live evidence на actor `AK/@M_a_g_g_i_e` для `@abs11144`:
    - `/home/max/telegram_invite_jobs/contact_add__AK__1/executions/20260503T131500Z-fix-abs11144/execution_record.json`;
    - verify уже показывает `Изменить контакт` и `Удалить контакт`, а `Добавить контакт` исчез;
    - итог команды: `status=completed`, `outcome=contact_added_verified`.
- Для Telegram control center закрыт ещё один операторский UX-gap на уже существующем контакте:
  - если в профиле пользователя кнопки `Добавить контакт` уже нет, но видны `Изменить контакт` / `Удалить контакт`, backend больше не возвращает `ui_add_button_not_found`;
  - новый outcome: `contact_already_present`;
  - batch считает это успехом, переводит пользователя в `contact_added` и отдельно возвращает `already_present_count`;
  - live evidence на actor `AK/@M_a_g_g_i_e` для `@abs11144`:
    - `/tmp/telegram-existing-contact-smoke/20260503T150245Z/job/executions/20260503T150245Z/batch_contact_add.json`;
    - итог batch: `status=completed`, `added_count=1`, `already_present_count=1`, `failed_count=0`.
- Для unified tool platform подтверждён первый рабочий orchestration layer:
  - registry: `/home/max/site-control-kit/tools/telegram/platform/registry/tools.json`;
  - CLI: `./tools/telegram/platform/bin/tool-platform validate-registry`;
  - GUI entrypoint: `./tools/telegram/platform/bin/tool-platform-panel`;
  - подключённые manifests:
    - `/home/max/site-control-kit/tools/telegram/invite_manager/tool_manifest.json`;
    - `/home/max/site-control-kit/tools/telegram/portable_helper/tool_manifest.json`;
    - `/home/max/site-control-kit/tools/telegram/export/tool_manifest.json`;
    - `/home/max/site-control-kit/tools/telegram/session_runner/tool_manifest.json`;
  - факт:
    - отдельный `telegram-portable-session-tool` остался standalone-репозиторием, но теперь виден через `tools/telegram/session_runner/`;
    - встроенные `telegram_invite_manager`, `telegram_portable_helper`, `telegram_export` и visible wrapper `telegram_session_runner` собраны в `tools/telegram/`;
    - общая панель теперь видит все эти workflow как единый Telegram catalog;
    - панель уже умеет выбирать пользователя из списка portable-профилей и добавлять нового по `tdata.zip`;
    - после UI-refresh details больше не клиппятся в `Treeview` на текущем Linux окружении с `tk scaling ~= 2.0`, потому что панель переведена на text-card layout и tabbed intake forms.
- Для Telegram control center подтверждено живое автоматическое чередование `Совместного режима` через сам panel-layer:
  - исправлена логика callbacks `combined_contact_add_success` и `combined_session_success`, чтобы панель не останавливалась после первого batch, а сама запускала следующий session-cycle и затем следующий contact batch;
  - чистая transition-логика вынесена в helper-функции и покрыта unit-тестами;
  - live harness на actor `AK/@M_a_g_g_i_e` с двумя уже существующими контактами (`@abrikosovoevarenie`, `@abs11144`) и `limit=1` показал реальную последовательность:
    - `добавление контактов`;
    - `запуск сессии`;
    - `добавление контактов`;
    - `запуск сессии`;
  - финальный артефакт:
    - `/tmp/telegram-panel-alternating-live/result.json`;
  - по итогам smoke:
    - `combined_start_count = 4`;
    - `contact_snapshot.counts = {contact_added: 2}`;
    - `pending_total = 0`;
    - финальная фаза combined-state: `stopped`, `last_action = combined_session_finished`, `last_status = completed`.
- Дополнительно подтверждён живой `Совместный режим` уже на реальном файле `/home/max/контакты/1.txt` и реальной очереди `contact_add__AK__1`:
  - запускался через сам panel-layer на actor `AK/@M_a_g_g_i_e`;
  - сообщения были отключены (`0` сообщений за цикл), чтобы проверить только alternation `добавление -> сессия`;
  - batch-limit был выставлен в `1`, чтобы панель переходила между режимами после каждого username;
  - за один live smoke панель реально выполнила:
    - `добавление @aguilarchik -> session-cycle`;
    - `добавление @ahmaaad7777 -> session-cycle`;
  - оба contact-add execution record завершились как `contact_added_verified`:
    - `/home/max/telegram_invite_jobs/contact_add__AK__1/executions/20260503T160228Z-001-aguilarchik/execution_record.json`;
    - `/home/max/telegram_invite_jobs/contact_add__AK__1/executions/20260503T160333Z-001-ahmaaad7777/execution_record.json`;
  - job snapshot после smoke:
    - `contact_added: 27`;
    - `failed: 5`;
    - `new: 81`;
  - полный harness summary:
    - `/tmp/telegram-panel-real-combined-live/result.json`;
  - panel-log подтвердил именно чередование стартов:
    - `добавление`;
    - `запуск сессии`;
    - `добавление`;
    - `запуск сессии`;
  - после остановки smoke persisted combined-state был вручную нормализован в `stopped`, потому что headless harness нажал `Стоп` уже после старта следующего add-step и завершился быстрее, чем Tk успел переписать phase-state; живых процессов после этого не осталось.
- Следующим live smoke тот же `Совместный режим` был прогнан ещё раз на том же `1.txt` уже на трёх подряд alternating циклах без отправки сообщений:
  - `@ahmedovsssss -> session-cycle`;
  - `@ahtoxaveesp -> session-cycle`;
  - `@aidadovgan -> session-cycle`;
  - итоговый harness summary:
    - `/tmp/telegram-panel-real-combined-live-2/result.json`;
  - прирост состояния очереди за этот прогон:
    - было `contact_added: 27`, `new: 81`;
    - стало `contact_added: 30`, `new: 78`;
    - `failed` не вырос и остался `5`;
  - panel-log снова подтвердил pattern:
    - `добавление`;
    - `сессия`;
    - `добавление`;
    - `сессия`;
    - `добавление`;
    - `сессия`;
  - persisted combined-state после остановки снова был нормализован в `stopped`, чтобы панель не выглядела зависшей на `running`, хотя живых child-процессов уже не было.
- Отдельно подтверждён первый живой `Совместный режим` с реальной автоотправкой сообщения:
  - использовался тот же профиль `AK/@M_a_g_g_i_e`, та же очередь `contact_add__AK__1` и тот же файл `/home/max/контакты/1.txt`;
  - для safety-run были выставлены:
    - `limit=1` на contact batch;
    - `1` visit за session-cycle;
    - `1` сообщение за cycle;
    - общий message limit поднят ровно на один send (`messages_sent_total: 1 -> 2`);
  - фактический результат:
    - очередной contact-add шаг завершился успешно для `@aidar996`;
    - после него session-run `20260503T161534Z-a04741cd` реально отправил `1` сообщение;
    - адресат: `@M_a_x_i_m_M_i_k_h_a_i_l_o_v`;
    - текст: `Позвоню?`;
    - `messages_sent_total` вырос с `1` до `2`;
  - артефакты:
    - combined smoke summary: `/tmp/telegram-panel-real-combined-send-live/result.json`;
    - session run: `/home/max/telegram-portable-session-tool/runs/20260503T161534Z-a04741cd/run.json`;
    - contact add execution: `/home/max/telegram_invite_jobs/contact_add__AK__1/executions/20260503T161425Z-001-aidar996/execution_record.json`;
  - persisted combined-state после stop снова был нормализован в `stopped`, чтобы панель не оставалась в псевдо-`running` после headless harness stop.
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
2. Для Invite/Desktop: прогнать новый operator flow `Старт добавления -> Продолжить очередь -> Повторить ошибки` уже на панели, чтобы подтвердить не только backend batch, но и новый summary/retry UX end-to-end.
3. Для Telegram control center: прогнать оператором руками долгий `Совместный режим` уже через видимую панель с реальной отправкой сообщений, чтобы подтвердить не только alternating harness, но и пользовательский live UX.
4. Для Telegram control center: добавить быстрые кнопки `Открыть последний batch json`, `Открыть последний session run`, `Открыть последний screenshot`, если оператору станет тесно в текущем summary-режиме.
5. Для Telegram control center: вывести в явный UI-блок подсказку, что `Непрерывно до Стопа` отключает дальнейшее автоматическое чередование и удерживает панель в одном session-run.
6. Снизить runtime-затраты discovery относительно deep, чтобы multi-peer deep чаще успевал проходить следующий слой visible peer.
7. Поднять приоритеты deep-target'ов: раньше брать тех peer, у кого вероятность успешного `Mention` выше.
8. Разделить browser capability/runtime compatibility и Telegram export concerns в отдельные модули/слои.
9. Отделить понятие `best-known latest` от `most-recent run` в UI и документации, если пользователю важно видеть именно последний прогон как основной артефакт.
10. Декомпозировать `export_telegram_members_non_pii.py` на модули.

## Как Продолжать Следующему Агенту
1. Прочитать `AGENTS.md`.
2. Прочитать `docs/PROJECT_WORKFLOW_RU.md`.
3. Прочитать этот файл полностью.
4. Проверить `git status --short --branch` и `git log --oneline -n 15`.
5. Если задача относится к текущему Telegram control center, начать с `tools/telegram/NEXT_CHAT_AGENT_PROMPT_RU.md`.
6. Если задача про Telegram username, сначала открыть:
   - `latest_full.md`
   - `latest_safe.md`
   - последний `run.json`
   - последний `export.log`
   - `identity_history.json`
7. Только потом делать правки.
