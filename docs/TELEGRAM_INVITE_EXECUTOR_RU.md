# Telegram Invite Executor RU

## Что Это
`Telegram Invite Executor` — новый безопасный execution-слой внутри `site-control-kit` для `Telegram Invite Manager`.

Он не делает массовое добавление пользователей в чат и не реализует обход лимитов Telegram.
Его задача другая:
- держать конфигурацию consent-based invite workflow;
- готовить execution-plan для оператора;
- использовать `site-control` для открытия нужного Telegram-чата;
- сохранять execution-артефакты;
- записывать результат ручных действий обратно в `invite_state.json`.

## Файлы
- `scripts/telegram_invite_executor.py`
- `scripts/telegram_invite_executor_gui.sh`
- `tests/test_telegram_invite_executor.py`

## Как Он Связан С Invite Manager
`Invite Manager` остаётся источником истины по пользователям и статусам:
- `invite_state.json`
- `invite_run.json`

`Invite Executor` использует тот же `invite_state.json`, но работает уже на слое исполнения:
- `configure`
- `plan`
- `inspect-chat`
- `open-chat`
- `add-contact`
- `record`
- `report`

## Что Хранится В State
В `invite_state.json` теперь может появляться секция:

```json
{
  "execution": {
    "invite_link": "https://t.me/+example",
    "message_template": "Привет! Вот ссылка для вступления в чат: {invite_link}",
    "note": "operator-assisted flow",
    "requires_approval": true,
    "browser_target": {
      "client_id": "client-123",
      "tab_id": 0,
      "url_pattern": "web.telegram.org/k/#-2465948544",
      "active": true
    }
  }
}
```

## Execution Артефакты
По умолчанию execution-каталог:

```text
~/telegram_invite_jobs/chat_<slug>/executions/<timestamp>/
```

Внутри:
- `execution_plan.json`
- `execution.log`
- `execution_record.json`
- `execution_record.log`

## Команды

### `configure`
Сохраняет invite-link и browser-target в `invite_state.json`.

Пример:

```bash
cd /home/max/site-control-kit
python3 scripts/telegram_invite_executor.py configure \
  --job-dir "/home/max/telegram_invite_jobs/chat_-2465948544" \
  --invite-link "https://t.me/+example" \
  --message-template "Привет! Вот ссылка для вступления в чат: {invite_link}" \
  --url-pattern "web.telegram.org/k/#-2465948544" \
  --requires-approval
```

### `plan`
Готовит execution-plan для следующей пачки пользователей.

По умолчанию берёт пользователей из статуса `checked`.

Если передан `--reserve`, выбранные пользователи переводятся в `invite_link_created`, чтобы не попасть повторно в другую операторскую сессию.

Пример:

```bash
cd /home/max/site-control-kit
python3 scripts/telegram_invite_executor.py plan \
  --job-dir "/home/max/telegram_invite_jobs/chat_-2465948544" \
  --limit 3 \
  --reserve
```

### `open-chat`
Использует `site-control` browser CLI, чтобы открыть или активировать нужный Telegram-чат.

Логика такая:
- если в execution-config есть `tab_id`, будет `browser --tab-id ... activate`
- если есть `url_pattern`, будет `browser --url-pattern ... activate`
- иначе будет `browser new-tab <chat_url>`
- если `chat_url` хранится как публичный `https://t.me/<handle>`, executor перед `new-tab` автоматически нормализует его в `https://web.telegram.org/k/#@<handle>`, чтобы открыть именно Telegram Web, а не preview-страницу `t.me`

Сначала можно проверить dry-run:

```bash
cd /home/max/site-control-kit
python3 scripts/telegram_invite_executor.py open-chat \
  --job-dir "/home/max/telegram_invite_jobs/chat_-2465948544" \
  --dry-run
```

### `inspect-chat`
Считывает текущий Telegram Web view и возвращает:
- `page_url`;
- видимый `member_count`;
- исходный `member_count_text`;
- признак `add_members_visible`;
- `visible_member_count`;
- `visible_member_peers` с `peer_id/title` для уже видимых строк в секции участников справа.

Это штатная команда для проверки счётчика до и после `add-contact`.

Пример:

