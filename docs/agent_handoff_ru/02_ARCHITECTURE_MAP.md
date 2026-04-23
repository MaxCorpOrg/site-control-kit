# Architecture Map

## Общая Схема
У проекта четыре основных слоя:
1. `webcontrol` hub
2. CLI / wrappers
3. browser extension
4. Telegram automation scripts

## Поток Команды
Типичный поток выглядит так:

```text
agent/operator
  -> sitectl / shell script
  -> webcontrol hub
  -> browser extension (background/content)
  -> реальная вкладка сайта
  -> результат обратно в hub
  -> артефакты / файлы / отчёты
```

## Роли Слоёв
### 1. Hub
Хаб хранит:
- клиентов;
- вкладки;
- очередь команд;
- статусы команд;
- итоговые результаты.

Он является единственным источником правды по состоянию browser bridge.

### 2. CLI / wrappers
CLI нужен для:
- ручного управления;
- удобных команд для агента;
- fallback-действий;
- подбора нужной вкладки;
- отладки и smoke-проверок.

### 3. Extension
Расширение делится на два логических слоя:
- `background.js` для tab-level команд;
- `content.js` для DOM-level команд.

### 4. Telegram automation
Скрипты Telegram уровня делают:
- выбор целевого чата;
- scroll/discovery;
- mention/url/profile deep;
- history backfill;
- safe filtering;
- batch output;
- chain orchestration.

## Ключевой Принцип Архитектуры
Browser bridge не должен быть жёстко пришит к Telegram.
Telegram — это прикладной consumer существующего bridge.

То есть архитектурно правильно думать так:
- `webcontrol` и extension — это платформа;
- Telegram scripts — это сложный рабочий сценарий поверх платформы.

## Где Сейчас Основная Сложность
Хаб и расширение уже рабочие.
Основная сложность сейчас концентрируется не в queue или auth, а в глубоком Telegram path:
- обнаружить новых visible peer;
- выбрать правильный peer для deep;
- достать `@username` через `Mention` или URL fallback;
- вернуться в target group dialog;
- не тратить runtime впустую.

## Почему Важны Артефакты
Артефакты run'ов — это не просто логи.
Это часть архитектуры сопровождения.
Они позволяют:
- понимать, где именно оборвался run;
- сравнивать профили `fast/deep`;
- не делать выводы по одному `.txt`;
- строить повторяемый handoff между агентами.
