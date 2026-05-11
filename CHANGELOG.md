# Changelog

## 2026-05-11

- Завершён end-of-day checkpoint pass: обновлены project docs, agent rules, next steps и checkpoint.
- Добавлена защита `.gitignore` для локальных env/agent/Telegram/cache artifacts.
- Исправлена hygiene сборки `.deb`: agent/checkpoint/next-step docs исключены из product payload.
- Опубликован Linux-first productization baseline для `Telegram Username Collector`.
- Добавлена сборка Ubuntu `.deb` пакета через `scripts/build_linux_deb.sh`.
- Добавлены Linux product wrappers, desktop entry, иконки и bundled companion extension zip.
- `telegram-username-collector` получил `--doctor` и `--create-desktop-shortcut`.
- Runtime установленной версии переведён на пользовательские XDG-пути вместо записи рабочих данных в `/opt`.
- Выполнен fresh-clone build smoke из GitHub `main`.
- Выполнен simulated installed-mode smoke через `dpkg-deb -x`: doctor, XDG dirs, shortcut и GTK GUI startup.
- Clean Ubuntu 24.04 system install smoke остаётся открытым, потому что на текущей машине `sudo` требует пароль и среда не подтверждена как clean VM.

## 2026-05-10

- Зафиксирован Windows smoke handoff для `telegram-username-collector`.
- Уточнено, что Windows проверяет wrappers/runtime/fast-fail, а не полный Telegram feature-cycle.

## 2026-05-09

- Закрыт production-hardening baseline для Telegram GUI extraction и runtime diagnostics.
- Подтверждён основной Linux GTK operator path.
