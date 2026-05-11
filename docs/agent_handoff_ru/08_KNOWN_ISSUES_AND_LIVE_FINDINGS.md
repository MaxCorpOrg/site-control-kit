# Known Issues And Live Findings

## Самый Новый Local Windows Smoke Rerun
Новый самый свежий факт на 2026-05-11 уже не про новый repo blocker, а про повторный live rerun текущей Windows-машины:
- rerun делался в `C:\site-control-kit-win-smoke` на `Windows 10 Pro`, `PowerShell 5.1.26100.8115`, `Python 3.14.0`;
- `python -m webcontrol runtime-env --format json --no-create` снова дал валидный JSON и подтвердил:
  - `legacy-adopted`
  - `SITECTL_TOKEN_SOURCE=token_file`
  - repo-local `.site-control-kit/generated_token.txt`
  - repo-local `.site-control-kit/local.yaml`
  - effective `state.json`, `hub.log`, `runtime_events.jsonl` в `%USERPROFILE%\.site-control-kit`
- exact Windows smoke на этом host:
  - `scripts\start_hub.cmd` поднял hub без traceback;
  - первый `.\browser.cmd status` / `.\browser.cmd tabs` увидел stale offline client;
  - extension storage уже был корректный, root cause оказался не token/runtime mismatch, а drift active unpacked-extension load state в adopted Edge debug profile;
  - live client восстановлен без code changes: runtime-only relaunch Edge debug profile с явными `--disable-extensions-except=<repo>\extension` и `--load-extension=<repo>\extension`;
  - после relaunch `browser.cmd status` и `browser.cmd tabs` снова показали online client и live tabs;
  - `.\telegram-username-collector.cmd` завершился expected fast-fail exit без traceback и без GTK окна.
- practical finding:
  - текущий remaining Windows risk теперь узкий и operational-only: drift active unpacked-extension load state в adopted Edge debug profile;
  - первый safe fix для такого сбоя — extension reload / explicit `--load-extension`, а не новый Telegram feature-cycle или shared-helper refactor.

## Самый Новый Linux Productization Layer
Новый самый свежий факт на 2026-05-11 уже уже не про Windows-only handoff, а про Linux-first product baseline:
- `.deb` build path реально landed:
  - `scripts/build_linux_deb.sh` собирает `dist/linux-deb/telegram-username-collector_0.1.0_amd64.deb`;
  - package payload подтверждён через `dpkg-deb --contents`;
  - в пакет попадают:
    - `/usr/bin/telegram-username-collector`
    - `/usr/bin/sitectl`
    - `usr/share/applications/telegram-username-collector.desktop`
    - icon sizes `64/128/256` + scalable svg
    - bundled `site-control-bridge-extension.zip`
- launcher contract расширен:
  - `telegram-username-collector --doctor`
  - `telegram-username-collector --create-desktop-shortcut`
- installed mode больше не должен писать artifact index в `/opt/...`: GUI/runtime уводят это в user-writable XDG reports/runtime paths.
- live Linux finding:
  - `DISPLAY=:0 python3 scripts/telegram_members_export_gui.py` снова реально поднял окно `Telegram Username Collector`;
  - product `--doctor` отрабатывает без GTK traceback и печатает runtime/install diagnostics.
- practical finding:
  - главный remaining Linux release risk теперь уже не build, а отсутствие clean Ubuntu install evidence:
    - Applications menu launcher
    - actual XDG runtime dirs after install
    - desktop shortcut creation after install
    - one-time extension setup from installed `/opt/...` paths
  - package размер сейчас около `52M`, основной вес даёт bundled venv + `PyQt5-Qt5` из `opentele`; это заметный, но ожидаемый tradeoff текущего v1.

## Самый Новый Windows Scope Fix
Новый самый свежий факт на 2026-05-11 уже уже не про новый runtime blocker, а про исправление handoff ambiguity:
- был риск, что Windows-агент уйдёт в слишком широкий verify-pass, потому что desktop prompt смешивал узкий Windows smoke с Linux-only и full-platform шагами;
- для этого добавлен точный runbook:
  - `docs/WINDOWS_SMOKE_HANDOFF_RU.md`
- `README.md` и `docs/INSTALL_OTHER_DEVICES_RU.md` теперь тоже ведут в этот runbook и явно включают `telegram-username-collector` в checklist;
- corrected desktop prompt теперь требует:
  - только Windows install/runtime/wrapper/fast-fail smoke;
  - никакого нового Telegram feature-cycle;
  - никакого shared-helper refactor до live Windows evidence.
- practical finding:
  - ближайший remaining release risk теперь снова чисто live:
    - real Windows wrapper smoke
    - fresh-checkout runtime dir auto-create
    - UTF-8 output on Windows console
    - live Windows fast-fail of `telegram-username-collector`
  - новый blocker в repo code этим циклом не найден.

## Самый Новый Windows Release-Confidence Dry Run
Новый самый свежий факт на 2026-05-10 уже уже не про новый code blocker, а про честно зафиксированный release-confidence gap:
- локальный verify-контур снова зелёный:
  - `python3 -m unittest discover -s tests -p 'test_*.py'` -> `294 tests OK`
  - `python3 -m webcontrol --help` -> OK
  - `python3 -m webcontrol browser --help` -> OK
  - `python3 -m webcontrol runtime-env --format json --no-create` -> OK
  - `python3 scripts/export_telegram_members_non_pii.py --help` -> OK
  - `bash scripts/bootstrap_telegram_workstation.sh --doctor` -> OK
  - `git diff --check` -> clean
- browser-side smoke на текущем Linux host:
  - без хаба `health/status/tabs` дают `Connection refused`;
  - после `bash scripts/start_hub.sh` команды `python3 -m webcontrol health`, `./browser.sh status`, `./browser.sh tabs`, `python3 -m webcontrol clients` снова рабочие;
  - visible clients в state остаются stale/offline (`is_online=false`), поэтому это smoke runtime/wrapper contract, а не live browser control confirmation.
- Windows-specific finding:
  - host остаётся Linux-only; `wine`, `cmd.exe`, `pwsh` отсутствуют;
  - exact `Windows core smoke checklist` по-прежнему требует real Windows machine/fresh checkout;
  - `telegram-username-collector` Windows fast-fail подтверждён тестом `tests/test_telegram_username_collector_launcher.py` (`3 tests OK`) и кодом launcher-а, но ещё не live-run на Windows console.
- practical finding:
  - ближайший remaining release risk теперь совсем узкий:
    - real Windows wrapper smoke
    - fresh-checkout runtime dir auto-create
    - UTF-8 output on Windows console
    - live Windows fast-fail of `telegram-username-collector`
  - новый Linux-side product blocker в этом цикле не появился.

