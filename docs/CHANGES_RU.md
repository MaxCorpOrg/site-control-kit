# Перечень изменений (русская версия)

Дата фиксации состояния: **30 апреля 2026**.

Этот документ описывает, что именно реализовано в `site-control-kit`, какие проблемы закрыты и где находятся ключевые файлы.

## 0. Актуализация состояния на 27 апреля 2026

### 0.0 Progress panel + stop control для `tdata` history-scan (30 апреля 2026)
- Дополнительно починен resize UX:
  - длинные названия чатов больше не должны фиксировать окно на слишком большой ширине;
  - `scripts/telegram_members_export_gui.py` теперь явно держит окно `resizable`, верхний layout обёрнут в `Gtk.ScrolledWindow`, а длинные заголовки сжимаются через wrap/ellipsis;
  - live X11 verify подтвердил новый min-size окна: `46x46`.
- Обновлён `scripts/telegram_members_export_gui.py`:
  - добавлен отдельный блок прогресса сканирования в GTK GUI;
  - показываются счётчики `сообщений`, `@username`, elapsed time и `last update`;
  - добавлена кнопка `Остановить сбор`;
  - закрыт runtime-баг `AttributeError ... _is_tdata_target` в tdata callback после загрузки чатов;
  - `Выбрать .md файл` переведён на `Gtk.FileChooserDialog`;
  - ошибочный финальный статус `Сканирование истории завершено` после export-error заменён на отдельный error-state.
- Обновлён `scripts/telegram_tdata_helper.py`:
  - helper сразу пишет стартовый `PROGRESS ... messages=0 usernames=0 stage=start`;
  - по `SIGTERM` helper завершает текущий проход и отдаёт partial payload с `interrupted=1`.
- Обновлены defaults progress:
  - `scripts/telegram_members_export_gui.py` теперь по умолчанию запускает history-scan с `TELEGRAM_TDATA_PROGRESS_EVERY=250`;
  - `scripts/telegram_tdata_helper.py export-chat` тоже использует default `--progress-every 250`.
- Обновлён timeout contract:
  - `TELEGRAM_TDATA_EXPORT_TIMEOUT_SEC=0` теперь означает unlimited и это новый default для полного history-run;
  - timeout-ошибка теперь объясняет, что limit был именно настроен вручную.
- Практический эффект:
  - длинный history-scan больше не выглядит как немой freeze;
  - оператор может остановить scan без потери уже собранного partial результата.
- Зафиксировано новое правило repo-workflow:
  - задача внутри `site-control-kit` не считается завершённой без полного живого прохода изменённого user-facing сценария и устранения найденных ошибок по основному пути.
- Добавлен coverage:
  - `tests/test_telegram_tdata_helper.py`
  - `tests/test_telegram_members_export_gui.py`
- Проверено:
  - `python3 -m py_compile scripts/telegram_members_export_gui.py scripts/telegram_tdata_helper.py tests/test_telegram_members_export_gui.py tests/test_telegram_tdata_helper.py`
  - `PYTHONPATH=/home/max/site-control-kit python3 -m unittest tests.test_telegram_members_export_gui tests.test_telegram_tdata_helper -v`
  - live probes на `-1001753733827`:
    - backend cancel probe -> partial payload `history_messages_scanned=500`, `rows=35`, `interrupted=true`;
    - direct helper timeout probe -> partial payload `history_messages_scanned=600`, `42` usernames, `interrupted=true`.
  - live GTK smoke на `-1001753733827`:
    - загрузка `8` чатов через `tdata`;
    - stop после первого progress;
    - partial result `history_messages_scanned=300`, `usernames_found=30`, `safe_count=30`;
    - повторный smoke после фикса прошёл без traceback.
  - live chooser probe:
    - появился X11 dialog `Куда сохранить Telegram export` после вызова `_choose_output_file()`.

### 0.0 Централизация Telegram workspace + слоты 1..10 (29 апреля 2026)
- Добавлен `scripts/telegram_workspace_layout.py`:
  - единый корень: `~/.site-control-kit/telegram_workspace`;
  - автоматическое создание структуры:
    - `registry/users.json`,
    - `profiles/default`,
    - `cache/unpacked_profiles`,
    - `accounts/1..10/{profile,imports,keys}`.
- Обновлён `scripts/telegram_members_export_gui.sh`:
  - lock-файл от параллельного запуска GUI;
  - lazy browser start (браузер стартует только если нет готового bridge client);
  - автопрофили читаются из `accounts/*/profile` и `accounts/*/imports/*.zip`.
- Локальная миграция:
  - `/home/max/site-control-kit/TG_CONTACT` перенесён в `accounts/1/profile`.
- Добавлен coverage:
  - `tests/test_telegram_workspace_layout.py`.

### 0.0 User registry + dropdown users/chats (29 апреля 2026)
- Добавлен `scripts/telegram_user_registry.py`:
  - отдельное пространство для пользователей Telegram в `~/.site-control-kit/telegram_workspace/registry/users.json`;
  - хранит `name`, `profile` (папка или zip), `token`, `default_user`;
  - команды: `list`, `add`, `remove`, `set-default`, `resolve`.
- Пересобран `scripts/telegram_members_export_gui.sh`:
  - выбор пользователя из выпадающего списка;
  - добавление пользователя прямо из GUI;
  - выбор чата/группы из выпадающего списка открытых Telegram tabs выбранного пользователя;
  - fallback: если URL нет, можно ввести название (например `BigpharmaMarket`) и получить resolve по title.
- Добавлен coverage:
  - `tests/test_telegram_user_registry.py`.

### 0.0 Single-window GUI + поиск чата по названию (29 апреля 2026)
- `scripts/telegram_members_export_gui.sh` переписан в режим одного окна:
  - единая форма с полями: пользователь (profile dir/zip), чат/группа (URL или название), папка сохранения, имя файла;
  - убран каскад лишних операторских шагов (несколько списков account/client).
- Добавлен title-based resolve чата:
  - если в поле чата не URL, GUI ищет подходящий Telegram tab по `title` у выбранного пользователя (и затем по всем клиентам);
  - это закрывает кейс, когда в чате нет явного адреса и оператор знает только название (например `BigpharmaMarket`).
- Добавлен автоматический flow после `Start`:
  - поднимается браузер из выбранного профиля;
  - автоматически выбирается лучший `client_id`;
  - запускается `run_chat_export_once.sh` и затем `safe snapshot`.

