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

Новый самый свежий repo-level факт на 2026-05-09 теперь уже не про отдельный чат, а про install/runtime baseline:
- закрыт `Production Hardening Change Set 3: Telegram GUI Extraction + Legacy Collector Cleanup`:
  - code fact:
    - `scripts/telegram_gui/backend.py` теперь реальный owner для `TelegramGuiBackend`;
    - `scripts/telegram_gui/ui/window.py` теперь реальный owner для `TelegramMembersExportWindow` и `TelegramMembersExportApp`;
    - `scripts/telegram_gui/app.py` истончён до shared prelude + compatibility exports + `main()`;
    - shared globals `app.py` зеркалятся в owner-модули, поэтому старый import/test contract не сломан;
    - implicit legacy collector fallback `/home/max/telegram-api-collector` убран из GUI runtime и `bootstrap_telegram_workstation.sh`.
  - verify:
    - `python3 -m unittest discover -s tests -p 'test_*.py'` -> `294 tests OK`
    - `python3 -m webcontrol --help` -> OK
    - `python3 -m webcontrol browser --help` -> OK
    - `python3 -m webcontrol runtime-env --format json --no-create` -> OK
    - `python3 scripts/export_telegram_members_non_pii.py --help` -> OK
    - `bash scripts/bootstrap_telegram_workstation.sh --doctor` -> OK
    - `python3 -m webcontrol health` -> OK
    - `python3 -m webcontrol state` -> OK
    - clean install smoke:
      - `pip install -r requirements.txt` -> OK
      - `pip install -e .` -> OK
      - `sitectl --help` -> OK
      - `telegram-username-collector` -> clean GTK fast-fail, не traceback
    - live GTK startup smoke на `DISPLAY=:0` подтвердил реальное окно
  - practical result:
    - extraction backend/window уже не pending;
    - следующий безопасный этап теперь уже не ещё один `app.py` split, а Windows core smoke + короткий release checklist;
    - exact Windows core smoke checklist теперь уже записан в `README.md` и `docs/INSTALL_OTHER_DEVICES_RU.md`, и следующий агент должен идти по нему буквально.
- закрыт `Production Hardening Change Set 2: Logging + Launcher + Install Story`:
  - code fact:
    - `PyGObject` больше не входит в pip-manifest проекта; GTK GUI на Linux теперь считается system dependency;
    - новый launcher `telegram-username-collector` даёт понятный fast-fail на Windows и при отсутствии GTK bindings;
    - старый `scripts/telegram_members_export_gui.py` оставлен как compatibility alias;
    - hub теперь пишет `runtime_events.jsonl` и `runtime_errors.jsonl`;
    - Telegram GUI теперь пишет `telegram_workspace/runs/<run_id>/{summary.json,artifacts.json,events.jsonl}`;
    - `bootstrap_telegram_workstation.sh --doctor` теперь печатает resolved runtime/log/report paths;
    - `scripts/telegram_contact_chain.py` больше не использует home-path default output root.
  - verify:
    - `python3 -m unittest discover -s tests -p 'test_*.py'` -> `293 tests OK`
    - `python3 -m webcontrol --help` -> OK
    - `python3 -m webcontrol browser --help` -> OK
    - `python3 -m webcontrol runtime-env --format json --no-create` -> OK
    - `python3 scripts/export_telegram_members_non_pii.py --help` -> OK
    - `bash scripts/bootstrap_telegram_workstation.sh --doctor` -> OK
    - `bash scripts/start_hub.sh` -> hub started; `python3 -m webcontrol health` -> OK; `python3 -m webcontrol state` -> OK
    - clean install smoke:
      - `pip install -r requirements.txt` -> OK
      - `pip install -e .` -> OK
      - `sitectl --help` -> OK
      - `telegram-username-collector` -> clean GTK fast-fail, не traceback
    - live GTK startup smoke on `DISPLAY=:0` подтвердил реальное окно
  - practical result:
    - install story теперь не падает на `PyGObject` в чистом venv;
    - runtime/log/report paths теперь ясны и через doctor, и через JSONL logs;
    - следующий безопасный этап — extraction backend/window orchestration из `scripts/telegram_gui/app.py`, а не ещё один baseline pass.
- закрыт `Production Hardening Change Set 1: Runtime/Config Baseline`:
  - code fact:
    - появился общий settings-layer `webcontrol/settings.py`;
    - в репозитории появились `requirements.txt`, `config/default.yaml`, `.env.example`;
    - default runtime root теперь проектный: `./var/site-control-kit`;
    - settings precedence теперь единая: `env -> .env -> .site-control-kit/local.yaml -> config/default.yaml`;
    - при существующем `~/.site-control-kit` репозиторий не переносит данные автоматически, а создаёт pointer `.site-control-kit/local.yaml`;
    - quickstart token больше не является рабочим fallback для core entrypoints.
  - verify:
    - `python3 -m unittest discover -s tests -p 'test_*.py'` -> `285 tests OK`
    - `python3 -m webcontrol --help` -> OK
    - `python3 -m webcontrol browser --help` -> OK
    - `python3 -m webcontrol runtime-env --format json --no-create` -> OK
    - `bash scripts/start_hub.sh` -> hub started; `python3 -m webcontrol health` -> OK; `python3 -m webcontrol state` -> OK
    - `python3 scripts/export_telegram_members_non_pii.py --help` -> OK
    - `bash scripts/bootstrap_telegram_workstation.sh --doctor` -> OK
    - live GTK startup smoke на `DISPLAY=:0` подтвердил реальное окно `Telegram Username Collector`
  - practical result:
    - на этой машине current runtime по-прежнему резолвится в legacy `~/.site-control-kit/...`, но уже через явный compatibility pointer, а не через разбросанные hardcoded пути;
    - локальный generated token теперь лежит в `.site-control-kit/generated_token.txt`.
  - practical next step:
    - следующий безопасный цикл теперь уже не про новый target-chat, а про unified logging/error-reporting и минимальный extraction runtime/logging orchestration из `scripts/telegram_gui/app.py`.