## Самый Новый Stable Release Checkpoint
Новый самый свежий факт на 2026-05-09 уже уже не про новый blocker, а про зафиксированную publish-ready точку:
- новых code/runtime blocker-ов в этом цикле не появилось;
- current production-hardening state сохранён как stable release checkpoint;
- главный remaining risk теперь уже не Linux Telegram path, а отсутствие real Windows core smoke на живой Windows-машине;
- practical rule:
  - не начинать новый Telegram feature-cycle до прохождения `Windows core smoke checklist`
  - не тянуть в commit локальные `.codex`, `TG_CONTACT/`, `.site-control-kit`, `var/` и операторские runtime/log artifacts.

## Самый Новый Production Hardening Architecture
Новый самый свежий факт на 2026-05-09 уже уже про архитектурный repo-level слой после install/logging stabilization:
- `scripts/telegram_gui/backend.py` и `scripts/telegram_gui/ui/window.py` больше не alias-only:
  - backend/window extraction landed как реальные owner-модули;
  - `scripts/telegram_gui/app.py` теперь thin composition/shared-prelude layer;
  - старый import/test contract через `scripts.telegram_members_export_gui` сохранён зеркалированием shared globals;
- implicit legacy collector fallback `/home/max/telegram-api-collector` больше не участвует в runtime defaults:
  - GUI runtime не подставляет этот path молча;
  - `bootstrap_telegram_workstation.sh` тоже не использует его без явного env override;
- verify:
  - `python3 -m unittest discover -s tests -p 'test_*.py'` -> `294 tests OK`
  - `bash scripts/bootstrap_telegram_workstation.sh --doctor` -> OK, `legacy_helper_python=` теперь пустой без explicit env
  - `python3 -m webcontrol health` -> OK
  - live GTK startup smoke on `DISPLAY=:0` -> окно реально поднялось
- practical finding:
  - ближайший архитектурный риск теперь уже не alias-split, а просто remaining size shared helper layer в `scripts/telegram_gui/app.py`;
  - следующий maintenance-risk after this cycle — отсутствие live Windows core smoke, а не Linux packaging;
  - exact Windows smoke checklist уже зафиксирован в `README.md` и `docs/INSTALL_OTHER_DEVICES_RU.md`, так что следующий агенту не нужно придумывать verify-набор заново.

## Самый Новый Production Hardening Layer
Новый самый свежий факт на 2026-05-09 уже уже про второй repo-level production-hardening слой:
- `PyGObject` как pip dependency был реальным install blocker в clean venv и больше им не является:
  - `requirements.txt` и `pyproject.toml` больше не тянут `PyGObject`;
  - Linux GTK GUI теперь считается system dependency и проверяется через `bootstrap_telegram_workstation.sh --doctor`;
- launcher `telegram-username-collector` теперь:
  - на Windows честно сообщает, что GTK GUI не входит в Windows v1;
  - в Python-окружении без GTK bindings выдаёт понятную ошибку и отправляет в doctor path;
- hub теперь пишет structured runtime logs:
  - `logs/runtime_events.jsonl`
  - `logs/runtime_errors.jsonl`;
- Telegram GUI теперь пишет structured run sidecars:
  - `telegram_workspace/runs/<run_id>/summary.json`
  - `telegram_workspace/runs/<run_id>/artifacts.json`
  - `telegram_workspace/runs/<run_id>/events.jsonl`
- verify:
  - `python3 -m unittest discover -s tests -p 'test_*.py'` -> `293 tests OK`
  - clean install smoke:
    - `pip install -r requirements.txt` -> OK
    - `pip install -e .` -> OK
    - `sitectl --help` -> OK
    - `telegram-username-collector` -> controlled GTK fast-fail, не traceback
- practical finding:
  - install story теперь production-safe для core/browser tooling even in clean venv;
  - Linux GUI path остаётся живым через system Python + GTK;
  - новый ближайший архитектурный риск теперь не packaging, а размер/смешение обязанностей в `scripts/telegram_gui/app.py`

## Самый Новый Production Hardening Baseline
Новый самый свежий факт на 2026-05-09 уже уже про repo-level runtime/config stabilization:
- default runtime root теперь уже не должен считаться `~/.site-control-kit`:
  - канонический default теперь `./var/site-control-kit`;
  - если в системе уже есть `~/.site-control-kit`, это теперь compatibility adoption через `.site-control-kit/local.yaml`, а не silent hardcoded fallback;
- core wrappers и CLI больше не используют `local-bridge-quickstart-2026` как рабочий fallback token;
- локальный generated token теперь живёт в `.site-control-kit/generated_token.txt`;
- verify:
  - `python3 -m unittest discover -s tests -p 'test_*.py'` -> `285 tests OK`
  - `python3 -m webcontrol runtime-env --format json --no-create` -> OK
  - `bash scripts/bootstrap_telegram_workstation.sh --doctor` -> OK
  - GTK startup smoke on `DISPLAY=:0` -> window visible, startup traceback absent
- practical finding:
  - на текущей машине `bootstrap --doctor` и GUI всё ещё резолвят workspace в `~/.site-control-kit/...`, но это уже controlled compatibility mode, а не product drift;
  - `scripts/reload_bridge_extension.sh` теперь без хаба даёт короткую ошибку про недоступный hub instead of raw traceback.

## Самый Новый `ROST FARMA` Live Run
Новый самый свежий факт на 2026-05-09 уже уже про новый strongest target:
- `TG_CONTACT 4` без нового кода прошёл ещё один live export по прямому chat-row path
- preflight:
  - `bash scripts/bootstrap_telegram_workstation.sh --doctor` -> `managed_helper_ready=1`, `gtk_runtime=ok`, `selected_helper_source=managed`
  - `python3 -m webcontrol --help` -> OK
  - `python3 -m webcontrol browser --help` -> OK
  - `python3 -m unittest discover -s tests -p 'test_*.py'` -> `280 tests OK`
  - browser hub probe:
    - `bash scripts/start_hub.sh` -> OK
    - `./browser.sh status` -> OK
    - `./browser.sh tabs` -> OK
    - browser clients остались stale/offline, но это не заблокировало `Primary tdata` export path
- live run:
  - target:
    - `Чат ROST FARMA`
    - `chat_ref=-1001340567266`
    - `source_kind=live`
    - output root `/home/max/4`
  - summary:
    - `/tmp/tg_contact4_rost_farma_live_20260509T073256Z.json`
  - action log:
    - `/home/max/.site-control-kit/telegram_workspace/logs/gui_actions_tg_contact4_rost_farma_live_20260509T073256Z.log`
  - quick artifacts:
    - `/home/max/4/tg_contact4_rost_farma_quick_check_20260509T073256Z.md`
    - `/home/max/4/tg_contact4_rost_farma_quick_check_20260509T073256Z_usernames.txt`
    - `/home/max/4/tg_contact4_rost_farma_quick_check_20260509T073256Z_usernames.json`
    - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260509T073309Z.log`
  - full artifacts:
    - `/home/max/4/tg_contact4_rost_farma_full_history_20260509T073256Z.md`
    - `/home/max/4/tg_contact4_rost_farma_full_history_20260509T073256Z_usernames.txt`
    - `/home/max/4/tg_contact4_rost_farma_full_history_20260509T073256Z_usernames.json`
    - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260509T073315Z.log`
  - safe continuity dir:
    - `/home/max/4/telegram_export_чат_rost_farma/latest_safe.txt`
    - `/home/max/4/telegram_export_чат_rost_farma/latest_safe.md`
