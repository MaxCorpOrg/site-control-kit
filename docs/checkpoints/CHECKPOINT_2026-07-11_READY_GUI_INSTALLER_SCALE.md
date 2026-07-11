# Checkpoint 2026-07-11: Ready GUI Installer Scale

## Summary

Собран готовый Linux desktop contour для `Telegram Username Collector`: GTK-панель, `.deb`-установщик, масштабирование интерфейса, Shadow Admin дизайн из PDF-гайда, логотип и live-проверка hover/press кнопок.

Follow-up fix in the same checkpoint:
- removed white GTK defaults from `ComboBox`, `StackSwitcher`, list/viewport areas and dropdown/popover surfaces;
- made green action buttons use dark text for readability;
- verified the previously white scale selector, right-side tabs, quick-chat empty area and preset dropdown area in live screenshots.

## Branch And Remote

- Branch: `main`
- Remote tracking: `origin/main`
- Перед checkpoint рабочее дерево уже содержало старые локальные изменения/артефакты:
  - `artifacts/telegram_exports/INDEX.md`
  - `docs/checkpoints/CHECKPOINT_2026-06-16.md`
  - `ПРОКСИ/`

## Product Artifact

- Package:
  - `/home/max/site-control-kit/dist/linux-deb/telegram-username-collector_0.1.0_amd64.deb`
- Size:
  - `52M`
- sha256:
  - `57f4d9ea88c20b1cb67762a9ce0e1e7b200ca9a89ff07a42aef55dc8a5a73736`
- Confirmed package entries:
  - `/usr/bin/telegram-username-collector`
  - `/usr/bin/sitectl`
  - `/usr/share/applications/telegram-username-collector.desktop`
  - `/opt/telegram-username-collector/app`
  - `/opt/telegram-username-collector/app/resources/site-control-bridge-extension.zip`
  - `/opt/telegram-username-collector/app/resources/branding/shadow-admin-logo-mark.png`

## Code Changes

- `scripts/telegram_username_collector_launcher.py`
  - added `--ui-scale FACTOR`
  - sets `TELEGRAM_GUI_SCALE` before GUI import
  - rejects invalid scale values
- `scripts/telegram_gui/ui/styles.py`
  - builds GTK CSS from the resolved scale
  - clamps scale to a safe range
  - implements Shadow Admin dark tokens and explicit button hover/press feedback
- `scripts/telegram_gui/app.py`
  - scales initial window size
- `scripts/telegram_gui/ui/window.py`
  - adds `Масштаб интерфейса` selector
  - available values: `90%`, `100%`, `115%`, `125%`, `150%`
  - adds Shadow Admin logo, `Следующий шаг`, Russian badges and clearer action labels
- `scripts/telegram_gui/ui/panels.py`
  - uses Russian preflight/log labels
- `scripts/telegram_gui/backend.py`
  - uses unified `Сбор номеров` wording instead of old open-only wording
- `resources/branding/`
  - stores extracted Shadow Admin logo assets from the provided PDF guide
- `tests/test_telegram_username_collector_launcher.py`
  - covers valid/invalid launcher scaling path

## Verification

- `python3 -m py_compile scripts/telegram_username_collector_launcher.py scripts/telegram_gui/app.py scripts/telegram_gui/ui/styles.py scripts/telegram_gui/ui/window.py tests/test_telegram_username_collector_launcher.py` -> OK
- `python3 -m unittest tests.test_telegram_username_collector_launcher tests.test_telegram_members_export_gui` -> `53 tests OK`, `2 skipped`
- `python3 -m unittest discover -s tests -p 'test_*.py'` -> `324 tests OK`, `2 skipped`
- `python3 -m webcontrol --help` -> OK
- `python3 -m webcontrol browser --help` -> OK
- `git diff --check` -> OK
- `./scripts/verify.sh` -> OK
- `dpkg-deb --info dist/linux-deb/telegram-username-collector_0.1.0_amd64.deb` -> OK
- `dpkg-deb --contents dist/linux-deb/telegram-username-collector_0.1.0_amd64.deb` -> expected product files present
- final package sha256:
  - `57f4d9ea88c20b1cb67762a9ce0e1e7b200ca9a89ff07a42aef55dc8a5a73736`
- Repo GUI smoke:
  - `DISPLAY=:0`
  - `python3 -m scripts.telegram_username_collector_launcher --ui-scale 1.15`
  - window `Telegram Username Collector` appeared
  - screenshot:
    - `/tmp/shadow_admin_gui_after_feedback_normal_20260711.png`
  - hover screenshot:
    - `/tmp/shadow_admin_gui_final2_hover_refresh_20260711.png`
  - press screenshot:
    - `/tmp/shadow_admin_gui_final2_press_refresh_20260711.png`
  - white-widget fix screenshots:
    - `/tmp/shadow_admin_theme_fix_mid_20260711.png`
    - `/tmp/shadow_admin_theme_fix_wide_20260711.png`
    - `/tmp/shadow_admin_theme_fix_bottom_20260711.png`
    - `/tmp/shadow_admin_theme_fix_preset_20260711.png`
  - safe click on `Обновить профили` completed without a panel crash
- Extracted `.deb` smoke:
  - package unpacked under `/tmp/tgcollector-shadow-admin-deb-smoke-20260711/root`
  - `--help` worked from extracted app/venv
  - `--doctor` worked
  - `hub_reachable=0` was expected because the hub was not started for that smoke

## Limitations

- Real system install was not executed:
  - `sudo apt install ./dist/linux-deb/telegram-username-collector_0.1.0_amd64.deb`
- The package was checked through `dpkg-deb` inspection and extracted installed-mode smoke.
- `dist/` is a build artifact; do not commit it unless the user explicitly wants package artifacts in git.

## Next Step

- If distributing to an operator:
  - install the `.deb` on a clean Ubuntu 24.04 machine
  - run `telegram-username-collector --doctor`
  - open the desktop launcher
  - verify scale selector and one Telegram `Quick Check`
- If scaling means more parallel work rather than UI size:
  - design a job queue / worker profile layer separately from this UI packaging pass.
