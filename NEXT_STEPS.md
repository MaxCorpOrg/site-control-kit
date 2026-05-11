# Next Steps

Дата: 2026-05-11

## Текущий Приоритет

Главный следующий gate: clean Ubuntu 24.04 VM smoke для `.deb` пакета `Telegram Username Collector`.

Нужно выполнить на чистой Ubuntu 24.04 VM с графической сессией и доступным `sudo`:

```bash
git clone https://github.com/MaxCorpOrg/site-control-kit.git site-control-kit-product-smoke
cd site-control-kit-product-smoke
git checkout main
git rev-parse HEAD
bash scripts/build_linux_deb.sh
sudo apt install -y ./dist/linux-deb/telegram-username-collector_0.1.0_amd64.deb
telegram-username-collector --doctor
telegram-username-collector --create-desktop-shortcut
gtk-launch telegram-username-collector
```

Ожидаемый `HEAD`: `3412ccd26d5ebcd3710a50b8f6c0b5b9696a6447` или более новый commit с checkpoint-only документацией.

## Что Проверить

- `/usr/bin/telegram-username-collector` и `/usr/bin/sitectl` доступны после установки.
- `/opt/telegram-username-collector/app` и `/opt/telegram-username-collector/venv` существуют.
- `telegram-username-collector --doctor` показывает `mode=installed`, `gtk_runtime=ok`, `extension_zip_ready=1`.
- Пользовательские данные создаются в `~/.config/site-control-kit`, `~/.local/share/site-control-kit`, `~/.local/state/site-control-kit/logs`.
- В `/opt/telegram-username-collector` нет пользовательских runtime-файлов.
- GUI запускается из Applications menu или через `gtk-launch telegram-username-collector`.

## Не Делать В Следующем Цикле

- Не начинать новый Telegram feature-cycle до закрытия clean VM smoke.
- Не делать Windows productization; Windows сейчас secondary compatibility smoke.
- Не коммитить `.codex/`, `TG_CONTACT/`, `.site-control-kit/`, `dist/`, логи, токены и локальные export artifacts.