### 0.1 GTK GUI + чат-лист из Telegram Web (29 апреля 2026)
- `scripts/telegram_members_export_gui.sh` и `scripts/telegram_members_export_app.sh` теперь запускают отдельное GTK-приложение `scripts/telegram_members_export_gui.py`.
- Новый GUI работает по фактическому операторскому сценарию:
  - выбор профиля только из реальных записей; пустые workspace slots больше не попадают в список пользователей;
  - список чатов/групп читается прямо из левой колонки Telegram Web и показывается в приложении;
  - итоговый `*.md` выбирается через системный `Save As` диалог, а не через ручной ввод пути;
  - перед экспортом выбранный чат принудительно открывается через `--force-navigate`, поэтому заранее искать/вставлять URL не нужно.
- Добавлен coverage:
  - `tests/test_telegram_members_export_gui.py`;
  - `tests/test_telegram_workspace_layout.py` расширен проверкой, что пустые профили скрываются.

### 0.2 GUI chat-list retry + online-only client selection (29 апреля 2026)
- Исправлен дефект, при котором GUI мог считать старый офлайн bridge-клиент «подключённым» и поэтому не показывал список чатов.
- Новый порядок:
  - для GUI принимаются только online Telegram clients;
  - после `Подключить Telegram` chat-list запускается автоматически;
  - загрузка списка чатов ждёт появления левой колонки Telegram Web и делает retry, если первый ответ пустой.
- Добавлен regression coverage:
  - `tests/test_telegram_members_export_gui.py` проверяет, что offline client игнорируется и пустой первый payload по чатам корректно ретраится.

### 0.3 Direct CDP fallback для branded Chrome (29 апреля 2026)
- Закрыт кейс, когда GUI писал «не удаётся подключить к телеграмму», потому что в выбранном `google-chrome` профиле не был установлен `Site Control Bridge`.
- Новый порядок работы GUI:
  - сначала по-прежнему пробуется старый bridge/hub path;
  - если живого bridge-client нет, GUI автоматически поднимает тот же browser profile с `--remote-debugging-port`;
  - новый helper `scripts/telegram_cdp_helper.js` читает список чатов, открывает выбранный чат и делает простой `cdp-simple` export напрямую через Chrome DevTools Protocol.
- Практический эффект:
  - branded `google-chrome` больше не является стоп-фактором для самого GUI-подключения;
  - оператору не нужно отдельно руками ставить unpacked extension только ради того, чтобы увидеть список чатов и запустить базовый сбор.
- Добавлен coverage:
  - `tests/test_telegram_members_export_gui.py` проверяет CDP chat-list path и merge `mentions -> synthetic rows`.
- Проверено:
  - `node --check scripts/telegram_cdp_helper.js`
  - `PYTHONPATH=/home/max/site-control-kit python3 -m unittest tests.test_telegram_members_export_gui tests.test_telegram_workspace_layout tests.test_telegram_export_parser tests.test_telegram_user_registry -v`
  - smoke: `telegram_cdp_helper.js status --port <temp-port>` на временном Chrome CDP browser -> OK

### 0.4 Telegram Desktop tdata backend для portable-сессий (29 апреля 2026)
- Закрыт кейс, когда GUI запускал Telegram Web и попадал в окно авторизации, хотя у пользователя уже была живая portable `tdata`-сессия.
- Новый порядок:
  - если в `accounts/<N>/profile` найден `tdata`/matching `tdata-*.zip`, GUI сначала использует backend `tdata-api`, а не browser profile;
  - новый helper `scripts/telegram_tdata_helper.py` запускается через `/home/max/telegram-api-collector/.venv/bin/python` и читает dialogs/usernames напрямую из Telegram Desktop session;
  - список чатов теперь может появляться вообще без Telegram Web и без bridge extension;
  - export path строит тот же `.md`, `*_usernames.*` и `safe snapshot`, но данные приходят из `participants + history`.
- Уточнение по live-path:
  - для текущего slot `1` рабочей оказалась не распакованная папка `accounts/1/profile/tdata-20260428T125500Z-3-001/tdata`, а импортированная session `~/telegram-api-collector/tdata_import/tdata`;
  - GUI теперь сверяет сигнатуру `tdata-*.zip` и предпочитает этот живой импорт вместо нерабочей локальной копии, чтобы не сваливаться обратно в окно авторизации.
- Дополнительный фикс live-зависания:
  - в `tdata`-режиме GUI больше не auto-launch'ит внешний `Telegram` на том же `tdata_import`, потому что этот запуск портил импортированную сессию для `opentele`;
  - кнопка открытия чата в `tdata`-режиме теперь не гоняет portable runtime, а сам export идёт напрямую через MTProto helper;
  - при ошибке export action log теперь пишет `run_failed ...`, чтобы не оставлять немой freeze.
- Дополнительный фикс полноты сбора:
  - `scripts/telegram_tdata_helper.py export-chat` получил режим `--source history`;
  - для history-сбора helper теперь:
    - читает авторов сообщений через `iter_messages`, а не через `participants`;
    - догружает sender через `get_entity(sender_id)`, если `msg.sender` пустой;
    - фильтрует bots и non-user sender'ов;
    - сохраняет только валидные `@username`, без строк без username.
  - GUI `tdata`-экспорт теперь использует именно `history-only` path и по умолчанию берёт `TELEGRAM_TDATA_HISTORY_LIMIT=0` (весь доступный history).
  - Live smoke на `BigpharmaMarket`:
    - helper `--source history --history-limit 5000` -> `34` уникальных `@username`;
    - GUI/backend smoke с `TELEGRAM_TDATA_HISTORY_LIMIT=5000` -> `safe_count=34`, markdown начинается с `Username из сообщений Telegram`.
- Дополнительный фикс длительного export-timeout:
  - GUI-wrapper больше не использует жёсткий `timeout=180` вокруг `telegram_tdata_helper.py export-chat`;
  - теперь helper запускается через `Popen`, stderr progress читается на лету и попадает в live-log окна;
  - новые env-параметры:
    - `TELEGRAM_TDATA_LIST_TIMEOUT_SEC` (`30` по умолчанию)
    - `TELEGRAM_TDATA_EXPORT_TIMEOUT_SEC` (`1800` по умолчанию)
    - `TELEGRAM_TDATA_PROGRESS_EVERY` (`250` по умолчанию)
  - live smoke на `-1001753733827` при `TELEGRAM_TDATA_HISTORY_LIMIT=5000` завершился успешно и показал рост usernames прямо по progress-строкам до `135`.