- result:
  - quick-check: `31` usernames / `400` messages
  - full-history: `2481` usernames / `269206` messages
  - live window was visible on `DISPLAY=:0`
  - save dialog was observed in both phases
  - artifact index already contains entries for both runs
- practical finding:
  - `ROST FARMA` теперь strongest confirmed target для `TG_CONTACT 4` по абсолютному числу `@username`
  - browser hub/offline clients сейчас не являются blocker-ом для `tdata-history-authors`
  - новый repo-level blocker в этом цикле не появился; path отработал end-to-end штатно
  - `security_mode` у `TG_CONTACT 4` всё ещё `Insecure local token`, но это не мешает export path

## Самый Новый Window Close Fix
Новый самый свежий факт на 2026-05-08 уже уже про сам GTK shell:
- `scripts/telegram_gui/app.py` теперь обрабатывает `close-request`
- practical behavior:
  - если export ещё идёт, закрытие окна больше не должно выглядеть как `не закрывается`;
  - вместо этого path теперь делает мягкий stop, ждёт partial-save и только потом закрывает GUI;
  - если export уже не идёт, окно закрывается сразу и приложение завершает `Gtk.Application`
- verify:
  - `python3 -m unittest tests.test_telegram_members_export_gui tests.test_telegram_tdata_helper` -> `47 tests OK`
  - `python3 -m unittest discover -s tests -p 'test_*.py'` -> `280 tests OK`
- live finding:
  - stale окно `Telegram Username Collector` без helper child было реально видно на `DISPLAY=:0`
  - после закрытия `DISPLAY=:0 xwininfo -root -tree | rg "Telegram Username Collector"` уже не видит живое окно
- practical finding:
  - close-path теперь согласован с правилом `Stop сохраняет partial contacts`

## Самый Новый `BigpharmaMarket` Retry + Partial Save
Новый самый свежий факт на 2026-05-08 уже уже про long-run retry recovery:
- `TG_CONTACT 4` получил helper-level fix для `MsgidDecreaseRetryError`
- code fix:
  - `scripts/telegram_tdata_helper.py` теперь продолжает history scan после `MsgidDecreaseRetryError` вместо fatal abort
  - неожиданные helper-исключения теперь печатают полный traceback в stderr
  - `tests/test_telegram_tdata_helper.py` покрывает recovery path
- verify:
  - `python3 -m unittest discover -s tests -p 'test_*.py'` -> `277 tests OK`
  - `python3 -m webcontrol --help` -> OK
  - `python3 -m webcontrol browser --help` -> OK
  - `./browser.sh status` -> OK
  - `./browser.sh tabs` -> OK
  - `git diff --check` -> clean
- live retry run:
  - target:
    - `Чат BigpharmaMarket`
    - `chat_ref=-1001461811598`
    - output path `/home/max/3/@BigpharmaMarket`
  - summary:
    - `/tmp/tg_contact4_bigpharmamarket_retry_live_20260508T120151Z.json`
  - action log:
    - `/home/max/.site-control-kit/telegram_workspace/logs/gui_actions_tg_contact4_bigpharmamarket_retry_live_20260508T120151Z.log`
  - progress log:
    - `/home/max/.site-control-kit/telegram_workspace/logs/live_progress_tg_contact4_bigpharmamarket_retry_20260508T120151Z.log`
  - run log:
    - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260508T120205Z.log`
  - saved artifacts:
    - `/home/max/3/@BigpharmaMarket`
    - `/home/max/3/@BigpharmaMarket_usernames.txt`
    - `/home/max/3/@BigpharmaMarket_usernames.json`
    - `/home/max/3/telegram_export_чат_bigpharmamarket/latest_safe.txt`
    - `/home/max/3/telegram_export_чат_bigpharmamarket/latest_safe.md`
- result:
  - repeated `Telegram is having internal issues MsgidDecreaseRetryError` warnings were still visible in the live stderr stream
  - unlike the old blocker run, export continued through them and reached `304900` scanned messages
  - a graceful stop then produced `interrupted=1 done=1` with `436` saved usernames
  - partial-save semantics are now live-verified, not just unit-tested
- practical finding:
  - `MsgidDecreaseRetryError` on `BigpharmaMarket` is no longer a current blocker
  - operator can stop a long `Primary tdata` run and still keep contacts in markdown plus `*_usernames.txt` and `*_usernames.json`

## Самый Новый `НаДопинге 2.0` Live Run
Новый самый свежий факт на 2026-05-08 уже уже про strongest live target:
- `TG_CONTACT 4` без нового кода прошёл ещё один live export по прямому chat-row path
- preflight:
  - `./browser.sh status` -> OK
  - `./browser.sh tabs` -> OK
  - `bash scripts/bootstrap_telegram_workstation.sh --doctor` -> `managed_helper_ready=1`, `selected_helper_source=managed`
  - backend `ensure_connected -> fetch_chats` подтвердил:
    - `НаДопинге 2.0 ЧАТ | Бодибилдинг | Фитнес | Спорт Фармакология`
    - `chat_ref=-1002465948544`
    - `source_kind=live`
- live run:
  - target:
    - `НаДопинге 2.0 ЧАТ | Бодибилдинг | Фитнес | Спорт Фармакология`
    - `chat_ref=-1002465948544`
  - summary:
    - `/tmp/tg_contact4_nadopinge20_live_20260508T103755Z.json`
  - action log:
    - `/home/max/.site-control-kit/telegram_workspace/logs/gui_actions_tg_contact4_nadopinge20_live_20260508T103755Z.log`
  - quick artifacts:
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_nadopinge20_quick_check_20260508T103755Z.md`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_nadopinge20_quick_check_20260508T103755Z_usernames.txt`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_nadopinge20_quick_check_20260508T103755Z_usernames.json`
    - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260508T103827Z.log`
  - full artifacts:
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_nadopinge20_full_history_20260508T103755Z.md`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_nadopinge20_full_history_20260508T103755Z_usernames.txt`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_nadopinge20_full_history_20260508T103755Z_usernames.json`
    - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260508T103838Z.log`
- result:
  - quick-check: `33` usernames / `400` messages
  - full-history: `1614` usernames / `187829` messages
  - live window was visible on `DISPLAY=:0`
  - save dialog was observed in both phases by the GTK harness
  - artifact index already contains entries for both runs
- practical finding:
  - `НаДопинге 2.0` теперь strongest confirmed target для `TG_CONTACT 4` по абсолютному числу `@username`
  - target не потребовал `resolve-chat` и не зависел от invite path, потому что уже виден как live row
  - новый blocker в этом цикле не появился; path отработал end-to-end штатно
  - `security_mode` у `TG_CONTACT 4` всё ещё `Insecure local token`, но это не мешает export path

## Самый Новый `FitPharma` Live Run
Новый самый свежий факт на 2026-05-08 уже уже про следующий public target:
- `TG_CONTACT 4` без нового кода прошёл ещё один live export на уже закрытом public-target path
- preflight:
  - `./browser.sh status` -> OK
  - `./browser.sh tabs` -> OK
  - `bash scripts/bootstrap_telegram_workstation.sh --doctor` -> `managed_helper_ready=1`, `selected_helper_source=managed`
  - backend-resolve `https://t.me/FitPharma` -> `FitPharma / @FitPharma / chat_ref=-1001739132808`
