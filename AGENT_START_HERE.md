# Agent Start Here

Этот файл обязателен для любого агента, который заходит в `/home/max/site-control-kit`.
Перед любыми командами, правками, live-run или git-действиями сначала читать этот файл, потом `CODEX_STATE.md`, потом `docs/agent_handoff_ru/00_START_HERE.md`.

После завершения любой задачи агент обязан вернуться сюда и в связанные handoff-файлы, чтобы оставить короткие заметки:
- что сделал;
- что проверил;
- где лежат важные файлы/артефакты;
- что осталось;
- какой следующий шаг.

Дополнительное правило для этого проекта:
- задача не считается выполненной, пока агент не довёл изменённый сценарий до реально рабочего состояния;
- для GUI/Telegram/operator flow агент обязан проходить весь живой цикл вместе с программой, фиксировать и устранять найденные баги/ошибки/неверные шаги по ходу прохода, а не останавливаться на уровне "код уже написан".

## Куда Смотреть Сразу
1. `AGENT_START_HERE.md`
2. `CODEX_STATE.md`
3. `docs/agent_handoff_ru/00_START_HERE.md`
4. `docs/PROJECT_STATUS_RU.md`
5. `docs/agent_handoff_ru/08_KNOWN_ISSUES_AND_LIVE_FINDINGS.md`
6. `docs/agent_handoff_ru/09_CURRENT_BACKLOG_AND_NEXT_STEPS.md`

## Что Это За Ветка
- Репозиторий: `site-control-kit`
- Ветка: `main`
- Активная тема: Telegram export path
- Цель не менялась: собирать именно peer-bound Telegram `@username` и двигаться к `100`

## Где Мы Закончили Работу
- На 2026-04-30 закрыт новый GUI-регресс по окну:
  - длинные названия чатов раздували минимальную ширину GTK-окна;
  - из-за этого окно переставало нормально уменьшаться и хуже прилипало к краям экрана;
  - fix: окно теперь явно `resizable`, а длинные chat-title / selected-title строки ужимаются через wrap/ellipsis вместо раздувания всей ширины;
  - live X11 verify: `WM_NORMAL_HINTS` теперь показывает `program specified minimum size: 46 by 46`, а не прежний большой принудительный минимум.
- На 2026-04-30 закрыт следующий UX-gap в `tdata-history-authors` path:
  - GTK GUI получил отдельный блок прогресса сканирования;
  - в блоке видно `сколько сообщений просмотрено`, `сколько @username найдено`, `сколько времени идёт скан`, `когда было последнее обновление`;
  - в long-run теперь есть явная кнопка `Остановить сбор`.
  - базовая частота progress уменьшена до `250` сообщений, чтобы оператор видел движение счётчиков заметно раньше.
- На 2026-04-30 закрыт следующий product-gap в full history path:
  - для полного history-run больше нет дефолтного export-timeout;
  - `TELEGRAM_TDATA_EXPORT_TIMEOUT_SEC=0` теперь означает unlimited и это новый default;
  - если оператор вручную задаёт timeout, GUI теперь пишет про "настроенный лимит", а не про якобы встроенный предел истории.
- На 2026-04-30 закрыт новый runtime-баг в GTK GUI:
  - во время живого smoke `tdata`-ветка падала в callback `AttributeError: 'TelegramMembersExportWindow' object has no attribute '_is_tdata_target'`;
  - fix: window больше не зовёт несуществующий helper у себя и проверяет `tdata`-target через backend.
- На 2026-04-30 закрыт UX-баг по сохранению результата:
  - `Выбрать .md файл` переведён с `Gtk.FileChooserNative` на более стабильный `Gtk.FileChooserDialog`;
  - живой X11 probe подтвердил появление окна `Куда сохранить Telegram export`;
  - кнопка `Открыть папку результата` теперь сначала создаёт каталог, если его ещё нет.
- На 2026-04-30 `scripts/telegram_tdata_helper.py` усилен для stop/resume UX:
  - helper теперь сразу пишет стартовый `PROGRESS ... messages=0 usernames=0 stage=start`, а не молчит до первой тысячи сообщений;
  - по `SIGTERM` helper пытается завершить текущий проход и вернуть частичный JSON payload вместо немого обрыва;
  - GUI/backend path сохраняет частичный `.md`/`*_usernames.*`, если остановка была штатной.
- На 2026-04-29 добавлен `users registry` слой:
  - `scripts/telegram_user_registry.py`;
  - рабочий registry path: `~/.site-control-kit/telegram_users/registry.json`.
