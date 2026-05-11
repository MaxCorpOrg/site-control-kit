# Checkpoint 2026-05-11

## Git State At Start

- Branch: `main`
- Remote: `origin git@github.com:MaxCorpOrg/site-control-kit.git`
- Last commit before closure work: `3412ccd26d5ebcd3710a50b8f6c0b5b9696a6447`
- Published productization commit: `Упаковать Telegram Username Collector как Linux-продукт`

## What Was Done

- Completed end-of-day documentation handoff for Linux productization.
- Recorded fresh GitHub clone `.deb` smoke evidence.
- Recorded why full clean VM install smoke is still open.
- Added root `NEXT_STEPS.md` and `CHANGELOG.md`.
- Updated project and agent docs so the next agent enters from the current release gate.
- Added `.gitignore` protection for local env files, `.codex/`, `TG_CONTACT/`, and `node_modules/`.

## Changed Files Intended For Commit

- `.gitignore`
- `README.md`
- `AGENTS.md`
- `NEXT_STEPS.md`
- `CHANGELOG.md`
- `AGENT_START_HERE.md`
- `CODEX_STATE.md`
- `docs/ARCHITECTURE.md`
- `docs/PROJECT_STATUS_RU.md`
- `docs/agent_handoff_ru/00_START_HERE.md`
- `docs/agent_handoff_ru/09_CURRENT_BACKLOG_AND_NEXT_STEPS.md`
- `docs/checkpoints/CHECKPOINT_2026-05-11.md`
- `scripts/build_linux_deb.sh`

## Local Files Not Intended For Commit

- `artifacts/telegram_exports/INDEX.md`
- `.codex`
- `.codex/`
- `TG_CONTACT/`
- `.site-control-kit/`
- `dist/`
- runtime logs, generated tokens, cache directories, `__pycache__/`

## Smoke Evidence

- Environment: `Ubuntu 24.04.4 LTS`, GNOME/X11, `Python 3.12.3`.
- Fresh clone path: `/home/max/site-control-kit-product-smoke-20260511-164357`.
- Fresh clone `HEAD`: `3412ccd26d5ebcd3710a50b8f6c0b5b9696a6447`.
- Fresh clone status: `## main...origin/main`.
- Build command: `bash scripts/build_linux_deb.sh`.
- Built package: `/home/max/site-control-kit-product-smoke-20260511-164357/dist/linux-deb/telegram-username-collector_0.1.0_amd64.deb`.
- Package size: `52M`.
- `dpkg-deb --info` confirmed package `telegram-username-collector`, version `0.1.0`, arch `amd64`.
- `dpkg-deb --contents` confirmed launchers, desktop entry, icons and bundled extension zip.
- Forbidden payload was absent: handoff files, tests, `.codex`, `TG_CONTACT`, `artifacts/telegram_exports`.

## Simulated Installed-Mode Evidence

- Extract root: `/tmp/sitectl-deb-extract-20260511-164732`.
- Temp XDG root: `/tmp/sitectl-deb-xdg-20260511-164732`.
- `telegram-username-collector --doctor` from extracted payload:
  - `mode=installed`
  - `overall_status=warning`
  - `token_present=1`
  - `gtk_runtime=ok`
  - `extension_zip_ready=1`
  - `hub_reachable=0`
- `hub_reachable=0` is expected here because the hub was not started.
- Temp XDG config/data/state directories were created.
- Extracted `/opt/telegram-username-collector` had no user runtime files named `generated_token.txt`, `runtime_events.jsonl`, or `state.json`.
- `--create-desktop-shortcut` with temp `HOME` created a desktop shortcut.
- Direct GUI launch from extracted package payload opened a real `Telegram Username Collector` window on `DISPLAY=:0`; no traceback was printed.

## End-of-Day Verification

- `./scripts/verify.sh` -> `299 tests OK`, `python3 -m webcontrol --help` OK, `python3 -m webcontrol browser --help` OK.
- `python3 -m compileall webcontrol scripts tests` -> OK.
- `python3 -m scripts.telegram_username_collector_launcher --doctor` -> OK with expected `overall_status=warning` because `hub_reachable=0`.
- `bash scripts/build_linux_deb.sh` -> built `dist/linux-deb/telegram-username-collector_0.1.0_amd64.deb`.
- `dpkg-deb --info dist/linux-deb/telegram-username-collector_0.1.0_amd64.deb` -> OK.
- `dpkg-deb --contents ...` initially found `docs/checkpoints/CHECKPOINT_2026-05-11.md` inside product payload.
- `scripts/build_linux_deb.sh` was fixed to exclude agent/checkpoint/next-step docs from `.deb`.
- Rebuilt `.deb` and repeated payload scan -> forbidden payload absent.
- `git diff --check` -> OK.

## Errors And Blockers

- `sudo -n true` failed with `sudo: a password is required`.
- `sudo -n apt install -y ...telegram-username-collector_0.1.0_amd64.deb` failed with `sudo: a password is required`.
- Because of this, real system install was not executed on the current host.
- Current host is not confirmed as a clean Ubuntu VM, so Applications menu and real `/usr/bin`/`/opt` installed-mode checks remain open.
- No lint/typecheck command is configured in this repository; closest available static check used in this closure was `python3 -m compileall webcontrol scripts tests`.

## Commands Already Run In This Closure Cycle

```bash
git status --short --branch
git branch --show-current
git remote -v
git rev-parse HEAD
cat /etc/os-release
python3 --version
git --version
sudo -n true
git clone https://github.com/MaxCorpOrg/site-control-kit.git /home/max/site-control-kit-product-smoke-20260511-164357
git -C /home/max/site-control-kit-product-smoke-20260511-164357 rev-parse HEAD
git -C /home/max/site-control-kit-product-smoke-20260511-164357 status --short --branch
bash scripts/build_linux_deb.sh
dpkg-deb --info /home/max/site-control-kit-product-smoke-20260511-164357/dist/linux-deb/telegram-username-collector_0.1.0_amd64.deb
dpkg-deb --contents /home/max/site-control-kit-product-smoke-20260511-164357/dist/linux-deb/telegram-username-collector_0.1.0_amd64.deb
dpkg-deb -x /home/max/site-control-kit-product-smoke-20260511-164357/dist/linux-deb/telegram-username-collector_0.1.0_amd64.deb /tmp/sitectl-deb-extract-20260511-164732
```

## Next Step For The Next Agent

Do not start new feature work first.

Start from:

1. `AGENT_START_HERE.md`
2. `CODEX_STATE.md`
3. `docs/checkpoints/CHECKPOINT_2026-05-11.md`
4. `NEXT_STEPS.md`

Then run clean Ubuntu 24.04 VM smoke:

```bash
git clone https://github.com/MaxCorpOrg/site-control-kit.git site-control-kit-product-smoke
cd site-control-kit-product-smoke
bash scripts/build_linux_deb.sh
sudo apt install -y ./dist/linux-deb/telegram-username-collector_0.1.0_amd64.deb
telegram-username-collector --doctor
telegram-username-collector --create-desktop-shortcut
gtk-launch telegram-username-collector
```

Expected final result: `PASS` or `PASS with warning hub_reachable=0`.