- live public run:
  - target:
    - `https://t.me/FitPharma`
    - `FitPharma`
    - `@FitPharma`
    - `chat_ref=-1001739132808`
  - summary:
    - `/tmp/tg_contact4_fitpharma_live_20260508T085911Z.json`
  - action log:
    - `/home/max/.site-control-kit/telegram_workspace/logs/gui_actions_tg_contact4_fitpharma_live_20260508T085911Z.log`
  - quick artifacts:
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_fitpharma_quick_check_20260508T085911Z.md`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_fitpharma_quick_check_20260508T085911Z_usernames.txt`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_fitpharma_quick_check_20260508T085911Z_usernames.json`
    - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260508T085955Z.log`
  - full artifacts:
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_fitpharma_full_history_20260508T085911Z.md`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_fitpharma_full_history_20260508T085911Z_usernames.txt`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_fitpharma_full_history_20260508T085911Z_usernames.json`
    - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260508T090006Z.log`
- result:
  - quick-check: `34` usernames / `400` messages
  - full-history: `253` usernames / `28509` messages
  - live window was visible on `DISPLAY=:0`
  - save dialog was observed in both phases by the GTK harness
  - artifact index already contains entries for both runs
- practical finding:
  - `FitPharma` теперь подтверждён как продуктивный `TG_CONTACT 4` target, хотя и с заметно меньшей плотностью `@username`, чем `@cosmetologna`
  - новый blocker в этом цикле не появился; public-target path отработал end-to-end штатно
  - `security_mode` у `TG_CONTACT 4` всё ещё `Insecure local token`, но это не мешает export path

## Самый Новый Public Resolve + Bootstrap Fix
Новый самый свежий факт на 2026-05-08 уже уже про public target path:
- `TG_CONTACT 4` теперь уже имеет рабочий helper/backend путь не только для invite, но и для public `t.me/<slug>` / `@username`
- code fix:
  - `scripts/telegram_tdata_helper.py` получил `resolve-chat`
  - `scripts/telegram_gui/app.py` получил `resolve_tdata_chat_target(...)` и single-window action `Открыть чат по ссылке / @username`
  - GUI helper calls теперь сериализуются lock-ом, чтобы deep preflight и `connect` не ломали друг другу session access
  - GUI run history теперь пишет entries в `artifacts/telegram_exports/INDEX.md`
- Linux install finding:
  - `scripts/bootstrap_telegram_workstation.sh --doctor` уже показывает `managed_helper_ready=1`
  - `selected_helper_source=managed`
  - текущий helper python уже идёт из `~/.site-control-kit/telegram_workspace/managed_helper/.venv/bin/python`
- live public run:
  - target:
    - `https://t.me/cosmetologna`
    - `Косметолог на Миллион`
    - `@cosmetologna`
    - `chat_ref=-1001506021345`
  - summary:
    - `/tmp/tg_contact4_cosmetologna_live_20260508T082312Z.json`
  - action log:
    - `/home/max/.site-control-kit/telegram_workspace/logs/gui_actions_tg_contact4_cosmetologna_live_20260508T082312Z.log`
  - quick artifacts:
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_cosmetologna_quick_check_20260508T082312Z.md`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_cosmetologna_quick_check_20260508T082312Z_usernames.txt`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_cosmetologna_quick_check_20260508T082312Z_usernames.json`
    - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260508T082357Z.log`
  - full artifacts:
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_cosmetologna_full_history_20260508T082312Z.md`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_cosmetologna_full_history_20260508T082312Z_usernames.txt`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_cosmetologna_full_history_20260508T082312Z_usernames.json`
    - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260508T082408Z.log`
- result:
  - quick-check: `117` usernames / `400` messages
  - full-history: `1534` usernames / `13055` messages
  - live window was visible on `DISPLAY=:0`
  - save dialog was observed in both phases by the GTK harness
- practical finding:
  - старый race `Portable профиль найден, но helper не смог открыть сессию` уже больше не считается текущим blocker после helper serialization
  - `https://t.me/cosmetologna` теперь подтверждён как продуктивный public target для `history-authors` path
  - `security_mode` у `TG_CONTACT 4` всё ещё `Insecure local token`, но это уже не blocker для export path

## Самый Новый Invite Fix
Новый самый свежий факт на 2026-05-07 уже уже про invite-path:
- `TG_CONTACT 4` теперь уже имеет рабочий helper/backend путь для `t.me/+invite`
- code fix:
  - `scripts/telegram_tdata_helper.py` получил `join-invite`
  - `scripts/telegram_gui/app.py` получил `join_tdata_invite(...)`
- verify:
  - `python3 -m unittest discover -s tests -p 'test_*.py'` -> `265 tests OK`
- live invite:
  - `http://t.me/+6FMgmFJCh0I4M2Yy`
  - `joined=False`
  - `already_member=True`
  - resolved chat: `RIVIVE LIFE Chat` / `chat_ref=-1002269737802`
- summary:
  - `/tmp/tg_contact4_invite_live_20260507T123136Z.json`
- action log:
  - `/home/max/.site-control-kit/telegram_workspace/logs/gui_actions_tg_contact4_invite_live_20260507T123136Z.log`
- quick artifacts:
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_invite_quick_check_20260507T123136Z.md`
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_invite_quick_check_20260507T123136Z_usernames.txt`
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_invite_quick_check_20260507T123136Z_usernames.json`
  - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260507T123156Z.log`
- full artifacts:
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_invite_full_history_20260507T123136Z.md`
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_invite_full_history_20260507T123136Z_usernames.txt`
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_invite_full_history_20260507T123136Z_usernames.json`
  - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260507T123200Z.log`
- result:
  - quick-check: `56` usernames / `400` messages
  - full-history: `1158` usernames / `62029` messages
- practical finding:
  - invite-gap now is no longer a blocker
  - this exact invite resolved to an already joined productive chat, not to a brand-new membership flow
  - no runtime fix was needed during the live export itself after the code change

