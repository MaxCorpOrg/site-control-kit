# Быстрый старт браузерного контура

Полная инструкция находится в [руководстве пользователя](USER_GUIDE_RU.md).
Здесь только минимальный рабочий путь.

## Запуск

```bash
PYTHONPATH="$PWD" python3 -m webcontrol serve
```

После установки расширения:

```bash
sitectl browser status
sitectl browser tabs
sitectl browser open https://example.com
sitectl browser snapshot
```

Ожидается онлайн‑клиент, вкладка `example.com` и семантические строки с `ref`.

## Действия

```bash
sitectl browser smart-click --role link --name "More information..." --exact
sitectl browser set-text --label "Имя" "Анна"
sitectl browser wait-for --text "Готово" --state visible --exact
sitectl browser screenshot --full-page
```

Для iframe передайте `--frame-id` перед подкомандой:

```bash
sitectl browser --frame-id 3 smart-click --role button --name "Сохранить" --exact
```

## Безопасный порядок агента

1. Проверить `status` и `tabs`.
2. Создать сессию.
3. Заблокировать точную вкладку.
4. Получить `snapshot`.
5. Выполнить действие с проверкой результата.
6. Закрыть сессию.

Никогда не повторяйте опасный клик после `running`, если неизвестно, был ли он
выполнен. Сначала прочитайте состояние страницы.

API и состояния доставки описаны в [контракте протокола](docs/API.md).