Новый самый свежий факт на 2026-05-09 теперь уже про `ROST FARMA` live continuation:
- закрыт `TG_CONTACT 4 ROST FARMA Stability And Live Export Cycle`:
  - code fact:
    - новый код в репозитории в этом цикле не потребовался;
    - основной `TG_CONTACT 4 -> Primary tdata` path уже отработал end-to-end без нового blocker-а;
    - browser hub проверялся только как secondary contour: `status/tabs` стали рабочими после `bash scripts/start_hub.sh`, но browser clients остались stale/offline и не повлияли на export path.
  - verify:
    - `bash scripts/bootstrap_telegram_workstation.sh --doctor` -> `managed_helper_ready=1`, `gtk_runtime=ok`, `selected_helper_source=managed`
    - `python3 -m webcontrol --help` -> OK
    - `python3 -m webcontrol browser --help` -> OK
    - `python3 -m unittest discover -s tests -p 'test_*.py'` -> `280 tests OK`
  - live target:
    - `Чат ROST FARMA`
    - `chat_ref=-1001340567266`
    - `source_kind=live`
    - output root: `/home/max/4`
  - artifacts:
    - `/tmp/tg_contact4_rost_farma_live_20260509T073256Z.json`
    - `/home/max/.site-control-kit/telegram_workspace/logs/gui_actions_tg_contact4_rost_farma_live_20260509T073256Z.log`
    - `/home/max/4/tg_contact4_rost_farma_quick_check_20260509T073256Z.md`
    - `/home/max/4/tg_contact4_rost_farma_quick_check_20260509T073256Z_usernames.txt`
    - `/home/max/4/tg_contact4_rost_farma_quick_check_20260509T073256Z_usernames.json`
    - `/home/max/4/tg_contact4_rost_farma_full_history_20260509T073256Z.md`
    - `/home/max/4/tg_contact4_rost_farma_full_history_20260509T073256Z_usernames.txt`
    - `/home/max/4/tg_contact4_rost_farma_full_history_20260509T073256Z_usernames.json`
    - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260509T073309Z.log`
    - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260509T073315Z.log`
    - `artifacts/telegram_exports/INDEX.md`
  - result:
    - quick-check: `31 usernames / 400 messages`
    - full-history: `2481 usernames / 269206 messages`
  - practical next step:
    - считать `ROST FARMA` strongest confirmed target на `TG_CONTACT 4`
    - следующий run брать как ещё один productive live/public/invite target на `TG_CONTACT 4`
    - secure token / legacy cleanup по-прежнему держать отдельными explicit циклами

Новый самый свежий факт на 2026-05-08 теперь уже про close-path самого окна:
- закрыт `GTK Window Close -> Stop Save -> Auto Close`:
  - code fact:
    - `scripts/telegram_gui/app.py` теперь обрабатывает `close-request`;
    - во время активного export закрытие окна теперь значит `request_cancel -> partial save -> auto close`;
    - в idle-state окно закрывается сразу и приложение явно завершает `Gtk.Application`.
  - verify:
    - `python3 -m unittest tests.test_telegram_members_export_gui tests.test_telegram_tdata_helper` -> `47 tests OK`
    - `python3 -m unittest discover -s tests -p 'test_*.py'` -> `280 tests OK`
    - `git diff --check` -> clean
  - practical result:
    - старое зависшее окно `Telegram Username Collector` уже больше не висит на `DISPLAY=:0`;
    - новый close-path теперь согласован с уже live-verified partial-save path.
  - practical next step:
    - при следующих длинных run считать safe close-through-stop уже штатной частью operator UX, а не отдельным workaround.

Новый самый свежий факт на 2026-05-08 теперь уже про `BigpharmaMarket` retry + partial-save continuation:
- закрыт `TG_CONTACT 4 BigpharmaMarket Retry Fix + Partial Stop Save`:
  - code fact:
    - `scripts/telegram_tdata_helper.py` теперь переживает `MsgidDecreaseRetryError` во время history scan и продолжает export с меньшего `message_id`;
    - неожиданные helper-исключения теперь печатают полный traceback в stderr;
    - в `tests/test_telegram_tdata_helper.py` landed recovery-тест именно на этот retry path.
  - verify:
    - `python3 -m unittest discover -s tests -p 'test_*.py'` -> `277 tests OK`
    - `python3 -m webcontrol --help` -> OK
    - `python3 -m webcontrol browser --help` -> OK
    - `./browser.sh status` -> OK
    - `./browser.sh tabs` -> OK
    - `git diff --check` -> clean
  - live target:
    - `Чат BigpharmaMarket`
    - `chat_ref=-1001461811598`
    - output path: `/home/max/3/@BigpharmaMarket`
  - artifacts:
    - `/tmp/tg_contact4_bigpharmamarket_retry_live_20260508T120151Z.json`
    - `/home/max/.site-control-kit/telegram_workspace/logs/gui_actions_tg_contact4_bigpharmamarket_retry_live_20260508T120151Z.log`
    - `/home/max/.site-control-kit/telegram_workspace/logs/live_progress_tg_contact4_bigpharmamarket_retry_20260508T120151Z.log`
    - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260508T120205Z.log`
    - `/home/max/3/@BigpharmaMarket`
    - `/home/max/3/@BigpharmaMarket_usernames.txt`
    - `/home/max/3/@BigpharmaMarket_usernames.json`
    - `/home/max/3/telegram_export_чат_bigpharmamarket/latest_safe.txt`
    - `/home/max/3/telegram_export_чат_bigpharmamarket/latest_safe.md`
    - `artifacts/telegram_exports/INDEX.md`
  - result:
    - live run прошёл старый fatal region и дошёл до `304900` сообщений / `436` usernames;
    - после мягкого stop helper вернул `interrupted=1`, а partial markdown и username sidecars были сохранены;
    - checkpoint зафиксирован как `status=partial`, не как `failed`.
  - practical next step:
    - считать `BigpharmaMarket` blocker по `MsgidDecreaseRetryError` закрытым;
    - если пользователь хочет полный естественный конец, можно запускать long run снова без страха потерять уже собранные контакты по stop-path;
    - держать в голове, что artifact index на этот partial run уже обновлён.

Новый самый свежий факт на 2026-05-08 теперь уже про `НаДопинге 2.0` live continuation:
- закрыт `TG_CONTACT 4 НаДопинге 2.0 Live Run`:
  - code fact:
    - новый код в этом цикле не потребовался; использован прямой live-row path
    - чат уже был виден `TG_CONTACT 4` в текущем dialog list как `source_kind=live`
  - verify:
    - `./browser.sh status` -> OK
    - `./browser.sh tabs` -> OK
    - `bash scripts/bootstrap_telegram_workstation.sh --doctor` -> `managed_helper_ready=1`, `selected_helper_source=managed`
    - backend `ensure_connected -> fetch_chats` подтвердил:
      - `НаДопинге 2.0 ЧАТ | Бодибилдинг | Фитнес | Спорт Фармакология`
      - `chat_ref=-1002465948544`
  - live target:
    - `НаДопинге 2.0 ЧАТ | Бодибилдинг | Фитнес | Спорт Фармакология`
    - `chat_ref=-1002465948544`
  - artifacts:
    - `/tmp/tg_contact4_nadopinge20_live_20260508T103755Z.json`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_nadopinge20_quick_check_20260508T103755Z.md`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_nadopinge20_quick_check_20260508T103755Z_usernames.txt`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_nadopinge20_quick_check_20260508T103755Z_usernames.json`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_nadopinge20_full_history_20260508T103755Z.md`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_nadopinge20_full_history_20260508T103755Z_usernames.txt`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_nadopinge20_full_history_20260508T103755Z_usernames.json`
    - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260508T103827Z.log`
    - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260508T103838Z.log`
    - `/home/max/.site-control-kit/telegram_workspace/logs/gui_actions_tg_contact4_nadopinge20_live_20260508T103755Z.log`
    - `artifacts/telegram_exports/INDEX.md`
  - result:
    - quick-check: `33 usernames / 400 messages`
    - full-history: `1614 usernames / 187829 messages`
  - practical next step:
    - считать `НаДопинге 2.0` strongest confirmed target для `TG_CONTACT 4`
    - следующий run можно брать либо как ещё один productive chat, либо уже как отдельный цикл сравнения top targets
    - secure token / legacy cleanup по-прежнему держать отдельными explicit циклами

Новый самый свежий факт на 2026-05-08 теперь уже про `FitPharma` live continuation:
- закрыт `TG_CONTACT 4 FitPharma Live Run`:
  - code fact:
    - новый код в этом цикле не потребовался; использован уже landed public-target path
    - preflight снова подтвердил `managed helper` и рабочий `Primary tdata` contour
  - verify:
    - `./browser.sh status` -> OK
    - `./browser.sh tabs` -> OK
    - `bash scripts/bootstrap_telegram_workstation.sh --doctor` -> `managed_helper_ready=1`, `selected_helper_source=managed`
    - backend-resolve `https://t.me/FitPharma` -> `FitPharma / @FitPharma / chat_ref=-1001739132808`
  - live target:
    - `https://t.me/FitPharma`
    - `FitPharma`
    - `@FitPharma`
    - `chat_ref=-1001739132808`
  - artifacts:
    - `/tmp/tg_contact4_fitpharma_live_20260508T085911Z.json`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_fitpharma_quick_check_20260508T085911Z.md`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_fitpharma_quick_check_20260508T085911Z_usernames.txt`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_fitpharma_quick_check_20260508T085911Z_usernames.json`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_fitpharma_full_history_20260508T085911Z.md`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_fitpharma_full_history_20260508T085911Z_usernames.txt`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_fitpharma_full_history_20260508T085911Z_usernames.json`
    - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260508T085955Z.log`
    - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260508T090006Z.log`
    - `/home/max/.site-control-kit/telegram_workspace/logs/gui_actions_tg_contact4_fitpharma_live_20260508T085911Z.log`
    - `artifacts/telegram_exports/INDEX.md`
  - result:
    - quick-check: `34 usernames / 400 messages`
    - full-history: `253 usernames / 28509 messages`
  - practical next step:
    - брать следующий public/invite/live target уже на `TG_CONTACT 4`
    - считать `FitPharma` подтверждённым продуктивным target, но с меньшей плотностью `@username`, чем у `@cosmetologna`
    - secure token / legacy cleanup по-прежнему держать отдельными explicit циклами

