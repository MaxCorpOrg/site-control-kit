# Telegram Portable Helper

Видимая папка low-level Telegram Desktop portable helper внутри `tools/telegram/`.

Основной код живёт в:
- `scripts/telegram_portable.py`
- `scripts/telegram_portable_gui.sh`
- `docs/TELEGRAM_PORTABLE_RU.md`

Эта папка нужна как удобный operator entrypoint и как отдельная единица для unified platform.

## Быстрый Старт

```bash
cd /home/max/site-control-kit/tools/telegram/portable_helper

./bin/telegram-portable --help
./bin/telegram-portable-gui
```

## Что Это Умеет

- импортировать `tdata.zip` в Linux portable profile;
- принимать существующий профиль через `adopt`;
- показывать `status` и `list`;
- поднимать профиль через `--display-backend x11`, если на `Wayland` нужен XWayland-backed attach path;
- открывать `tg://` URI;
- печатать текст и key chords;
- делать window click/screenshot;
- использовать accessibility primitives Telegram Desktop.

## Подключение В Единую Платформу

Инструмент подключён через:

```text
tool_manifest.json
../platform/registry/tools.json
```

То есть helper можно использовать и отдельно, и через общую панель.
