# Переносимый Telegram Desktop

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

Не использовать его напрямую для задач Telegram Web, browser DOM automation или export flows.
Для invite-flow helper используется только как низкоуровневый actor через `telegram_invite_executor.py`, чтобы state/consent/status оставались в общем invite-контуре.
Session-runner consumer этого helper теперь встроен в `site-control-kit` как `telegram_portable_session_tool`, а operator-facing wrapper виден через `tools/telegram/session_runner/`.
Внутри самого `site-control-kit` видимый operator entrypoint для этого слоя теперь собран в `tools/telegram/portable_helper/`.

## Файлы Инструмента
- `scripts/telegram_portable.py`
- `scripts/telegram_portable_gui.sh`
- `tests/test_telegram_portable.py`

## Что делает помощник
### `import-zip`
Команда:
- принимает путь к `zip` с `tdata`;
- при первом запуске скачивает официальный Linux runtime Telegram Desktop в локальный cache;
- создаёт отдельный профиль `~/TelegramPortable-<profile>`;
- распаковывает `tdata` в `TelegramForcePortable/tdata`;
- пишет metadata в `portable-profile.json`;
- может сразу сохранить `account.username` и `account.label` в metadata;
- по флагу `--launch` сразу запускает Telegram.

### `launch`
Команда:
- берёт уже существующий portable-профиль;
- запускает его повторно;
- если этот же профиль уже запущен, не плодит второй процесс и возвращает `already_running`;
- поддерживает `--display-backend x11`, чтобы на `Wayland` форсировать `QT_QPA_PLATFORM=xcb`;
- сохраняет выбранный backend в `portable-profile.json` как `launch_preferences.display_backend`, чтобы следующий relaunch был воспроизводимым.

### `status`
Команда:
- показывает, запущен ли portable-профиль;
- возвращает `pid`, X11-окна, путь к `TelegramForcePortable/tdata`;
- читает `portable-profile.json`, если профиль уже принят в управление;
- теперь дополнительно возвращает:
  - `session_type`
  - `display`
  - `wayland_display`
  - `display_backend`
  - `attach_proof_mode`
  - Wayland-warning о том, что наличие X11 primitives само по себе не является safe attach.

### `adopt`
Команда:
- принимает уже существующую portable-папку без переимпорта `tdata`;
- пишет `portable-profile.json`;
- позволяет привязать метку аккаунта, например `@M_a_g_g_i_e`;
- нужна для старых папок вида `~/TelegramPortableAK`, которые были созданы до helper-формата `~/TelegramPortable-<profile>`.

### `list`
Команда:
- показывает все portable-профили под выбранным `output-root`;
- полезна агенту перед переключением Telegram-аккаунта.

### `open-uri`
Команда:
- открывает `tg://...` URI через конкретный portable-профиль;
- используется executor-слоем для открытия DM одного пользователя;
- поддерживает `--dry-run`;
- тоже умеет `--display-backend x11`, если нужно послать URI через XWayland-backed launch path.

### `type-text`
Команда:
- печатает ASCII-текст в X11-окно запущенного portable-профиля;
- может нажать Enter только при `--press-enter`;
- используется executor-слоем для controlled one-user invite link flow.

### `press-keys`
Команда:
- отправляет один или несколько X11 key chords в окно portable-профиля;
- принимает repeatable `--sequence`, например `Control_L+f` или `Escape`;
- нужна как no-API keyboard fallback, когда Telegram Desktop реагирует на shortcut надёжнее, чем на правый header-click.

### `log-diagnose`
Команда:
- читает последние строки `TelegramForcePortable/log.txt`;
- вытаскивает `RPC Error`, `API Error`, `App Error`;
- отдельно поднимает сигналы вроде `PEER_FLOOD`, `PEER_ID_INVALID`, `FLOOD_WAIT`;
- нужна для Desktop portable диагностики, когда надо понять, что Telegram уже не даёт делать этому аккаунту.