- Дополнительно:
  - GUI best-effort ищет portable binary вроде `~/Загрузки/Telegram Desktop/e/Telegram`;
  - если у binary нет execute-bit, GUI сам добавляет его и запускает Telegram с `-workdir <portable-data-root>`.
- Live проверка на текущем slot 1:
  - helper `list-chats` вернул `8` dialogs, включая `Чат BigpharmaMarket`;
  - helper `export-chat` по `-1001461811598` вернул usernames из `participants` и `history`;
  - backend smoke `_run_export_via_tdata()` собрал markdown на `43` rows и `34` safe usernames.
- Добавлен coverage:
  - `tests/test_telegram_members_export_gui.py` проверяет `normalize_tdata_chat_options()` и `resolve_tdata_dir()`.

### 0.5 History-only `@username` из окна сообщений для `tdata`-экспорта (29 апреля 2026)
- Продуктовый source-of-truth для portable `tdata` path переведён на авторов сообщений, а не на список участников.
- Обновлён `scripts/telegram_tdata_helper.py`:
  - добавлен `export-chat --source history`;
  - `msg.sender` при необходимости добирается через `get_entity(sender_id)`;
  - невалидные и числовые псевдо-username отсекаются;
  - bot/non-user sender'ы не попадают в итоговый набор;
  - добавлены progress-строки через `--progress-every`.
- Обновлён `scripts/telegram_members_export_gui.py`:
  - `tdata`-экспорт запускает helper именно как history-only path;
  - default `TELEGRAM_TDATA_HISTORY_LIMIT=0` означает весь доступный history.
- Обновлён `scripts/export_telegram_members_non_pii.py`:
  - markdown для этого режима теперь пишет `# Username из сообщений Telegram`.
- Live baseline:
  - `BigpharmaMarket` (`-1001461811598`) при `--history-limit 5000` -> `34` уникальных `@username`, включая `@EgorTuchkov`.
- Добавлен coverage:
  - `tests/test_telegram_tdata_helper.py`
  - `tests/test_telegram_members_export_gui.py`

### 0.6 Timeout/progress fix для длинного `tdata` history-export (29 апреля 2026)
- Закрыт live-дефект, когда GUI обрывал history-export ровно через `180s`.
- Новый порядок:
  - helper больше не запускается через `subprocess.run(... timeout=180)`;
  - используется `Popen` + streaming stderr, поэтому progress попадает в live-log GUI;
  - добавлены env-параметры:
    - `TELEGRAM_TDATA_LIST_TIMEOUT_SEC`
    - `TELEGRAM_TDATA_EXPORT_TIMEOUT_SEC`
    - `TELEGRAM_TDATA_PROGRESS_EVERY`
- Live verify:
  - чат `-1001753733827` при `TELEGRAM_TDATA_HISTORY_LIMIT=5000` завершился успешно;
  - progress вырос по шагам `1000 -> 53`, `2000 -> 75`, `3000 -> 101`, `4000 -> 123`, `5000 -> 135`;
  - итоговый `safe_count=135`.
- Проверено:
  - `PYTHONPATH=/home/max/site-control-kit python3 -m unittest tests.test_telegram_members_export_gui tests.test_telegram_tdata_helper -v`
  - `python3 -m py_compile scripts/telegram_tdata_helper.py scripts/telegram_members_export_gui.py scripts/export_telegram_members_non_pii.py`

### 0.0 GUI-поток под portable-пользователя и путь сохранения @username (29 апреля 2026)
- Пересобран `scripts/telegram_members_export_gui.sh` под операторский сценарий:
  - выбор пользователя: `default` профиль, папка portable-профиля или `.zip` portable-профиля;
  - `.zip` автоматически распаковывается в `~/.site-control-kit/telegram_workspace/cache/unpacked_profiles/*` и используется как `SITECTL_BROWSER_PROFILE`;
  - GUI сам пытается поднять Telegram-клиент из выбранного профиля и дождаться bridge client;
  - чат/группу можно выбрать из открытых Telegram tabs или ввести URL вручную;
  - путь сохранения задаётся как папка + basename, затем exporter пишет `*.md` и `*_usernames.txt/json` в эту папку.
- `scripts/telegram_members_export_app.sh` превращён в thin-wrapper, который запускает новый `telegram_members_export_gui.sh`.
- Проверено:
  - `bash -n scripts/telegram_members_export_gui.sh scripts/telegram_members_export_app.sh scripts/run_chat_export_once.sh`

### 0.0 Bot-фильтр в Telegram username sidecars (29 апреля 2026)
- Обновлён `scripts/export_telegram_members_non_pii.py`:
  - добавлен детектор bot-профилей по полям `username/status/role/name`;
  - deep username enrichment (chat/info/helper) теперь не запускается для bot-target;
  - итоговые sidecar `*_usernames.txt/json` по умолчанию исключают bot-username;
  - добавлен явный override: `--include-bots`.
- Добавлен coverage:
  - `tests/test_telegram_export_parser.py`:
    - bot-username отфильтровывается по умолчанию;
    - при `include_bots=True` bot-username возвращается;
    - parser default подтверждён: `include_bots=False`.
  - `tests/test_telegram_export_runtime.py`:
    - chat deep path не вызывает `_enrich_usernames_deep_chat` для bot-target.
- Проверено:
  - `python3 -m py_compile scripts/export_telegram_members_non_pii.py tests/test_telegram_export_parser.py tests/test_telegram_export_runtime.py`
  - `PYTHONPATH=/home/max/site-control-kit python3 -m unittest tests.test_telegram_export_parser tests.test_telegram_export_runtime tests.test_telegram_api_accounts tests.test_telegram_client_selection` -> `92 tests OK`
  - `PYTHONPATH=/home/max/site-control-kit python3 -m unittest discover -s tests -p 'test_*.py'` -> `169 tests OK`.

### 0.0 Multi-account GUI для Telegram экспорта (29 апреля 2026)
- Добавлен `scripts/telegram_api_accounts.py`:
  - хранение API-аккаунтов для Telegram export (`name`, `token`, optional `client_id`, `default_account`);
  - команды: `list`, `add`, `remove`, `set-default`, `resolve`;
  - registry path по умолчанию: `~/.site-control-kit/telegram_workspace/registry/api_accounts.json`.
- Пересобран `scripts/telegram_members_export_gui.sh`:
  - выбор token-источника (`auto` / saved API account);
  - добавление нового API-аккаунта из GUI (без правки shell/env вручную);
  - ручной/авто выбор `client_id` перед запуском;
  - запуск экспортёра с передачей выбранного `client_id`.
