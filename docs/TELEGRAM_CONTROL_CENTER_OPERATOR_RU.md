# Центр управления Telegram: руководство оператора

Этот документ — каноническая точка входа для оператора Telegram control center.

Он нужен, чтобы без чтения кода понять:
- как запустить панель;
- где лежат аккаунты, очереди, сессии и логи;
- где импортировать, скрывать и удалять аккаунты;
- как продолжать `invite`, `session` и `combined` workflow.

Важный product contract:
- `Telegram Control Center` собирается из репозитория `site-control-kit`, но для оператора может устанавливаться отдельно как `.deb`;
- для обычного запуска полный checkout репозитория не нужен;
- репозиторий нужен только для разработки, сборки, отладки и maintainer-команд.

## Где Всё Лежит

Есть два поддерживаемых layout-режима: standalone production install и repo/dev mode.

### Отдельная установка готового пакета `.deb`

Установленное приложение живёт здесь:

- app bundle: `/opt/site-control-kit/app`
- запуск: `telegram-control-center`

Пользовательский runtime живёт в XDG-папках:

- profiles / invite jobs / session / unified state:
  - `~/.local/share/site-control-kit/telegram/`
- runtime configs:
  - `~/.config/site-control-kit/telegram/runtime_configs/`
- panel log:
  - `~/.local/state/site-control-kit/logs/telegram/panel/telegram-control-center-panel.log`
- cache:
  - `~/.cache/site-control-kit/telegram/`

### Запуск из репозитория для разработки

Если панель запускается прямо из исходников, runtime root остаётся project-local:

`/home/max/site-control-kit/runtime/telegram`

Главные подпапки:
- `profiles/` — project-local Telegram Desktop portable-профили.
- `invite_jobs/` — очереди и execution-артефакты invite batch.
- `session/configs/` — session-конфиги.
- `session/state/` — session state.
- `session/runs/` — session-run артефакты.
- `state/jobs/` — unified jobs index.
- `state/locks/` — profile locks.
- `state/agent/` — machine-readable handoff.
- `logs/panel/` — лог панели.

## Как Запустить

Отдельная установленная версия:

```bash
telegram-control-center
```

Режим разработки из репозитория:

Из корня репозитория:

```bash
cd /home/max/site-control-kit
./tools/telegram/platform/bin/tool-platform-panel
```

CLI-health для выбранного профиля в repo/dev mode:

```bash
./tools/telegram/platform/bin/tool-platform profile-health --profile-name AK3 --profile-dir /home/max/site-control-kit/runtime/telegram/profiles/TelegramPortable-AK3
```

## Основной Порядок Работы

1. Выбрать профиль в верхнем dropdown.
2. Проверить блок `Профиль и workflow`.
3. Если профиль не запущен или attach не готов, сначала восстановить профиль.
4. Затем выбрать один из трёх режимов:
   - `Добавить контакты из TXT`
   - `Сессия и сообщения`
   - `Совместный режим: Добавить → Сессия`

## Работа С Аккаунтами

Кнопка `Аккаунты...` — единая точка входа для lifecycle профиля.

Что там можно сделать:
- импортировать новый `tdata.zip` прямо в `runtime/telegram/profiles/`;
- забрать внешний portable-профиль в проект по схеме `copy-then-switch`;
- скрыть аккаунт из основного списка панели;
- вернуть скрытый аккаунт;
- удалить project-local portable-папку профиля;
- открыть папку профиля, лог или весь runtime root.

Важно:
- внешние профили больше не считаются нормальной постоянной базой хранения;
- рабочий steady-state storage всегда должен быть внутри `runtime/telegram/profiles/`.
- для standalone production install это означает тот же Telegram runtime внутри `~/.local/share/site-control-kit/telegram/profiles/`.

## Приглашения: добавить контакты из TXT

Порядок:
1. Выбрать профиль.
2. Открыть режим `Добавить контакты из TXT`.
3. Выбрать `.txt`, `.csv` или `.json`.
4. Проверить `Папка задачи`.
5. Поставить лимит batch.
6. Использовать нужную кнопку:
   - `Старт добавления`
   - `Продолжить очередь`
   - `Повторить ошибки`
   - `Статус задачи`
   - `Что осталось`
   - `Стоп`

Что смотреть во время работы:
- `Текущее состояние задачи`
- `История запусков`
- `Последние ошибки`
- `Осталось в очереди`
- `Уже добавлены`
- `Живой статус и лог`

## Сессия: посещение и сообщения

Порядок:
1. Выбрать session config.
2. Загрузить список адресатов.
3. Проверить настройки:
   - визитов за цикл;
   - минимум/максимум секунд в чате;
   - сообщений за цикл;
   - общий лимит;
   - автоотправка;
   - непрерывный режим.
4. Использовать:
   - `Старт сессии`
   - `Показать план`
   - `Продолжить workflow`
   - `Стоп`

## Объединённый сценарий: добавить → провести сессию

Порядок:
1. Выбрать файл контактов.
2. Проверить session config.
3. Проверить шаблон шагов.
4. Использовать:
   - `Старт общего режима`
   - `Продолжить workflow`
   - `Стоп`

Важно:
- persisted workflow progression живёт в unified jobs/state;
- operator draft inputs живут отдельно;
- GUI не должен путать historical state и текущие поля формы.

## Если Панель Пишет, Что Окно Недоступно

Панель теперь честно блокирует live workflow, если attach небезопасен.

Типичный recovery path:
1. Нажать `Обновить статус`.
2. Если профиль в `running_without_window`, перезапустить сам portable-профиль.
3. Повторно проверить `attach_status`.
4. Только потом снова жать `Старт` или `Продолжить`.

Attach gating ослаблять не нужно.

## Где Смотреть Артефакты И Логи

Главные быстрые точки:
- лог панели:
  - `/home/max/site-control-kit/runtime/telegram/logs/panel/telegram-control-center-panel.log`
- runtime agent handoff:
  - `/home/max/site-control-kit/runtime/telegram/state/agent/`
- invite jobs:
  - `/home/max/site-control-kit/runtime/telegram/invite_jobs/`
- session runs:
  - `/home/max/site-control-kit/runtime/telegram/session/runs/`

Для maintenance-операций и historical repair использовать отдельный runbook:
- [TELEGRAM_CONTROL_CENTER_RUNBOOK_RU.md](/home/max/site-control-kit/docs/TELEGRAM_CONTROL_CENTER_RUNBOOK_RU.md)