### `window-click`
Команда:
- кликает в окно portable-профиля по относительным координатам `x_ratio/y_ratio`;
- использует реальную X11-геометрию окна из `wmctrl -l -G -p`;
- нужна как низкоуровневый fallback, когда конкретный Desktop control не имеет стабильного accessibility node.

### `window-screenshot`
Команда:
- снимает PNG именно X11-окна Telegram Desktop по `window_id`, а не просто общий bbox активного экрана;
- полезна для live-debug no-API Desktop-flow, когда нужно проверить, что реально открылось после accessibility/X11 шага;
- особенно нужна для случаев, где правый header Telegram ведёт себя нестабильно.

### `accessibility-dump`
Команда:
- читает AT-SPI accessibility-дерево Telegram Desktop;
- ищет узлы по `query`, `role`, `match_mode`;
- умеет фильтровать только видимые узлы через `--visible-only`;
- умеет фильтровать по AT-SPI state через repeatable `--state`, например `focused` или `editable`;
- нужна для no-API desktop automation, когда надо понять, какие controls Telegram реально отдаёт в системную accessibility layer.

### `accessibility-click`
Команда:
- ищет доступный control по AT-SPI и кликает в его центр;
- если у самого узла нет собственных extents, пробует виртуальную точку через ближайший видимый ancestor container;
- это основной no-API click primitive для Desktop UI-driver.

### `accessibility-type-text`
Команда:
- находит доступное поле по AT-SPI;
- фокусирует его click-ом;
- печатает ASCII-текст через X11 typing helper;
- умеет `--clear-first` и `--press-enter`.

## Базовые Команды
### Импорт и запуск

```bash
cd /home/max/site-control-kit
python3 scripts/telegram_portable.py import-zip \
  --zip "/path/to/tdata.zip" \
  --profile-name "ak" \
  --account-username "@M_a_g_g_i_e" \
  --account-label "@M_a_g_g_i_e" \
  --launch
```

### Импорт без запуска

```bash
python3 scripts/telegram_portable.py import-zip \
  --zip "/path/to/tdata.zip" \
  --profile-name "ak" \
  --account-username "@M_a_g_g_i_e"
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

### Повторный запуск в Wayland через путь на основе XWayland

```bash
python3 scripts/telegram_portable.py launch \
  --profile-dir "/home/max/site-control-kit/runtime/telegram/profiles/TelegramPortable-AK5" \
  --display-backend x11
```

### Принять существующий профиль в управление

```bash
python3 scripts/telegram_portable.py adopt \
  --profile-dir "/home/max/TelegramPortableAK" \
  --profile-name "AK" \
  --account-username "@M_a_g_g_i_e" \
  --account-label "@M_a_g_g_i_e"
```

### Проверить, что нужный профиль запущен

```bash
python3 scripts/telegram_portable.py status \
  --profile-dir "/home/max/TelegramPortableAK"
```

### Список профилей

```bash
python3 scripts/telegram_portable.py list
```

### Низкоуровневое открытие URI и ввод текста

Обычно эти команды вызывает `telegram_invite_executor.py desktop-send-link`.
Ручной запуск нужен только для диагностики:

```bash
python3 scripts/telegram_portable.py open-uri \
  --profile-dir "/home/max/TelegramPortableAK" \
  --uri "tg://resolve?domain=alice_123" \
  --dry-run

python3 scripts/telegram_portable.py open-uri \
  --profile-dir "/home/max/site-control-kit/runtime/telegram/profiles/TelegramPortable-AK5" \
  --display-backend x11 \
  --uri "tg://resolve?domain=telegram"

python3 scripts/telegram_portable.py type-text \
  --profile-dir "/home/max/TelegramPortableAK" \
  --text "https://t.me/Zhirotop_shop" \
  --dry-run

python3 scripts/telegram_portable.py press-keys \
  --profile-dir "/home/max/TelegramPortableAK" \
  --sequence "Control_L+f" \
  --dry-run

python3 scripts/telegram_portable.py window-screenshot \
  --profile-dir "/home/max/TelegramPortableAK" \
  --output /tmp/tg_window.png

