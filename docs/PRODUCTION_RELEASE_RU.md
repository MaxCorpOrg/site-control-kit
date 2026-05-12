# Production Release: Telegram Control Center

Дата: 2026-05-12

Этот документ фиксирует релизный контур для `Telegram Control Center`.

## Release Matrix

- Linux — основной production target: `.deb`, меню приложений, иконка, double-click launcher и полный live workflow при строгом attach gating.
- Windows — installer/exe GUI target: приложение запускается двойным кликом, но Telegram Desktop live lanes в v1 считаются degraded до отдельного Windows adapter tranche.

## Что Попадает В Релиз

- `Telegram Control Center` GUI.
- Внутренние CLI/helper-компоненты, нужные панели.
- Embedded `telegram_portable_session_tool` без `.git`, `runs`, `.state` и приватных конфигов.
- Документация и registry/manifests.

В релиз не попадают:

- `runtime/`
- `telegram_ak/`
- `TG_APP/`
- `.codex/`
- `tdata`, portable profiles, logs, job history, user secrets.

## Linux Install

Сборка:

```bash
./packaging/linux/build_deb.sh
```

Установка на Ubuntu/Debian:

```bash
sudo apt install ./packaging/dist/linux/telegram-control-center_0.1.1_all.deb
```

Запуск:

```bash
telegram-control-center
```

Self-test:

```bash
telegram-control-center --release-self-test
```

Если нужен ярлык на рабочем столе:

```bash
telegram-control-center-install-desktop-shortcut
```

Удаление:

```bash
sudo apt remove telegram-control-center
```

Пользовательские data/config/logs при обычном удалении не удаляются.

## Runtime Folders

Linux production defaults:

- config: `~/.config/site-control-kit`
- data: `~/.local/share/site-control-kit`
- logs: `~/.local/state/site-control-kit/logs`
- cache: `~/.cache/site-control-kit`

Windows production defaults:

- config: `%APPDATA%\\SiteControlKit\\config`
- data: `%LOCALAPPDATA%\\SiteControlKit\\data`
- logs: `%LOCALAPPDATA%\\SiteControlKit\\logs`
- cache: `%LOCALAPPDATA%\\SiteControlKit\\cache`

Overrides:

- `SITE_CONTROL_KIT_CONFIG_DIR`
- `SITE_CONTROL_KIT_DATA_DIR`
- `SITE_CONTROL_KIT_LOG_DIR`
- `SITE_CONTROL_KIT_CACHE_DIR`
- `SITE_CONTROL_KIT_APP_ROOT`

## Windows Build

Windows packaging из Linux требует Wine toolchain:

```bash
./packaging/windows/build_windows_installer.sh 0.1.1 --check-tools
./packaging/windows/build_windows_installer.sh 0.1.1
```

Ожидаемый результат:

- `packaging/dist/windows/TelegramControlCenterSetup-0.1.1.exe`

Если `wine` или Inno Setup compiler отсутствуют, build script завершится диагностическим кодом и не будет имитировать успешный installer.

## Release Checklist

1. `git status --short --branch`.
2. `python3 -m py_compile` для изменённых Python entrypoints.
3. `PYTHONPATH="$PWD" python3 -m unittest tests.test_tool_platform tests.test_telegram_portable`.
4. `PYTHONPATH="$PWD" python3 -m unittest discover -s tests -p 'test_*.py'`.
5. `git diff --check`.
6. `desktop-file-validate packaging/linux/telegram-control-center.desktop`.
7. `bash -n` для shell packaging scripts.
8. `./packaging/linux/build_deb.sh`.
9. `python3 packaging/release/check_release_tree.py <extracted-app-root>`.
10. Rootless clean install smoke через `dpkg-deb -x` и `telegram-control-center --release-self-test`.
11. Linux live smoke только при safe attach: `attach_status in {exact_window, title_match}`.
12. Windows installer smoke только при доступном Wine/Inno toolchain.
13. `sha256sum` для release artifacts.
14. Финальный commit/push.

## Текущая Release Evidence

- Linux artifact: `packaging/dist/linux/telegram-control-center_0.1.1_all.deb`
- sha256: считать после финальной сборки командой `sha256sum packaging/dist/linux/telegram-control-center_0.1.1_all.deb`.
- Rootless clean install smoke: OK через `dpkg-deb -x`, release tree scan и `telegram-control-center --release-self-test`.
- Staged uninstall smoke: OK на temp-root layout; реальный `apt remove` нужно повторить на disposable VM/rootful окружении.
- Windows installer: not built on this Linux host, blocked by missing `wine`/`winepath`.

## Security Checklist

- Не коммитить и не паковать `runtime/`, `telegram_ak/`, `TG_APP/`, `.codex/`.
- Не паковать `tdata`, portable profiles, job history и logs.
- Не зашивать токены, пароли, bot tokens, API keys.
- Не ослаблять Telegram attach gating.
- AK5 на Wayland запускать через сохранённый `display_backend = x11` и только при safe attach.
