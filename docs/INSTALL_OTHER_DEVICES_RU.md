# Установка на другом устройстве

Этот документ описывает перенос браузерного ядра на Linux или Windows.
Пошаговый первый запуск находится в
[`USER_GUIDE_RU.md`](../USER_GUIDE_RU.md).

## Что поддерживается

- Linux: хаб, CLI и расширение Chromium; отдельно доступен Telegram GTK GUI;
- Windows: хаб, CLI, расширение и `.cmd`/PowerShell wrappers;
- macOS: Python-хаб и расширение можно запускать из исходников, но отдельный
  пакет пока не проверен.

Нужно установить Python 3.10+, Git и Chrome, Chromium или Edge.

## Установка из исходников

```bash
git clone https://github.com/MaxCorpOrg/site-control-kit.git
cd site-control-kit
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -e .
```

На Windows:

```powershell
git clone https://github.com/MaxCorpOrg/site-control-kit.git
cd site-control-kit
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

Ожидается установленная команда `sitectl`. Если активация PowerShell
запрещена, временно разрешите локальные сценарии согласно политике вашей
организации или вызывайте `.\.venv\Scripts\python.exe -m webcontrol`.

## Настройки и рабочие данные

Приоритет настроек:

1. переменные процесса;
2. `.env`;
3. `.site-control-kit/local.yaml`;
4. `config/default.yaml`.

Точный путь без создания файлов:

```bash
python3 -m webcontrol runtime-env --format json --no-create
```

По умолчанию рабочие данные находятся в `var/site-control-kit`. Хаб создаёт
SQLite-файл рядом с совместимым JSON-снимком, журналы и артефакты. Не
переносите браузерный профиль или токен через Git.

## Токен

Если `SITECTL_TOKEN` не задан, первый запуск создаёт случайный локальный токен
в `.site-control-kit/generated_token.txt`. Посмотреть разрешённый для ручной
настройки вывод можно так:

```bash
python3 -m webcontrol runtime-env --format json --show-secrets
```

Не прикладывайте этот вывод к issue или логу: он содержит секрет. Для
диагностики используйте ту же команду без `--show-secrets`.

Для общей или удалённой машины задайте отдельный длинный токен через менеджер
секретов либо `SITECTL_TOKEN`. Токен передаётся только HTTP-заголовком.

## Запуск

Linux:

```bash
./scripts/start_hub.sh
./browser.sh status
./browser.sh tabs
```

Windows:

```cmd
scripts\start_hub.cmd
browser.cmd status
browser.cmd tabs
```

После установки распакованного расширения из `extension/` укажите адрес хаба
и тот же токен. Ожидается хотя бы один онлайн-клиент.

## Локальная сеть

Хаб намеренно слушает только `127.0.0.1`. Для доступа с другой машины не
открывайте порт напрямую. Используйте SSH-туннель, ограниченный список Origin,
отдельный токен и правила межсетевого экрана. Практический вариант описан в
[`SERVER_BROWSER_ACCESS.md`](SERVER_BROWSER_ACCESS.md).

## Проверка новой машины

```bash
PYTHONPATH="$PWD" python3 -m unittest discover -s tests -p 'test_*.py'
python3 scripts/check_docs.py
python3 -m webcontrol --help
python3 -m webcontrol browser --help
sitectl health
sitectl browser status
sitectl browser tabs
```

На Windows используйте `python` вместо `python3`, если именно так называется
интерпретатор.

## Telegram и Linux-пакет

Telegram GTK GUI и `.deb` — отдельная прикладная подсистема. Её установка
описана в [`LINUX_PRODUCT_INSTALL_RU.md`](LINUX_PRODUCT_INSTALL_RU.md). Не
смешивайте проверку Telegram-пакета с приёмкой браузерного протокола.

## Удаление

1. остановите хаб;
2. удалите расширение;
3. выполните `python3 -m pip uninstall site-control-kit`;
4. после резервной копии удалите runtime-каталог, показанный `runtime-env`.

Удаление исходников не удаляет пользовательские данные автоматически.