```bash
cd /home/max/site-control-kit
python3 scripts/telegram_invite_executor.py inspect-chat \
  --job-dir "/home/max/telegram_invite_jobs/chat_Zhirotop_shop" \
  --tab-id 614280764 \
  --skip-open
```

### `add-contact`
Пробует добавить ровно одного consented пользователя через Telegram Web `Add Members`.

Ограничения:
- пользователь должен уже быть в `invite_state.json`;
- у пользователя должен быть `consent: true`;
- команда работает по одному `--username`;
- финальный клик Telegram `Add` выполняется только с `--confirm-add`;
- live-режим теперь может сам снимать `inspect-chat`-снимки до и после клика `Add`;
- без проверяемого сигнала вступления результат нужно считать `requested`, не `joined`.

Dry-run:

```bash
cd /home/max/site-control-kit
python3 scripts/telegram_invite_executor.py add-contact \
  --job-dir "/home/max/telegram_invite_jobs/chat_Zhirotop_shop" \
  --username "@alice_123" \
  --tab-id 614280764 \
  --skip-open \
  --dry-run
```

Остановиться перед финальным внешним действием:

```bash
python3 scripts/telegram_invite_executor.py add-contact \
  --job-dir "/home/max/telegram_invite_jobs/chat_Zhirotop_shop" \
  --username "@alice_123" \
  --tab-id 614280764 \
  --skip-open
```

Реально нажать `Add`, автоматически снять before/after проверку и записать результат:

```bash
python3 scripts/telegram_invite_executor.py add-contact \
  --job-dir "/home/max/telegram_invite_jobs/chat_Zhirotop_shop" \
  --username "@alice_123" \
  --tab-id 614280764 \
  --skip-open \
  --confirm-add \
  --verify-membership \
  --verify-wait 10 \
  --record-result
```

Семантика результата:
- если выбранный `peer_id` появился в видимом списке участников после live add, `--record-result` может записать `joined`;
- если `member_count` вырос на before/after проверке, `--record-result` тоже может записать `joined`;
- если рост не подтверждён, даже после реального клика `Add` записывается `requested`;
- `execution_record.json` хранит не только steps, но и блок `verification` с before/after snapshot summary;
- в `verification.confirmed_signal` теперь различаются как минимум `member_list_visible_peer` и `member_count_delta`.

Проверенные селекторы Telegram Web:
- открыть панель: `#column-right .profile-container.can-add-members button.btn-circle.btn-corner`
- поиск: `.add-members-container .selector-search-input`
- строка кандидата: `.add-members-container .chatlist a.row[data-peer-id="<peer_id>"]`
- открыть подтверждение: `.add-members-container > .sidebar-content > button.btn-circle.btn-corner`
- финальная кнопка: `.popup-add-members .popup-buttons button:nth-child(1)`

### `record`
После ручного действия оператор записывает результат обратно в state.

Пример:

```bash
cd /home/max/site-control-kit
python3 scripts/telegram_invite_executor.py record \
  --job-dir "/home/max/telegram_invite_jobs/chat_-2465948544" \
  --username @alice_123 \
  --status sent \
  --reason manual_link_sent
```

### `report`
Показывает:
- текущее агрегированное состояние job;
- execution-config;
- последние execution-plan;
- последние execution-record;
- preview следующей execution-пачки.

## GUI Wrapper
Есть базовый wrapper:

```bash
bash scripts/telegram_invite_executor_gui.sh
```

Теперь GUI покрывает основные operator actions:
- `configure`
- `plan`
- `inspect-chat`
- `open-chat`
- `add-contact dry`
- `add-contact prepare`
- `add-contact live`
- `record`
- `report`

GUI не заменяет CLI, но теперь закрывает обычный one-user operator loop без ручной сборки команд.
В live-режиме GUI теперь умеет спросить:
- нужно ли автоматическое before/after `inspect-chat` подтверждение;
- сколько ждать перед повторной after-проверкой;
- записывать ли итог обратно в state.

## Безопасная Семантика
Этот слой не должен:
- автоматически массово добавлять пользователей в чат;
- переключать аккаунты для обхода лимитов;
- маскировать спам под “growth automation”.