## Самый Новый Продуктивный Чат
Новый самый свежий факт на 2026-05-07 уже уже про productive rerun:
- `TG_CONTACT 4` заново прошёл живой export по `@cosmochatrussia`
- current operator state не менялся:
  - `default_user = TG_CONTACT 4`
  - runtime/helper target остался на `runtime/helper_workdir/tdata`
- summary:
  - `/tmp/tg_contact4_cosmochatrussia_repeat_20260507T094441Z.json`
- action log:
  - `/home/max/.site-control-kit/telegram_workspace/logs/gui_actions_tg_contact4_cosmochatrussia_repeat_20260507T094441Z.log`
- quick artifacts:
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_cosmochatrussia_repeat_quick_check_20260507T094441Z.md`
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_cosmochatrussia_repeat_quick_check_20260507T094441Z_usernames.txt`
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_cosmochatrussia_repeat_quick_check_20260507T094441Z_usernames.json`
  - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260507T094455Z.log`
- full artifacts:
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_cosmochatrussia_repeat_full_history_20260507T094441Z.md`
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_cosmochatrussia_repeat_full_history_20260507T094441Z_usernames.txt`
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_cosmochatrussia_repeat_full_history_20260507T094441Z_usernames.json`
  - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260507T094504Z.log`
- result:
  - quick-check: `status=done`, `safe_count=103`, `history_messages_scanned=400`
  - full-history: `status=done`, `safe_count=1486`, `history_messages_scanned=9351`
  - during full-history Telegram emitted transient `MsgidDecreaseRetryError`, but the run recovered and finished normally
- practical finding:
  - `@cosmochatrussia` снова подтверждён как продуктивный TG_CONTACT 4 target
  - `@slivcosmo` zero-output был связан с контентом именно того чата, а не с поломкой профиля

## Самый Новый Operator Pivot
Новый самый свежий факт на 2026-05-07 уже уже про operator state:
- вся текущая работа теперь закреплена только за `TG_CONTACT 4`
- `~/.site-control-kit/telegram_workspace/registry/users.json` уже переключён на `default_user = TG_CONTACT 4`
- `TG_CONTACT 2`, `TG_CONTACT 3`, `@AK-LIVE`, `@AK-ADOPTED`, `Слот 1`, `Слот 2` не удалены, но больше не считаются текущим рабочим профилем
- cleanup legacy rows не делался и остаётся отдельным шагом
- повторный live GTK verify снова прошёл только через `TG_CONTACT 4`:
  - summary:
    - `/tmp/tg_contact4_only_slivcosmo_live_verify_20260507T084752Z.json`
  - action log:
    - `/home/max/.site-control-kit/telegram_workspace/logs/gui_actions_tg_contact4_only_slivcosmo_live_verify_20260507T084752Z.log`
  - quick artifacts:
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_only_slivcosmo_quick_check_20260507T084752Z.md`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_only_slivcosmo_quick_check_20260507T084752Z_usernames.txt`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_only_slivcosmo_quick_check_20260507T084752Z_usernames.json`
    - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260507T084840Z.log`
  - full artifacts:
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_only_slivcosmo_full_history_20260507T084752Z.md`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_only_slivcosmo_full_history_20260507T084752Z_usernames.txt`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_only_slivcosmo_full_history_20260507T084752Z_usernames.json`
    - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260507T084855Z.log`
  - result:
    - rerun summary сам по себе ещё отражает historical pre-pivot `TG_CONTACT 2`, потому что registry promotion была записана после него
    - current workspace state уже другой: `default_user = TG_CONTACT 4`
    - quick-check: `status=done`, `safe_count=0`, `history_messages_scanned=400`
    - full-history: `status=done`, `safe_count=0`, `history_messages_scanned=1358`
    - runtime/helper path снова не деградировал и остался на `runtime/helper_workdir/tdata`
- practical finding:
  - проблема на `@slivcosmo` уже не в профиле и не в runtime, а в том, что этот чат даёт `0` usernames для текущего extraction path
  - следующий practical шаг теперь либо новый chat target на `TG_CONTACT 4`, либо отдельный cleanup legacy-профилей
## Самый Важный Актуальный Live-Факт
Новый самый свежий факт на 2026-05-07 уже про fixed runtime path:
- `TG_CONTACT 4` прошёл реальный GTK live-cycle `launch -> close -> refresh -> connect -> @slivcosmo -> Quick Check -> Full History` на `DISPLAY=:0`:
  - summary:
    - `/tmp/tg_contact4_slivcosmo_live_verify_20260507T083138Z.json`
  - action log:
    - `/home/max/.site-control-kit/telegram_workspace/logs/gui_actions_tg_contact4_slivcosmo_live_verify_20260507T083138Z.log`
  - key runtime fact:
    - `portable_profile_launch ... workdir=/home/max/.site-control-kit/telegram_workspace/PortableProfiles/TelegramPortable-tg-contact-4/runtime/launch_workdir`
    - `chats_loaded tdata dir=/home/max/.site-control-kit/telegram_workspace/PortableProfiles/TelegramPortable-tg-contact-4/runtime/helper_workdir/tdata`
    - оба export run тоже уже шли через helper clone, а не через канонический `TelegramForcePortable/tdata`
  - quick artifacts:
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_slivcosmo_quick_check_20260507T083138Z.md`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_slivcosmo_quick_check_20260507T083138Z_usernames.txt`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_slivcosmo_quick_check_20260507T083138Z_usernames.json`
    - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260507T083217Z.log`
  - full artifacts:
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_slivcosmo_full_history_20260507T083138Z.md`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_slivcosmo_full_history_20260507T083138Z_usernames.txt`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_slivcosmo_full_history_20260507T083138Z_usernames.json`
    - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260507T083226Z.log`
  - result:
    - `default_user` остался `TG_CONTACT 2`
    - save dialog реально открылся в обоих фазах
    - quick-check: `status=done`, `safe_count=0`, `history_messages_scanned=400`
    - full-history: `status=done`, `safe_count=0`, `history_messages_scanned=1358`
    - `security_mode=Insecure local token`
- Новый практический вывод уже другой:
  - launch-triggered `OpenTeleException: No account has been loaded` на этом fixed path больше не воспроизвёлся;
  - главный content residual теперь в том, что `@slivcosmo` для текущего `history-authors` path даёт `0` usernames даже при рабочем flow.

## Более Ранний Актуальный Live-Факт
Новый самый свежий факт на 2026-05-07 уже не blocker-only:
- `TG_CONTACT 4` реально собрал `@username` по `@cosmochatrussia` (`-1001909598727`) через реальное GTK окно:
  - quick-check artifacts:
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_cosmochatrussia_quick_check_20260507T073523Z.md`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_cosmochatrussia_quick_check_20260507T073523Z_usernames.txt`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_cosmochatrussia_quick_check_20260507T073523Z_usernames.json`
    - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260507T073607Z.log`
    - `/home/max/.site-control-kit/telegram_workspace/logs/gui_actions_tg_contact4_cosmochatrussia_live_20260507T073523Z_20260507T073540Z.log`
  - quick result:
    - `status=done`
    - `safe_count=103`
    - `history_messages_scanned=400`
