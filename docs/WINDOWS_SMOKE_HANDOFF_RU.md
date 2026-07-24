# Контрольная проверка Windows

## Цель

Подтвердить запуск хаба, CLI и расширения на чистой Windows‑машине. Telegram
GTK и Linux‑пакет в эту проверку не входят.

## Подготовка

```powershell
git status --short --branch
python --version
```

Рабочее дерево должно быть чистым, Python — 3.10 или новее.

## Установка

```powershell
python -m pip install -e .
```

## Запуск хаба

```powershell
.\start-hub.cmd
```

Ожидается:

```text
Server started on http://127.0.0.1:8765
```

## Проверка до расширения

```powershell
.\browser.cmd status
```

Хаб должен отвечать, но клиентов может не быть.

## Установка расширения

1. Открыть `chrome://extensions`.
2. Включить режим разработчика.
3. Загрузить папку `extension`.
4. Указать адрес и токен хаба.
5. Нажать Heartbeat.

## Основная быстрая проверка

```powershell
.\browser.cmd status
.\browser.cmd tabs
.\browser.cmd open https://example.com
python -m webcontrol browser snapshot
python -m webcontrol browser screenshot --output windows-smoke.png
```

Ожидается онлайн‑клиент, одна вкладка и PNG‑файл.

## Что записать

- версия Windows, Python и Chrome;
- SHA коммита;
- команды и коды выхода;
- число тестов;
- путь к локальному скриншоту;
- точный текст ошибки, если шаг не прошёл.

Токен, имя пользователя и приватные абсолютные пути в отчёт не включать.

## Завершение

Остановить хаб через `Ctrl+C`, удалить временный скриншот или сохранить его как
защищённый артефакт CI. Обновить `PROJECT_STATUS_RU.md` только итогом и
риском.