- Обновлён `scripts/run_chat_export_once.sh`:
  - добавлены optional overrides:
    - arg10 `client_id`
    - arg11 `tab_id`
  - добавлена валидация target client в `/api/clients`;
  - при наличии override runner передаёт `--client-id`/`--tab-id` в `export_telegram_members_non_pii.py`.
- Добавлен coverage:
  - `tests/test_telegram_api_accounts.py` (`3 tests OK`).
- Проверено:
  - `bash -n scripts/run_chat_export_once.sh scripts/telegram_members_export_gui.sh`
  - `python3 -m py_compile scripts/telegram_api_accounts.py`
  - `PYTHONPATH=/home/max/site-control-kit python3 -m unittest discover -s tests -p 'test_*.py'` -> `166 tests OK`.

### 0.0 Helper route source-of-truth probes (27 апреля 2026)
- В `scripts/export_telegram_members_non_pii.py` добавлены инструменты диагностики source-of-truth для helper-route после `navigate/activate`:
  - `_get_tab_meta_best_effort()` (stale `tab_url` + `tab title` из `/api/clients`);
  - `_trace_helper_route_probe()` (единый trace snapshot по `get_page_url`, stale tab meta и helper header identity).
- В trace добавлены новые стадии:
  - `helper-route-probe-prewait`
  - `helper-route-probe-soft`
  - `helper-route-probe-miss`
- В `tests/test_telegram_export_runtime.py` добавлены регрессии:
  - чтение `url/title` через `_get_tab_meta_best_effort()`;
  - no-op probe при выключенном `TELEGRAM_CHAT_MENTION_TRACE`;
  - корректный snapshot всех route-сигналов при включённом trace.
- Проверено:
  - `python3 -m py_compile scripts/export_telegram_members_non_pii.py tests/test_telegram_export_runtime.py`
  - `PYTHONPATH=/home/max/site-control-kit python3 -m unittest tests.test_telegram_export_runtime` -> `64 tests OK`
  - `PYTHONPATH=/home/max/site-control-kit python3 -m unittest discover -s tests -p 'test_*.py'` -> `163 tests OK`
- Текущий live факт:
  - probe-run `/tmp/tg_route_probe_live/chat_-1002465948544/runs/20260427T063636Z/run.json` упал на раннем `get_html` (`command_status=expired`);
  - по `/api/clients` оба Telegram bridge clients сейчас `online=false`, поэтому полный live helper-stage trace на новом probe пока не подтверждён.

### 0.1 Telegram helper soft-route fallback и новый live диагноз
- В `scripts/export_telegram_members_non_pii.py` добавлен `_soft_confirm_helper_target_route()`:
  - он даёт late soft-accept по helper-route только если нет conflicting header/title;
  - после `soft=1` helper делает короткий deadline-aware foreground kick;
  - numeric helper-route после `soft=1` больше не тратит budget на пустой `quick-url/page-url`, а оставляет его под header/profile path.
- Добавлен regression coverage в `tests/test_telegram_export_runtime.py`:
  - accept soft-route без header-conflict;
  - reject soft-route при conflicting header;
  - проход helper-read до profile path после soft-route confirm без URL polling.
- Проверено:
  - `python3 -m py_compile scripts/export_telegram_members_non_pii.py tests/test_telegram_export_runtime.py`
  - `PYTHONPATH=/home/max/site-control-kit python3 -m unittest tests.test_telegram_export_runtime` -> `61 tests OK`
  - `PYTHONPATH=/home/max/site-control-kit python3 -m unittest discover -s tests -p 'test_*.py'` -> `160 tests OK`
- Live verify:
  - `/tmp/tg_mention_probe_live_softroute/chat_-1002465948544/runs/20260426T081833Z/run.json`
  - `/tmp/tg_mention_probe_live_softroute/chat_-1002465948544/runs/20260426T081833Z/export.log`
  - `/tmp/tg_mention_probe_live_softroute/chat_-1002465948544/runs/20260426T081833Z/export_stats.json`
  - впервые в trace:
    - `helper-soft-route matched=1`
    - `helper-wait-identity matched=1 soft=1`
    - затем `helper-quick-url` и `helper-page-url`
- Новый диагноз после повторных fresh-run:
  - `/tmp/tg_mention_probe_live_softroute2/chat_-1002465948544/runs/20260426T082107Z/run.json`
  - `/tmp/tg_mention_probe_live_softroute3/chat_-1002465948544/runs/20260426T082310Z/run.json`
  - тот же sticky peer `972235006` и обычные helper peer уже снова дают `helper-soft-route matched=0`;
  - значит текущий blocker уже не в shell/session overhead, а в нестабильной materialization helper-route target на live Telegram DOM.

### 0.1 Hub command-state pruning и live re-verify Telegram export
- В `webcontrol/store.py` добавлен bounded pruning terminal command history:
  - persisted state теперь держит только последние `40` terminal command records;
  - pruning выполняется на startup и перед `dump_json`;
  - `queues` очищаются от orphan `command_id`, которые уже были вычищены из `commands`.
- Добавлен regression test в `tests/test_store.py`:
  - startup pruning старых terminal commands;
  - cleanup сиротских queue entries.
- Почему это понадобилось:
  - forced live probe на `client-601f3396-50aa-4989-ae5d-9c450e28f65e` после relaunch таба показал новый ранний fail `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T055744Z/run.json`;
  - лог обрывался на `force-navigate:start` с `Network error: timed out`;
  - фактический control-plane state был раздут:
    - `/home/max/.site-control-kit/state.json` = `88995936` байт;
    - `2286` terminal commands (`completed`, `failed`, `expired`);
  - старый hub в log уже показывал `POST /api/commands ... 200` и сразу `BrokenPipeError`, то есть клиент не дожидался записи ответа после тяжёлого state-save.
- После применения фикса и рестарта hub:
  - `/home/max/.site-control-kit/state.json` ужался до `1030707` байт;
  - persisted commands -> `40`;
  - direct helpers `_detect_current_dialog_url()`, `_is_dialog_surface_open()`, `_ensure_group_dialog_url()` на живом tab снова проходят.