Новый самый свежий факт на 2026-05-08 теперь уже про public-link path и install foundation:
- закрыт `TG_CONTACT 4 Public Resolve + Linux Bootstrap + cosmetologna Live Run`:
  - code fact:
    - helper `resolve-chat` уже добавлен в `scripts/telegram_tdata_helper.py`
    - backend/UI public-target path уже добавлен в `scripts/telegram_gui/app.py`
    - `scripts/bootstrap_telegram_workstation.sh` и `scripts/telegram_helper_requirements.txt` уже формируют managed helper venv
    - `telegram-username-collector` уже добавлен в `pyproject.toml`
    - GUI helper calls теперь сериализуются lock-ом, чтобы deep preflight и `connect` не конфликтовали на одном `tdata/session`
    - GUI run history теперь автоматически пишет entry в `artifacts/telegram_exports/INDEX.md`
  - verify:
    - `bash scripts/bootstrap_telegram_workstation.sh --doctor` -> `managed_helper_ready=1`, `selected_helper_source=managed`
    - `python3 -m unittest discover -s tests -p 'test_*.py'` -> `276 tests OK`
    - `python3 -m webcontrol --help` -> OK
    - `python3 -m webcontrol browser --help` -> OK
    - `./browser.sh status` -> OK
    - `./browser.sh tabs` -> OK
    - `git diff --check` -> clean
  - live target:
    - `https://t.me/cosmetologna`
    - `Косметолог на Миллион`
    - `@cosmetologna`
    - `chat_ref=-1001506021345`
  - artifacts:
    - `/tmp/tg_contact4_cosmetologna_live_20260508T082312Z.json`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_cosmetologna_quick_check_20260508T082312Z.md`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_cosmetologna_quick_check_20260508T082312Z_usernames.txt`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_cosmetologna_quick_check_20260508T082312Z_usernames.json`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_cosmetologna_full_history_20260508T082312Z.md`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_cosmetologna_full_history_20260508T082312Z_usernames.txt`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_cosmetologna_full_history_20260508T082312Z_usernames.json`
    - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260508T082357Z.log`
    - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260508T082408Z.log`
    - `/home/max/.site-control-kit/telegram_workspace/logs/gui_actions_tg_contact4_cosmetologna_live_20260508T082312Z.log`
    - `artifacts/telegram_exports/INDEX.md`
  - result:
    - quick-check: `117 usernames / 400 messages`
    - full-history: `1534 usernames / 13055 messages`
  - practical next step:
    - брать следующий public/invite/live target уже на `TG_CONTACT 4`
    - не считать отсутствие чата в live dialog list блокером, если есть public link или `@username`
    - secure token / legacy cleanup решать отдельными explicit циклами