- Реальный GTK `Full History` на том же live dialog row тоже уже завершён:
  - summary:
    - `/tmp/tg_contact4_cosmochatrussia_full_only_20260507T074001Z.json`
  - artifacts:
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_cosmochatrussia_full_history_20260507T074001Z.md`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_cosmochatrussia_full_history_20260507T074001Z_usernames.txt`
    - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_cosmochatrussia_full_history_20260507T074001Z_usernames.json`
    - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260507T074039Z.log`
    - `/home/max/.site-control-kit/telegram_workspace/logs/gui_actions_tg_contact4_cosmochatrussia_full_only_20260507T074001Z_20260507T074016Z.log`
  - full result:
    - `status=done`
    - `safe_count=1486`
    - `history_messages_scanned=9341`
    - `security_mode=Insecure local token`
- Новый critical residual уже другой:
  - первый combined pass `quick -> full` после portable launch был нестабилен;
  - quick-check успел сохраниться, но immediate full-history path дал helper failure `OpenTeleException: No account has been loaded`;
  - direct helper probes на managed `tdata` после этого тоже ломались тем же способом, пока `tdata` не была снова восстановлена из source ZIP;
  - drifted copy сохранена как `/home/max/.site-control-kit/telegram_workspace/PortableProfiles/TelegramPortable-tg-contact-4/TelegramForcePortable/tdata.backup_20260507T073936Z`;
  - успешный full-history pass прошёл только на втором GTK run без повторного portable launch, так что главный оставшийся live-risk теперь именно launch-triggered runtime drift у `TG_CONTACT 4`.

Более ранний свежий факт на 2026-05-07:
- обязательный verify и browser contour снова подняты:
  - `python3 -m unittest discover -s tests -p 'test_*.py'` -> `258 tests OK`
  - `python3 -m webcontrol --help` -> OK
  - `python3 -m webcontrol browser --help` -> OK
  - `./start-browser.sh` снова поднял hub, а `./browser.sh status` / `./browser.sh tabs` снова прошли по online browser client
- новый `TG_CONTACT 4` import fact:
  - managed profile уже создан как `/home/max/.site-control-kit/telegram_workspace/PortableProfiles/TelegramPortable-tg-contact-4`
  - `registry/users.json` уже содержит row `TG_CONTACT 4`, а `default_user` остаётся `TG_CONTACT 2`
  - current selector/backend list теперь показывает `TG_CONTACT 2`, `@AK-ADOPTED`, `@AK-LIVE`, `TG_CONTACT 3`, `TG_CONTACT 4`, `Слот 1`, `Слот 2`
  - `/home/max/.site-control-kit/telegram_workspace/logs/gui_actions_tg_contact4_first_live_20260507T065536Z_20260507T065600Z.log`
  - этот action log уже содержит `portable_profile_imported`, `portable_profile_account_synced`, `client_ready portable_tdata ...`, `chats_loaded ... count=30`
- новый `TG_CONTACT 4` blocker fact:
  - `/tmp/tg_contact4_direct_live_20260507T070439Z.json`
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact4_runtime_blocker_20260507T070439Z.md`
  - `/home/max/.site-control-kit/telegram_workspace/logs/gui_actions_tg_contact4_direct_live_20260507T070439Z_20260507T070446Z.log`
  - direct GTK re-check остановился в `ensure_connected()` с `PrimarySurfaceBlocked`
  - repeated direct probe now gives `prepare_portable_runtime() -> unauthorized`
  - detail: `Portable профиль найден, но helper не смог открыть сессию. Откройте этот Telegram Desktop профиль и дождитесь полной загрузки.`
  - новых export sidecars для blocker-pass нет, потому что export не стартовал
- новый `TG_CONTACT 2` live fact:
  - `/tmp/tg_contact2_live_walkthrough_20260507T061343Z.json`
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact2_live_walkthrough_20260507T061343Z.md`
  - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260507T061359Z.log`
  - `/home/max/.site-control-kit/telegram_workspace/logs/gui_actions_tg_contact2_live_walkthrough_20260507T061343Z_20260507T061343Z.log`
  - реальное GTK окно снова было видно на `DISPLAY=:0`;
  - save dialog снова реально открылся;
  - export на `Патрик Stars | Звёзды и подарки бесплатно` (`7996790736`) завершился `status=done`, `safe_count=1`, `history_messages_scanned=12`.
- новый `TG_CONTACT 2` known-only guard fact:
  - `/tmp/tg_contact2_bigpharma_known_guard_20260507T061415Z.json`
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact2_bigpharma_known_guard_20260507T061415Z.md`
  - `/home/max/.site-control-kit/telegram_workspace/logs/gui_actions_tg_contact2_bigpharma_known_guard_20260507T061415Z_20260507T061416Z.log`
  - `Чат BigpharmaMarket` снова показывается как `known`;
  - export на этом профиле снова режется заранее ожидаемой operator-ошибкой про `known chat` и отсутствие live dialog row;
  - sidecars по этому сценарию не появились, потому что export не стартовал.