- Новый live re-verify:
  - успешный run: `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T060315Z/run.json`
  - log: `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T060315Z/export.log`
  - stats: `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T060315Z/export_stats.json`
  - exporter дошёл до:
    - `force-navigate:done`
    - `chat-collect:done`
  - факты run:
    - `unique_members = 41`
    - `members_with_username = 14`
    - `history_backfilled_total = 14`
    - `deep_attempted_total = 5`
    - `deep_updated_total = 0`
    - `chat_runtime_limited = 1`
    - `discovery_new_visible = 41`
- Новый практический вывод:
  - ранний blocker на `POST /api/commands` снят;
  - текущий limit уже внутри helper-heavy `chat collect`, а не в hub timeout и не до `force-navigate:done`;
  - отдельный auxiliary mention pass теперь не первый stopper, потому что run завершает `chat collect` с `skip mention deep because chat runtime limit was reached`.
- Следующий throughput-фикс после этого:
  - `_wait_for_helper_target_identity()` теперь принимает стабильный numeric helper-route без лишнего ожидания header, но не принимает его при явном conflicting header;
  - `_poll_username_from_page_location()` больше не игнорирует короткий timeout budget;
  - chat-deep helper session вынесен на уровень всего `chat collect`, чтобы между step reuse шёл через `helper-navigate`, а не через новый `new_tab`.
- Проверено:
  - `python3 -m py_compile scripts/export_telegram_members_non_pii.py tests/test_telegram_export_runtime.py`
  - `PYTHONPATH=/home/max/site-control-kit python3 -m unittest tests.test_telegram_export_runtime` -> `52 tests OK`
  - `PYTHONPATH=/home/max/site-control-kit python3 -m unittest discover -s tests -p 'test_*.py'` -> `150 tests OK`
- Live re-verify:
  - `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T063418Z/run.json`
  - `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T063418Z/export.log`
  - `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T063418Z/export_stats.json`
  - в trace первый helper peer ещё делает `helper-open-tab`, а следующие peer уже идут через `helper-navigate` в тот же `tab_id=997920228`;
  - run дошёл до:
    - `unique_members = 42`
    - `deep_attempted_total = 7`
    - `chat_scroll_steps_done = 10`
    - `chat_runtime_limited = 1`
- Практический вывод:
  - throughput helper path действительно вырос;
  - лишний tab/page-url waste уже снят;
  - текущий limit всё ещё внутри helper-heavy `chat collect`, но теперь он уже ближе к реальному per-peer ceiling, а не к инфраструктурным или orchestration накладным расходам.
- Следующий шаг на 2026-04-26:
  - `scripts/export_telegram_members_non_pii.py` теперь открывает helper tab в фоне (`active=false`) и reuse path больше не делает лишний `activate_tab` перед каждым `navigate`;
  - отдельный `helper-wait-body` убран как лишний poll-round-trip;
  - sticky helper fallback теперь использует тот же `chat_helper_session`, что и обычный helper path.
- Новый regression coverage:
  - background helper tab;
  - reuse helper session без `activate_tab`;
  - conditional restore при закрытии helper session;
  - sticky helper fallback с общим helper session;
  - синхронизирован `tests/test_telegram_deep_helper.py`.
- Промежуточный live run, который вскрыл sticky leak:
  - `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T064323Z/run.json`
  - `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T064323Z/export_stats.json`
  - обычный helper reuse уже работал, но sticky helper ещё открывал новые tabs;
  - stats: `members_with_username = 11`, `deep_attempted_total = 8`, `sticky_helper_attempted = 3`.
- Финальный live re-verify этого шага:
  - `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T064626Z/run.json`
  - `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T064626Z/export.log`
  - `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T064626Z/export_stats.json`
  - trace подтвердил устойчивый helper reuse в одном `tab_id=997920238`;
  - `helper-wait-body` исчез из trace;
  - `helper-navigate` на reuse path опустился до `0.69..1.23s`.
- Проверено:
  - `python3 -m py_compile scripts/export_telegram_members_non_pii.py tests/test_telegram_export_runtime.py tests/test_telegram_deep_helper.py`
  - `PYTHONPATH=/home/max/site-control-kit python3 -m unittest tests.test_telegram_export_runtime` -> `55 tests OK`
  - `PYTHONPATH=/home/max/site-control-kit python3 -m unittest discover -s tests -p 'test_*.py'` -> `153 tests OK`
- Новый актуальный blocker:
  - repeated open-tab/foreground churn больше не главный limit;
  - текущий runtime blocker уже внутри `helper-wait-identity`, который держит около `2.0..2.5s` на zero-yield peer и режет ceiling до отдельного mention-pass.
- Следующий шаг на 2026-04-26:
  - `_wait_for_helper_target_identity()` теперь читает helper-route через direct `get_page_url` с fallback на stale hub `tab_url`;
  - добавлен `_read_dialog_fragment_best_effort()`;
  - helper identity может early reject после двух одинаковых non-target route;
  - `_get_page_url_best_effort()` исправлен и теперь поддерживает short timeout budget до `0.3s`.
- Новый regression coverage:
  - `test_wait_for_helper_target_identity_rejects_stable_non_target_route_after_two_polls`
  - `test_read_dialog_fragment_best_effort_prefers_page_location_over_stale_tab_url`
  - `test_get_page_url_best_effort_respects_short_timeout_budget`
- Диагностический live run:
  - `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T070235Z/run.json`
  - `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T070235Z/export_stats.json`
  - он временно ухудшил `helper-wait-identity` и помог локализовать hidden `1s` floor в `_get_page_url_best_effort()`.
- Финальный live re-verify после corrective fix:
  - `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T070607Z/run.json`
  - `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T070607Z/export.log`
  - `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T070607Z/export_stats.json`
  - `helper-wait-identity` avg вернулся к `2.243s` после регрессивных `2.987s` на diagnostic run;
  - run дал `41` members, `11` usernames, `7` deep attempts, `12` scroll steps.
- Проверено:
  - `python3 -m py_compile scripts/export_telegram_members_non_pii.py tests/test_telegram_export_runtime.py`
  - `PYTHONPATH=/home/max/site-control-kit python3 -m unittest tests.test_telegram_export_runtime` -> `58 tests OK`
  - `PYTHONPATH=/home/max/site-control-kit python3 -m unittest discover -s tests -p 'test_*.py'` -> `156 tests OK`
- Новый актуальный blocker после этого:
  - short-budget regression снят;
  - но `helper-wait-identity` по-прежнему остаётся главным zero-yield cost center, и лучший live результат по username всё ещё у run `20260426T060315Z`.