Новый самый свежий факт на 2026-05-07 уже ещё новее:
- закрыт `TG_CONTACT 4 Invite Join Fix + RIVIVE LIFE Chat Live Run`:
  - code fact:
    - helper `join-invite` уже добавлен в `scripts/telegram_tdata_helper.py`
    - backend path `join_tdata_invite(...)` уже добавлен в `scripts/telegram_gui/app.py`
    - targeted/backend tests уже включены в общий suite
  - verify:
    - `python3 -m unittest discover -s tests -p 'test_*.py'` -> `265 tests OK`
    - `python3 -m webcontrol --help` -> OK
    - `python3 -m webcontrol browser --help` -> OK
    - `./browser.sh status` -> OK
    - `./browser.sh tabs` -> OK
    - `git diff --check` -> clean
  - invite fact:
    - source invite: `http://t.me/+6FMgmFJCh0I4M2Yy`
    - `joined=False`, `already_member=True`
    - resolved chat: `RIVIVE LIFE Chat`, `chat_ref=-1002269737802`
  - artifacts:
    - `/tmp/tg_contact4_invite_live_20260507T123136Z.json`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_invite_quick_check_20260507T123136Z.md`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_invite_quick_check_20260507T123136Z_usernames.txt`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_invite_quick_check_20260507T123136Z_usernames.json`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_invite_full_history_20260507T123136Z.md`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_invite_full_history_20260507T123136Z_usernames.txt`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_invite_full_history_20260507T123136Z_usernames.json`
    - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260507T123156Z.log`
    - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260507T123200Z.log`
    - `/home/max/.site-control-kit/telegram_workspace/logs/gui_actions_tg_contact4_invite_live_20260507T123136Z.log`
  - result:
    - quick-check: `56 usernames / 400 messages`
    - full-history: `1158 usernames / 62029 messages`
  - practical next step:
    - брать следующий invite/live target на `TG_CONTACT 4`
    - либо отдельным циклом чистить legacy profiles
    - operator note: `только у нас ножичек с собой`

Новый самый свежий факт на 2026-05-07 уже ещё новее:
- закрыт `TG_CONTACT 4 Next Productive Chat = @cosmochatrussia Repeat Run`:
  - operator fact:
    - текущий operator profile не менялся: вся работа остаётся только на `TG_CONTACT 4`
    - `default_user` остаётся `TG_CONTACT 4`
    - helper/export path снова шёл через `runtime/helper_workdir/tdata`
  - live target:
    - `Чат Косметологов | Косметологи чат | Чат косметологов России`
    - `@cosmochatrussia`
    - `chat_ref=-1001909598727`
  - summary:
    - `/tmp/tg_contact4_cosmochatrussia_repeat_20260507T094441Z.json`
  - artifacts:
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_cosmochatrussia_repeat_quick_check_20260507T094441Z.md`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_cosmochatrussia_repeat_quick_check_20260507T094441Z_usernames.txt`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_cosmochatrussia_repeat_quick_check_20260507T094441Z_usernames.json`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_cosmochatrussia_repeat_full_history_20260507T094441Z.md`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_cosmochatrussia_repeat_full_history_20260507T094441Z_usernames.txt`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_cosmochatrussia_repeat_full_history_20260507T094441Z_usernames.json`
    - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260507T094455Z.log`
    - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260507T094504Z.log`
    - `/home/max/.site-control-kit/telegram_workspace/logs/gui_actions_tg_contact4_cosmochatrussia_repeat_20260507T094441Z.log`
  - result:
    - quick-check: `103 usernames / 400 messages`
    - full-history: `1486 usernames / 9351 messages`
    - during full-history Telegram emitted transient `MsgidDecreaseRetryError`, but the run recovered and completed
  - practical next step:
    - следующий content-step теперь уже новый target после `@cosmochatrussia`
    - cleanup legacy profiles остаётся отдельным explicit циклом

Новый самый свежий факт на 2026-05-07 уже ещё новее:
- закрыт `TG_CONTACT 4 Only Operator Pivot + Repeat @slivcosmo Live Verify`:
  - operator fact:
    - вся текущая живая работа теперь ведётся только через `TG_CONTACT 4`
    - `~/.site-control-kit/telegram_workspace/registry/users.json` уже содержит `default_user = TG_CONTACT 4`
    - `TG_CONTACT 2`, `TG_CONTACT 3`, `@AK-LIVE`, `@AK-ADOPTED`, `Слот 1`, `Слот 2` пока не удалялись и остаются legacy rows
    - cleanup этих legacy rows не выполнен и должен делаться только отдельным explicit циклом
  - repeat live summary:
    - `/tmp/tg_contact4_only_slivcosmo_live_verify_20260507T084752Z.json`
  - repeat live target:
    - `БЕСПЛАТНАЯ КОСМЕТОЛОГИЯ`
    - `@slivcosmo`
    - `chat_ref=-1001555954026`
  - repeat artifacts:
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_only_slivcosmo_quick_check_20260507T084752Z.md`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_only_slivcosmo_quick_check_20260507T084752Z_usernames.txt`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_only_slivcosmo_quick_check_20260507T084752Z_usernames.json`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_only_slivcosmo_full_history_20260507T084752Z.md`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_only_slivcosmo_full_history_20260507T084752Z_usernames.txt`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_only_slivcosmo_full_history_20260507T084752Z_usernames.json`
    - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260507T084840Z.log`
    - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260507T084855Z.log`
    - `/home/max/.site-control-kit/telegram_workspace/logs/gui_actions_tg_contact4_only_slivcosmo_live_verify_20260507T084752Z.log`
  - repeat result:
    - rerun summary ещё показывает historical pre-pivot `TG_CONTACT 2`, потому что registry promotion была выполнена сразу после rerun
    - фактический current workspace state уже `default_user = TG_CONTACT 4`
    - quick-check: `0 usernames / 400 messages`
    - full-history: `0 usernames / 1358 messages`
    - runtime/helper path остался стабильным и шёл через `runtime/helper_workdir/tdata`
  - practical next step:
    - брать следующий productive live-чат уже на `TG_CONTACT 4`
    - или делать отдельный cleanup legacy-профилей по точному списку, но не смешивать это с новым export cycle

