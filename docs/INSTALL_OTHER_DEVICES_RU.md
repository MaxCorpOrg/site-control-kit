# Запуск на других устройствах

Документ описывает перенос `site-control-kit` на новую машину без ручной правки кода.

## 1. Поддерживаемая модель v1

- Linux:
  - production-ready `hub + browser + telegram-username-collector`
  - GTK GUI работает только через системный `python3` с установленными GTK bindings
- Windows:
  - production-ready `hub + browser + wrappers + docs`
  - GTK GUI не входит в Windows v1

## 2. Что нужно заранее

- Python `3.10+`, рекомендовано `3.11+`
- git
- Chromium-совместимый браузер для `extension/`
- для Linux Telegram GUI:
  - системный `python3`
  - рабочий `python3-gi`
  - GTK 4 runtime

## 3. Базовый runtime-контракт

- runtime root по умолчанию: `./var/site-control-kit`
- precedence настроек:
  - `env`
  - `.env`
  - `.site-control-kit/local.yaml`
  - `config/default.yaml`
- если на машине уже есть legacy runtime `~/.site-control-kit`, проект не переносит его автоматически
- вместо переноса создаётся `.site-control-kit/local.yaml`, который явно указывает на существующий runtime

Проверка:

```bash
cd <repo-root>
python3 -m webcontrol runtime-env --format json
```

## 4. Установка

### Linux

```bash
git clone <repo-url> site-control-kit
cd site-control-kit
python3 -m pip install -r requirements.txt
python3 -m pip install -e .
```

Telegram GUI Linux preflight:

```bash
cd <repo-root>
bash scripts/bootstrap_telegram_workstation.sh --doctor
```

### Windows

```powershell
git clone <repo-url> site-control-kit
cd site-control-kit
py -3.11 -m pip install -r requirements.txt
py -3.11 -m pip install -e .
```

## 5. Токен и конфиги

- пример env: `.env.example`
- базовый конфиг: `config/default.yaml`
- если `SITECTL_TOKEN` не задан, локальный runtime создаёт `.site-control-kit/generated_token.txt`
- для shared/remote сценариев используйте явный `SITECTL_TOKEN`, а не generated token

## 6. Запуск хаба

### Linux

```bash
cd <repo-root>
./scripts/start_hub.sh
```

### Windows

```cmd
cd <repo-root>
scripts\start_hub.cmd
```

## 7. Запуск browser-контура

После старта хаба:

### Linux

```bash
cd <repo-root>
./browser.sh status
./browser.sh tabs
```

### Windows

```cmd
cd <repo-root>
browser.cmd status
browser.cmd tabs
```

Если расширение ещё не загружено:

1. Откройте страницу расширений браузера.
2. Включите `Developer mode`.
3. Нажмите `Load unpacked`.
4. Выберите `<repo-root>/extension`.
5. В `Options` расширения задайте:
   - `Server URL`: `http://127.0.0.1:8765`
   - `Access Token`: тот же токен, что использует хаб

## 8. Запуск Telegram GUI

### Linux

```bash
cd <repo-root>
bash scripts/bootstrap_telegram_workstation.sh
telegram-username-collector
```

Если launcher запущен в Python-окружении без GTK bindings, он завершится понятной ошибкой и отправит в `bootstrap_telegram_workstation.sh --doctor`.

### Windows

GTK GUI не входит в Windows v1.
Используйте Windows только для core/browser-контура или запускайте Telegram GUI на Linux workstation.

## 9. Где лежат данные и логи

В project-local режиме:

- `var/site-control-kit/state/state.json`
- `var/site-control-kit/logs/hub.log`
- `var/site-control-kit/logs/runtime_events.jsonl`
- `var/site-control-kit/logs/runtime_errors.jsonl`
- `var/site-control-kit/reports/`
- `var/site-control-kit/telegram_workspace/`

В adopted legacy режиме те же каталоги будут жить под `~/.site-control-kit/...`, а `.site-control-kit/local.yaml` внутри репозитория будет только pointer-файлом.

## 10. Минимальная проверка

### Linux

```bash
cd <repo-root>
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m webcontrol --help
python3 -m webcontrol browser --help
bash scripts/bootstrap_telegram_workstation.sh --doctor
```

### Windows

```powershell
cd <repo-root>
python -m unittest discover -s tests -p "test_*.py"
python -m webcontrol --help
python -m webcontrol browser --help
```

## 11. Windows core smoke checklist

Этот checklist обязателен для следующего production-checkpoint на реальной Windows-машине:

```cmd
cd <repo-root>
scripts\start_hub.cmd
browser.cmd status
browser.cmd tabs
python -m webcontrol --help
python -m webcontrol browser --help
python -m webcontrol runtime-env --format json --no-create
```

Что нужно подтвердить:
- в fresh checkout runtime-каталоги создаются автоматически;
- `browser.cmd` использует resolved runtime, а не machine-specific path;
- UTF-8 пути и русский текст читаемы в console output;
- `telegram-username-collector` на Windows завершает запуск понятным fast-fail сообщением, а не traceback, потому что GTK GUI не входит в Windows v1.

## 12. Что не делать

- не хардкодить токен в локальных скриптах
- не переносить вручную `~/.site-control-kit` внутрь репозитория без отдельного решения
- не считать Windows GTK GUI поддержанным в v1
