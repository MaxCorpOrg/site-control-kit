# Telegram Portable RU

## Что Это
`telegram_portable.py` — локальный helper внутри `site-control-kit` для Linux-профилей Telegram Desktop, когда у оператора уже есть `zip` с `tdata` и нужно быстро поднять отдельный portable-профиль без ручной раскладки файлов.

Это не Telegram Web automation и не browser bridge.
Это отдельный локальный инструмент для Telegram Desktop на Linux:
- берёт `zip` с `tdata`;
- подготавливает отдельную папку `~/TelegramPortable-<profile>`;
- кладёт данные в `TelegramForcePortable/tdata`;
- может сразу запустить Telegram именно с этим профилем.

## Когда Агенту Использовать Этот Инструмент
Использовать его, если задача звучит примерно так:
- "есть `tdata.zip`, открой этого пользователя в Telegram";
- "подними ещё один Telegram-профиль из архива";
- "сделай portable Telegram под Linux";
- "автоматизируй импорт desktop-сессии Telegram".

Не использовать его для задач Telegram Web, browser DOM automation, invite/extract flows или работы через `site-control` bridge.

## Файлы Инструмента
- `scripts/telegram_portable.py`
- `scripts/telegram_portable_gui.sh`
- `tests/test_telegram_portable.py`

## Что Делает Helper
### `import-zip`
Команда:
- принимает путь к `zip` с `tdata`;
- при первом запуске скачивает официальный Linux runtime Telegram Desktop в локальный cache;
- создаёт отдельный профиль `~/TelegramPortable-<profile>`;
- распаковывает `tdata` в `TelegramForcePortable/tdata`;
- пишет metadata в `portable-profile.json`;
- по флагу `--launch` сразу запускает Telegram.

### `launch`
Команда:
- берёт уже существующий portable-профиль;
- запускает его повторно;
- если этот же профиль уже запущен, не плодит второй процесс и возвращает `already_running`.

## Базовые Команды
### Импорт и запуск

```bash
cd /home/max/site-control-kit
python3 scripts/telegram_portable.py import-zip \
  --zip "/path/to/tdata.zip" \
  --profile-name "ak" \
  --launch
```

### Импорт без запуска

```bash
python3 scripts/telegram_portable.py import-zip \
  --zip "/path/to/tdata.zip" \
  --profile-name "ak"
```

### Офлайн-режим с локальным архивом Telegram Desktop

```bash
python3 scripts/telegram_portable.py import-zip \
  --zip "/path/to/tdata.zip" \
  --profile-name "ak" \
  --runtime-archive "/path/to/tsetup.tar.xz" \
  --launch
```

### Повторный запуск существующего профиля

```bash
python3 scripts/telegram_portable.py launch \
  --profile-name "ak"
```

### GUI-режим

```bash
cd /home/max/site-control-kit
./scripts/telegram_portable_gui.sh
```

## Где Что Лежит
По умолчанию профиль создаётся здесь:

```text
~/TelegramPortable-<profile>/
```

Внутри:
- `Telegram`
- `Updater`
- `TelegramForcePortable/tdata`
- `portable-profile.json`
- `portable-launch.log`

Runtime cache лежит здесь:

```text
~/.cache/site-control-kit/telegram-portable-runtime/
```

## Что Смотреть При Диагностике
### `portable-profile.json`
Содержит:
- имя профиля;
- путь к папке;
- путь к `tdata`;
- исходный `zip`;
- источник runtime: `download`, `archive` или `cache`.

### `portable-launch.log`
Содержит stdout/stderr запуска.

### `TelegramForcePortable/log.txt`
Это основной внутренний лог самого Telegram Desktop.
Если там есть строка вида:

```text
Working dir: .../TelegramForcePortable/
```

значит профиль реально поднялся в portable-режиме, а не ушёл в домашний каталог пользователя.

## Правила Безопасности И Поведения
- Один `zip` с `tdata` = один отдельный профиль `~/TelegramPortable-<name>`.
- Не распаковывать другой `zip` поверх уже запущенного профиля.
- Helper сам блокирует переимпорт, если видит, что именно этот `Telegram` уже запущен.
- `tdata` — это фактически пользовательская Telegram-сессия; не пересылать архивы и содержимое profile dir третьим лицам.
- Для повторного импорта того же имени сначала закрыть Telegram этого профиля.

## Что Уже Умеет Делать Надёжно
- находит `tdata`, даже если оно лежит внутри вложенной папки архива;
- безопасно извлекает `zip` и runtime archive без path traversal;
- переиспользует кэш runtime, чтобы не качать Telegram каждый раз заново;
- возвращает JSON-результат, удобный для дальнейшей автоматизации;
- имеет unit-тесты на import, replace, launch и already-running path.

## Что Агенту Полезно Помнить
- Это отдельный helper для Telegram Desktop, а не часть browser API.
- Если задача именно про desktop-сессию из `tdata.zip`, этот инструмент предпочтительнее ручной возни с `tar`, `unzip` и `TelegramForcePortable`.
- Если задача про Telegram Web, чаты, DOM, экспорт usernames, invite execution или browser actions, использовать основной `site-control-kit` browser stack, а не этот helper.