Новый самый свежий факт на 2026-05-07 уже ещё новее:
- закрыт `TG_CONTACT 4 Safe Launch Clone + @slivcosmo Live Verify`:
  - code/runtime fact:
    - portable launch у imported `TG_CONTACT 4` уже не трогает канонический `TelegramForcePortable/tdata`
    - launch идёт через `/home/max/.site-control-kit/telegram_workspace/PortableProfiles/TelegramPortable-tg-contact-4/runtime/launch_workdir`
    - helper/export идут через `/home/max/.site-control-kit/telegram_workspace/PortableProfiles/TelegramPortable-tg-contact-4/runtime/helper_workdir/tdata`
    - `Обновить статус` уже live-синхронизирует stopped `launch_workdir -> helper_workdir`
  - verify:
    - `python3 -m unittest discover -s tests -p 'test_*.py'` -> `262 tests OK`
    - `python3 -m webcontrol --help` -> OK
    - `python3 -m webcontrol browser --help` -> OK
    - `./start-browser.sh`, `./browser.sh status`, `./browser.sh tabs` -> OK
    - `git diff --check` -> clean
  - live summary:
    - `/tmp/tg_contact4_slivcosmo_live_verify_20260507T083138Z.json`
  - live target:
    - `БЕСПЛАТНАЯ КОСМЕТОЛОГИЯ`
    - `@slivcosmo`
    - `chat_ref=-1001555954026`
  - artifacts:
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_slivcosmo_quick_check_20260507T083138Z.md`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_slivcosmo_quick_check_20260507T083138Z_usernames.txt`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_slivcosmo_quick_check_20260507T083138Z_usernames.json`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_slivcosmo_full_history_20260507T083138Z.md`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_slivcosmo_full_history_20260507T083138Z_usernames.txt`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_slivcosmo_full_history_20260507T083138Z_usernames.json`
    - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260507T083217Z.log`
    - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260507T083226Z.log`
    - `/home/max/.site-control-kit/telegram_workspace/logs/gui_actions_tg_contact4_slivcosmo_live_verify_20260507T083138Z.log`
  - result:
    - `default_user` остался `TG_CONTACT 2`
    - save dialog реально открылся в обоих фазах
    - quick-check: `status=done`, `safe_count=0`, `history_messages_scanned=400`
    - full-history: `status=done`, `safe_count=0`, `history_messages_scanned=1358`
    - `security_mode=Insecure local token`
  - practical conclusion:
    - launch-driven helper corruption на fixed isolated runtime path больше не воспроизвелась;
    - `@slivcosmo` стал content-zero live baseline, а не runtime blocker;
    - следующий шаг теперь либо новый target chat с ожидаемыми `@username`, либо отдельный secure/default promotion cycle.

Новый самый свежий факт на 2026-05-07 уже другой:
- закрыт `TG_CONTACT 4 @cosmochatrussia Live Collection`:
  - source: `/home/max/site-control-kit/TG_CONTACT/4/tdata-003.zip`
  - managed profile: `/home/max/.site-control-kit/telegram_workspace/PortableProfiles/TelegramPortable-tg-contact-4`
  - `default_user` остаётся `TG_CONTACT 2`
  - live chat:
    - `Чат Косметологов | Косметологи чат | Чат косметологов России`
    - `@cosmochatrussia`
    - `chat_ref=-1001909598727`
  - live quick-check artifacts:
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_cosmochatrussia_quick_check_20260507T073523Z.md`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_cosmochatrussia_quick_check_20260507T073523Z_usernames.txt`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_cosmochatrussia_quick_check_20260507T073523Z_usernames.json`
    - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260507T073607Z.log`
    - `/home/max/.site-control-kit/telegram_workspace/logs/gui_actions_tg_contact4_cosmochatrussia_live_20260507T073523Z_20260507T073540Z.log`
  - quick-check result:
    - `status=done`
    - `safe_count=103`
    - `history_messages_scanned=400`
  - live full-history artifacts:
    - `/tmp/tg_contact4_cosmochatrussia_full_only_20260507T074001Z.json`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_cosmochatrussia_full_history_20260507T074001Z.md`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_cosmochatrussia_full_history_20260507T074001Z_usernames.txt`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_cosmochatrussia_full_history_20260507T074001Z_usernames.json`
    - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260507T074039Z.log`
    - `/home/max/.site-control-kit/telegram_workspace/logs/gui_actions_tg_contact4_cosmochatrussia_full_only_20260507T074001Z_20260507T074016Z.log`
  - full-history result:
    - `status=done`
    - `safe_count=1486`
    - `history_messages_scanned=9341`
    - `security_mode=Insecure local token`
  - critical residual:
    - первый combined pass `quick -> full` после portable launch дал быстрый helper failure `OpenTeleException: No account has been loaded`;
    - managed `tdata` пришлось повторно восстанавливать из source ZIP;
    - drifted copy сохранена как `/home/max/.site-control-kit/telegram_workspace/PortableProfiles/TelegramPortable-tg-contact-4/TelegramForcePortable/tdata.backup_20260507T073936Z`;
    - successful full pass получен только во втором GTK run без повторного portable launch.

Более ранний свежий факт того же дня:
- закрыт `TG_CONTACT 4 Managed Import + Runtime Blocker`:
  - source: `/home/max/site-control-kit/TG_CONTACT/4/tdata-003.zip`
  - companion metadata: `/home/max/site-control-kit/TG_CONTACT/4/apiapp.txt`
  - managed profile уже создан как `/home/max/.site-control-kit/telegram_workspace/PortableProfiles/TelegramPortable-tg-contact-4`
  - `registry/users.json` уже содержит row `TG_CONTACT 4`
  - `default_user` по-прежнему `TG_CONTACT 2`
  - current selector/backend list теперь включает `TG_CONTACT 2`, `@AK-ADOPTED`, `@AK-LIVE`, `TG_CONTACT 3`, `TG_CONTACT 4`, `Слот 1`, `Слот 2`
- import/live evidence:
  - `/home/max/.site-control-kit/telegram_workspace/logs/gui_actions_tg_contact4_first_live_20260507T065536Z_20260507T065600Z.log`
  - в этом log уже есть `portable_profile_imported`, `portable_profile_account_synced`, `client_ready portable_tdata ...`, `chats_loaded ... count=30`
- current blocker evidence:
  - `/tmp/tg_contact4_direct_live_20260507T070439Z.json`
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_runtime_blocker_20260507T070439Z.md`
  - `/home/max/.site-control-kit/telegram_workspace/logs/gui_actions_tg_contact4_direct_live_20260507T070439Z_20260507T070446Z.log`
- practical blocker result:
  - direct GTK re-check остановился в `ensure_connected()` с `PrimarySurfaceBlocked`
  - repeated direct probe даёт `prepare_portable_runtime() -> unauthorized`
  - detail: `Portable профиль найден, но helper не смог открыть сессию. Откройте этот Telegram Desktop профиль и дождитесь полной загрузки.`
  - новых export sidecars пока нет, потому что blocker-pass не дошёл до export start
- новый пошаговый следующий ход:
  - шаг 1: открыть managed portable profile `TG_CONTACT 4` на desktop и дождаться полной загрузки Telegram-сессии
  - шаг 2: повторить `prepare_portable_runtime()` и добиться `authorized=True`
  - шаг 3: сразу после этого снова пройти live GTK `connect -> fetch chats -> choose live dialog row -> save dialog -> Quick Check`
  - шаг 4: только после успешного artifact pack решать, оставлять ли `TG_CONTACT 4` auxiliary profile или продвигать его дальше

Более ранний новый факт того же дня:
- поверх `Known Chat Guard + TG_CONTACT 3 Bigpharma Live Path` уже выполнен `Checkpoint Stabilization`;
- обязательный verify снова зелёный:
  - `python3 -m unittest discover -s tests -p 'test_*.py'` -> `258 tests OK`
  - `python3 -m webcontrol --help` -> OK
  - `python3 -m webcontrol browser --help` -> OK
- browser contour перед live GTK verify снова поднят:
  - `./start-browser.sh` вернул healthy hub
  - `./browser.sh status` и `./browser.sh tabs` снова прошли по живому browser client
- новый current-list/live baseline для `TG_CONTACT 2`:
  - `/tmp/tg_contact2_live_walkthrough_20260507T061343Z.json`
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact2_live_walkthrough_20260507T061343Z.md`
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact2_live_walkthrough_20260507T061343Z_usernames.txt`
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact2_live_walkthrough_20260507T061343Z_usernames.json`
  - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260507T061359Z.log`
  - `/home/max/.site-control-kit/telegram_workspace/logs/gui_actions_tg_contact2_live_walkthrough_20260507T061343Z_20260507T061343Z.log`
- новый current-list fact:
  - реальное GTK окно снова прошло live path на `DISPLAY=:0`;
  - системный save dialog снова реально открылся;
  - `TG_CONTACT 2` остался `default_user` с `Local secure token`;
  - live export на `Патрик Stars | Звёзды и подарки бесплатно` (`7996790736`) завершился `status=done`, `safe_count=1`, `history_messages_scanned=12`.
- новый known-guard fact:
  - `/tmp/tg_contact2_bigpharma_known_guard_20260507T061415Z.json`
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact2_bigpharma_known_guard_20260507T061415Z.md`
  - `/home/max/.site-control-kit/telegram_workspace/logs/gui_actions_tg_contact2_bigpharma_known_guard_20260507T061415Z_20260507T061416Z.log`
  - `Чат BigpharmaMarket` снова пришёл как `known chat`, и GUI снова заблокировал export до старта helper/export path понятной operator-ошибкой.
