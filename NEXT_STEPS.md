# Next Steps

Дата: 2026-05-12

## Текущий baseline

- Published `origin/main`: `48abaf551e8997ad07bc6389719c7c1691766c3c`
- Reference-only closure commit: `77ecd4e52e27d42c242b0bed59c8ec2b3a6b2abf`
- Текущая интеграционная ветка: `rebaseline-origin-main-20260512`
- Текущий интеграционный worktree: `/home/max/site-control-kit-rebaseline-20260512`
- Новый live-smoke host:
  - `maxcorp-server`
  - `Ubuntu 24.04.4 LTS`
  - GUI environment: `Xvfb :99 + fluxbox + x11vnc`

## Что уже подтверждено

- Старый Linux installed-mode gate на `b740d6603787da701687a4fae421f7c68c94f9a8` закрыт со статусом `PASS with warning`.
- Закрывающий transcript:
  - `/tmp/tgcollector-smoke-logs/install-and-smoke-20260512-091934.log`
- На старом baseline подтверждены:
  - `dpkg -s telegram-username-collector` -> `install ok installed`
  - `/usr/bin/telegram-username-collector` и `/usr/bin/sitectl`
  - `/opt/telegram-username-collector/app` и `/opt/telegram-username-collector/venv`
  - `telegram-username-collector --doctor` -> `mode=installed`, `gtk_runtime=ok`, `extension_zip_ready=1`, `hub_reachable=0`
  - desktop shortcut
  - user XDG dirs
  - отсутствие runtime leakage в `/opt/...`
  - GUI через `gtk-launch` и через меню приложений
- Новый GitHub `main` уже ушёл на `45c25e4fc5641a807a809f173ac0cfeaed798934`.
- Diff `b740d66..45c25e4` не является docs-only drift и затрагивает product/runtime/test paths.
- Реальный regression нового baseline уже найден и исправлен:
  - initial fail on `maxcorp-server`:
    - `PermissionError: [Errno 13] Permission denied: '/opt/telegram-username-collector/app/.site-control-kit'`
  - fix landed in:
    - `webcontrol/settings.py`
    - `packaging/linux/telegram-username-collector.wrapper.sh`
    - `packaging/linux/sitectl.wrapper.sh`
    - `tests/test_settings.py`
    - `tests/test_telegram_product_runtime.py`
- После fix live rerun на `maxcorp-server` уже подтвердил:
  - rebuilt candidate root: `/tmp/site-control-kit-rebaseline-live-20260512-100713`
  - smoke log: `/tmp/tgcollector-smoke-logs/reinstall-and-smoke-20260512-080828.log`
  - `telegram-username-collector --doctor` -> `mode=installed`, `overall_status=ok`, `gtk_runtime=ok`, `extension_zip_ready=1`, `hub_reachable=1`
  - desktop shortcut создан
  - `gtk-launch telegram-username-collector` реально поднял окно
  - user XDG dirs созданы в temp-home
  - runtime leakage в `/opt/...` не найден

## Что осталось

- Обязательных Linux release-blocker-ов больше нет.
- Новый installed-mode gate на `45c25e4` закрыт и уже опубликован в `origin/main`.
- Стандартный GNOME/App-menu proof подтверждён.
- Следующий шаг теперь уже только по новой пользовательской задаче.

## Следующий узкий контур

```bash
git -C /home/max/site-control-kit fetch origin main
git -C /home/max/site-control-kit status --short --branch
```

Только если потребуется повторить installed-mode proof уже после публикации, запускать команды не из repo root, а из `/tmp`, чтобы локальный checkout не затенял установленный `/opt/...` код.

## Что не перепутать

- Старый Linux gate больше не считать open blocker.
- Regression с `/opt/.../.site-control-kit` уже исправлен, не возвращать его в backlog как открытый баг.
- GNOME/App-menu acceptance уже закрыт на текущем Ubuntu host.
- Исходный `/home/max/site-control-kit` всё ещё локально грязный из-за `artifacts/telegram_exports/INDEX.md`; не путать это с состоянием опубликованного `origin/main`.
- Не коммитить `.codex/`, `TG_CONTACT/`, `.site-control-kit/`, `dist/`, логи, токены и `artifacts/telegram_exports/INDEX.md`.
