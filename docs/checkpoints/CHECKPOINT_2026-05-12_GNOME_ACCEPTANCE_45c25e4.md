# Checkpoint 2026-05-12 GNOME Acceptance 45c25e4

## Git State At Start

- Integration worktree: `/home/max/site-control-kit-rebaseline-20260512`
- Integration branch: `rebaseline-origin-main-20260512`
- Candidate commit under acceptance: `b73c2ebc9d9c1c0995848702dff3c1c936af3629`
- Remote baseline lineage:
  - `45c25e4fc5641a807a809f173ac0cfeaed798934`
- Original repo worktree intentionally left dirty and untouched for publish:
  - `/home/max/site-control-kit`
  - `M artifacts/telegram_exports/INDEX.md`

## Why This Checkpoint Exists

- `docs/checkpoints/CHECKPOINT_2026-05-12_REBASELINE_45c25e4.md` already proved the installed-mode core path and regression fix on `maxcorp-server`.
- The only missing proof there was a standard Ubuntu GNOME Applications menu launch path.
- This checkpoint closes that last acceptance gap.

## Acceptance Host

- Host: current local Ubuntu desktop machine
- OS: `Ubuntu 24.04.4 LTS`
- Desktop session: `GNOME/X11`
- Python: `3.12.3`
- Important caveat:
  - this host is not pristine because `telegram-username-collector` was already installed earlier
  - however it is a real standard GNOME desktop, so it is the correct host to close the Applications menu proof gap left by `maxcorp-server`

## Critical Operational Nuance

- Installed-mode checks must be run from `/tmp`, not from the repo root.
- If `telegram-username-collector` is launched from `/home/max/site-control-kit`, the local checkout can shadow the installed `/opt/telegram-username-collector/app` code path and produce misleading results.

## Package Reinstall

- Reinstall command:

```bash
sudo apt install --reinstall -y /home/max/site-control-kit-rebaseline-20260512/dist/linux-deb/telegram-username-collector_0.1.0_amd64.deb
```

- Result:
  - reinstall completed successfully
  - `telegram-username-collector (0.1.0)` was unpacked and configured again

## Installed-Mode Evidence From `/tmp`

- `dpkg -s telegram-username-collector` -> `install ok installed`
- `/usr/bin/telegram-username-collector` -> exists
- `/usr/bin/sitectl` -> exists
- `/opt/telegram-username-collector` -> exists
- `/opt/telegram-username-collector/app` -> exists
- `/opt/telegram-username-collector/venv` -> exists

## Doctor Output From `/tmp`

- Command:

```bash
cd /tmp && telegram-username-collector --doctor
```

- Key output:
  - `mode=installed`
  - `overall_status=warning`
  - `project_root=/opt/telegram-username-collector/app`
  - `runtime_root=/home/max/.local/share/site-control-kit`
  - `token_file=/home/max/.config/site-control-kit/generated_token.txt`
  - `token_present=1`
  - `logs_root=/home/max/.local/state/site-control-kit/logs`
  - `reports_root=/home/max/.local/share/site-control-kit/reports`
  - `workspace_root=/home/max/.local/share/site-control-kit/telegram_workspace`
  - `helper_source=explicit`
  - `helper_python=/usr/bin/python3.12`
  - `gtk_runtime=ok`
  - `extension_dir=/opt/telegram-username-collector/app/extension`
  - `extension_zip=/opt/telegram-username-collector/app/resources/site-control-bridge-extension.zip`
  - `extension_zip_ready=1`
  - `desktop_file=/usr/share/applications/telegram-username-collector.desktop`
  - `desktop_dir=/home/max/Рабочий стол`
  - `hub_url=http://127.0.0.1:8765`
  - `hub_reachable=0`

## Shortcut And GUI Evidence

- Shortcut command:

```bash
cd /tmp && telegram-username-collector --create-desktop-shortcut
```

- Result:
  - created `/home/max/Рабочий стол/Telegram Username Collector.desktop`

- GTK launch command:

```bash
cd /tmp && gtk-launch telegram-username-collector
```

- Result:
  - real window opened
  - confirming log: `/tmp/tgcollector-gnome-postreinstall-20260512-103941.log`
  - log content was limited to:
    - `INFO: Telegram helper python (explicit): /opt/telegram-username-collector/venv/bin/python`

- Window proof:
  - `xwininfo -root -tree` found `Telegram Username Collector`

- Applications menu proof:
  - user manually launched `Telegram Username Collector` from the ordinary Ubuntu Applications menu
  - manual result confirmed in chat: `открылось`

## XDG Paths And Negative Checks

- Confirmed user XDG paths:
  - `/home/max/.config/site-control-kit`
  - `/home/max/.local/share/site-control-kit`
  - `/home/max/.local/state/site-control-kit/logs`

- Extended XDG/data tree observed:
  - `/home/max/.local/share/site-control-kit/browser-profile`
  - `/home/max/.local/share/site-control-kit/firefox-profile`
  - `/home/max/.local/share/site-control-kit/reports`
  - `/home/max/.local/share/site-control-kit/reports/telegram_exports`
  - `/home/max/.local/share/site-control-kit/state`
  - `/home/max/.local/share/site-control-kit/telegram_workspace`

- No runtime leakage found inside `/opt/telegram-username-collector` for:
  - `generated_token.txt`
  - `state.json`
  - `runtime_events.jsonl`
  - `runtime_errors.jsonl`

## Practical Verdict

- The standard Ubuntu GNOME/App-menu acceptance gap is closed.
- The new Linux installed-mode gate for baseline `45c25e4` is closed.
- On this host the only warning is:
  - `hub_reachable=0`
- That warning is acceptable here because the hub was not started on this host during the menu-path acceptance step.
- The earlier `maxcorp-server` checkpoint already proved the same fixed package with `overall_status=ok` and `hub_reachable=1`.
- Combined verdict for the rebaseline branch:
  - publish-ready

## Next Step

- Publish `rebaseline-origin-main-20260512` to `origin/main` without trying to clean or rewrite the dirty original worktree `/home/max/site-control-kit`.