- Следующий шаг на 2026-04-26:
  - `_open_current_chat_user_info_and_read_username()` переприоритизирован под текущий Telegram Web:
    - сначала `.MiddleHeader .ChatInfo .fullName`
    - затем `.MiddleHeader .ChatInfo`
    - generic `.chat-info` path отодвинут ниже.
  - после `wait_selector` функция теперь валидирует, что `RIGHT_COLUMN_SELECTOR` действительно содержит profile content, а не пустой shell.
- Новый regression coverage:
  - `test_open_current_chat_user_info_prefers_current_telegram_header_selector`
  - `test_open_current_chat_user_info_skips_empty_right_column_shell`
- Manual live finding:
  - direct helper page на known-good peer `306536305` после ~`11s` и клика по `.MiddleHeader .ChatInfo(.fullName)` действительно раскрывает populated `User Info` с `@alxkat`;
  - прямой `_read_username_via_helper_tab()` всё ещё возвращает `—`, потому что обычно не доходит до этого stage.
- Full live re-verify:
  - `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T075023Z/run.json`
  - `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T075023Z/export.log`
  - `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T075023Z/export_stats.json`
  - run дал только `13` members / `5` usernames и `deep_updated_total = 0`, потому что helper peer снова остановились на `helper-wait-identity matched=0`.
- Проверено:
  - `python3 -m py_compile scripts/export_telegram_members_non_pii.py tests/test_telegram_deep_helper.py tests/test_telegram_export_runtime.py`
  - `PYTHONPATH=/home/max/site-control-kit python3 -m unittest tests.test_telegram_deep_helper tests.test_telegram_export_runtime` -> `66 tests OK`
  - `PYTHONPATH=/home/max/site-control-kit python3 -m unittest discover -s tests -p 'test_*.py'` -> `157 tests OK`
- Новый актуальный blocker после этого:
  - profile-open shell bug больше не главный;
  - но helper identity gate всё ещё не пускает exporter к исправленному profile-open path.

## 0.1 Актуализация состояния на 25 апреля 2026

### 0.1.0 Telegram discovery-aware chain
- `scripts/export_telegram_members_non_pii.py` получил persistent discovery state `version=2`:
  - `peer_states` хранят `attempt_count`, `success_count`, `failure_count`, `last_outcome`, `last_attempted_at`, `last_username`, `cooldown_until`;
  - blank peer после helper/mention fail ставится на cooldown;
  - sticky peer в cooldown больше не должен монопольно удерживать шаг.
- `scripts/telegram_contact_chain.py` теперь использует discovery progress как сигнал продуктивности run:
  - productive run считается не только по `new_usernames`, но и по `unique_members`, `members_with_username`, `discovery_new_visible` и productive deep-yield;
  - добавлен target `--target-members-with-username`;
  - `chain.json` теперь сохраняет реальные effective env текущего запуска.
- Live-подтверждение discovery accumulation:
  - `/home/max/site-control-kit/artifacts/telegram_exports/20260425_091528_chat_1002465948544_15.md`
  - `/home/max/site-control-kit/artifacts/telegram_exports/20260425_091937_chat_1002465948544_22.md`
  - `seen_peer_ids: 15 -> 23`
  - cooldown peers после пары run: `5364308868`, `7965869498`
- Live-подтверждение нового chain поведения:
  - `/home/max/telegram_contact_batches/chat_-1002465948544/chains/20260425T052627Z/chain.json`
  - run1 `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260425T052627Z/run.json` -> `18` unique members, `9` members_with_username, `discovery_new_visible=18`
  - run2 `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260425T052959Z/run.json` -> `23` unique members, `8` members_with_username, `discovery_new_visible=9`
  - chain с `--stop-after-idle 1` не остановился преждевременно и завершил оба run, потому что discovery/coverage ещё росли
  - суммарный live итог chain: `discovery_progress_runs=2`, `discovery_new_visible_total=27`, `best_unique_members=23`
- Chat-dir state после этого:
  - `/home/max/telegram_contact_batches/chat_-1002465948544/discovery_state.json`
  - `seen_peer_ids=27`
  - cooldown peers: `966384255`, `6964266260`
  - новые numbered batch файлы: `8.txt`, `9.txt`
  - суммарно numbered batches теперь дают `16` уникальных username.
- Проверено:
  - `python3 -m py_compile scripts/telegram_contact_chain.py scripts/export_telegram_members_non_pii.py`
  - `PYTHONPATH=/home/max/site-control-kit python3 -m unittest tests/test_telegram_contact_chain.py` -> `16 tests OK`
  - `PYTHONPATH=/home/max/site-control-kit python3 -m unittest discover -s tests -p 'test_*.py'` -> `125 tests OK`
- Следующий live-фикс после этого:
  - `deep` run `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260425T062608Z/run.json` показал repeated-view waste: `8` шагов, те же `15` peer, `discovery_new_visible=0`, `deep_attempted_total=0`, runtime дожигался до лимита;
  - `scripts/export_telegram_members_non_pii.py` теперь имеет ранний stop-path для repeated identical discovery view, независимый от `minimum_steps`;
  - `chat_stats` теперь всегда содержат `revisited_view_steps`, `burst_scrolls_done`, `jump_scrolls_done`.
- Live re-verify после патча:
  - chain: `/home/max/telegram_contact_batches/chat_-1002465948544/chains/20260425T063414Z/chain.json`
  - run1 `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260425T063414Z/run.json`
  - run2 `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260425T063708Z/run.json`
  - оба run остановились раньше с:
    - `chat_scroll_steps_done=3`
    - `chat_revisited_view_steps=3`
    - `chat_runtime_limited=0`
    - `deep_attempted_total=2`
    - `deep_updated_total=0`
  - chain завершился `stopped_on_no_growth`, а не длинным пустым дожигом.
- Практический смысл:
  - scroll-loop больше не главный источник waste;
  - следующий bottleneck уже был переведён в zero-yield `mention deep`, который нужно cooldown-ить или deprioritize после repeated-view stop.
- Следующий фикс после repeated-view stop:
  - `_normalize_username_from_mention_input()` теперь принимает raw mention candidate без `@`, потому что `_extract_chat_mention_usernames()` именно так и возвращает данные;
  - `discovery_state.json` теперь хранит `mention_candidate_states` с cooldown для zero-yield mention-кандидатов;
  - `_enrich_chat_usernames_via_mentions()` пишет success/failure и в `peer_states`, и в `mention_candidate_states`.
