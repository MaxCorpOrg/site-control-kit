# Checkpoint 2026-05-12

## Git State At Start

- Local repo branch: `main`
- Local repo `HEAD`: `b740d6603787da701687a4fae421f7c68c94f9a8`
- Remote configured in local repo: `origin git@github.com:MaxCorpOrg/site-control-kit.git`
- Local worktree noise outside this task:
  - `M artifacts/telegram_exports/INDEX.md`

## What Was Done

- Completed the old Linux installed-mode release gate on baseline `b740d66`.
- Confirmed that fresh GitHub `main` no longer matches that old gate baseline.
- Ran the real interactive install smoke on the local baseline clone, captured transcript, and validated the installed-mode paths and runtime behavior.
- Updated repo handoff/state docs from blocker-state to `PASS with warning`.

## Fresh GitHub Clone Finding

- Fresh GitHub clone path: `/home/max/site-control-kit-product-smoke-20260512-085548`
- Fresh clone `HEAD`: `45c25e4fc5641a807a809f173ac0cfeaed798934`
- Recent remote commits observed:
  - `45c25e4 Fix product runtime Windows-host verify and sync checkpoint`
  - `4647fab Stabilize Windows smoke and record end-of-day checkpoint`
- `b740d66..45c25e4` is not docs-only drift.
- The diff includes product/runtime/test changes such as:
  - `webcontrol/settings.py`
  - `scripts/telegram_product_runtime.py`
  - `requirements.txt`
  - `pyproject.toml`
  - `tests/test_settings.py`
  - `tests/test_telegram_members_export_gui.py`

## Baseline Smoke Run

- Fresh local baseline clone path: `/home/max/site-control-kit-product-smoke-local-20260512-085840`
- Baseline clone `HEAD`: `b740d6603787da701687a4fae421f7c68c94f9a8`
- Build command: `bash scripts/build_linux_deb.sh`
- Built package: `/home/max/site-control-kit-product-smoke-local-20260512-085840/dist/linux-deb/telegram-username-collector_0.1.0_amd64.deb`
- Package size: `52M`
- Transcript: `/tmp/tgcollector-smoke-logs/install-and-smoke-20260512-091934.log`

## Installed-Mode Evidence

- Interactive install completed:

```bash
sudo apt install -y /home/max/site-control-kit-product-smoke-local-20260512-085840/dist/linux-deb/telegram-username-collector_0.1.0_amd64.deb
```

- Package status:

- `dpkg -s telegram-username-collector` -> `install ok installed`
- `/usr/bin/telegram-username-collector` -> exists
- `/usr/bin/sitectl` -> exists
- `/opt/telegram-username-collector/app` -> exists
- `/opt/telegram-username-collector/venv` -> exists

## Doctor Output

- `telegram-username-collector --doctor` showed:
  - `mode=installed`
  - `overall_status=warning`
  - `project_root=/home/max/site-control-kit`
  - `runtime_root=/home/max/.local/share/site-control-kit`
  - `token_file=/home/max/.config/site-control-kit/generated_token.txt`
  - `token_present=1`
  - `logs_root=/home/max/.local/state/site-control-kit/logs`
  - `reports_root=/home/max/.local/share/site-control-kit/reports`
  - `workspace_root=/home/max/.local/share/site-control-kit/telegram_workspace`
  - `gtk_runtime=ok`
  - `extension_dir=/opt/telegram-username-collector/app/extension`
  - `extension_zip=/opt/telegram-username-collector/app/resources/site-control-bridge-extension.zip`
  - `extension_zip_ready=1`
  - `desktop_file=/usr/share/applications/telegram-username-collector.desktop`
  - `desktop_dir=/home/max/Рабочий стол`
  - `hub_reachable=0`

## Shortcut And GUI

- Desktop shortcut created:
  - `/home/max/Рабочий стол/Telegram Username Collector.desktop`
- GUI launch:
  - `gtk-launch telegram-username-collector` was used in the transcript
  - the operator confirmed the window opened
  - the operator also confirmed separate launch from the Applications menu

## Runtime Paths And Negative Checks

- Created user XDG paths:
  - `~/.config/site-control-kit`
  - `~/.local/share/site-control-kit`
  - `~/.local/state/site-control-kit/logs`
- No runtime leakage found inside `/opt/telegram-username-collector` for:
  - `generated_token.txt`
  - `state.json`
  - `runtime_events.jsonl`
  - `runtime_errors.jsonl`

## Transcript Nuance

- `COMMAND_EXIT_CODE=127` at the end of the transcript was not caused by the product.
- The failing step was `xwininfo -root -tree | rg "Telegram Username Collector"` because `rg` was not available in that shell session.
- The successful install and GUI launch remain valid.

## Practical Verdict

- Result: `PASS with warning`
- The only warning is `hub_reachable=0`.
- The old Linux installed-mode gate on `b740d66` is now closed.
- The current host is no longer pristine because the package is installed.

## Next Step

- Re-baseline GitHub `main` at `45c25e4fc5641a807a809f173ac0cfeaed798934`.
- Decide separately whether that newer baseline needs another installed-mode smoke.