- новый blocker fact по `TG_CONTACT 3`:
  - старый success `2026-05-05` остаётся историческим фактом, но на `2026-05-07` профиль уже не прошёл live re-verify;
  - `/tmp/tg_contact3_bigpharma_blocker_20260507T061738Z.json`
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact3_bigpharma_blocker_20260507T061738Z.md`
  - `prepare_portable_runtime()` для `TG_CONTACT 3` сейчас возвращает `unauthorized`;
  - helper не смог открыть session и упёрся в `tdata helper timed out after 12s: list-chats /home/max/.site-control-kit/telegram_workspace/PortableProfiles/TelegramPortable-tg-contact-3/TelegramForcePortable/tdata`;
  - повторный launch portable binary не вернул профиль в `ready`.
- новый selector fact:
  - current selector сейчас включает `TG_CONTACT 2`, `@AK-ADOPTED`, `@AK-LIVE`, `TG_CONTACT 3`, `Слот 1`, `Слот 2`;
  - это новее текста, где legacy row ещё назывался `Слот 2 · portable ZIP`.
- новый practical residual:
  - `TG_CONTACT 2` остаётся рабочим default profile;
  - `BigpharmaMarket` у него по-прежнему only-known;
  - `TG_CONTACT 3` нельзя считать current live-confirmed Bigpharma profile, пока не восстановлена desktop session;
  - automated GTK harness после успешного export поймал `Gtk-CRITICAL gtk_box_remove ...`, но артефакты и run history записались штатно.

Более ранний новый факт на 2026-05-05:
- поверх `TG_CONTACT 2 Non-Blocking GUI Startup` уже реализован `Known Chat Guard + TG_CONTACT 3 Bigpharma Live Path`;
- новый current-list/live baseline для `TG_CONTACT 2`:
  - `/tmp/telegram_live_walkthrough_20260505T131711Z.json`
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact2_live_walkthrough_20260505T131711Z.md`
  - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260505T131726Z.log`
  - `/home/max/.site-control-kit/telegram_workspace/logs/gui_actions_live_walkthrough_20260505T131711Z.log`
- новый current-list fact:
  - реальное GTK окно на `DISPLAY=:0` прошло путь `startup -> connect -> choose chat -> save dialog -> Quick Check`;
  - `TG_CONTACT 2` остаётся default profile с `Local secure token`;
  - live-чат `Патрик Stars | Звёзды и подарки бесплатно` (`7996790736`) дал `status=done`, `safe_count=1`, `history_messages_scanned=9`.
- новый known-chat guard fact:
  - synthetic row `Чат BigpharmaMarket` теперь может оставаться видимым в списке как `known chat`;
  - но export на `Primary tdata` больше не уводит в поздний helper/Telethon traceback, если этот профиль не видит чат в своём live dialog list;
  - вместо этого GUI сразу показывает operator-ошибку, что для `TG_CONTACT 2` `BigpharmaMarket` сейчас only-known, а не live-resolvable target.
- новый import/live fact по `TG_CONTACT 3`:
  - source ZIP: `/home/max/site-control-kit/TG_CONTACT/3/tdata-20260505T131440Z-3-001.zip`
  - managed dir: `/home/max/.site-control-kit/telegram_workspace/PortableProfiles/TelegramPortable-tg-contact-3`
  - `TG_CONTACT 3` уже импортирован как дополнительный managed profile, но `TG_CONTACT 2` при этом остался `default_user`.
- новый Bigpharma baseline через `TG_CONTACT 3`:
  - `/tmp/telegram_tg_contact3_live_20260505T131952Z.json`
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact3_bigpharma_quick_check_20260505T131952Z.md`
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact3_bigpharma_quick_check_20260505T131952Z_usernames.txt`
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact3_bigpharma_quick_check_20260505T131952Z_usernames.json`
  - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260505T132011Z.log`
  - `/home/max/.site-control-kit/telegram_workspace/logs/gui_actions_tg_contact3_live_20260505T131952Z.log`
- новый Bigpharma fact:
  - `TG_CONTACT 3` реально видит `Чат BigpharmaMarket` (`-1001461811598`) в своём live dialog list;
  - GTK walkthrough прошёл `select TG_CONTACT 3 -> connect -> BigpharmaMarket -> save dialog -> Quick Check`;
  - итог `status=done`, `safe_count=14`, `history_messages_scanned=400`.
- новый selector/verify fact:
  - current selector теперь включает ещё и `TG_CONTACT 3` рядом с `TG_CONTACT 2`, `@AK-ADOPTED`, `@AK-LIVE`, `Слот 1`, `Слот 2 · portable ZIP`;
  - полный suite после этих правок снова зелёный: `258 tests OK`.
- новый practical residual:
  - `TG_CONTACT 2` остаётся основным default profile, но он не является рабочим `BigpharmaMarket` profile;
  - если целевой чат именно `BigpharmaMarket`, подтверждённый рабочий профиль теперь `TG_CONTACT 3`;
  - отдельно ещё нужно решить, оставлять ли `TG_CONTACT 3` вспомогательным live-profile или поднимать ему secure token / default status.

Более ранний live-факт того же дня:
- поверх `TG_CONTACT 2 As New Primary Portable Profile` уже реализован `TG_CONTACT 2 Non-Blocking GUI Startup`;
- новый startup/live baseline:
  - `/tmp/telegram_gui_nonblocking_smoke.json`
  - `/tmp/telegram_gui_nonblocking_smoke2.json`
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact2_nonblocking_start_quick_check_20260505T123731Z.md`
  - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260505T123731Z.log`
  - `/home/max/.site-control-kit/telegram_workspace/logs/live_verify_export_20260505.log`
- новый startup-hardening fact:
  - окно теперь открывается сразу, а bootstrap аккаунтов и deep preflight идут в фоне;
  - missing external profile больше не валит `load_accounts()` и весь GTK startup;
  - startup errors больше не выходят modal-диалогом, а остаются inline в hero/preflight/log.
- новый operator fact:
  - `@AK-ADOPTED` теперь остаётся видимым как `missing` с detail про `/tmp/telegram-portable-adopt-live`;
  - `TG_CONTACT 2` после bootstrap остаётся selected/default account, `Primary tdata`, `Local secure token`;
  - live `ensure_connected -> fetch_chats` на `TG_CONTACT 2` вернул `19` чатов;
  - live quick-check export на `астра | языки и темы` прошёл до конца, но снова дал `safe_count=0`, `history_messages_scanned=400`.
- новый selector fact:
  - duplicate `Слот 1` уже убран; current backend list снова one-per-slot:
    - `TG_CONTACT 2`
    - `@AK-ADOPTED`
    - `@AK-LIVE`
    - `Слот 1`
    - `Слот 2 · portable ZIP`
- новый safety fact:
  - `ss -ltnp '( sport = :8765 )'` до и после live smoke был пустым, так что этот цикл не трогал listener на `:8765`.
- новый verify fact:
  - полный suite после этих правок зелёный: `256 tests OK`.
- новый practical residual:
  - startup/root-cause layer закрыт;
  - следующий live export всё ещё лучше делать на чате с ожидаемыми `@username`, потому что quick-check `20260505T123731Z` снова дал `0/400`.

Новый самый свежий факт на 2026-05-04:
- поверх `Portable Profile Orchestration v1` уже реализован `TG_CONTACT 2 As New Primary Portable Profile`;
- новый primary-profile baseline:
  - `/tmp/telegram_tg_contact2_primary_live_20260504T125745Z.json`
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact2_primary_quick_check_20260504T125745Z.md`
  - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260504T125849Z.log`
  - `/home/max/.site-control-kit/telegram_workspace/logs/gui_actions_tg_contact2_primary_20260504T125745Z.log`
- новый default-profile fact:
  - source `/home/max/site-control-kit/TG_CONTACT/2/tdata-20260430T111415Z-3-001.zip` теперь импортирован как managed profile `TG_CONTACT 2`;
  - managed directory created as `/home/max/.site-control-kit/telegram_workspace/PortableProfiles/TelegramPortable-tg-contact-2`;
  - `TG_CONTACT 2` is now `default_user` in `registry/users.json` and selected in both account selector and portable dropdown;
  - security mode for this profile is `Local secure token`.
- новый cleanup fact:
  - `@AK-GUI-WALK` и `@AK-ADOPT-WALK` больше не висят в selectors;
  - managed directory `/home/max/.site-control-kit/telegram_workspace/PortableProfiles/TelegramPortable-ak-gui-walk-21610z` удалён;
  - adopted external folder `/tmp/telegram-portable-real-window-adopt-20260504t121610z` сохранён на диске вместе с external data.
- новый operator fact:
  - для текущего сценария основным profile по умолчанию теперь считать именно `TG_CONTACT 2`, а не legacy slot `2` и не временные live-check profiles;
  - quick-check export на этом профиле уже подтверждён как `Primary tdata`, `Local secure token`, `status=done`, `history_messages_scanned=400`.
- новый continuation-prompt fact:
  - ready-to-use prompt for the next agent is saved at:
    - `/home/max/Desktop/TG_CONTACT_2_CHECKPOINT_PROMPT_2026-05-04.md`
    - `/home/max/Рабочий стол/TG_CONTACT_2_CHECKPOINT_PROMPT_2026-05-04.md`
- поверх `Portable tdata Restore v1` уже реализован `Portable Profile Orchestration v1`;
- новый portable-profile baseline:
  - `/tmp/telegram_portable_profiles_live.json`
  - `/tmp/telegram_portable_profiles_adopt_live.json`
  - `/tmp/telegram_portable_profiles_gui_probe.json`
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/portable_profile_live_quick_check.md`
  - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260504T115535Z.log`
- новый profile-first fact:
  - `scripts/telegram_gui/services/portable_profiles.py` теперь даёт отдельный portable runtime/profile registry слой;
  - managed profile `/home/max/.site-control-kit/telegram_workspace/PortableProfiles/TelegramPortable-ak-live` реально создан из `TG_CONTACT` ZIP и привязан к account `@AK-LIVE`;
  - adopted folder `/tmp/telegram-portable-adopt-live` принят в управление, получил `portable-profile.json` и workspace-link `PortableProfiles/LinkedPortable-ak-adopted`;
  - GTK panel probe на `DISPLAY=:0` увидел `4` portable profiles в одном dropdown и держит selected profile/account `@AK-ADOPTED`.
- новый real-window fact:
  - `/tmp/telegram_portable_profiles_real_window_walkthrough_20260504T121610Z.json`
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/portable_profile_real_window_walkthrough_20260504T121610Z.md`
  - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260504T121716Z.log`
  - `/home/max/.site-control-kit/telegram_workspace/logs/gui_actions_portable_profiles_real_window_20260504T121610Z.log`
  - в одном реальном GTK окне уже прошёл полный portable-profile flow: import `TG_CONTACT` ZIP -> adopt external folder -> select imported profile -> launch -> refresh status -> connect -> list chats -> export;
  - imported managed profile `/home/max/.site-control-kit/telegram_workspace/PortableProfiles/TelegramPortable-ak-gui-walk-21610z` реально экспортировал `Чат BigpharmaMarket` с итогом `status=done`, `safe_count=12`, `history_messages_scanned=400`.
- новый verify fact:
  - полный suite после этих правок зелёный: `241 tests OK`.
- новый practical residual:
  - real-window walkthrough portable-panel уже закрыт;
  - новые live-check profiles `@AK-GUI-WALK` и `@AK-ADOPT-WALK` теперь видны в selectors;
  - для них security mode пока `Insecure local token`, если их нужно использовать дальше за пределами чистого `tdata` path;
  - legacy slot `2` пока всё ещё живёт как старый slot runtime path.
- поверх `Telegram Workstation v1.3` уже реализован `Portable tdata Restore v1`;
- новый portable baseline:
  - `/tmp/telegram_portable_restore_live_recovered.json`
  - `/tmp/telegram_portable_restore_safety.json`
  - `/tmp/telegram_portable_restore_gui_headless.json`
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/portable_restore_slot2_quick_check.md`
  - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260504T110826Z.log`
- новый runtime/source fact:
  - slot `2` теперь импортирован из repo-local `TG_CONTACT` как `Слот 2 · portable ZIP`;
  - persistent runtime clone живёт в `accounts/2/runtime/portable_tdata`;
  - рядом держится alias `accounts/2/runtime/tdata -> portable_tdata`, чтобы portable Telegram и helper работали на одном slot-owned runtime;
  - quick-check export на `Чат BigpharmaMarket` завершился `status=done`, `safe_count=12`, `history_messages_scanned=400`.
- новый safety fact:
  - `import + runtime rebuild` не меняют ни repo-local `TG_CONTACT`, ни `~/telegram-api-collector/tdata_import/tdata`; это зафиксировано в `/tmp/telegram_portable_restore_safety.json`.
- новый practical residual:
  - scripted real-window GTK smoke на `DISPLAY=:0` в этом цикле прибивался средой, поэтому GUI evidence сейчас это headless GTK binding summary + live backend/export, а не полный click-driven walkthrough.
- поверх `Telegram Workstation v1.2` уже реализован `Telegram Workstation v1.3 Secondary Surface Live Closure`;
- новый fallback live baseline:
  - `/tmp/telegram_workstation_v13_backend_live.json`
  - `/tmp/telegram_workstation_v13_gui_fallback.json`
  - `/tmp/telegram_workstation_v13_screen.png`
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/v13_fallback_live_status.md`
- новый runtime/UI fact:
  - `bridge` на реальном slot `1` сейчас классифицируется как `foreign_hub`;
  - внешний `python3` listener `pid=17766` на `:8765` по-прежнему не убивается автоматически;
  - `cdp` в dedicated profile поднимается как `cdp:9430`, но Telegram Web там показывает QR login page и теперь это идёт как `telegram_auth_required`;
  - fallback-card видна даже при `Primary tdata` и показывает actionable states `Bridge: foreign_hub`, `CDP: telegram_auth_required`.