python3 scripts/telegram_portable.py log-diagnose \
  --profile-dir "/home/max/TelegramPortableAK"
```

### Действия с интерфейсом рабочего стола без API

Для кодового Desktop-flow без Telegram API:

```bash
python3 scripts/telegram_portable.py accessibility-dump \
  --profile-dir "/home/max/TelegramPortableAK" \
  --query "Info" \
  --role "push button" \
  --match-mode exact \
  --visible-only \
  --pick rightmost

python3 scripts/telegram_portable.py accessibility-dump \
  --profile-dir "/home/max/TelegramPortableAK" \
  --state focused \
  --visible-only

python3 scripts/telegram_portable.py accessibility-click \
  --profile-dir "/home/max/TelegramPortableAK" \
  --query "Info" \
  --role "push button" \
  --match-mode exact \
  --visible-only \
  --pick rightmost \
  --dry-run

python3 scripts/telegram_portable.py accessibility-type-text \
  --profile-dir "/home/max/TelegramPortableAK" \
  --query "Search" \
  --role text \
  --visible-only \
  --pick rightmost \
  --text "bulan04" \
  --dry-run
```

### Графический режим

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

Для принятого legacy-профиля путь может отличаться от нового шаблона.
Например текущий профиль аккаунта `@M_a_g_g_i_e` принят как:

```text
/home/max/TelegramPortableAK/
```

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
Рабочий каталог: `.../TelegramForcePortable/`
```

значит профиль реально поднялся в portable-режиме, а не ушёл в домашний каталог пользователя.

Теперь helper умеет читать этот лог структурированно через `log-diagnose`.
Это полезно, когда надо быстро увидеть:
- `PEER_FLOOD` — Telegram уже режет peer/invite операции;
- `PEER_ID_INVALID` — target/username не резолвится;
- `FLOOD_WAIT` — Telegram требует паузу.

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
- умеет принимать существующий portable-профиль через `adopt`;
- умеет показывать running status и X11-окна через `status`;
- умеет открывать `tg://...` URI через `open-uri`;
- умеет печатать ASCII-текст в окно профиля через `type-text`;
- умеет отправлять произвольные X11 key chords через `press-keys`;
- умеет разбирать `TelegramForcePortable/log.txt` через `log-diagnose`;
- умеет кликать по окну portable-профиля через `window-click`;
- умеет снимать PNG текущего Telegram X11-окна через `window-screenshot`;
- умеет читать AT-SPI accessibility-узлы через `accessibility-dump`;
- умеет фильтровать accessibility-узлы по state (`focused`, `editable`, `showing`);
- умеет кликать по доступным controls через `accessibility-click`;
- умеет печатать текст в доступные поля через `accessibility-type-text`;
- имеет unit-тесты на import, replace, launch и already-running path.

## Что Агенту Полезно Помнить
- Это отдельный helper для Telegram Desktop, а не часть browser API.
- Если задача именно про desktop-сессию из `tdata.zip`, этот инструмент предпочтительнее ручной возни с `tar`, `unzip` и `TelegramForcePortable`.
- Если задача про Telegram Web, DOM, экспорт usernames или browser actions, использовать основной `site-control-kit` browser stack, а не этот helper.
- Если задача про consent-based invite execution через Desktop portable, использовать `scripts/telegram_invite_executor.py`, а не вызывать `open-uri/type-text` напрямую.
- Если нужно понять, почему Telegram Desktop portable перестал давать invite/peer действия, сначала смотреть `log-diagnose`, а уже потом продолжать попытки.
- Если цель именно "без Telegram API, но тоже кодом", начинать теперь можно с accessibility-команд этого helper: они дают более стабильный слой, чем blind X11-click по окну.
- Если правый header Telegram Desktop ведёт себя нестабильно, использовать `press-keys` как отдельный no-API слой для shortcut/focus navigation и проверять layout через `accessibility-dump`.
- Для спорных UI-случаев теперь лучше сразу добавлять `window-screenshot` после каждого шага: это даёт честный Telegram-only PNG по X11 `window_id`, даже если поверх экрана есть другое окно.
