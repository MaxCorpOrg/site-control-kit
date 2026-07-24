# Инструкция для `config`

## Назначение

Значения по умолчанию для runtime, хаба, логов и прикладных подсистем.

## Как работать

Меняйте `default.yaml` только вместе с `webcontrol/settings.py` и тестами
наследования `env -> .env -> local.yaml -> default.yaml`.

## Ограничения

Не добавляйте реальный токен, домашний путь, публичный IP или данные аккаунта.
Безопасный default слушает loopback.

## Частые ошибки и проверка

Не путайте путь проекта и пользовательский runtime. Запустите
`tests/test_settings.py` и `python -m webcontrol runtime-env --no-create`.

## Документация

Изменение пользовательской настройки отражается в `USER_GUIDE_RU.md` и
`docs/SECURITY.md`.
