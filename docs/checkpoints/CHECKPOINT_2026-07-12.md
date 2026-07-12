# Checkpoint 2026-07-12

## Branch And Remote
- Branch: `main`
- Remote: `origin git@github.com:MaxCorpOrg/site-control-kit.git`
- Status before commit: `main...origin/main`

## Scope
- Stabilized the ready `Telegram Username Collector` desktop package after live GUI/log analysis.
- Added GUI import for Telegram API ID/Hash for selected slot/TG_CONTACT profiles.
- Added manageable quick chat templates so built-in cosmetology shortcuts are not confused with live account access.
- Kept Telegram collection/export semantics unchanged.
- Rebuilt the ignored `.deb` artifact and refreshed the desktop install kit.

## Code Changes
- Linux installed wrappers now execute from app root:
  - `packaging/linux/telegram-username-collector.wrapper.sh`
  - `packaging/linux/sitectl.wrapper.sh`
- Installed-mode doctor now uses `SITECTL_PRODUCT_APP_ROOT` as the product project root.
- `webcontrol runtime-env --format json` now redacts `SITECTL_TOKEN` by default.
- GUI now writes action log entries for startup and profile refresh:
  - `app_started`
  - `profiles_refreshed accounts=... ready=...`
- Launcher handles Ctrl+C as a clean interrupt:
  - exit code `130`
  - no traceback.
- GTK profile section now has `Импорт API`.
- API import saves Telegram API credentials locally:
  - `telegram_workspace/accounts/<N>/keys/api_id.txt`
  - `telegram_workspace/accounts/<N>/keys/api_hash.txt`
- Backend resolves slots from workspace paths and `TG_CONTACT N` labels.
- Backend passes saved credentials to tdata helper as `--api-id/--api-hash`.
- `scripts/telegram_tdata_helper.py` accepts optional `--api-id/--api-hash` and only uses custom `APIData` when both are present.
- API Hash is not logged to action logs.
- Quick chat UX:
  - templates are labelled as local shortcuts, not access proof;
  - `Добавить шаблон`;
  - `Скрыть стандартные` / `Показать стандартные`;
  - `Сбросить стандартные`;
  - per-standard-row `Скрыть`;
  - per-pinned-row `Открепить`;
  - settings stored in `telegram_workspace/state/quick_chats.json`.

## Installer Artifacts
- Repo build artifact:
  - `/home/max/site-control-kit/dist/linux-deb/telegram-username-collector_0.1.0_amd64.deb`
- Desktop install kit:
  - `/home/max/Рабочий стол/telegram-username-collector-install-kit/telegram-username-collector_0.1.0_amd64.deb`
  - `/home/max/Рабочий стол/telegram-username-collector-install-kit/telegram-username-collector_0.1.0_amd64.deb.sha256`
  - `/home/max/Рабочий стол/telegram-username-collector-install-kit/INSTALL_RU.md`
- SHA256:
  - `624676f1ae4489019b1056847441e2549df5270ee1f70820ffa6cdfe2fa55d97`

## Live Smoke
- Final smoke folder:
  - `/home/max/Рабочий стол/telegram-program-live-smoke-20260712T065625Z-final`
- Key evidence:
  - `/home/max/Рабочий стол/telegram-program-live-smoke-20260712T065625Z-final/screenshot-hover-refresh.png`
  - `/home/max/.local/share/site-control-kit/telegram_workspace/logs/gui_actions_20260712T065533Z.log`
- Confirmed:
  - build-root installed-mode GUI opens on `DISPLAY=:0`
  - X11 scroll works
  - hover feedback on `Обновить профили` is visible
  - click on `Обновить профили` completes without panel crash
  - action log contains `app_started` and `profiles_refreshed`
  - Ctrl+C exits with code `130` and no traceback

