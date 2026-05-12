# Checkpoint 2026-05-12 Rebaseline 45c25e4

## Git State At Start

- Integration worktree: `/home/max/site-control-kit-rebaseline-20260512`
- Integration branch: `rebaseline-origin-main-20260512`
- Remote baseline under test: `origin/main`
- Remote baseline `HEAD`: `45c25e4fc5641a807a809f173ac0cfeaed798934`
- Historical local reference commit only:
  - `77ecd4e52e27d42c242b0bed59c8ec2b3a6b2abf`
- Local main worktree noise outside this cycle:
  - `M artifacts/telegram_exports/INDEX.md`

## What Was Done

- Rebased the handoff flow onto the newer `origin/main` baseline in a separate worktree.
- Confirmed that `b740d66..45c25e4` is not docs-only drift.
- Ran a real installed-mode smoke on `maxcorp-server`.
- Captured a real installed-mode regression on the new baseline.
- Fixed the regression in code and wrappers.
- Added regression tests.
- Rebuilt the product and reran the installed-mode smoke successfully on the same host.

## New Baseline Drift

- `origin/main` had already moved to:
  - `45c25e4fc5641a807a809f173ac0cfeaed798934`
- The drift from `b740d66` includes product/runtime/test files such as:
  - `webcontrol/settings.py`
  - `scripts/telegram_product_runtime.py`
  - `requirements.txt`
  - `pyproject.toml`
  - `packaging/linux/*.wrapper.sh`
  - GUI-related paths under `scripts/telegram_gui/`

## Remote Smoke Host

- Host alias: `maxcorp-server`
- OS: `Ubuntu 24.04.4 LTS`
- GUI environment:
  - `Xvfb :99`
  - `fluxbox`
  - `x11vnc`
- Package precondition before rerun:
  - `telegram-username-collector` was not installed initially

## Environment Blockers Found On Host

- First fresh build failure:
  - command: `bash scripts/build_linux_deb.sh`
  - error: `ERROR: required tool is missing: rsync`
  - resolved with: `apt-get install -y rsync`
- Second fresh build failure:
  - command: `bash scripts/build_linux_deb.sh`
  - error: `ERROR: required tool is missing: convert`
  - resolved with: `apt-get install -y imagemagick`

## Real Product Regression Found

- First failing command on the new baseline:

```bash
runuser -u sitectl -- env DISPLAY=:99 HOME=/home/sitectl telegram-username-collector --doctor
```

- Failure:
  - `PermissionError: [Errno 13] Permission denied: '/opt/telegram-username-collector/app/.site-control-kit'`
- Offending path:
  - `/opt/telegram-username-collector/app/.site-control-kit`
- Practical root cause:
  - installed-mode still tried to create local state under `/opt/.../.site-control-kit` before honoring user/XDG runtime paths

## Code Changes For The Fix

- `webcontrol/settings.py`
  - added installed-mode-aware local config path resolution into user/XDG config space
  - added `SITECTL_LOCAL_CONFIG_PATH` support
  - expanded runtime override detection
- `packaging/linux/telegram-username-collector.wrapper.sh`
  - exports `SITECTL_LOCAL_CONFIG_PATH`
- `packaging/linux/sitectl.wrapper.sh`
  - exports `SITECTL_LOCAL_CONFIG_PATH`
- `tests/test_settings.py`
  - added installed-mode local-config regression test
- `tests/test_telegram_product_runtime.py`
  - added installed-mode doctor regression test

## Local Verify After Fix

- `python3 -m unittest tests/test_settings.py tests/test_telegram_product_runtime.py` -> OK
- `python3 -m unittest discover -s tests -p 'test_*.py'` -> `305 tests OK`
- `git diff --check` -> OK

## Live Rerun After Fix

- Candidate source root on remote host:
  - `/tmp/site-control-kit-rebaseline-live-20260512-100713`
- Rebuilt package:
  - `/tmp/site-control-kit-rebaseline-live-20260512-100713/dist/linux-deb/telegram-username-collector_0.1.0_amd64.deb`
- Package size:
  - `52M`
- Reinstall/smoke log:
  - `/tmp/tgcollector-smoke-logs/reinstall-and-smoke-20260512-080828.log`
- Temp smoke home:
  - `/tmp/tgcollector-home-20260512-080828`

## Installed-Mode Evidence After Fix

- `dpkg -s telegram-username-collector` -> `install ok installed`
- `/usr/bin/telegram-username-collector` -> exists
- `/usr/bin/sitectl` -> exists
- `/opt/telegram-username-collector/app` -> exists
- `/opt/telegram-username-collector/venv` -> exists

## Doctor Output After Fix

- `telegram-username-collector --doctor` showed:
  - `mode=installed`
  - `overall_status=ok`
  - `project_root=/opt/telegram-username-collector/app`
  - `runtime_root=/tmp/tgcollector-home-20260512-080828/.local/share/site-control-kit`
  - `token_file=/tmp/tgcollector-home-20260512-080828/.config/site-control-kit/generated_token.txt`
  - `token_present=1`
  - `logs_root=/tmp/tgcollector-home-20260512-080828/.local/state/site-control-kit/logs`
  - `reports_root=/tmp/tgcollector-home-20260512-080828/.local/share/site-control-kit/reports`
  - `workspace_root=/tmp/tgcollector-home-20260512-080828/.local/share/site-control-kit/telegram_workspace`
  - `gtk_runtime=ok`
  - `extension_dir=/opt/telegram-username-collector/app/extension`
  - `extension_zip=/opt/telegram-username-collector/app/resources/site-control-bridge-extension.zip`
  - `extension_zip_ready=1`
  - `desktop_file=/usr/share/applications/telegram-username-collector.desktop`
  - `desktop_dir=/tmp/tgcollector-home-20260512-080828/Desktop`
  - `hub_reachable=1`

## Shortcut And GUI Evidence

- Desktop shortcut created:
  - `/tmp/tgcollector-home-20260512-080828/Desktop/Telegram Username Collector.desktop`
- `gtk-launch telegram-username-collector` opened a real window.
- `xwininfo -root -tree | grep -F 'Telegram Username Collector'` found:
  - `0x1a00004 "Telegram Username Collector"`

## XDG Paths And Negative Checks

- Created user XDG paths:
  - `/tmp/tgcollector-home-20260512-080828/.config/site-control-kit`
  - `/tmp/tgcollector-home-20260512-080828/.local/share/site-control-kit`
  - `/tmp/tgcollector-home-20260512-080828/.local/state/site-control-kit/logs`
- No runtime leakage found inside `/opt/telegram-username-collector` for:
  - `generated_token.txt`
  - `state.json`
  - `runtime_events.jsonl`
  - `runtime_errors.jsonl`

## Environment Caveat

- `maxcorp-server` is not a standard Ubuntu GNOME desktop session.
- It uses `Xvfb :99 + fluxbox + x11vnc`.
- Therefore the standard Applications menu path is still not confirmed in a normal desktop shell.
- `gtk-launch`, desktop shortcut creation, live window appearance, XDG runtime routing, and `/opt` hygiene are confirmed.

## Practical Verdict

- Product regression on `45c25e4` is fixed.
- New baseline installed-mode core path on `maxcorp-server` is green.
- Remaining open item is acceptance-level only:
  - decide whether the lack of a standard GNOME Applications menu check is acceptable
  - or run one last smoke on a normal Ubuntu GUI desktop before publish