- новый `TG_CONTACT 3` blocker fact:
  - `/tmp/tg_contact3_bigpharma_blocker_20260507T061738Z.json`
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact3_bigpharma_blocker_20260507T061738Z.md`
  - текущий direct probe теперь даёт `prepare_portable_runtime() -> unauthorized`;
  - detail: `Portable профиль найден, но helper не смог открыть сессию... tdata helper timed out after 12s: list-chats /home/max/.site-control-kit/telegram_workspace/PortableProfiles/TelegramPortable-tg-contact-3/TelegramForcePortable/tdata`;
  - повторный launch portable binary не вернул профиль в `ready`, то есть старый success `2026-05-05` уже нельзя считать current live truth.
- новый selector fact:
  - live selector сейчас показывает `TG_CONTACT 2`, `@AK-ADOPTED`, `@AK-LIVE`, `TG_CONTACT 3`, `Слот 1`, `Слот 2`.
- новый automation residual:
  - automated GTK harness после успешного export поймал `Gtk-CRITICAL gtk_box_remove ...`;
  - это не сломало export и не помешало записи артефактов, но это уже отдельный warning для будущей GUI automation.

Более ранний свежий факт на 2026-05-05:
- уже реализован `Known Chat Guard + TG_CONTACT 3 Bigpharma Live Path`:
  - `/tmp/telegram_live_walkthrough_20260505T131711Z.json`
  - `/tmp/telegram_tg_contact3_live_20260505T131952Z.json`
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact2_live_walkthrough_20260505T131711Z.md`
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact3_bigpharma_quick_check_20260505T131952Z.md`
  - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260505T131726Z.log`
  - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260505T132011Z.log`
- новый `TG_CONTACT 2` fact:
  - реальный current-list walkthrough на `DISPLAY=:0` прошёл `startup -> connect -> choose chat -> save dialog -> Quick Check`;
  - live-чат `Патрик Stars | Звёзды и подарки бесплатно` (`7996790736`) дал `status=done`, `safe_count=1`, `history_messages_scanned=9`.
- новый known-only guard fact:
  - `Чат BigpharmaMarket` может показываться у `TG_CONTACT 2` как synthetic `known chat`;
  - но export на этом профиле теперь заранее блокируется понятной operator-ошибкой, если чат не появился в текущем live dialog list;
  - это закрывает старый поздний traceback `Could not find the input entity for PeerChannel(channel_id=1461811598)`.
- новый `TG_CONTACT 3` fact:
  - `/home/max/site-control-kit/TG_CONTACT/3/tdata-20260505T131440Z-3-001.zip` импортирован как managed profile `TG_CONTACT 3`;
  - real GTK walkthrough на `DISPLAY=:0` прошёл `select TG_CONTACT 3 -> connect -> BigpharmaMarket -> save dialog -> Quick Check`;
  - итог `status=done`, `safe_count=14`, `history_messages_scanned=400`.
- новый safety fact:
  - `ss -ltnp '( sport = :8765 )'` после этого цикла по-прежнему пуст, так что listener на `:8765` не трогался.
- новый practical residual:
  - `TG_CONTACT 2` всё ещё не Bigpharma profile и не должен использоваться там как direct export target;
  - `TG_CONTACT 3` уже рабочий Bigpharma profile, но пока остаётся на `Insecure local token`.

Более ранний live-факт того же дня:
- уже реализован `TG_CONTACT 2 Non-Blocking GUI Startup`:
  - `/tmp/telegram_gui_nonblocking_smoke.json`
  - `/tmp/telegram_gui_nonblocking_smoke2.json`
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact2_nonblocking_start_quick_check_20260505T123731Z.md`
  - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260505T123731Z.log`
  - `/home/max/.site-control-kit/telegram_workspace/logs/live_verify_export_20260505.log`
- новый startup/live fact:
  - реальное GTK окно подтвердилось на `DISPLAY=:0` через `xwininfo -root -tree | rg "Telegram Username Collector Smoke"`;
  - окно больше не падает на startup из-за missing adopted profile;
  - `@AK-ADOPTED` остаётся видимым как `missing` с detail про `/tmp/telegram-portable-adopt-live`, а не ломает всю панель;
  - `TG_CONTACT 2` остаётся selected/default profile c `Local secure token` и `Primary tdata`.
- новый connect/list/export fact:
  - live `ensure_connected -> fetch_chats` на `TG_CONTACT 2` вернул `19` чатов;
  - quick-check export на чате `астра | языки и темы` завершился `status=done`, `safe_count=0`, `history_messages_scanned=400`.
- новый selector fact:
  - duplicate `Слот 1` уже убран и current account list снова one-per-slot.
- новый safety fact:
  - `ss -ltnp '( sport = :8765 )'` до и после smoke был пустым, так что этот цикл не трогал listener на `:8765`.
- новый practical residual:
  - startup/freeze root cause закрыт;
  - content-level next step не поменялся: нужен целевой чат с ожидаемыми `@username`, потому что и новый quick-check снова дал `0/400`.

Новый самый свежий факт на 2026-05-04:
- уже реализован `TG_CONTACT 2 As New Primary Portable Profile`:
  - `/tmp/telegram_tg_contact2_primary_live_20260504T125745Z.json`
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/tg_contact2_primary_quick_check_20260504T125745Z.md`
  - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260504T125849Z.log`
  - `/home/max/.site-control-kit/telegram_workspace/logs/gui_actions_tg_contact2_primary_20260504T125745Z.log`
- новый primary-profile live fact:
  - `/home/max/site-control-kit/TG_CONTACT/2/tdata-20260430T111415Z-3-001.zip` реально импортирован как managed profile `TG_CONTACT 2`;
  - managed directory создан как `/home/max/.site-control-kit/telegram_workspace/PortableProfiles/TelegramPortable-tg-contact-2`;
  - `TG_CONTACT 2` стал `default_user`, selected account и selected portable profile;
  - security mode переключён в `Local secure token`;
  - quick-check export на `Primary tdata` завершился `status=done`, `safe_count=0`, `history_messages_scanned=400`.
- новый cleanup/remove fact:
  - inline action `Убрать из панели` теперь реально работает live;
  - managed temporary profile `@AK-GUI-WALK` удалён из panel/registry и его workspace directory больше не существует;
  - adopted temporary profile `@AK-ADOPT-WALK` удалён из panel/registry, но `/tmp/telegram-portable-real-window-adopt-20260504t121610z` остался на диске;
  - selectors после cleanup больше показывают только:
    - `TG_CONTACT 2`
    - `@AK-ADOPTED`
    - `@AK-LIVE`
    - `Слот 1`
    - `Слот 2 · portable ZIP`
- новый practical residual:
  - для текущего оператора default profile теперь уже зафиксирован и больше не должен дрейфовать между временными live-check profiles;
  - content-level verify для `TG_CONTACT 2` пока был только quick-check на чат с `safe_count=0`, то есть следующий live export стоит делать уже на целевом чате с ожидаемыми `@username`.
- уже реализован `Portable Profile Orchestration v1`:
  - `/tmp/telegram_portable_profiles_live.json`
  - `/tmp/telegram_portable_profiles_adopt_live.json`
  - `/tmp/telegram_portable_profiles_gui_probe.json`
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/portable_profile_live_quick_check.md`
- новый portable-profile live fact:
  - managed profile `PortableProfiles/TelegramPortable-ak-live` реально создан из `TG_CONTACT` ZIP и зарегистрирован как account `@AK-LIVE`;
  - quick-check export на `Чат BigpharmaMarket` завершился `status=done`, `safe_count=12`, `history_messages_scanned=400`;
  - external folder `/tmp/telegram-portable-adopt-live` принят как adopted portable profile, получил `portable-profile.json` и workspace-link `PortableProfiles/LinkedPortable-ak-adopted`.
- новый GUI/profile-first fact:
  - GTK panel probe на `DISPLAY=:0` увидел `4` portable profiles в одном dropdown;
  - selected profile `@AK-ADOPTED`, selected account `@AK-ADOPTED`, `surface_badge=Primary tdata`.
- новый real-window fact:
  - `/tmp/telegram_portable_profiles_real_window_walkthrough_20260504T121610Z.json`
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/portable_profile_real_window_walkthrough_20260504T121610Z.md`
  - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260504T121716Z.log`
  - `/home/max/.site-control-kit/telegram_workspace/logs/gui_actions_portable_profiles_real_window_20260504T121610Z.log`
  - полный GTK/operator flow теперь закрыт live: import zip -> adopt folder -> launch profile -> refresh status -> connect -> list chats -> export;
  - imported managed profile `@AK-GUI-WALK` дал `status=done`, `safe_count=12`, `history_messages_scanned=400` на `Чат BigpharmaMarket`.