- GUI теперь умеет выпадающий список пользователей и выпадающий список чатов выбранного пользователя;
- если URL чата нет, GUI принимает название и резолвит по tab title.
- Пользователи теперь не только ручные:
  - в GUI всегда есть `auto-default`;
  - и есть автоподгрузка профилей из `~/.site-control-kit/telegram_users/profiles` + выбор из registry.
- На 2026-04-29 GUI упрощён до single-window режима:
  - один мастер-экран с 4 полями (пользователь, чат/группа, папка сохранения, имя файла);
  - чат можно вводить названием (без URL), GUI ищет его по Telegram tab title.
- На 2026-04-29 GUI-поток теперь операторский:
  - сначала выбор пользователя (`default`/portable папка/portable `.zip`);
  - затем выбор чата/группы;
  - затем выбор папки и имени набора для `*.md` + `*_usernames.txt/json`.
- `scripts/telegram_members_export_app.sh` больше не отдельный legacy-flow, а wrapper на `scripts/telegram_members_export_gui.sh`.
- На 2026-04-29 закрыт bot-filter для username-output:
  - deep path не запускается для bot-target;
  - sidecar usernames по умолчанию excludes bots (`--include-bots` как override).
- Базовый ранний blocker в hub control-plane уже снят.
- Повторный helper tab/session churn уже снят.
- Пустой `RightColumn` shell больше не главный blocker.
- Последний code-level шаг уже закрыт:
  - source-of-truth probe для helper-route после `navigate/activate` уже добавлен в exporter trace;
  - probe пишет `get_page_url` fragment, stale `tab_url/title`, helper header identity и `route_match/header_match`;
  - regression-слой на этом шаге зелёный (`64 runtime tests`, `163 total tests`).
- Последний точный live blocker:
  - live Telegram DOM нестабильно materialize-ит target helper-route;
  - плюс на 2026-04-27 bridge clients в `/api/clients` были `online=false`, поэтому новый probe-run упал до helper-stage.

## Последние Важные Артефакты
- Лучший live ceiling по username пока здесь:
  - `/tmp/tg_mention_probe_live/chat_-1002465948544/runs/20260426T060315Z/run.json`
- Первый isolated run, где helper реально прошёл дальше identity gate:
  - `/tmp/tg_mention_probe_live_softroute/chat_-1002465948544/runs/20260426T081833Z/run.json`
  - `/tmp/tg_mention_probe_live_softroute/chat_-1002465948544/runs/20260426T081833Z/export.log`
  - `/tmp/tg_mention_probe_live_softroute/chat_-1002465948544/runs/20260426T081833Z/export_stats.json`
- Два свежих run, которые подтвердили текущий blocker:
  - `/tmp/tg_mention_probe_live_softroute2/chat_-1002465948544/runs/20260426T082107Z/run.json`
  - `/tmp/tg_mention_probe_live_softroute3/chat_-1002465948544/runs/20260426T082310Z/run.json`
- Новый probe-run на 2026-04-27:
  - `/tmp/tg_route_probe_live/chat_-1002465948544/runs/20260427T063636Z/run.json`
  - `/tmp/tg_route_probe_live/chat_-1002465948544/runs/20260427T063636Z/export.log`
  - `/tmp/tg_route_probe_live/chat_-1002465948544/runs/20260427T063636Z/export_stats.json`
  - статус: `failed` (`get_html ... expired`) до helper-stage.