- Live verify:
  - chain `/home/max/telegram_contact_batches/chat_-1002465948544/chains/20260425T070126Z/chain.json`
  - run1 `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260425T070126Z/run.json` -> `deep_attempted_total=2`, `deep_updated_total=0`
  - run2 `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260425T070502Z/run.json` -> `deep_attempted_total=0`, `deep_updated_total=0`
  - `discovery_state.json` получил cooldown-кандидаты `@plaguezonebot` и `@oleghellmode` с `mention_peer_unknown`
  - архивы:
    - `/home/max/site-control-kit/artifacts/telegram_exports/20260425_110501_chat_1002465948544_15.md`
    - `/home/max/site-control-kit/artifacts/telegram_exports/20260425_110714_chat_1002465948544_15.md`
- Проверено:
  - `python3 -m py_compile scripts/export_telegram_members_non_pii.py`
  - `PYTHONPATH=/home/max/site-control-kit python3 -m unittest tests.test_telegram_export_parser tests.test_telegram_export_runtime` -> `50 tests OK`
  - `PYTHONPATH=/home/max/site-control-kit python3 -m unittest discover -s tests -p 'test_*.py'` -> `129 tests OK`
- Следующий шаг после этого:
  - mention URL-pass теперь читает identity через waited opened identity fallback (`peer_id` + title), а не только через один `body` regex;
  - добавлен safe unique title-match fallback, если `peer_id` у opened profile не прочитался;
  - extra mention-pass переведён на best-effort `get_html`, candidate cap через `TELEGRAM_CHAT_MENTION_DEEP_MAX_PER_STEP`, runtime budget и короткие timeouts внутри auxiliary path.
- Проверено:
  - `PYTHONPATH=/home/max/site-control-kit python3 -m unittest tests.test_telegram_export_runtime tests.test_telegram_export_parser` -> `56 tests OK`
  - `PYTHONPATH=/home/max/site-control-kit python3 -m unittest discover -s tests -p 'test_*.py'` -> `135 tests OK`
- Live status пока частичный:
  - temp probe `/tmp/tg_mention_probe_root/chat_-1002465948544/runs/20260425T082329Z/run.json` остался `partial`;
  - `export.log` на нём дошёл только до repeated-view stop и history backfill;
  - значит следующий реальный blocker остаётся внутри первого auxiliary mention-pass на live DOM, а не в parser/runtime/test слое.

## 0.2 Актуализация состояния на 24 апреля 2026

### 0.2.0 Telegram sticky-author path
- После фикса попадания по sticky icon добавлен sticky helper fallback:
  - если `telegram_sticky_author context_click=true` открыл menu, но `Mention` отсутствует, exporter пробует helper-tab для того же sticky `peer_id`;
  - stats получили `sticky_helper_attempted` и `sticky_helper_updated`;
  - best-effort command missing-result grace сокращён до 0.4..1.2s, чтобы helper не зависал на selector miss до 90s.
- Live-подтверждение:
  - `/tmp/telegram_live_sticky_helper.md`: `306536305 -> @alxkat`
  - `/tmp/telegram_live_sticky_helper_fastgrace.md`: `1127139638 -> @Mitiacaramba`
- Combined deliverable:
  - `/tmp/telegram_combined_54_usernames.txt`
  - `/tmp/telegram_combined_54_usernames.json`
  - `/home/max/site-control-kit/artifacts/telegram_exports/20260424_164916_combined-usernames_1002465948544_54.txt`
  - `/home/max/site-control-kit/artifacts/telegram_exports/20260424_164916_combined-usernames_1002465948544_54.json`
  - count: `54` уникальных `@username` из текущих member/chat-mentions/batch источников.
- `extension/content.js` получил команду `telegram_sticky_author`.
- Команда ищет нижнюю прилипшую иконку автора Telegram Web через `elementsFromPoint`.
- Для `context_click=true` используется только большая avatar под нижней point-пробой; fallback на текст сообщения/reply-avatar для правого клика запрещён.
- `scripts/export_telegram_members_non_pii.py` сначала пробует sticky-author mention для текущего прилипшего автора и ограничивает deep этим peer, если sticky-author найден.
- Добавлены stats:
  - `sticky_authors_seen`
  - `sticky_mention_attempted`
  - `sticky_mention_updated`
- Live probe на текущем чате после extension `0.1.5`:
  - `peer_id=8055002493`
  - `source=point`
  - `point={x:512,y:539}`
  - `rect=506,535,540,569`, `34x34`
  - `context_clicked=true`
  - `Mention` в открытом Telegram menu не найден: `menu_missing`.
- Live wrapper smoke:
  - output: `/tmp/telegram_live_sticky_icon.md`
  - archive: `/home/max/site-control-kit/artifacts/telegram_exports/20260424_143524_chat_1002465948544_18.md`
  - результат: `18` members, `10` usernames
  - sticky path дошёл до menu-path, но Telegram вернул `menu_missing`.
- Проверено:
  - `node --check extension/content.js && node --check extension/background.js`
  - `python3 -m unittest discover -s tests -p 'test_*.py'` -> `117 tests OK`

### 0.2.1 Telegram history/parser/helper correctness
- `scripts/export_telegram_members_non_pii.py` теперь предпочитает более свежий archive `identity_history` перед устаревшим явным `CHAT_IDENTITY_HISTORY`, а из старого файла добирает только отсутствующие non-conflicting записи.
- `_parse_chat_members()` больше не может подхватить `@username` из текста сообщения: username ищется только в author/header block.
- Helper-tab больше не должен присваивать stale username от чужого профиля:
  - перед чтением username helper ждёт подтверждение ожидаемого `peer_id` или имени;
  - live ложный кейс `6964266260 (Evgeniy) -> @Tri87true` перестал воспроизводиться.
- Live verify:
  - `/tmp/telegram_live_verify.md` -> `14` members, `8` usernames;
  - `/tmp/telegram_live_verify_2.md` -> `20` members, `8` usernames;
  - archive: `/home/max/site-control-kit/artifacts/telegram_exports/20260424_171947_chat_1002465948544_20.md`
  - `output_usernames_cleared_total = 0`
- Chat-dir state подтверждённо обновлён:
  - `/home/max/telegram_contact_batches/chat_-1002465948544/identity_history.json`
  - `@super_pavlik -> 1621138520`
  - `@alxkat -> 306536305`
  - `@mitiacaramba -> 1127139638`