- новый residual:
  - live portable-panel walkthrough уже закрыт;
  - но imported/adopted profiles по умолчанию пока живут на `Insecure local token`, если их будут использовать за пределами чистого `Primary tdata` path.
- уже реализован `Portable tdata Restore v1`:
  - `/tmp/telegram_portable_restore_live_recovered.json`
  - `/tmp/telegram_portable_restore_safety.json`
  - `/tmp/telegram_portable_restore_gui_headless.json`
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/portable_restore_slot2_quick_check.md`
- новый portable live fact:
  - slot `2` импортирован из `/home/max/site-control-kit/TG_CONTACT` как `Слот 2 · portable ZIP`;
  - runtime clone `accounts/2/runtime/portable_tdata` готов и авторизован;
  - runtime alias реально создан как `accounts/2/runtime/tdata -> portable_tdata`;
  - quick-check export на `Чат BigpharmaMarket` дал `status=done`, `safe_count=12`, `history_messages_scanned=400`.
- новый safety fact:
  - `import + runtime rebuild` не изменили ни repo-local `TG_CONTACT`, ни `~/telegram-api-collector/tdata_import/tdata`; это подтверждено `/tmp/telegram_portable_restore_safety.json`.
- старый GUI residual для `Portable tdata Restore v1`:
  - scripted real-window GTK smoke тогда убивался средой;
  - теперь этот gap закрыт уже на следующем слое `Portable Profile Orchestration v1` через `/tmp/telegram_portable_profiles_real_window_walkthrough_20260504T121610Z.json`.
- уже реализован `Telegram Workstation v1.3 Secondary Surface Live Closure`:
  - `/tmp/telegram_workstation_v13_backend_live.json`
  - `/tmp/telegram_workstation_v13_gui_fallback.json`
  - `/tmp/telegram_workstation_v13_screen.png`
  - `/home/max/.site-control-kit/telegram_workspace/live_smokes/v13_fallback_live_status.md`
- новый fallback fact:
  - `bridge_probe=foreign_hub` и `bridge_prepare=foreign_hub`;
  - внешний listener `pid=17766` на `:8765` использует другой token и остаётся warning-only path;
  - `cdp_prepare=telegram_auth_required`, потому что dedicated profile открывает Telegram Web QR login page;
  - fallback-card теперь показывает эти два blocker'а даже при `Primary tdata`.
- новый practical residual:
  - полноценный secondary export всё ещё не подтверждён не из-за нового code regression, а из-за host-state blockers:
    - foreign hub на `:8765` для bridge;
    - operator login required в dedicated CDP profile.
- уже реализован `Telegram Workstation v1.2 Secure Token Operator Setup`:
  - `/tmp/telegram_workstation_v12_gui_live.json`
  - `/tmp/telegram_workstation_v12_foreign_hub_warning.json`
- новый secure-token fact:
  - реальный slot `1` больше не использует quickstart fallback;
  - `users.json` теперь содержит только `secret_ref`, а `accounts/1/keys/api_token.txt` пуст;
  - GTK quick-check через реальное окно записан как `security_mode=Local secure token`, `safe_count=12`, `history_messages_scanned=400`.
- новый warning-card fact:
  - на хосте всё ещё живёт внешний listener `pid=17766` на `:8765`;
  - security card остаётся видимой даже в secure-state и явно пишет, что этот внешний hub/process использует другой token;
  - destructive kill/restart path для foreign listener не предлагается.
- уже есть следующий live слой `Telegram Workstation v1.1 Hardening + Panel UX`:
  - `/tmp/telegram_workstation_v11_backend_live.json`
  - `/tmp/telegram_workstation_v11_backend_full_stop_retry.json`
  - `/tmp/telegram_workstation_v11_gui_live.json`
  - `/tmp/telegram_workstation_v11_foreign_port_verify.json`
- live на реальном `~/.site-control-kit/telegram_workspace` уже подтверждён:
  - backend quick-check -> `status=done`, `safe_count=31`, `history_messages_scanned=400`
  - backend full-history stop verify -> `status=partial`, `safe_count=30`, `history_messages_scanned=300`, `interrupted=true`
  - GTK walkthrough через реальное окно -> visible progress `250/27`, stop, partial save `300/30`
- новый security/live-fact:
  - listener `pid=17766` на `:8765` пережил вызов `backend._ensure_hub()` с неправильным токеном;
  - значит новый hardening path действительно не убивает чужой/чуждо-токенный hub автоматически.
- новый token-hygiene fact:
  - `users.json` уже без `"token"` field;
  - `rg` по `logs/runs/state/live_smokes` не нашёл quickstart-token string;
  - child bridge script в `ps` идёт без token в argv.
- новый residual risk:
  - secure-token setup уже закрыт для slot `1`, но live fallback export через bridge/CDP всё ещё не подтверждён из-за отсутствия online client.
- `Telegram Workstation v1` уже живой:
  - outside sandbox live backend quick-check на `-1001753733827` завершился успешно;
  - результат: `/tmp/telegram_workstation_backend_smoke_ok.md`;
  - `safe_count=31`, `history_messages_scanned=400`, `interrupted=false`;
  - live GTK smoke через само окно тоже прошёл:
    - `/tmp/telegram_workstation_gui_smoke_ok.md`
    - `/tmp/tg_workstation_gui_ws_escalated/logs/export_run_20260504T062030Z.log`
    - `safe_count=31`, `history_messages_scanned=400`, `interrupted=false`.
  - outside sandbox live full-history stop verify тоже прошёл:
    - `/tmp/telegram_workstation_full_history_ok.md`
    - `/home/max/.site-control-kit/telegram_workspace/logs/export_run_20260504T064547Z.log`
    - `/tmp/tg_full_history_backend.log`
    - `history_messages_scanned=85300`, `safe_count=1032`, `interrupted=true`
    - partial-result contract реально дошёл до `runs/index.jsonl` и `state/last_session.json`.
- Новый fallback/live-fact этого же цикла:
  - реальный hub отвечает, но текущие bridge-clients были `is_online=false`;
  - поэтому полноценный bridge export в этом цикле не гнали;
  - при этом adapter smoke против live hub подтвердил fallback routing: `surface=fallback`, `badge=Fallback required`, `BRIDGE_TARGET none`.
- Новый environment-факт этого же verify:
  - inside sandbox `Gtk` мог падать с `Gtk couldn't be initialized`;
  - inside sandbox MTProto connect мог падать с `PermissionError: [Errno 1] Operation not permitted`;
  - вне sandbox тот же код прошёл, значит это verify-ограничение среды, а не новый регресс в коде.
- Новый UX/race факт:
  - поздний stop-click близко к завершению helper-run мог создавать ненужную гонку;
  - в GUI это уже зажато: если приходит `PROGRESS ... done=1`, stop-button сразу выключается.

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
