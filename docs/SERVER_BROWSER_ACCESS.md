# Доступ к браузеру на сервере

Документ объясняет, как управлять браузером, запущенным на сервере, и когда нужен визуальный доступ через noVNC. Термины собраны в [словаре](TERMS_RU.md).

## Правила безопасности

- По умолчанию хаб и noVNC должны слушать только `127.0.0.1`.
- Для удалённого доступа используйте SSH-туннель или другой защищённый канал.
- Не публикуйте в документации IP-адрес, пароль noVNC и токен хаба.
- Не оставляйте порт noVNC открытым после завершения ручной работы.
- Перед изменяющей командой явно проверьте клиент и вкладку.

Пример SSH-туннеля с рабочей машины:

```bash
ssh -L 6080:127.0.0.1:6080 -L 8765:127.0.0.1:8765 user@server.example
```

После подключения визуальный интерфейс доступен локально:

```text
http://127.0.0.1:6080/vnc.html?host=127.0.0.1&port=6080
```

## Запуск noVNC

Предпочтительный способ:

```bash
cd /home/max/site-control-kit
NOVNC_LISTEN_HOST=127.0.0.1 ./scripts/start_browser_novnc.sh
```

Сценарий поднимает доступ поверх текущего X11-экрана и сохраняет служебные файлы в `~/.cache/site-control-kit/novnc`.

Если приходится запускать компоненты вручную:

```bash
websockify --web=/usr/share/novnc 6080 127.0.0.1:5900
```

Не открывайте `6080/tcp` во внешний интернет. Если временное правило межсетевого экрана всё же необходимо, ограничьте адрес источника и удалите правило сразу после работы.

## Проверка noVNC

```bash
curl -I http://127.0.0.1:6080/vnc.html
```

Ожидается ответ `HTTP/1.1 200 OK`.

Проверить слушающий процесс:

```bash
ss -ltnp | rg ':6080'
```

## Остановка noVNC

```bash
cd /home/max/site-control-kit
./scripts/stop_browser_novnc.sh
```

После остановки проверьте, что временные правила межсетевого экрана удалены.

## Токен хаба

Токен берите из защищённой настройки текущей установки и передавайте через переменную среды:

```bash
export SITECTL_TOKEN='ЗНАЧЕНИЕ_ИЗ_ЗАЩИЩЁННОГО_ХРАНИЛИЩА'
```

Не вставляйте реальное значение в историю оболочки, снимки экрана, отчёты и коммиты. Для системной установки расположение файла среды определяет оператор; не полагайтесь на один жёстко заданный путь.

## Основное управление браузером

Из корня репозитория:

```bash
cd /home/max/site-control-kit
PYTHONPATH="$PWD" python3 -m webcontrol browser status
PYTHONPATH="$PWD" python3 -m webcontrol browser clients
PYTHONPATH="$PWD" python3 -m webcontrol browser tabs
```

Открыть сайт:

```bash
PYTHONPATH="$PWD" python3 -m webcontrol browser open 'https://example.com/'
```

Открыть новую вкладку:

```bash
PYTHONPATH="$PWD" python3 -m webcontrol browser new-tab 'https://example.com/form'
```

Получить компактный снимок для агента:

```bash
PYTHONPATH="$PWD" python3 -m webcontrol browser snapshot
```

Прочитать текст или HTML:

```bash
PYTHONPATH="$PWD" python3 -m webcontrol browser text body
PYTHONPATH="$PWD" python3 -m webcontrol browser html body
```

Умный клик и ввод:

```bash
PYTHONPATH="$PWD" python3 -m webcontrol browser smart-click --role button --name 'Сохранить'
PYTHONPATH="$PWD" python3 -m webcontrol browser set-text 'Макс' --label 'Имя'
PYTHONPATH="$PWD" python3 -m webcontrol browser wait-for --text 'Сохранено'
```

Снимок экрана:

```bash
PYTHONPATH="$PWD" python3 -m webcontrol browser screenshot --output /tmp/page.png
```

## Явный выбор страницы

По фрагменту URL:

```bash
PYTHONPATH="$PWD" python3 -m webcontrol browser \
  --url-pattern '/form' \
  snapshot
```

По идентификатору вкладки:

```bash
PYTHONPATH="$PWD" python3 -m webcontrol browser \
  --tab-id 123456 \
  screenshot --output /tmp/tab.png
```

Если подключено несколько браузеров, дополнительно передайте `--client-id`. Идентификаторы всегда берите из свежего вывода `browser clients` и `browser tabs`.

## Рабочая последовательность

1. Убедитесь, что хаб и браузер запущены.
2. Проверьте `browser status`.
3. Посмотрите клиентов и вкладки.
4. Явно выберите цель, если их больше одной.
5. Откройте страницу и получите снимок.
6. Выполните действие по `ref` или семантическому локатору.
7. Дождитесь наблюдаемого результата.
8. Повторно прочитайте страницу или сделайте снимок экрана.
9. Используйте noVNC только для ручной авторизации, проверки или восстановления.
10. После работы остановите временный визуальный доступ.