- Новый GTK smoke-run на 2026-04-30:
  - `/tmp/telegram_gui_smoke_export.md`
  - `/tmp/telegram_gui_smoke_export_usernames.txt`
  - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260430T094917Z.log`
  - итог: `-1001753733827`, `8` чатов загружено, stop после первого progress, partial result `history_messages_scanned=300`, `@username=30`, `safe_count=30`.
- Новый save-dialog probe на 2026-04-30:
  - отдельное X11 окно `Куда сохранить Telegram export` появилось после вызова `_choose_output_file()`;
  - chooser-path сейчас доходит до реального видимого окна, а не падает до показа.

## Что Именно Менялось В Последнем Цикле
- `scripts/telegram_members_export_gui.py`
  - починен resize-UX GTK-окна: длинные chat titles больше не должны блокировать уменьшение окна;
  - selected chat title теперь wrap/ellipsis, list rows больше не держат окно слишком широким.
- `AGENTS.md`
  - добавлено явное правило закрытия задач: для user-facing flow задача не считается завершённой без полного живого прохода и отладки процесса до конца.
- `scripts/telegram_tdata_helper.py`
  - добавлены немедленный стартовый `PROGRESS` и graceful interrupt path;
  - при остановке helper возвращает partial payload с `interrupted=1`, `history_messages_scanned` и уже найденными `@username`.
- `scripts/telegram_members_export_gui.py`
  - добавлен графический блок прогресса для `tdata` history-scan;
  - GUI теперь парсит `PROGRESS ...` линии в отдельные счётчики, пульсирующий progress bar и stop-button flow;
  - при штатной остановке GUI показывает `частичный экспорт сохранён`, а не только ошибку.
- `tests/test_telegram_tdata_helper.py`
  - добавлена регрессия на partial result при stop-request.
- `tests/test_telegram_members_export_gui.py`
  - добавлены регрессии на parsing progress line, cancel path для helper subprocess, tdata chat-load callback без runtime traceback, unlimited export-timeout default и error-state progress panel.
- `scripts/telegram_tdata_helper.py`
  - helper переведён на product-path `history-only` для Telegram Desktop `tdata`;
  - добавлены `--source history`, `--progress-every`, bot-filter и resolve sender через `get_entity(sender_id)`;
  - итог: сбор идёт по авторам сообщений, а не по `participants`.
- `scripts/telegram_members_export_gui.py`
  - GTK GUI теперь использует `tdata-history-authors` как основной путь для portable/logged-in desktop session;
  - в `tdata`-режиме больше нет auto-launch внешнего `Telegram`, который портил импортированную session;
  - wrapper больше не рвёт длинный export по жёсткому `180s`, а стримит `PROGRESS ...` из helper в live-log.
- `scripts/export_telegram_members_non_pii.py`
  - markdown для этого режима переименован под history-only output: `Username из сообщений Telegram`.
- `tests/test_telegram_tdata_helper.py`
  - добавлены регрессии на history-only path, sender resolve и отсеивание bot/non-user sender'ов.
- `tests/test_telegram_members_export_gui.py`
  - добавлены регрессии на выбор рабочего `tdata`, отказ от portable auto-launch и стриминг progress/timeout.
- `CODEX_STATE.md`
  - сохранён новый checkpoint по `tdata-history-authors`, live-baseline и следующему действию.
- `docs/PROJECT_STATUS_RU.md`
  - сохранён новый операторский baseline для GTK GUI + `tdata` history-only path.
- `docs/CHANGES_RU.md`
  - добавлена запись о `tdata` history-only сборе и timeout/progress фиксе.
- `docs/agent_handoff_ru/00_START_HERE.md`
  - обновлена точка входа новым операторским порядком для GUI и текущим resume path.
- `docs/agent_handoff_ru/08_KNOWN_ISSUES_AND_LIVE_FINDINGS.md`
  - добавлены свежие live-факты по `BigpharmaMarket` и `-1001753733827`.
- `docs/agent_handoff_ru/09_CURRENT_BACKLOG_AND_NEXT_STEPS.md`
  - зафиксирован следующий practical шаг для полного history-run и UX progress.

## С Чего Начинать Следующему Агенту
1. Прочитать этот файл.
2. Прочитать `CODEX_STATE.md`.
3. Проверить `git status --short --branch`.
4. Не делать `git reset` / `git checkout` в грязном дереве без прямого запроса.
5. Если работа продолжается по Telegram export, держаться только этого path.
6. Если меняется поведение, синхронно обновлять:
   - `CODEX_STATE.md`
   - `docs/PROJECT_STATUS_RU.md`
   - `docs/CHANGES_RU.md`
   - `docs/agent_handoff_ru/00_START_HERE.md`
   - `docs/agent_handoff_ru/08_KNOWN_ISSUES_AND_LIVE_FINDINGS.md`
   - `docs/agent_handoff_ru/09_CURRENT_BACKLOG_AND_NEXT_STEPS.md`
7. После каждой завершённой задачи оставить handoff-заметку:
   - что сделано;
   - что проверено;
   - что осталось;
   - что делать следующим шагом.

## Следующий Узкий Шаг
- Для текущего пользовательского сценария сначала держаться `tdata-history-authors`, а не старого bridge/helper path.
- Следующий практический шаг:
  - прогонять целевой чат полным history-run (`TELEGRAM_TDATA_HISTORY_LIMIT=0`) через GTK GUI или helper;
  - вместе с пользователем проверить, устраивает ли operator UX: частота progress, читаемость partial-result и обычный drag/snap окна мышью;
  - если пользователю всё ещё мало частоты обновлений даже после нового default `250`, отдельно подбирать `TELEGRAM_TDATA_PROGRESS_EVERY` без возврата к старому route-probe расследованию;
  - если пользователь видит "зависло", проверять наличие `PROGRESS ...` в логе GUI и при необходимости поднимать только `TELEGRAM_TDATA_EXPORT_TIMEOUT_SEC`;
  - после live full-run сохранить `safe_count`, итоговый `.md` и `*_usernames.*` в handoff/state, не возвращаясь без причины к старому route-probe расследованию.