Правильный сценарий:
1. менеджерит consented users;
2. готовит execution-plan;
3. открывает нужный чат через `site-control`;
4. оператор выполняет безопасный invite workflow или запускает `add-contact` на одного пользователя с auto-verification before/after;
5. результат записывается через `record`.

## Следующий Шаг
Следующий логичный шаг — не forced-add path, а:
- безопасный invite link / join request orchestration;
- более сильная проверка вступления за пределами текущего видимого member list, если нужный пользователь не попал в правую панель сразу;
- optional operator checklist для реального Telegram UI;
- затем живой smoke на поднятом browser bridge.

## Live Notes

### `@Kamaz_master1` -> `Zhirotop_shop`

Дата: `2026-04-24`

Проверен one-user flow:
- `add-user`;
- `run --limit 1 --to-status checked`;
- `configure --invite-link https://t.me/Zhirotop_shop`;
- `plan --limit 1 --reserve`;
- `open-chat`.

Результат:
- job: `/home/max/telegram_invite_jobs/chat_Zhirotop_shop`;
- execution plan: `/home/max/telegram_invite_jobs/chat_Zhirotop_shop/executions/20260424T142347Z/execution_plan.json`;
- Telegram Web tab: `614280505`;
- live URL: `https://web.telegram.org/k/#@Zhirotop_shop`;
- статус пользователя: `invite_link_created`.

Фактическая отправка сообщения пользователю не выполнялась.

### Live Add `@Kamaz_master1` -> `Zhirotop_shop`

Дата: `2026-04-25`

Проверен реальный UI-path `Add Members`:
- активная вкладка: `614280764`;
- live URL: `https://web.telegram.org/k/#@Zhirotop_shop`;
- поиск `Kamaz_master1` вернул контакт `Камаз`, `data-peer-id="1404471788"`;
- выбран контакт и открыт popup подтверждения;
- финальная кнопка `Add` нажата точным селектором `.popup-add-members .popup-buttons button:nth-child(1)`;
- popup закрылся;
- видимых ошибок не было;
- `joined/added` не найдено, счётчик остался `2 440 members`.

State записан осторожно:

```text
@kamaz_master1: invite_link_created -> requested
reason: live_add_members_confirmed_unverified_20260425
```

Артефакт:

```text
/home/max/telegram_invite_jobs/chat_Zhirotop_shop/executions/20260425T052501Z/execution_record.json
```

### Live Add `@olegoleg48` -> `Zhirotop_shop`

Дата: `2026-04-25`

Проверен тот же live path, но уже с отдельной проверкой счётчика до и после:
- `inspect-chat` до действия показал `2 440 members`;
- `add-contact --confirm-add --record-result` нашёл пользователя как `Oleg S`, `data-peer-id="1410391920"`;
- финальная кнопка `Add` была нажата;
- видимой ошибки Telegram не было;
- `inspect-chat` сразу после действия и после ожидания показал те же `2 440 members`.

State записан осторожно:

```text
@olegoleg48: checked -> requested
reason: live_add_members_confirmed_unverified
```

Практический вывод:
- `add-contact` доходит до реального `Add`;
- Telegram Web не подтверждает рост количества участников;
- для live add теперь нужно фиксировать не только popup/result state, но и `inspect-chat` before/after.

Артефакт:

```text
/home/max/telegram_invite_jobs/chat_Zhirotop_shop/executions/20260425T061336Z/execution_record.json
```

### Safe Smoke: `inspect-chat` после нормализации `t.me -> web.telegram`

Дата: `2026-04-25`

Проверено на том же job:
- `chat_url` в `invite_state.json` оставался `https://t.me/Zhirotop_shop`;
- `inspect-chat` без явного `tab_id` открыл новый tab через `browser new-tab https://web.telegram.org/k/#@Zhirotop_shop`;
- live URL вернулся как `https://web.telegram.org/k/#@Zhirotop_shop`;
- видимый счётчик прочитан как `2 667 members`;
- в правой панели разобран один видимый участник: `peer_id="1960795556"`, title `@joinhide9_bot`.

Артефакт:

```text
/tmp/tg_invite_executor_inspect_members_20260425_v3.json
```
