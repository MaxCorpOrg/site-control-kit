# Запуск на других устройствах и браузерах

Документ описывает перенос `site-control-kit` на любой другой компьютер и подключение расширения в популярных браузерах.

## 1. Что нужно заранее

- ОС: Linux / macOS / Windows.
- Python: 3.10+.
- Браузер на Chromium (Chrome, Edge, Brave, Chromium, Opera, Яндекс Браузер).
- Доступ к файлам проекта (`git clone` или копия папки).

## 2. Базовая схема

Есть 2 варианта:

1. Хаб и браузер на одном устройстве (самый простой).
2. Хаб на устройстве A, браузер-клиент на устройстве B (LAN/интернет).

В обоих случаях токен в хабе и расширении должен совпадать.

## 3. Установка проекта на новое устройство

### В Windows

```powershell
git clone <URL_вашего_репозитория> site-control-kit
cd site-control-kit
python -m pip install -e .
```

Проверка командного интерфейса:

```powershell
sitectl --help
```

### В Linux и macOS

```bash
cd ~
git clone <URL_вашего_репозитория> site-control-kit
cd site-control-kit
python3 -m pip install -e .
```

Проверка командного интерфейса:

```bash
sitectl --help
```

## 4. Запуск хаба

### В Windows

```cmd
cd C:\site-control-kit
scripts\start_hub.cmd
```

Если нужен собственный токен:

```powershell
$env:SITECTL_TOKEN = "очень-длинный-случайный-токен"
.\scripts\start_hub.ps1
```

### В Linux и macOS

### 4.1 Локальный быстрый режим

```bash
cd ~/site-control-kit
./scripts/start_hub.sh
```

Используется токен по умолчанию:
- `local-bridge-quickstart-2026`

Этот режим подходит только для личной локальной машины.

### 4.2 Безопасный режим (рекомендуется)

```bash
cd ~/site-control-kit
export SITECTL_TOKEN='очень-длинный-случайный-токен'
./scripts/start_hub.sh
```

### 4.3 Хаб для подключения с другого устройства

```bash
cd ~/site-control-kit
export SITECTL_HOST='0.0.0.0'
export SITECTL_PORT='8765'
export SITECTL_TOKEN='очень-длинный-случайный-токен'
./scripts/start_hub.sh
```

После запуска используйте IP машины-хаба, например:
- `http://192.168.1.50:8765`

Важно:
- предпочтите SSH-туннель и оставьте хаб на `127.0.0.1`;
- если нужен прямой доступ, откройте порт в межсетевом экране только для доверенной сети;
- не публикуйте хаб в интернет без TLS и дополнительной проверки доступа;
- текущая версия рассчитана на одного доверенного оператора, а не на общий многопользовательский сервер.

## 5. Установка расширения в браузер

## Chrome / Chromium / Brave / Opera / Яндекс Браузер

1. Откройте страницу расширений браузера:
- Chrome/Brave/Chromium: `chrome://extensions`
- Edge: `edge://extensions`
- Opera: `opera://extensions`
- Яндекс: `browser://extensions`
2. Включите режим разработчика (`Developer mode`, то есть режим загрузки локальных расширений).
3. Нажмите `Load unpacked` («Загрузить распакованное расширение») или аналог.
4. Выберите папку `.../site-control-kit/extension`.

### В Windows

Для Windows путь такой же, только выбирайте папку `C:\site-control-kit\extension`.

## Edge
Шаги те же, только страница `edge://extensions`.

## 6. Настройка расширения

Откройте настройки (`Options`) расширения и заполните:
- адрес сервера (`Server URL`):
  - локально: `http://127.0.0.1:8765`
  - удалённый хаб: `http://<IP_ХАБА>:8765`
- `Токен доступа`: такой же, как `SITECTL_TOKEN` у хаба.
- идентификатор клиента (`ID клиента`): можно оставить автоматическую генерацию.

Нажмите `Сохранить`.

## 7. Проверка подключения

На машине с командным интерфейсом:

```bash
cd ~/site-control-kit
sitectl health
sitectl clients
```

В списке клиентов должен появиться `client_id` расширения.

Тест команды:

```bash
sitectl send --type navigate --client-id client-REPLACE_ME --url https://example.com --wait 20
```

## 8. Запуск на нескольких устройствах сразу

Один хаб может обслуживать много клиентов.

Рекомендация:
- на каждом устройстве свой браузер-клиент с уникальным `client_id`.
- для точной маршрутизации всегда указывайте `--client-id`.

## 9. Обновление проекта на устройствах

### В Windows

```powershell
cd C:\site-control-kit
git pull
python -m pip install -e .
```

Если менялся код расширения:
- откройте страницу расширений браузера;
- нажмите `Reload` («Перезагрузить») для `Site Control Bridge`.

### В Linux и macOS

```bash
cd ~/site-control-kit
git pull
python3 -m pip install -e .
```

Если менялся код расширения:
- откройте страницу расширений;
- нажмите `Reload` («Перезагрузить») для `Site Control Bridge`.

## 10. Частые проблемы

- `401 unauthorized`: не совпадает токен хаба и расширения/CLI.
- Команды в `pending`: расширение не подключено или service worker уснул.
- `run_script` падает: CSP сайта запрещает `unsafe-eval`.
- `No response from content script`: служебная вкладка (`chrome://...`) или ограниченная страница.

Подробно: `docs/TROUBLESHOOTING.md`.
