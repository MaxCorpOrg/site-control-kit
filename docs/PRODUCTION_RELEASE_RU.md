# Выпуск центра управления Telegram

Дата актуализации: 2026-07-24.

Документ фиксирует выпускной контур приложения `Telegram Control Center` — центра управления Telegram.

## Как приложение связано с `site-control-kit`

- Центр управления собирается из репозитория `site-control-kit`, но устанавливается как отдельное операторское приложение.
- Обычному пользователю не нужна копия репозитория: достаточно готового пакета `.deb`.
- После установки код приложения находится в `/opt/site-control-kit/app`.
- Команда запуска — `telegram-control-center`.
- Настройки, данные, журналы и кэш пользователя хранятся в стандартных каталогах XDG.
- Полный репозиторий нужен для разработки, диагностики, сборки и выпуска новых версий.

## Поддерживаемые варианты выпуска

| Платформа | Состояние |
|---|---|
| Linux | Основная рабочая цель: пакет `.deb`, меню приложений, значок и полный живой сценарий при строгой проверке присоединения к окну. |
| Windows | Цель для установщика и графического приложения. Живые действия Telegram Desktop в первой версии считаются ограниченными до отдельной реализации адаптера Windows. |

## Что входит в выпуск

- графическая панель центра управления Telegram;
- внутренние команды и помощники, нужные панели;
- встроенный `telegram_portable_session_tool` без `.git`, запусков, состояния и личных настроек;
- русская документация, реестр и манифесты.

Не входят:

- `runtime/`;
- `telegram_ak/`;
- `TG_APP/`;
- `.codex/`;
- `tdata`, переносимые профили, журналы заданий и пользовательские секреты.

## Установка в Linux

Сборка:

```bash
./packaging/linux/build_deb.sh
```

Установка в Ubuntu или Debian:

```bash
sudo apt install ./packaging/dist/linux/telegram-control-center_0.1.1_all.deb
```

Запуск и самопроверка:

```bash
telegram-control-center
telegram-control-center --release-self-test
```

Создание ярлыка на рабочем столе:

```bash
telegram-control-center-install-desktop-shortcut
```

Удаление:

```bash
sudo apt remove telegram-control-center
```

Обычное удаление сохраняет пользовательские настройки, данные и журналы. Для возврата приложения установите тот же пакет повторно.

## Каталоги среды выполнения

Это схема установленного приложения, а не репозитория разработки.

Linux:

- настройки: `~/.config/site-control-kit`;
- данные: `~/.local/share/site-control-kit`;
- журналы: `~/.local/state/site-control-kit/logs`;
- кэш: `~/.cache/site-control-kit`.

Windows:

- настройки: `%APPDATA%\\SiteControlKit\\config`;
- данные: `%LOCALAPPDATA%\\SiteControlKit\\data`;
- журналы: `%LOCALAPPDATA%\\SiteControlKit\\logs`;
- кэш: `%LOCALAPPDATA%\\SiteControlKit\\cache`.

Пути можно переопределить:

- `SITE_CONTROL_KIT_CONFIG_DIR`;
- `SITE_CONTROL_KIT_DATA_DIR`;
- `SITE_CONTROL_KIT_LOG_DIR`;
- `SITE_CONTROL_KIT_CACHE_DIR`;
- `SITE_CONTROL_KIT_APP_ROOT`.

## Сборка для Windows

Для сборки Windows-установщика в Linux нужны Wine и компилятор Inno Setup:

```bash
./packaging/windows/build_windows_installer.sh 0.1.1 --check-tools
./packaging/windows/build_windows_installer.sh 0.1.1
```

Ожидаемый файл:

```text
packaging/dist/windows/TelegramControlCenterSetup-0.1.1.exe
```

Если Wine или компилятор Inno Setup недоступен, сценарий завершается с диагностической ошибкой и не имитирует успешную сборку.

## Проверка выпуска

1. Проверить `git status --short --branch`.
2. Запустить `python3 -m py_compile` для изменённых точек входа Python.
3. Запустить `PYTHONPATH="$PWD" python3 -m unittest tests.test_tool_platform tests.test_telegram_portable`.
4. Запустить полный набор: `PYTHONPATH="$PWD" python3 -m unittest discover -s tests -p 'test_*.py'`.
5. Запустить `git diff --check`.
6. Проверить файл меню: `desktop-file-validate packaging/linux/telegram-control-center.desktop`.
7. Запустить `bash -n` для изменённых сценариев оболочки.
8. Собрать пакет: `./packaging/linux/build_deb.sh`.
9. Проверить извлечённое дерево: `python3 packaging/release/check_release_tree.py <корень-приложения>`.
10. Выполнить установку без прав администратора через `dpkg-deb -x` и `telegram-control-center --release-self-test`.
11. Живую проверку Linux выполнять только при безопасном присоединении: `attach_status` равен `exact_window` или `title_match`.
12. Проверять Windows-установщик только при доступных Wine и Inno Setup.
13. Посчитать `sha256sum` для выпускных файлов.
14. Просмотреть точный состав коммита и отправить ветку.

## Последние подтверждения выпуска

- Пакет Linux: `packaging/dist/linux/telegram-control-center_0.1.1_all.deb`.
- Контрольная сумма принятого пакета: `1bb7315ccb2a03e5261604327e380a82cd77f51f0d3fa4500b5fd516c65f1f60`.
- Чистая установка без прав администратора прошла через `dpkg-deb -x`, проверку дерева и `telegram-control-center --release-self-test`.
- Системная установка версии `0.1.1` прошла; приложение запускается из `/opt/site-control-kit/app`, а XDG-пути указывают в домашний каталог пользователя.
- Подтверждено, что `.deb` устанавливается без исходного репозитория.
- Запуск из командной строки и меню принят; падение пустого состояния устранено.
- `apt remove` удаляет системную часть и сохраняет пользовательские XDG-данные.
- Пользовательский ярлык остаётся после удаления и может требовать подтверждения доверия рабочим столом.
- Windows-установщик на текущем Linux-хосте не собирался из-за отсутствия Wine и `winepath`.

## Проверка безопасности

- Не коммитить и не упаковывать `runtime/`, `telegram_ak/`, `TG_APP/`, `.codex/`.
- Не упаковывать `tdata`, переносимые профили, историю заданий и журналы.
- Не вшивать токены, пароли, токены ботов и ключи API.
- Не ослаблять проверку присоединения к окну Telegram.
- Профиль AK5 в Wayland запускать с сохранённым `display_backend = x11` и только после безопасного присоединения.