- новый verify fact:
  - полный suite после этих правок зелёный: `232 tests OK`.
- поверх `Telegram Workstation v1` уже собран `Workstation v1.1 Hardening + Panel UX`;
- поверх этого уже реализован `Telegram Workstation v1.2 Secure Token Operator Setup`;
- реальный slot `1` больше не сидит на `Insecure local token`:
  - `/tmp/telegram_workstation_v12_gui_live.json`
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/gui_v12_secure_quick_check.md`
  - quick-check через реальное окно записан с `security_mode=Local secure token`, `safe_count=12`, `history_messages_scanned=400`
- `accounts/1/keys/api_token.txt` теперь только legacy import-source и после secure setup пустой;
- `users.json` хранит row `Слот 1` только с `secret_ref`;
- если на `:8765` живёт внешний hub/process с другим token, security card теперь остаётся видимой и пишет это явно:
  - `/tmp/telegram_workstation_v12_foreign_hub_warning.json`
  - foreign listener не убивается и restart action для него не предлагается.
- security/runtime слой теперь включает `secret_ref + secret files`, checklist `Preflight`, quick chats, history filters и artifact actions;
- реальный `~/.site-control-kit/telegram_workspace` уже прогнан live:
  - `/tmp/telegram_workstation_v11_backend_live.json`
  - `/tmp/telegram_workstation_v11_backend_full_stop_retry.json`
  - `/tmp/telegram_workstation_v11_gui_live.json`
  - `/tmp/telegram_workstation_v11_foreign_port_verify.json`
- новый live operator fact:
  - backend quick-check -> `safe_count=31`, `history_messages_scanned=400`
  - backend stop/partial verify -> `safe_count=30`, `history_messages_scanned=300`, `interrupted=true`
  - GTK walkthrough на `DISPLAY=:0` тоже прошёл до `partial save`
  - foreign listener на `:8765` при token mismatch не убивается автоматически.
- для текущего пользовательского GUI-сценария уже есть `Telegram Workstation v1`;
- старый `scripts/telegram_members_export_gui.py` теперь только фасад, а реальный код живёт в `scripts/telegram_gui/`;
- внутри GUI появился `Run Center` с вкладками `Прогресс`, `Артефакты`, `История`;
- появились preflight-panel, surface badging и presets `Full History`, `Quick Check`, `Resume Last`;
- run history хранится в `~/.site-control-kit/telegram_workspace/runs/index.jsonl`, last session в `~/.site-control-kit/telegram_workspace/state/last_session.json`.

Новый live-факт этого же цикла:
- outside sandbox live backend quick-check на `-1001753733827` через `tdata` завершился успешно:
  - `/tmp/telegram_workstation_backend_smoke_ok.md`
  - `safe_count=31`
  - `history_messages_scanned=400`
- outside sandbox live GTK smoke через само окно тоже прошёл:
  - `/tmp/telegram_workstation_gui_smoke_ok.md`
  - `/tmp/tg_workstation_gui_ws_escalated/logs/export_run_20260504T062030Z.log`
  - `safe_count=31`
  - `history_messages_scanned=400`
- outside sandbox live full-history stop verify тоже подтверждён:
  - `/tmp/telegram_workstation_full_history_ok.md`
  - `/tmp/telegram_workstation_full_history_ok_usernames.txt`
  - `/tmp/telegram_workstation_full_history_ok_usernames.json`
  - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260504T064547Z.log`
  - partial result после stop: `history_messages_scanned=85300`, `safe_count=1032`, `interrupted=true`
  - `runs/index.jsonl` и `state/last_session.json` реально обновились этим run.
- live fallback smoke против реального hub тоже уже сделан:
  - hub отвечает, но bridge-clients сейчас `is_online=false`
  - adapter smoke подтвердил fallback badging/selection: `surface=fallback`, `badge=Fallback required`, `BRIDGE_TARGET none`.
- новый residual fact:
  - image-generated mockup artifact для панели ещё не выпущен;
  - live fallback export через bridge/CDP всё ещё ждёт реально online client.

Новый environment-факт:
- внутри sandbox `Gtk` init и MTProto connect могли падать по ограничениям среды;
- вне sandbox тот же путь прошёл, значит это не новый code regression, а verify-ограничение среды.

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