## Verify
- `python3 -m unittest discover -s tests -p 'test_*.py'` -> `335 tests OK`, `2 skipped`
- `./scripts/verify.sh` -> OK
- `python3 -m webcontrol --help` -> OK
- `python3 -m webcontrol browser --help` -> OK
- `python3 -m unittest tests.test_telegram_gui_backend_features tests.test_telegram_tdata_helper -v` -> `54 tests OK`
- `python3 -m unittest tests.test_telegram_gui_run_history tests.test_telegram_members_export_gui -v` -> targeted quick-chat coverage OK
- `python3 -m py_compile scripts/telegram_tdata_helper.py scripts/telegram_gui/backend.py scripts/telegram_gui/ui/window.py` -> OK
- `python3 -m py_compile webcontrol/settings.py webcontrol/cli.py scripts/telegram_product_runtime.py scripts/telegram_username_collector_launcher.py scripts/telegram_gui/app.py scripts/telegram_gui/backend.py` -> OK
- `python3 -m webcontrol runtime-env --format json --no-create` -> redaction OK
- `dpkg-deb -x` package content check -> OK
- build-root installed-mode `telegram-username-collector --doctor` -> OK with expected `hub_reachable=0`

## Installed Smoke After Sudo Access
- Real local reinstall is now complete:
  - `sudo apt install -y --reinstall ./telegram-username-collector_0.1.0_amd64.deb`
- Verified `/opt` payload:
  - wrappers contain `cd "$APP_ROOT"`
  - app contains `SITECTL_TOKEN_REDACTED`, `app_started`, `profiles_refreshed`, and the Shadow Admin logo asset
- Verified installed runtime:
  - `cd /tmp && telegram-username-collector --doctor`
  - `project_root=/opt/telegram-username-collector/app`
  - `gtk_runtime=ok`
  - `extension_zip_ready=1`
  - `hub_reachable=0` because hub was not started
- Verified installed payload after API-import rebuild:
  - `/opt/telegram-username-collector/app/scripts/telegram_gui/ui/window.py` contains `Импорт API`
  - `/opt/telegram-username-collector/app/scripts/telegram_gui/backend.py` contains `api_credentials_saved`
  - `/opt/telegram-username-collector/app/scripts/telegram_tdata_helper.py` contains `--api-id`
- Verified installed GUI:
  - `telegram-username-collector --ui-scale 1.15`
  - window opened in `Installed .deb mode`
  - API import button visible:
    - `/tmp/tg_gui_api_import_smoke_20260712/window-fresh-profile.png`
  - API import dialog opened:
    - `/tmp/tg_gui_api_import_smoke_20260712/api-dialog-root-2.png`
  - quick chat management visible:
    - `/tmp/tg_gui_quick_chats_smoke_20260712T111139Z/quick-chats-2.png`
  - add-template dialog opened:
    - `/tmp/tg_gui_quick_chats_smoke_20260712T111139Z/add-dialog-3.png`
  - hide-standard flow checked:
    - `/tmp/tg_gui_quick_chats_smoke_20260712T111139Z/hidden-standard.png`
  - latest action log: `/home/max/.local/share/site-control-kit/telegram_workspace/logs/gui_actions_20260712T111129Z.log`

## Limits And Risks
- External clean Ubuntu install smoke is still optional before wider distribution.
- The local desktop was cleaned after smoke; temporary `telegram-installed-smoke-*` folder was moved to trash.
- Do not commit ignored/generated artifacts:
  - `dist/`
  - `.site-control-kit/`
  - `TG_CONTACT/`
  - `var/`
  - `*.log`

## Not Part Of This Commit
- Existing dirty generated file:
  - `artifacts/telegram_exports/INDEX.md`
- Existing untracked local files:
  - `docs/checkpoints/CHECKPOINT_2026-06-16.md`
  - `ПРОКСИ/`

## Next Step
- If the user wants to install on another host:
  - `cd "/home/max/Рабочий стол/telegram-username-collector-install-kit"`
  - `sha256sum -c telegram-username-collector_0.1.0_amd64.deb.sha256`
  - `sudo apt install ./telegram-username-collector_0.1.0_amd64.deb`
  - `cd /tmp && telegram-username-collector --doctor`
