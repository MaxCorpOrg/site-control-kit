# Linux Product Install

Документ описывает именно готовый Linux-first продукт `Telegram Username Collector`, а не dev-checkout репозитория.

Целевая система v1: `Ubuntu 24.04`.

## 1. Что получает пользователь

После установки `.deb`:

- программа ставится в `/opt/telegram-username-collector`
- в меню приложений появляется `Telegram Username Collector`
- доступна команда `telegram-username-collector`
- доступна команда диагностики `telegram-username-collector --doctor`
- можно создать ярлык на рабочем столе через `telegram-username-collector --create-desktop-shortcut`
- рабочие данные пишутся не в `/opt/...`, а в пользовательские XDG-каталоги

## 2. Сборка `.deb`

Из корня репозитория:

```bash
cd <repo-root>
bash scripts/build_linux_deb.sh
```

Результат:

- пакет: `dist/linux-deb/telegram-username-collector_<version>_<arch>.deb`
- bundled extension zip внутри пакета: `/opt/telegram-username-collector/app/resources/site-control-bridge-extension.zip`

## 3. Установка

На Ubuntu 24.04:

```bash
cd <repo-root>
sudo apt install ./dist/linux-deb/telegram-username-collector_<version>_<arch>.deb
```

Системные зависимости, на которые рассчитан пакет:

- `python3`
- `python3-gi`
- `gir1.2-gtk-4.0`
- `libgtk-4-1`
- `xdg-utils`
- `zip`

## 4. Куда пишутся данные

Установленная версия использует XDG-пути:

- config/token: `${XDG_CONFIG_HOME:-~/.config}/site-control-kit`
- runtime/workspace/reports: `${XDG_DATA_HOME:-~/.local/share}/site-control-kit`
- logs: `${XDG_STATE_HOME:-~/.local/state}/site-control-kit/logs`

Практически это значит:

- token file: `~/.config/site-control-kit/generated_token.txt`
- workspace: `~/.local/share/site-control-kit/telegram_workspace`
- reports: `~/.local/share/site-control-kit/reports/telegram_exports`
- state: `~/.local/share/site-control-kit/state/state.json`
- browser profiles: `~/.local/share/site-control-kit/browser-profile`

Удаление пакета не удаляет эти пользовательские данные автоматически.

## 5. Первый запуск

Сразу после установки выполните:

```bash
telegram-username-collector --doctor
```

Что проверяет `--doctor`:

- GTK runtime
- resolved runtime paths
- наличие token file
- готовность helper python
- путь к extension zip
- desktop file
- доступность hub health endpoint

Запуск GUI:

```bash
telegram-username-collector
```

Создание ярлыка на рабочем столе:

```bash
telegram-username-collector --create-desktop-shortcut
```

## 6. Браузерное расширение

В этой версии расширение не публикуется в Store.
Используется one-time unpacked setup.

Что есть в установленном продукте:

- unpacked folder: `/opt/telegram-username-collector/app/extension`
- zip archive: `/opt/telegram-username-collector/app/resources/site-control-bridge-extension.zip`

One-time setup:

1. Откройте `chrome://extensions` или `edge://extensions`.
2. Включите `Developer mode`.
3. Нажмите `Load unpacked`.
4. Выберите `/opt/telegram-username-collector/app/extension`.
5. В `Options` расширения укажите:
   - `Server URL`: `http://127.0.0.1:8765`
   - `Access Token`: значение из `~/.config/site-control-kit/generated_token.txt`

Важно:

- расширение остаётся companion-контуром;
- основной Linux workflow продукта остаётся `GTK GUI + tdata-history-authors`;
- отсутствие extension не должно ломать основной `tdata`-сценарий.

## 7. Обновление

Соберите новый `.deb` и установите его поверх:

```bash
cd <repo-root>
bash scripts/build_linux_deb.sh
sudo apt install ./dist/linux-deb/telegram-username-collector_<version>_<arch>.deb
```

Пользовательские данные в XDG-каталогах сохраняются.

## 8. Удаление

```bash
sudo apt remove telegram-username-collector
```

Это удалит системные файлы пакета, но не удалит автоматически:

- `~/.config/site-control-kit`
- `~/.local/share/site-control-kit`
- `~/.local/state/site-control-kit`

## 9. Что не входит в этот релиз

- полноценный Windows-продукт
- Windows GTK GUI для `telegram-username-collector`
- публикация расширения в Chrome Web Store / Edge Add-ons

Windows в текущей версии остаётся secondary platform для core/browser smoke и fast-fail launcher contract.