### 0.2.2 Telegram pre-deep history backfill
- `scripts/export_telegram_members_non_pii.py` теперь применяет history backfill до deep-обхода видимых участников чата.
- Это экономит helper/deep runtime: уже известные `peer_id` не попадают в `deep_targets`, если username можно восстановить из `identity_history.json`.
- Добавлены stats:
  - `history_prefilled`
  - `history_prefill_conflicts`
- Добавлен regression test: известный `peer_id` получает username из history, а `_enrich_usernames_deep_chat()` не вызывается.
- Проверено:
  - короткий runtime/helper набор: `27 tests OK`;
  - полный Telegram-related набор: `77 tests OK`.
- Live smoke:
  - чат: `https://web.telegram.org/a/#-1002465948544`
  - output: `/tmp/telegram_live_after_prefill.md`
  - archive: `/home/max/site-control-kit/artifacts/telegram_exports/20260424_132543_chat_1002465948544_22.md`
  - результат: `22` members, `9` usernames, `9` username восстановлены pre-deep из history.

## 0.3 Актуализация состояния на 23 апреля 2026

### 0.3.1 Telegram export зафиксирован живым run
Подтверждён рабочий end-to-end контур на:
- `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T173223Z/run.json`
- `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T173223Z/export.log`
- `/home/max/telegram_contact_batches/chat_-1002465948544/runs/20260423T173223Z/export_stats.json`

Факты:
- `unique_members = 27`
- `members_with_username = 10`
- `safe_count = 10`
- `new_usernames = 2`
- `latest_full.*` и `latest_safe.*` promoted на этот run

Новые numbered batch usernames:
- `@oleg_klsnkv`
- `@andreu_bogatchenko`

### 0.3.2 Telegram mention-path теперь честнее
- Если Telegram Web отвечает `No visible menu item found by text`, exporter больше не тратит шаг на пустые retry и сразу уходит в helper fallback.
- Это отражает текущее реальное состояние Telegram UI: `Mention` часто отсутствует в доступном context menu.

### 0.3.3 Numeric `@username` артефакты закрыты
- Ложные значения вида `@1291639730` больше не должны попадать в новые Telegram outputs.
- Фильтр добавлен и в exporter, и в history-loader, и в safe/batch helper.
- Active файлы `latest_safe.*`, `latest_full.*`, `identity_history.json` и numbered batches приведены к этому правилу.

## 1. Что создано с нуля

### 1.1 Локальный хаб управления (Python)
Реализован локальный HTTP-сервер, который принимает команды, раздаёт их клиентам-расширениям и сохраняет результаты.

Файлы:
- `webcontrol/server.py` — HTTP API (`/health`, `/api/clients/*`, `/api/commands/*`).
- `webcontrol/store.py` — in-memory + persistence (`state.json`), очередь команд, статусы.
- `webcontrol/config.py` — конфигурация хаба.
- `webcontrol/utils.py` — утилиты сериализации.

### 1.2 CLI для оператора
Реализован CLI для ручного и скриптового управления.

Файлы:
- `webcontrol/cli.py` — команды `serve`, `health`, `clients`, `state`, `send`, `wait`, `cancel`.
- `webcontrol/__main__.py` — запуск через `python3 -m webcontrol`.
- `pyproject.toml` — установка команды `sitectl`.

### 1.3 Расширение браузера (MV3)
Создано расширение-мост между реальными вкладками и локальным хабом.

Файлы:
- `extension/manifest.json` — разрешения и точки входа MV3.
- `extension/background.js` — heartbeat, polling, получение/выполнение команд, отправка результатов.
- `extension/content.js` — DOM-команды (`click`, `fill`, `wait_selector`, `extract_text`, `get_html`, `scroll`, `get_attribute`, `run_script`).
- `extension/options.*` — настройка URL хаба, токена и интервалов.
- `extension/popup.*` — диагностика клиента в 1 клик.

### 1.4 Скрипты эксплуатации
Файлы:
- `scripts/start_hub.sh` — запуск хаба с переменными окружения.
- `scripts/package_extension.sh` — упаковка расширения в zip.
- `scripts/export_feishu_bundle.py` — экспорт Feishu-страниц в Markdown (сырой + RU).

## 2. Что доработано для удобства

### 2.1 Быстрый локальный режим без ручной генерации токена
Добавлен единый токен по умолчанию:
- `local-bridge-quickstart-2026`

Поведение:
- Если `SITECTL_TOKEN` не задан, `start_hub.sh` запускает хаб в quickstart-режиме.
- CLI и расширение также имеют fallback на этот токен.
- Для production/сети рекомендуется обязательно переопределять токен.

### 2.2 Русификация пользовательской части расширения
Сделаны русские подписи в popup/options для более удобной эксплуатации:
- статус heartbeat/poll,
- кнопки диагностики,
- статусы сохранения настроек.

### 2.3 Документация для пользователя и ИИ
Подготовлен комплект русской документации по архитектуре, API, безопасности и сопровождению.

## 3. Протокол и команды

Поддерживаемые типы команд:
- `navigate`
- `click`
- `fill`
- `wait_selector`
- `extract_text`
- `get_html`
- `get_attribute`
- `scroll`
- `screenshot`
- `run_script`

Особенности:
- Команды ставятся в очередь и назначаются целевым клиентам (`client_id`).
- Каждый результат возвращается в хаб с финальным статусом (`completed/failed/canceled/expired`).
- История сохраняется в `~/.site-control-kit/state.json`.

## 4. Безопасность

Реализовано:
- проверка токена на всех `/api/*` endpoint;
- поддержка `X-Access-Token` и `Authorization: Bearer ...`;
- базовые рекомендации по изоляции хаба на `127.0.0.1`.

Ограничения:
- `run_script` может падать на сайтах со строгим CSP (запрет `unsafe-eval`). Это ожидаемое поведение браузера.

## 5. Тесты и примеры

Добавлено:
- `tests/test_store.py` — проверка ключевой логики очереди/статусов.
- `examples/*.json` — готовые примеры payload-команд.

## 6. Экспорт контента в Markdown

Подготовлен сценарий выгрузки контента страниц Feishu в локальные `.md`:
- сырой слой (raw),
- русский слой (RU),
- пакетный bundle-экспорт по ссылкам.

Это позволяет переносить знания сайта в локальную документационную базу.

## 7. Что важно при дальнейшем развитии

1. Не ломать API-контракт без миграции и обновления `docs/API.md`.
2. Не ослаблять auth-проверки токена.
3. При расширении типов команд сразу обновлять:
- `docs/API.md`,
- `docs/EXTENSION.md`,
- `examples/`.
4. Держать поведение deterministic для `state.json`.
