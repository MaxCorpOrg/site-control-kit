# Установка готового продукта в Linux

Документ относится к прикладному продукту Telegram Username Collector для
Ubuntu 24.04. Это отдельный контур поверх Site Control Kit, а не способ
разработки браузерного ядра.

## Что устанавливается

- приложение в `/opt/telegram-username-collector`;
- команды `telegram-username-collector` и `sitectl`;
- пункт меню приложений;
- распакованное браузерное расширение и его ZIP-архив;
- GTK 4 — библиотека графического интерфейса.

Рабочие данные пишутся в пользовательские XDG-каталоги, а не в `/opt`.

## Сборка

```bash
bash scripts/build_linux_deb.sh
```

Ожидаемый пакет:

```text
dist/linux-deb/telegram-username-collector_<версия>_<архитектура>.deb
```

Готовый `.deb` — сборочный артефакт. Его не следует коммитить; публикуйте
пакет в GitHub Releases или хранилище артефактов.

## Установка

```bash
sudo apt install ./dist/linux-deb/telegram-username-collector_<версия>_<архитектура>.deb
```

Пакет рассчитан на системные зависимости Python 3, GTK 4, `xdg-utils` и
`zip`. Если сборщик сообщает об отсутствующей программе, установите
перечисленную зависимость и повторите сборку в чистом каталоге.

## Пользовательские данные

- конфиг и токен: `${XDG_CONFIG_HOME:-~/.config}/site-control-kit`;
- состояние, отчёты и Telegram workspace:
  `${XDG_DATA_HOME:-~/.local/share}/site-control-kit`;
- журналы: `${XDG_STATE_HOME:-~/.local/state}/site-control-kit/logs`;
- SQLite: `~/.local/share/site-control-kit/state/state.sqlite3`;
- совместимый JSON-снимок:
  `~/.local/share/site-control-kit/state/state.json`;
- браузерный профиль:
  `~/.local/share/site-control-kit/browser-profile`.

Удаление пакета намеренно не стирает эти данные.

## Первый запуск

```bash
telegram-username-collector --doctor
telegram-username-collector
```

Диагностика проверяет GTK, пути, токен, Python-помощник, расширение,
desktop-файл и здоровье хаба. `hub_reachable=0` означает, что хаб не запущен
или недоступен; это не всегда ошибка Telegram-сценария.

Ярлык на рабочем столе:

```bash
telegram-username-collector --create-desktop-shortcut
```

## Браузерное расширение

Расширение пока не публикуется в Chrome Web Store. Один раз выполните:

1. откройте `chrome://extensions`;
2. включите режим разработчика;
3. нажмите «Загрузить распакованное расширение»;
4. выберите `/opt/telegram-username-collector/app/extension`;
5. в настройках укажите `http://127.0.0.1:8765` и токен из
   `~/.config/site-control-kit/generated_token.txt`.

Расширение — дополнительный браузерный контур. Основной Telegram-сбор через
`tdata` не должен зависеть от его наличия.

## Обновление

```bash
bash scripts/build_linux_deb.sh
sudo apt install ./dist/linux-deb/telegram-username-collector_<версия>_<архитектура>.deb
telegram-username-collector --doctor
```

XDG-данные сохраняются. Перед крупным обновлением сделайте резервную копию
Telegram workspace и SQLite.

## Удаление

```bash
sudo apt remove telegram-username-collector
```

После резервной копии пользователь может отдельно удалить:

```text
~/.config/site-control-kit
~/.local/share/site-control-kit
~/.local/state/site-control-kit
```

## Ограничения

- отдельный готовый Windows GUI не входит в этот пакет;
- расширение устанавливается вручную;
- пакет нужно проверять на чистой Ubuntu перед широкой публикацией;
- готовые бинарные сборки не входят в обычную историю Git.
