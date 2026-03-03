# Site Control Kit

Локальный набор инструментов для управления сайтами через браузерное расширение и локальный хаб-команд.

## Что внутри
- Локальный HTTP-хаб управления (`webcontrol`) с очередью команд и сохранением состояния.
- CLI (`sitectl` / `python3 -m webcontrol`) для отправки команд и диагностики.
- Расширение браузера (Manifest V3) для выполнения команд в реальных вкладках.
- Подробная документация для пользователя и ИИ-агентов сопровождения.

## Основные сценарии
- Открывать нужные URL во вкладках.
- Кликать по элементам, заполнять поля, ждать появления селекторов.
- Извлекать текст/HTML, делать скриншоты вкладок.
- Управлять несколькими клиентами (браузерами) через `client_id`.

## Архитектура

```text
CLI (sitectl) <----HTTP----> Локальный хаб (Python) <----HTTP poll----> Расширение браузера
                                                                      |
                                                                      +--> Content Script -> DOM-действия
```

Хаб — единый источник правды: клиенты, очередь команд, результаты выполнения.

## Быстрый старт (локальный режим)

## 1) Запуск хаба

```bash
cd /home/max/site-control-kit
./scripts/start_hub.sh
```

Если `SITECTL_TOKEN` не задан, используется быстрый локальный токен:
`local-bridge-quickstart-2026`.

Важно: для реальной/удалённой эксплуатации задайте свой токен:

```bash
cd /home/max/site-control-kit
export SITECTL_TOKEN='ваш-сильный-секретный-токен'
./scripts/start_hub.sh
```

## 2) Установка расширения (без публикации в Store)
1. Откройте `chrome://extensions`.
2. Включите `Developer mode`.
3. Нажмите `Load unpacked`.
4. Выберите папку: `/home/max/site-control-kit/extension`.
5. Откройте `Options` расширения и проверьте:
- `Server URL`: `http://127.0.0.1:8765`
- `Access Token`: тот же, что у хаба.

Упаковка в zip:

```bash
cd /home/max/site-control-kit
./scripts/package_extension.sh
```

Готовый архив: `dist/site-control-bridge-extension.zip`

## 3) Проверка связи

```bash
cd /home/max/site-control-kit
python3 -m webcontrol health
python3 -m webcontrol clients
```

## 4) Примеры команд

```bash
# Открыть страницу в активной вкладке клиента
python3 -m webcontrol send \
  --type navigate \
  --client-id client-REPLACE_ME \
  --url "https://example.com" \
  --wait 20
```

```bash
# Заполнить поле и кликнуть кнопку
python3 -m webcontrol send --type fill --client-id client-REPLACE_ME --selector "#email" --value "user@example.com"
python3 -m webcontrol send --type click --client-id client-REPLACE_ME --selector "button[type='submit']"
```

```bash
# Подождать селектор
python3 -m webcontrol send --type wait_selector --client-id client-REPLACE_ME --selector "body" --wait 20
```

```bash
# Извлечь текст
python3 -m webcontrol send --type extract_text --client-id client-REPLACE_ME --selector "main" --wait 20
```

## 5) Просмотр состояния хаба

```bash
python3 -m webcontrol state
```

## Установка CLI как команды `sitectl`

```bash
cd /home/max/site-control-kit
python3 -m pip install -e .
```

После этого можно использовать:

```bash
sitectl clients
sitectl state
sitectl send --type navigate --client-id client-... --url https://example.com --wait 20
```

## Работа на других устройствах
Подробно: [INSTALL_OTHER_DEVICES_RU.md](docs/INSTALL_OTHER_DEVICES_RU.md)

Коротко:
1. Скопировать репозиторий на устройство.
2. Запустить хаб.
3. Загрузить расширение в браузер.
4. Указать URL/токен.
5. Проверить `clients`.

Поддерживаемые браузеры для загрузки unpacked-расширения:
- Google Chrome
- Microsoft Edge
- Brave
- Chromium
- Opera
- Яндекс Браузер

## Документация
- [CHANGES_RU.md](docs/CHANGES_RU.md) — полный перечень реализованных изменений.
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — архитектура и жизненный цикл команд.
- [API.md](docs/API.md) — API и контракт команд.
- [EXTENSION.md](docs/EXTENSION.md) — внутренняя логика расширения.
- [SECURITY.md](docs/SECURITY.md) — безопасность и рекомендации.
- [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — диагностика проблем.
- [AI_MAINTAINER_GUIDE.md](docs/AI_MAINTAINER_GUIDE.md) — гайд для ИИ-сопровождения.
- [AGENTS.md](AGENTS.md) — правила для ИИ-агентов в репозитории.

## Структура проекта

```text
webcontrol/         # Python: сервер, очередь, CLI
extension/          # Расширение браузера (MV3)
scripts/            # Вспомогательные скрипты запуска/упаковки/экспорта
docs/               # Полная документация
examples/           # Примеры payload-команд
tests/              # Автотесты
```

## Важные ограничения
- `run_script` может блокироваться CSP сайта (`unsafe-eval`), это нормально.
- На служебных страницах (`chrome://*`) content script не работает.
- Manifest V3 service worker может «засыпать», поэтому есть polling + alarms.

## Правовые границы
Используйте инструмент только для сайтов и систем, где у вас есть разрешение на автоматизацию.

## Публикация на GitHub

```bash
cd /home/max/site-control-kit
git config user.name "Ваше имя в GitHub"
git config user.email "ваш_email@example.com"
git add .
git commit -m "Стартовая версия: локальный хаб, расширение и документация (RU)"
git remote add origin https://github.com/<ВАШ_ЛОГИН>/site-control-kit.git
git push -u origin main
```

Если репозиторий `site-control-kit` ещё не создан в GitHub:
1. Откройте GitHub и создайте пустой репозиторий `site-control-kit` без README/.gitignore.
2. Выполните команды выше для первого push.
